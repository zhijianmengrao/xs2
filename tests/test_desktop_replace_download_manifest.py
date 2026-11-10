"""R239：replace 下载清单 ↔ 两 producer artifact 名同账（W 系续 W63）。

背景（实测，R236 §3 登记）：replace-desktop-assets.yml 的 provenance
heredoc 用两个字面清单声明要从构建 run 下载的 artifact 名
（windows: ``DeterminFlow-Windows-x64-{core,full}``；macos:
``DeterminFlow-macOS-arm64-{core,full}-adhoc-candidate``），对面是两个
producer workflow 的上传名模板：desktop-windows.yml 的
``DeterminFlow-Windows-x64-${{ matrix.flavor }}``（matrix 为块式列表
``- core`` / ``- full``）与 desktop-macos.yml 的
``DeterminFlow-macOS-arm64-${{ matrix.flavor }}-adhoc-candidate``
（matrix 内联 ``[core, full]``）。消费与生产漂移无人判（
test_desktop_packaging 只钉模板单源，不与 replace 的清单对账）：matrix
增 flavor 或改名而 replace 没跟 → 应急通道 ``gh run download --name``
失败；replace 清单改名而 workflow 没跟，同样失败。

W63 把这条边钉成两半（W58/W59/W60/W61 同型分工）：

- **W63a 语料守卫**：replace 恰两份平台清单、各恰 2 个条目；两个
  producer 各恰 1 个 artifact 名模板、恰 1 份 flavor matrix、每份恰
  2 个 flavor。
- **W63b 展开双向恰等**：模板按各自 matrix 展开后的集合 == 对应平台
  的消费清单集合（谁多谁少都红）。

边界：只判 artifact 名的字面同账——不判 artifact 内容（校验由
provenance/release 步脚本负责）、不判 gh run download/upload-artifact
行为（CI 负责）、不判 installer-diagnostics 等其余 artifact 名（不进
replace 下载清单）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)
WINDOWS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"
MACOS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"

FLAVOR_RX = re.compile(r"[a-z]+")

# 消费：provenance heredoc 元组里各平台的 artifact 名清单。
CONSUMER_RX = {
    "windows": re.compile(
        r"\('windows', 'WINDOWS_RUN',\s*'[^']*',\s*\[([^\]]+)\]", re.S
    ),
    "macos": re.compile(
        r"\('macos', 'MACOS_RUN',\s*'[^']*',\s*\[([^\]]+)\]", re.S
    ),
}
# 生产：artifact 名模板（upload-artifact 的 with.name）与 flavor matrix。
TEMPLATE_RX = {
    "windows": re.compile(
        r"^ *name: (DeterminFlow-Windows-x64-\$\{\{ matrix\.flavor \}\})$",
        re.M,
    ),
    "macos": re.compile(
        r"^ *name: (DeterminFlow-macOS-arm64-\$\{\{ matrix\.flavor \}\}"
        r"-adhoc-candidate)$",
        re.M,
    ),
}
# windows 的 matrix 是块式列表（- core / - full）。
BLOCK_MATRIX_RX = re.compile(
    r"^ {8}flavor:\n((?: {10}- [a-z]+\n)+)", re.M
)
# macos 的 matrix 是内联列表（[core, full]）。
INLINE_MATRIX_RX = re.compile(r"^ {8}flavor: \[([a-z, ]+)\]", re.M)

WORKFLOW_PATHS = {
    "windows": WINDOWS_WF,
    "macos": MACOS_WF,
}
MATRIX_RX = {
    "windows": BLOCK_MATRIX_RX,
    "macos": INLINE_MATRIX_RX,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _consumer(platform: str) -> list[str]:
    match = CONSUMER_RX[platform].search(_read(REPLACE_WF))
    assert match, f"replace workflow 找不到 {platform} 的下载清单——语料形态变了"
    return re.findall(r"'([^']+)'", match.group(1))


def _template(platform: str) -> str:
    found = TEMPLATE_RX[platform].findall(_read(WORKFLOW_PATHS[platform]))
    assert len(found) == 1, (
        f"{WORKFLOW_PATHS[platform].name} 的 artifact 名模板应恰 1 个，"
        f"实测 {len(found)} 个（{found}）"
    )
    return found[0]


def _flavors(platform: str) -> list[str]:
    text = _read(WORKFLOW_PATHS[platform])
    match = MATRIX_RX[platform].search(text)
    assert match, f"{WORKFLOW_PATHS[platform].name} 找不到 flavor matrix"
    if platform == "windows":
        return FLAVOR_RX.findall(
            match.group(1).replace("-", " ").replace("\n", " ")
        )
    return FLAVOR_RX.findall(match.group(1))


def test_download_manifest_corpus_shape() -> None:
    """W63a：两份清单各 2 条目；两 producer 各 1 模板、1 matrix、2 flavor。"""
    for platform in ("windows", "macos"):
        entries = _consumer(platform)
        assert len(entries) == 2, (
            f"replace 的 {platform} 下载清单应恰 2 个条目，实测 "
            f"{len(entries)} 个（{entries}）——W63a 语料守卫"
        )
        flavors = _flavors(platform)
        assert len(flavors) == 2, (
            f"{WORKFLOW_PATHS[platform].name} 的 flavor matrix 应恰 2 个，"
            f"实测 {len(flavors)} 个（{flavors}）——W63a 语料守卫"
        )
        # _template 的「恰 1 个」断言在提取时已经执行。
        _template(platform)


def test_download_manifest_expands_to_consumer_lists() -> None:
    """W63b：模板按 matrix 展开后的集合 == 消费清单集合（双向）。"""
    for platform in ("windows", "macos"):
        template = _template(platform)
        expanded = {template.replace("${{ matrix.flavor }}", f) for f in _flavors(platform)}
        consumed = set(_consumer(platform))
        assert expanded and consumed, "展开集或消费集为空——W63b 无锚"
        missing = sorted(consumed - expanded)
        extra = sorted(expanded - consumed)
        assert not missing and not extra, (
            f"{platform} 的 artifact 名生产 != 消费：消费未生产 {missing}"
            f"（gh run download --name 失败）、生产未消费 {extra}——matrix"
            "与下载清单必须同改"
        )
