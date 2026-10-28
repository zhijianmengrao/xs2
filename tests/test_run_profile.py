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

from src.workflow.run_profile import build_run_profile, classify_error
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


def test_run_profile_endpoint_creates_nothing(tmp_path, monkeypatch):
    """B26/B28 家族纪律：GET 画像端点对幻影任务/幻影 run 不得建目录。"""
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    client = _client(tmp_path, monkeypatch)
    for url in ("/api/workflows/wf-x/tasks/task-1/run-profile",
                "/api/workflows/phantom-wf/tasks/phantom-task/run-profile"):
        assert client.get(url).status_code in (404, 500)
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert after == before, "run-profile 端点查询即建目录（B26/B28 同族复发）"
