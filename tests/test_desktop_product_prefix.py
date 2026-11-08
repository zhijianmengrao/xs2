"""R223：产物名前缀多源同账（W 系续 W51）。

背景（实测，R220 §3 登记）：桌面产物名的前缀 ``DeterminFlow_<version>_``
在 **7 处**出现、三份文件——replace-desktop-assets.yml 2（L77
``f'DeterminFlow_{version}_{suffix}'``、L93
``f'DeterminFlow_{version}_x64-setup.exe'``）、build_macos.py 1（L37
``f"DeterminFlow_{version}_aarch64{suffix}.dmg"``）、desktop-windows.yml
3（L175/L176 bash ``DeterminFlow_${version}_${suffix}``（含 .sha256）、
L185 ``DeterminFlow_${version}_x64-setup.exe``）。占位写法两种（bash
``${version}`` / python ``{version}``）。前缀漂移无人判：改产品名前缀
（如改名/加品牌段）只改一处，其余产物名仍旧——发版资产命名分叉，
W34 的后缀词表、W50 的安装包名都对不上。

W51 把这条边钉成两半（W32/W34/W38–W50 同型分工）：

- **W51a 语料守卫**：前缀（占位归一形状，容忍 ``_``/``-`` 连接符）
  逐份恰等（build_macos 1 / replace 2 / windows 3，合计 7）。
- **W51b 前缀同账**：占位归一（``${version}`` → ``{version}``）后
  前缀集合 == {``DeterminFlow_{version}_``}。

边界：只判 ``DeterminFlow_<version>_`` 前缀的字面同账——不判后缀
（W34 词表已管）、不判 windows L114 的 ``DeterminFlow_${version}_
${suffix}`` 变体（其连接下划线在 $suffix 内，是 PS 重命名步的另一
种组合，不进本账）、不判 ``.sig``/``.sha256`` 派生名、不判执行行为
（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# 语料守卫：每份文件的 DeterminFlow_<version>[_-] 前缀出现数。
EXPECTED_COUNTS: dict[Path, int] = {
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml": 3,
    REPO_ROOT / "desktop" / "scripts" / "build_macos.py": 1,
    REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml": 3,
}
# 形状值无关：容忍 _/- 连接符（变体进形状，值由 W51b 同账）。
PREFIX_RX = re.compile(r"DeterminFlow_(\$\{version\}|\{version\})([_-])")
BASH_PLACEHOLDER_RX = re.compile(r"\$\{(\w+)\}")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(prefix: str) -> str:
    """bash 的 ``${version}`` 归一成 python 的 ``{version}``。"""
    return BASH_PLACEHOLDER_RX.sub(r"{\1}", prefix)


def test_product_prefix_counts() -> None:
    """W51a：前缀出现数逐份恰等（1/2/3，合计 7）。"""
    for path, expected in EXPECTED_COUNTS.items():
        found = PREFIX_RX.findall(_text(path))
        assert len(found) == expected, (
            f"{path.name} 的产物名前缀应恰 {expected} 处，实测 "
            f"{len(found)} 处——W51a 语料守卫"
        )


def test_product_prefixes_agree() -> None:
    """W51b：占位归一后前缀集合 == {DeterminFlow_{version}_}。"""
    prefixes: set[str] = set()
    for path in EXPECTED_COUNTS:
        for placeholder, connector in PREFIX_RX.findall(_text(path)):
            prefixes.add(f"DeterminFlow_{_normalize(placeholder)}{connector}")
    assert prefixes == {"DeterminFlow_{version}_"}, (
        f"产物名前缀不同账：{sorted(prefixes)}——改产品名前缀必须全部同改，"
        "否则发版资产命名分叉"
    )
