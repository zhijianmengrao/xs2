"""R193：desktop README 工作流名同账（W 系续 W28）。

背景（实测，R192 §3 登记、R193 开工修复）：``desktop/README.md`` 的
「桌面更新发布」节长期写「macOS 候选由 ``Desktop macOS candidate`` 工作流
生成」，而 ``.github/workflows/desktop-macos.yml`` 的 ``name:`` 是
``Desktop macOS``——README 引用的名字在仓库里不存在（工作流文件、job 名
与产物名里的 "candidate" 都是候选制的叙述词，只有工作流 ``name:`` 没有
它）。照 README 排查 CI 的人会找不到这个工作流；workflow 改名时 README
同样会静默失真。这是候选制第三次在登记阶段抓到真实不一致（前两次
R177 P10、R187 W24），R193 先修文档再钉同账。

W28 把这条边钉成两半：

- **W28a 词表与形状守卫**：``.github/workflows/desktop-*.yml`` 每份都有
  ``name:`` 字符串（结构守卫），name 集合恰等于登记词表
  ``{Desktop macOS, Desktop Windows}``——新增/改名/删除 desktop 工作流先
  红在词表，强制显式扩表；README 的「``X`` 工作流」引用形状（反引号
  token 紧跟「工作流」）全文档恰一处。
- **W28b 名字同账**：README 引用的名必须 ∈ desktop-*.yml 的 name 集合
  （逐字）——workflow 改名而 README 没跟、或 README 写出集合外的名，
  双向显式红。

边界：只判 desktop/README.md 的「``X`` 工作流」引用形状与两份
desktop-*.yml 的 ``name:``——不判 Windows 表「工作流」行引用的路径
（W26 射程：路径存在性）、不判 ``replace-desktop-assets.yml``（文件名不
匹配 ``desktop-*.yml`` glob，其 ``name:`` 由 job 内 ``workflow_call`` 消
费，不在人读引用面）、不判工作流的触发条件与 job 行为（CI 负责）、
不判 README 里不带「工作流」后缀的反引号 token。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

REF_RX = re.compile(r"`([^`]+)`\s*工作流")

KNOWN_WORKFLOW_NAMES = frozenset({"Desktop macOS", "Desktop Windows"})


def _readme_refs() -> list[str]:
    text = README.read_text(encoding="utf-8")
    refs = REF_RX.findall(text)
    assert len(refs) == 1, (
        f"desktop/README.md 的「`X` 工作流」引用应恰一处，实测 {refs}"
        "——W28 无锚"
    )
    return refs


def _workflow_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in sorted(WORKFLOW_DIR.glob("desktop-*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = document.get("name") if isinstance(document, dict) else None
        assert isinstance(name, str) and name.strip(), (
            f"{path.name} 没有 name 字符串——W28 无锚"
        )
        names[path.name] = name.strip()
    assert names, (
        ".github/workflows/ 下没有 desktop-*.yml 工作流——W28 无锚"
    )
    return names


def test_desktop_workflow_names_stay_in_the_registered_vocabulary() -> None:
    """W28a：desktop-*.yml 的 name 集合 == 登记词表；README 引用形状恰一处。"""
    names = _workflow_names()
    assert set(names.values()) == set(KNOWN_WORKFLOW_NAMES), (
        f"desktop 工作流名集合漂移：实测 {sorted(names.values())}，词表 "
        f"{sorted(KNOWN_WORKFLOW_NAMES)}——新增/改名/删除 desktop 工作流"
        "必须先更新本判据的词表，再同步 desktop/README.md 的引用"
    )
    _readme_refs()


def test_readme_workflow_reference_matches_a_workflow_name() -> None:
    """W28b：README「`X` 工作流」引用的名 ∈ desktop-*.yml 的 name 集合。"""
    refs = _readme_refs()
    names = set(_workflow_names().values())
    for ref in refs:
        assert ref in names, (
            f"desktop/README.md 引用的工作流名 `{ref}` 不在 desktop-*.yml 的 "
            f"name 集合 {sorted(names)} 中——workflow 改名必须同步 README，"
            "README 也不得写出集合外的名"
        )
