"""R211：smoke_installer.ps1 调用面参数同账（W 系续 W42）。

背景（实测，R208 §3 登记、R211 开工实测补面）：PowerShell 冒烟脚本
``smoke_installer.ps1`` 被 desktop workflow 调用 **恰 1 处**
（desktop-windows.yml 的 smoke 步）：
``./desktop/scripts/smoke_installer.ps1 -Installer "${
{ steps.installer.outputs.path }}" -Flavor "${{ matrix.flavor }}"``；
脚本 ``param()`` 定义恰 2 个参数（``$Installer`` Mandatory /
``$Flavor = "core"``，带 ``[ValidateSet("core", "full")]``）。
调用面漂移无人判：workflow 写错参数名（PowerShell 把无法绑定的参数
当位置参数吞掉或直接报错）、或脚本改名参数而 workflow 没跟；且
``ValidateSet`` 是 **flavor 词表的第六源**（W29 钉的五源之外）——
冒烟脚本允许的 flavor 集合漂移无人判，full 冒烟可能拿 core 的校验
口径。

W42 把这条边钉成两半（W32/W34/W38/W39/W40/W41 同型分工）：

- **W42a 语料守卫**：call site 恰一处；脚本 ``param()`` 恰 2 个参数。
- **W42b 调用面同账**：call site 的参数集合 == ``param()`` 参数集合
  （双向恰等）；``ValidateSet`` 的值集合 == {core, full}（与 W29 的
  flavor 词表第六源同账）。

边界：只判参数名与 ValidateSet 值的字面同账——不判 PowerShell 参数
绑定语义（大小写不敏感是运行时行为）、不判 ``$Flavor`` 默认值的
取值（默认值在词表内即可）、不判脚本执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "smoke_installer.ps1"
CALL_RX = re.compile(r"desktop/scripts/smoke_installer\.ps1([^\r\n]*)")
CALL_PARAM_RX = re.compile(r"-(Installer|Flavor)\b")
PARAM_BLOCK_RX = re.compile(r"param\((.*?)^\)", re.S | re.M)
PARAM_RX = re.compile(r"\[string\]\$(\w+)")
VALIDATESET_RX = re.compile(r'\[ValidateSet\("([^"]+)",\s*"([^"]+)"\)\]')


def _param_names(script_text: str) -> list[str]:
    """param() 块内的参数名（块外的 [string]$ 局部变量不收）。"""
    block = PARAM_BLOCK_RX.search(script_text)
    assert block, "smoke_installer.ps1 没有 param() 块——W42 无锚"
    return PARAM_RX.findall(block.group(1))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_smoke_installer_call_site_shape() -> None:
    """W42a：call site 恰一处；脚本 param() 恰 2 个参数。"""
    calls = CALL_RX.findall(_text(WINDOWS_WF))
    assert len(calls) == 1, (
        f"desktop-windows.yml 的 smoke_installer.ps1 调用应恰 1 处，实测 "
        f"{len(calls)} 处——W42a 语料守卫"
    )
    params = _param_names(_text(SCRIPT))
    assert len(params) == 2, (
        f"smoke_installer.ps1 的 param() 应恰 2 个参数，实测 "
        f"{sorted(params)}——W42a 语料守卫（参数名集合由 W42b 同账）"
    )


def test_smoke_installer_params_and_vocab_agree() -> None:
    """W42b：call site 参数集合 == param() 集合；ValidateSet == {core, full}。"""
    calls = CALL_RX.findall(_text(WINDOWS_WF))
    call_params = sorted(set(CALL_PARAM_RX.findall(calls[0])))
    script_params = sorted(_param_names(_text(SCRIPT)))
    assert call_params == script_params, (
        f"smoke_installer.ps1 调用面参数不同账：call site {call_params} "
        f"vs param() {script_params}——写错参数名/脚本改名都要同改"
    )
    validateset = VALIDATESET_RX.findall(_text(SCRIPT))
    assert len(validateset) == 1, (
        f"smoke_installer.ps1 的 ValidateSet 应恰一处，实测 "
        f"{len(validateset)} 处——W42b 无锚"
    )
    vocab = set(validateset[0])
    assert vocab == {"core", "full"}, (
        f"smoke_installer.ps1 的 flavor 词表（ValidateSet）漂移：{sorted(vocab)}"
        "——这是 W29 五源之外的第六源，改 flavor 词表必须同改"
    )
