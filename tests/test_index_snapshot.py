"""R137：索引 §1 快照数字机械化。

背景（实测，R136 §7）：``HANDOVER_INDEX.md`` §1 是给人看的三行快照
（交接文档份数、当前用例、写回历史），每轮靠手更新，漂移是常态——R137
开工实测：交接文档行停在「109 份（24..134）」，磁盘已是 **111 份
（24..136）**（R135/R136 两轮都没更新该行）；更早的例子见索引 §6.2
（写回 run 未记账）与 R133（写回行停在 62、实际已 63）。

本文件把三行变成机判（**S 系判据**），允许的口径只有「磁盘实况」：

- **S1 交接文档行**：份数 == 磁盘 ``HANDOVER_ROUND*.md`` 数量；行内的
  轮次区间 ``24..M`` 两端都必须等于磁盘的最小/最大轮次号。
- **S2 写回行**：``K / 80`` 的 K == history.json 条目数，且行内末条
  ``ci-<id>`` == 第 K 条的 run_id（行内自洽 + 与磁盘恰等）。
- **S3 用例行**：数字 == ``pytest --collect-only`` 的收集数。用例数不能
  从磁盘直接算，但收集数可以确定性导出（仓库无模块级 ``importorskip``，
  收集数跨平台一致——R137 实测）。改测试不改索引行，CI 红。

边界：行的**括号注记**（passed/skipped 计数、「R14x 跑预计」之类）不钉
——平台差异与预期值不该机械化；行的**存在**与三行的键名（交接文档 /
当前用例 / CI 写回历史）钉住——行被删也红。索引其余部分由 R133 的
N2/N3 与 R135/R136 的判据覆盖。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = REPO_ROOT / "docs" / "HANDOVER_INDEX.md"
HISTORY = REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history" / "history.json"

ROW_DOCS = "交接文档"
ROW_CASES = "当前用例"
ROW_WRITEBACK = "CI 写回历史"


def _index_row(key: str) -> str:
    for line in INDEX.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith(f"| {key} |"):
            return line
    raise AssertionError(f"索引 §1 缺少「{key}」行——快照行被删，S 判据失守")


def _history_entries() -> list[dict]:
    document = json.loads(HISTORY.read_text(encoding="utf-8"))
    entries = document["history"] if isinstance(document, dict) else document
    assert isinstance(entries, list) and entries, "history.json 没有条目"
    return entries


def _disk_handover_files() -> list[Path]:
    files = sorted(Path(REPO_ROOT, "docs").glob("HANDOVER_ROUND*.md"))
    assert files, "docs/ 下没有交接文档"
    return files


def test_docs_row_matches_disk_inventory() -> None:
    """S1：交接文档行——份数与轮次区间两端都必须等于磁盘实况。"""
    line = _index_row(ROW_DOCS)
    files = _disk_handover_files()
    nums = [int(re.search(r"ROUND(\d+)", p.name).group(1)) for p in files]
    count_match = re.search(r"\*\*(\d+)\s*份\*\*", line)
    assert count_match, f"交接文档行没有「**N 份**」：{line.strip()[:80]}"
    assert int(count_match.group(1)) == len(files), (
        f"交接文档份数漂移：行写 {count_match.group(1)}，磁盘 {len(files)} 份"
    )
    range_match = re.search(r"HANDOVER_ROUND(\d+)\.\.(\d+)\.md", line)
    assert range_match, f"交接文档行没有 24..M 区间写法：{line.strip()[:80]}"
    lo, hi = int(range_match.group(1)), int(range_match.group(2))
    assert (lo, hi) == (min(nums), max(nums)), (
        f"轮次区间漂移：行写 {lo}..{hi}，磁盘 {min(nums)}..{max(nums)}"
    )


def test_writeback_row_matches_history_ledger() -> None:
    """S2：写回行——K == history 条目数，且末条 id == 第 K 条的 run_id。"""
    line = _index_row(ROW_WRITEBACK)
    entries = _history_entries()
    count_match = re.search(r"\*\*(\d+)\s*/\s*80\s*轮\*\*", line)
    assert count_match, f"写回行没有「**K / 80 轮**」：{line.strip()[:80]}"
    claimed = int(count_match.group(1))
    assert claimed == len(entries), (
        f"写回条数漂移：行写 {claimed}，history.json 实为 {len(entries)} 条"
    )
    last_match = re.search(r"末条 `ci-(\d+)`", line)
    assert last_match, f"写回行没有末条 run id：{line.strip()[:80]}"
    expected_last = str(entries[claimed - 1]["run_id"])
    assert expected_last == f"ci-{last_match.group(1)}", (
        f"末条漂移：行写 ci-{last_match.group(1)}，第 {claimed} 条实为 "
        f"{expected_last}"
    )


def test_case_count_row_matches_pytest_collection() -> None:
    """S3：用例行数字 == pytest --collect-only 的收集数（确定性导出）。"""
    line = _index_row(ROW_CASES)
    count_match = re.search(r"\*\*([\d,]+)\*\*", line)
    assert count_match, f"用例行没有「**N**」：{line.strip()[:80]}"
    claimed = int(count_match.group(1).replace(",", ""))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    collect_match = re.search(r"(\d+) tests? collected", tail)
    assert collect_match, (
        f"收集失败（退出码 {proc.returncode}），末行：{tail[:200]}\n"
        f"{proc.stdout[-500:] if proc.stdout else ''}"
    )
    actual = int(collect_match.group(1))
    assert claimed == actual, (
        f"用例数漂移：索引行写 {claimed}，pytest --collect-only 实为 {actual}"
        "（改测试必须同步更新索引 §1 用例行）"
    )
