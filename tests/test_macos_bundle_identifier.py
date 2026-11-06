"""R185：macOS bundle identifier 同账——六处声明必须逐字相等（W 系续 W22）。

背景（实测，R184 §3 登记、R185 开工复核）：桌面应用的 bundle identifier
写在三个地方：

- ``desktop/src-tauri/tauri.conf.json`` 的 ``identifier``（Tauri 打进
  ``Info.plist`` 的 ``CFBundleIdentifier``，同时决定数据目录名）；
- ``desktop/scripts/verify_bundle.py`` 2 处——``CFBundleIdentifier``
  逐字校验与失败错误消息；
- ``desktop/README.md`` 3 处——Windows（``%LOCALAPPDATA%``）与 macOS
  （``Application Support``）两条数据路径 + 数据目录树根。

实测共 **6 处 / 3 个文件**，当前全部是 ``io.determinflow.desktop``。改
identifier 时漏改 ``verify_bundle`` 会把正确 bundle 判失败；漏改 README
会让用户在文档指向的路径上找不到数据目录。tests 里的
``CFBundleIdentifier`` 是 fixture 取值（跟产品走），不是声明面。

W22 把这条边钉成两半：

- **W22a 语料守卫**：三源各解析出登记条数（tauri 1 / verify_bundle 2 /
  README 3，合计 6）；README 的 3 处各自落在登记的三种上下文里；全部是
  反向域名形状。
- **W22b 逐字同账**：六个值完全相同。

边界：只判「identifier 声明」——不判 productName、不判数据目录的实际
创建行为（安装后落盘由 runtime 负责）、不判 updater 相关 URL；tests 的
fixture 取值与 ``desktop/README.md`` 之外的文档不在射程。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
VERIFY_BUNDLE = REPO_ROOT / "desktop" / "scripts" / "verify_bundle.py"
README = REPO_ROOT / "desktop" / "README.md"

VERIFY_CMP_RX = re.compile(r'CFBundleIdentifier"\)\s*!=\s*"([^"]+)"')
VERIFY_MSG_RX = re.compile(r"identifier 必须是\s+([\w.]+):")
README_TOKEN_RX = re.compile(r"\bio\.[a-z0-9-]+(?:\.[a-z0-9-]+)+")
README_WINDOWS_RX = re.compile(r"LOCALAPPDATA%\\+[^\s`；]+")
README_MACOS_RX = re.compile(r"Application Support/([^\s`；]+)")
README_TREE_ROOT_RX = re.compile(r"^([\w.]+)/$", re.M)
# 反向域名：全小写标签、点分、至少两段（io.determinflow.desktop 是三段）。
REVERSE_DOMAIN_RX = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z0-9-]+)+$")

# 登记口径：三源 1 / 2 / 3，合计 6 处。
EXPECTED_TOTAL = 6


def _tauri_identifier() -> list[str]:
    document = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    value = document.get("identifier")
    assert isinstance(value, str) and value, (
        "tauri.conf.json 缺少 identifier——W22 无锚"
    )
    return [value]


def _verify_identifiers() -> list[str]:
    text = VERIFY_BUNDLE.read_text(encoding="utf-8")
    cmp_values = VERIFY_CMP_RX.findall(text)
    msg_values = VERIFY_MSG_RX.findall(text)
    assert len(cmp_values) == 1, (
        f"verify_bundle.py 的 CFBundleIdentifier 比较应恰一处，实测 {cmp_values}"
    )
    assert len(msg_values) == 1, (
        f"verify_bundle.py 的错误消息应恰一处，实测 {msg_values}"
    )
    return cmp_values + msg_values


def _readme_identifiers() -> list[str]:
    text = README.read_text(encoding="utf-8")
    tokens = README_TOKEN_RX.findall(text)
    windows = README_WINDOWS_RX.findall(text)
    macos = README_MACOS_RX.findall(text)
    tree = README_TREE_ROOT_RX.findall(text)
    assert len(tokens) == 3, (
        f"desktop/README.md 的 identifier 引用应恰 3 处，实测 {tokens}"
        "（Windows 路径 / macOS 路径 / 目录树根各一）"
    )
    assert len(windows) == 1 and tokens[0] in windows[0], (
        f"Windows 数据路径应恰一处且带 identifier，实测 {windows}"
    )
    assert len(macos) == 1, (
        f"macOS 数据路径应恰一处，实测 {macos}"
    )
    assert len(tree) == 1 and tree[0] == tokens[0], (
        f"目录树根应恰一处且与 identifier 相同，实测 {tree}"
    )
    return tokens


def _sources() -> dict[str, list[str]]:
    return {
        "tauri.conf.json": _tauri_identifier(),
        "verify_bundle.py": _verify_identifiers(),
        "desktop/README.md": _readme_identifiers(),
    }


def test_bundle_identifier_sources_are_parseable() -> None:
    """W22a：三源各解析出登记条数，合计恰 6，全部反向域名形状。"""
    sources = _sources()
    total = sum(len(values) for values in sources.values())
    assert total == EXPECTED_TOTAL, (
        f"identifier 声明面解析到 {total} 处（预期 {EXPECTED_TOTAL} 处）——"
        "tauri 1 / verify_bundle 2 / README 3 的登记口径被破坏"
    )
    malformed = [
        f"{name}: {value!r}"
        for name, values in sources.items()
        for value in values
        if not REVERSE_DOMAIN_RX.match(value)
    ]
    assert not malformed, (
        "bundle identifier 必须是反向域名形状（本判据按字面相等对账）：\n"
        + "\n".join(malformed)
    )


def test_bundle_identifiers_agree() -> None:
    """W22b：六个声明值逐字相等。"""
    sources = _sources()
    values = [value for items in sources.values() for value in items]
    distinct = sorted(set(values))
    if len(distinct) > 1:
        detail = "\n".join(
            f"{name}: {items}" for name, items in sources.items()
        )
        raise AssertionError(
            "bundle identifier 不同账（改 identifier 必须同时改 "
            "tauri.conf.json / verify_bundle.py / desktop/README.md）：\n"
            f"{detail}"
        )
    assert distinct, "三个源都没有解析出 identifier——W22 无锚"
