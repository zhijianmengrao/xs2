"""R225：community-updates 当前正式版同账（W 系续 W52）。

背景（实测，R224 §3 登记）：``docs/community-updates.md`` 的
「当前正式版」叙述引用 ``v1.1.1``（另有 v1.1.0 的历史链接，W36 已钉
两处可解析），而 ``desktop/release-notes/`` 目录现有 13 个版本文件、
最高 ``v1.1.1.md``。「当前正式版」是发版叙事的门面账：新日志入库
（如 v1.2.0.md）而叙述没跟——读者看到的还是旧版；或叙述写到尚未
入库的版本——点开 404（W36 抓后者，但只对「引用的都在盘」，不判
「最高引用 == 目录最高」）。

W52 把「当前正式版」钉成同账：

- **W52a 语料守卫**：release-notes 目录至少一个版本文件（形状
  ``v<数字.数字…>.md``）；community-updates 至少一处版本引用。
- **W52b 最高版本同账**：community-updates 引用的最高版本 ==
  release-notes 目录的最高版本文件（版本按数字段比较，不是字符串）。

边界：只判最高版本的同账——不判目录里的历史文件是否都被引用（旧
日志无需叙述）、不判日志内容、不判 tag 与日志的对应（发版流程负责）、
不判 v1.0.10 这类字符串排序陷阱（按数字段比较正是为了它）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMMUNITY = REPO_ROOT / "docs" / "community-updates.md"
NOTES_DIR = REPO_ROOT / "desktop" / "release-notes"

VERSION_RX = re.compile(r"v(\d+(?:\.\d+)+)")
COMMUNITY_LINK_RX = re.compile(r"\.\./desktop/release-notes/(v[\d.]+)\.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _version_key(version: str) -> tuple[int, ...]:
    """v1.1.1 → (1, 1, 1)：按数字段比较，避免 v1.0.10 < v1.0.9 的字符串陷阱。"""
    return tuple(int(part) for part in version[1:].split("."))


def _dir_versions() -> list[str]:
    files = sorted(NOTES_DIR.glob("v*.md"))
    assert files, "desktop/release-notes/ 没有版本文件——W52a 无锚"
    versions = []
    for path in files:
        match = VERSION_RX.fullmatch(path.stem)
        assert match, f"release-notes 文件名形状意外：{path.name}——W52a 无锚"
        versions.append(match.group(0))
    return versions


def _referenced_versions() -> list[str]:
    refs = COMMUNITY_LINK_RX.findall(_text(COMMUNITY))
    assert refs, "community-updates 没有版本引用——W52a 无锚"
    for ref in refs:
        assert VERSION_RX.fullmatch(ref), (
            f"community-updates 引用形状意外：{ref!r}——W52a 无锚"
        )
    return refs


def test_release_notes_inventory() -> None:
    """W52a：目录有版本文件（形状 v<数字段>.md）；community 至少一处引用。"""
    assert len(_dir_versions()) >= 1
    assert len(_referenced_versions()) >= 1


def test_current_release_version_agrees() -> None:
    """W52b：引用的最高版本 == 目录的最高版本文件（按数字段比较）。"""
    dir_max = max(_version_key(v) for v in _dir_versions())
    ref_max = max(_version_key(v) for v in _referenced_versions())
    assert ref_max == dir_max, (
        f"community-updates 的当前正式版与 release-notes 不同账：引用最高 "
        f"v{'.'.join(map(str, ref_max))}，目录最高 "
        f"v{'.'.join(map(str, dir_max))}——新日志入库时叙述要同改"
    )
