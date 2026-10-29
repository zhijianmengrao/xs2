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
    """失败率闸门那一步（R47）。按「不带判据开关」定位，不按名字。

    R51 给同一脚本加了 ``--check-sample-size`` 的第二处调用，所以不能再按
    「有几个 step 调了这个脚本」来定位——那样每加一条判据都要改一处测试。
    这里按「调了脚本但没带任何 ``--check-*`` 开关」找失败率闸门本身。
    """
    hits = [
        s for s in _backend_steps()
        if "check_live_snapshot_gate.py" in str(s.get("run", ""))
        and "--check-" not in str(s.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处调用失败率闸门（不带 --check-*）"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def _windows_backend_steps() -> list[dict]:
    jobs = _load_ci().get("jobs")
    assert isinstance(jobs, dict)
    windows = jobs.get("windows-backend")
    assert windows is not None, "ci.yml 缺少 windows-backend job"
    steps = windows.get("steps")
    assert isinstance(steps, list)
    return steps


def _sample_size_step() -> dict:
    """样本量闸门那一步（R51）。"""
    hits = [
        s for s in _backend_steps()
        if "--check-sample-size" in str(s.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处跑 --check-sample-size"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def _windows_sample_size_step() -> dict:
    """Windows runner 上的样本量闸门（R52）。"""
    hits = [
        s for s in _windows_backend_steps()
        if "--check-sample-size" in str(s.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 windows-backend job 必须且只能有一处跑 --check-sample-size"
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


# ------------------------------------------------- 快照保鲜（R48）
def _write_snapshot(root: Path, exported_at: object, *, with_key: bool = True) -> None:
    (root / "workflows" / "wf" / "runs").mkdir(parents=True, exist_ok=True)
    (root / "workflows" / "wf" / "runs" / "run-a.json").write_text(
        json.dumps({"run_id": "run-a", "status": "completed",
                    "node_executions": []}), encoding="utf-8")
    meta: dict = {"totals": {"attempts": 0, "failed": 0}}
    if with_key:
        meta["exported_at"] = exported_at
    (root / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")


def _write_real_run(root: Path, started_at: str) -> None:
    (root / "wf" / "runs").mkdir(parents=True, exist_ok=True)
    (root / "wf" / "runs" / "run-real.json").write_text(
        json.dumps({"run_id": "run-real", "status": "running",
                    "started_at": started_at, "completed_at": None}),
        encoding="utf-8")


def test_stale_check_flags_snapshot_older_than_real_data(tmp_path: Path) -> None:
    """快照滞后超容忍 → 退出码 5，与「失败率超阈」的 1 分开。"""
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot(snap, "2026-01-01T00:00:00+00:00")
    _write_real_run(real, "2026-02-01T00:00:00+00:00")

    code, message = live_gate.check_stale(snap, real, max_lag_days=7.0)
    assert code == live_gate.EXIT_STALE, message
    assert "过期" in message
    # 过期与超阈必须是不同退出码，否则 CI 日志里两种失效混成一类
    assert live_gate.EXIT_STALE != live_gate.EXIT_GATE_TRIGGERED


def test_stale_check_passes_when_snapshot_is_current(tmp_path: Path) -> None:
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot(snap, "2026-02-01T00:00:00+00:00")
    _write_real_run(real, "2026-02-02T00:00:00+00:00")

    code, message = live_gate.check_stale(snap, real, max_lag_days=7.0)
    assert code == live_gate.EXIT_OK, message


def test_stale_check_reads_in_flight_runs_not_just_completed(tmp_path: Path) -> None:
    """只看 completed_at 会对「正在进行中的新 run」失明，也会对 B31 前的旧数据失明。"""
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot(snap, "2026-01-01T00:00:00+00:00")
    # completed_at 为 None，只有 started_at 能证明数据比快照新
    _write_real_run(real, "2026-03-01T00:00:00+00:00")

    code, message = live_gate.check_stale(snap, real, max_lag_days=7.0)
    assert code == live_gate.EXIT_STALE, message


def test_stale_check_reports_no_sample_when_real_data_absent(tmp_path: Path) -> None:
    """CI 检出里没有 data/workflows —— 必须报「判不到」，不能假绿。"""
    snap = tmp_path / "snap"
    _write_snapshot(snap, "2026-01-01T00:00:00+00:00")

    code, message = live_gate.check_stale(snap, tmp_path / "missing", max_lag_days=7.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message
    assert code != live_gate.EXIT_OK


def test_stale_check_requires_exported_at(tmp_path: Path) -> None:
    """元数据没有 exported_at 时不能默认「够新」，只能报判不到。"""
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot(snap, None, with_key=False)
    _write_real_run(real, "2026-02-01T00:00:00+00:00")

    code, message = live_gate.check_stale(snap, real, max_lag_days=7.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message
    assert "exported_at" in message


def test_stale_check_is_not_wired_into_ci() -> None:
    """CI 检出没有真实数据，接进去只会变成永远绿的防护（R47 §2.3 的教训）。"""
    for step in _backend_steps():
        assert "--check-stale" not in str(step.get("run", "")), (
            "快照保鲜是轮次收官动作，不该作为 CI step：CI 里没有 data/workflows"
        )


# ------------------------------------------------- 快照覆盖度（R49）
def _write_snapshot_workflows(root: Path, names: list[str]) -> None:
    """快照里放若干「有 run 记录」的工作流。"""
    (root / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "snapshot-meta.json").write_text(
        json.dumps({"totals": {"attempts": 0, "failed": 0},
                    "exported_at": "2026-02-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    for name in names:
        runs = root / "workflows" / name / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "run-x.json").write_text(
            json.dumps({"run_id": "run-x", "status": "completed",
                        "node_executions": []}), encoding="utf-8")


def _write_real_workflows(root: Path, names: list[str]) -> None:
    for name in names:
        runs = root / name / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "run-real.json").write_text(
            json.dumps({"run_id": "run-real", "status": "completed",
                        "node_executions": []}), encoding="utf-8")


def test_coverage_flags_workflow_missing_from_snapshot(tmp_path: Path) -> None:
    """真实跑过但快照里没有的 workflow → 退出码 6，且 6 与 5/1 都不同。"""
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot_workflows(snap, ["wf-old"])
    _write_real_workflows(real, ["wf-old", "wf-new"])

    code, message = live_gate.check_coverage(snap, real)
    assert code == live_gate.EXIT_COVERAGE_GAP, message
    assert "wf-new" in message
    assert code != live_gate.EXIT_STALE
    assert code != live_gate.EXIT_GATE_TRIGGERED


def test_coverage_does_not_confuse_time_with_scope(tmp_path: Path) -> None:
    """快照「尚新」也不能替覆盖度作保——这是 R48 §8-2 记的那个缺口。

    时间全对（真实最新时间早于导出时间），但真实数据里多了一个 workflow。
    ``--check-stale`` 会绿，``--check-coverage`` 必须红。
    """
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot_workflows(snap, ["wf-old"])
    _write_real_workflows(real, ["wf-old", "wf-added"])
    for name in ("wf-old", "wf-added"):
        (real / name / "runs" / "run-real.json").write_text(
            json.dumps({"run_id": "run-real", "status": "completed",
                        "started_at": "2026-01-01T00:00:00+00:00",
                        "completed_at": "2026-01-01T00:00:10+00:00",
                        "node_executions": []}),
            encoding="utf-8",
        )

    stale_code, _ = live_gate.check_stale(snap, real, max_lag_days=7.0)
    assert stale_code == live_gate.EXIT_OK, "本用例的前提是新鲜度判据为绿"

    code, message = live_gate.check_coverage(snap, real)
    assert code == live_gate.EXIT_COVERAGE_GAP, message


def test_coverage_passes_when_all_real_workflows_are_sampled(tmp_path: Path) -> None:
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot_workflows(snap, ["wf-a", "wf-b", "wf-c"])
    _write_real_workflows(real, ["wf-a", "wf-b"])

    code, message = live_gate.check_coverage(snap, real)
    assert code == live_gate.EXIT_OK, message


def test_coverage_ignores_snapshot_only_workflows(tmp_path: Path) -> None:
    """快照里有、真实已删：只是冗余样本，不影响代表性，不得报缺口。"""
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_snapshot_workflows(snap, ["wf-live", "wf-deleted"])
    _write_real_workflows(real, ["wf-live"])

    code, message = live_gate.check_coverage(snap, real)
    assert code == live_gate.EXIT_OK, message


def test_coverage_reports_no_sample_when_real_data_absent(tmp_path: Path) -> None:
    """CI 检出里没有 data/workflows —— 必须报判不到，不能假绿。"""
    snap = tmp_path / "snap"
    _write_snapshot_workflows(snap, ["wf-a"])

    code, message = live_gate.check_coverage(snap, tmp_path / "missing")
    assert code == live_gate.EXIT_NO_SAMPLE, message


def test_coverage_requires_snapshot_metadata(tmp_path: Path) -> None:
    snap, real = tmp_path / "snap", tmp_path / "real"
    _write_real_workflows(real, ["wf-a"])
    (snap / "workflows" / "wf-a" / "runs").mkdir(parents=True)
    (snap / "workflows" / "wf-a" / "runs" / "run-x.json").write_text(
        json.dumps({"run_id": "run-x", "node_executions": []}), encoding="utf-8")

    code, message = live_gate.check_coverage(snap, real)
    assert code == live_gate.EXIT_NO_SAMPLE, message


def test_coverage_check_is_not_wired_into_ci() -> None:
    """与 --check-stale 同理：CI 无真实数据，接进去只会变成永远判不到的步骤。"""
    for step in _backend_steps():
        assert "--check-coverage" not in str(step.get("run", "")), (
            "快照覆盖度是轮次收官动作，不该作为 CI step：CI 里没有 data/workflows"
        )


# ------------------------------------------------- 样本量厚度（R51）
def _write_snapshot_with_totals(root: Path, attempts: int, failed: int) -> None:
    """造一份「内容与元数据一致」的快照：单 workflow、单 run、attempts 次尝试。

    内容必须真的产生 ``attempts`` 次尝试，否则 ``check_sample_size`` 会以退出码
    4（元数据漂移）拒绝——那正是它该有的行为，所以这里的 helper 必须造对。
    """
    runs = root / "workflows" / "wf-a" / "runs"
    runs.mkdir(parents=True)
    nodes = []
    for index in range(attempts):
        status = "failed" if index < failed else "completed"
        nodes.append({
            "node_id": f"n{index}",
            "status": status,
            "attempt_history": [{
                "attempt_number": 1, "trigger": "initial", "status": status,
            }],
        })
    (runs / "run-x.json").write_text(
        json.dumps({"run_id": "run-x", "status": "completed",
                    "node_executions": nodes}), encoding="utf-8")
    (root / "snapshot-meta.json").write_text(
        json.dumps({"totals": {"attempts": attempts, "failed": failed},
                    "exported_at": "2026-02-01T00:00:00+00:00"}),
        encoding="utf-8")


def test_sample_size_passes_on_the_committed_snapshot() -> None:
    """入库快照自己必须过——否则 CI 一接就红。"""
    code, message = live_gate.check_sample_size(SNAPSHOT_ROOT, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_sample_size_rejects_a_thin_snapshot(tmp_path: Path) -> None:
    """14 次尝试 1 次失败：失败率 7.1% 的半宽 ~13.8 个百分点，超过 10 的余量。

    这正是 R49 §7-6 挂账的那个失效形状：``--check-coverage`` 会说「都覆盖了」，
    而这份快照的失败率其实粗到不能当基线。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=14, failed=1)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_THIN_SAMPLE, message
    assert "14" in message


def test_sample_size_judges_precision_not_run_count(tmp_path: Path) -> None:
    """一次 run 里 200 次尝试，精度不该比 5 次 run 共 10 次尝试差。

    若判据写成「要有 N 条 run」，这条会红——那正是把「样本量」误当「run 数」
    的回归形状。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=200, failed=1)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_sample_size_does_not_let_zero_failures_pass_for_free(tmp_path: Path) -> None:
    """零失败时比例点估计恒为 0，正态近似会给「半宽 0」——那是恒绿的坑。

    2 次尝试 0 失败的真实单侧 95% 上界高达 ~78%，绝不能判合格。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=2, failed=0)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_THIN_SAMPLE, message
    assert "77" in message or "78" in message, (
        f"零失败分支没有给出单侧上界，实际说明：{message!r}"
    )


def test_sample_size_accepts_enough_zero_failure_attempts(tmp_path: Path) -> None:
    """60 次尝试 0 失败：单侧上界 ~4.9% ≤ 10，应当通过。

    与上一条互为正反面：只验「薄的要拒」会让「一律拒绝」也绿灯。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=60, failed=0)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_sample_size_detects_metadata_drift(tmp_path: Path) -> None:
    """改了内容没重导元数据 → 退出码 4，不是拿旧数字判新内容。"""
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=60, failed=0)
    # 往内容里塞一个带尝试的 run，元数据不变 → 复算 61 次 ≠ 记录 60 次
    extra = snap / "workflows" / "wf-a" / "runs" / "run-y.json"
    extra.write_text(json.dumps({
        "run_id": "run-y", "status": "completed",
        "node_executions": [{
            "node_id": "n-extra", "status": "completed",
            "attempt_history": [{"attempt_number": 1, "trigger": "initial",
                                 "status": "completed"}],
        }],
    }), encoding="utf-8")

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message


def test_sample_size_reports_no_sample_when_snapshot_empty(tmp_path: Path) -> None:
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "snapshot-meta.json").write_text(
        json.dumps({"totals": {"attempts": 0, "failed": 0}}), encoding="utf-8")

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message


def test_sample_size_is_wired_into_ci() -> None:
    """R51 唯一一条能进 CI 的判据：只读快照自身，CI 检出里可判。"""
    step = _sample_size_step()
    assert "python scripts/check_live_snapshot_gate.py" in str(step["run"])
    assert "tests/fixtures/live_snapshot" in str(step["run"])


def test_sample_size_ci_step_is_not_permanently_green() -> None:
    """这一步必须能红：只跑「当前快照该过」会得到一个恒绿步骤。

    「0/n 与任何 margin 都通过」是这一族判据的默认失效形状，所以要反向跑一次
    收紧余量、期望退出码 7。
    """
    run = str(_sample_size_step()["run"])
    assert "--margin 2" in run, "CI 步骤没有反向验证（收紧余量应触发 7）"
    assert "-ne 7" in run or "-eq 7" in run, (
        "CI 步骤没有断言退出码 7，收紧余量后判据失去判定力也不会被发现"
    )
    assert "exit 0" not in run.replace('"$code" -ne 0', ""), (
        "样本量步骤不得以无条件 exit 0 收尾"
    )


def test_stale_and_coverage_still_stay_out_of_ci() -> None:
    """R51 只放了 sample-size 进去，另两条仍必须留在 CI 外。

    这条守着「别顺手把两条需要真实数据的判据也接上」——那会让它们永远无法判定。
    """
    for step in _backend_steps():
        run = str(step.get("run", ""))
        assert "--check-stale" not in run
        assert "--check-coverage" not in run


# --------------------------------------- Windows runner 也判（R52 / §10-1）
def test_windows_runner_also_judges_the_sample_size() -> None:
    """R51 §10-1 的缺口：第 9 步只在 ubuntu 的 backend job 上跑。

    判据只用 ``math`` 与四则运算，看起来与平台无关——但那正是「只在单一环境
    验证」最容易漏掉的情形：stderr 编码、路径分隔、浮点格式化任一隐含假设都
    只在另一个 runner 上才显形。
    """
    step = _windows_sample_size_step()
    run = str(step["run"])
    assert "python scripts/check_live_snapshot_gate.py" in run
    assert "tests/fixtures/live_snapshot" in run
    assert step.get("shell") == "pwsh", (
        "windows runner 的步骤应显式指定 shell：默认可能变，而这段脚本用的是"
        "PowerShell 语法（$LASTEXITCODE）"
    )


def test_windows_sample_size_step_is_not_permanently_green() -> None:
    """与 ubuntu 那一步同样的反向要求：只跑「该通过」的分支等于恒绿。"""
    run = str(_windows_sample_size_step()["run"])
    assert "--margin 2" in run, "Windows 步骤没有反向验证（收紧余量应触发 7）"
    assert "-ne 7" in run or "-eq 7" in run, (
        "Windows 步骤没有断言退出码 7"
    )


def test_windows_sample_size_step_reads_last_exit_code_not_stop_preference() -> None:
    """pwsh 的默认 ``$ErrorActionPreference='Stop'`` 会把「故意以 7 退出」判成崩溃。

    反向验证恰恰要求被测脚本以非零码退出。若不在脚本里把它降成 Continue，
    这一步会在判据正常工作时红——那是比恒绿更难排查的失效（红灯指向错误的东西）。
    """
    run = str(_windows_sample_size_step()["run"])
    assert "$LASTEXITCODE" in run, "Windows 步骤没有读 $LASTEXITCODE"
    assert "ErrorActionPreference" in run and "Continue" in run, (
        "Windows 步骤没有把 $ErrorActionPreference 降成 Continue："
        "故意非零退出的反向验证会被 NativeCommandError 当成崩溃"
    )


def test_windows_step_does_not_reintroduce_stale_or_coverage() -> None:
    """同一条纪律在 Windows job 上同样成立。"""
    for step in _windows_backend_steps():
        run = str(step.get("run", ""))
        assert "--check-stale" not in run
        assert "--check-coverage" not in run
