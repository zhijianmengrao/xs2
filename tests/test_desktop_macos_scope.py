"""R187：desktop README macOS 候选范围 ↔ workflow 矩阵（W 系续 W24）。

背景（实测，R184 §3 登记、R187 开工修复）：``desktop/README.md`` 的
macOS 候选表长期写「范围 | 只构建 Core，不构建 Full」，而
``.github/workflows/desktop-macos.yml`` 的 matrix 是 ``[core, full]``、
同文档叙述段也写「分别生成 Apple Silicon Core 与 Full」。三处叙述里
只有表行是旧值——照表理解的人会以为 Full 候选不存在。这是候选制在
登记阶段抓到的真实不一致，R187 先修文档再钉同账。

W24 把这条边钉成两半：

- **W24a 范围行 ↔ 矩阵**：``desktop-macos.yml`` build job 的
  ``flavor`` 矩阵非空且值都在 ``{core, full}`` 词表内；README macOS
  小节的「范围」行必须**点名矩阵里的每一个 flavor**（大小写不敏感）、
  不得出现矩阵外的值、不得再出现「只构建」「不构建」这类否定式叙述
  （历史上它就是「矩阵加了一个、表行没跟上」的形状）；「配置」行指向
  的 ``tauri.macos.conf.json`` 必须在磁盘。
- **W24b 叙述段双覆盖**：macOS 小节的叙述段提到 flavor 时必须同时
  提到两者（小节导语写的是「Core / Full 候选」，与矩阵一致）。

边界：只判 macOS 小节的「范围」「配置」两行与叙述段的 flavor 双覆盖
——不判 Windows 小节、不判矩阵的执行行为（CI 负责）、不判架构行里的
「不构建 universal 或 Intel」（那是架构排除，不是 flavor 范围）、
不判「桌面更新发布」节的历史叙述（其 macOS 段写「分别生成 … Core 与
Full」，与矩阵同账，但该节的职责是发版收尾，不是候选范围声明）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
README = REPO_ROOT / "desktop" / "README.md"

KNOWN_FLAVORS = frozenset({"core", "full"})
MATRIX_RX = re.compile(r"^\s*flavor:\s*\[([^\]]*)\]\s*$", re.M)
NEGATION_RX = re.compile(r"只构建|不构建")
FLAVOR_WORD_RX = re.compile(r"\b(core|full)\b", re.I)


def _matrix_flavors() -> list[str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    matches = MATRIX_RX.findall(text)
    assert len(matches) == 1, (
        f"desktop-macos.yml 的 flavor 矩阵应恰一处，实测 {matches}——W24 无锚"
    )
    flavors = [token.strip().strip("\"'") for token in matches[0].split(",")]
    flavors = [flavor for flavor in flavors if flavor]
    assert flavors, "desktop-macos.yml 的 flavor 矩阵为空——W24 无锚"
    unknown = sorted(set(flavors) - KNOWN_FLAVORS)
    assert not unknown, (
        f"flavor 矩阵出现词表外的值 {unknown}（词表 {sorted(KNOWN_FLAVORS)}）"
        "——扩充 flavor 必须同步更新本判据的词表与 README 的范围行"
    )
    return flavors


def _macos_section() -> list[tuple[int, str]]:
    lines = README.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("## macOS")),
        None,
    )
    assert start is not None, "desktop/README.md 缺少 macOS 小节——W24 无锚"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return [(i + 1, lines[i]) for i in range(start, end)]


def _table_row(cells: list[tuple[int, str]], key: str) -> tuple[int, str]:
    rows = [
        (lineno, line)
        for lineno, line in cells
        if line.startswith(f"| {key} |")
    ]
    assert len(rows) == 1, (
        f"macOS 小节的「{key}」行应恰一处，实测 {len(rows)} 处——W24 无锚"
    )
    return rows[0]


def _row_value(line: str) -> str:
    return line.split("|")[2].strip()


def test_macos_scope_row_matches_the_workflow_matrix() -> None:
    """W24a：范围行点名矩阵全部 flavor、无否定式；配置行路径在磁盘。"""
    flavors = _matrix_flavors()
    section = _macos_section()
    _, scope_line = _table_row(section, "范围")
    scope_value = _row_value(scope_line)

    words = {match.group(1).lower() for match in FLAVOR_WORD_RX.finditer(scope_value)}
    missing = sorted(set(flavors) - words)
    extra = sorted(words - set(flavors))
    assert not missing and not extra, (
        f"macOS 候选范围行与 workflow 矩阵不同账：矩阵 {flavors}，"
        f"范围行点名 {sorted(words)}（缺 {missing}，多 {extra}）——"
        "矩阵加减 flavor 必须同步更新 desktop/README.md 的范围行"
    )
    negated = NEGATION_RX.findall(scope_value)
    assert not negated, (
        f"范围行不得用否定式叙述 flavor 范围（实测 {negated}）——"
        "「只构建 / 不构建」就是本次修复前的分叉形状"
    )

    _, config_line = _table_row(section, "配置")
    config_value = _row_value(config_line)
    config_path = REPO_ROOT / config_value.strip("`")
    assert config_path.is_file(), (
        f"macOS 小节的配置行指向不存在的文件：{config_value}"
    )


def test_macos_prose_mentions_both_flavors() -> None:
    """W24b：叙述段提 flavor 必须双覆盖（Core 与 Full 同时出现）。"""
    section = _macos_section()
    prose = [
        line for _, line in section
        if not line.startswith("|") and not line.startswith("#")
    ]
    text = "\n".join(prose)
    words = {match.group(1).lower() for match in FLAVOR_WORD_RX.finditer(text)}
    if not words:
        return  # 叙述段完全不提 flavor 也是一致态
    flavors = _matrix_flavors()
    assert words == set(flavors), (
        f"macOS 叙述段的 flavor 叙述与矩阵不同账：矩阵 {flavors}，"
        f"叙述段只提到 {sorted(words)}"
    )
