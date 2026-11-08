"""R222：核心安装包名两 workflow 同账（W 系续 W50）。

背景（实测，R220 §3 登记）：核心（core）NSIS 安装包名有两份账——
desktop-windows.yml 的 bash 字面（``installer="release-assets/
DeterminFlow_${version}_x64-setup.exe"``，L185，喂给
create_update_manifest 的 --installer）与 replace-desktop-assets.yml
的 python 组合（``installer=assets / f'DeterminFlow_{version}_
x64-setup.exe'``，L93，补发版资产时的定位）。占位写法不同（bash 的
``${version}`` vs python 的 ``{version}``），安装包名是同一份账：一边
改名/改后缀而另一边没跟——create_update_manifest 按新名读到安装包、
replace 按旧名找（或反之），发版补资产/清单生成找不到文件。

W50 把这条边钉成两半（W32/W34/W38–W49 同型分工）：

- **W50a 语料守卫**：windows 的 installer 赋值恰一处（值无关形状）；
  replace 的组合行恰一处。
- **W50b 安装包名同账**：占位归一（``${version}`` → ``{version}``）
  后两份安装包名逐字恰等。

边界：只判核心安装包名的字面同账——不判 full 安装包名（windows 的
full 走 ``${suffix}`` 变量，W34 的词表已管）、不判 ``.sig``/``.sha256``
派生名（由安装包名推出）、不判 ``release-assets/`` 目录前缀（W37 的
上传面已管）、不判执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
REPLACE_WF = WORKFLOWS / "replace-desktop-assets.yml"

# 值无关形状：只钉「installer= 到 release-assets/ 下的字面」的形状。
WIN_INSTALLER_RX = re.compile(r'installer="(release-assets/[^"]+)"')
REPLACE_INSTALLER_RX = re.compile(r"installer=assets\s*/\s*f'([^']+)'")
BASH_PLACEHOLDER_RX = re.compile(r"\$\{(\w+)\}")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(name: str) -> str:
    """bash 的 ``${version}`` 归一成 python 的 ``{version}``。"""
    return BASH_PLACEHOLDER_RX.sub(r"{\1}", name)


def test_installer_name_anchors() -> None:
    """W50a：windows installer 赋值与 replace 组合行各恰一处。"""
    win = WIN_INSTALLER_RX.findall(_text(WINDOWS_WF))
    assert len(win) == 1, (
        f"desktop-windows.yml 的 installer 赋值应恰一处，实测 {len(win)} 处"
        "——W50a 语料守卫"
    )
    rep = REPLACE_INSTALLER_RX.findall(_text(REPLACE_WF))
    assert len(rep) == 1, (
        f"replace-desktop-assets.yml 的 installer 组合行应恰一处，实测 "
        f"{len(rep)} 处——W50a 语料守卫"
    )


def test_installer_names_agree() -> None:
    """W50b：占位归一后两份安装包名逐字恰等（两侧都在才判，缺失归 W50a）。"""
    win = WIN_INSTALLER_RX.findall(_text(WINDOWS_WF))
    rep = REPLACE_INSTALLER_RX.findall(_text(REPLACE_WF))
    if not win or not rep:
        return
    win_name = _normalize(win[0])
    rep_name = rep[0]
    # windows 侧带 release-assets/ 目录前缀，剥掉后比文件名。
    win_file = win_name.rsplit("/", 1)[-1]
    assert win_file == rep_name, (
        f"核心安装包名不同账：windows {win_file!r} vs replace {rep_name!r}"
        "——改安装包名两 workflow 必须同改，否则发版补资产/清单生成找不"
        "到文件"
    )
