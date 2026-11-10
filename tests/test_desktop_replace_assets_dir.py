"""R238：replace workflow 资产目录名四源同账（W 系续 W62）。

背景（实测，R236 §3 登记）：replace-desktop-assets.yml 里「发版资产的
暂存目录」字面 ``release-assets`` 出现在四处、四个不同来源：

- ``mkdir -p release-assets``（L36，shell 建目录）；
- ``'--dir', 'release-assets'``（L58，gh run download 的下载目录）；
- ``Path('release-assets')``（L71，清单脚本读取资产目录）；
- ``--assets-dir release-assets``（L133，publish_r2_release 的实参）。

W37 只钉 gh release upload 的 ``release-assets/*`` 实参，不钉这四源。
四处漂移无人判：下载目录与清单读取目录分叉 → 发版资产校验/清单生成
失败；或 R2 发布拿到空目录 → 上传半套产物。

W62 把这条边钉成两半（W57/W58/W61 同型分工）：

- **W62a 语料守卫**：四种来源形状各恰 1 处（mkdir -p / '--dir' /
  Path('…') / --assets-dir）。
- **W62b 四源逐字恰等**：四源提取值的并集 == {release-assets}——
  任何一处漂移都红。

边界：只判目录名的字面同账——不判目录内文件（expected 集合由
release 步脚本自校验）、不判 gh/publish_r2_release 行为（CI 负责）、
不判 build-runs.json 等其余路径字面。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)

# 四源提取形状（各恰 1 处）。
MKDIR_RX = re.compile(r"mkdir -p (\S+)")
DOWNLOAD_DIR_RX = re.compile(r"'--dir', '([^']+)'")
PATH_DIR_RX = re.compile(r"Path\('([a-z-]+)'\)")
ASSETS_DIR_RX = re.compile(r"--assets-dir (\S+)")

EXPECTED_DIR = "release-assets"


def _text() -> str:
    return REPLACE_WF.read_text(encoding="utf-8")


def _sources() -> dict[str, list[str]]:
    text = _text()
    return {
        "mkdir -p": MKDIR_RX.findall(text),
        "--dir": DOWNLOAD_DIR_RX.findall(text),
        "Path()": PATH_DIR_RX.findall(text),
        "--assets-dir": ASSETS_DIR_RX.findall(text),
    }


def test_asset_dir_sources_are_singletons() -> None:
    """W62a：四种来源形状各恰 1 处。"""
    for shape, values in _sources().items():
        assert len(values) == 1, (
            f"资产目录来源「{shape}」应恰 1 处，实测 {len(values)} 处"
            f"（{values}）——W62a 语料守卫"
        )


def test_asset_dir_four_sources_agree() -> None:
    """W62b：四源提取值的并集 == {release-assets}（逐字恰等）。"""
    sources = _sources()
    assert all(sources.values()), "四源提取有空洞——W62b 无锚"
    union = {v for values in sources.values() for v in values}
    assert union == {EXPECTED_DIR}, (
        f"资产目录名四源不同账：并集 {sorted(union)} != "
        f"{{{EXPECTED_DIR}}}——下载/读取/发布目录分叉会让发版资产校验、"
        "清单生成或 R2 上传失败；四源必须同改"
    )
