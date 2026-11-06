"""R181：macOS 最低版本同账——六处声明必须逐字相等（W 系续 W20）。

背景（实测，R180 §3 登记、R181 开工复核）：Apple Silicon 候选包的最低
系统版本写在四个地方：

- ``desktop/src-tauri/tauri.macos.conf.json`` 的
  ``bundle.macOS.minimumSystemVersion``（Tauri 打进 ``Info.plist`` 的
  ``LSMinimumSystemVersion``）；
- ``desktop/scripts/verify_bundle.py`` 的 ``MINIMUM_MACOS_VERSION``
  （打包后逐字校验 ``LSMinimumSystemVersion``，并拒绝 deployment target
  高于它的 Mach-O）；
- ``.github/workflows/desktop-macos.yml`` 的
  ``MACOSX_DEPLOYMENT_TARGET``（编译期目标，决定二进制能跑在哪）；
- ``desktop/README.md`` 的 3 处（架构行 ``macOS 11.0+`` 与两条构建命令的
  ``MACOSX_DEPLOYMENT_TARGET=11.0``）。

实测共 **6 处 / 4 个文件**，当前全部是 ``11.0``。改最低版本时漏改
``verify_bundle``，正确的 bundle 会被自己的判据判失败；漏改 workflow，
构建目标仍是旧系统；漏改 README，文档与产物失真。desktop-macos
workflow 只在 ``desktop/**`` 变更时触发（本文件与纯文档改动都不会让它
运行），这条边没有 CI 会咬住。

W20 把这条边钉成两半：

- **W20a 语料守卫**：四个源各自解析出预期条数（tauri / verify_bundle /
  workflow 各 1 处，README 恰 3 处），合计 6 处；全部是 ``X.Y`` 形状。
- **W20b 同账**：六个值逐字相等。

边界：只判「最低版本声明」——不判 macOS SDK / runner 版本、不判
``desktop/scripts/install_macos_build_dependencies.py`` 的
``macosx_11_0_arm64`` wheel 平台标签（它是二进制兼容标签，低版本 wheel
可以装在高版本系统上，不需要随应用下限同步）与同文件的说明文字；不判
``tauri.conf.json`` 的其它键、不判 ``README.md`` 之外的文档。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_MACOS_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.macos.conf.json"
VERIFY_BUNDLE = REPO_ROOT / "desktop" / "scripts" / "verify_bundle.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
README = REPO_ROOT / "desktop" / "README.md"

VERSION_RX = re.compile(r"^(\d+\.\d+)$")
README_ARCH_RX = re.compile(r"macOS\s+(\d+\.\d+)\+")
README_TARGET_RX = re.compile(r"MACOSX_DEPLOYMENT_TARGET=(\d+\.\d+)")
WORKFLOW_TARGET_RX = re.compile(
    r"MACOSX_DEPLOYMENT_TARGET:\s*[\"']?(\d+\.\d+)[\"']?"
)
VERIFY_CONSTANT_RX = re.compile(
    r"^MINIMUM_MACOS_VERSION\s*=\s*[\"'](\d+\.\d+)[\"']\s*$", re.M
)

# 登记口径：四源 1/1/1/3，合计 6 处。README 恰 3 处是语料守卫的一部分：
# 删掉任一条构建命令都会让 W20a 红，而不是让同账判据静默少看一处。
EXPECTED_COUNTS = {
    "tauri.macos.conf.json": 1,
    "verify_bundle.py": 1,
    "desktop-macos.yml": 1,
    "desktop/README.md": 3,
}
EXPECTED_TOTAL = 6


def _tauri_minimum() -> list[str]:
    document = json.loads(TAURI_MACOS_CONF.read_text(encoding="utf-8"))
    value = document.get("bundle", {}).get("macOS", {}).get("minimumSystemVersion")
    assert isinstance(value, str) and value, (
        "tauri.macos.conf.json 缺少 bundle.macOS.minimumSystemVersion"
        "——W20 无锚"
    )
    return [value]


def _verify_minimum() -> list[str]:
    text = VERIFY_BUNDLE.read_text(encoding="utf-8")
    return VERIFY_CONSTANT_RX.findall(text)


def _workflow_targets() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return WORKFLOW_TARGET_RX.findall(text)


def _readme_versions() -> list[str]:
    text = README.read_text(encoding="utf-8")
    arch = README_ARCH_RX.findall(text)
    targets = README_TARGET_RX.findall(text)
    assert len(arch) == 1, (
        f"desktop/README.md 的架构行应恰有一处「macOS X.Y+」，实测 {arch}"
    )
    assert len(targets) == 2, (
        "desktop/README.md 的两条构建命令应恰好各有一处 "
        f"MACOSX_DEPLOYMENT_TARGET=X.Y，实测 {targets}"
    )
    return arch + targets


def _sources() -> dict[str, list[str]]:
    return {
        "tauri.macos.conf.json": _tauri_minimum(),
        "verify_bundle.py": _verify_minimum(),
        "desktop-macos.yml": _workflow_targets(),
        "desktop/README.md": _readme_versions(),
    }


def test_macos_minimum_version_sources_are_parseable() -> None:
    """W20a：四个源各自解析出登记的条数，全部是 X.Y 形状。"""
    sources = _sources()
    short = [
        f"{name}: {len(values)} 处（预期 {EXPECTED_COUNTS[name]} 处）"
        for name, values in sources.items()
        if len(values) != EXPECTED_COUNTS[name]
    ]
    assert not short, (
        "macOS 最低版本声明面缩水——W20 会静默少看一处：\n" + "\n".join(short)
    )
    total = sum(len(values) for values in sources.values())
    assert total == EXPECTED_TOTAL, (
        f"四个源合计解析到 {total} 处 macOS 最低版本（预期 {EXPECTED_TOTAL} 处）"
    )
    malformed = [
        f"{name}: {value!r}"
        for name, values in sources.items()
        for value in values
        if not VERSION_RX.match(value)
    ]
    assert not malformed, (
        "macOS 最低版本必须是 X.Y 形状（本判据按字面相等对账）：\n"
        + "\n".join(malformed)
    )


def test_macos_minimum_versions_agree() -> None:
    """W20b：六个声明值逐字相等。"""
    sources = _sources()
    distinct = sorted({value for values in sources.values() for value in values})
    if len(distinct) > 1:
        detail = "\n".join(
            f"{name}: {values}" for name, values in sources.items()
        )
        raise AssertionError(
            "macOS 最低版本不同账（改下限必须同时改 "
            "tauri.macos.conf.json / verify_bundle.py / "
            "desktop-macos.yml / desktop/README.md）：\n"
            f"{detail}"
        )
    assert distinct, "四个源都没有解析出 macOS 最低版本——W20 无锚"
