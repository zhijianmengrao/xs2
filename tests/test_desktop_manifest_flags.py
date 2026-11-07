"""R207：create_update_manifest 调用面参数同账（W 系续 W39）。

背景（实测，R204 §3 登记）：``desktop/scripts/create_update_manifest.py``
被 desktop workflow 调用 **恰 1 处**（desktop-windows.yml 的
create_update_manifest 步），脚本 argparse 定义 7 个 option
（--version / --installer / --signature / --base-url / --notes-file /
--pub-date / --output），call site 把 7 个**全用**。调用面漂移无人判：
workflow 写错 flag 字、或脚本增删 option 而 call site 没跟——清单缺
一段账（如 --pub-date 丢了，latest.json 的发布时间就缺）或 run 时
unrecognized arguments。

W39 把这条边钉成两半（W32/W34/W38 同型分工）：

- **W39a 语料守卫**：create_update_manifest 的 call site 在
  desktop workflow 里恰一处；脚本 argparse 定义非空（锚存在）。
- **W39b 调用面恰等**：call site 的 flag 多重集 == argparse option
  集合（sorted 逐字恰等）——漏 flag、错字、重复、脚本侧增删都翻红。

边界：只判 flag 名的字面同账——不判 flag 取值（--base-url 的形状由
W35 钉、--notes-file 引用由 W36 覆盖、--output 文件名由 W35 钉）、
不判脚本执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "create_update_manifest.py"
CALL_RX = re.compile(
    r"desktop/scripts/create_update_manifest\.py((?:[^\\\n]|\\\r?\n)*)"
)
# flag 只认续行行首：块内 $(git show -s --format=…) 的 git flag 不误收。
FLAG_RX = re.compile(r"(?:\\\r?\n)\s*(--[a-z][a-z0-9-]*)")
ARGPARSE_RX = re.compile(r'add_argument\(\s*"(--[^"]+)"')


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _call_blocks() -> list[str]:
    return CALL_RX.findall(_text(WINDOWS_WF))


def _argparse_options() -> list[str]:
    return ARGPARSE_RX.findall(_text(SCRIPT))


def test_manifest_call_site_exists() -> None:
    """W39a：create_update_manifest 的 call site 在 desktop workflow 恰一处。"""
    blocks = _call_blocks()
    assert len(blocks) == 1, (
        f"desktop-windows.yml 的 create_update_manifest call site 应恰 "
        f"1 处，实测 {len(blocks)} 处——W39a 语料守卫"
    )
    assert _argparse_options(), "脚本 argparse 定义为空——W39a 无锚"


def test_manifest_flags_agree_with_argparse() -> None:
    """W39b：call site 的 flag 多重集 == argparse option 集合（恰等）。"""
    options = sorted(_argparse_options())
    assert len(options) == 7, (
        f"create_update_manifest 的 argparse option 应 7 个，实测 "
        f"{len(options)} 个——W39b 无锚（option 集合漂移先红这里）"
    )
    for block in _call_blocks():
        flags = sorted(FLAG_RX.findall(block))
        assert flags == options, (
            f"create_update_manifest call site 的 flag 与 argparse option "
            f"不同账：call site {flags} vs 定义 {options}——漏 flag 清单缺"
            "一段账，写错字/脚本增删 run 时 unrecognized arguments"
        )
