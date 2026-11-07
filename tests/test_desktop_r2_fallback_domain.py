"""R197：R2 公网回落域名三源同账（W 系续 W31）。

背景（实测，R196 §3 登记）：R2 分发域名在 R46 变量化后，
``desktop-windows.yml`` 与 ``replace-desktop-assets.yml`` 各带一处
``${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}``
回落缺省（前者注释自述「与 replace-desktop-assets.yml 同款，便于改域名
时不改代码」）；R195 修复后 ``desktop/README.md`` 的「桌面更新发布」节
也带回落说明（``未设置时回落 https://downloads.determinflow.com``）。
三份文件是同一份账的三个来源，回落域名字面值现同值——但两处 workflow
漂移无人判：改域名时只改其一，另一 workflow 与 README 的回落就跟丢，
未设变量的仓库会把公开对象 URL 发到旧域名上（发布成功但校验/下载域名
分叉）。这是候选制登记面里第一次把「同一条回落缺省的多个来源」钉成
同账。

W31 把这条边钉成两半：

- **W31a 语料守卫**：两份分发 workflow 的回落缺省模式各恰一处、
  ``--public-base-url "$R2_PUBLIC_BASE_URL"`` 消费点各恰一处（回落值
  必须真的被发布命令吃掉）；desktop-macos.yml 实测不在 R2 更新通道
  （回落模式 0 处，多出来的第四源当场红）；README 的「未设置时回落」
  说明恰一处。
- **W31b 三源同账**：从三份文件提取的回落域名字面值逐字恰等——任一
  源改域名而其余未跟显式红。

边界：只判回落域名字面值与消费点的存在——不判未设变量时的回落触发
行为（CI 负责）、不判 ``vars.R2_PUBLIC_BASE_URL`` 的取值、不判 R46
注释散文（「同款」自述不进射程）、不判 ``publish_r2_release.py`` 的
URL 拼装逻辑（``public_object_url`` 已有自己的判据面）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
README = REPO_ROOT / "desktop" / "README.md"
PUBLISHING_WORKFLOWS = ("desktop-windows.yml", "replace-desktop-assets.yml")
MACOS_WORKFLOW = "desktop-macos.yml"

FALLBACK_RX = re.compile(
    r"\$\{\{\s*vars\.R2_PUBLIC_BASE_URL\s*\|\|\s*'([^']+)'\s*\}\}"
)
CONSUME_RX = re.compile(r'--public-base-url "\$R2_PUBLIC_BASE_URL"')
README_FALLBACK_RX = re.compile(r"未设置时回落\s*`([^`]+)`")


def _workflow_fallbacks(name: str) -> list[str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return FALLBACK_RX.findall(text)


def _readme_fallbacks() -> list[str]:
    text = README.read_text(encoding="utf-8")
    return README_FALLBACK_RX.findall(text)


def test_fallback_anchor_counts() -> None:
    """W31a：两 workflow 回落/消费各恰一处；macOS 0 处；README 恰一处。"""
    for name in PUBLISHING_WORKFLOWS:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        fallbacks = FALLBACK_RX.findall(text)
        assert len(fallbacks) == 1, (
            f"{name} 的 R2_PUBLIC_BASE_URL 回落缺省应恰一处，实测 "
            f"{len(fallbacks)} 处——W31a 语料守卫"
        )
        consumed = CONSUME_RX.findall(text)
        assert len(consumed) == 1, (
            f"{name} 的 --public-base-url 消费点应恰一处，实测 "
            f"{len(consumed)} 处——回落值必须真的被发布命令吃掉"
        )
    macos = _workflow_fallbacks(MACOS_WORKFLOW)
    assert not macos, (
        f"{MACOS_WORKFLOW} 实测不在 R2 更新通道，出现回落缺省 {macos}"
        "——第四源要么删掉要么并入 W31b 同账"
    )
    readme = _readme_fallbacks()
    assert len(readme) == 1, (
        f"desktop/README.md 的「未设置时回落」说明应恰一处，实测 "
        f"{len(readme)} 处——W31a 语料守卫"
    )


def test_fallback_domains_agree_across_three_sources() -> None:
    """W31b：三源回落域名字面值逐字恰等（双向：谁漂谁红）。"""
    sources: dict[str, str] = {}
    for name in PUBLISHING_WORKFLOWS:
        found = _workflow_fallbacks(name)
        assert found, f"{name} 没有回落缺省——W31b 无锚"
        sources[name] = found[0]
    readme = _readme_fallbacks()
    assert readme, "desktop/README.md 没有回落说明——W31b 无锚"
    sources["desktop/README.md"] = readme[0]

    domains = set(sources.values())
    assert len(domains) == 1, (
        "R2 公网回落域名三源不同账：" + "；".join(
            f"{name}={domain}" for name, domain in sorted(sources.items())
        )
        + "——改域名必须三源同改（两份分发 workflow + README 回落说明）"
    )
