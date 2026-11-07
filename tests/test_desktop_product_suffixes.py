"""R201：产物后缀词表四源同账（W 系续 W34）。

背景（实测，R196 §3 登记候选面、R200 §3 实测扩成四源）：桌面发行
产物的文件名后缀词表有四份账——

- ``replace-desktop-assets.yml`` 的期望资产词表
  ``('x64-setup.exe', 'x64-full-setup.exe', 'aarch64.dmg',
  'aarch64-full.dmg')``（补资产/校验 SHA-256 的输入，name =
  ``DeterminFlow_{version}_{suffix}``）；
- ``desktop-windows.yml`` 发布步的 bash 四后缀列表（重命名 + sha256sum
  的输入，无下划线）；
- ``desktop-windows.yml`` 安装包步的 NSIS 后缀对 ``_x64-setup.exe`` /
  ``_x64-full-setup.exe``（**带前导下划线**，拼进
  ``DeterminFlow_${version}_${suffix}``）；
- ``build_macos.py`` 的 DMG 对：``suffix = "-full" if flavor == "full"
  else ""`` 拼进 ``DeterminFlow_{version}_aarch64{suffix}.dmg``。

同一条词表的四个来源：NSIS 对（剥前导下划线）∪ DMG 对 == replace
词表 == bash 列表。任何一处加减/改后缀，其余未跟：replace-desktop-assets
的补资产步漏找新产物（资产不齐）或 desktop-windows 的 sha256sum 找不
到旧名（发布步炸）——词表静默分叉。

W34 把这条边钉成两半（W32 同型分工：语料守卫只管锚的存在与结构，
值由同账判）：

- **W34a 语料守卫**：四源的提取锚各恰一处、结构形状各就各位
  （replace 元组恰 4 项引号 token、NSIS 对带前导下划线的 if/else 对、
  bash 发布列表存在、build_macos 三元分支 + DMG 模板）——锚被删/
  复制先红语料守卫。
- **W34b 四源同账**：NSIS 对（剥 ``_``）∪ DMG 对 == replace 词表 ==
  bash 列表，且 NSIS 对与 DMG 对不相交（复制后缀混族当场红）——
  词表值只由这里判，加减/改后缀先红同账。

边界：只判后缀词表字面同账——不判产物名里 version 段的取值（W18
的版本五源已管）、不判 ``.sha256``/``.sig`` 派生后缀（由同一 name
推出，词表同账即覆盖）、不判 workflow/脚本的执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
REPLACE_WF = WORKFLOWS / "replace-desktop-assets.yml"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
BUILD_MACOS = REPO_ROOT / "desktop" / "scripts" / "build_macos.py"

# W34a 结构锚（值无关，形状钉死）。
REPLACE_TUPLE_RX = re.compile(
    r"for suffix in \('([^']+)', '([^']+)', '([^']+)', '([^']+)'\):"
)
NSIS_PAIR_RX = re.compile(r'\{ "(_[^"]+)" \} else \{ "(_[^"]+)" \}')
BASH_LIST_RX = re.compile(r"for suffix in ([^;]+); do")
MACOS_BRANCH_RX = re.compile(
    r'suffix\s*=\s*"([^"]*)"\s*if\s+flavor\s*==\s*"[^"]+"\s*else\s*"([^"]*)"'
)
MACOS_TEMPLATE_RX = re.compile(
    r'f"DeterminFlow_\{version\}_([^{}\s]+)\{suffix\}\.dmg"'
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _anchors() -> dict[str, list[tuple[str, ...]]]:
    """四源锚的原始提取（供两半共用；presence 由调用方各自守卫）。"""
    return {
        "replace": REPLACE_TUPLE_RX.findall(_text(REPLACE_WF)),
        "nsis": NSIS_PAIR_RX.findall(_text(WINDOWS_WF)),
        "bash": BASH_LIST_RX.findall(_text(WINDOWS_WF)),
        "branch": MACOS_BRANCH_RX.findall(_text(BUILD_MACOS)),
        "template": MACOS_TEMPLATE_RX.findall(_text(BUILD_MACOS)),
    }


def _require(anchors: dict[str, list[tuple[str, ...]]], key: str) -> tuple:
    found = anchors[key]
    assert len(found) == 1, (
        f"产物后缀词表的 {key} 锚应恰一处，实测 {len(found)} 处——W34a "
        "语料守卫（锚被删/复制先红这里，值由 W34b 判）"
    )
    return found[0]


def _first(anchors: dict[str, list[tuple[str, ...]]], key: str) -> tuple:
    """W34b 侧取首个匹配：只守「存在」，不守唯一（唯一归 W34a）。"""
    found = anchors[key]
    assert found, (
        f"产物后缀词表的 {key} 锚不存在——W34b 无锚可比"
    )
    return found[0]


def test_suffix_anchor_shapes() -> None:
    """W34a：五处锚各恰一处 + 结构形状就位（词表值只由 W34b 判）。"""
    anchors = _anchors()
    replace_tuple = _require(anchors, "replace")
    assert len(replace_tuple) == 4, (
        f"replace 词表元组应 4 项，实测 {len(replace_tuple)} 项——W34a 结构"
    )
    nsis_pair = _require(anchors, "nsis")
    assert len(nsis_pair) == 2 and all(
        item.startswith("_") for item in nsis_pair
    ), f"NSIS 对应两项且带前导下划线，实测 {nsis_pair}——W34a 结构"
    bash_list = _require(anchors, "bash")
    assert len(bash_list.split()) >= 2, (
        f"bash 发布列表应至少两项，实测 {bash_list!r}——W34a 结构"
    )
    branch = _require(anchors, "branch")
    assert len(branch) == 2, (
        f"build_macos 分支应含 full/else 两个后缀值，实测 {branch}——W34a 结构"
    )
    _require(anchors, "template")


def _replace_set() -> set[str]:
    return set(_first(_anchors(), "replace"))


def _nsis_set() -> set[str]:
    return {item[1:] for item in _first(_anchors(), "nsis")}


def _bash_set() -> set[str]:
    return set(_first(_anchors(), "bash").split())


def _dmg_set() -> set[str]:
    full_suffix, bare_suffix = _first(_anchors(), "branch")
    base = _first(_anchors(), "template")
    return {f"{base}{s}.dmg" for s in (full_suffix, bare_suffix)}


def test_suffix_vocabulary_agrees_across_four_sources() -> None:
    """W34b：NSIS 对 ∪ DMG 对 == replace 词表 == bash 列表（且两族不相交）。"""
    replace_set = _replace_set()
    nsis_set = _nsis_set()
    bash_set = _bash_set()
    dmg_set = _dmg_set()

    composed = nsis_set | dmg_set
    assert not (nsis_set & dmg_set), (
        f"NSIS 对与 DMG 对不应相交，实测交集 {sorted(nsis_set & dmg_set)}"
        "——复制后缀混族当场红"
    )
    assert composed == replace_set, (
        f"产物后缀词表不同账：NSIS 对 ∪ DMG 对 = {sorted(composed)}，"
        f"replace 词表 = {sorted(replace_set)}——改后缀/加产物必须四源同改"
    )
    assert bash_set == replace_set, (
        f"bash 四后缀列表与 replace 词表不同账：{sorted(bash_set)} vs "
        f"{sorted(replace_set)}"
    )
