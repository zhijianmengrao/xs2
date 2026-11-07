"""R214：macOS 产物路径前缀同账（W 系续 W44）。

背景（实测，R212 §3 登记）：macOS 产物路径有两份账——
``build_macos.py`` 用 pathlib 拼出产物位置（``bundle = desktop /
"src-tauri" / "target" / "release" / "bundle"``，``app = bundle /
"macos" / "DeterminFlow.app"``，``dmg = bundle / "dmg" / f
"DeterminFlow_{version}_aarch64{suffix}.dmg"``），
``desktop-macos.yml`` 的 verify 调用按字面路径消费（``--app-bundle
desktop/src-tauri/target/release/bundle/macos/DeterminFlow.app``、
``--dmg desktop/src-tauri/target/release/bundle/dmg/*.dmg``）。路径
漂移无人判：产物挪目录（如 tauri 升级改 bundle 布局）只改一边——
build 出来的 app/dmg 落在新位置而 verify 按旧路径找，CI 到 run 时
才炸（FileNotFoundError），或 verify 找到的根本不是刚构建的产物。

W44 把这条边钉成两半（W32/W34/W38–W42 同型分工）：

- **W44a 语料守卫**：脚本的 bundle 组合行、app 行、dmg 行各恰一处；
  yml 的 ``--app-bundle``/``--dmg`` 各恰一处。
- **W44b 路径同账**：脚本拼出的 app 路径（段 join）== yml 的
  ``--app-bundle`` 字面路径；脚本拼出的 dmg 目录前缀 == yml 的
  ``--dmg`` 去掉 ``*.dmg`` 后的前缀——两段逐字恰等。

边界：只判路径字面同账——不判 dmg 文件名模板（W34 的 aarch64 后缀
词表已管）、不判 tauri 实际输出布局（tauri 升级行为，CI 负责）、
不判 verify 的执行行为。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MACOS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "build_macos.py"

BUNDLE_RX = re.compile(
    r'bundle\s*=\s*desktop\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"'
    r'\s*/\s*"([^"]+)"'
)
APP_RX = re.compile(r'app\s*=\s*bundle\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"')
DMG_RX = re.compile(r'dmg\s*=\s*bundle\s*/\s*"([^"]+)"\s*/\s*f"')
APP_BUNDLE_RX = re.compile(r"--app-bundle\s+(\S+)")
DMG_ARG_RX = re.compile(r"--dmg\s+(\S+)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_paths() -> tuple[str, str, str]:
    """返回 (bundle 前缀, app 相对路径, dmg 目录相对段)。"""
    text = _text(SCRIPT)
    bundle = BUNDLE_RX.findall(text)
    assert len(bundle) == 1, (
        f"build_macos.py 的 bundle 组合行应恰一处，实测 {len(bundle)} 处"
        "——W44a 语料守卫"
    )
    app = APP_RX.findall(text)
    assert len(app) == 1, (
        f"build_macos.py 的 app 产物行应恰一处，实测 {len(app)} 处"
        "——W44a 语料守卫"
    )
    dmg = DMG_RX.findall(text)
    assert len(dmg) == 1, (
        f"build_macos.py 的 dmg 产物行应恰一处，实测 {len(dmg)} 处"
        "——W44a 语料守卫"
    )
    prefix = "desktop/" + "/".join(bundle[0])
    return prefix, f"{app[0][0]}/{app[0][1]}", dmg[0]


def test_product_path_anchors() -> None:
    """W44a：脚本三行 + yml 两个消费点各恰一处。"""
    _script_paths()
    text = _text(MACOS_WF)
    assert len(APP_BUNDLE_RX.findall(text)) == 1, (
        "desktop-macos.yml 的 --app-bundle 应恰一处——W44a 语料守卫"
    )
    assert len(DMG_ARG_RX.findall(text)) == 1, (
        "desktop-macos.yml 的 --dmg 应恰一处——W44a 语料守卫"
    )


def test_product_paths_agree() -> None:
    """W44b：脚本拼出的 app 路径与 dmg 目录前缀 == yml 字面路径。"""
    prefix, app_rel, dmg_rel = _script_paths()
    text = _text(MACOS_WF)
    app_literal = APP_BUNDLE_RX.search(text).group(1)
    dmg_literal = DMG_ARG_RX.search(text).group(1)

    script_app = f"{prefix}/{app_rel}"
    assert script_app == app_literal, (
        f"macOS app 产物路径不同账：脚本 {script_app!r} vs workflow "
        f"{app_literal!r}——产物挪目录两边同改，否则 verify run 时才炸"
    )
    script_dmg_dir = f"{prefix}/{dmg_rel}"
    m = re.fullmatch(r"(.+)/\*\.dmg", dmg_literal)
    assert m, f"--dmg 应为 `<目录>/*.dmg` 形状，实测 {dmg_literal!r}"
    assert script_dmg_dir == m.group(1), (
        f"macOS dmg 目录前缀不同账：脚本 {script_dmg_dir!r} vs workflow "
        f"{m.group(1)!r}"
    )
