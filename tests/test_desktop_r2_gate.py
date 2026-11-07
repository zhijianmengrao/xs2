"""R213：R2 分发门控变量同账（W 系续 W43）。

背景（实测，R212 §3 登记）：R2 分发是否启用的门控有 4 份账——
desktop/README.md 两处叙述（L120「两个仓库必须保持
``R2_DISTRIBUTION_ENABLED=true``」、L126「当仓库变量
``R2_DISTRIBUTION_ENABLED=true`` 时」）+ desktop-windows.yml 与
replace-desktop-assets.yml 各一处 ``if: vars.R2_DISTRIBUTION_ENABLED
== 'true'``。门控漂移无人判：一边改门控语义（如 `!= 'false'`，空值
行为完全不同）或换比较值（'True'/'yes'），另一边没跟——README 教人
配置 `=true`，workflow 却在等别的值，R2 分发静默不启用（发布任务
整段跳过，无人察觉）。

W43 把这条边钉成两半（W31/W32/W33 同型分工）：

- **W43a 语料守卫**：两 workflow 的门控条件各恰一处（形状值无关，
  `==`/`!=` 都算门控）；README 的 `R2_DISTRIBUTION_ENABLED=<值>`
  提及恰 2 处。
- **W43b 门控同账**：两 workflow 的门控条件整行逐字恰等；README 提
  及的门控值集合 == workflow 比较值集合（按集合，prose 重复提及不
  影响账面）。

边界：只判门控条件的字面与值的同账——不判门控的求值行为（CI
负责）、不判 README 两处叙述的措辞（prose 措辞不进射程，只对值）、
不判 `R2_PUBLIC_BASE_URL` 等其他变量（W31/W30 已管）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
README = REPO_ROOT / "desktop" / "README.md"
GATED_WORKFLOWS = ("desktop-windows.yml", "replace-desktop-assets.yml")

# W43a：门控条件形状（值与 ==/!= 运算符无关）。
GATE_RX = re.compile(
    r"if:\s*(vars\.R2_DISTRIBUTION_ENABLED\s*[=!]=\s*'([^']+)')"
)
README_MENTION_RX = re.compile(r"R2_DISTRIBUTION_ENABLED=(\w+)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _gates() -> dict[str, tuple[str, str]]:
    """每份 workflow 的（门控条件全文, 比较值）；恰一处由 W43a 守。"""
    gates: dict[str, tuple[str, str]] = {}
    for name in GATED_WORKFLOWS:
        found = GATE_RX.findall(_text(WORKFLOWS / name))
        assert found, f"{name} 没有 R2_DISTRIBUTION_ENABLED 门控——W43 无锚"
        gates[name] = found[0]
    return gates


def test_gate_anchor_counts() -> None:
    """W43a：两 workflow 门控各恰一处；README 提及恰 2 处。"""
    for name in GATED_WORKFLOWS:
        found = GATE_RX.findall(_text(WORKFLOWS / name))
        assert len(found) == 1, (
            f"{name} 的 R2_DISTRIBUTION_ENABLED 门控应恰一处，实测 "
            f"{len(found)} 处——W43a 语料守卫"
        )
    mentions = README_MENTION_RX.findall(_text(README))
    assert len(mentions) == 2, (
        f"desktop/README.md 的 R2_DISTRIBUTION_ENABLED 提及应恰 2 处，"
        f"实测 {len(mentions)} 处——W43a 语料守卫"
    )


def test_gate_conditions_agree() -> None:
    """W43b：两 workflow 门控值集合一致；README 提及值集合 == 门控值集合。"""
    gates = _gates()
    workflow_conditions = {condition for condition, _value in gates.values()}
    assert len(workflow_conditions) == 1, (
        f"两 workflow 的 R2 门控条件不同账：{gates}——改门控语义/比较值"
        "必须两边同改，否则一个平台分发、另一个静默跳过"
    )
    workflow_values = {value for _condition, value in gates.values()}
    readme_values = set(README_MENTION_RX.findall(_text(README)))
    assert readme_values == workflow_values, (
        f"README 门控叙述与 workflow 门控不同账：README {sorted(readme_values)}"
        f" vs workflow {sorted(workflow_values)}——按 README 配置仓库的人"
        "会遇到分发静默不启用"
    )
