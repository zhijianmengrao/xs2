"""供应商失败率画像（R40，R38 §7.4 落地）回归锚。

覆盖两层：
- 纯函数聚合 ``src/workflow/run_profile.py``：单尝试/重试/旧数据兼容/
  坏时间戳/空 run，以及错误分类启发式（R38 §2.0 实测形态：530/524/502、
  超时打穿、流式停摆）。
- 只读端点 GET /api/workflows/{wf}/tasks/{task}/run-profile：200 载荷、
  404 三态（任务不存在 / 无 run_id / run 文件缺失），以及 B26/B28 家族
  纪律——查询不建目录、不写任何文件。

endpoint 测试全程 monkeypatch workflow_routes.WORKFLOWS_DIR 到临时目录
（B27 纪律：不触碰真实运行数据）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.workflow.run_profile import (build_run_profile, classify_error,
                                      compare_run_profiles, pick_previous_run)
from src.web import workflow_routes


def _attempt(n, status, error="", trigger="initial", started=None, completed=None):
    return {
        "attempt_number": n, "trigger": trigger, "status": status,
        "automatic_retry_count": n - 1, "output_repair_count": 0,
        "session_id": "", "started_at": started, "completed_at": completed,
        "error": error,
    }


def _node(node_id, attempts, status="completed", error="", **extra):
    entry = {
        "node_id": node_id, "status": status, "error": error,
        "attempt_count": len(attempts) or extra.get("attempt_count", 1),
        "attempt_history": attempts,
        "automatic_retry_count": max(len(attempts) - 1, 0),
        "output_repair_count": 0,
        "started_at": "2026-10-28T10:00:00+08:00",
        "completed_at": "2026-10-28T10:05:00+08:00",
    }
    entry.update(extra)
    return entry


# ---------- 纯函数聚合 ----------

def test_single_attempt_success_stage():
    profile = build_run_profile([_node("outline", [_attempt(1, "completed")])],
                                run_id="run-1", workflow_id="wf")
    assert profile["totals"] == {
        "stages": 1, "attempts": 1, "completed": 1, "failed": 0,
        "failure_rate": 0.0, "stages_with_multiple_attempts": [],
        "stages_with_failures": [], "error_classes": {},
    }
    stage = profile["stages"][0]
    assert stage["node_id"] == "outline"
    assert stage["duration_seconds"] == 300.0
    assert stage["attempts_detail"][0]["error_class"] == ""


def test_retry_profile_matches_r38_shape():
    """R38 实跑形态：build 2 次尝试（超时→成功）、character 3 次（530/524/成功）。"""
    nodes = [
        _node("build", [
            _attempt(1, "failed", error="stream chunk timed out after 600s",
                     started="2026-10-28T10:00:00+08:00",
                     completed="2026-10-28T10:10:00+08:00"),
            _attempt(2, "completed", trigger="automatic_retry",
                     started="2026-10-28T10:10:00+08:00",
                     completed="2026-10-28T10:50:00+08:00"),
        ]),
        _node("character", [
            _attempt(1, "failed", error="provider returned HTTP 530",
                     started="2026-10-28T11:00:00+08:00"),
            _attempt(2, "failed", error="HTTP 524 upstream timeout",
                     started="2026-10-28T11:20:00+08:00"),
            _attempt(3, "completed", trigger="automatic_retry",
                     started="2026-10-28T11:40:00+08:00"),
        ]),
    ]
    profile = build_run_profile(
        nodes, run_id="run-2", workflow_id="wf",
        started_at="2026-10-28T10:00:00+08:00",
        completed_at="2026-10-28T12:00:00+08:00")
    totals = profile["totals"]
    assert totals["stages"] == 2
    assert totals["attempts"] == 5
    assert totals["completed"] == 2
    assert totals["failed"] == 3
    assert totals["failure_rate"] == 0.6
    assert totals["stages_with_multiple_attempts"] == ["build", "character"]
    assert totals["stages_with_failures"] == ["build", "character"]
    assert totals["error_classes"] == {"timeout": 1, "http_5xx": 2}
    assert profile["wall_seconds"] == 7200.0
    build = next(s for s in profile["stages"] if s["node_id"] == "build")
    assert build["failure_rate"] == 0.5
    assert build["attempts_detail"][0]["error_class"] == "timeout"
    assert build["attempts_detail"][0]["duration_seconds"] == 600.0


def test_legacy_run_without_attempt_history():
    """旧数据兼容：无逐尝试历史时以 attempt_count 计数、终态近似成败。"""
    entry = {"node_id": "old-stage", "status": "failed", "error": "boom",
             "attempt_count": 3, "attempt_history": [],
             "automatic_retry_count": 2, "output_repair_count": 0,
             "started_at": None, "completed_at": None}
    profile = build_run_profile([entry])
    stage = profile["stages"][0]
    assert stage["attempts"] == 3
    assert stage["completed"] == 0
    assert stage["failed"] == 3
    assert stage["failure_rate"] == 1.0
    assert stage["attempts_detail"][0]["error_class"] == "other"
    assert stage["duration_seconds"] is None


def test_bad_timestamps_and_malformed_entries_dont_crash():
    profile = build_run_profile([
        {"node_id": "broken", "attempt_history": [{"attempt_number": 1}],
         "started_at": "not-a-date", "completed_at": 12345, "status": "completed"},
        "not-a-dict",
        {"node_id": "n2", "attempt_history": "garbage", "attempt_count": 0},
    ])
    assert profile["totals"]["stages"] == 2
    broken = profile["stages"][0]
    assert broken["duration_seconds"] is None
    assert broken["attempts_detail"][0]["duration_seconds"] is None


def test_empty_run_has_null_failure_rate():
    profile = build_run_profile([], run_id="run-3")
    assert profile["totals"]["attempts"] == 0
    assert profile["totals"]["failure_rate"] is None


def test_classify_error_buckets():
    assert classify_error("HTTP 530 from provider") == "http_5xx"
    assert classify_error("request timed out after 120s") == "timeout"
    assert classify_error("连接被重置") == "connection"
    assert classify_error("stream chunk 停摆") == "stream_stall"
    assert classify_error("") == ""
    assert classify_error("weird failure") == "other"


def test_engine_finalize_stamps_run_completed_at(tmp_path, monkeypatch):
    """R40 观察项修复回归：run 记录终态盖章（此前恒 null，画像 wall_seconds
    无法计算）；retry_waiting 是恢复中转而非终点，不盖章。"""
    import asyncio
    import src.config as config
    from types import SimpleNamespace

    from src.workflow.engine import WorkflowEngine
    from src.workflow.runtime_models import WorkflowRunRecord

    monkeypatch.setattr(config, "WORKFLOWS_DIR", tmp_path)
    engine = WorkflowEngine(SimpleNamespace(sessions={}))

    async def _finalize(record):
        await engine._finalize_run_artifacts("wf-x", "", record)

    record = WorkflowRunRecord(workflow_id="wf-x", status="completed")
    asyncio.run(_finalize(record))
    assert record.completed_at is not None
    persisted = json.loads(
        (tmp_path / "wf-x" / "runs" / f"{record.run_id}.json")
        .read_text(encoding="utf-8"))
    assert persisted["completed_at"] == record.completed_at

    waiting = WorkflowRunRecord(workflow_id="wf-x", status="retry_waiting")
    asyncio.run(_finalize(waiting))
    assert waiting.completed_at is None


# ---------- 只读端点 ----------

def _seed_run_tree(tmp_path: Path, *, task_payload: dict | None,
                   run_body: dict | None, run_id: str = "run-abc"):
    wf_dir = tmp_path / "wf-x"
    (wf_dir / "tasks").mkdir(parents=True)
    if task_payload is not None:
        (wf_dir / "tasks" / "task-1.json").write_text(
            json.dumps(task_payload, ensure_ascii=False), encoding="utf-8")
    if run_body is not None:
        (wf_dir / "runs").mkdir()
        (wf_dir / "runs" / f"{run_id}.json").write_text(
            json.dumps(run_body, ensure_ascii=False), encoding="utf-8")
    return wf_dir


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(workflow_routes, "WORKFLOWS_DIR", tmp_path)
    app = FastAPI()
    app.include_router(workflow_routes.router)
    with TestClient(app) as test_client:
        return test_client


_TASK = {"task_id": "task-1", "run_id": "run-abc", "status": "completed"}


def test_run_profile_endpoint_returns_aggregated_payload(tmp_path, monkeypatch):
    run_body = {
        "run_id": "run-abc", "workflow_id": "wf-x", "status": "completed",
        "started_at": "2026-10-28T10:00:00+08:00",
        "completed_at": "2026-10-28T10:30:00+08:00",
        "node_executions": [_node("build", [
            _attempt(1, "failed", error="HTTP 502 bad gateway"),
            _attempt(2, "completed", trigger="automatic_retry"),
        ])],
    }
    _seed_run_tree(tmp_path, task_payload=_TASK, run_body=run_body)
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/workflows/wf-x/tasks/task-1/run-profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run-abc"
    assert body["totals"]["attempts"] == 2
    assert body["totals"]["failed"] == 1
    assert body["totals"]["error_classes"] == {"http_5xx": 1}
    assert body["totals"]["stages_with_multiple_attempts"] == ["build"]


@pytest.mark.parametrize("task_payload,run_body,detail", [
    (None, {"run_id": "run-abc"}, "任务不存在"),
    (_TASK, None, "运行记录不存在"),          # task 引用 run 但 runs/ 无文件
    ({**_TASK, "run_id": None}, None, "任务尚无运行记录"),
])
def test_run_profile_endpoint_honest_404s(tmp_path, monkeypatch,
                                          task_payload, run_body, detail):
    _seed_run_tree(tmp_path, task_payload=task_payload, run_body=run_body)
    client = _client(tmp_path, monkeypatch)
    resp = client.get("/api/workflows/wf-x/tasks/task-1/run-profile")
    assert resp.status_code == 404
    assert resp.json()["detail"] == detail


def test_run_profile_endpoint_explicit_run_id_queries_history(tmp_path, monkeypatch):
    """R41：?run_id= 查任意历史 run，不再局限于任务 JSON 记录的最新 run。"""
    _seed_run_tree(tmp_path, task_payload=_TASK, run_body={
        "run_id": "run-abc", "status": "completed",
        "node_executions": [_node("build", [_attempt(1, "completed")])],
    })
    (tmp_path / "wf-x" / "runs" / "run-old.json").write_text(json.dumps({
        "run_id": "run-old", "status": "failed",
        "started_at": "2026-10-27T09:00:00+08:00",
        "completed_at": "2026-10-27T09:10:00+08:00",
        "node_executions": [_node("character", [
            _attempt(1, "failed", error="HTTP 530 from provider",
                     started="2026-10-27T09:00:00+08:00"),
            _attempt(2, "completed", trigger="automatic_retry",
                     started="2026-10-27T09:05:00+08:00"),
        ])],
    }, ensure_ascii=False), encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    latest = client.get("/api/workflows/wf-x/tasks/task-1/run-profile")
    assert latest.status_code == 200
    assert latest.json()["run_id"] == "run-abc"

    historical = client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?run_id=run-old")
    assert historical.status_code == 200
    body = historical.json()
    assert body["run_id"] == "run-old"
    assert body["status"] == "failed"
    assert body["totals"]["attempts"] == 2
    assert body["totals"]["error_classes"] == {"http_5xx": 1}
    assert body["stages"][0]["node_id"] == "character"


def test_run_profile_endpoint_run_id_validation(tmp_path, monkeypatch):
    """非法 run_id 拒 400（单规则 ^[\\w][\\w\\-]*$，穿越无从构造）；
    缺失 run 拒 404 且语义不变。"""
    _seed_run_tree(tmp_path, task_payload=_TASK, run_body={"run_id": "run-abc"})
    client = _client(tmp_path, monkeypatch)
    for bad in ("..%5C..%5Cevil", "..%2F..%2Fdata", "%2e%2e%2fescape", "a/b"):
        resp = client.get(f"/api/workflows/wf-x/tasks/task-1/run-profile?run_id={bad}")
        assert resp.status_code == 400, f"{bad} 应拒 400，实得 {resp.status_code}"
    missing = client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?run_id=run-ghost")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "运行记录不存在"


def test_run_profile_endpoint_creates_nothing(tmp_path, monkeypatch):
    """B26/B28 家族纪律：GET 画像端点对幻影任务/幻影 run 不得建目录。"""
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    client = _client(tmp_path, monkeypatch)
    for url in ("/api/workflows/wf-x/tasks/task-1/run-profile",
                "/api/workflows/phantom-wf/tasks/phantom-task/run-profile",
                "/api/workflows/wf-x/tasks/task-1/run-profile?run_id=run-ghost"):
        assert client.get(url).status_code in (404, 500)
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert after == before, "run-profile 端点查询即建目录（B26/B28 同族复发）"


# ---------- 跨 run 对比（R43） ----------

def _profile(node_specs, **kwargs):
    """按 {node_id: [attempt_status...]} 造一份 run 画像（供对比纯函数测试）。

    值也可以是 ``[[status...], [status...]]``——表示同一 node_id 在同一 run 内
    多次执行（如 agent_deep 循环 N 次），用于覆盖「按 node_id 汇总」口径。
    """
    entries = []
    for node_id, statuses in node_specs.items():
        runs = statuses if statuses and isinstance(statuses[0], list) else [statuses]
        for execution in runs:
            entries.append(_node(node_id, [
                _attempt(i + 1, s) for i, s in enumerate(execution)]))
    return build_run_profile(entries, **kwargs)


def test_compare_pools_repeated_nodes_and_uses_signed_deltas():
    """对比按 node_id 汇总（一 run 内可重复执行 N 次），差值恒为 current - previous。"""
    current = _profile({"agent_deep": [
        ["completed"], ["failed"], ["completed"], ["completed"]]}, run_id="run-new")
    previous = _profile({"agent_deep": [["completed"], ["completed"]]},
                        run_id="run-old")
    comparison = compare_run_profiles(current, previous)
    stage = comparison["stages"][0]
    assert stage["node_id"] == "agent_deep"
    assert stage["occurrences_current"] == 4
    assert stage["occurrences_previous"] == 2
    assert stage["attempts_current"] == 4
    assert stage["attempts_previous"] == 2
    assert stage["delta_attempts"] == 2
    assert stage["failed_current"] == 1
    assert stage["failed_previous"] == 0
    assert stage["failure_rate_current"] == 0.25
    assert stage["failure_rate_previous"] == 0.0
    assert stage["delta_failure_rate"] == 0.25   # 正值 = 退步
    assert stage["comparable"] is True
    assert comparison["previous_run_id"] == "run-old"
    assert comparison["totals"]["delta_attempts"] == 2
    assert comparison["totals"]["delta_failed"] == 1
    assert comparison["totals"]["delta_failure_rate"] == 0.25


def test_compare_improvement_is_negative():
    current = _profile({"build": ["completed"]}, run_id="run-new")
    previous = _profile({"build": ["failed", "failed", "completed"]}, run_id="run-old")
    stage = compare_run_profiles(current, previous)["stages"][0]
    assert stage["delta_failure_rate"] < 0          # 负值 = 改善
    assert stage["delta_failure_rate"] == round(0.0 - 2 / 3, 4)
    assert stage["delta_attempts"] == -2


def test_compare_stage_only_in_one_run_is_not_comparable():
    """一侧无该阶段 → comparable=False 且差值 None（不把「无数据」当 0%）。"""
    current = _profile({"build": ["completed"], "new_stage": ["failed"]},
                       run_id="run-new")
    previous = _profile({"build": ["completed"], "gone_stage": ["completed"]},
                        run_id="run-old")
    by_node = {s["node_id"]: s for s in compare_run_profiles(current, previous)["stages"]}
    added = by_node["new_stage"]
    assert added["comparable"] is False
    assert added["delta_failure_rate"] is None
    assert added["failure_rate_previous"] is None
    assert added["attempts_previous"] == 0
    removed = by_node["gone_stage"]
    assert removed["comparable"] is False
    assert removed["delta_failure_rate"] is None
    assert removed["failure_rate_current"] is None


def test_compare_empty_runs_stay_non_comparable():
    """两次空 run：总失败率差值必须诚实为 None 而非 0。"""
    empty = build_run_profile([], run_id="run-x")
    comparison = compare_run_profiles(empty, empty)
    assert comparison["totals"]["comparable"] is False
    assert comparison["totals"]["delta_failure_rate"] is None
    assert comparison["stages"] == []


def test_compare_delta_uses_unrounded_ratio():
    """差值用未舍入比值算：1/3 vs 0 的差值应是 0.3333 而不是舍入后判平。"""
    current = _profile({"s": ["failed", "completed", "completed"]}, run_id="run-new")
    previous = _profile({"s": ["completed"]}, run_id="run-old")
    stage = compare_run_profiles(current, previous)["stages"][0]
    assert stage["delta_failure_rate"] == 0.3333
    comparison = compare_run_profiles(current, previous)
    assert comparison["totals"]["delta_failure_rate"] == 0.3333


@pytest.mark.parametrize("current_started,current_mtime,older,expected", [
    ("2026-10-27T10:00:00+08:00", 1.9e9, "2026-10-26T10:00:00+08:00", "run-older"),
    ("2026-10-27T10:00:00+08:00", 1.9e9, "2026-10-28T10:00:00+08:00", None),  # 只有更晚的
    (None, 1.9e9, "2026-10-26T10:00:00+08:00", "run-older"),  # 当前缺 started_at → 用 mtime
])
def test_pick_previous_run_picks_strictly_older(current_started, current_mtime,
                                               older, expected):
    """「上一次 run」= 排序键严格更小的最大者；没有更早的就不冒充。"""
    current = {"run_id": "run-cur", "started_at": current_started,
               "mtime": current_mtime}
    candidates = [
        {"run_id": "run-older", "started_at": older, "mtime": 1.8e9},
        {"run_id": "run-cur", "started_at": current_started, "mtime": current_mtime},
    ]
    picked = pick_previous_run(current, candidates)
    assert (picked or {}).get("run_id") == expected


def test_pick_previous_run_falls_back_to_mtime_for_unparsable_time():
    """started_at 坏/缺时回落 mtime 比较，且不与可解析的 aware 值混比抛错。

    当前 run 的 started_at 是废值、mtime=2000（unix 秒，远早于 2026 年），
    因此 run-b（2026-10-01，可解析）比它**更晚**、run-a（mtime=1000）更早。
    """
    current = {"run_id": "run-cur", "started_at": "not-a-date", "mtime": 2000.0}
    candidates = [
        {"run_id": "run-a", "started_at": None, "mtime": 1000.0},
        {"run_id": "run-b", "started_at": "2026-10-01T00:00:00+08:00", "mtime": 3000.0},
    ]
    picked = pick_previous_run(current, candidates)
    assert picked is not None and picked["run_id"] == "run-a"


# ---------- 端点 ?compare=true ----------

def _seed_compare_tree(tmp_path: Path) -> None:
    """种子：task 指向 run-new，runs/ 里另有更早的 run-old。"""
    wf_dir = tmp_path / "wf-x"
    (wf_dir / "tasks").mkdir(parents=True)
    (wf_dir / "tasks" / "task-1.json").write_text(
        json.dumps({"task_id": "task-1", "run_id": "run-new", "status": "completed"}),
        encoding="utf-8")
    (wf_dir / "runs").mkdir()
    (wf_dir / "runs" / "run-new.json").write_text(json.dumps({
        "run_id": "run-new", "status": "completed",
        "started_at": "2026-10-27T10:00:00+08:00",
        "completed_at": "2026-10-27T10:30:00+08:00",
        "node_executions": [_node("build", [
            _attempt(1, "completed", started="2026-10-27T10:00:00+08:00",
                     completed="2026-10-27T10:30:00+08:00")])],
    }, ensure_ascii=False), encoding="utf-8")
    (wf_dir / "runs" / "run-old.json").write_text(json.dumps({
        "run_id": "run-old", "status": "failed",
        "started_at": "2026-10-26T10:00:00+08:00",
        "completed_at": "2026-10-26T10:20:00+08:00",
        "node_executions": [_node("build", [
            _attempt(1, "failed", error="HTTP 502",
                     started="2026-10-26T10:00:00+08:00",
                     completed="2026-10-26T10:05:00+08:00"),
            _attempt(2, "completed", trigger="automatic_retry",
                     started="2026-10-26T10:05:00+08:00",
                     completed="2026-10-26T10:20:00+08:00")])],
    }, ensure_ascii=False), encoding="utf-8")


def test_run_profile_endpoint_compare_block(tmp_path, monkeypatch):
    """?compare=true 返回上一次 run 的对比块，且不改变原有画像字段。"""
    _seed_compare_tree(tmp_path)
    client = _client(tmp_path, monkeypatch)
    body = client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?compare=true").json()
    assert body["run_id"] == "run-new"
    assert body["totals"]["attempts"] == 1          # 原画像字段不变
    comparison = body["comparison"]
    assert comparison["previous_run_id"] == "run-old"
    assert comparison["totals"]["delta_attempts"] == -1
    assert comparison["totals"]["delta_failed"] == -1
    # 本次 0% vs 上次 50% → 改善 50 个百分点
    assert comparison["totals"]["delta_failure_rate"] == -0.5
    assert comparison["stages"][0]["node_id"] == "build"
    assert comparison["stages"][0]["delta_attempts"] == -1


def test_run_profile_endpoint_without_compare_has_no_comparison_key(tmp_path, monkeypatch):
    """缺省（不带 compare）不返回 comparison 键——不加查询参数就没有多余扫描。"""
    _seed_compare_tree(tmp_path)
    client = _client(tmp_path, monkeypatch)
    body = client.get("/api/workflows/wf-x/tasks/task-1/run-profile").json()
    assert "comparison" not in body


def test_run_profile_endpoint_compare_on_oldest_run_is_null(tmp_path, monkeypatch):
    """查最早那个 run 的对比 → comparison 为 null（没有更早的 run 可对比）。"""
    _seed_compare_tree(tmp_path)
    client = _client(tmp_path, monkeypatch)
    body = client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?run_id=run-old&compare=true"
    ).json()
    assert body["run_id"] == "run-old"
    assert body["comparison"] is None


def test_run_profile_endpoint_compare_skips_corrupt_sibling(tmp_path, monkeypatch):
    """损坏的兄弟 run 记录不参与「上一次 run」选择，也不让请求失败。"""
    _seed_compare_tree(tmp_path)
    (tmp_path / "wf-x" / "runs" / "run-broken.json").write_text(
        "{not json", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)
    body = client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?compare=true").json()
    assert body["comparison"]["previous_run_id"] == "run-old"


def test_run_profile_endpoint_compare_creates_nothing(tmp_path, monkeypatch):
    """?compare=true 仍属 GET 只读面：扫 runs/ 目录不得新建任何文件。"""
    _seed_compare_tree(tmp_path)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    client = _client(tmp_path, monkeypatch)
    assert client.get(
        "/api/workflows/wf-x/tasks/task-1/run-profile?compare=true").status_code == 200
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert after == before, "compare 查询即建目录（B26/B28 同族复发）"
