"""R210：smoke_backend 调用面同账（W 系续 W41）。

背景（实测，R208 §3 登记）：``smoke_backend.py``（backend 冒烟）被
desktop workflow 调用 **4 处**——desktop-macos.yml 3（构建后 L52、
DMG 前核验 L66、挂载副本核验 L77）、desktop-windows.yml 1（L88），
均带 ``--timeout 180``。超时预算漂移无人判：一处改超时而其余没跟，
四个冒烟点的等待预算分叉——CI 各自能绿，但「冒烟到底等多久」在
平台间/阶段间语义不一致，慢机器上只有部分点会偶发超时。

W41 把这条边钉成两半（W32/W34/W38/W39/W40 同型分工）：

- **W41a 语料守卫**：调用逐份计数恰等（macos 3 / windows 1，合计 4）
  ——加/删调用先红语料守卫。
- **W41b 超时预算同账**：每处调用恰有一个 ``--timeout <N>`` 且全部
  逐字同值（== 180）——超时预算改动四处同改。

边界：只判调用计数与 ``--timeout`` 值的字面同账——不判各处定位参数
（app-bundle/挂载副本路径是各点的本意差异，不同账是设计）、不判
smoke 的执行行为（CI 负责）、不判 ``--timeout`` 的取值合理性（180 是
政策值，改动先红同账再改）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
EXPECTED_COUNTS: dict[str, int] = {
    "desktop-macos.yml": 3,
    "desktop-windows.yml": 1,
}
CALL_RX_TEMPLATE = (
    r"desktop/scripts/smoke_backend\.py((?:[^\\\n]|\\\r?\n)*)"
)
TIMEOUT_RX = re.compile(r"--timeout\s+(\d+)")


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _call_blocks(name: str) -> list[str]:
    return re.findall(CALL_RX_TEMPLATE, _text(name))


def test_smoke_backend_call_counts() -> None:
    """W41a：调用逐份恰等（macos 3 / windows 1，合计 4）。"""
    for name, expected in EXPECTED_COUNTS.items():
        blocks = _call_blocks(name)
        assert len(blocks) == expected, (
            f"{name} 的 smoke_backend 调用应恰 {expected} 处，实测 "
            f"{len(blocks)} 处——W41a 语料守卫"
        )


def test_smoke_backend_timeout_agrees() -> None:
    """W41b：每处调用恰有一个 --timeout 且全部逐字同值（== 180）。"""
    timeouts: list[tuple[str, str]] = []
    for name in EXPECTED_COUNTS:
        for block in _call_blocks(name):
            found = TIMEOUT_RX.findall(block)
            assert len(found) == 1, (
                f"{name} 的 smoke_backend 调用应恰一个 --timeout，实测 "
                f"{len(found)} 个（{found}）——W41b 超时预算同账"
            )
            timeouts.append((name, found[0]))
    values = {value for _name, value in timeouts}
    assert values == {"180"}, (
        f"smoke_backend 超时预算不同账：{timeouts}——改超时四处同改，"
        "否则平台/阶段间冒烟等待预算分叉"
    )
