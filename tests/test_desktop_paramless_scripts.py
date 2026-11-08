"""R218：macOS 无参前置脚本调用面（W 系续 W47）。

背景（实测，R216 §3 登记）：desktop-macos.yml 里有两个**无参**前置
脚本调用——``install_macos_build_dependencies.py``（L40，装构建
依赖）与 ``generate_macos_icon.py``（L55，生成图标）。9 脚本调用面
（W32 的 17 处路径账）至此全部有账：带参脚本由 W38/W39/W40/W41/W42
钉 flag，这两个无参脚本由本判据钉「恰一处 + 真的无参」。调用面漂移
无人判：有人给前置脚本加了 flag（脚本并不认识，argparse 退错）或
删了调用（依赖没装/图标没生成，后续步骤炸得更隐蔽）。

W47 把这条边钉成两半（W32/W34/W38–W46 同型分工）：

- **W47a 语料守卫**：两脚本在 desktop-macos.yml 各恰 1 处调用。
- **W47b 无参同账**：两处调用的参数尾（脚本路径后的全部实参，空白
  归一）为空——任何一方加了参数显式红。

边界：只判调用计数与无参形状——不判脚本内部行为（CI 负责）、不判
脚本间执行顺序（step 顺序是 workflow 结构账）、不判 windows 侧
（两脚本都是 macOS 专属，desktop-windows.yml 实测 0 处）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MACOS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
PARAMLESS_SCRIPTS = (
    "install_macos_build_dependencies.py",
    "generate_macos_icon.py",
)


def _text() -> str:
    return MACOS_WF.read_text(encoding="utf-8")


def _call_tails(script: str) -> list[str]:
    """该脚本在 desktop-macos.yml 里每处调用的参数尾（空白归一）。"""
    rx = re.compile(
        re.escape(f"desktop/scripts/{script}") + r"((?:[^\\\n]|\\\r?\n)*)"
    )
    return [" ".join(tail.split()) for tail in rx.findall(_text())]


def test_paramless_call_counts() -> None:
    """W47a：两脚本各恰 1 处调用。"""
    for script in PARAMLESS_SCRIPTS:
        tails = _call_tails(script)
        assert len(tails) == 1, (
            f"desktop-macos.yml 的 {script} 调用应恰 1 处，实测 "
            f"{len(tails)} 处——W47a 语料守卫"
        )


def test_paramless_calls_are_parameterless() -> None:
    """W47b：存在的调用的参数尾为空（真无参；调用缺失归 W47a）。"""
    for script in PARAMLESS_SCRIPTS:
        tails = _call_tails(script)
        assert not tails or tails[0] == "", (
            f"{script} 实测无参（脚本不接受 flag），调用却带了实参："
            f"{tails[0]!r}——加参数要么脚本先支持要么删掉，否则 argparse "
            "run 时才炸"
        )
