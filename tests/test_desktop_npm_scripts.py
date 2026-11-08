"""R215：desktop workflow npm script 调用面（W 系续 W45）。

背景（实测，R212 §3 登记）：desktop workflows 的 ``npm run <X>`` 共
**4 处**——desktop-macos.yml 2（``npm ci && npm run build`` L48、
``npm run build:macos -- --flavor ${{ matrix.flavor }}`` L58）、
desktop-windows.yml 2（``npm run build`` L83、L99）；desktop/package.json
的 ``scripts`` = {build, build:macos, tauri, test}。调用面漂移无人判：
workflow 的 ``npm run <X>`` 写错 script 名（npm 报 ``Missing script``
退非零，run 时才炸）、或 package.json 改名 script 而 workflow 没跟。
V6/V7 管的是 README 与文档 npm 命令面，workflow 侧第一次进射程。

W45 把这条边钉成两半（W32/W34/W38–W44 同型分工）：

- **W45a 语料守卫**：``npm run <X>`` 调用逐份恰等（macos 2 /
  windows 2，合计 4）——加/删调用先红语料守卫。
- **W45b 调用面同账**：每个 ``npm run <X>`` 的 ``<X>`` ∈
  package.json ``scripts`` 键集合（解析 JSON，键集合漂移显式红）。

边界：只判 script 名可解析——不判 script 内容（package.json 的
build/tauri 命令行是各 script 自己的账）、不判 ``npm ci``（不是
npm run 面）、不判 `npm exec tauri` 直调（tauri CLI 面）、不判
执行行为（CI 负责）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PACKAGE_JSON = REPO_ROOT / "desktop" / "package.json"
EXPECTED_COUNTS: dict[str, int] = {
    "desktop-macos.yml": 2,
    "desktop-windows.yml": 2,
}
NPM_RUN_RX = re.compile(r"npm run (\S+)")


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _package_scripts() -> set[str]:
    document = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    scripts = document.get("scripts")
    assert isinstance(scripts, dict) and scripts, (
        "desktop/package.json 没有 scripts——W45 无锚"
    )
    return set(scripts)


def test_npm_run_call_counts() -> None:
    """W45a：npm run 调用逐份恰等（macos 2 / windows 2，合计 4）。"""
    for name, expected in EXPECTED_COUNTS.items():
        calls = NPM_RUN_RX.findall(_text(name))
        assert len(calls) == expected, (
            f"{name} 的 npm run 调用应恰 {expected} 处，实测 {len(calls)} 处"
            "——W45a 语料守卫"
        )


def test_npm_run_scripts_resolve() -> None:
    """W45b：每个 npm run <X> 的 <X> ∈ package.json scripts 键集合。"""
    scripts = _package_scripts()
    assert {"build", "build:macos"} <= scripts, (
        f"desktop/package.json 缺基础 scripts（{sorted(scripts)}）——W45b 无锚"
    )
    unknown: list[str] = []
    for name in EXPECTED_COUNTS:
        for script in NPM_RUN_RX.findall(_text(name)):
            if script not in scripts:
                unknown.append(f"{name}: {script}")
    assert not unknown, (
        "desktop workflow 调用了 package.json 未定义的 npm script："
        + "；".join(unknown) + "——script 改名时 workflow 要同改，"
        "否则 npm 报 Missing script 在 run 时才炸"
    )
