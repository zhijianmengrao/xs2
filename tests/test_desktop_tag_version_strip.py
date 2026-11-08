"""R217：tag→version 剥离逻辑同账（W 系续 W46）。

背景（实测，R216 §3 登记）：desktop-windows.yml 的
``version="${RELEASE_TAG#v}"``（tag 剥 v 得版本号）恰 **3 处**——
bash 后缀循环步（L172）、create_update_manifest 步（L184）、
publish_r2_release 步（L223）。同一条「tag→版本」剥离逻辑三处复制：
一处改剥离逻辑（如支持 `v` 前缀之外的形式、或改用 `${RELEASE_TAG:1}`）
而其余没跟，同一 tag 构建出的清单/发布资产版本号分叉——latest.json
写 1.2.3、发布资产名写 1.2.3 但 R2 前缀写 v1.2.3，更新通道与资产
目录对不上。

W46 把这条边钉成两半（W32/W34/W38–W45 同型分工）：

- **W46a 语料守卫**：``version="${RELEASE_TAG#v}"`` 恰 3 处——
  加/删/改写先红语料守卫。
- **W46b 剥离逻辑同账**：3 处逐字恰等（每处 == 首处；集合大小 1）。

边界：只判该赋值语句的字面同账——不判 tag 的取值（RELEASE_TAG 来自
github.ref_name，CI 负责）、不判 ``${RELEASE_TAG#v}`` 的 bash 语义、
不判发布版本与代码版本五源的关系（tag 驱动发版的设计语义，见 R216
§5 实测观察）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"
STRIP_RX = re.compile(r'version="\$\{RELEASE_TAG#v\}"')


def _text() -> str:
    return WINDOWS_WF.read_text(encoding="utf-8")


def test_tag_strip_assignment_count() -> None:
    """W46a：version="${RELEASE_TAG#v}" 恰 3 处。"""
    found = STRIP_RX.findall(_text())
    assert len(found) == 3, (
        f"desktop-windows.yml 的 tag→version 剥离赋值应恰 3 处，实测 "
        f"{len(found)} 处——W46a 语料守卫"
    )


def test_tag_strip_assignments_agree() -> None:
    """W46b：3 处逐字恰等（集合大小 1）。"""
    found = STRIP_RX.findall(_text())
    assert found, "desktop-windows.yml 没有剥离赋值——W46b 无锚"
    assert len(set(found)) == 1, (
        f"tag→version 剥离逻辑不同账：{found}——改剥离逻辑三处同改，"
        "否则同一 tag 的清单/资产版本分叉"
    )
