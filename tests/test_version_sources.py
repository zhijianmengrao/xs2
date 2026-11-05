"""R161：版本双源同账——pyproject ↔ web/package.json。

背景（实测，R160 §7 登记）：发版要同时改两处 ``version``——
``pyproject.toml`` ``[project].version`` 与 ``web/package.json``
``version``（前端产物打进桌面包与容器镜像）。两处此前无人对账：
``test_branding`` 只钉名字与资产来源，不钉版本；漏改一边时
「前端界面显示的版本」与「打包元数据的版本」悄悄分叉。

本文件把这条边钉住（**W 系续**：W1–W11 对账依赖的四源，W12 把
「版本」也当一份双源对账）：

- **W12 版本逐字相等**：两处 ``version`` 都是 ``X.Y.Z`` 形状
  （语料守卫）且逐字相等。

边界：不判 ``web/package-lock.json``（npm ci 自带 package.json↔lock
一致性闸门）；不判 ``[tool.*]`` 的其他版本字段；不判 git tag（发版
流程的账，RELEASE_SOP 自己管）。
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_RX = re.compile(r"^\d+\.\d+\.\d+$")


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
