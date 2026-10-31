"""判据容忍量的翻转点（R69）。

`tests/test_judgement_ledger.py` 钉住的是「登记页上的数 == 代码里的常量」。那还
不够：一个把阈值写成 `基线 + margin * 2` 的实现，常量完全相同，**边界却挪了
一倍**——日志、文档、CI 文案全都对得上，只有判决是错的。

本文件对登记页上每一个**带数字**的容忍量构造两次输入：

- **边界内**（容忍量的内侧）：必须通过 / 不判失败；
- **边界外**（刚好越过一步）：必须判失败。

并断言判决真的翻转。阈值本身一律取自代码常量（`REGRESSION_MARGIN`、
`DEFAULT_MARGIN`、`DEFAULT_MAX_LAG_DAYS`、`UNDER_SLEEP_TOLERANCE`、
`OVER_SLEEP_TOLERANCE`、`BACKOFF_EXTRA_MIN_SECONDS`），不在这里写第二份字面量。

最后一条是**覆盖守卫**：登记页 §2 的容忍量列里出现数字的行，必须在本文件登记
一个翻转点用例，且用例名必须出现在登记页 §7——「有数字」与「有翻转点」不能
各写各的。

R72 补的是这些翻转点的**前提**：#4 的「元数据漂移 → 退出 4」「无样本 → 退出 3」
两条路径，R56 的用例各测各的、与这里用的不是同一组计数。本文件用 #4 的同一组
计数把门与翻转点绑在一起——翻转点不仅要翻得动，还得真的能被走到。
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from scripts import check_live_snapshot_gate as gate
from scripts import e2e_workflow_stub as e2e

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / "docs" / "JUDGEMENT_LEDGER.md"

# 登记页 §2 的判据编号 → 钉住它翻转点的用例名（一条判据可以有多条，R70 起）。
# 没有数字容忍量的行（#7 覆盖度、#10 算术失败）不在此列，由覆盖守卫逐条核对。
_FLIP_POINT_TESTS = {
    "1": ("test_policy_ceiling_flips_between_28_and_29_failures",),
    "2": ("test_merged_regression_margin_flips_at_26_failures",),
    "3": ("test_per_workflow_regression_margin_flips_at_the_registered_k",),
    "4": ("test_leave_one_out_margin_flips_at_four_failures",
          "test_leave_one_out_baseline_drives_the_flip_point",
          "test_leave_one_out_flip_point_through_the_real_gate",
          "test_metadata_drift_preempts_the_leave_one_out_verdict",
          "test_no_sample_preempts_the_leave_one_out_verdict"),
    "5": ("test_sample_size_margin_flips_between_28_and_29_attempts",),
    "6": ("test_freshness_flips_at_the_registered_days",
          "test_freshness_default_is_the_registered_days",
          "test_freshness_flips_within_one_microsecond"),
    "8": ("test_shape_tolerances_flip_on_both_sides",),
    "9": ("test_backoff_amplitude_flips_at_the_registered_minimum",),
}


# ------------------------------------------------ #1 政策上限 8 个百分点

def test_policy_ceiling_flips_between_28_and_29_failures() -> None:
    """n=255 时 k=28 判不了、k=29 判超阈（与 failure-ceiling-calibration §3 同数）。"""
    assert gate._ceiling_verdict(255, 28, 8.0)[0] != "exceeds"
    assert gate._ceiling_verdict(255, 29, 8.0)[0] == "exceeds"


# ------------------------------------------------ #2 合并层回归 3 个百分点

def test_merged_regression_margin_flips_at_26_failures() -> None:
    """基线 10/255：k=25（9.80%）判不了，k=26（10.20%）判回归。

    阈值 = 3.92% + REGRESSION_MARGIN；两次只差一次失败，判决必须翻转。
    """
    baseline = (255, 10)
    assert gate._baseline_verdict(
        255, 25, baseline[0], baseline[1], gate.REGRESSION_MARGIN)[0] == "undetermined"
    assert gate._baseline_verdict(
        255, 26, baseline[0], baseline[1], gate.REGRESSION_MARGIN)[0] == "exceeds"


# ------------------------------------------------ #3 逐 workflow 回归 10 个百分点

def test_per_workflow_regression_margin_flips_at_the_registered_k() -> None:
    """character 2/79：第 15 次失败判不了，第 16 次（20.25%）判回归。

    这是登记页 #3 与 §4 提前量表里「第 16 次开口」的同一个数——翻转点用例与
    提前量命令必须落在同一处，否则表格会替判据说话。
    """
    previous = {"character": (79, 2)}
    at_15 = gate.per_workflow_regression_report(
        previous, {"character": (79, 15)}, gate.DEFAULT_MARGIN)
    at_16 = gate.per_workflow_regression_report(
        previous, {"character": (79, 16)}, gate.DEFAULT_MARGIN)
    assert at_15["character"]["verdict"] == "undetermined", at_15["character"]["reason"]
    assert at_16["character"]["verdict"] == "exceeds", at_16["character"]["reason"]


# ------------------------------------------------ #4 留一法 10 个百分点

def test_leave_one_out_margin_flips_at_four_failures() -> None:
    """留一法基线 0/30 时，10 次尝试里第 3 次判不了、第 4 次判超出。

    #4 与 #2/#3 共用 ``_rate_verdict``；这里钉的是它在「其余 workflow 合并基线」
    这个总体上的翻转点，防止有人给留一法单独换一套阈值。
    """
    baseline_pct = 0.0
    assert gate._rate_verdict(
        10, 3, baseline_pct, gate.DEFAULT_MARGIN)[0] == "undetermined"
    assert gate._rate_verdict(
        10, 4, baseline_pct, gate.DEFAULT_MARGIN)[0] == "exceeds"


def test_leave_one_out_baseline_drives_the_flip_point() -> None:
    """同一条翻转点，这次基线必须由 ``per_workflow_baselines`` **算出来**（R70）。

    上一条用例把 ``baseline_pct = 0.0`` 当字面量传进 ``_rate_verdict``，它钉的是
    「阈值 = 基线 + 10」这一步；但基线本身怎么来的它完全看不见。于是两种改法都能
    在它面前保持全绿：把基线换成**含自己的全局合计**（R56 修掉的那个自指错误），
    或者给留一法这一条路单独换一套阈值。

    这里从 ``{workflow: (attempts, failed)}`` 出发，走完整的
    ``per_workflow_baselines`` → ``per_workflow_rate_report`` 路径，
    让「基线」与「翻转点」咬在同一处：

    - rest 30 次零失败 ⇒ target 的留一法基线是 0/30 = 0.0%（**不含自己**）；
    - target 10 次里 3 次失败判不了、4 次（40%）判超出。

    两个改法都会在这里掉：换全局合计时基线变成 4/40 = 10%（阈值 20%），
    4 次失败的 95% 下界 12.2% 仍在阈值之下，``exceeds`` 出不来；
    留一法单独乘 2 时阈值 20%，同样说不出 ``exceeds``。
    """
    rest = {"attempts": 30, "failed": 0}
    at_3 = {"rest": rest, "target": {"attempts": 10, "failed": 3}}
    at_4 = {"rest": rest, "target": {"attempts": 10, "failed": 4}}

    # 基线取自代码算出来的值，且**不随 target 自己的失败数变化**——这正是
    # 「留一法」三个字的意思，也是 k=4 还能翻得过去的原因。
    assert gate.per_workflow_baselines(at_3)["target"] == pytest.approx(0.0)
    assert gate.per_workflow_baselines(at_4)["target"] == pytest.approx(0.0)
    assert (gate.per_workflow_baselines(at_4)["target"]
            == gate.per_workflow_baselines(at_3)["target"])

    report_3 = gate.per_workflow_rate_report(at_3, gate.DEFAULT_MARGIN)
    report_4 = gate.per_workflow_rate_report(at_4, gate.DEFAULT_MARGIN)
    assert report_3["target"]["verdict"] == "undetermined", report_3["target"]["detail"]
    assert report_4["target"]["verdict"] == "exceeds", report_4["target"]["detail"]
    # 明细里的基线必须是算出来的那个 0.00%，而不是被写死在报告里的数。
    assert "基线 0.00%" in report_4["target"]["detail"], report_4["target"]["detail"]


# ------------------------------------------------ #4 的退出路径前提（R72）

def _write_rate_snapshot(root: Path, spec: dict[str, tuple[int, int]],
                         declare_meta: bool = True) -> None:
    """造一份 ``check_per_workflow_rate`` 真能读到的落盘快照。

    ``spec`` 是 ``{workflow: (attempts, failed)}``，每个 workflow 一个 run，
    attempt 数就是 attempts。形状与 ``test_live_snapshot_gate.py`` 里的
    ``_write_per_workflow_snapshot`` 相同；这里保留一份本地副本：``tests/``
    没有 ``__init__.py``，跨测试模块 import 依赖 pytest 的 prepend 模式，
    比复制这二十行更脆（与 R70 的 ``_write_snapshot`` 同一取舍）。
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


def test_leave_one_out_flip_point_through_the_real_gate(tmp_path: Path) -> None:
    """#4 的翻转点必须能穿过真实入口：落盘快照 → 漂移校验 → 报告 → 退出码。

    R70 的两条用例都停在纯函数层（``_rate_verdict`` / ``per_workflow_baselines``
    → ``per_workflow_rate_report``），没有任何一条证明磁盘上的计数能走到同一个
    翻转点。这里用 §7 第 4 行的同一组计数（rest 30/0、target 10 次里 k 次失败）
    跑 ``check_per_workflow_rate``：k=3 不判失败、k=4 在硬门槛下退出 1；报告
    模式仍退出 0——开关是唯一的差别。
    """
    at_3 = tmp_path / "at-3"
    _write_rate_snapshot(at_3, {"rest": (30, 0), "target": (10, 3)})
    code, message = gate.check_per_workflow_rate(
        at_3, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_OK, message
    assert "0 个超出" in message, message
    assert "1 个样本不足无法判定" in message, message

    at_4 = tmp_path / "at-4"
    _write_rate_snapshot(at_4, {"rest": (30, 0), "target": (10, 4)})
    code, message = gate.check_per_workflow_rate(
        at_4, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_GATE_TRIGGERED, message
    assert "1 个超出" in message, message
    assert "target" in message, message

    code, message = gate.check_per_workflow_rate(at_4, gate.DEFAULT_MARGIN)
    assert code == gate.EXIT_OK, message
    assert "报告模式" in message, message


def test_metadata_drift_preempts_the_leave_one_out_verdict(tmp_path: Path) -> None:
    """漂移必须说在判决之前：同一份 k=4 快照，元数据改写后只能退出 4。

    R56 的漂移用例用的是「无论如何都判不出超出」的计数，所以「只有判不出时才
    查漂移」这类改法在它面前全绿——而它会让一个真实失败被一句元数据改写成
    「判不了」。这里故意用 §7 第 4 行的边界外计数（target 4/10），并把一次失败
    从 rest 挪进 target 的元数据：全局合计分毫不动（这正是分组校验存在的理由），
    内容仍是 target 4/10，任何「先判后查」的路径都会说出「超出」。
    """
    snap = tmp_path / "snap"
    _write_rate_snapshot(snap, {"rest": (30, 0), "target": (10, 4)})
    meta = json.loads((snap / "snapshot-meta.json").read_text(encoding="utf-8"))
    meta["per_workflow"]["rest"]["failed"] = 1
    meta["per_workflow"]["target"]["failed"] = 3
    (snap / "snapshot-meta.json").write_text(json.dumps(meta), encoding="utf-8")

    code, message = gate.check_per_workflow_rate(
        snap, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_META_DRIFT, message
    assert "rest" in message and "target" in message, message
    assert "重导" in message, message
    assert "超出" not in message, message


def test_no_sample_preempts_the_leave_one_out_verdict(tmp_path: Path) -> None:
    """无样本同样必须先于判决：退出 3 的三条分支都不许说出判决词。

    R56 只测了「缺 ``per_workflow`` 块」一种；这里用 §7 第 4 行的边界外计数
    把三条分支都对齐一次：缺元数据文件 / 缺块 / 元数据说有但内容为空。否则
    「元数据里有数就拿来判」这种改法可以让一个空快照判出超出。
    """
    missing_meta = tmp_path / "missing-meta"
    missing_meta.mkdir()
    code, message = gate.check_per_workflow_rate(
        missing_meta, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_NO_SAMPLE, message
    assert "快照元数据缺失" in message, message
    assert "超出" not in message, message

    missing_block = tmp_path / "missing-block"
    _write_rate_snapshot(missing_block, {"rest": (30, 0), "target": (10, 4)},
                         declare_meta=False)
    code, message = gate.check_per_workflow_rate(
        missing_block, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_NO_SAMPLE, message
    assert "per_workflow" in message, message
    assert "超出" not in message, message

    empty_content = tmp_path / "empty-content"
    _write_rate_snapshot(empty_content, {"rest": (30, 0), "target": (10, 4)})
    shutil.rmtree(empty_content / "workflows")
    code, message = gate.check_per_workflow_rate(
        empty_content, gate.DEFAULT_MARGIN, fail_on_exceeds=True)
    assert code == gate.EXIT_NO_SAMPLE, message
    assert "没有任何带 run 记录的工作流" in message, message
    assert "超出" not in message, message


# ------------------------------------------------ #5 样本量 margin 10 个百分点

def test_sample_size_margin_flips_between_28_and_29_attempts() -> None:
    """零失败时 28 次尝试差 0.15 个百分点、29 次达标——判据必须在这一步翻转。"""
    assert gate.sample_size_margin_needed(28, 0) > gate.DEFAULT_MARGIN
    assert gate.sample_size_margin_needed(29, 0) <= gate.DEFAULT_MARGIN
    assert gate._failure_rate_precision(28, 0, gate.DEFAULT_MARGIN)[0] is False
    assert gate._failure_rate_precision(29, 0, gate.DEFAULT_MARGIN)[0] is True


# ------------------------------------------------ #6 快照保鲜 7 天

def _write_snapshot(root: Path, exported_at: str) -> None:
    runs = root / "workflows" / "wf" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "run-a.json").write_text(
        json.dumps({"run_id": "run-a", "status": "completed",
                    "node_executions": []}), encoding="utf-8")
    (root / "snapshot-meta.json").write_text(
        json.dumps({"totals": {"attempts": 0, "failed": 0},
                    "exported_at": exported_at}), encoding="utf-8")


def _write_real_run(root: Path, started_at: str) -> None:
    runs = root / "wf" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "run-real.json").write_text(
        json.dumps({"run_id": "run-real", "status": "running",
                    "started_at": started_at, "completed_at": None}),
        encoding="utf-8")


def test_freshness_flips_at_the_registered_days(tmp_path: Path) -> None:
    """滞后 7.0 天通过、7.1 天过期；且**默认值**就是 7（不给开关也一样）。"""
    exported = "2026-01-01T00:00:00+00:00"
    snap, inside, outside = tmp_path / "snap", tmp_path / "inside", tmp_path / "outside"
    _write_snapshot(snap, exported)
    _write_real_run(inside, "2026-01-07T21:36:00+00:00")   # 6.9 天
    _write_real_run(outside, "2026-01-08T02:24:00+00:00")  # 7.1 天

    assert gate.check_stale(snap, inside, gate.DEFAULT_MAX_LAG_DAYS)[0] == gate.EXIT_OK
    assert gate.check_stale(snap, outside, gate.DEFAULT_MAX_LAG_DAYS)[0] == gate.EXIT_STALE
    # 恰好在边界上：7.0 天不算过期（判据是「滞后 ≤ N」）。
    exact = tmp_path / "exact"
    _write_real_run(exact, "2026-01-08T00:00:00+00:00")
    assert gate.check_stale(snap, exact, gate.DEFAULT_MAX_LAG_DAYS)[0] == gate.EXIT_OK


def test_freshness_default_is_the_registered_days(monkeypatch, tmp_path: Path) -> None:
    """不传 ``--max-lag-days`` 时，7.1 天必须红——默认值不是文档里的一句话。"""
    snap, outside = tmp_path / "snap", tmp_path / "outside"
    _write_snapshot(snap, "2026-01-01T00:00:00+00:00")
    _write_real_run(outside, "2026-01-08T02:24:00+00:00")
    monkeypatch.setattr(sys, "argv", [
        "check_live_snapshot_gate.py", "--check-stale",
        "--data-dir", str(snap), "--source", str(outside)])
    assert gate.main() == gate.EXIT_STALE


def test_freshness_flips_within_one_microsecond(tmp_path: Path) -> None:
    """边界落在 1 微秒上：7 天 −1µs 通过、7 天 +1µs 过期（R70）。

    上一条用的是整点时间戳，「7.0 天」在整秒世界里恰好可表示。真正容易出错的
    不是比较符，而是**时间算术的粒度**：把 ``total_seconds() / 86400`` 改成
    ``(latest - exported).days``、或者把天数四舍五入到 0.1 天，7 天加一秒都还能
    判成「尚新」——而这恰好是真实重导会落到的位置（每一次重导滞后都会往整数
    天上贴）。这里用微秒把「滞后是按秒算的、边界是精确的」钉死。
    """
    exported = "2026-01-01T00:00:00+00:00"
    snap = tmp_path / "snap"
    _write_snapshot(snap, exported)
    below = tmp_path / "below"
    _write_real_run(below, "2026-01-07T23:59:59.999999+00:00")   # 7 天 − 1 微秒
    above = tmp_path / "above"
    _write_real_run(above, "2026-01-08T00:00:00.000001+00:00")   # 7 天 + 1 微秒

    assert gate.check_stale(
        snap, below, gate.DEFAULT_MAX_LAG_DAYS)[0] == gate.EXIT_OK
    assert gate.check_stale(
        snap, above, gate.DEFAULT_MAX_LAG_DAYS)[0] == gate.EXIT_STALE


# ------------------------------------------------ #8 e2e 形状（欠睡 0.05 / 超睡 0.30）

def test_shape_tolerances_flip_on_both_sides() -> None:
    """欠睡 −0.050 通过 / −0.051 失败；超睡 +0.300 通过 / +0.301 失败。

    两侧都测：只测一侧的话，把 `> over_tol` 写成 `>= over_tol` 这种一字之差
    不会有人发现（它会把「恰好 0.30s」的抖动判红）。
    """
    configured = [0.4]
    assert e2e._rising_shape_violations([0.35], configured) == []      # −0.050
    assert e2e._rising_shape_violations([0.349], configured) != []     # −0.051
    assert e2e._rising_shape_violations([0.70], configured) == []      # +0.300
    assert e2e._rising_shape_violations([0.701], configured) != []     # +0.301
    # 数字必须就是登记页写的那两个，不在这里另拍。
    assert e2e.UNDER_SLEEP_TOLERANCE == pytest.approx(0.05)
    assert e2e.OVER_SLEEP_TOLERANCE == pytest.approx(0.30)


# ------------------------------------------------ #9 e2e 单点幅度 0.7s

def test_backoff_amplitude_flips_at_the_registered_minimum() -> None:
    """多出 0.700s 通过 / 0.699s 失败（判据是 `extra < 0.7` 即失败）。"""
    assert e2e._backoff_amplitude_problems({"zero": 0.0, "configured": 0.7}) == []
    assert e2e._backoff_amplitude_problems({"zero": 0.0, "configured": 0.699}) != []


# ------------------------------------------------ 覆盖守卫

def _ledger_rows(section_start: str, section_end: str) -> list[list[str]]:
    text = LEDGER.read_text(encoding="utf-8")
    start = text.index(section_start)
    end = text.index(section_end, start)
    rows = []
    for line in text[start:end].splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.split("|")]
        rows.append(cells)
    return rows


def test_every_numeric_tolerance_has_a_registered_flip_point() -> None:
    """登记页 §2 里有数字的容忍量，必须有一条翻转点用例，且用例名写进 §7。"""
    rows = _ledger_rows("## 2. 逐条登记", "## 3.")
    numeric: dict[str, str] = {}
    for cells in rows:
        # cells[0] == ""、cells[1] == 编号、cells[5] == 容忍量
        if len(cells) < 6 or not cells[1].isdigit():
            continue
        tolerance = cells[5]
        if any(ch.isdigit() for ch in tolerance):
            numeric[cells[1]] = tolerance
    assert numeric, "登记页 §2 没有解析出任何带数字的容忍量（表格格式变了？）"
    assert set(numeric) == set(_FLIP_POINT_TESTS), (
        f"登记页上有数字但没有翻转点的判据：{sorted(set(numeric) - set(_FLIP_POINT_TESTS))}；"
        f"登记了翻转点但登记页没有数字的判据：{sorted(set(_FLIP_POINT_TESTS) - set(numeric))}")
    spread = LEDGER.read_text(encoding="utf-8")
    for judgement_id, test_names in _FLIP_POINT_TESTS.items():
        for test_name in test_names:
            assert callable(globals().get(test_name)), (
                f"判据 #{judgement_id} 登记的翻转点用例 {test_name} 不存在")
            assert test_name in spread, (
                f"判据 #{judgement_id} 的翻转点用例 {test_name} 没有写进登记页 §7")
