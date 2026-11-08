"""R221：verify 调用第三段同账（W 系续 W49）。

背景（实测，R220 §3 登记）：desktop-macos.yml 的 verify_bundle 调用
有三段路径：``--app-bundle`` 与 ``--dmg``（W44 已钉）+ ``--forbid-
updater-artifacts desktop/src-tauri/target/release/bundle``（L65，
禁 updater 资产混入 bundle 根）。第三段取值 == build_macos.py 的
bundle 组合前缀（``desktop/src-tauri/target/release/bundle``）——
同一次 verify 调用里的第三份路径账。漂移无人判：bundle 根挪目录只改
--app-bundle/--dmg 而漏 forbid（W44 的两段同账不覆盖它），updater
资产的禁入检查指向旧根——核验通过但检查的范围错了。

W49 把第三段钉进 W44 的账（W44 的提取逻辑复用，本文件自带同款
正则——判据文件彼此独立不互相 import）：

- **W49a 语料守卫**：yml 的 ``--forbid-updater-artifacts`` 取值恰
  一处；脚本 bundle 组合行恰一处。
- **W49b 第三段同账**：forbid 取值 == 脚本拼出的 bundle 前缀。

边界：只判 forbid 取值与脚本 bundle 前缀的字面同账——不判
--app-bundle/--dmg（W44 已管）、不判 forbid 的语义（哪些文件算
updater 资产是 verify_bundle 自己的逻辑）、不判执行行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MACOS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "build_macos.py"

BUNDLE_RX = re.compile(
    r'bundle\s*=\s*desktop\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"\s*/\s*"([^"]+)"'
    r'\s*/\s*"([^"]+)"'
)
FORBID_RX = re.compile(r"--forbid-updater-artifacts\s+(\S+)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_bundle_prefix() -> str:
    text = _text(SCRIPT)
    bundle = BUNDLE_RX.findall(text)
    assert len(bundle) == 1, (
        f"build_macos.py 的 bundle 组合行应恰一处，实测 {len(bundle)} 处"
        "——W49a 语料守卫"
    )
    return "desktop/" + "/".join(bundle[0])


def test_forbid_anchor_counts() -> None:
    """W49a：yml --forbid-updater-artifacts 恰一处；脚本组合行恰一处。"""
    _script_bundle_prefix()
    values = FORBID_RX.findall(_text(MACOS_WF))
    assert len(values) == 1, (
        f"desktop-macos.yml 的 --forbid-updater-artifacts 应恰一处，实测 "
        f"{len(values)} 处——W49a 语料守卫"
    )


def test_forbid_value_agrees_with_bundle_prefix() -> None:
    """W49b：forbid 取值 == 脚本拼出的 bundle 前缀（存在才判，缺失归 W49a）。"""
    prefix = _script_bundle_prefix()
    for value in FORBID_RX.findall(_text(MACOS_WF)):
        assert value == prefix, (
            f"--forbid-updater-artifacts 取值不同账：yml {value!r} vs 脚本 "
            f"bundle 前缀 {prefix!r}——bundle 根挪目录三段（app-bundle/dmg/"
            "forbid）都要同改"
        )
