"""R226：应用显示名两脚本同账（W 系续 W53）。

背景（实测，R224 §3 登记）：应用显示名 "DeterminFlow" 有三处来源——
``build_macos.py`` 的 ``hdiutil create -volname "DeterminFlow"``（L44，
DMG 卷名）与 ``app = bundle / "macos" / "DeterminFlow.app"``（L31，
app 产物名段）、``smoke_installer.ps1`` 的 ``$ProductName =
"DeterminFlow"``（L9，安装后按 DisplayName 找已装应用）。显示名漂移
无人判：一边改名（如加品牌段）而其余没跟——DMG 卷名与 app 名不一致
（Finder 里两个名字）、或 smoke 按 DisplayName 找不到已装应用（安装
冒烟 run 时才炸）。

W53 把这条边钉成两半（W32/W34/W38–W52 同型分工）：

- **W53a 语料守卫**：volname 行、app 产物行、ProductName 行各恰一处。
- **W53b 显示名同账**：三处提取的名字（volname 值 / app 名去 .app /
  ProductName 值）逐字恰等（== "DeterminFlow"）。

边界：只判显示名的字面同账——不判 ``.app`` 后缀（路径面 W44 已管）、
不判 ``$ProductName`` 的查询语义（PowerShell Get-Package 行为）、不判
执行行为（CI 负责）、不判其他 ``DeterminFlow`` 字面（如后缀词表的
产物名前缀，W51 已管）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_MACOS = REPO_ROOT / "desktop" / "scripts" / "build_macos.py"
SMOKE_INSTALLER = REPO_ROOT / "desktop" / "scripts" / "smoke_installer.ps1"

VOLNAME_RX = re.compile(r'"-volname",\s*"([^"]+)"')
APP_NAME_RX = re.compile(r'app\s*=\s*bundle\s*/\s*"[^"]+"\s*/\s*"([^"]+)\.app"')
PRODUCT_RX = re.compile(r'\$ProductName\s*=\s*"([^"]+)"')

EXPECTED_NAME = "DeterminFlow"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _names() -> dict[str, str]:
    text_mac = _text(BUILD_MACOS)
    text_ps1 = _text(SMOKE_INSTALLER)
    volname = VOLNAME_RX.findall(text_mac)
    assert len(volname) == 1, (
        f"build_macos.py 的 -volname 应恰一处，实测 {len(volname)} 处"
        "——W53a 语料守卫"
    )
    app = APP_NAME_RX.findall(text_mac)
    assert len(app) == 1, (
        f"build_macos.py 的 app 产物行应恰一处，实测 {len(app)} 处"
        "——W53a 语料守卫"
    )
    product = PRODUCT_RX.findall(text_ps1)
    assert len(product) == 1, (
        f"smoke_installer.ps1 的 $ProductName 应恰一处，实测 "
        f"{len(product)} 处——W53a 语料守卫"
    )
    return {"volname": volname[0], "app": app[0], "product": product[0]}


def _first_names() -> dict[str, str]:
    """W53b 侧取首个匹配：只守「存在」，不守唯一（唯一归 W53a）。"""
    text_mac = _text(BUILD_MACOS)
    text_ps1 = _text(SMOKE_INSTALLER)
    volname = VOLNAME_RX.findall(text_mac)
    app = APP_NAME_RX.findall(text_mac)
    product = PRODUCT_RX.findall(text_ps1)
    assert volname and app and product, "显示名锚缺失——W53b 无锚"
    return {"volname": volname[0], "app": app[0], "product": product[0]}


def test_display_name_anchors() -> None:
    """W53a：volname 行、app 产物行、ProductName 行各恰一处。"""
    _names()


def test_display_names_agree() -> None:
    """W53b：三处名字逐字恰等（== "DeterminFlow"）。"""
    names = _first_names()
    drifted = {key: value for key, value in names.items() if value != EXPECTED_NAME}
    assert not drifted, (
        f"应用显示名不同账：{drifted}（三处应都为 {EXPECTED_NAME!r}）——"
        "DMG 卷名 / app 名 / smoke 的 DisplayName 查找名必须同改，否则 "
        "Finder 里两个名字、或 smoke 找不到已装应用"
    )
