"""R206：verify_bundle 调用面参数同账（W 系续 W38）。

背景（实测，R204 §3 登记）：``desktop/scripts/verify_bundle.py`` 被
desktop workflow 调用 **3 处**，flag 家族随平台/阶段不同——

- desktop-macos.yml 恰 1 处（7 flag：``--expected-flavor`` +
  ``--app-bundle`` + ``--dmg`` + ``--verify-macos-load-commands`` +
  ``--verify-macos-signatures`` + ``--verify-dmg-container``）；
- desktop-windows.yml 恰 2 处（构建后核验 1 flag
  ``--expected-flavor``；发布前核验 3 flag ``--desktop-executable`` +
  ``--installer`` + ``--updater-signature``）。

脚本 argparse 定义 10 个 option。调用面漂移无人判：workflow 里的
flag 写错字（或脚本改名 option 而 workflow 没跟），CI 到 run 时才炸
——argparse 直接 ``unrecognized arguments`` 退非零，且炸在发版路径
深处。W32 管的是脚本**路径**可解析，这里把面推进到 **flag** 可解析。

W38 把这条边钉成两半（W32/W34 同型分工）：

- **W38a 语料守卫**：三处 call site 各恰一处（macos 1 / windows 2）、
  每处 flag 数语料守卫（7/1/3）——加/删 flag 先红语料守卫。
- **W38b 调用面同账**：三处 call site 用到的每个 flag ∈ 脚本
  argparse 的 option 集合（单向：定义未被调用的 option 是脚本 API，
  不判；调用未定义的 flag 当场红）。

边界：只判 flag 名的字面可解析——不判 flag 取值（``--expected-flavor``
choices 由 W29 钉）、不判 flag 顺序与折行写法、不判脚本执行行为
（CI 负责）、不判 ``--forbid-updater-artifacts`` 等 workflow 侧未用
option（脚本 API 面不收缩）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "verify_bundle.py"
CALL_SITES: dict[str, int] = {
    "desktop-macos.yml": 1,
    "desktop-windows.yml": 2,
}
EXPECTED_FLAG_COUNTS: dict[str, list[int]] = {
    "desktop-macos.yml": [7],
    "desktop-windows.yml": [1, 3],
}
CALL_RX = re.compile(
    r"desktop/scripts/verify_bundle\.py((?:[^\\\n]|\\\r?\n)*)"
)
FLAG_RX = re.compile(r"(--[a-z][a-z0-9-]*)")
ARGPARSE_RX = re.compile(r'add_argument\(\s*"(--[^"]+)"')


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _call_blocks(name: str) -> list[str]:
    """每个 call site 的完整逻辑行（含反斜杠续行）。"""
    return CALL_RX.findall(_text(WORKFLOWS / name))


def _argparse_options() -> set[str]:
    return set(ARGPARSE_RX.findall(_text(SCRIPT)))


def test_verify_bundle_call_site_shapes() -> None:
    """W38a：三处 call site 各恰一处、每处 flag 数恰等 7/1/3。"""
    for name, expected in CALL_SITES.items():
        blocks = _call_blocks(name)
        assert len(blocks) == expected, (
            f"{name} 的 verify_bundle call site 应恰 {expected} 处，实测 "
            f"{len(blocks)} 处——W38a 语料守卫"
        )
    for name, counts in EXPECTED_FLAG_COUNTS.items():
        actual = [len(FLAG_RX.findall(block)) for block in _call_blocks(name)]
        assert actual == counts, (
            f"{name} 的 verify_bundle call site flag 数应恰 {counts}，"
            f"实测 {actual}——W38a 语料守卫（加/删 flag 先红这里）"
        )


def test_verify_bundle_flags_resolve() -> None:
    """W38b：三处 call site 的每个 flag ∈ 脚本 argparse option 集合。"""
    defined = _argparse_options()
    assert "--expected-flavor" in defined and "--installer" in defined, (
        "argparse 提取失真——W38b 无锚"
    )
    unknown: list[str] = []
    for name in CALL_SITES:
        for block in _call_blocks(name):
            for flag in FLAG_RX.findall(block):
                if flag not in defined:
                    unknown.append(f"{name}: {flag}")
    assert not unknown, (
        "verify_bundle 调用面用了脚本未定义的 flag：" + "；".join(unknown)
        + "——脚本改名 option 时三处 call site 必须同改，否则 CI 到 run "
        "时才 unrecognized arguments"
    )
