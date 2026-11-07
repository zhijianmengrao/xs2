"""R205：gh release 上传面同账（W 系续 W37）。

背景（实测，R204 §3 登记）：三份发版资产进 GitHub release 的
``gh release`` 调用共 **5 处**、两份 workflow——desktop-windows.yml 3
（``view`` 判存在 → 分支 ``upload "$RELEASE_TAG" release-assets/*
--clobber`` / ``create "$RELEASE_TAG" release-assets/*``）、
replace-desktop-assets.yml 2（``upload "$RELEASE_TAG" release-assets/*
--clobber`` 补发版资产、``edit`` 只改 notes）。两条 upload 路径与
create 分支的资产集合都是 ``release-assets/*``，upload 都带
``--clobber``（重传不炸）与 ``--repo "$GITHUB_REPOSITORY"``。

上传面漂移无人判：改资产目录（如 ``release-assets`` 改名）只改一处，
另一条 upload 或 create 分支就指向空目录——upload 静默传空集合或
create 挂一个空 release；丢 ``--clobber``，重跑发布时 ``gh release
upload`` 撞已存在的资产直接失败。

W37 把这条边钉成两半（W32/W34 同型分工）：

- **W37a 语料守卫**：``gh release`` 调用逐份计数恰等（3/2，合计 5）
  且子命令形状就位（view ×1 / upload ×2 / create ×1 / edit ×1），
  upload 处都带 ``release-assets/*``、``--clobber``、
  ``--repo "$GITHUB_REPOSITORY"``。
- **W37b 上传面同账**：两条 upload 与 create 分支的资产实参逐字恰等
  （== ``release-assets/*``）；所有 gh 调用都带 ``--repo
  "$GITHUB_REPOSITORY"``（走错仓库的调用当场红）。

边界：只判 gh 调用的字面形状——不判 release 是否真的存在/资产是否
真的传上（CI 负责）、不判 ``--verify-tag``/``--title``/``--notes-file``
的语义（edit/create 的 notes-file 面由 W36 的引用面覆盖）、不判
``$RELEASE_TAG`` 的取值。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS_WF = WORKFLOWS / "desktop-windows.yml"
REPLACE_WF = WORKFLOWS / "replace-desktop-assets.yml"

EXPECTED_COUNTS: dict[str, int] = {
    "desktop-windows.yml": 3,
    "replace-desktop-assets.yml": 2,
}
GH_CALL_RX = re.compile(r"gh release (\w+)([^\n]*)")
UPLOAD_ASSET_RX = re.compile(r'upload "\$RELEASE_TAG" ([^\s]+)')
CREATE_ASSET_RX = re.compile(r'create "\$RELEASE_TAG" ([^\s]+)')


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _calls(name: str) -> list[tuple[str, str]]:
    return GH_CALL_RX.findall(_text(WORKFLOWS / name))


def test_gh_release_call_shapes() -> None:
    """W37a：调用逐份 3/2、子命令形状就位、upload 全带 --clobber（值由 W37b 判）。"""
    for name, expected in EXPECTED_COUNTS.items():
        calls = _calls(name)
        assert len(calls) == expected, (
            f"{name} 的 gh release 调用应恰 {expected} 处，实测 "
            f"{len(calls)} 处——W37a 语料守卫"
        )
    windows = _calls("desktop-windows.yml")
    replace = _calls("replace-desktop-assets.yml")
    subs = [sub for sub, _ in windows + replace]
    assert sorted(subs) == ["create", "edit", "upload", "upload", "view"], (
        f"gh release 子命令形状漂移：{sorted(subs)}——W37a 语料守卫"
    )
    for sub, rest in windows + replace:
        if sub != "upload":
            continue
        assert "--clobber" in rest, (
            f"gh release upload 缺 --clobber（重跑发布会撞已存在资产）："
            f"{rest.strip()!r}——W37a 语料守卫"
        )


def _upload_assets() -> list[str]:
    assets = []
    for name in EXPECTED_COUNTS:
        text = _text(WORKFLOWS / name)
        assets += UPLOAD_ASSET_RX.findall(text)
    return assets


def test_upload_faces_agree() -> None:
    """W37b：upload/create 的资产实参逐字恰等（== release-assets/*）。"""
    assets = _upload_assets()
    assert len(assets) == 2, f"upload 锚应恰 2 处，实测 {len(assets)} 处"
    windows_text = _text(WINDOWS_WF)
    for name, sub, rest in [
        (name, sub, rest)
        for name in EXPECTED_COUNTS
        for sub, rest in _calls(name)
        if sub != "create"
    ]:
        assert '--repo "$GITHUB_REPOSITORY"' in rest, (
            f"{name} 的 gh release {sub} 缺 --repo "
            "\"$GITHUB_REPOSITORY\"——W37b 同账（走错仓库的调用当场红）"
        )
    creates = CREATE_ASSET_RX.findall(windows_text)
    assert len(creates) == 1, (
        f"gh release create 的资产实参应恰一处，实测 {len(creates)} 处"
    )
    create_at = windows_text.index('gh release create "$RELEASE_TAG"')
    create_block = windows_text[create_at:create_at + 400]
    assert '--repo "$GITHUB_REPOSITORY"' in create_block, (
        "gh release create 块（含续行）缺 --repo "
        "\"$GITHUB_REPOSITORY\"——W37b 同账"
    )
    account = set(assets) | set(creates)
    assert account == {"release-assets/*"}, (
        f"gh release 资产实参不同账：{sorted(account)}——改资产目录必须"
        "upload×2 与 create 分支同改，否则一条路径传空集合"
    )
