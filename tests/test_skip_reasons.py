"""R141：skip 分类钉测——每条 skip 必须带可读 reason。

背景（实测，R140 §7）：tests/ 里静态提取到 46 个 ``pytest.mark.skip[if]``
标记与 ``pytest.skip()`` 调用，**全部带 reason**——这是 R71（msys skip
归因：判据先被判据自己吞掉）以来逐轮积累的纪律。但「带 reason」本身没有
判据：一条新加的 ``@pytest.mark.skip()``（无参）或 ``pytest.skip()``
（无消息）会静默通过，skipped 计数 +1 而没人知道为什么。

本文件把「skip 必须自述」钉成机判（**R 系判据**）：

- **R1 标记带 reason**：每个 ``@pytest.mark.skip[if](...)`` 必须有非空
  ``reason=`` 字符串参数；
- **R2 运行时调用带消息**：每个 ``pytest.skip(...)``/``pytest.fail(...)``
  必须有非空首参；
- 逐条参数化（ids = 文件名）——新增的裸 skip 会以自己的文件名出现在
  判红清单里。

边界：不钉 reason 的**内容**（平台归因的措辞由 R71 家族的测试自己担保）；
不钉 skip 的数量（平台差异大：本机 28 / CI ubuntu 65）；``pytest.xfail``
不在范围（它本来就要求理由的语义不同）。conftest.py 也在扫描范围。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# 排除自身：本文件的 docstring/正则里就有 skip 字样（自扫自咬，R141 首跑
# 教训——扫描器的语料必须不含扫描器自己）。
SCAN_FILES = sorted(
    p for p in (REPO_ROOT / "tests").glob("*.py") if p.name != "test_skip_reasons.py"
)

MARKER_RX = re.compile(
    r"@pytest\.mark\.(?:skip|skipif)\((?P<args>[^()]*(?:\([^()]*\)[^()]*)*)\)",
    re.S,
)
CALL_HEAD_RX = re.compile(r"pytest\.(?:skip|fail)\(")
STRING_RX = re.compile(r"[\"']([^\"']+)[\"']")


def _balanced_paren(text: str, start: int) -> str:
    """取从 start（指向 '('）开始的平衡括号片段（一层嵌套）。"""
    depth = 0
    for i in range(start, min(start + 4000, len(text))):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start : start + 200]


def _findings() -> list[tuple[str, int, str, str]]:
    """返回 (文件名, 行号, 种类, 代码片段) 四元组。"""
    out: list[tuple[str, int, str, str]] = []
    for path in SCAN_FILES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in MARKER_RX.finditer(text):
            out.append((path.name, text[: m.start()].count("\n") + 1, "marker", m.group(0)))
        for m in CALL_HEAD_RX.finditer(text):
            call = _balanced_paren(text, m.end() - 1)
            out.append((path.name, text[: m.start()].count("\n") + 1, "call", call))
    return out


FINDINGS = _findings()


def test_skip_findings_exist() -> None:
    """语料守卫：扫描必须找到 skip 标记（否则 R1/R2 是空转判据）。"""
    assert FINDINGS, "tests/ 没扫到任何 skip 标记/调用——R 系判据空转"


def _has_reason(snippet: str) -> bool:
    m = re.search(r"reason\s*=\s*[\"']([^\"']+)[\"']", snippet)
    return bool(m and m.group(1).strip())


def _has_message(snippet: str) -> bool:
    """调用形：首个非空字符串实参，或 reason= 关键字实参。"""
    args = snippet[snippet.find("(") + 1 : snippet.rfind(")")]
    kw = re.search(r"reason\s*=\s*[\"']([^\"']+)[\"']", args)
    if kw and kw.group(1).strip():
        return True
    for m in STRING_RX.finditer(args):
        if m.group(1).strip():
            return True
    return False


@pytest.mark.parametrize(
    "name, lineno, kind, snippet",
    FINDINGS,
    ids=[f"{n}:{l}:{k}" for n, l, k, _ in FINDINGS],
)
def test_every_skip_carries_a_reason(
    name: str, lineno: int, kind: str, snippet: str
) -> None:
    """R1/R2：marker 必须带非空 reason，调用必须带非空消息。"""
    if kind == "marker":
        ok = _has_reason(snippet)
        need = "reason=\"…\""
    else:
        ok = _has_message(snippet)
        need = "pytest.skip(\"…\") 的消息参数"
    assert ok, (
        f"{name}:{lineno} 的 skip 没有{need}（R71：skipped 计数 +1 而无人知道"
        f"为什么）——{snippet.strip()[:120]}"
    )
