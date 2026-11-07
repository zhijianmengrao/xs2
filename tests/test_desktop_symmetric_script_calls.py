"""R209：跨平台脚本调用面同账（W 系续 W40）。

背景（实测，R208 §3 登记）：desktop workflow 里有两份脚本被
windows/macos **对称调用**——``build_backend.py`` 2 处（windows L87 /
macos L51，均 ``--flavor ${{ matrix.flavor }}``）、
``refresh_official_plugin_lock.py`` 2 处（windows L66 / macos L45，
均 ``--check``）。跨平台一边改 flag（或丢 flag、或换值）而另一边
没跟：macos 构建出的 backend 与 windows 语义分叉、或一边校验插件锁
一边不校验——CI 各自全绿，产物已经不同。

W40 把这条边钉成两半（W32/W34/W38/W39 同型分工）：

- **W40a 语料守卫**：两脚本各恰 2 处调用、且 windows/macos 各恰 1 处
  ——加/删调用先红语料守卫。
- **W40b 跨平台同账**：每脚本的各处调用实参（脚本路径后的整个参数
  尾，空白归一）逐字恰等——一边改 flag/值，另一边没跟当场红。

边界：只判 flag 与实参的字面同账——不判 ``--flavor`` 的取值空间
（W29 的词表已钉）、不判脚本执行行为（CI 负责）、不判其他脚本的
非对称调用面（smoke_backend 4 处归 W41、smoke_installer.ps1 归 W42、
verify_bundle/create_update_manifest 已由 W38/W39 钉）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
MACOS_WF = WORKFLOWS / "desktop-macos.yml"
# 对称调用面：脚本名 →（windows 调用数, macos 调用数）。
SYMMETRIC_SCRIPTS: dict[str, tuple[int, int]] = {
    "build_backend.py": (1, 1),
    "refresh_official_plugin_lock.py": (1, 1),
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _call_tails(script: str, workflow: Path) -> list[str]:
    """该脚本在给定 workflow 里每处调用的参数尾（脚本路径后的全部实参）。"""
    rx = re.compile(
        re.escape(f"desktop/scripts/{script}") + r"((?:[^\\\n]|\\\r?\n)*)"
    )
    tails = []
    for tail in rx.findall(_text(workflow)):
        tails.append(" ".join(tail.split()))
    return tails


def test_symmetric_call_site_counts() -> None:
    """W40a：两脚本各恰 2 处调用，windows/macos 各恰 1 处。"""
    for script, (win_n, mac_n) in SYMMETRIC_SCRIPTS.items():
        win_tails = _call_tails(script, WINDOWS_WF)
        mac_tails = _call_tails(script, MACOS_WF)
        assert len(win_tails) == win_n, (
            f"desktop-windows.yml 的 {script} 调用应恰 {win_n} 处，实测 "
            f"{len(win_tails)} 处——W40a 语料守卫"
        )
        assert len(mac_tails) == mac_n, (
            f"desktop-macos.yml 的 {script} 调用应恰 {mac_n} 处，实测 "
            f"{len(mac_tails)} 处——W40a 语料守卫"
        )


def test_symmetric_call_args_agree() -> None:
    """W40b：每脚本各处调用的参数尾逐字恰等（跨平台一边改一边红）。"""
    for script in SYMMETRIC_SCRIPTS:
        tails = _call_tails(script, WINDOWS_WF) + _call_tails(
            script, MACOS_WF
        )
        assert tails, f"{script} 没有任何调用——W40b 无锚"
        assert len(set(tails)) == 1, (
            f"{script} 的跨平台调用实参不同账：{tails}——一边改 flag/值"
            "必须两边同改，否则两个平台构建/校验语义分叉"
        )
