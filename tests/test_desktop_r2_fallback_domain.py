"""R197 / R241：R2 公网域必须显式提供（W 系续 W31；R241 改判）。

背景：R197 曾把「回落缺省」钉成三源同账（两份 workflow 的
``${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}``
与 desktop/README.md 的「未设置时回落」说明）。R241 拍板改判——实测
``https://downloads.determinflow.com/desktop/stable/latest.json`` 是
**上游**的稳定清单（version 1.1.1，本 fork 是 1.0.2）：本 fork 一旦打开
``R2_DISTRIBUTION_ENABLED`` 而未设 ``R2_PUBLIC_BASE_URL``，生成的清单
URL 会指向别人的域名，客户端的本 fork 公钥验签必败。政策因此从
「三源回落同值」改为「**无任何内置回落，未设即失败**」。

W31 现在钉两半：

- **W31a 语料守卫**：两份分发 workflow 各恰一处裸
  ``R2_PUBLIC_BASE_URL: ${{ vars.R2_PUBLIC_BASE_URL }}`` 声明（不得出现
  ``||`` 缺省）、各恰一处 ``-z "$R2_PUBLIC_BASE_URL"`` fail-closed 守卫、
  各恰一处 ``--public-base-url "$R2_PUBLIC_BASE_URL"`` 消费点；
  desktop-macos.yml 实测不在 R2 更新通道（三类形状各 0 处）；
  desktop/README.md 的「必须显式设置」说明恰一处；
  ``publish_r2_release.py`` 的 ``--public-base-url`` 为 ``required=True``。
- **W31b 无内置缺省**：发布面（两份 workflow + README + 脚本）里不得
  出现 ``downloads.determinflow.com``（回落复活即红）；两份 workflow 的
  env 声明逐字相同（同款声明）。

边界：只判发布面的字面与守卫形状——不判 ``vars.R2_PUBLIC_BASE_URL`` 的
取值（仓库变量，不在树内）、不判未启用 R2 时的行为（门控由 W43 负责）、
不判 ``public_object_url`` 的拼装逻辑（脚本自身判据）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
README = REPO_ROOT / "desktop" / "README.md"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "publish_r2_release.py"
PUBLISHING_WORKFLOWS = ("desktop-windows.yml", "replace-desktop-assets.yml")
MACOS_WORKFLOW = "desktop-macos.yml"

ENV_RX = re.compile(
    r"^\s*R2_PUBLIC_BASE_URL:\s*\$\{\{\s*vars\.R2_PUBLIC_BASE_URL\s*\}\}\s*$",
    re.M,
)
DEFAULT_RX = re.compile(r"R2_PUBLIC_BASE_URL\s*\|\|")
GUARD_RX = re.compile(r'if \[ -z "\$R2_PUBLIC_BASE_URL" \]; then')
CONSUME_RX = re.compile(r'--public-base-url "\$R2_PUBLIC_BASE_URL"')
README_REQUIRED_RX = re.compile(r"必须显式设置")
UPSTREAM_DOMAIN = "downloads.determinflow.com"


def _text(path: Path) -> str:
    assert path.is_file(), f"文件不在：{path}"
    return path.read_text(encoding="utf-8")


def _workflow(name: str) -> str:
    return _text(WORKFLOWS / name)


def test_public_base_shapes() -> None:
    """W31a：两 workflow 各恰一处裸声明 + 守卫 + 消费；README 说明恰一处。"""
    for name in PUBLISHING_WORKFLOWS:
        text = _workflow(name)
        declared = ENV_RX.findall(text)
        assert len(declared) == 1, (
            f"{name} 的裸 R2_PUBLIC_BASE_URL 声明应恰一处，实测 "
            f"{len(declared)} 处——W31a 语料守卫"
        )
        defaults = DEFAULT_RX.findall(text)
        assert not defaults, (
            f"{name} 仍有 R2_PUBLIC_BASE_URL 回落缺省 {len(defaults)} 处"
            "——R241 起禁止任何内置回落"
        )
        guards = GUARD_RX.findall(text)
        assert len(guards) == 1, (
            f"{name} 的 fail-closed 守卫（-z 检查）应恰一处，实测 "
            f"{len(guards)} 处——未设变量必须显式失败"
        )
        consumed = CONSUME_RX.findall(text)
        assert len(consumed) == 1, (
            f"{name} 的 --public-base-url 消费点应恰一处，实测 "
            f"{len(consumed)} 处——值必须真的被发布命令吃掉"
        )

    macos = _workflow(MACOS_WORKFLOW)
    assert not ENV_RX.findall(macos), f"{MACOS_WORKFLOW} 不应声明 R2 公网域"
    assert not CONSUME_RX.findall(macos), f"{MACOS_WORKFLOW} 不应消费 R2 公网域"

    readme = _text(README)
    required = README_REQUIRED_RX.findall(readme)
    assert len(required) == 1, (
        f"desktop/README.md 的「必须显式设置」说明应恰一处，实测 "
        f"{len(required)} 处——W31a 语料守卫"
    )

    script = _text(SCRIPT)
    assert 'add_argument("--public-base-url", required=True)' in script, (
        "publish_r2_release.py 的 --public-base-url 必须是 required=True"
        "——脚本层同样不允许缺省"
    )


def test_no_baked_upstream_domain() -> None:
    """W31b：发布面不得内置上游域名；两 workflow 声明逐字相同。"""
    surface = {
        name: _workflow(name) for name in PUBLISHING_WORKFLOWS
    }
    surface["desktop/README.md"] = _text(README)
    surface["desktop/scripts/publish_r2_release.py"] = _text(SCRIPT)

    baked = sorted(
        name for name, text in surface.items() if UPSTREAM_DOMAIN in text
    )
    assert not baked, (
        f"发布面仍内置上游域名 {UPSTREAM_DOMAIN}：{baked}"
        "——未设变量时会把清单 URL 发到上游站上"
    )

    declarations = {
        name: ENV_RX.findall(surface[name]) for name in PUBLISHING_WORKFLOWS
    }
    values = {name: found[0] for name, found in declarations.items() if found}
    assert len(values) == len(PUBLISHING_WORKFLOWS), (
        f"两份发布 workflow 的 R2 声明不齐：{declarations}"
    )
    assert len(set(values.values())) == 1, (
        "两份 workflow 的 R2_PUBLIC_BASE_URL 声明不同款："
        + "；".join(f"{name}={value.strip()}" for name, value in values.items())
    )