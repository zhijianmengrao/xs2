"""R177：环境检查脚本 ↔ 支持面下限（P 系续 P10）。

背景（实测，R176 §3 登记、R177 开工复核）：

- ``pyproject.toml`` 的 ``requires-python = ">=3.11"`` 与
  ``web/package.json`` 的 ``engines.node = ">=22.12.0"`` 是支持面锚点；
- README 双语已由 P4/P7 钉住；``CONTRIBUTING.md`` 的「Python 3.11+ /
  Node.js 22+」与 ``scripts/check_environment.py`` 的下限仍是手抄；
- 实测发现 checker 的 Node 下限写的是 **18+**（engines 已是 22.12）：
  Node 18/20 会被判绿，随后 ``npm run build`` 才失败。

P10 把剩余两处收进「支持面下限」判据：

- **P10a 语料守卫**：requires-python / engines.node / CONTRIBUTING 的
  Python 与 Node 下限、脚本的两个常量都能解析且形状唯一；缺一处显式红。
- **P10b 下限同账 + 行为边界**：两个常量 == 锚点下限；脚本对低于下限的
  Python 报错、对低于下限的 Node 告警，等于/高于下限判绿。

边界：只判「下限声明」；不判 Node / Python 的实际安装版本（运行时探针
不是声明面）；不判 README（P4/P7 已覆盖）；不判 CONTRIBUTING 的其它
版本叙述。
"""

from __future__ import annotations

import json
import re
import tomllib
import types
from pathlib import Path

import pytest

from scripts import check_environment as checker_module
from scripts.check_environment import MIN_NODE, MIN_PYTHON, EnvironmentChecker

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
WEB_PACKAGE = REPO_ROOT / "web" / "package.json"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

CONTRIBUTING_PYTHON_RX = re.compile(r"Python\s+(\d+\.\d+)\+")
CONTRIBUTING_NODE_RX = re.compile(r"Node\.js\s+(\d+\.\d+)\+")
SPEC_FLOOR_RX = re.compile(r">=\s*(\d+)\.(\d+)")


def _floor(spec: str, *, source: str) -> tuple[int, int]:
    match = SPEC_FLOOR_RX.search(spec)
    assert match, f"{source} 没有 >=X.Y 下限——P10 无锚: {spec!r}"
    return int(match.group(1)), int(match.group(2))


def _manifest_floors() -> tuple[tuple[int, int], tuple[int, int]]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    python_floor = _floor(
        project["project"]["requires-python"], source="pyproject requires-python"
    )
    engines = json.loads(WEB_PACKAGE.read_text(encoding="utf-8"))["engines"]
    node_floor = _floor(engines["node"], source="web/package.json engines.node")
    return python_floor, node_floor


def _contributing_floors() -> tuple[tuple[int, int], tuple[int, int]]:
    text = CONTRIBUTING.read_text(encoding="utf-8")
    python_matches = CONTRIBUTING_PYTHON_RX.findall(text)
    node_matches = CONTRIBUTING_NODE_RX.findall(text)
    assert len(python_matches) == 1, (
        f"CONTRIBUTING 的 Python 下限应恰一处，实测 {python_matches}"
    )
    assert len(node_matches) == 1, (
        f"CONTRIBUTING 的 Node 下限应恰一处，实测 {node_matches}"
    )
    return (
        tuple(int(part) for part in python_matches[0].split(".")),
        tuple(int(part) for part in node_matches[0].split(".")),
    )


def test_support_floor_sources_are_parseable() -> None:
    """P10a：四个下限源都能解析，脚本常量形状唯一。"""
    for constant, name in ((MIN_PYTHON, "MIN_PYTHON"), (MIN_NODE, "MIN_NODE")):
        assert isinstance(constant, tuple) and len(constant) == 2, (
            f"{name} 必须是 (major, minor) 二元组，实测 {constant!r}"
        )
        assert all(isinstance(value, int) for value in constant), (
            f"{name} 的 major/minor 必须是 int，实测 {constant!r}"
        )
    source = (REPO_ROOT / "scripts" / "check_environment.py").read_text(
        encoding="utf-8"
    )
    assert source.count("MIN_PYTHON =") == 1, "MIN_PYTHON 定义必须恰一处"
    assert source.count("MIN_NODE =") == 1, "MIN_NODE 定义必须恰一处"
    _manifest_floors()
    _contributing_floors()


def test_support_floors_match_and_the_checker_judges_by_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P10b：两处手抄下限 == 锚点；脚本在边界两侧的行为正确。"""
    python_floor, node_floor = _manifest_floors()
    attending_python, attending_node = _contributing_floors()

    assert MIN_PYTHON == python_floor, (
        f"checker Python 下限 {MIN_PYTHON} != requires-python {python_floor}"
    )
    assert MIN_NODE == node_floor, (
        f"checker Node 下限 {MIN_NODE} != engines.node {node_floor}"
    )
    assert attending_python == python_floor, (
        f"CONTRIBUTING Python 下限 {attending_python} != {python_floor}"
    )
    assert attending_node == node_floor, (
        f"CONTRIBUTING Node 下限 {attending_node} != {node_floor}"
    )

    def fake_node(version: str):
        def run(*_args, **_kwargs):
            return types.SimpleNamespace(returncode=0, stdout=version)

        return run

    checker = EnvironmentChecker()
    checker.system = "Linux"
    monkeypatch.setattr(checker_module.subprocess, "run", fake_node("v22.11.0"))
    assert checker.check_nodejs() is True
    assert any("22.12" in warning for warning in checker.warnings), (
        f"Node 22.11 低于 engines 下限，必须告警：{checker.warnings}"
    )
    assert not checker.info

    checker = EnvironmentChecker()
    checker.system = "Linux"
    monkeypatch.setattr(checker_module.subprocess, "run", fake_node("v22.12.0"))
    assert checker.check_nodejs() is True
    assert not checker.warnings
    assert any("Node.js" in info for info in checker.info)

    checker = EnvironmentChecker()
    monkeypatch.setattr(
        checker_module,
        "sys",
        types.SimpleNamespace(
            version_info=types.SimpleNamespace(major=3, minor=10, micro=0)
        ),
    )
    assert checker.check_python_version() is False
    assert any("3.11" in error for error in checker.errors), (
        f"Python 3.10 低于 requires-python 下限，必须报错：{checker.errors}"
    )

    checker = EnvironmentChecker()
    monkeypatch.setattr(
        checker_module,
        "sys",
        types.SimpleNamespace(
            version_info=types.SimpleNamespace(major=3, minor=11, micro=0)
        ),
    )
    assert checker.check_python_version() is True
    assert not checker.errors
    assert any("Python 3.11" in info for info in checker.info)
