"""R227：安装数据目录标识同账（W 系续 W54）。

背景（实测，R224 §3 登记）：安装数据目录的标识有两份账——
``smoke_installer.ps1`` 的 ``$UserData = Join-Path $env:LOCALAPPDATA
"io.determinflow.desktop"``（L10，冒烟校验已装应用的数据目录）与
``tauri.conf.json`` 的 ``"identifier": "io.determinflow.desktop"``
（L5，tauri 按 identifier 建数据目录）。标识漂移无人判：identifier
改名（换品牌/换域）而 smoke 的 UserData 没跟——smoke 检查的是一个
不存在的目录（或旧应用的目录），安装冒烟「通过」但什么都没验到。

W54 把这条边钉成两半（W32/W34/W38–W53 同型分工）：

- **W54a 语料守卫**：脚本的 UserData 行恰一处；conf 的 identifier
  恰一处。
- **W54b 标识同账**：两处 id 逐字恰等（存在才判，缺失归 W54a）。

边界：只判标识的字面同账——不判 ``LOCALAPPDATA`` 的平台语义、不判
tauri 按 identifier 建目录的运行时行为（tauri 负责）、不判 conf 的
其他键（W22 管过 bundle identifier 的 macOS 面、W27 管过打包三键）、
不判执行行为（CI 负责）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
SMOKE_INSTALLER = REPO_ROOT / "desktop" / "scripts" / "smoke_installer.ps1"

USER_DATA_RX = re.compile(
    r'\$UserData\s*=\s*Join-Path\s+\$env:LOCALAPPDATA\s+"([^"]+)"'
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _conf_identifier() -> str:
    document = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    identifier = document.get("identifier")
    assert isinstance(identifier, str) and identifier, (
        "tauri.conf.json 没有 identifier——W54a 无锚"
    )
    return identifier


def test_identifier_anchors() -> None:
    """W54a：脚本的 UserData 行恰一处；conf 的 identifier 存在。"""
    ids = USER_DATA_RX.findall(_text(SMOKE_INSTALLER))
    assert len(ids) == 1, (
        f"smoke_installer.ps1 的 $UserData 赋值应恰一处，实测 {len(ids)} 处"
        "——W54a 语料守卫"
    )
    _conf_identifier()


def test_identifiers_agree() -> None:
    """W54b：两处 id 逐字恰等（存在才判，缺失归 W54a）。"""
    for user_data in USER_DATA_RX.findall(_text(SMOKE_INSTALLER)):
        assert user_data == _conf_identifier(), (
            f"安装数据目录标识不同账：smoke {user_data!r} vs tauri identifier "
            f"{_conf_identifier()!r}——identifier 改名时 smoke 的 UserData "
            "要同改，否则安装冒烟检查的是不存在的目录"
        )
