"""判据全景登记的数字一致性（R65）。

R63 §9-2 把「判据全景登记」挂成待办：把退出码与 e2e 形状判据按「偏移型/
精度型/政策型/时钟型」分类入库，并回答 R63 的预算式能否迁移。

分类文字无法自动校验，但**数字可以**：登记页上的每个阈值都必须在代码里找到
同一个数，否则那一行就是文档在替判据吹牛。R64 已经这么错过一次——把共模预算
0.40s 当成单段预算写进文档，实际是 0.133s。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_live_snapshot_gate as gate
from scripts import e2e_workflow_stub as e2e

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / "docs" / "JUDGEMENT_LEDGER.md"


def _ledger() -> str:
    assert LEDGER.is_file(), f"判据全景登记页不存在：{LEDGER}"
    return LEDGER.read_text(encoding="utf-8")


def test_ledger_pins_every_exit_code_value() -> None:
    """退出码的**数值**必须与脚本常量逐字相同，且一个都不能漏。

    别处的用例只钉「互不相同」，没有钉字面值；登记页是唯一写着「5=过期、
    6=覆盖度」的地方，所以字面值在这里钉。
    """
    expected = {
        0: gate.EXIT_OK,
        1: gate.EXIT_GATE_TRIGGERED,
        3: gate.EXIT_NO_SAMPLE,
        4: gate.EXIT_META_DRIFT,
        5: gate.EXIT_STALE,
        6: gate.EXIT_COVERAGE_GAP,
        7: gate.EXIT_THIN_SAMPLE,
        8: gate.EXIT_NUMERIC_FAILURE,
    }
    text = _ledger()
    for documented, constant in sorted(expected.items()):
        assert documented == constant, (
            f"登记页写着 {documented}，脚本里是 {constant}")
        assert f"| {documented} |" in text, f"登记页的退出码表缺 {documented}"


def test_ledger_pins_the_e2e_shape_tolerances() -> None:
    """逐段容差与最小相邻差：三个形状场景都必须满足「容差 < 相邻差」。"""
    assert e2e.UNDER_SLEEP_TOLERANCE == pytest.approx(0.05)
    assert e2e.OVER_SLEEP_TOLERANCE == pytest.approx(0.30)
    text = _ledger()
    assert "欠睡 0.05s" in text
    assert "超睡 0.30s" in text
    for configured in ([0.4, 0.8], [0.4, 0.8, 1.6], [0.4, 0.8, 1.6, 3.2]):
        budget = e2e._rising_shape_segment_budget(configured)
        assert budget.judgeable, configured
        assert budget.min_gap == pytest.approx(0.40), configured


def test_ledger_pins_the_regression_margin() -> None:
    assert gate.REGRESSION_MARGIN == pytest.approx(3.0)
    assert "3 个百分点" in _ledger()


def test_ledger_answers_the_r63_migration_question() -> None:
    """R63 §9-2 的问题必须有明确答案，而且答案里的数要是判据自己的算术。

    「不能直接迁移」这句话之所以可信，是因为同一页写清了前提三条与反例
    （单段预算是 0.133s 而不是 0.40s）。
    """
    text = _ledger()
    assert "不能直接迁移" in text
    assert "rho ≥ r" in text
    assert "c / a" in text
    assert "0.133" in text


def test_ledger_has_no_placeholder_rows() -> None:
    text = _ledger()
    for placeholder in ("TODO", "TBD", "待定"):
        assert placeholder not in text, f"登记页还留着 {placeholder}"
