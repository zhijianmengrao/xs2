"""R230：installer 步 outputs 定义 == 消费（W 系续 W56）。

背景（实测，R228 §3 登记）：desktop-windows.yml 的 installer 步定义
三个 GITHUB_OUTPUT（``"path=$($installer.FullName)" >> $env:GITHUB_
OUTPUT`` 等三行：path/checksum/signature），消费点为 smoke_installer
的 ``outputs.path``（L127）与 upload-artifact 的三个（L142–144）。
定义与消费漂移无人判：消费写错输出名（引用不存在的 output——空字
符串传给 smoke/artifact）、或定义改名/删除而消费没跟——安装冒烟拿
到空 Installer 路径、或 artifact 上传空路径。

W56 把这条边钉成两半（W32/W34/W38–W55 同型分工）：

- **W56a 语料守卫**：定义块恰 3 行（``"key=… >> $env:GITHUB_OUTPUT``
  形状）。
- **W56b 定义 == 消费（双向）**：定义键集合 == 消费键集合（消费未
  定义的红、定义未消费的死输出也红）。

边界：只判输出键名的字面同账——不判输出的取值（``$installer.FullName``
的解析是 PowerShell 运行时）、不判 artifact 的上传行为（CI 负责）、
不判其他 step 的 outputs（smoke 步没有 outputs）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"

# 定义：`"key=…" >> $env:GITHUB_OUTPUT`（引号在 >> 之前闭合）
DEFINE_RX = re.compile(r'"(\w+)=[^"]*"\s*>>\s*\$env:GITHUB_OUTPUT')
# 消费：steps.installer.outputs.<key>
CONSUME_RX = re.compile(r"steps\.installer\.outputs\.(\w+)")

EXPECTED_DEFINES = 3


def _text() -> str:
    return WINDOWS_WF.read_text(encoding="utf-8")


def test_output_definition_count() -> None:
    """W56a：定义块恰 3 行。"""
    defined = DEFINE_RX.findall(_text())
    assert len(defined) == EXPECTED_DEFINES, (
        f"installer 步的 outputs 定义应恰 {EXPECTED_DEFINES} 行，实测 "
        f"{len(defined)} 行（{defined}）——W56a 语料守卫"
    )


def test_output_keys_agree() -> None:
    """W56b：定义键集合 == 消费键集合（双向：谁多谁少都红）。"""
    defined = set(DEFINE_RX.findall(_text()))
    consumed = set(CONSUME_RX.findall(_text()))
    assert defined and consumed, "outputs 定义或消费为空——W56b 无锚"
    undefined = sorted(consumed - defined)
    dead = sorted(defined - consumed)
    assert not undefined and not dead, (
        f"installer 步 outputs 定义与消费不同账：消费未定义 {undefined}，"
        f"定义未消费 {dead}——改名/删除两侧必须同改，否则空字符串传给 "
        "smoke/artifact"
    )
