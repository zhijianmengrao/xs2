"""R199：README R2 发行路径 ↔ publish_r2_release.py 两段同账（W 系续 W33）。

背景（实测，R196 §3 登记）：desktop/README.md「桌面更新发布」节写
「先上传并公开校验 ``desktop/releases/vX/`` 下的不可变资产，最后更新
``desktop/stable/latest.json``」；脚本 ``publish_r2_release.py`` 的
``version_prefix = f"desktop/releases/v{version}"`` 与
``publish_latest(manifest_path, "desktop/stable/latest.json")`` 是同一
份账的实现侧——README 的 ``vX`` 形状对脚本的 ``v{version}`` 前缀、
稳定清单键。两段路径（发行目录前缀 + 稳定键）任何一段单侧漂移，
发布物落在新位置而 README 指着旧位置：按文档核对发版的人校验不到
新键，稳定通道的消费者拿不到更新——静默分叉。

W33 把这条边钉成两半：

- **W33a 语料守卫**：README 的 ``…/vX/`` 发行前缀 token 与「最后更新
  `<stable>`」句各恰一处（``vX`` 形状钉在提取正则里）；脚本的
  ``version_prefix`` 定义与 ``publish_latest`` 稳定键实参各恰一处。
- **W33b 两段同账**：发行目录前缀（README token 去掉 ``/vX/`` ==
  脚本 f-string 去掉 ``/v{version}``）与稳定清单键逐字恰等——改目录/
  改键名单侧漂移显式红。

边界：只判两段路径的字面同账——不判发布行为与不可变校验（CI 与
脚本自身的判据面负责）、不判 ``latest.json`` 内容结构、不判
``publish_immutable`` 的逐资产键（``{version_prefix}/latest.json``
由同一前缀推出，前缀同账即覆盖）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "publish_r2_release.py"

# README 侧：反引号 token 形状（版本占位 vX 由提取正则钉住）。
README_RELEASE_RX = re.compile(r"`([^`]+?)/vX/`")
README_STABLE_RX = re.compile(r"最后更新 `([^`]+)`")
# 脚本侧：version_prefix 定义行与 publish_latest 的稳定键实参。
VERSION_PREFIX_RX = re.compile(r'version_prefix\s*=\s*f"([^"]+)"')
PUBLISH_LATEST_RX = re.compile(r'publish_latest\([^,]+,\s*"([^"]+)"\)')


def test_release_path_anchors_are_unique() -> None:
    """W33a：README 两段 token 与脚本两处定义各恰一处（v 形状钉在提取正则里）。"""
    readme = README.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    release = README_RELEASE_RX.findall(readme)
    assert len(release) == 1, (
        f"desktop/README.md 的 `…/vX/` 发行前缀 token 应恰一处，实测 "
        f"{len(release)} 处——W33a 语料守卫（vX 形状由提取正则钉住）"
    )
    stable = README_STABLE_RX.findall(readme)
    assert len(stable) == 1, (
        f"desktop/README.md 的「最后更新 `<stable>`」应恰一处，实测 "
        f"{len(stable)} 处——W33a 语料守卫"
    )
    prefix = VERSION_PREFIX_RX.findall(script)
    assert len(prefix) == 1, (
        f"publish_r2_release.py 的 version_prefix 定义应恰一处，实测 "
        f"{len(prefix)} 处——W33a 语料守卫"
    )
    latest = PUBLISH_LATEST_RX.findall(script)
    assert len(latest) == 1, (
        f"publish_r2_release.py 的 publish_latest 稳定键实参应恰一处，"
        f"实测 {len(latest)} 处——W33a 语料守卫"
    )


def test_release_path_segments_agree() -> None:
    """W33b：发行目录前缀与稳定清单键两段逐字同账（双向）。"""
    readme = README.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    readme_dir = README_RELEASE_RX.search(readme).group(1)
    readme_stable = README_STABLE_RX.search(readme).group(1)
    prefix_value = VERSION_PREFIX_RX.search(script).group(1)
    script_stable = PUBLISH_LATEST_RX.search(script).group(1)

    assert prefix_value.endswith("/v{version}") and len(prefix_value) > len(
        "/v{version}"
    ), (
        f"publish_r2_release.py 的 version_prefix 形状漂移：{prefix_value!r}"
        "——应为「<目录>/v{{version}}」（README 的 vX 对应脚本的 v{{version}}）"
    )
    script_dir = prefix_value[: -len("/v{version}")]
    assert readme_dir == script_dir, (
        f"R2 发行目录前缀不同账：README 写 {readme_dir!r}，脚本写 "
        f"{script_dir!r}——改目录两处必须同改"
    )
    assert readme_stable == script_stable, (
        f"稳定清单键不同账：README 写 {readme_stable!r}，脚本写 "
        f"{script_stable!r}——改键名两处必须同改"
    )
