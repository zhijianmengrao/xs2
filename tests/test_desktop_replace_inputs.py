"""R231：replace workflow inputs 定义 == 消费（W 系续 W57）。

背景（实测，R228 §3 登记）：replace-desktop-assets.yml 的
``workflow_dispatch.inputs`` 定义两个输入（``windows_run`` L6 /
``macos_run`` L9），消费点为 provenance 步的 env 两行
（``WINDOWS_RUN: ${{ inputs.windows_run }}`` L33 / ``MACOS_RUN:
${{ inputs.macos_run }}`` L34）。定义与消费漂移无人判：消费引用不
存在的输入（gh 收到空字符串——脚本抛 ``Invalid build run ID``）、
或定义改名/删除而消费没跟。

W57 把这条边钉成两半（W32/W34/W38–W56 同型分工）：

- **W57a 语料守卫**：inputs 块恰 2 个键行（``      <key>:`` 形状）。
- **W57b 定义 == 消费（双向）**：定义键集合 == 消费键集合（消费未
  定义的红、定义未消费的死输入也红）。

边界：只判输入名的字面同账——不判输入的 description/required 等其余
键、不判 ``gh api`` 的运行时校验（脚本负责）、不判 workflow 触发与
下载行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)

# 定义：`    inputs:` 块内的 6 空格键行（read_text 统一 CRLF/LF）。
INPUTS_BLOCK_RX = re.compile(r"^    inputs:\n((?:      .*\n)+)", re.M)
INPUT_KEY_RX = re.compile(r"^      (\w+):", re.M)
# 消费：`${{ inputs.<key> }}`（允许表达式修饰，同一表达式只取第一个名）。
CONSUME_RX = re.compile(r"\$\{\{[^}\n]*?inputs\.(\w+)[^}\n]*?\}\}")

EXPECTED_DEFINES = 2


def _text() -> str:
    return REPLACE_WF.read_text(encoding="utf-8")


def _defined() -> list[str]:
    match = INPUTS_BLOCK_RX.search(_text())
    if not match:
        return []
    return INPUT_KEY_RX.findall(match.group(1))


def test_input_definition_count() -> None:
    """W57a：workflow_dispatch.inputs 块恰 2 个键行。"""
    defined = _defined()
    assert len(defined) == EXPECTED_DEFINES, (
        f"replace workflow 的 inputs 定义应恰 {EXPECTED_DEFINES} 个键，"
        f"实测 {len(defined)} 个（{defined}）——W57a 语料守卫"
    )


def test_input_keys_agree() -> None:
    """W57b：定义键集合 == 消费键集合（双向：谁多谁少都红）。"""
    defined = set(_defined())
    consumed = set(CONSUME_RX.findall(_text()))
    assert defined and consumed, "inputs 定义或消费为空——W57b 无锚"
    undefined = sorted(consumed - defined)
    dead = sorted(defined - consumed)
    assert not undefined and not dead, (
        f"replace workflow inputs 定义与消费不同账：消费未定义 "
        f"{undefined}（gh 会拿到空 run id）、定义未消费 {dead}——改名/"
        "删除两侧必须同改"
    )
