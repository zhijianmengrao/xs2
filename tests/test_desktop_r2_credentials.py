"""R195：README R2 分发凭据同账（W 系续 W30）。

背景（实测，R192 §3 登记、R195 开工修复）：``desktop/README.md`` 的
「桌面更新发布」节写「R2 凭据只通过 ``R2_ACCESS_KEY_ID``、
``R2_SECRET_ACCESS_KEY`` Secret 和 ``R2_BUCKET``、``R2_ENDPOINT_URL``
Variable 注入」，另有 ``R2_DISTRIBUTION_ENABLED=true`` 与
``TAURI_SIGNING_PRIVATE_KEY`` 两处提名；而 desktop 工作流实际消费七个
名字——上述六个加 ``vars.R2_PUBLIC_BASE_URL``（带公网缺省值
``https://downloads.determinflow.com``，未设变量时回落）。README 的
「只」清单漏了 ``R2_PUBLIC_BASE_URL``：照清单配仓库的人会少配一个
Variable，发版时 ``--public-base-url`` 拿到回落值而不是仓库里配置的
值——配置静默失效。这是候选制第四次实测抓到真实不一致（R177 P10、
R187 W24、R193 W28 之后），R195 先补清单再钉同账。

W30 把这条边钉成两半：

- **W30a 语料守卫**：「桌面更新发布」节恰一处；节内凭据提名（
  ``R2_*``/``TAURI_*`` 形状的反引号 token，容忍 ``=true`` 后缀）可解析
  非空；「R2 凭据只通过」清单句恰一处；三份 desktop 工作流的
  ``secrets.*``/``vars.*`` 引用可解析（desktop-macos.yml 实测无引用，
  并集非空即可）。
- **W30b 凭据同账**：README 提名的凭据名集合 == 三份 desktop 工作流
  （desktop-windows / desktop-macos / replace-desktop-assets）的
  ``secrets.*``/``vars.*`` 引用名集合（双向恰等：workflow 加了名字
  README 不提、README 提了 workflow 不消费，都红）。

边界：只判 README「桌面更新发布」节的凭据提名与三份 desktop workflow
的 ``secrets.*``/``vars.*`` 引用名——不判 ``ci.yml``（实测无
``secrets.*``/``vars.*`` 引用，非桌面分发面）、不判凭据的取值与缺省
回落值（``--public-base-url`` 的回落域名字面值不在本判据射程）、
不判 ``env:` ``AWS_*`` 别名（R2_* 到 AWS_* 的映射是实现细节）、
不判 step 的执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DESKTOP_WORKFLOWS = (
    "desktop-windows.yml",
    "desktop-macos.yml",
    "replace-desktop-assets.yml",
)

SECTION_KEY = "## 桌面更新发布"
LIST_SENTENCE_KEY = "R2 凭据只通过"
CREDENTIAL_RX = re.compile(r"`((?:R2|TAURI)_[A-Z0-9_]+(?:=[^`]*)?)`")
WORKFLOW_REF_RX = re.compile(r"(?:secrets|vars)\.([A-Z0-9_]+)")


def _section_text() -> str:
    lines = README.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(SECTION_KEY)]
    assert len(starts) == 1, (
        f"desktop/README.md 的「桌面更新发布」节应恰一处，实测 {len(starts)} 处"
        "——W30 无锚"
    )
    start = starts[0]
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _readme_credentials() -> set[str]:
    section = _section_text()
    tokens = CREDENTIAL_RX.findall(section)
    assert tokens, "「桌面更新发布」节没有 R2/签名凭据提名——W30 无锚"
    return {token.split("=", 1)[0] for token in tokens}


def _workflow_credentials() -> set[str]:
    consumed: set[str] = set()
    for name in DESKTOP_WORKFLOWS:
        path = WORKFLOWS / name
        text = path.read_text(encoding="utf-8")
        consumed |= set(WORKFLOW_REF_RX.findall(text))
    assert consumed, (
        "三份 desktop workflow 没有任何 secrets.*/vars.* 引用——W30 无锚"
    )
    return consumed


def test_readme_credential_section_parses() -> None:
    """W30a：节恰一处；凭据提名可解析；清单句恰一处；workflow 引用非空。"""
    section = _section_text()
    listed = section.count(LIST_SENTENCE_KEY)
    assert listed == 1, (
        f"「R2 凭据只通过」清单句应恰一处，实测 {listed} 处——W30a 语料守卫"
    )
    names = _readme_credentials()
    unknown = sorted(name for name in names if not re.fullmatch(
        r"(?:R2|TAURI)_[A-Z0-9_]+", name
    ))
    assert not unknown, f"凭据提名出现意外形状：{unknown}——W30a 语料守卫"
    _workflow_credentials()


def test_readme_credential_list_matches_workflow_consumption() -> None:
    """W30b：README 提名集合 == 三份 desktop workflow 的消费集合（双向）。"""
    nominated = _readme_credentials()
    consumed = _workflow_credentials()
    missing = sorted(consumed - nominated)
    extra = sorted(nominated - consumed)
    assert not missing and not extra, (
        "README 凭据清单与 desktop workflow 消费不同账："
        f"workflow 消费但 README 未提名 {missing}，README 提名但 workflow "
        f"不消费 {extra}——「只通过」清单必须与三份 workflow 的 "
        "secrets.*/vars.* 引用逐名恰等"
    )
