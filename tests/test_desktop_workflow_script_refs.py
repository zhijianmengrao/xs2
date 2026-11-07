"""R198：desktop workflow 脚本引用路径逐处可解析（W 系续 W32）。

背景（实测，R196 §3 登记）：三份 desktop workflow 共 **17 处**
``desktop/scripts/*`` 引用 / **9 个不同脚本**（desktop-windows.yml 8：
refresh_official_plugin_lock / build_backend / smoke_backend /
verify_bundle ×2 / smoke_installer.ps1 / create_update_manifest /
publish_r2_release；desktop-macos.yml 8：install_macos_build_dependencies
/ refresh_official_plugin_lock / build_backend / smoke_backend ×3 /
generate_macos_icon / verify_bundle；replace-desktop-assets.yml 1：
publish_r2_release）——登记时全部在磁盘。V8 管的是 README 侧命令引用
面，workflow 侧此前没有锚：脚本改名/挪走时 CI 在 run 时才炸（一次推送
把 desktop-*.yml 引用的脚本重命名，三个分发工作流一起红在远端，且
只有发版时才走到那一步）。

W32 把这条边钉成两半：

- **W32a 语料守卫**：三份 workflow 的 ``desktop/scripts/*`` 引用数
  逐份恰等（8 / 8 / 1，合计 17）——加引用、删引用都先红语料守卫，
  强迫把新引用并进这份账。
- **W32b 逐处可解析**：17 处引用逐处按仓库根解析后必须在磁盘
  （``Path.is_file()``）——脚本改名/挪走而 workflow 没跟显式红，
  不等 CI run 时才炸。

边界：只判 ``desktop/scripts/`` 形状的字面引用——不判脚本内容、不判
step 的执行行为（CI 负责）、不判 README 侧命令引用面（V8 已管）、
``ci.yml`` 实测 0 处引用（非桌面分发面，不进账）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
# 语料守卫：每份 workflow 的 desktop/scripts/* 引用数（R198 实测 8/8/1）。
EXPECTED_REFS: dict[str, int] = {
    "desktop-windows.yml": 8,
    "desktop-macos.yml": 8,
    "replace-desktop-assets.yml": 1,
}
REF_RX = re.compile(r"desktop/scripts/[A-Za-z0-9_.\-]+")


def _references(name: str) -> list[str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return REF_RX.findall(text)


def test_workflow_script_reference_counts() -> None:
    """W32a：三份 workflow 的 desktop/scripts/* 引用数逐份恰等 8/8/1。"""
    for name, expected in EXPECTED_REFS.items():
        refs = _references(name)
        assert len(refs) == expected, (
            f"{name} 的 desktop/scripts/* 引用应恰 {expected} 处，实测 "
            f"{len(refs)} 处（{sorted(set(refs))}）——W32a 语料守卫："
            "加/删引用必须同步更新这份账"
        )
    total = sum(len(_references(name)) for name in EXPECTED_REFS)
    assert total == 17, f"三份 workflow 合计应 17 处，实测 {total} 处"


def test_every_workflow_script_reference_resolves() -> None:
    """W32b：17 处引用逐处按仓库根解析后在磁盘。"""
    missing: list[str] = []
    for name in EXPECTED_REFS:
        for ref in _references(name):
            if not (REPO_ROOT / ref).is_file():
                missing.append(f"{name} -> {ref}")
    assert not missing, (
        "workflow 引用的脚本解析不到：" + "；".join(missing)
        + "——脚本改名/挪走时 desktop workflow 的引用要同改，"
        "否则 CI 到 run 时才炸"
    )
