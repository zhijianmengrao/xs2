"""真实数据面的闸门接线（R47）。

R46 把闸门接进了 CI，但判的是 ``tests/fixtures/run_samples`` ——**固定**样本，
它自己也在 §2.1 写明「保护的命题是闸门与脚本不退化，不是供应商今天健康」。
本文件钉住 R47 补上的那一半：对入库的**真实 run 快照**判失败率。

四类回归，全部静态或纯函数可验：
1. CI 真的有第二个闸门 step，且指向快照而不是 fixture；
2. 快照与其元数据一致（内容变了没重导 → 会以退出码 4 失败）；
3. 阈值来自**调用方给的政策上限**，精度（区间）由快照自身算——R57 修掉了
   「阈值 = 实测 + 余量」的自指写法，那种写法判据恒假（见下方 R57 一组）；
4. 快照不含内容载荷（小说正文/轨迹/token 明细不该进仓库）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import check_live_snapshot_gate as live_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SNAPSHOT_ROOT = REPO_ROOT / "tests" / "fixtures" / "live_snapshot"
# 反向验证用的合成快照（R58）：一个 workflow 全挂、两个健康。它必须判 exceeds，
# 否则 CI 的硬门槛反向验证就是在测一个恒绿步骤。
EXCEEDS_ROOT = REPO_ROOT / "tests" / "fixtures" / "live_snapshot_exceeds"


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


def _ceilings(run: str) -> list[float]:
    """这一段里所有 ``--fail-if-above`` 的数字（第一个是真实判定，其后是反向验证）。"""
    import re

    return [float(v) for v in re.findall(r"--fail-if-above\s+([0-9.]+)", run)]


def _gate_invocations(run: str) -> list[str]:
    """这一段里每一次调用闸门的命令行。

    按行取而不是只数开关：若真实判定那次调用没带上限、只有反向验证带了，光看
    「有几个 --fail-if-above」会给出错误的安全感。换行书写会被拆成两行而让测试
    报错——那种情况必须重写这条测试，而不是默默放过。
    """
    return [line for line in run.splitlines()
            if "check_live_snapshot_gate.py" in line]


def _windows_main_gate_step() -> dict:
    """Windows 上的失败率闸门（R57）。与 ubuntu 的 ``_live_gate_step`` 同一口径。"""
    hits = [
        s for s in _windows_backend_steps()
        if "check_live_snapshot_gate.py" in str(s.get("run", ""))
        and "--check-" not in str(s.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 windows-backend job 必须且只能有一处调用失败率闸门（不带 --check-*）"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def test_ci_live_gate_passes_an_explicit_ceiling() -> None:
    """真实数据闸门**每一次**调用都必须带写明数字的政策上限（R57）。

    不带上限就是报告模式（恒退出 0）——那正是本轮修掉的缺陷换件外衣：一个挂在
    CI 上、从不判定的步骤。只断言「这一步里有几个 --fail-if-above」不够：真实
    判定那次不带上限、只有反向验证带一个，同样能骗过那种断言。
    """
    run = str(_live_gate_step()["run"])
    invocations = _gate_invocations(run)
    assert len(invocations) >= 1
    for line in invocations:
        assert "--fail-if-above" in line, (
            f"这次调用没有 --fail-if-above，会退化成报告模式：{line.strip()}")
    assert 0 < _ceilings(invocations[0])[0] <= 100


def test_ci_live_gate_reverse_verifies_the_ceiling() -> None:
    """上限必须有反向验证：压到实测以下必须判 1。

    只跑「8% 该通过」会得到一个恒绿步骤——上限写得比谁都高也是绿。这里断言两
    件事：真的跑了第二次、且第二次的退出码被断言为 1。
    """
    import re

    run = str(_live_gate_step()["run"])
    invocations = _gate_invocations(run)
    assert len(invocations) >= 2, "CI 步骤没有第二次（反向验证）上限调用"
    real, tight = _ceilings(invocations[0])[0], _ceilings(invocations[1])[0]
    assert tight < real, f"反向验证的上限 {tight} 不低于真实判定 {real}：它验证不了什么"
    match = re.search(r'if\s*\[\s*"\$(\w+)"\s*-ne\s*1\s*\]', run)
    assert match, "CI 步骤没有断言「收紧上限后退出码为 1」"
    # 那个变量必须来自第二次调用，而不是第一次。
    tail = run.split("--fail-if-above")[-1]
    assert re.search(rf"\|\|\s*{match.group(1)}\s*=\s*\$\?", tail), (
        f"退出码变量 {match.group(1)} 不是反向验证那一次调用的")


def test_both_runners_use_the_same_policy_ceiling() -> None:
    """ubuntu 与 windows 必须给同一个上限：漂开就会在两个 runner 上自相矛盾。

    上限是政策值，不是各 runner 的本地参数。两个数字不一致时，同一份快照会在
    一个平台判红、另一个判绿，而根因只是一次手误。
    """
    ubuntu = _ceilings(str(_live_gate_step()["run"]))
    windows = _ceilings(str(_windows_main_gate_step()["run"]))
    assert ubuntu and windows
    assert ubuntu[0] == windows[0], (
        f"两个 runner 的政策上限不一致：ubuntu {ubuntu[0]}，windows {windows[0]}")


def test_windows_main_gate_step_ends_with_exit_zero() -> None:
    """pwsh 包装器会追加 ``exit $LASTEXITCODE``，而最后一条原生命令故意以 1 退出。"""
    run = str(_windows_main_gate_step()["run"])
    assert run.rstrip().endswith("exit 0"), (
        "windows 的失败率闸门步骤末尾必须显式 exit 0（R52 踩过的坑）")
    assert "$ErrorActionPreference" in run


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


# ------------------------------------------ 阈值来自外部，不是快照自身（R57）
def _threshold_from(message: str) -> float:
    """从判定说明里取出实际使用的阈值数值（"...阈值（政策上限）8.00%..."）。"""
    import re

    match = re.search(r"阈值（政策上限）\s*([0-9.]+)%", message)
    assert match, f"判定说明里没有阈值数字：{message}"
    return float(match.group(1))


def test_gate_threshold_comes_from_the_caller() -> None:
    """阈值必须是外部给的：同一份快照换上限，**结论**要跟着翻转。

    R57 修的就是 R47 的「阈值从快照自身算」——那是同义反复：阈值 = 实测 +
    余量，判据 = 实测 > 阈值，而余量禁止为负，于是恒假。只断言「说明里出现了
    上限数字」会被这种实现骗过去，所以这里钉的是翻转：8% 判正常、1% 判超阈。
    """
    code_ok, msg_ok = live_gate.evaluate(SNAPSHOT_ROOT, ceiling=8.0)
    code_bad, msg_bad = live_gate.evaluate(SNAPSHOT_ROOT, ceiling=1.0)
    assert code_ok == live_gate.EXIT_OK, msg_ok
    assert code_bad == live_gate.EXIT_GATE_TRIGGERED, msg_bad
    assert _threshold_from(msg_ok) == pytest.approx(8.0, abs=0.005)
    assert _threshold_from(msg_bad) == pytest.approx(1.0, abs=0.005)


def test_a_snapshot_of_only_failures_actually_triggers(tmp_path: Path) -> None:
    """R57 的回归钉子：20 次尝试全失败，在上限 8% 下必须退出 1。

    这正是老实现**实测判 0** 的场景：阈值被截到 100%，判据 ``100 > 100`` 为假。
    没有这一条，一个恒真的比较也能让上面那条测试全绿（它靠的是「换上限翻转」，
    而恒真实现根本不会翻转——两条测试分工：一条钉「有判定力」，一条钉「比谁」）。
    """
    _write_snapshot_with_totals(tmp_path, attempts=20, failed=20)
    code, message = live_gate.evaluate(tmp_path, ceiling=8.0)
    assert code == live_gate.EXIT_GATE_TRIGGERED, message


def test_report_mode_does_not_pass_for_a_verdict() -> None:
    """不给上限是报告模式：退出 0，但必须写明「没有判定」。

    「没给阈值」被沉默成通过，是本缺陷的另一件外衣。所以这里断言说明里既有
    「未给 --fail-if-above」，又**不出现**正常判决的措辞。
    """
    code, message = live_gate.evaluate(SNAPSHOT_ROOT)
    assert code == live_gate.EXIT_OK, message
    assert "未给 --fail-if-above" in message
    assert "只报告不判定" in message
    assert "判正常" not in message


def test_interval_straddling_the_ceiling_is_undetermined_not_a_failure() -> None:
    """区间横跨上限 → 判不了：不红，也不许说成正常（R56 的三分法）。

    入库快照 10/255 = 3.92%，95% 区间 [2.14%, 6.56%]。上限 4% 落在区间里：
    这份样本回答不了「真实失败率是否高于 4%」，所以既不是 exceeds 也不是 normal。
    """
    code, message = live_gate.evaluate(SNAPSHOT_ROOT, ceiling=4.0)
    assert code == live_gate.EXIT_OK, message
    assert "区间横跨阈值" in message
    assert "不判失败" in message
    assert "判正常" not in message


def test_main_gate_and_per_workflow_share_the_same_interval() -> None:
    """主闸门与 per-workflow 判决必须共用同一份区间算术（R56 §4 的纪律）。

    两处各写一份精确界，迟早出现「这边说超、那边说不超」。这里让两个函数对同一
    组 ``(n, k)`` 与同一个阈值出判决——任何一处改了口径（换正态近似、换点估计）
    就会在这一组上分裂。主闸门的阈值是「0 + 上限」，所以直接用同一个数比。
    """
    for attempts, failed in ((255, 10), (20, 20), (14, 0), (5, 1), (1, 1)):
        for threshold in (1.0, 4.0, 8.0, 50.0, 100.0):
            assert (live_gate._ceiling_verdict(attempts, failed, threshold)[0]
                    == live_gate._rate_verdict(attempts, failed, 0.0, threshold)[0]), (
                        f"n={attempts} k={failed} 阈值={threshold}：两处判决不一致")


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

    code, message = live_gate.evaluate(tmp_path, ceiling=8.0)
    assert code == live_gate.EXIT_META_DRIFT, message
    assert "不一致" in message


def test_gate_reports_no_sample_when_snapshot_missing(tmp_path: Path) -> None:
    code, message = live_gate.evaluate(tmp_path, ceiling=8.0)
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


# ------------------------------------------------- 全部失败（R53）
def test_sample_size_does_not_let_all_failures_pass_for_free(tmp_path: Path) -> None:
    """全部失败（p=1.0）是零失败的**镜像退化点**，之前漏了（R53）。

    ``p(1-p)`` 在 p=0 与 p=1 时都等于 0，正态近似在两端都会给出「半宽 0 →
    永远合格」。零失败那条在 R51 就补了单侧上界，全部失败这一端直到 R53 才
    被发现——而它恰好是最需要被看见的运维状况：一个「每次尝试都失败」的
    快照被判「样本量足够」，闸门于是拿 100% 当基线，阈值封顶成 100%，
    永远不触发。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=2, failed=2)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_THIN_SAMPLE, message
    assert "77" in message or "78" in message, (
        f"全部失败分支没有给出单侧距离，实际说明：{message!r}"
    )


def test_sample_size_accepts_enough_all_failed_attempts(tmp_path: Path) -> None:
    """30 次尝试全失败：单侧距离 9.50 ≤ 10，应当通过。

    与上一条互为正反面：只验「薄的要拒」会让「一律拒绝全失败样本」也绿灯，
    而那会把一个确实够厚的全失败画像挡在门外——它的结论（100% 失败）是
    可信的。
    """
    snap = tmp_path / "snap"
    _write_snapshot_with_totals(snap, attempts=30, failed=30)

    code, message = live_gate.check_sample_size(snap, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_both_degenerate_ends_use_the_same_closed_form() -> None:
    """两端用的是同一个单侧界，不该一边一个公式。

    ``1 - 0.05**(1/n)`` 同时是「全成功时 p 的上界」与「全失败时 p 下界到 1
    的距离」。如果将来有人把其中一端换成别的估计（比如 Wilson），两端就会
    对同一个 n 给出不同的「所需余量」，而两处都还绿着。
    """
    for attempts in (2, 5, 10, 30, 100):
        zero_failed = live_gate.sample_size_margin_needed(attempts, 0)
        all_failed = live_gate.sample_size_margin_needed(attempts, attempts)
        assert zero_failed is not None and all_failed is not None
        assert abs(zero_failed - all_failed) < 1e-9, (
            f"n={attempts}：零失败 {zero_failed} 与全部失败 {all_failed} 不对称"
        )


def test_degenerate_ends_are_not_treated_as_zero_width() -> None:
    """两端都**不得**回落到正态近似的 0 宽度。

    这是这条判据存在的全部理由：0 宽度会让任何 margin 都通过。
    """
    for failed in (0, 10):
        needed = live_gate.sample_size_margin_needed(10, failed)
        assert needed is not None and needed > 0, (failed, needed)


def test_middle_of_the_range_uses_the_exact_bound_not_the_normal_approximation() -> None:
    """中段也走精确界——R55 推翻了 R53 的「中段保持正态近似」这个决定。

    R53 的理由是「换成 Clopper-Pearson 会得到更宽的区间，于是本来够厚的快照会被
    判太薄」。那个理由站不住：把三种形状拆成两条式子，会在 ``p`` 从 0 跳到
    ``1/n`` 处留下一个**方向错误**的台阶（见下一条测试）。宁可区间宽一点、全线
    同一把尺，也不要一把尺在两个区间上得出互相矛盾的结论。

    代价是实测的：入库快照全局 10/255 的所需余量 2.38 → 2.64 个百分点，仍远小于
    margin=10；但 per-workflow 诊断里 build 与 post-hoc 会从达标变不达标——那一块
    恒退出 0，变的是诊断文字。
    """
    attempts, failed = 255, 10
    needed = live_gate.sample_size_margin_needed(attempts, failed)
    normal = live_gate.Z_95 * ((failed / attempts) * (1 - failed / attempts)
                              / attempts) ** 0.5 * 100
    assert needed is not None
    # 精确界比正态近似宽（这是有意的保守），且两者在同量级（不是差一个数量级）。
    assert needed > normal, (needed, normal)
    assert needed < normal * 2, (needed, normal)
    # 与精确界定义对齐（这不是「背下来的参考值」，而是定义式本身）：上界满足
    # P(X <= k | p=upper) = 0.05，下界满足 P(X <= k-1 | p=lower) = 0.95。
    # n=255, k=10 时实测 lower≈2.143%、upper≈6.561%，点估计 3.922%。
    lower, upper = live_gate._cp_bounds(attempts, failed)
    assert abs(live_gate._binomial_cdf_le(attempts, failed, upper) - 0.05) < 1e-9
    assert abs(live_gate._binomial_cdf_le(attempts, failed - 1, lower) - 0.95) < 1e-9
    assert 0.021 < lower < 0.022, lower
    assert 0.065 < upper < 0.066, upper


def test_a_first_failure_never_makes_the_sample_look_more_trustworthy() -> None:
    """R55 的核心回归：``p`` 从 0 跳到 ``1/n`` 时，所需余量**必须变大**。

    这是本轮修的那个坑的形状。旧的混合实现下 n=10、k=0 要 25.89 个百分点，
    而 k=1 只要 18.59——多了一次失败，样本反而显得更可信，判据在说反话。
    它会让「刚出现失败」的样本比「零失败」的样本更容易过闸门，正好把最该被
    看见的那一刻放过去。

    只对 n ≥ 5 断言：n ≤ 4 时精确界在低端仍有轻微反转（n=2 时 77.6 → 47.5），
    但那几个 n 的所有 k 都已经远超任何合理 margin（最小值也在 45 个百分点
    以上），判决结果不可能因此不同——见下一条测试把它钉住。
    """
    for attempts in range(5, 301):
        zero = live_gate.sample_size_margin_needed(attempts, 0)
        one = live_gate.sample_size_margin_needed(attempts, 1)
        assert zero is not None and one is not None
        assert one > zero, (
            f"n={attempts}：一次失败（{one:.2f}）没有比零失败（{zero:.2f}）要求更厚——"
            "判据又在说反话"
        )
        # 高端镜像。
        one_short = live_gate.sample_size_margin_needed(attempts, attempts - 1)
        all_failed = live_gate.sample_size_margin_needed(attempts, attempts)
        assert one_short is not None and all_failed is not None
        assert one_short > all_failed, (attempts, one_short, all_failed)


def test_the_small_n_inversion_cannot_change_any_verdict() -> None:
    """n ≤ 4 的残余反转必须落在「怎么判都太薄」的区域里，不该影响结论。

    上一条测试刻意从 n=5 起断言，把 n=2..4 留给这条：如果哪天有人给 n=3 加了
    特殊处理让它「变合格」，这里会红。判据是「这些 n 的最小所需余量仍远大于
    一个现实 margin」——只要成立，反转就不是可观测差异。
    """
    realistic_margin = 10.0  # 闸门默认值，也是快照闸门在用的量级
    for attempts in (2, 3, 4):
        worst = min(live_gate.sample_size_margin_needed(attempts, k)
                    for k in range(attempts + 1))
        assert worst is not None
        assert worst > realistic_margin * 4, (
            f"n={attempts} 的最小所需余量只有 {worst:.1f} 个百分点，"
            "反转可能影响判决：需要重新审视而不是假定它无害")
    # 反向钉住：n=5 起已无反转，所以「n<=4 无害」这个豁免范围不能再扩大。
    assert live_gate.sample_size_margin_needed(5, 1) > \
        live_gate.sample_size_margin_needed(5, 0)


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


def test_windows_sample_size_step_ends_with_exit_zero() -> None:
    """末尾必须显式 ``exit 0``（R52 实测踩到）。

    GHA 的 pwsh 包装器在脚本末尾追加 ``exit $LASTEXITCODE``，而脚本里最后一条
    原生命令正是那次**故意**以 7 退出的反向验证。于是判据两个分支都对、日志也
    打印了 OK，步骤仍然红——CI run **40801653541** 的 `windows-backend` 就是这么
    红的。`exit 0` 是让「提前 exit 的失败路径」与「走到末尾的成功路径」分开。

    这条测试不是风格检查：删掉它这一步就会在每次跑的时候红，而红的原因与判据
    毫无关系。
    """
    run = str(_windows_sample_size_step()["run"])
    tail = [line.strip() for line in run.strip().splitlines() if line.strip()]
    assert tail[-1] == "exit 0", (
        f"Windows 步骤没有以 exit 0 收尾（末行是 {tail[-1]!r}）："
        "pwsh 包装器会把最后一次故意非零的退出码透传出去"
    )


def test_windows_step_does_not_reintroduce_stale_or_coverage() -> None:
    """同一条纪律在 Windows job 上同样成立。"""
    for step in _windows_backend_steps():
        run = str(step.get("run", ""))
        assert "--check-stale" not in run
        assert "--check-coverage" not in run


# --------------------------------------- per-workflow 样本量（R54）
def _write_per_workflow_snapshot(root: Path, spec: dict[str, tuple[int, int]],
                                 declare_meta: bool = True) -> None:
    """造一份带 ``per_workflow`` 块的快照。

    ``spec`` 是 ``{workflow: (attempts, failed)}``，每个 workflow 一个 run，
    attempt 数就是 attempts。``declare_meta=False`` 时省掉 ``per_workflow``
    块，用来验「元数据缺这一块」的挂号路径。
    """
    per_workflow: dict[str, dict] = {}
    total_attempts = total_failed = 0
    for wf_name, (attempts, failed) in spec.items():
        runs = root / "workflows" / wf_name / "runs"
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
        per_workflow[wf_name] = {"runs": 1, "attempts": attempts,
                                 "failed": failed}
        total_attempts += attempts
        total_failed += failed
    meta: dict = {"totals": {"attempts": total_attempts, "failed": total_failed},
                  "exported_at": "2026-02-01T00:00:00+00:00"}
    if declare_meta:
        meta["per_workflow"] = per_workflow
    (root / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_per_workflow_passes_on_the_committed_snapshot() -> None:
    """入库快照自己必须过——否则 CI 一接就红。"""
    code, message = live_gate.check_per_workflow(SNAPSHOT_ROOT, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_per_workflow_catches_drift_the_global_totals_miss(tmp_path: Path) -> None:
    """R54 的全部动机：把一次失败从一个 workflow 挪到另一个。

    两个 workflow 各 10 次尝试、各 1 次失败。全局 attempts/failed 都是
    (20, 2)，分毫不动——所以 ``recompute_totals`` 的全局校验通过；而
    ``per_workflow`` 元数据里 a 已写成 2 次失败，与内容不一致。
    全局判据看不出来的洞，只能由分组复算补。
    """
    _write_per_workflow_snapshot(tmp_path, {"wf-a": (10, 1), "wf-b": (10, 1)})
    # 先确认基线：全局与 per-workflow 都一致时双绿。
    assert live_gate.evaluate(tmp_path, ceiling=8.0)[0] == live_gate.EXIT_OK
    assert live_gate.check_per_workflow(tmp_path, margin=10.0)[0] == live_gate.EXIT_OK

    meta = json.loads((tmp_path / "snapshot-meta.json").read_text(encoding="utf-8"))
    meta["per_workflow"]["wf-a"]["failed"] = 2
    meta["per_workflow"]["wf-b"]["failed"] = 0
    (tmp_path / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")

    # 全局合计未变 → 全局判据仍然绿（这正是缺口本身）。
    assert live_gate.evaluate(tmp_path, ceiling=8.0)[0] == live_gate.EXIT_OK
    # 分组复算必须抓到。
    code, message = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message
    assert "wf-a" in message and "wf-b" in message


def test_per_workflow_detects_run_count_drift(tmp_path: Path) -> None:
    """runs 数也在校验范围内：删掉一个 run 文件同样要被抓到。"""
    _write_per_workflow_snapshot(tmp_path, {"wf-a": (10, 1)})
    meta = json.loads((tmp_path / "snapshot-meta.json").read_text(encoding="utf-8"))
    meta["per_workflow"]["wf-a"]["runs"] = 5
    (tmp_path / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    code, message = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message


def test_per_workflow_reports_workflow_present_in_meta_but_absent_in_content(
        tmp_path: Path) -> None:
    """元数据里有、内容里没有：也要判漂移，不是静默跳过。"""
    _write_per_workflow_snapshot(tmp_path, {"wf-a": (10, 1)})
    meta = json.loads((tmp_path / "snapshot-meta.json").read_text(encoding="utf-8"))
    meta["per_workflow"]["wf-ghost"] = {"runs": 1, "attempts": 5, "failed": 0}
    (tmp_path / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    code, message = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message
    assert "wf-ghost" in message


def test_per_workflow_thin_workflow_is_reported_but_not_a_hard_failure(
        tmp_path: Path) -> None:
    """薄 workflow 只被报告，不判失败——这是本判据的设计核心（R54）。

    真实快照里 ``xs2-novel-flywheel-export`` 只有 5 次尝试、零失败，零失败时
    95% 上界 45 个百分点，压到 margin=10 要 29 次尝试，而真实数据里那个
    workflow 总共只有 10 个 run——物理上补不到。把它做成硬门槛，会得到一个
    **永远红**的步骤，与历轮反复批评的「永远绿的防护」是同一个错误的两面。

    所以判据只有两件事能红：元数据漂移、无样本。薄只进报告。
    """
    # 5 次尝试零失败：所需余量约 45 个百分点，远超 margin=10。
    _write_per_workflow_snapshot(tmp_path, {"wf-thin": (5, 0)})
    code, message = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_OK, message
    assert "wf-thin" in message
    assert "不达标" in message


def test_per_workflow_requires_the_per_workflow_block(tmp_path: Path) -> None:
    """元数据缺 ``per_workflow`` 块时报无样本（3），不是静默通过。"""
    _write_per_workflow_snapshot(tmp_path, {"wf-a": (10, 1)}, declare_meta=False)
    code, message = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message
    assert "per_workflow" in message


def test_per_workflow_reports_no_sample_when_snapshot_has_no_workflows(
        tmp_path: Path) -> None:
    """快照里一个 workflow 都没有时报无样本（3）。"""
    (tmp_path / "workflows").mkdir()
    (tmp_path / "snapshot-meta.json").write_text(
        json.dumps({"per_workflow": {"wf-a": {"runs": 1, "attempts": 1,
                                              "failed": 0}}}),
        encoding="utf-8")
    code, _ = live_gate.check_per_workflow(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_NO_SAMPLE


def _has_flag(run: str, flag: str) -> bool:
    """``run`` 里是否出现了**完整**的开关 ``flag``。

    用「后面不能再接 ``-`` 或标识符字符」判边界，而不是要求后跟空格——开关也
    可能出现在行尾，或后面直接跟续行反斜杠。``--check-per-workflow`` 与
    ``--check-per-workflow-rate`` 因此能被区分开。
    """
    import re

    return re.search(re.escape(flag) + r"(?![-\w])", run) is not None


def _per_workflow_step() -> dict:
    """ubuntu backend 上的 per-workflow **样本量**步骤（R54）。

    不能按子串 ``--check-per-workflow`` 定位：R56 加了
    ``--check-per-workflow-rate``，它把前者当词前缀，子串匹配会把两个步骤都算
    进来（R56 实测踩到，这条断言报的 2 处）。改为按完整开关 token 匹配，
    以后再加 ``--check-per-workflow-*`` 也不会误伤。
    """
    hits = [
        s for s in _backend_steps()
        if _has_flag(str(s.get("run", "")), "--check-per-workflow")
    ]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处跑 --check-per-workflow"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def test_per_workflow_is_wired_into_ci() -> None:
    """只读快照自身，所以同样能进 CI 检出。"""
    run = str(_per_workflow_step()["run"])
    assert "python scripts/check_live_snapshot_gate.py" in run
    assert "tests/fixtures/live_snapshot" in run


def test_per_workflow_ci_step_is_not_permanently_green() -> None:
    """这一步必须能红：它唯一的红路径是元数据漂移，所以 CI 要注入一处。

    不注入的话，这一步在判据完全失效时也会绿——因为「薄」本身不判失败。
    """
    run = str(_per_workflow_step()["run"])
    assert "per_workflow" in run, "CI 步骤没有注入漂移样本"
    assert "-ne 4" in run or "-eq 4" in run, (
        "CI 步骤没有断言退出码 4，判据失去判定力也不会被发现"
    )


def test_per_workflow_does_not_reintroduce_single_global_checks() -> None:
    """新步骤不得顺手把 --check-stale/--check-coverage 拉进 CI。"""
    run = str(_per_workflow_step()["run"])
    assert "--check-stale" not in run
    assert "--check-coverage" not in run


def test_windows_runner_also_judges_per_workflow() -> None:
    """Windows job 上有同一段（与 sample-size 同样的理由：判据看似平台无关）。"""
    hits = [
        s for s in _windows_backend_steps()
        if _has_flag(str(s.get("run", "")), "--check-per-workflow")
    ]
    assert len(hits) == 1, (
        "ci.yml 的 windows-backend job 必须且只能有一处跑 --check-per-workflow"
        f"（实际 {len(hits)} 处）"
    )
    run = str(hits[0]["run"])
    assert "per_workflow" in run
    assert "-ne 4" in run or "-eq 4" in run


def test_judgement_flags_are_mutually_exclusive(monkeypatch) -> None:
    """四条判据互斥：混判会让人看不出是哪种不合格。

    ``argparse`` 的 ``parser.error`` 以退出码 2 结束进程，所以这里断言
    ``SystemExit(2)``——不是在测 argparse 本身，而是钉住「新判据也被纳入了
    互斥列表」。漏纳入时两个判据会串着判，第二个的结果覆盖第一个。
    """
    import sys

    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py",
        "--check-sample-size", "--check-per-workflow"])
    with pytest.raises(SystemExit) as excinfo:
        live_gate.main()
    assert excinfo.value.code == 2


# --------------------------------------- per-workflow 失败率（R56）
# 这一组钉住 R56 的主线：此前闸门用**全局合计**当基线，而全局合计对「某个
# workflow 在变坏」是结构性失明的——一个全挂的 workflow 会把自己也拉进基线里，
# 观测值和阈值一起涨，于是它永远判不出自己。留一法基线把被判的那份扣掉。
def _rate_snapshot(root: Path, spec: dict[str, tuple[int, int]]) -> None:
    """造一份 per-workflow 快照：``spec`` 是 ``{workflow: (attempts, failed)}``。

    复用 ``_write_per_workflow_snapshot`` 的落盘形状（每个 workflow 一个 run，
    attempt 数即 attempts），这个包装只是给本组测试一个说得出意图的名字。
    """
    _write_per_workflow_snapshot(root, spec)


def test_leave_one_out_baseline_excludes_the_judged_workflow() -> None:
    """留一法基线必须把被判的那份从基线里扣掉——这是全部判据的地基。

    三个 workflow 各 10 次尝试、各 0 失败，再加一个 10/10 的全挂者。全局合计
    基线是 10/40 = 25%，而留一法给全挂者的基线是 0/30 = 0%。**这两个数字必须
    不同**：若判据用的是全局合计，全挂者观测 100% 也只比 25% 高 75 个百分点，
    而它自己的 10 次失败贡献了阈值里的 10 个百分点——自己抬高了自己的门槛。

    这里不测判据结论，只测基线算术：把「基线含不含自己」这件事单独钉住，
    否则后面所有判决测试都可能建立在错误的基线上而仍然通过。
    """
    buckets = {
        "a": {"runs": 1, "attempts": 10, "failed": 0},
        "b": {"runs": 1, "attempts": 10, "failed": 0},
        "c": {"runs": 1, "attempts": 10, "failed": 0},
        "bad": {"runs": 1, "attempts": 10, "failed": 10},
    }
    baselines = live_gate.per_workflow_baselines(buckets)
    # 全挂者看其余三个：0/30。
    assert baselines["bad"] == pytest.approx(0.0, abs=1e-12)
    # 健康者看其余（含那个全挂的）：10/30。
    assert baselines["a"] == pytest.approx(10 / 30 * 100.0, abs=1e-12)
    # 与「全局合计」明确不同——这条断言就是「不能拿全局合计当基线」的意思。
    global_baseline = 10 / 40 * 100.0
    assert baselines["bad"] != pytest.approx(global_baseline, abs=1e-6)


def test_leave_one_out_baseline_is_none_for_a_lone_workflow() -> None:
    """只剩一个 workflow 时基线无从计算，必须给 None 而不是 0。

    拿 0 当基线会让「唯一那个 workflow」永远跟 0% 比，任何失败都判超出——
    一个只有单 workflow 的快照会变成恒红，而它实际上无法回答这个问题。
    """
    assert live_gate.per_workflow_baselines(
        {"only": {"runs": 1, "attempts": 20, "failed": 5}}) == {"only": None}


def test_a_wildly_failing_workflow_exceeds_its_leave_one_out_baseline(
        tmp_path: Path) -> None:
    """本判据存在的全部理由：一个全挂的 workflow 必须被判 ``exceeds``。

    两个健康 workflow 各 30 次尝试零失败，第三个 40 次尝试全失败。它的 95%
    下界 92.78% 远高于阈值（基线 0% + margin 10 = 10%），整个区间都在阈值之上。

    反向意义：这条判据若失效（比如退回全局合计基线），全挂者在全局口径下
    观测 100% 对基线 40%（40/100）、阈值 50%，**依然会超出**——所以光靠这条
    测试不能证明用的是留一法。留一法本身由上一条基线算术测试钉住，两者分工
    明确：一条钉「判得出来」，一条钉「比的是谁」。
    """
    _rate_snapshot(tmp_path, {"good-a": (30, 0), "good-b": (30, 0), "bad": (40, 40)})
    report = live_gate.per_workflow_rate_report(
        live_gate.recompute_per_workflow(tmp_path / "workflows"), margin=10.0)
    assert report["bad"]["verdict"] == "exceeds", report["bad"]
    assert report["good-a"]["verdict"] == "normal", report["good-a"]
    assert report["good-b"]["verdict"] == "normal", report["good-b"]


def test_a_thin_workflow_is_undetermined_not_failed_and_not_passed(
        tmp_path: Path) -> None:
    """样本太薄时判 ``undetermined``——它既不是合格也不是不合格（R56 的核心）。

    这是真实快照逼出来的形状：9 个 workflow 里 8 个的 95% 区间横跨阈值。
    把这种样本判「合格」就是恒绿（判不了当通过），判「不合格」就是恒红
    （判不了当失败）。两者都是历轮反复批评的假防护，所以它必须是第三种判决。

    这里用 1 次尝试 1 次失败：区间 [5.4%, 100%] 横跨阈值 10% 以上。
    """
    _rate_snapshot(tmp_path, {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)})
    report = live_gate.per_workflow_rate_report(
        live_gate.recompute_per_workflow(tmp_path / "workflows"), margin=10.0)
    assert report["thin"]["verdict"] == "undetermined", report["thin"]
    # 明细里必须同时给出区间两端，否则没法看出「为什么判不了」。
    assert "95% 区间" in report["thin"]["detail"]
    assert "[" in report["thin"]["detail"] and "]" in report["thin"]["detail"]


def test_undetermined_is_never_a_hard_failure_even_with_fail_on_exceeds(
        tmp_path: Path) -> None:
    """``--fail-on-exceeds`` 只对 ``exceeds`` 生效，不能被 ``undetermined`` 触发。

    这一条防的是最省事的错误实现：把「不是 normal」一律当失败。那样真实快照
    （8 个 undetermined）一接进 CI 就恒红，而且红的原因与「有 workflow 在变坏」
    毫无关系——指向的是错误的处置。
    """
    _rate_snapshot(tmp_path, {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)})
    code, message = live_gate.check_per_workflow_rate(
        tmp_path, margin=10.0, fail_on_exceeds=True)
    assert code == live_gate.EXIT_OK, message
    assert "undetermined" not in message  # 报告用中文，不泄露内部枚举名
    assert "样本不足" in message


def test_report_mode_does_not_fail_on_exceeds(tmp_path: Path) -> None:
    """默认报告模式：即使有 workflow 超出基线，也恒退出 0（本轮用户拍定的形态）。

    这不是「判据不敢判」，而是 R56 刻意选的两步走：先让真实的 per-workflow 结论
    在 CI 日志里跑一轮，看清红的是什么、是不是「样本太薄」冒充「在变坏」，
    再在下一轮决定硬门槛。硬门槛靠 ``--fail-on-exceeds`` 显式打开。
    """
    _rate_snapshot(tmp_path, {"bad": (40, 40), "good-a": (30, 0), "good-b": (30, 0)})
    code, message = live_gate.check_per_workflow_rate(
        tmp_path, margin=10.0, fail_on_exceeds=False)
    assert code == live_gate.EXIT_OK, message
    assert "报告模式" in message
    # 同一份快照，打开开关就必须红——证明这个开关不是摆设。
    strict_code, _ = live_gate.check_per_workflow_rate(
        tmp_path, margin=10.0, fail_on_exceeds=True)
    assert strict_code == live_gate.EXIT_GATE_TRIGGERED


def test_rate_check_reuses_the_per_workflow_drift_check(tmp_path: Path) -> None:
    """判失败率之前必须先确认判的是内容——漂移同样判 4。

    把一次失败从 a 挪到 b，全局合计不动；此时若直接判失败率，判的是元数据里
    写的那句话而不是内容。与 ``check_per_workflow`` 同一层校验，不另写一份。
    """
    _rate_snapshot(tmp_path, {"wf-a": (20, 1), "wf-b": (20, 1)})
    meta = json.loads((tmp_path / "snapshot-meta.json").read_text(encoding="utf-8"))
    meta["per_workflow"]["wf-a"]["failed"] = 2
    meta["per_workflow"]["wf-b"]["failed"] = 0
    (tmp_path / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")
    code, message = live_gate.check_per_workflow_rate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_META_DRIFT, message
    assert "wf-a" in message and "wf-b" in message


def test_rate_check_reports_no_sample_without_the_per_workflow_block(
        tmp_path: Path) -> None:
    """元数据缺 ``per_workflow`` 块时报无样本（3），不是静默通过。"""
    _write_per_workflow_snapshot(tmp_path, {"wf-a": (10, 1)}, declare_meta=False)
    code, message = live_gate.check_per_workflow_rate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_NO_SAMPLE, message
    assert "per_workflow" in message


def test_rate_check_passes_on_the_committed_snapshot() -> None:
    """入库快照自己必须在硬门槛下也过——否则 CI 一接就红。

    同时把这个快照当下的三分法结论钉住：9 个 workflow 里**没有一个**超出基线。
    这不是「快照很健康」的断言，而是「当前真实数据在 per-workflow 粒度上判不出
    坏样本」这个事实的存档。若哪天它变了，说明真实数据变了，测试红得其所。
    """
    code, message = live_gate.check_per_workflow_rate(
        SNAPSHOT_ROOT, margin=10.0, fail_on_exceeds=True)
    assert code == live_gate.EXIT_OK, message
    assert "0 个超出" in message, message
    assert "8 个样本不足" in message, message


# ------------------------------------- 连续多轮样本不足的次级信号（R58）
# 单轮判不了是样本薄；连续几轮都判不了，说明数据量本身支撑不了逐 workflow
# 判决。这条信号只提示重导，**不改变退出码**——把「判不了」做成失败，就是
# R56 §2 批评过的「向错方向的假红」换到时间维度。
def _write_history(root: Path, rounds: list[dict[str, tuple[int, int]]]) -> None:
    """给快照元数据写 ``history`` 块（旧→新；最后一条通常是当前这轮）。"""
    meta_path = root / "snapshot-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["history"] = [
        {"exported_at": f"2026-01-{index + 1:02d}T00:00:00+00:00",
         "per_workflow": {name: {"attempts": attempts, "failed": failed}
                          for name, (attempts, failed) in counts.items()}}
        for index, counts in enumerate(rounds)
    ]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def test_snapshot_rounds_append_the_current_round_only_once(tmp_path: Path) -> None:
    """历史以当前快照收尾时不得把这一轮数两次（导出脚本就是这么写的）。

    反过来：最后一条与当前内容不一致时（旧快照、手改过内容），当前这轮必须
    补进去——不能因为「历史里没有当前」就少算一轮，那会让提示晚一轮出现。
    """
    current = {"a": {"attempts": 10, "failed": 0}}
    meta = {"history": [{"per_workflow": {"a": {"attempts": 10, "failed": 0}}}]}
    rounds, invalid = live_gate.snapshot_rounds(meta, current)
    assert len(rounds) == 1, "当前这一轮被数了两次"
    assert invalid == 0

    meta["history"][0]["per_workflow"]["a"]["failed"] = 1
    rounds, invalid = live_gate.snapshot_rounds(meta, current)
    assert rounds[-1] == {"a": (10, 0)}, "当前内容没有补成新的一轮"
    assert len(rounds) == 2
    assert invalid == 0

    rounds, invalid = live_gate.snapshot_rounds({"history": []}, current)
    assert rounds == [{"a": (10, 0)}] and invalid == 0


def test_malformed_history_entries_are_skipped_not_guessed() -> None:
    """形状无效的历史条目跳过并计数，不猜一个 0 也不炸掉整条判据。"""
    current = {"a": {"attempts": 10, "failed": 0}}
    meta = {"history": [{"per_workflow": "not-a-dict"}, {}, "junk"]}
    rounds, invalid = live_gate.snapshot_rounds(meta, current)
    assert rounds == [{"a": (10, 0)}]
    assert invalid == 3


def test_undetermined_streak_counts_the_current_round_and_stops_at_a_verdict() -> None:
    """连续轮数含当前轮，并在第一个能判出结论的轮次处中断。"""
    thin_round = {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)}
    rounds = [thin_round, thin_round, thin_round]
    streaks = live_gate.undetermined_streaks(rounds, margin_pct=10.0)
    assert streaks["thin"] == 3
    assert streaks["good-a"] == 0

    # 最早一轮里 thin 是 0/40（判得出 normal）→ 只连续 2 轮。
    resolved_round = {"thin": (40, 0), "good-a": (40, 0), "good-b": (40, 0)}
    streaks = live_gate.undetermined_streaks(
        [resolved_round, thin_round, thin_round], margin_pct=10.0)
    assert streaks["thin"] == 2


def test_chronic_undetermined_prompts_reexport_without_failing(tmp_path: Path) -> None:
    """连续 3 轮样本不足 → 提示重导，但退出码仍是 0（报告与硬门槛两种模式都是）。

    构造：一个只有 1 次尝试的 workflow，其余两个各 40 次零失败。它的区间
    [5.4%, 100%] 横跨阈值 10%，单轮就是 ``undetermined``，连续三轮仍如此。
    """
    spec = {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)}
    _rate_snapshot(tmp_path, spec)
    _write_history(tmp_path, [spec, spec, spec])

    strict_code, strict_message = live_gate.check_per_workflow_rate(
        tmp_path, margin=10.0, fail_on_exceeds=True)
    assert strict_code == live_gate.EXIT_OK, strict_message
    assert "连续 3 轮以上样本不足" in strict_message
    assert "thin" in strict_message
    assert "重导" in strict_message
    # 内部枚举名不该出现在给 CI 读的报告里（R56 的同一纪律）。
    assert "undetermined" not in strict_message

    report_code, report_message = live_gate.check_per_workflow_rate(
        tmp_path, margin=10.0)
    assert report_code == live_gate.EXIT_OK
    assert "连续 3 轮以上样本不足" in report_message


def test_short_history_reports_coverage_instead_of_inventing_a_streak(
        tmp_path: Path) -> None:
    """历史不足 3 轮时明说「提示未生效」，不把沉默当连续性。"""
    spec = {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)}
    _rate_snapshot(tmp_path, spec)
    code, message = live_gate.check_per_workflow_rate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_OK
    assert "连续 3 轮以上样本不足" not in message
    assert "快照历史 1 轮" in message
    assert "未生效" in message


def test_malformed_history_is_reported_so_the_streak_is_not_oversold(
        tmp_path: Path) -> None:
    """跳过的历史条目要在报告里写明——否则连续轮数会被低估却没人知道。"""
    spec = {"thin": (1, 1), "good-a": (40, 0), "good-b": (40, 0)}
    _rate_snapshot(tmp_path, spec)
    meta_path = tmp_path / "snapshot-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["history"] = [{"per_workflow": "not-a-dict"}, {}, "junk"]
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    code, message = live_gate.check_per_workflow_rate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_OK, message
    assert "3 条历史形状无效" in message


def test_history_rounds_do_not_participate_in_the_drift_check(tmp_path: Path) -> None:
    """历史条目描述的是过去几轮各自的快照，不能拿它们跟当前内容比。

    它们本来就该与当前 ``per_workflow`` 不同（数据变了），若把它们纳入漂移
    校验，每次重导后这一步都会判 4——处置指向「重导」，而问题在判据自己。
    """
    spec = {"wf-a": (20, 1), "wf-b": (20, 1)}
    _rate_snapshot(tmp_path, spec)
    _write_history(tmp_path, [{"wf-a": (2, 2), "wf-b": (2, 0)}])
    code, message = live_gate.check_per_workflow_rate(tmp_path, margin=10.0)
    assert code == live_gate.EXIT_OK, message


def test_committed_snapshot_records_the_current_export_in_history() -> None:
    """入库快照的历史必须以它自己的那一次导出收尾。

    这是「连续 N 轮」的分母：历史里的最后一条等于当前 ``per_workflow``，
    下一轮重导追加一条，连续性就有据可查；若这一条缺失，本轮会被补进来，
    提示会比数据实际支持的晚一轮。
    """
    meta = json.loads(
        (SNAPSHOT_ROOT / "snapshot-meta.json").read_text(encoding="utf-8"))
    history = meta.get("history")
    assert isinstance(history, list) and history, "快照元数据缺 history 块"
    last = history[-1]
    assert last["exported_at"] == meta["exported_at"]
    current = {name: {"attempts": bucket["attempts"], "failed": bucket["failed"]}
               for name, bucket in meta["per_workflow"].items()}
    assert last["per_workflow"] == current


def test_the_exceeds_fixture_really_exceeds() -> None:
    """CI 拿它做硬门槛的反向验证，所以它自己的判决必须先被钉住。"""
    code, message = live_gate.check_per_workflow_rate(
        EXCEEDS_ROOT, margin=10.0, fail_on_exceeds=True)
    assert code == live_gate.EXIT_GATE_TRIGGERED, message
    assert "1 个超出" in message


def test_the_exceeds_fixture_only_fails_with_the_flag() -> None:
    """没有 ``--fail-on-exceeds`` 时必须退出 0——红是开关带来的，不是数据本身。

    这条同时是 CI 反向验证语义的存档：那一步断言的是「开关打开后判 1」。
    """
    code, message = live_gate.check_per_workflow_rate(EXCEEDS_ROOT, margin=10.0)
    assert code == live_gate.EXIT_OK, message
    assert "报告模式" in message


def test_exceeds_is_driven_by_the_interval_not_the_point_estimate(
        tmp_path: Path) -> None:
    """判定用区间下界，不是点估计——点估计会让薄样本轻易判超。

    构造一个点估计明显高于阈值、但下界仍在阈值之下的样本：30 次尝试 6 次失败
    （点估计 20%），其余三个 workflow 零失败时基线 0%、阈值 10%。点估计 20%
    已经超过 10%，但 95% 下界只有 4.45%，所以必须判 ``undetermined``。

    这是 R55 §1「判据不许说反话」在另一条判据上的延伸：窄样本的点估计几乎必然
    越过某个阈值，用点估计判就等于「样本越小越容易被判坏」。
    """
    _rate_snapshot(tmp_path, {"mild": (30, 6), "good-a": (40, 0), "good-b": (40, 0)})
    report = live_gate.per_workflow_rate_report(
        live_gate.recompute_per_workflow(tmp_path / "workflows"), margin=10.0)
    assert report["mild"]["rate_pct"] == pytest.approx(20.0)
    assert report["mild"]["verdict"] == "undetermined", report["mild"]


def test_fail_on_exceeds_requires_the_rate_check(monkeypatch) -> None:
    """``--fail-on-exceeds`` 单独出现时报错，而不是被静默忽略。

    静默忽略会让「我加了开关、CI 却没红」变成一个无人排查的谜。与判据互斥
    检查同一纪律：不确定的配置在参数层就炸掉。
    """
    import sys

    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py", "--check-sample-size", "--fail-on-exceeds"])
    with pytest.raises(SystemExit) as excinfo:
        live_gate.main()
    assert excinfo.value.code == 2


def test_fail_if_above_is_rejected_on_check_modes(monkeypatch) -> None:
    """上限只属于默认判定模式：与 ``--check-*`` 同给时报错。

    静默接受会让人以为「样本量判据也按这个上限判」，而它判的是精度，与上限无关。
    与 ``--fail-on-exceeds`` 那条同一纪律：不确定的配置在参数层就炸掉。
    """
    import sys

    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py", "--check-sample-size", "--fail-if-above", "8"])
    with pytest.raises(SystemExit) as excinfo:
        live_gate.main()
    assert excinfo.value.code == 2


def test_margin_is_rejected_in_default_mode(monkeypatch) -> None:
    """``--margin`` 在默认模式里没有作用，必须报错而不是静默忽略。

    R57 之后默认模式的阈值只来自 ``--fail-if-above``。静默忽略会让「我把余量
    收紧到 2，CI 却没变」变成一个无人排查的谜。
    """
    import sys

    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py", "--margin", "5"])
    with pytest.raises(SystemExit) as excinfo:
        live_gate.main()
    assert excinfo.value.code == 2


def test_fail_if_above_out_of_range_is_rejected(monkeypatch) -> None:
    """``>=100`` 的上限永远判不出超阈（又一个恒绿），``<0`` 则任何数据都超。

    100 也要拒绝：CP 上界最多到 100%，判据又要求整个区间都高于上限，于是
    ``--fail-if-above 100`` 是一个写着「容忍一切」的恒绿配置——与自指阈值同一类
    失效，只是更容易被发现。
    """
    import sys

    for value in ("101", "100", "-0.5"):
        monkeypatch.setattr(sys, "argv", [
            "check_live_snapshot_gate.py", "--fail-if-above", value])
        with pytest.raises(SystemExit) as excinfo:
            live_gate.main()
        assert excinfo.value.code == 2, f"--fail-if-above {value} 应被拒绝"


def test_cli_default_mode_honours_the_ceiling(monkeypatch) -> None:
    """``main()`` 要把 ``--fail-if-above`` 真的传下去：1% 时退出 1。

    只测 ``evaluate`` 不管用——接线断了的话，CI 里那一步又会退回「阈值没人给」
    的报告模式，而报告模式恒退出 0。
    """
    import sys

    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py", "--fail-if-above", "1",
        "--data-dir", str(SNAPSHOT_ROOT)])
    assert live_gate.main() == live_gate.EXIT_GATE_TRIGGERED


def _rate_step(job: str) -> dict:
    """指定 job 上的 per-workflow 失败率步骤（R56）。"""
    steps = _backend_steps() if job == "backend" else _windows_backend_steps()
    hits = [s for s in steps
            if _has_flag(str(s.get("run", "")), "--check-per-workflow-rate")]
    assert len(hits) == 1, (
        f"ci.yml 的 {job} job 必须且只能有一处跑 --check-per-workflow-rate"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def test_rate_report_is_wired_into_ci() -> None:
    """与样本量判据同理：只读快照自身，所以能进 CI 检出真判。"""
    run = str(_rate_step("backend")["run"])
    assert "python scripts/check_live_snapshot_gate.py" in run
    assert "tests/fixtures/live_snapshot" in run


def test_rate_report_ci_step_is_not_permanently_green() -> None:
    """报告模式不等于恒绿：必须注入漂移并断言退出码 4。

    没有这一条，判据彻底失效时这一步仍然绿——因为「超出基线」在报告模式下
    本来就不判失败。漂移注入是本步骤唯一的红路径，必须真的在那儿。
    """
    run = str(_rate_step("backend")["run"])
    assert "per_workflow" in run, "CI 步骤没有注入漂移样本"
    assert "-ne 4" in run or "-eq 4" in run, (
        "CI 步骤没有断言退出码 4，判据失去判定力也不会被发现"
    )


def _rate_invocations(run: str) -> list[str]:
    """这一段里每一次调用失败率判据的命令行。

    先把 ``\\`` 续行拼回一行再按行取：命令行可能写成两行，只看含开关的那一行
    会漏掉紧随其后的 ``--fail-on-exceeds``——与 R57 对 ``--fail-if-above``
    的处理同一理由，只断言「这一步里出现过某个开关」会给出错误的安全感。
    """
    joined = run.replace("\\\n", " ")
    return [line for line in joined.splitlines()
            if "--check-per-workflow-rate" in line]


def test_rate_gate_ci_step_hard_fails_on_exceeds() -> None:
    """R58 硬门槛：两个 runner 的失败率步骤里**每一次**调用都必须带开关。

    R56 的那条断言方向相反（当时钉住「不得加」，两步走的第一步），R57 §11-1
    把它列为下一轮要改的那一行。改成硬门槛的前提在 R57 已备好：主闸门的自指
    阈值修掉之后，「判不了」不再冒充「不合格」。两个 runner 同口径是 R52/R57
    的纪律——漂开就会在两个平台给出互相矛盾的结论。

    按「每一次调用都带」检查而不是「这一段里出现过」：真实判定那次不带、只有
    反向验证带，同样能骗过后者。
    """
    for job in ("backend", "windows-backend"):
        invocations = _rate_invocations(str(_rate_step(job)["run"]))
        assert len(invocations) >= 2, (
            f"{job} 应同时有真实判定与全挂快照反向验证两次调用"
            f"（实际 {len(invocations)} 次）")
        for line in invocations:
            assert _has_flag(line, "--fail-on-exceeds"), (
                f"{job} 有一次调用没带 --fail-on-exceeds，硬门槛在那次上等于没接："
                f"{line.strip()}")


def test_rate_gate_ci_step_reverse_verifies_the_hard_failure() -> None:
    """反向验证必须真的断言「全挂快照 → 退出码 1」。

    只跑真实快照会得到一个恒绿步骤：判据失效、开关丢了、甚至整段判据退化成
    报告模式，它都绿。全挂快照（``live_snapshot_exceeds``）在测试里已被钉住
    判 ``exceeds``，CI 断言它的退出码为 1；``-ne 1`` 必须出现在引用该快照
    之后，否则断言的可能是不相干的那一次调用。
    """
    for job in ("backend", "windows-backend"):
        run = str(_rate_step(job)["run"])
        invocations = _rate_invocations(run)
        assert any("live_snapshot_exceeds" in line for line in invocations), (
            f"{job} 的失败率步骤没有全挂快照的反向验证")
        assert "-ne 1" in run, f"{job} 没有断言全挂快照的退出码 1"
        assert run.index("live_snapshot_exceeds") < run.index("-ne 1"), (
            f"{job} 的「期望 1」断言出现在全挂快照调用之前：它断言的不是那一次")


def test_windows_runner_also_reports_per_workflow_rate() -> None:
    """Windows job 上有同一段，且末尾显式 ``exit 0``。

    GHA 的 pwsh 包装器会在末尾追加 ``exit $LASTEXITCODE``，而最后一条原生命令
    正是那次故意以 4 退出的漂移验证——不显式 exit 0 的话，全部分支判对、日志
    也打了 OK，步骤仍然红（R52 实测踩到）。
    """
    run = str(_rate_step("windows-backend")["run"])
    assert "per_workflow" in run
    assert "-ne 4" in run
    assert "exit 0" in run


def test_rate_report_does_not_reintroduce_stale_or_coverage() -> None:
    """新步骤不得顺手把 --check-stale/--check-coverage 拉进 CI（同一纪律）。"""
    for job in ("backend", "windows-backend"):
        run = str(_rate_step(job)["run"])
        assert "--check-stale" not in run
        assert "--check-coverage" not in run
