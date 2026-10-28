"""供应商失败率挖矿脚本（``scripts/provider_failure_profile.py``）回归锚。

R41 起该脚本被写进「每轮收官固定跑」的流程（``--summary`` 输出贴进交接文档
形成时间序列），因此需要钉住两件事：

1. 聚合口径稳定——同 workflow 多 run 的 attempts/failed/failure_rate 汇总，
   时间序列逐轮可比的前提是口径不变。
2. **严格只读**——扫完 tmp 目录后文件树必须逐字节不变（不写、不建、不删）。

测试全部走 ``collect_profiles`` / ``summarize`` 并以 ``tmp_path`` 注入，
不触碰真实 ``data/workflows``（B27 纪律）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "provider_failure_profile.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("provider_failure_profile", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["provider_failure_profile"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mining():
    return _load_module()


def _attempt(n, status, error=""):
    return {"attempt_number": n, "trigger": "initial" if n == 1 else "automatic_retry",
            "status": status, "error": error, "automatic_retry_count": n - 1,
            "output_repair_count": 0, "session_id": "",
            "started_at": f"2026-10-27T10:0{n}:00+08:00",
            "completed_at": f"2026-10-27T10:0{n}:30+08:00"}


def _run(run_id, status, node_executions):
    return {"run_id": run_id, "workflow_id": "wf", "status": status,
            "started_at": "2026-10-27T10:00:00+08:00",
            "completed_at": "2026-10-27T10:30:00+08:00",
            "node_executions": node_executions}


def _node(node_id, attempts):
    return {"node_id": node_id, "status": attempts[-1]["status"],
            "error": attempts[-1]["error"], "attempt_count": len(attempts),
            "attempt_history": attempts,
            "automatic_retry_count": max(len(attempts) - 1, 0),
            "output_repair_count": 0,
            "started_at": "2026-10-27T10:00:00+08:00",
            "completed_at": "2026-10-27T10:30:00+08:00"}


def _seed(root: Path) -> Path:
    wf = root / "wf-a"
    (wf / "runs").mkdir(parents=True)
    # run-2（名字更大 → 排序更新）复现重试形态：agent 2 次（超时→成功）
    (wf / "runs" / "run-b.json").write_text(json.dumps(_run("run-b", "completed", [
        _node("agent_deep", [
            _attempt(1, "failed", "stream chunk timed out after 600s"),
            _attempt(2, "completed"),
        ]),
        _node("script_done", [_attempt(1, "completed")]),
    ]), ensure_ascii=False), encoding="utf-8")
    # run-1：全成功
    (wf / "runs" / "run-a.json").write_text(json.dumps(_run("run-a", "completed", [
        _node("agent_deep", [_attempt(1, "completed")]),
        _node("script_done", [_attempt(1, "completed")]),
    ]), ensure_ascii=False), encoding="utf-8")
    # 坏 JSON 与空 runs 目录都必须被跳过而非崩溃
    (wf / "runs" / "run-broken.json").write_text("{not json", encoding="utf-8")
    (root / "wf-empty" / "runs").mkdir(parents=True)
    (root / "wf-noruns").mkdir()
    return root


def test_collect_and_summarize_aggregates_across_runs(mining, tmp_path):
    _seed(tmp_path)
    by_workflow = mining.collect_profiles(tmp_path, limit=10)

    assert set(by_workflow) == {"wf-a"}, "只有含 run 文件的 workflow 入选"
    profiles = by_workflow["wf-a"]
    assert [p["run_id"] for p in profiles] == ["run-b", "run-a"], "按文件名倒序取最近 run"
    assert profiles[0]["totals"]["failed"] == 1
    assert profiles[0]["totals"]["error_classes"] == {"timeout": 1}

    rows = mining.summarize(by_workflow)
    assert len(rows) == 1
    row = rows[0]
    assert row["workflow"] == "wf-a"
    assert row["runs"] == 2
    assert row["attempts"] == 5, "2 次 agent 重试 + 2 次 script + 1 次 agent"
    assert row["failed"] == 1
    assert row["failure_rate"] == 0.2
    assert row["failing_stages"] == ["agent_deep"]
    assert row["error_classes"] == {"timeout": 1}


def test_limit_truncates_per_workflow(mining, tmp_path):
    _seed(tmp_path)
    by_workflow = mining.collect_profiles(tmp_path, limit=1)
    assert len(by_workflow["wf-a"]) == 1
    assert by_workflow["wf-a"][0]["run_id"] == "run-b"


def test_workflow_filter_isolates(mining, tmp_path):
    _seed(tmp_path)
    assert mining.collect_profiles(tmp_path, workflow_filter="wf-a", limit=10).keys() == {"wf-a"}
    assert mining.collect_profiles(tmp_path, workflow_filter="wf-nope", limit=10) == {}


def test_summary_is_empty_for_missing_dir(mining, tmp_path):
    """workflows 目录不存在时诚实空结果，不抛异常（首次装机/空数据）。"""
    assert mining.collect_profiles(tmp_path / "does-not-exist") == {}
    assert mining.summarize({}) == []


def test_collect_is_strictly_read_only(mining, tmp_path):
    """时间序列的可信前提：扫描不得改动文件树（不写、不建、不删）。"""
    _seed(tmp_path)
    before = {str(p.relative_to(tmp_path)): p.stat().st_mtime_ns
              for p in sorted(tmp_path.rglob("*"))}
    mining.collect_profiles(tmp_path, limit=10)
    mining.summarize(mining.collect_profiles(tmp_path, limit=10))
    after = {str(p.relative_to(tmp_path)): p.stat().st_mtime_ns
             for p in sorted(tmp_path.rglob("*"))}
    assert after == before, "挖矿脚本改动了 run 数据（只读纪律破坏）"
