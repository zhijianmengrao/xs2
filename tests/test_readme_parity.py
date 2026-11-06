"""R153：README 双语结构同账（M 系判据 M1–M4）。

背景（实测，R152 §7 登记、R153 开工复核）：

- ``README.md`` 有 **25 个** Markdown 标题（11 个 H2 + 14 个 H3），
  ``README.en.md`` 有 **24 个**（11 个 H2 + 13 个 H3）——中文多一个
  ``### 社区贡献者``，英文只有 ``### Join the group chat``；
- 两份各 **5 个代码块**（10 行围栏；R152 §7 记的「10 个代码块」是围栏
  行数，M3 按配对后的块计数）；
- 两份的 **6 个显式锚点**（``<a id="…"></a>``）同名同序。

双语 README 是两处独立的写入点：中文加一节、英文忘了加，没有任何命令
会报错，读者只会看到两份「长度不同」的说明。R153 把结构钉成 **M 系
判据**（Markdown mirror）：

- **M1 语料守卫**：两份文件存在且非空，都能解析出 H2/H3、代码块与锚点，
  代码围栏必须配对闭合。任一处解析为空都在此红，防止 M2–M4 空转。
- **M2 标题层级序列**：H2–H6 的层级序列逐项相等（个数与顺序）；标题
  文本不参与——两份文档语言不同。
- **M3 代码块序列**：围栏配对后，代码块个数与开头围栏的语言标签序列
  逐项相等（当前均为 mermaid / bash / powershell / bash / bash）。
- **M4 锚点序列**：``<a id>`` 的 id 序列逐项相等，且每份文件内不重复
  ——锚点是跨语言深链的稳定地址。

R166 补 **M5 徽章序列**（R164 §7 登记）：两份 README 顶部各有 4 枚
``img.shields.io`` 徽章（Release / CI / license / Python），URL 序列
逐项相等；alt 不参与——license 徽章的 alt 按语言写
``许可证：AGPL-3.0`` / ``License: AGPL-3.0``，是正常翻译。

边界：只判**结构**，M5 只判徽章的 URL 序列（alt 有语言差异，豁免），
不判标题措辞、代码内容与徽章指向的上游仓库（fork 徽章有意指 upstream）；
Markdown 标题只覆盖 H2–H6（两份文档的 H1 都是顶部 HTML ``<h1>``，品牌图
不在标题序列里）；M3 不要求每个块都有语言标签，只要求两份的标签序列相同；
锚点必须是 ``<a id="…"></a>`` 的显式写法——GitHub 自动生成的标题锚点
不在射程（标题文本本就不同）。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH_README = REPO_ROOT / "README.md"
EN_README = REPO_ROOT / "README.en.md"
READMES = {"README.md": ZH_README, "README.en.md": EN_README}

HEADING_RX = re.compile(r"^ {0,3}(#{2,6})[ \t]+(\S.*?)[ \t]*$")
FENCE_RX = re.compile(r"^ {0,3}(`{3,})([^`]*)$")
ANCHOR_RX = re.compile(r'<a\s+id="([^"]+)"\s*>\s*</a>')
BADGE_SRC_RX = re.compile(
    r'<img\s+[^>]*src="('
    r"https://img\.shields\.io/[^\"]+"
    r"|https://github\.com/[^\"]+/actions/workflows/[^\"]+/badge\.svg"
    r')"'
)


@dataclass(frozen=True)
class ReadmeStructure:
    """一份 README 的结构面：标题层级、代码块语言、显式锚点。"""

    headings: tuple[tuple[int, str], ...]
    code_languages: tuple[str, ...]
    anchors: tuple[str, ...]

    @property
    def levels(self) -> tuple[int, ...]:
        return tuple(level for level, _ in self.headings)


def _scan(path: Path) -> ReadmeStructure:
    """按行扫描 README；围栏内的 ``#`` 与 ``<a id>`` 不算结构。"""
    assert path.is_file(), f"{path.name} 不存在——双语 README 少一份"
    text = path.read_text(encoding="utf-8-sig")
    assert text.strip(), f"{path.name} 为空——M 系判据没有语料"

    headings: list[tuple[int, str]] = []
    languages: list[str] = []
    anchors: list[str] = []
    fence: str | None = None

    for line in text.splitlines():
        if fence is not None:
            stripped = line.strip()
            # 结束围栏：仅由反引号组成，且不短于开头围栏。
            if len(stripped) >= len(fence) and set(stripped) == {"`"}:
                fence = None
            continue
        opener = FENCE_RX.match(line)
        if opener:
            fence = opener.group(1)
            languages.append(opener.group(2).strip())
            continue
        heading = HEADING_RX.match(line)
        if heading:
            headings.append((len(heading.group(1)), heading.group(2).strip()))
            continue
        anchors.extend(ANCHOR_RX.findall(line))

    assert fence is None, f"{path.name} 的代码围栏未闭合——M3 的块计数不可信"
    return ReadmeStructure(
        headings=tuple(headings),
        code_languages=tuple(languages),
        anchors=tuple(anchors),
    )


def _level_summary(levels: tuple[int, ...]) -> str:
    counts = Counter(levels)
    return " / ".join(
        f"H{level} {counts[level]}" for level in sorted(counts)
    )


def _first_level_difference(
    zh: tuple[int, ...], en: tuple[int, ...]
) -> str:
    for position, (left, right) in enumerate(zip(zh, en), 1):
        if left != right:
            return (
                f"第 {position} 个标题层级不同：中文 H{left} vs 英文 H{right}"
            )
    if len(zh) != len(en):
        longer = "中文" if len(zh) > len(en) else "英文"
        return (
            f"前 {min(len(zh), len(en))} 个相同，{longer}多 "
            f"{abs(len(zh) - len(en))} 个标题"
        )
    return "无差异"


def test_readmes_are_parseable() -> None:
    """M1：两份 README 都能解析出非空的标题、代码块与锚点。"""
    for name, path in READMES.items():
        structure = _scan(path)
        assert structure.headings, f"{name} 没有解析到任何 H2–H6 标题"
        assert structure.levels.count(2) > 0, f"{name} 没有 H2 标题"
        assert structure.levels.count(3) > 0, f"{name} 没有 H3 标题"
        assert structure.code_languages, f"{name} 没有解析到代码块"
        assert structure.anchors, f"{name} 没有解析到 <a id> 锚点"
        assert len(structure.levels) == len(structure.headings), (
            f"{name} 标题解析计数自相矛盾——M 系判据不可信"
        )


def test_heading_level_sequence_matches() -> None:
    """M2：两份 README 的 H2–H6 层级序列逐项相等。"""
    zh = _scan(ZH_README)
    en = _scan(EN_README)
    assert zh.levels == en.levels, (
        "README 标题层级序列不同账：\n"
        f"  中文 {len(zh.levels)} 个（{_level_summary(zh.levels)}）\n"
        f"  英文 {len(en.levels)} 个（{_level_summary(en.levels)}）\n"
        f"  {_first_level_difference(zh.levels, en.levels)}\n"
        "双语 README 是两处写入点：加/删一节必须两份同时改"
    )


def test_code_block_sequence_matches() -> None:
    """M3：两份 README 的代码块个数与语言标签序列逐项相等。"""
    zh = _scan(ZH_README)
    en = _scan(EN_README)
    assert zh.code_languages == en.code_languages, (
        "README 代码块序列不同账：\n"
        f"  中文 {len(zh.code_languages)} 个：{zh.code_languages}\n"
        f"  英文 {len(en.code_languages)} 个：{en.code_languages}\n"
        "块数或开头围栏的语言标签顺序不一致"
    )


def test_anchor_sequence_matches() -> None:
    """M4：两份 README 的显式锚点 id 同名同序，且各自不重复。"""
    zh = _scan(ZH_README)
    en = _scan(EN_README)
    for name, structure in (("README.md", zh), ("README.en.md", en)):
        duplicates = sorted(
            anchor
            for anchor, count in Counter(structure.anchors).items()
            if count > 1
        )
        assert not duplicates, (
            f"{name} 的 <a id> 重复：{duplicates}——HTML id 必须唯一"
        )
    assert zh.anchors == en.anchors, (
        "README 锚点序列不同账：\n"
        f"  中文 {zh.anchors}\n"
        f"  英文 {en.anchors}\n"
        "锚点是跨语言深链的稳定地址，改名/换序必须两份同时改"
    )


# ------------------------------------------------- R166: 徽章 URL 序列（M5）
# 徽章行是 README 顶部 HTML 块里唯一有跨语言对应关系的结构：两处独立
# 写入点，URL 必须同名同序；alt 是给人读的，license 徽章的 alt 按语言
# 写不同前缀是正常翻译，不参与对账。
def _badge_urls(path: Path) -> list[str]:
    """按文档顺序返回 ``img.shields.io`` 徽章的 URL 序列。"""
    text = path.read_text(encoding="utf-8-sig")
    urls = BADGE_SRC_RX.findall(text)
    assert urls, (
        f"{path.name} 没有解析到 img.shields.io 徽章——M5 的语料面空转"
    )
    return urls


def test_badge_url_sequence_matches() -> None:
    """M5：两份 README 的徽章 URL 序列逐项相等（alt 语言差异豁免）。"""
    zh = _badge_urls(ZH_README)
    en = _badge_urls(EN_README)
    for position, (left, right) in enumerate(zip(zh, en), 1):
        assert left == right, (
            "README 徽章 URL 序列不同账：\n"
            f"  第 {position} 枚：中文 {left}\n"
            f"           英文 {right}\n"
            f"  中文 {len(zh)} 枚，英文 {len(en)} 枚"
        )
    assert len(zh) == len(en), (
        "README 徽章数量不同账：\n"
        f"  中文 {len(zh)} 枚：{zh}\n"
        f"  英文 {len(en)} 枚：{en}\n"
        "双语徽章是两处写入点：加/删一枚必须两份同时改"
    )
