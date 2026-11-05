"""R137 / R149：索引 §1 快照数字机械化。

背景（实测，R136 §7）：``HANDOVER_INDEX.md`` §1 是给人看的快照行（交接
文档份数、文档体量、当前用例、写回历史、代码基线），每轮靠手更新，漂移
是常态——R137 开工实测：交接文档行停在「109 份（24..134）」，磁盘已是
**111 份（24..136）**（R135/R136 两轮都没更新该行）；更早的例子见索引
§6.2（写回 run 未记账）与 R133（写回行停在 62、实际已 63）。

R137 先钉了三行（S1–S3）。R149 把余下两行也变成机判（**S 系续**）：
R146 的 L 系明确把「文档体量」留在射程外（它随轮次波动）、代码基线则
一直没人对账：

- **S1 交接文档行**：份数 == 磁盘 ``HANDOVER_ROUND*.md`` 数量；行内的
  轮次区间 ``24..M`` 两端都必须等于磁盘的最小/最大轮次号。
- **S2 写回行**：``K / 80`` 的 K == history.json 条目数，且行内末条
  ``ci-<id>`` == 第 K 条的 run_id（行内自洽 + 与磁盘恰等）。
- **S3 用例行**：数字 == ``pytest --collect-only`` 的收集数。用例数不能
  从磁盘直接算，但收集数可以确定性导出（仓库无模块级 ``importorskip``，
  收集数跨平台一致——R137 实测）。改测试不改索引行，CI 红。
- **S4 文档体量行**：行数 == 磁盘交接文档 ``splitlines()`` 总和；MB ==
  归一化 UTF-8 字节 / 1 MiB（保留 1 位）。读取统一换行，CRLF 工作树与
  LF 检出得到同一个值——体量只随语料变，不随平台变。
- **S5 代码基线行**：sha == history.json 末条 run 的 bot 提交
  （``git log --grep "record CI run <id>"``）；行内 ``R<n>`` == 该 bot
  提交父提交的轮次。判据锚在「写回账的第 K 条」上，而不是某个手抄的
  main 快照。

边界：行的**括号注记**（passed/skipped 计数、「R14x 跑预计」之类）不钉
——平台差异与预期值不该机械化；行的**存在**与五行的键名（交接文档 /
文档体量 / 当前用例 / CI 写回历史 / 代码基线）钉住——行被删也红。体量
行的 MB 只判到 1 位小数：语料增删一行不该让「1.1 MB」在 1.05 附近翻
成 1.0/1.1 两个值。索引其余部分由 R133 的 N2/N3、R135/R136 的判据与
R146/R147 的 L 系覆盖。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX = REPO_ROOT / "docs" / "HANDOVER_INDEX.md"
HISTORY = REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history" / "history.json"

ROW_DOCS = "交接文档"
ROW_VOLUME = "文档体量"
ROW_CASES = "当前用例"
ROW_WRITEBACK = "CI 写回历史"
ROW_BASELINE = "代码基线"
MIB = 1024 * 1024


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


def _normalized_volume() -> tuple[int, int]:
    """交接文档语料的归一化体量：(splitlines 总和, UTF-8 字节数)。

    ``read_text`` 默认统一换行：CRLF 工作树与 LF 检出在这里得到同一份文本，
    体量不会因平台翻转（R149 的跨平台前提）。
    """
    files = _disk_handover_files()
    lines = 0
    octets = 0
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        lines += len(text.splitlines())
        octets += len(text.encode("utf-8"))
    return lines, octets


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert proc.returncode == 0, (
        f"git {' '.join(args)} 失败（退出码 {proc.returncode}）："
        f"{proc.stderr.strip()[:200]}——浅检出必须显式红，不许 skip"
    )
    return proc.stdout


def _bot_commit_for(run_id: str) -> str:
    """history 的 ``ci-<id>`` → 写回 bot 提交（``git log --grep``）。"""
    assert run_id.startswith("ci-"), (
        f"history 末条不是 ci-<id> 形状：{run_id!r}——写回账与 bot 提交"
        "无法对账"
    )
    sha = _git(
        "log", "-1", "--format=%H", "--fixed-strings",
        f"--grep=record CI run {run_id[3:]}",
    ).strip()
    assert sha, (
        f"git 里找不到 run {run_id} 的 bot 提交"
        "（chore(e2e): record CI run …）——写回账没有第二份账"
    )
    return sha


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


def test_docs_volume_row_matches_disk_corpus() -> None:
    """S4：文档体量行——行数与 MB 都必须等于磁盘交接文档语料。"""
    line = _index_row(ROW_VOLUME)
    lines, octets = _normalized_volume()
    match = re.search(r"([\d,]+)\s*行\s*/\s*([\d.]+)\s*MB", line)
    assert match, (
        f"文档体量行没有「N 行 / X MB」写法：{line.strip()[:100]}"
    )
    claimed_lines = int(match.group(1).replace(",", ""))
    assert claimed_lines == lines, (
        f"文档体量行数漂移：行写 {claimed_lines}，磁盘交接文档 "
        f"{len(_disk_handover_files())} 份共 {lines} 行"
    )
    expected_mb = Decimal(f"{octets / MIB:.1f}")
    claimed_mb = Decimal(match.group(2))
    assert claimed_mb == expected_mb, (
        f"文档体量 MB 漂移：行写 {match.group(2)}，归一化 UTF-8 "
        f"{octets} 字节 = {octets / MIB:.3f} MiB（1 位小数 {expected_mb}）"
    )


def test_baseline_row_matches_the_last_writeback_bot() -> None:
    """S5：代码基线行——sha == 末条写回的 bot 提交，行内 R<n> == 其父轮次。"""
    line = _index_row(ROW_BASELINE)
    entries = _history_entries()
    run_id = str(entries[-1]["run_id"])
    bot_sha = _bot_commit_for(run_id)

    sha_match = re.search(r"`main`\s*=\s*`([0-9a-f]{7,40})`", line)
    assert sha_match, (
        f"代码基线行没有「`main` = `<sha>`」：{line.strip()[:100]}"
    )
    claimed_sha = sha_match.group(1)
    assert bot_sha.startswith(claimed_sha), (
        f"代码基线漂移：行写 {claimed_sha}，history 末条 {run_id} 的 bot "
        f"提交是 {bot_sha[:12]}"
    )

    parent_subject = _git("log", "-1", "--format=%s", f"{bot_sha}^").strip()
    parent_match = re.search(r"\(R(\d+)\)", parent_subject)
    assert parent_match, (
        f"bot 提交 {bot_sha[:12]} 的父提交标题没有轮次锚"
        f"（形如 feat(R149): …）：{parent_subject[:80]}"
    )
    round_match = re.search(r"（R(\d+)[ 　]", line)
    assert round_match, (
        f"代码基线行没有「（R<n> …）」轮次锚：{line.strip()[:100]}"
    )
    assert int(round_match.group(1)) == int(parent_match.group(1)), (
        f"代码基线轮次漂移：行写 R{round_match.group(1)}，bot 提交的父提交"
        f"是 R{parent_match.group(1)}（{parent_subject[:60]}）"
    )
