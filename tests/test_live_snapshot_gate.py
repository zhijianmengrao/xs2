"""真实数据面的闸门接线（R47）。

R46 把闸门接进了 CI，但判的是 ``tests/fixtures/run_samples`` ——**固定**样本，
它自己也在 §2.1 写明「保护的命题是闸门与脚本不退化，不是供应商今天健康」。
本文件钉住 R47 补上的那一半：对入库的**真实 run 快照**判失败率。

四类回归，全部静态或纯函数可验：
1. CI 真的有第二个闸门 step，且指向快照而不是 fixture；
2. 快照与其元数据一致（内容变了没重导 → 会以退出码 4 失败）；
3. 阈值从快照自身算，不是写死的数字（写死会在重导后静默失准）；
4. 快照不含内容载荷（小说正文/轨迹/token 明细不该进仓库）。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import check_live_snapshot_gate as live_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SNAPSHOT_ROOT = REPO_ROOT / "tests" / "fixtures" / "live_snapshot"


def _load_ci() -> dict:
    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _backend_steps() -> list[dict]:
    jobs = _load_ci().get("jobs")
    assert isinstance(jobs, dict)
    backend = jobs.get("backend")
    assert backend is not None, "ci.yml 缺少 backend job"
    steps = backend.get("steps")
    assert isinstance(steps, list)
    return steps


def _live_gate_step() -> dict:
    hits = [s for s in _backend_steps()
            if "check_live_snapshot_gate.py" in str(s.get("run", ""))]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处调用真实快照闸门"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


# ------------------------------------------------- CI 真的对真实数据判闸门
def test_ci_runs_the_live_snapshot_gate() -> None:
    """真实数据面必须真的挂在 CI 上 —— 只有 fixture 自检等于只测了测试。"""
    step = _live_gate_step()
    assert "python scripts/check_live_snapshot_gate.py" in str(step["run"])


def test_ci_live_gate_points_at_the_snapshot_not_the_fixture() -> None:
    """指向 fixture 就退化成 R46 那一步，真实数据面等于没接线。"""
    step = _live_gate_step()
    env = step.get("env") or {}
    data_dir = str(env.get("DETERMINFLOW_DATA_DIR", ""))
    assert "live_snapshot" in data_dir, (
        f"真实数据闸门的 DETERMINFLOW_DATA_DIR 应指向 live_snapshot，实得 {data_dir!r}"
    )
    assert "run_samples" not in data_dir, (
        "真实数据闸门不得指向固定 fixture —— 那是 R46 自检 step 的职责"
    )


def test_ci_keeps_the_fixture_self_test_alongside() -> None:
    """两个闸门并存：fixture 自检不能再被真实数据那一步顶掉。"""
    runs = [s for s in _backend_steps()
            if "provider_failure_profile.py" in str(s.get("run", ""))]
    assert runs, "fixture 三态自检步骤消失了"


# ------------------------------------------------- 快照与元数据一致
def test_snapshot_metadata_matches_its_content() -> None:
    """元数据必须是内容复算的结果，否则闸门拿旧阈值判新内容。"""
    meta_path = SNAPSHOT_ROOT / "snapshot-meta.json"
    assert meta_path.is_file(), "快照缺少 snapshot-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    recorded = meta["totals"]
    attempts, failed = live_gate.recompute_totals(SNAPSHOT_ROOT / "workflows")
    assert attempts == recorded["attempts"], (
        f"元数据 attempts={recorded['attempts']} 与内容复算 {attempts} 不一致；"
        "改过快照就要重导"
    )
    assert failed == recorded["failed"]


def test_snapshot_holds_real_failures_and_retries() -> None:
    """空快照或零失败会让闸门恒通过——与 R46 §1 的「静默失效」同类。"""
    attempts, failed = live_gate.recompute_totals(SNAPSHOT_ROOT / "workflows")
    assert attempts >= 100, f"快照只有 {attempts} 次尝试，样本太小判不出东西"
    assert failed > 0, "快照零失败，闸门失去可判性"


# ------------------------------------------------- 阈值不是写死的
def _threshold_from(message: str) -> float:
    """从判定说明里取出实际使用的阈值数值（"未超出阈值 13.7%（..."）。"""
    import re

    match = re.search(r"阈值\s*([0-9.]+)%", message)
    assert match, f"判定说明里没有阈值数字：{message}"
    return float(match.group(1))


def test_threshold_is_derived_from_the_snapshot() -> None:
    """阈值跟着实测值走：同一份快照换余量，**阈值数值**必须跟着变。

    只断言「说明不同」是不够的——说明里本来就含余量文字，写死阈值的变异能
    骗过去（R47 实测：第一版断言就漏了）。这里直接比数字。
    """
    meta = json.loads((SNAPSHOT_ROOT / "snapshot-meta.json").read_text(encoding="utf-8"))
    totals = meta["totals"]
    measured = totals["failed"] / totals["attempts"] * 100

    code_tight, msg_tight = live_gate.evaluate(SNAPSHOT_ROOT, margin=0.0)
    code_loose, msg_loose = live_gate.evaluate(SNAPSHOT_ROOT, margin=50.0)
    assert code_tight == live_gate.EXIT_OK
    assert code_loose == live_gate.EXIT_OK

    assert abs(_threshold_from(msg_tight) - measured) < 0.15, (
        f"余量 0 时阈值应等于实测 {measured:.2f}%，实得 {_threshold_from(msg_tight)}")
    assert abs(_threshold_from(msg_loose) - min(100.0, measured + 50.0)) < 0.15, (
        f"余量 50 时阈值应约为 {measured + 50:.2f}%，实得 {_threshold_from(msg_loose)}")


def test_margin_zero_still_passes_on_unchanged_snapshot() -> None:
    """余量归零时「实测等于阈值」仍应通过（严格大于才触发）。"""
    code, message = live_gate.evaluate(SNAPSHOT_ROOT, margin=0.0)
    assert code == live_gate.EXIT_OK, message


# ------------------------------------------------- 元数据漂移必须显形
def test_gate_detects_metadata_drift(tmp_path: Path) -> None:
    """内容改了但元数据没重导 → 退出码 4，而不是拿旧阈值静默判过。"""
    (tmp_path / "workflows" / "wf").mkdir(parents=True)
    (tmp_path / "workflows" / "wf" / "runs").mkdir()
    (tmp_path / "workflows" / "wf" / "runs" / "run-x.json").write_text(
        json.dumps({
            "run_id": "run-x", "status": "completed",
            "node_executions": [{
                "node_id": "stage", "status": "completed",
                "attempt_count": 1, "attempt_history": [{
                    "attempt_number": 1, "trigger": "initial",
                    "status": "completed", "error": "",
                }],
            }],
        }), encoding="utf-8")
    # 元数据声称 5 次尝试，内容只有 1 次
    (tmp_path / "snapshot-meta.json").write_text(
        json.dumps({"totals": {"attempts": 5, "failed": 1}}), encoding="utf-8")

    code, message = live_gate.evaluate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message
    assert "不一致" in message


def test_gate_reports_no_sample_when_snapshot_missing(tmp_path: Path) -> None:
    code, message = live_gate.evaluate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message


# ------------------------------------------------- 快照不含内容载荷
def test_snapshot_has_no_content_payload() -> None:
    """裁剪纪律：小说正文/轨迹/token 明细不得进仓库（快照要入库）。"""
    forbidden = {"summary", "input_snapshot", "iteration_history", "outputs",
                 "token_usage_calls", "upstream_summary_snapshot",
                 "output_repair_history"}
    files = sorted(SNAPSHOT_ROOT.glob("workflows/*/runs/run-*.json"))
    assert files, "快照为空"
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for node in payload["node_executions"]:
            leaked = forbidden & set(node)
            assert not leaked, f"{path.name} 的 {node.get('node_id')} 仍带载荷字段 {leaked}"


def test_snapshot_is_small_enough_to_commit() -> None:
    files = sorted(SNAPSHOT_ROOT.glob("workflows/*/runs/run-*.json"))
    total = sum(p.stat().st_size for p in files)
    assert total < 400_000, (
        f"快照总量 {total} 字节；真实 run 单个可达 290KB，裁剪后应远小于此"
    )
