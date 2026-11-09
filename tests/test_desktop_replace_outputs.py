"""R233：replace workflow release 步 outputs 定义 == 消费（W 系续 W58）。

背景（实测，R232 §3 登记）：replace-desktop-assets.yml 的 release 步
用一行 ``f.write`` 向 GITHUB_OUTPUT 写三个键（version/tag/pub_date，
L105 的格式串 ``version={version}\\ntag={tag}\\npub_date={stamp}\\n``），
消费点为后续两步的 ``steps.release.outputs.tag``（L110）、
``.version``（L128）、``.tag``（L129）、``.pub_date``（L130）。定义与
消费漂移无人判：消费写错键名（发布上传拿到空 version/tag——R2 路径
错位、稳定清单发布时间缺失）或定义改名/删除而消费没跟。

W58 把这条边钉成两半（W32/W34/W38–W57 同型分工）：

- **W58a 语料守卫**：release 步的 GITHUB_OUTPUT 定义恰一处 f.write、
  恰 3 个键行。
- **W58b 定义 == 消费（双向）**：定义键集合 == 消费键集合（消费未
  定义的红、定义未消费的死输出也红）。

边界：只判输出键名的字面同账——不判键值（version/tag/stamp 的取值
由其他判据与脚本负责）、不判 ``gh release``/``publish_r2_release``
行为（CI 负责）、不判其余 step 的 outputs。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)

# 定义：release 步的 `f.write(f'key=…')`（f-string 内用字面 \n 分行）。
DEFINE_RX = re.compile(r"f\.write\(f'([^']*)'\)")
# 消费：`steps.release.outputs.<key>`。
CONSUME_RX = re.compile(r"steps\.release\.outputs\.(\w+)")

EXPECTED_DEFINES = 3
# f-string 里的字面 `\n`（反斜杠 + n），不是换行符。
NEWLINE_ESCAPE = chr(92) + "n"


def _text() -> str:
    return REPLACE_WF.read_text(encoding="utf-8")


def _blocks() -> list[str]:
    return DEFINE_RX.findall(_text())


def _defined() -> list[str]:
    blocks = _blocks()
    if not blocks:
        return []
    keys = []
    for segment in blocks[0].split(NEWLINE_ESCAPE):
        name, sep, _ = segment.partition("=")
        if sep and name:
            keys.append(name)
    return keys


def test_output_definition_count() -> None:
    """W58a：定义恰一处 f.write、恰 3 个键行。"""
    blocks = _blocks()
    assert len(blocks) == 1, (
        f"replace workflow 的 f.write 定义应恰 1 处，实测 {len(blocks)} 处"
        "——W58a 语料守卫"
    )
    defined = _defined()
    assert len(defined) == EXPECTED_DEFINES, (
        f"release 步的 outputs 定义应恰 {EXPECTED_DEFINES} 个键，实测 "
        f"{len(defined)} 个（{defined}）——W58a 语料守卫"
    )


def test_output_keys_agree() -> None:
    """W58b：定义键集合 == 消费键集合（双向：谁多谁少都红）。"""
    defined = set(_defined())
    consumed = set(CONSUME_RX.findall(_text()))
    assert defined and consumed, "outputs 定义或消费为空——W58b 无锚"
    undefined = sorted(consumed - defined)
    dead = sorted(defined - consumed)
    assert not undefined and not dead, (
        f"release 步 outputs 定义与消费不同账：消费未定义 {undefined}"
        f"（发布上传拿到空值）、定义未消费 {dead}——改名/删除两侧必须同改"
    )
