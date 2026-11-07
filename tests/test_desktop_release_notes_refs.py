"""R203：release-notes 引用面（W 系续 W36）。

背景（实测，R200 §3 登记）：``desktop/release-notes/<tag>.md`` 是发版
叙事的承载文件，引用面有两半——

- 生产端：三份发版 workflow 里恰 6 处引用（desktop-windows.yml 3、
  replace-desktop-assets.yml 3），tag 占位符两写法（bash 的
  ``$RELEASE_TAG.md``、python f-string 的 ``{tag}.md``）——目录前缀
  ``desktop/release-notes/`` 与 ``.md`` 后缀是共享字面值；
- 消费端：``docs/community-updates.md`` 恰 2 处 docs 链接
  （``../desktop/release-notes/v1.1.1.md`` / ``v1.1.0.md``），指向
  具体版本的实盘文件。

生产端一处改名/换占位符写法（或消费端链接指向被改名/删除的日志），
发版自动化就在 run 时炸、或读者点开 404——引用面静默分叉。

W36 把这条边钉成两半：

- **W36a 语料与形状同账**：workflow 引用逐份计数恰等（3/3，合计 6）
  且占位符形状 ∈ {``$RELEASE_TAG``, ``{tag}``}（目录前缀 + ``.md``
  后缀钉在提取正则里）；community-updates 的链接恰 2 处。
- **W36b 消费端可解析**：community-updates 的每条链接按 docs/ 为基
  解析后在磁盘——日志改名/删除而文档没跟显式红。

边界：只判引用路径的字面与可解析——不判日志内容、不判 workflow 的
执行行为（CI 负责）、不判 README（实测 0 处 release-notes 引用）、
不判历史日志是否该存在（消费端引用到的必须在盘，没被引用的旧日志
不判）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
COMMUNITY = REPO_ROOT / "docs" / "community-updates.md"

EXPECTED_WORKFLOW_REFS: dict[str, int] = {
    "desktop-windows.yml": 3,
    "replace-desktop-assets.yml": 1 + 2,  # python f-string 一处 + bash 两处
}
ALLOWED_TAG_PLACEHOLDERS = {"$RELEASE_TAG", "{tag}"}

WF_REF_RX = re.compile(r"desktop/release-notes/([^\"'\s)]+)\.md")
COMMUNITY_LINK_RX = re.compile(r"\]\((\.\./desktop/release-notes/[^)]+)\)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_release_notes_reference_shapes() -> None:
    """W36a：workflow 引用逐份 3/3、占位符形状同账；docs 链接恰 2 处。"""
    for name, expected in EXPECTED_WORKFLOW_REFS.items():
        refs = WF_REF_RX.findall(_text(WORKFLOWS / name))
        assert len(refs) == expected, (
            f"{name} 的 release-notes 引用应恰 {expected} 处，实测 "
            f"{len(refs)} 处——W36a 语料守卫"
        )
    bad = sorted(
        {tag for name in EXPECTED_WORKFLOW_REFS
         for tag in WF_REF_RX.findall(_text(WORKFLOWS / name))
         if tag not in ALLOWED_TAG_PLACEHOLDERS}
    )
    assert not bad, (
        f"release-notes 引用出现意外占位符形状：{bad}（合法两写法 "
        f"{sorted(ALLOWED_TAG_PLACEHOLDERS)}）——W36a 形状同账"
    )
    links = COMMUNITY_LINK_RX.findall(_text(COMMUNITY))
    assert len(links) == 2, (
        f"docs/community-updates.md 的 release-notes 链接应恰 2 处，实测 "
        f"{len(links)} 处——W36a 语料守卫"
    )


def test_community_release_notes_links_resolve() -> None:
    """W36b：community-updates 的每条链接按 docs/ 为基解析后在磁盘。"""
    links = COMMUNITY_LINK_RX.findall(_text(COMMUNITY))
    assert links, "community-updates 没有 release-notes 链接——W36b 无锚"
    missing = [
        ref for ref in links
        if not (REPO_ROOT / "docs" / ref).resolve().is_file()
    ]
    assert not missing, (
        f"community-updates 的 release-notes 链接解析不到：{missing}"
        "——日志改名/删除时文档要同改，否则读者点开 404"
    )
