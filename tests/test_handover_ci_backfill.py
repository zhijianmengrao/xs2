"""R144：交接文档 §6 的 CI 回填时限与 run id 同账。

背景（实测，R144 开工）：

- R139 §9 把「§6 由下一轮回填」明确列为**候选制的人的纪律**——S 系判据
  只钉索引 §1 的三行快照，不覆盖交接文档 §6 的回填及时性。
- 实测 R144 开工时：R137 §6 仍是模板（``<code-sha>`` / ``<run1>`` /
  「预计」），落后 **6 轮**；R143 §6 按单跑制待本轮回填；工作树里还躺着
  一份 R139 §6 的回填未提交。三处共同证明：没有判据的时限只是愿望。
- 单跑轮次制从 R135 起（docs 回填并入下一轮提交），所以扫描下限 = 135；
  R134 及以前的双跑制文档永久不扫（它们的「预计」是当时形态，见索引 §6.2）。

本文件两条 D 系判据：

- **D1 时限**：R135 .. latest-1 的每份交接文档，§6 必须已回填——含至少
  一个 GitHub run id，且不得出现 ``<run`` / ``<code-sha>`` / 「预计」占位。
  latest（当前轮）允许模板：它的 run 在推送后才存在，由下一轮回填。
- **D2 同账**：§6 里出现的每个 run id 必须能在 ``history.json`` 找到；同一
  条目内 ``A→B`` 的写回声明，若其前面有 run id，则 B 必须等于该 run id 在
  history 中的序号（A == B-1）。不带 run id 的 ``A→B`` 不判——那是下一轮
  docs 跑的预告，是未来账。

边界：不判「10 job 全绿」等叙述真假（CI 平台的结论不在仓库内），只判
run id 在账与序号自洽；不扫描 §6 之外的 CI 叙述。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
HISTORY = REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history" / "history.json"

# 单跑轮次制起点：R135 起 docs 回填并入下一轮提交。
BACKFILL_FLOOR = 135

SECTION_6_RX = re.compile(r"^## 6\.\s*CI\s*$", re.M)
NEXT_HEADING_RX = re.compile(r"^## ", re.M)
PLACEHOLDER_RX = re.compile(r"<run\d*>|<code-sha>|预计")
RUN_ID_RX = re.compile(r"(?<!\d)(\d{11})(?!\d)")
# 写回区间 ``A→B``；时间区间 ``18:04:03→18:25:43`` 不能误吃（冒号邻接排除）。
WRITEBACK_RX = re.compile(r"(?<![:\d])(\d+)\s*→\s*(\d+)(?![\d:])")


def _handover_numbers() -> list[int]:
    nums = []
    for path in DOCS.glob("HANDOVER_ROUND*.md"):
        match = re.search(r"ROUND(\d+)\.md$", path.name)
        if match:
            nums.append(int(match.group(1)))
    assert nums, "docs/ 下没有交接文档——仓库形态不对？"
    return sorted(nums)


def _section_6(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    match = SECTION_6_RX.search(text)
    assert match, f"{path.name} 缺少 §6「## 6. CI」——回填无处落账，D 判据失守"
    rest = text[match.end():]
    nxt = NEXT_HEADING_RX.search(rest)
    return rest[: nxt.start()] if nxt else rest


def _history_entries() -> list[dict]:
    document = json.loads(HISTORY.read_text(encoding="utf-8"))
    entries = document["history"] if isinstance(document, dict) else document
    assert isinstance(entries, list) and entries, "history.json 没有条目"
    return entries


def _bullets(section: str) -> list[str]:
    """按 ``- `` 切条目并把折行拼回一条（§6 的写法是 bullet 叙事）。"""
    bullets: list[str] = []
    current: list[str] = []
    for line in section.splitlines():
        if line.startswith("- "):
            if current:
                bullets.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        bullets.append("\n".join(current))
    return bullets


def _filled_rounds() -> list[int]:
    latest = max(_handover_numbers())
    return [n for n in _handover_numbers() if BACKFILL_FLOOR <= n < latest]


@pytest.mark.parametrize(
    "round_no", _filled_rounds(), ids=lambda n: f"R{n}"
)
def test_backfilled_handover_cites_ledger_runs(round_no: int) -> None:
    """D1+D2：R135..latest-1 的 §6 必须回填，且 run id 与写回序号同账。"""
    path = DOCS / f"HANDOVER_ROUND{round_no}.md"
    section = _section_6(path)

    # D1：旧轮次的 §6 不允许还是模板。
    assert not PLACEHOLDER_RX.search(section), (
        f"{path.name} §6 仍是模板（占位符/「预计」）——上一轮的 run 早已"
        f"发生，必须在下一轮提交里回填：{section.strip()[:160]}"
    )
    cited = RUN_ID_RX.findall(section)
    assert cited, f"{path.name} §6 没有 run id——回填至少要点名一次 CI run"

    # D2：每个 run id 都必须在 history.json 里，写回序号要对得上。
    entries = _history_entries()
    ledger_ids = {str(entry["run_id"]) for entry in entries}
    for run_id in cited:
        assert f"ci-{run_id}" in ledger_ids, (
            f"{path.name} §6 引用的 run {run_id} 不在 history.json——"
            "文档账与写回账分叉"
        )
    for bullet in _bullets(section):
        for match in WRITEBACK_RX.finditer(bullet):
            low, high = int(match.group(1)), int(match.group(2))
            preceding = [
                m for m in RUN_ID_RX.finditer(bullet) if m.start() < match.start()
            ]
            if not preceding:
                continue  # 下一轮 docs 跑的预告（未来账），不判
            run_id = preceding[-1].group(1)
            assert 1 <= high <= len(entries), (
                f"{path.name} §6 写回序号 {high} 超出 history 条目数 "
                f"{len(entries)}"
            )
            assert low == high - 1, (
                f"{path.name} §6 写回区间 {low}→{high} 不连续"
            )
            actual = str(entries[high - 1]["run_id"])
            assert actual == f"ci-{run_id}", (
                f"{path.name} §6 把 run {run_id} 记为第 {high} 条写回，"
                f"但 history 第 {high} 条是 {actual}——序号或 run id 漂移"
            )


def test_only_the_latest_handover_may_be_pending() -> None:
    """D1 的边界：R135 起只允许最新一轮的 §6 仍是模板。"""
    latest = max(_handover_numbers())
    pending = [
        n
        for n in _handover_numbers()
        if n >= BACKFILL_FLOOR and PLACEHOLDER_RX.search(
            _section_6(DOCS / f"HANDOVER_ROUND{n}.md")
        )
    ]
    assert set(pending) <= {latest}, (
        f"仍有旧轮次的 §6 是模板：{sorted(set(pending) - {latest})}——"
        "单跑轮次制下，下一轮提交必须回填上一轮"
    )
