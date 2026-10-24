"""R18 O1 等价性守卫：`skill_marketplace.bundle` 改用 win_names 单一规则源后，
对每个输入段的接受/拒绝判定必须与替换前的内联规则**逐项一致**。

替换前（xs2 HEAD 之前版本）的写法：

    _RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\.|$)", re.I)
    ... not _COMPONENT.fullmatch(part) or part.endswith(".") or _RESERVED.match(part)

替换后：

    ... not _COMPONENT.fullmatch(part) or has_unsafe_trailing_char(part) or is_reserved_device_name(part)

差异面（本测试逐一覆盖，防止将来 win_names 扩展集合时把 marketplace 打挂）：
- 新集合多了 `CONIN$`/`CONOUT$`/`CLOCK$`——但它们含 `$`，早被 `_COMPONENT` 拒；
- 新集合 `COM0` 不拦、`COM10` 拦（旧正则同样如此）；
- 尾随空格 `part.endswith(".")` 不拒、`has_unsafe_trailing_char` 拒——但空格不在
  `_COMPONENT` 字符集内，先一步被拒；
- POSIX 差异：两端都用平台无关谓词，与旧实现一样跨平台一致拒绝。
"""

from __future__ import annotations

import re

import pytest

from src.skill_marketplace.bundle import _COMPONENT, validate_paths
from src.skill_marketplace.errors import LocalSkillError
from src.core.win_names import has_unsafe_trailing_char, is_reserved_device_name

# R17 B3/B4 用例集 + 边界组合，覆盖设备名、大小写、带扩展名、尾随点/空格、
# 设备名前缀但非完整段、非保留编号、`$` 结尾与非法字符。
COMPONENTS = [
    # 应拒（设备名/尾随点）
    "NUL", "nul", "NUL.", "NUL.txt", "nul.md", "CON", "Con.", "PRN", "AUX.",
    "COM1", "COM1.log", "com9.x", "LPT9.", "LPT1", "aux.txt.bak",
    "CONIN$", "CONOUT$", "CLOCK$",
    "alpha.", "alpha..", "trail.", "trail ", "trail. ",
    # 应放
    "core", "console-NUL", "NULLU", "nul-x", "NULX", "COM0", "LPT0", "COM10",
    "CLOCKWORK", "alpha.beta", "a.b.c.md", "notes", "chapter-01", "SKILL",
    "_x", "x1",
    # 结构性非法字符（_COMPONENT 先拒）
    # 注：不含 "bad/slash"——validate_paths 先按 "/" 拆段，含分隔符的“段”无法作为
    # 单段进入整包对照；分隔符面由 test_separator_components_are_split_and_rejected 覆盖。
    "bad\\back", "bad space", "中文", "", "..", ".", "-lead", "@at",
]

# 替换前的旧实现（逐字复制），只用于对照判定，不参与生产逻辑。
_OLD_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def _old_reject(part: str) -> bool:
    return bool(
        not _COMPONENT.fullmatch(part)
        or part.endswith(".")
        or _OLD_RESERVED.match(part)
    )


def _new_reject(part: str) -> bool:
    return bool(
        not _COMPONENT.fullmatch(part)
        or has_unsafe_trailing_char(part)
        or is_reserved_device_name(part)
    )


@pytest.mark.parametrize("part", COMPONENTS)
def test_rule_source_matches_previous_inline_rule(part):
    assert _new_reject(part) == _old_reject(part), part


@pytest.mark.parametrize("part", COMPONENTS)
def test_validate_paths_acceptance_is_unchanged(part):
    """整包层面的接受/拒绝也与替换前一致（用 `<段>/note.md` 定位到路径规则）。"""
    files = {"SKILL.md": b"x", f"{part}/note.md": b"y"}
    if _old_reject(part):
        with pytest.raises(LocalSkillError):
            validate_paths(files)
    else:
        validate_paths(files)  # 不抛异常即通过


@pytest.mark.parametrize("path", ["a/b/NUL.md", "NUL/a.md", "a/../b.md", "./a.md", "a//b.md"])
def test_separator_components_are_split_and_rejected(path):
    """分隔符面：validate_paths 先拆段再逐段判定，设备名/空段/`..` 一律拒。

    与替换前一致（旧实现同样先 split 再 `_RESERVED.match(part)`）。
    """
    with pytest.raises(LocalSkillError):
        validate_paths({"SKILL.md": b"x", path: b"y"})
