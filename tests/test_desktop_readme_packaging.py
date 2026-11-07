"""R191：desktop README 表 ↔ tauri conf 打包三键同账（W 系续 W27）。

背景（实测，R188 §3 登记、R191 开工复核）：``desktop/README.md`` 用三行
表声明打包产物形态，每行对应一个 tauri 配置键：

- macOS 表「产物 | ``.app`` + ``.dmg``」↔
  ``tauri.macos.conf.json`` 的 ``bundle.targets == ["app", "dmg"]``；
- macOS 表「更新包 | ``createUpdaterArtifacts=false``」↔ 同键 ``false``
  （不生成 ``.sig`` / updater tar.gz，macOS 候选不进更新通道）；
- Windows 表「安装包 | NSIS ``currentUser``」↔ ``tauri.conf.json`` 的
  ``bundle.windows.nsis.installMode == "currentUser"``。

改打包目标 / updater 产物 / 安装模式时，README 三行会静默失真：targets
加减一种产物、updater 产物开关翻转、安装模式从 ``currentUser``（不申请
管理员权限）换 ``perMachine``/``both``，都只有 conf 单边变化——照表安装
或照表发布的人会拿到与文档相反的行为。这条边此前无人判：W22 管定位符、
W23 管 DMG 产物名、W24 管候选范围、W25 管 ui 路径链，打包三键没有锚。

W27 把三行表钉成两半：

- **W27a 语料守卫**：三行表各恰一处（产物/更新包在 macOS 小节、安装包
  在 Windows 小节）；产物行同时含 ``.app`` 与 ``.dmg`` 两个扩展名 token、
  更新包行含 ``createUpdaterArtifacts=<bool>`` token、安装包行含 NSIS
  安装模式 token；三个 conf 键都存在且类型正确（targets 列表 /
  createUpdaterArtifacts 布尔 / installMode 字符串）。
- **W27b 三键同账**：产物行扩展名集合 == ``targets`` 集合（双向：少提
  或多提都红）；更新包 token 的布尔 == conf 值；安装模式 token ==
  conf 值。

边界：只判这三行表与三个键——不判基础 ``tauri.conf.json`` 的
``bundle.targets == ["nsis"]`` 与 ``bundle.createUpdaterArtifacts == true``
（Windows 侧的 NSIS 目标与发版 ``.sig`` 账，README「桌面更新发布」节
另行叙述，登记口径未含）、不判 ``nsis`` 的其余键（compression / 
languages / installerHooks 等）、不判 ``flavor`` 矩阵（W24 射程）、
不判打包的执行行为（CI 负责）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
MACOS_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.macos.conf.json"

EXTENSION_TOKEN_RX = re.compile(r"`\.(app|dmg|deb|rpm|appimage|msi|nsis)`")
UPDATER_TOKEN_RX = re.compile(r"`createUpdaterArtifacts=(true|false)`")
INSTALL_MODE_TOKEN_RX = re.compile(r"NSIS\s+`([A-Za-z]+)`")

TRUE_SET = {"true": True, "false": False}


def _section(key: str) -> list[tuple[int, str]]:
    lines = README.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith(f"## {key}")),
        None,
    )
    assert start is not None, f"desktop/README.md 缺少「{key}」小节——W27 无锚"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return [(i + 1, lines[i]) for i in range(start, end)]


def _table_row(cells: list[tuple[int, str]], key: str, prefix: str | None = None) -> str:
    needle = f"| {key} | {prefix}" if prefix else f"| {key} |"
    rows = [line for _, line in cells if line.startswith(needle)]
    assert len(rows) == 1, (
        f"表「{key}」行应恰一处，实测 {len(rows)} 处——W27 无锚"
    )
    return rows[0]


def _row_value(line: str) -> str:
    return line.split("|")[2].strip()


def _macos_conf() -> dict:
    bundle = json.loads(MACOS_CONF.read_text(encoding="utf-8")).get("bundle", {})
    targets = bundle.get("targets")
    assert isinstance(targets, list) and targets, (
        "tauri.macos.conf.json 缺少 bundle.targets 列表——W27 无锚"
    )
    updater = bundle.get("createUpdaterArtifacts")
    assert isinstance(updater, bool), (
        "tauri.macos.conf.json 缺少 bundle.createUpdaterArtifacts 布尔值"
        "——W27 无锚"
    )
    return {"targets": targets, "updater": updater}


def _windows_install_mode() -> str:
    nsis = (
        json.loads(TAURI_CONF.read_text(encoding="utf-8"))
        .get("bundle", {})
        .get("windows", {})
        .get("nsis", {})
    )
    mode = nsis.get("installMode")
    assert isinstance(mode, str) and mode, (
        "tauri.conf.json 缺少 bundle.windows.nsis.installMode 字符串值"
        "——W27 无锚"
    )
    return mode


def test_readme_packaging_rows_parse() -> None:
    """W27a：三行表各恰一处；token 形状；conf 三键存在且类型正确。"""
    product_row = _table_row(_section("macOS"), "产物")
    extensions = set(EXTENSION_TOKEN_RX.findall(_row_value(product_row)))
    assert {"app", "dmg"} <= extensions, (
        f"macOS 产物行应同时含 .app 与 .dmg token，实测 {sorted(extensions)}"
        "——W27a 语料守卫"
    )

    updater_row = _table_row(_section("macOS"), "更新包")
    updater_tokens = UPDATER_TOKEN_RX.findall(_row_value(updater_row))
    assert len(updater_tokens) == 1, (
        f"macOS 更新包行应恰一处 createUpdaterArtifacts=<bool> token，"
        f"实测 {updater_tokens}——W27a 语料守卫"
    )

    installer_row = _table_row(_section("Windows"), "安装包", prefix="NSIS")
    mode_tokens = INSTALL_MODE_TOKEN_RX.findall(_row_value(installer_row))
    assert len(mode_tokens) == 1, (
        f"Windows 安装包行应恰一处 NSIS 安装模式 token，实测 {mode_tokens}"
        "——W27a 语料守卫"
    )

    _macos_conf()
    _windows_install_mode()


def test_readme_packaging_rows_match_the_tauri_configs() -> None:
    """W27b：产物集合 == targets；updater 布尔与安装模式与 conf 同账。"""
    conf = _macos_conf()

    product_row = _table_row(_section("macOS"), "产物")
    extensions = set(EXTENSION_TOKEN_RX.findall(_row_value(product_row)))
    targets = set(conf["targets"])
    assert extensions == targets, (
        f"macOS 产物行与 bundle.targets 不同账：targets {sorted(targets)}，"
        f"产物行 {sorted(extensions)}——加减打包目标必须同步更新 README"
    )

    updater_row = _table_row(_section("macOS"), "更新包")
    (updater_token,) = UPDATER_TOKEN_RX.findall(_row_value(updater_row))
    assert TRUE_SET[updater_token] == conf["updater"], (
        f"macOS 更新包行写 createUpdaterArtifacts={updater_token}，conf 是 "
        f"{conf['updater']}——updater 产物开关必须同账"
    )

    installer_row = _table_row(_section("Windows"), "安装包", prefix="NSIS")
    (mode_token,) = INSTALL_MODE_TOKEN_RX.findall(_row_value(installer_row))
    install_mode = _windows_install_mode()
    assert mode_token == install_mode, (
        f"Windows 安装包行写 NSIS `{mode_token}`，conf 是 "
        f"`{install_mode}`——安装模式必须同账"
    )
