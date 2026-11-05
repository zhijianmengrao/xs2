"""R147：索引 §4 行自描述同账（L 系续：日期 == 首次入库、主题 == H1）。

背景（实测，R144 §7 登记、R146 §7 复核）：

- ``HANDOVER_INDEX.md`` §4 的全量索引表每行由人手填三样东西：轮次、日期、
  主题。轮次与链接由 R133 的 N2 把守（集合恰等），日期与主题此前无人管；
- R147 开工实测 **121 行**（R24–R146）的日期与
  ``git log --diff-filter=A --date=short`` **0 漂移**——但这是运气：日期
  只在 git 提交里，抄错一位不会被任何判据咬；
- 主题列与 H1 副标题有 **7 处**标点/措辞差（R117/118/123/125/126/129/132）：
  R118/R123 的 H1 根本没有轮次区间（只写「收口轮」），另外 5 处是
  全角括号/冒号/反引号的写法差。归一后可解析，但没有判据把「归一后
  相等」写成规则。

本文件三条 **L 系续判据**：

- **L5 日期同账**：§4 每行的日期 == 该文档首次入库的提交日期
  （``git log --diff-filter=A --date=short``，取最早一条）。latest 轮
  在提交前不存在于 git：取不到首次入库日期时只豁免 latest（本地跑全量
  的时点）；一旦入库（CI 的检出树），latest 也照判。git 不可用/浅检出
  显式红，不 skip（R136 的纪律）。
- **L6 主题同账**：§4 每行的主题 == 该文档 H1 副标题（NFKC + 去空白/
  标点/反引号/强调符后逐字相等）。归一不是放宽内容：数字和汉字都在，
  只是括号、冒号、间隔号不参与对账。
- **L7 行覆盖**：§4 解析出的行集合 == 磁盘交接文档集合，一行对应一份，
  链接目标与行首轮次一致，日期是合法 ISO 日期。N2 判的是链接集合，
  这里判的是「行能解析且自述完整」——行被删/写坏时 N2 可能仍绿。

边界：只判 §4 表的行，不判主题列的措辞好坏；不读交接文档正文；R24
之前的历史轮次不在表内。
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
INDEX = DOCS / "HANDOVER_INDEX.md"

ROW_RX = re.compile(
    r"^\| R(\d+) \| (\d{4}-\d{2}-\d{2}) \| (.+?) "
    r"\| \[md\]\(HANDOVER_ROUND(\d+)\.md\) \|$"
)
TITLE_RX = re.compile(r"^# DeterminFlow \(xs2\) 交接报告 — Round (\d+)（(.+)）$")
NORMALIZE_STRIP_RX = re.compile(
    r"[\s，。；：、,!?:;（）()《》〈〉【】\[\]“”\"'‘’`*—–\-…·/]"
)


def _index_rows() -> list[re.Match[str]]:
    rows = [
        match
        for line in INDEX.read_text(encoding="utf-8-sig").splitlines()
        if (match := ROW_RX.match(line))
    ]
    assert rows, "索引 §4 没有解析到任何索引行——表形状变了？"
    return rows


def _handover_numbers() -> list[int]:
    nums = []
    for path in DOCS.glob("HANDOVER_ROUND*.md"):
        match = re.search(r"ROUND(\d+)\.md$", path.name)
        if match:
            nums.append(int(match.group(1)))
    assert nums, "docs/ 下没有交接文档——仓库形态不对？"
    return sorted(nums)


def _latest() -> int:
    return max(_handover_numbers())


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return NORMALIZE_STRIP_RX.sub("", text)


def _h1_subtitle(round_no: int) -> str:
    path = DOCS / f"HANDOVER_ROUND{round_no}.md"
    assert path.is_file(), f"索引登记了 R{round_no}，磁盘没有 {path.name}"
    first = next(
        (line for line in path.read_text(encoding="utf-8-sig").splitlines()
         if line.strip()),
        "",
    )
    match = TITLE_RX.match(first)
    assert match, (
        f"{path.name} 的 H1 不含主题副标题：{first[:80]}（N3 先把标题修好）"
    )
    assert int(match.group(1)) == round_no, (
        f"{path.name} 的 H1 轮次 {match.group(1)} 与文件名不一致"
    )
    return match.group(2)


def _git_first_add_date(round_no: int) -> str | None:
    rel = f"docs/HANDOVER_ROUND{round_no}.md"
    proc = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%ad", "--date=short",
         "--", rel],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert proc.returncode == 0, (
        f"git log 失败（退出码 {proc.returncode}）：{proc.stderr.strip()[:200]}"
        "——浅检出必须显式红，不许 skip"
    )
    dates = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return dates[-1] if dates else None


def test_every_index_row_is_well_formed_and_covered() -> None:
    """L7：§4 行集合 == 磁盘交接文档集合，链接与行首轮次一致。"""
    rows = _index_rows()
    disk = set(_handover_numbers())
    seen: set[int] = set()
    for row in rows:
        round_no = int(row.group(1))
        link_round = int(row.group(4))
        assert round_no == link_round, (
            f"§4 行首 R{round_no} 链接到 ROUND{link_round}——行与文档错位"
        )
        assert round_no not in seen, f"§4 把 R{round_no} 登记了两行"
        seen.add(round_no)
        dt.date.fromisoformat(row.group(2))  # 非法日期当场 ValueError
        assert row.group(3).strip(), f"§4 的 R{round_no} 主题为空"
    missing = sorted(disk - seen)
    stale = sorted(seen - disk)
    assert not missing and not stale, (
        f"§4 行覆盖不完整：磁盘有而表里没有 {missing}；"
        f"表里有而磁盘没有 {stale}"
    )


def test_row_dates_match_the_first_add_commit() -> None:
    """L5：§4 日期 == 首次入库日期；latest 在未入库时豁免。"""
    latest = _latest()
    violations: list[str] = []
    for row in _index_rows():
        round_no = int(row.group(1))
        documented = row.group(2)
        actual = _git_first_add_date(round_no)
        if actual is None:
            assert round_no == latest, (
                f"R{round_no} 在 git 里找不到首次入库提交，且它不是 latest"
                f"（latest = R{latest}）——浅检出或索引登记了不存在的文档"
            )
            continue  # 本轮文档尚未提交：CI 检出后照判
        if documented != actual:
            violations.append(
                f"R{round_no}: 索引写 {documented}，首次入库是 {actual}"
            )
    assert not violations, (
        "索引 §4 日期与首次入库日期漂移：\n" + "\n".join(violations)
    )


def test_row_subjects_match_h1_subtitles() -> None:
    """L6：§4 主题 == H1 副标题（标点/反引号归一后逐字相等）。"""
    violations: list[str] = []
    for row in _index_rows():
        round_no = int(row.group(1))
        documented = row.group(3)
        subtitle = _h1_subtitle(round_no)
        left, right = _normalize(documented), _normalize(subtitle)
        assert len(left) >= 2 and len(right) >= 2, (
            f"R{round_no} 的主题归一后过短（{left!r} / {right!r}）——"
            "归一规则吃掉了内容"
        )
        if left != right:
            violations.append(
                f"R{round_no}: 索引「{documented}」vs H1「{subtitle}」"
            )
    assert not violations, (
        "索引 §4 主题与 H1 副标题不同账（归一后仍不等）：\n"
        + "\n".join(violations)
    )
