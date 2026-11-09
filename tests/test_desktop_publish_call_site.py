"""R235：publish_r2_release 调用面同账（W 系续 W60）。

背景（实测，R232 §3 登记）：desktop/scripts/publish_r2_release.py 的
argparse 定义 9 个 option（--assets-dir / --version / --revision /
--notes-file / --pub-date / --bucket / --endpoint-url /
--public-base-url / --aws-binary，L196–204）；两处 call site——
desktop-windows.yml（L225，7 flags，常规发版不带 --revision）与
replace-desktop-assets.yml（L132，8 flags，补发通道带 --revision）。
调用面漂移无人判：workflow 写错 flag 字、脚本增删 option 而 call site
没跟——run 时 unrecognized arguments；两处调用面分叉（常规发版误带
--revision 覆盖不可变资产）也没人拦。

W60 把这条边钉成两半（W32/W34/W38–W59 同型分工）：

- **W60a 语料守卫**：两 workflow 各恰一处调用（合计 2）；argparse
  定义非空。
- **W60b 调用面同账**：每处 flags ⊆ argparse option 集合；两处调用面
  的对称差恰 == {--revision}（补发通道语义，W33/W43 的既有边界）。

边界：只判 flag 名的字面同账——不判取值（bucket/endpoint 等由 W30/W31
负责）、不判脚本执行行为（CI 负责）、不判 CLI 的 required/default
（argparse 自身负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
REPLACE_WF = WORKFLOWS / "replace-desktop-assets.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "publish_r2_release.py"

# 调用块：脚本路径之后的续行（`\` + 换行）序列。
CALL_RX = re.compile(
    r"desktop/scripts/publish_r2_release\.py((?:[^\\\n]|\\\r?\n)*)"
)
# 先剥命令替换 `$(…)`：`git show -s --format=…` 的 --format 不误收。
STRIP_RX = re.compile(r"\$\([^)]*\)")
FLAG_RX = re.compile(r"--[a-z][a-z0-9-]*")
ARGPARSE_RX = re.compile(r'add_argument\(\s*"(--[^"]+)"')


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _call_flags(path: Path) -> list[list[str]]:
    blocks = CALL_RX.findall(_text(path))
    return [FLAG_RX.findall(STRIP_RX.sub("", block)) for block in blocks]


def _argparse_options() -> set[str]:
    return set(ARGPARSE_RX.findall(_text(SCRIPT)))


def test_call_sites_exist() -> None:
    """W60a：两 workflow 各恰一处调用；argparse 定义非空。"""
    windows = _call_flags(WINDOWS_WF)
    replace = _call_flags(REPLACE_WF)
    assert len(windows) == 1, (
        f"desktop-windows.yml 的 publish_r2_release 调用应恰 1 处，实测 "
        f"{len(windows)} 处——W60a 语料守卫"
    )
    assert len(replace) == 1, (
        f"replace-desktop-assets.yml 的 publish_r2_release 调用应恰 1 处，"
        f"实测 {len(replace)} 处——W60a 语料守卫"
    )
    assert _argparse_options(), "脚本 argparse 定义为空——W60a 无锚"


def test_call_flags_agree() -> None:
    """W60b：flags ⊆ argparse 集合；两处调用面差集恰 == {--revision}。

    不做存在守卫（W47/W49 定式）：调用缺失/重复归 W60a 计数，这里
    遍历现有调用判值、数量不唯一时跳过差集断言。
    """
    options = _argparse_options()
    if not options:
        return
    windows = _call_flags(WINDOWS_WF)
    replace = _call_flags(REPLACE_WF)
    for name, calls in (("desktop-windows.yml", windows),
                        ("replace-desktop-assets.yml", replace)):
        for flags in calls:
            extra = sorted(set(flags) - options)
            assert not extra, (
                f"{name} 的调用 flag 不在 argparse 定义里：{extra}——"
                "run 时 unrecognized arguments"
            )
    if len(windows) != 1 or len(replace) != 1:
        return
    delta = set(windows[0]) ^ set(replace[0])
    assert delta == {"--revision"}, (
        f"两处调用面的对称差应恰 {{--revision}}（补发通道语义），实测 "
        f"{sorted(delta)}——常规发版误带 --revision 会覆盖不可变资产"
    )
