"""R229：smoke_installer flavor 参数自洽（W 系续 W55）。

背景（实测，R228 §3 登记）：``smoke_installer.ps1`` 的 flavor 参数
``[string]$Flavor = "core"``（L7）带 ``[ValidateSet("core", "full")]``
（L6，W42 已钉集合恰等）——默认值 "core" ∈ 集合。默认值漂移无人判：
有人把默认值改成集合外的值（如 "complete"），PowerShell 在脚本启动
时就抛 ParameterArgumentValidationError——workflow 里表现为「冒烟
步骤秒失败」，与集合漂移（W42）是两个不同的故障面。

W55 把默认值钉进 W42 的集合账：

- **W55a 语料守卫**：默认值赋值形状（``[string]$Flavor = "…"``）恰
  一处；ValidateSet 恰一处（W42 已钉集合恰等，这里钉形状存在）。
- **W55b 默认值自洽**：默认值 ∈ ValidateSet 集合（== {core, full}
  的成员）。

边界：只判默认值 ∈ 集合的字面同账——不判 ValidateSet 集合的内容
（W42 已管恰等 {core, full}）、不判 PowerShell 的参数绑定语义、
不判执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "smoke_installer.ps1"

DEFAULT_RX = re.compile(r'\[string\]\$Flavor\s*=\s*"([^"]+)"')
VALIDATESET_RX = re.compile(r'\[ValidateSet\("([^"]+)",\s*"([^"]+)"\)\]')


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_flavor_default_anchor() -> None:
    """W55a：默认值赋值与 ValidateSet 各恰一处。"""
    defaults = DEFAULT_RX.findall(_text())
    assert len(defaults) == 1, (
        f"smoke_installer.ps1 的 $Flavor 默认值赋值应恰一处，实测 "
        f"{len(defaults)} 处——W55a 语料守卫"
    )
    validatesets = VALIDATESET_RX.findall(_text())
    assert len(validatesets) == 1, (
        f"smoke_installer.ps1 的 ValidateSet 应恰一处，实测 "
        f"{len(validatesets)} 处——W55a 语料守卫"
    )


def test_flavor_default_in_vocabulary() -> None:
    """W55b：默认值 ∈ ValidateSet 集合（存在才判，缺失归 W55a）。"""
    defaults = DEFAULT_RX.findall(_text())
    validatesets = VALIDATESET_RX.findall(_text())
    if not defaults or not validatesets:
        return
    default = defaults[0]
    validateset = validatesets[0]
    assert default in validateset, (
        f"$Flavor 默认值 {default!r} 不在 ValidateSet {list(validateset)}"
        " 里——PowerShell 启动即抛 ParameterArgumentValidationError，"
        "冒烟步骤秒失败"
    )
