"""R162：许可证面同账——pyproject license ↔ LICENSE ↔ README 徽章。

背景（实测，R160 §7 登记）：授权声明有四个写入点，此前无人对账：

- ``pyproject.toml``：``license = "AGPL-3.0-only"`` +
  ``license-files = ["LICENSE"]``（打包元数据）；
- ``LICENSE``（仓库根，发布时随源码分发）；
- ``README.md`` 徽章：``badge/license-AGPL--3.0-blue`` +
  ``alt="许可证：AGPL-3.0"``；
- ``README.en.md`` 徽章：同 URL + ``alt="License: AGPL-3.0"``。

改 license 而不换 LICENSE 文件、或不改徽章时，PyPI 元数据、仓库
根文件与 README 展示各说各话。本文件把这条面钉住（**V 系续**：
V1–V3 是「引用可解析」，V4 把授权文件的引用与授权名展示收进来）：

- **V4a license-files 可解析**：``license-files`` 数组里的每个文件
  必须在磁盘（缺文件 = 打包时随源码分发清单指空）。
- **V4b 授权名同账**：pyproject license 标识符的核心 ``X.Y`` 部分
  （``AGPL-3.0-only`` → ``AGPL-3.0``）== 两份 README 徽章 alt 与
  URL 中的 ``AGPL-3.0``（shields URL 的 ``--`` 是转义，归一后比较；
  ``-only`` 后缀不进徽章是正常写法）。

边界：只判声明面——不读 LICENSE 文件内容、不校验 SPDX 合法性、
不判徽章 href 指向的上游仓库（fork 的徽章有意指 upstream，R140
V2b 同型边界）。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
READMES = (REPO_ROOT / "README.md", REPO_ROOT / "README.en.md")
BADGE_URL_RX = re.compile(r"badge/license-([A-Za-z0-9.\-]+?)-(?:blue|green|red|orange|yellow|brightgreen)")
BADGE_ALT_RX = re.compile(r'alt="[^"]*?([A-Z]{2,}-?\d\.\d)[^"]*"')
SPDX_CORE_RX = re.compile(r"^([A-Za-z0-9]+-[0-9]+\.[0-9]+)")


def _license_decl() -> tuple[str, list[str]]:
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    license_value = document["project"].get("license")
    files = document["project"].get("license-files")
    assert isinstance(license_value, str) and license_value.strip(), (
        "pyproject [project].license 不是字符串——V4 无处落锚"
    )
    assert isinstance(files, list) and files, (
        "pyproject [project].license-files 缺失或为空——V4a 空转"
    )
    return license_value, [str(f) for f in files]


def test_license_files_resolve() -> None:
    """V4a：license-files 数组里的每个文件必须在磁盘。"""
    _, files = _license_decl()
    missing = [f for f in files if not (REPO_ROOT / f).is_file()]
    assert not missing, (
        f"license-files 引用的文件不存在（打包分发清单指空）：{missing}"
    )


def test_license_badges_agree_with_pyproject() -> None:
    """V4b：README 双语徽章的授权名 == pyproject license 核心段。"""
    license_value, _ = _license_decl()
    core = SPDX_CORE_RX.match(license_value)
    assert core, (
        f"pyproject license 无法解析出 X.Y 核心段：{license_value!r}"
    )
    expected = core.group(1)
    violations = []
    for path in READMES:
        text = path.read_text(encoding="utf-8-sig")
        urls = {m.group(1).replace("--", "-") for m in BADGE_URL_RX.finditer(text)}
        alts = {m.group(1) for m in BADGE_ALT_RX.finditer(text)}
        assert len(urls) == 1, (
            f"{path.name} 的 license 徽章 URL 应恰好解析出一个授权名，"
            f"实际 {sorted(urls)}"
        )
        assert len(alts) == 1, (
            f"{path.name} 的 license 徽章 alt 应恰好解析出一个授权名，"
            f"实际 {sorted(alts)}"
        )
        for where, got in [("URL", urls.pop()), ("alt", alts.pop())]:
            if got != expected:
                violations.append(
                    f"{path.name}: 徽章 {where} 写 {got}，pyproject "
                    f"license 是 {license_value}"
                )
    assert not violations, (
        "README 授权徽章与 pyproject license 不同账：\n"
        + "\n".join(violations)
    )
