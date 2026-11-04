"""R142：PROJECT_INFO 专述 bullet 覆盖与顺序单调。

背景（实测，R141 §7）：``docs/PROJECT_INFO.md`` §项目状态 + §迭代记录
是「每轮一段」的叙事账，但它只有两把人肉尺：**覆盖**（每轮有没有专述
bullet）与**顺序**（bullet 是否按轮次单调）。R133 实测过顺序错位
（R40 排在 R39 前、R32 排在 R39/R40 后）并重排；R33 从未有专述 bullet
（R32 直接到 R36，R34/R35 从未有文档）。两把尺此前都没有判据。

本文件把两把尺钉住（**B 系判据**）：

- **B1 覆盖**：R23 起到磁盘上最新交接文档轮次，每个轮次必须有一条
  专述 bullet（行首 ``- **R<n>`` 旧格式或 ``- <日期> R<n>`` 新格式；
  三个叙事章节：§项目状态 R23–R40、§测试环境双基线 R41–R111、
  §迭代记录续记 R112 起）。豁免清单 {33, 34, 35} 登记在案（R33 属历史
  内容缺口，R34/R35 从未有文档，R36 收编）——豁免不是惯例，新轮次
  不再进入。
- **B2 顺序**：专述 bullet 的轮次序列必须严格单调递增（R133 的重排
  防复发）。

边界：不钉 bullet 的**内容**（那是叙事，不是账目）；不要求每个 bullet
单行（多行续行由行首判定天然豁免）；轮次 < 23 属「维护入口前」时代
（R15–R22 在完结段里以区间叙述），不在射程。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_INFO = REPO_ROOT / "docs" / "PROJECT_INFO.md"
DOCS = REPO_ROOT / "docs"

# 有意豁免：R33 无专述（历史内容缺口，R32 直接到 R36）；R34/R35 从未有
# 文档（R36 收编）。新轮次不得再加入。
ALLOWED_MISSING = frozenset({33, 34, 35})

# 专述 bullet 的两种行首格式：旧「- **R40 维护轮（…）」与新
# 「- 2026-11-04 R130 单 profile（…）」。
BULLET_RX = re.compile(
    r"^-\s+(?:\*\*)?R(\d+)\b| ^-\s+\d{4}-\d{2}-\d{2}\s+R(\d+)\b", re.X
)


def _dedicated_bullets() -> list[tuple[int, int]]:
    """返回 (轮次, 行号) 列表，按文件顺序。

    只扫三个叙事章节（``## 项目状态`` R23–R40、``## 测试环境`` R41–R111
    的双基线行、``## 迭代记录续记`` R112 起）——整文件扫描会吃进
    §平台注意事项 的按轮备注行（R17/R21 时代），它们不是专述 bullet，
    且会破坏顺序判据（R142 首跑实测）。
    """
    out: list[tuple[int, int]] = []
    text = PROJECT_INFO.read_text(encoding="utf-8-sig")
    in_scope = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            in_scope = line.startswith(
                ("## 项目状态", "## 测试环境", "## 迭代记录续记")
            )
            continue
        if not in_scope:
            continue
        m = re.match(r"^-\s+(?:\*\*)?R(\d+)\b", line) or re.match(
            r"^-\s+\d{4}-\d{2}-\d{2}\s+R(\d+)\b", line
        )
        if m:
            out.append((int(m.group(1)), lineno))
    assert out, "PROJECT_INFO 没有扫到任何专述 bullet——B 系判据空转"
    return out


def _latest_round() -> int:
    files = sorted(DOCS.glob("HANDOVER_ROUND*.md"))
    assert files, "docs/ 下没有交接文档"
    return max(
        int(re.search(r"ROUND(\d+)", p.name).group(1)) for p in files
    )


def test_every_round_has_a_dedicated_bullet() -> None:
    """B1：R23 起每轮一条专述 bullet（豁免清单除外）。"""
    rounds = {r for r, _ in _dedicated_bullets()}
    expected = set(range(23, _latest_round() + 1))
    missing = sorted(r for r in expected - rounds if r not in ALLOWED_MISSING)
    assert not missing, (
        f"PROJECT_INFO 缺专述 bullet 的轮次：{missing}"
        f"（豁免清单 {sorted(ALLOWED_MISSING)} 之外的轮次必须有专述段）"
    )


def test_dedicated_bullets_are_monotonic() -> None:
    """B2：三个叙事章节各自「账本段」内单调递增（R133 的节内错位防复发）。

    节的账本起点（LODGER_FLOOR）之外的行是有意历史记录，不参与单调性：
    §测试环境 开头 R15–R23 时代的双基线锚与尾部 R21 完结态抽查是历史锚
    （17/18/20/21/23 两处出现）；§项目状态 从 23 起账；§迭代记录续记
    从 112 起账。改章节结构必须连动本映射。
    """
    floors = {"项目状态": 23, "测试环境": 41, "迭代记录续记": 112}
    by_section: dict[str, list[int]] = {}
    text = PROJECT_INFO.read_text(encoding="utf-8-sig")
    section = ""
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            section = line[3:].split("（")[0].strip()
            continue
        if section not in floors:
            continue
        m = re.match(r"^-\s+(?:\*\*)?R(\d+)\b", line) or re.match(
            r"^-\s+\d{4}-\d{2}-\d{2}\s+R(\d+)\b", line
        )
        if m and int(m.group(1)) >= floors[section]:
            by_section.setdefault(section, []).append(int(m.group(1)))
    for name, seq in by_section.items():
        inversions = [
            (seq[i], seq[i + 1])
            for i in range(len(seq) - 1)
            if seq[i] > seq[i + 1]
        ]
        assert not inversions, (
            f"PROJECT_INFO §{name} bullet 顺序倒置（R133 的错位复发？）："
            f"{inversions}"
        )
