"""R161 / R175：版本同账——核心版本双源（W12）与桌面版本五源（W18）。

背景（实测，R160 §7 登记）：发版要同时改两处 ``version``——
``pyproject.toml`` ``[project].version`` 与 ``web/package.json``
``version``（前端产物打进桌面包与容器镜像）。两处此前无人对账：
``test_branding`` 只钉名字与资产来源，不钉版本；漏改一边时
「前端界面显示的版本」与「打包元数据的版本」悄悄分叉。

R175 把桌面发布版本线（与核心 0.1.0 独立的 1.0.x）也收进来：R172 §3
登记时只数到 ``desktop/package.json`` 与 ``tauri.conf.json`` 两处，
开工实测按 ``docs/RELEASE_SOP.md`` §1 的六处清单补齐——五份真实清单
（tauri / package / Cargo.toml / Cargo.lock / official-plugins.lock）
外加一处发版钉值测试：

- **W12 版本逐字相等**：pyproject 与 web/package.json 两处 ``version``
  都是 ``X.Y.Z`` 形状（语料守卫）且逐字相等。
- **W18a 语料守卫**：五份桌面版本清单都能解析出 ``X.Y.Z`` 形状的版本；
  ``RELEASE_SOP`` §1 的清单必须恰好是这五份文件 + 发版钉值测试。
- **W18b 五源同账**：五份清单的版本逐字相等（锚 = tauri.conf.json）。

边界：不判 ``web/package-lock.json``（npm ci 自带 package.json↔lock
一致性闸门）；不判 ``[tool.*]`` 的其他版本字段；不判 git tag（发版
流程的账，RELEASE_SOP 自己管）；不判桌面版本与核心版本相等（两条
独立版本线）。
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_RX = re.compile(r"^\d+\.\d+\.\d+$")

DESKTOP_DIR = REPO_ROOT / "desktop"
TAURI_CONF = DESKTOP_DIR / "src-tauri" / "tauri.conf.json"
DESKTOP_PACKAGE = DESKTOP_DIR / "package.json"
CARGO_TOML = DESKTOP_DIR / "src-tauri" / "Cargo.toml"
CARGO_LOCK = DESKTOP_DIR / "src-tauri" / "Cargo.lock"
OFFICIAL_PLUGIN_LOCK = DESKTOP_DIR / "official-plugins.lock.json"
RELEASE_SOP = REPO_ROOT / "docs" / "RELEASE_SOP.md"

# RELEASE_SOP §1 的「版本号统一（六处）」清单：五份真实清单 + 发版钉值测试。
SOP_VERSION_PATHS = (
    "desktop/src-tauri/tauri.conf.json",
    "desktop/src-tauri/Cargo.toml",
    "desktop/src-tauri/Cargo.lock",
    "desktop/package.json",
    "desktop/official-plugins.lock.json",
    "tests/test_desktop_packaging.py",
)
SOP_TABLE_ROW_RX = re.compile(r"^\|\s*`([^`]+)`\s*\|", re.M)


def _pyproject_version() -> str:
    document = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    version = document["project"].get("version")
    assert isinstance(version, str) and VERSION_RX.match(version), (
        f"pyproject [project].version 不是 X.Y.Z 形状：{version!r}"
    )
    return version


def _web_version() -> str:
    document = json.loads(
        (REPO_ROOT / "web" / "package.json").read_text(encoding="utf-8")
    )
    version = document.get("version")
    assert isinstance(version, str) and VERSION_RX.match(version), (
        f"web/package.json version 不是 X.Y.Z 形状：{version!r}"
    )
    return version


def test_version_sources_agree() -> None:
    """pyproject 与 web/package.json 的 version 必须逐字相等（R161）。"""
    pyproject = _pyproject_version()
    web = _web_version()
    assert pyproject == web, (
        f"版本双源漂移：pyproject=={pyproject}，web/package.json=={web}"
        "——发版时两处必须同改"
    )


def _json_version(path: Path, key: str = "version") -> object:
    document = json.loads(path.read_text(encoding="utf-8"))
    return document.get(key)


def _toml_package_version(path: Path) -> object:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    package = document.get("package")
    return package.get("version") if isinstance(package, dict) else None


def _cargo_lock_version() -> object:
    document = tomllib.loads(CARGO_LOCK.read_text(encoding="utf-8"))
    packages = [
        entry
        for entry in document.get("package", [])
        if entry.get("name") == "determinflow-desktop"
    ]
    assert len(packages) == 1, (
        "desktop/src-tauri/Cargo.lock 的 determinflow-desktop 条目应恰一处，"
        f"实际 {len(packages)} 处——W18 的锚唯一性失守"
    )
    return packages[0].get("version")


def _desktop_versions() -> dict[str, object]:
    return {
        "desktop/src-tauri/tauri.conf.json": _json_version(TAURI_CONF),
        "desktop/package.json": _json_version(DESKTOP_PACKAGE),
        "desktop/src-tauri/Cargo.toml": _toml_package_version(CARGO_TOML),
        "desktop/src-tauri/Cargo.lock": _cargo_lock_version(),
        "desktop/official-plugins.lock.json": _json_version(
            OFFICIAL_PLUGIN_LOCK, key="desktop_version"
        ),
    }


def _sop_version_section() -> str:
    text = RELEASE_SOP.read_text(encoding="utf-8")
    assert "## 1." in text and "## 2." in text, (
        "docs/RELEASE_SOP.md 的 §1/§2 标题被改名——W18a 的语料锚失守"
    )
    return text.split("## 1.", 1)[1].split("## 2.", 1)[0]


def test_desktop_version_sources_are_parseable() -> None:
    """W18a：五份桌面版本清单都是 X.Y.Z，且 SOP §1 恰好列出这六处。"""
    versions = _desktop_versions()
    invalid = [
        f"{relative} 的 version={value!r}"
        for relative, value in versions.items()
        if not (isinstance(value, str) and VERSION_RX.match(value))
    ]
    assert not invalid, (
        "desktop 版本源不是 X.Y.Z 形状：\n" + "\n".join(invalid)
    )

    listed = set(SOP_TABLE_ROW_RX.findall(_sop_version_section()))
    assert listed == set(SOP_VERSION_PATHS), (
        "RELEASE_SOP §1 的版本清单与实际版本源不同账："
        f"表里 {sorted(listed)}，实际 {sorted(SOP_VERSION_PATHS)}"
        "——新增/删除版本文件时两边必须同改"
    )


def test_desktop_version_sources_agree() -> None:
    """W18b：五份桌面版本清单逐字相等（锚 = tauri.conf.json）。"""
    versions = _desktop_versions()
    anchor_relative = "desktop/src-tauri/tauri.conf.json"
    anchor = versions[anchor_relative]
    violations = [
        f"{relative} 写 {value!r}，{anchor_relative} 写 {anchor!r}"
        for relative, value in versions.items()
        if value != anchor
    ]
    assert not violations, (
        "desktop 版本五源漂移：\n" + "\n".join(violations)
    )
