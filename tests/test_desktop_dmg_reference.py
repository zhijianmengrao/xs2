"""R186：desktop README DMG 产物路径同账——文档产物名 ↔ 构建模板 ↔ tauri 版本（W 系续 W23）。

背景（实测，R184 §3 登记、R186 开工复核）：``desktop/README.md`` 的
macOS 本地验证命令硬编码 DMG 产物名：

- ``desktop/README.md``：
  ``--dmg desktop/src-tauri/target/release/bundle/dmg/DeterminFlow_1.0.2_aarch64.dmg``；
- ``desktop/scripts/build_macos.py``：产物名由模板
  ``DeterminFlow_{version}_aarch64{suffix}.dmg`` 生成，``version`` 读自
  ``tauri.conf.json``（W18 五源之一）。

桌面版本升级（W18 会要求五源同步改）时，README 里这份硬编码不在五源
清单里：版本 1.0.2 → 1.0.3 后，照抄验证命令会「文件不存在」。这条边
无人判——W18 钉五份清单，README 的产物名是第六处独立账。

W23 把这条边钉成两半：

- **W23a 语料守卫**：README 恰一处 DMG 产物名引用；``build_macos.py``
  恰一处产物名模板；两者都能解析出 ``DeterminFlow_<version>_aarch64
  <suffix>.dmg`` 形状。
- **W23b 三处同账**：README 的版本 == tauri 版本（W18 的锚）；README
  的架构 == 模板架构（``aarch64``）；README 的后缀 == ``core`` 模板
  后缀（空，无 ``-full``）。

边界：只判 ``desktop/README.md`` 的 macOS 验证命令与 ``build_macos.py``
的产物模板——不判根 README / release-notes 的历史发版产物名（那是各
版本发版的史料）、不判 Windows 安装包名（NSIS 产物由 desktop-windows
链路负责）、不判 DMG 是否真的构建出来（macOS CI 负责）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
BUILD_MACOS = REPO_ROOT / "desktop" / "scripts" / "build_macos.py"
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"

README_DMG_RX = re.compile(
    r"DeterminFlow_(\d+\.\d+\.\d+)_([a-z0-9]+)(-full)?\.dmg"
)
TEMPLATE_RX = re.compile(
    r'"DeterminFlow_\{version\}_([a-z0-9]+)\{suffix\}\.dmg"'
)
VERSION_RX = re.compile(r"^\d+\.\d+\.\d+$")


def _readme_dmg() -> tuple[str, str, str]:
    text = README.read_text(encoding="utf-8")
    matches = README_DMG_RX.findall(text)
    assert len(matches) == 1, (
        f"desktop/README.md 的 DMG 产物名引用应恰一处，实测 {matches}"
        "——W23 无锚"
    )
    version, arch, suffix = matches[0]
    return version, arch, suffix


def _build_template() -> tuple[str, str]:
    text = BUILD_MACOS.read_text(encoding="utf-8")
    matches = TEMPLATE_RX.findall(text)
    assert len(matches) == 1, (
        f"build_macos.py 的 DMG 产物模板应恰一处，实测 {matches}"
        "——W23 无锚"
    )
    return matches[0]


def _tauri_version() -> str:
    document = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    version = document.get("version")
    assert isinstance(version, str) and VERSION_RX.match(version), (
        f"tauri.conf.json 的 version 不是 X.Y.Z：{version!r}——W23 无锚"
    )
    return version


def test_dmg_reference_sources_are_parseable() -> None:
    """W23a：README 引用与构建模板各恰一处，形状完整。"""
    version, arch, suffix = _readme_dmg()
    template_arch = _build_template()
    assert VERSION_RX.match(version), f"README DMG 版本不是 X.Y.Z：{version!r}"
    assert arch == template_arch, (
        f"README DMG 架构 {arch!r} 与 build_macos.py 模板 {template_arch!r} 不同"
    )
    assert suffix == "", (
        f"README 引用的应是 Core 产物（无 -full 后缀），实测 {suffix!r}"
    )


def test_readme_dmg_reference_matches_the_build_sources() -> None:
    """W23b：README 产物名的版本 / 架构 / 后缀与构建侧同账。"""
    version, arch, _ = _readme_dmg()
    template_arch = _build_template()
    tauri_version = _tauri_version()
    if version != tauri_version or arch != template_arch:
        raise AssertionError(
            "desktop/README.md 的 DMG 产物名与构建侧不同账："
            f"README 写 DeterminFlow_{version}_{arch}.dmg，"
            f"tauri 版本是 {tauri_version}，build_macos.py 模板架构是 "
            f"{template_arch}——升版本 / 改架构时必须同步更新验证命令"
        )
