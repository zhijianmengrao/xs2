"""R190：desktop README Windows 表 ↔ desktop-windows.yml runner 同账（W 系续 W26）。

背景（实测，R188 §3 登记、R190 开工复核）：``desktop/README.md`` 的
Windows 正式安装包表写「构建 | GitHub Actions ``windows-2025``」，而
``.github/workflows/desktop-windows.yml`` 的第一个 job ``build`` 的
``runs-on`` 也是 ``windows-2025``——表行是 runner 的人读账。runner 换代
（如 ``windows-2025`` → ``windows-latest``）时，只改 workflow 不改表行，
照表理解的人会以为构建还在 2025 镜像上；反向只改表行不改 workflow，
CI 的实际 runner 与文档分叉。这条边此前无人判——W24 管的是 macOS 表
的范围行，Windows 表的构建/配置/工作流三行没有锚。

W26 把这条边钉成两半：

- **W26a 语料守卫与路径存在性**：Windows 表「构建」「配置」「工作流」
  三行各恰一处；构建行的 runner 值是 ``windows-YYYY`` 形状（换代到
  ``windows-latest`` 这类无年份标签先在形状守卫红，强制改回带年份的
  显式值）；配置行与工作流行指向的路径按仓库根解析后在磁盘；workflow
  的第一个 job 有 ``runs-on`` 键（结构守卫，防「首 job 改名/换位」让
  下面 W26b 的锚落空）。
- **W26b runner 同账**：README 构建行的 runner == workflow 第一个 job
  的 ``runs-on``（逐字）。``desktop-windows.yml`` 实际有三个 job——
  ``build``（windows-2025）、``build-macos``（callable workflow，无
  ``runs-on``）、``release``（``ubuntu-latest``，仅 ``v*`` tag）——
  锚只钉第一个 job，``release`` 的 runner 不进射程。

边界：只判 Windows 表的构建/配置/工作流三行与 workflow 首个 job 的
runner——不判「安装包」「更新」两行（W27 射程：NSIS installMode）、
不判 runner 的矩阵展开行为（``flavor`` 矩阵由 W24 的同型思路与 CI
负责）、不判 ``build-macos`` 与 ``release`` 两个 job 的 runner、
不判工作流的触发条件与 step 行为。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"

RUNNER_TOKEN_RX = re.compile(r"`(windows-\d{4})`")
RUNS_ON_RX = re.compile(r"^\s+runs-on:\s*(\S+)\s*$", re.M)


def _windows_section() -> list[tuple[int, str]]:
    lines = README.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("## Windows")),
        None,
    )
    assert start is not None, "desktop/README.md 缺少 Windows 小节——W26 无锚"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return [(i + 1, lines[i]) for i in range(start, end)]


def _table_row(cells: list[tuple[int, str]], key: str) -> str:
    rows = [line for _, line in cells if line.startswith(f"| {key} |")]
    assert len(rows) == 1, (
        f"Windows 小节的「{key}」行应恰一处，实测 {len(rows)} 处——W26 无锚"
    )
    return rows[0]


def _row_value(line: str) -> str:
    return line.split("|")[2].strip()


def _readme_runner() -> str:
    section = _windows_section()
    build_row = _table_row(section, "构建")
    tokens = RUNNER_TOKEN_RX.findall(_row_value(build_row))
    assert len(tokens) == 1, (
        f"Windows 表构建行的 runner 应恰一处 windows-YYYY 形状，实测 {tokens}"
        "——runner 换代必须写显式带年份的镜像名（如 windows-2025），"
        "不得用 windows-latest 这类浮动标签"
    )
    return tokens[0]


def _workflow_runner() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = document.get("jobs") if isinstance(document, dict) else None
    assert isinstance(jobs, dict) and jobs, (
        "desktop-windows.yml 没有 jobs 映射——W26 无锚"
    )
    first_job = next(iter(jobs))
    first = jobs[first_job]
    assert isinstance(first, dict) and isinstance(first.get("runs-on"), str), (
        f"desktop-windows.yml 第一个 job {first_job!r} 没有 runs-on 字符串值"
        "——W26b 的锚落空"
    )
    return first["runs-on"].strip()


def test_windows_table_paths_resolve_on_disk() -> None:
    """W26a：构建/配置/工作流三行恰一处；runner 形状；两个路径在磁盘。"""
    section = _windows_section()
    _readme_runner()  # 形状守卫：恰一处 windows-YYYY

    for key in ("配置", "工作流"):
        value = _row_value(_table_row(section, key)).strip("`")
        resolved = REPO_ROOT / value
        assert resolved.is_file(), (
            f"Windows 表「{key}」行指向不存在的路径：{value}（按 {REPO_ROOT} 解析）"
        )

    _workflow_runner()  # 结构守卫：首个 job 有 runs-on


def test_windows_table_runner_matches_the_workflow() -> None:
    """W26b：README 构建行的 runner == workflow 第一个 job 的 runs-on。"""
    readme_runner = _readme_runner()
    workflow_runner = _workflow_runner()
    assert readme_runner == workflow_runner, (
        f"Windows 构建runner 与 workflow 不同账：README 写 {readme_runner}，"
        f"desktop-windows.yml 第一个 job 写 {workflow_runner}——"
        "runner 换代必须表行与 workflow 同步改"
    )
