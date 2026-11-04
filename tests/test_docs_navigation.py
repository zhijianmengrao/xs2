"""R133：交接文档导航层引用完整性（防复发钉测）。

背景（``docs/HANDOVER_INDEX.md`` §6.3 / §6.4）：R28 归档删除 R10–R23 后，
活文档里残留的具体失效引用（PROJECT_INFO 的 ``HANDOVER_ROUND23.md``、
helper-contract 的 R20/R21）在 107 份交接文档之间无人把守；R112 起的
交接文档标题漏写主题副标题也无从发现。本文件把三条导航层不变量钉住：

- **N1 引用可解析或带归档标记**：活文档（PROJECT_INFO / HANDOVER_INDEX /
  humanware-helper-contract）中对已归档 HANDOVER 文档的具体引用
  （``HANDOVER_ROUND<n>.md``、``docs/HANDOVER.md``）必须能在 ``docs/`` 下
  解析到，或所在行带归档取回标记（「归档」「已删」「``git show <sha>``」）。
- **N2 索引覆盖完整**：``HANDOVER_INDEX.md`` 里 ``[md](HANDOVER_ROUNDn.md)``
  链接集合必须与磁盘上的交接文档集合相等——新交接文档漏登记索引会被判红
  （R133 之前这靠人记，§6.4.3 正是漏登记的积累）。
- **N3 标题含副标题**：每份交接文档首个非空行必须是
  ``# DeterminFlow (xs2) 交接报告 — Round <n>（<主题副标题>）``，且 ``<n>``
  与文件名一致（§6.4.4：R112 起 19 份漏副标题，读引言才知道本轮做什么）。

边界（与 R130「展示层不判定」同族的纪律）：只扫三份**活文档**；历史交接
文档（R24/R28 等）里对删除事件本身的记载是有意史料，不在扫描范围。
``HANDOVER_INDEX.md`` §6.3 是失效引用的**登记表**（引用失效引用是它的职责），
扫描跳过该小节；若该小节标题被改名，本文件的定位会失效并判红，届时需同步
更新定位。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"

LIVING_DOCS = (
    "PROJECT_INFO.md",
    "HANDOVER_INDEX.md",
    "humanware-helper-contract.md",
)

# 具体文件名引用：HANDOVER_ROUND<n>.md（n 为纯数字，天然排除 R15..22 之类的
# 区间写法与 HANDOVER_ROUNDn.md 占位符）与 docs/HANDOVER.md 本身。
REF_RX = re.compile(r"(?:docs/)?HANDOVER\.md|(?:docs/)?HANDOVER_ROUND(\d+)\.md")
# 归档取回标记：出现即认为该引用是「有意指向已归档史料」。
ARCHIVE_MARKER_RX = re.compile(r"归档|已删|git show\s+[0-9a-fA-F]{7,40}")
INDEX_SECTION_63 = "### 6.3"
INDEX_LINK_RX = re.compile(r"\]\(HANDOVER_ROUND(\d+)\.md\)")
FILENAME_RX = re.compile(r"^HANDOVER_ROUND(\d+)\.md$")
TITLE_RX = re.compile(
    r"^# DeterminFlow \(xs2\) 交接报告 — Round (\d+)（(.+)）$"
)


def _handover_files() -> list[Path]:
    files = sorted(DOCS.glob("HANDOVER_ROUND*.md"))
    assert files, "docs/ 下没有任何交接文档——仓库形态不对？"
    return files


def _index_lines_skipping_63() -> list[tuple[int, str]]:
    """返回 HANDOVER_INDEX 的 (行号, 行文本)，跳过 §6.3（失效引用登记表）。"""
    lines = (DOCS / "HANDOVER_INDEX.md").read_text(encoding="utf-8-sig").splitlines()
    out: list[tuple[int, str]] = []
    skipping = False
    saw_63 = False
    for lineno, line in enumerate(lines, 1):
        if INDEX_SECTION_63 in line:
            skipping = True
            saw_63 = True
            continue
        if skipping and line.startswith(("### ", "## ")):
            skipping = False
        if not skipping:
            out.append((lineno, line))
    assert saw_63, (
        "HANDOVER_INDEX.md 里找不到 '### 6.3'——§6.3（失效引用登记表）的定位"
        "失效。若该小节被改名/移动，请同步更新本测试的小节定位。"
    )
    return out


def test_archived_handover_refs_resolve_or_carry_marker() -> None:
    """N1：活文档对已归档 HANDOVER 文档的引用必须可解析或带归档取回标记。"""
    resolvable = {p.name for p in _handover_files()} | {"HANDOVER.md"}
    violations: list[str] = []
    for name in LIVING_DOCS:
        path = DOCS / name
        assert path.exists(), f"活文档不在：{path}"
        text = path.read_text(encoding="utf-8-sig")
        lines = (
            _index_lines_skipping_63()
            if name == "HANDOVER_INDEX.md"
            else list(enumerate(text.splitlines(), 1))
        )
        for lineno, line in lines:
            for match in REF_RX.finditer(line):
                ref = match.group(0).split("/")[-1]
                if ref in resolvable:
                    continue
                if ARCHIVE_MARKER_RX.search(line):
                    continue
                violations.append(
                    f"{name}:{lineno}: 引用 {ref} 指向已归档文档且该行无归档"
                    f"取回标记（归档/已删/git show <sha>）：{line.strip()[:100]}"
                )
    assert not violations, (
        "活文档存在失效引用（R28 归档删除 R10–R23 的复发）：\n"
        + "\n".join(violations)
    )


def test_index_covers_every_handover_doc() -> None:
    """N2：索引 §4 链接集合必须与磁盘交接文档集合相等（漏登记判红）。"""
    disk = {int(FILENAME_RX.match(p.name).group(1)) for p in _handover_files()}
    index_text = (DOCS / "HANDOVER_INDEX.md").read_text(encoding="utf-8-sig")
    linked = {int(m.group(1)) for m in INDEX_LINK_RX.finditer(index_text)}
    missing = sorted(disk - linked)
    dangling = sorted(linked - disk)
    assert not missing and not dangling, (
        f"索引覆盖不完整：磁盘有而索引没登记 {missing}；"
        f"索引登记了但磁盘没有 {dangling}"
    )
    # 逐条核对链接目标确实存在（与集合等价性互为冗余，防正则误配）。
    for p in _handover_files():
        assert INDEX_LINK_RX.search(
            f"]({p.name})"
        ), f"索引缺 {p.name} 的 [md] 链接行"


@pytest.mark.parametrize(
    "path", _handover_files(), ids=lambda p: p.name
)
def test_handover_title_has_subtitle(path: Path) -> None:
    """N3：H1 必须是「— Round <n>（<主题副标题>）」且 <n> 与文件名一致。"""
    first = next(
        (l for l in path.read_text(encoding="utf-8-sig").splitlines() if l.strip()),
        "",
    )
    match = TITLE_RX.match(first)
    assert match, (
        f"{path.name} 的 H1 不含主题副标题（期望 "
        f"'# DeterminFlow (xs2) 交接报告 — Round <n>（<副标题>）'）：{first[:80]}"
    )
    expect_num = int(FILENAME_RX.match(path.name).group(1))
    assert int(match.group(1)) == expect_num, (
        f"{path.name} 标题轮次 {match.group(1)} 与文件名 {expect_num} 不一致"
    )
    assert match.group(2).strip(), f"{path.name} 的副标题为空白"
