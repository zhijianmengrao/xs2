"""R151：Python 支持面同账——CI / Dockerfile / classifiers / README。

背景（实测，R148 §7 登记、R151 开工复核）：

- ``pyproject.toml``：``requires-python = ">=3.11"``，classifiers 只有
  3.11 / 3.12；
- CI：ubuntu backend 与三个桌面 workflow 声明 3.11，windows-backend
  （Windows 权威基线）声明 **3.14**；
- ``Dockerfile``：``FROM python:3.12-slim``；
- ``README.md`` / ``README.en.md``：写「Python 3.11+」。

3.14 是权威 CI 却不在 classifiers——PyPI 元数据宣称的支持面与实际
测试面不一致；README 的下限也只是手抄，改 requires-python 时没人会
记得改它。本文件把四处声明钉成 **P 系判据**：

- **P1 语料守卫**：requires-python 有下限、classifiers 非空、CI 至少
  声明一个版本、Dockerfile 的 python 基础镜像版本、两份 README 的
  「Python X.Y+」都能解析；未知写法（``python-version-file``、非 X.Y）
  显式红，不静默跳过。
- **P2 CI → 声明面**：每个 workflow 的每个 ``python-version`` 都必须
  ∈ requires-python 范围且 ∈ classifiers。
- **P3 Dockerfile → 声明面**：基础镜像的 X.Y 同样 ∈ 范围与 classifiers。
- **P4 README → 下限**：README.md 与 README.en.md 的「Python X.Y+」
  下限 == requires-python 的下限（``>=X.Y``）。

边界：只判**声明面**（版本字符串），不判 runner 上 ``python3`` /
``python`` 的实际版本——replay 矩阵写的是解释器名，不是版本声明；
不要求每个 classifier 都在 CI 里跑（3.12 由 Dockerfile 覆盖）；
不判 requires-python 的上界（当前没有）。
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DOCKERFILE = REPO_ROOT / "Dockerfile"
READMES = (REPO_ROOT / "README.md", REPO_ROOT / "README.en.md")

CI_VERSION_RX = re.compile(
    r"^\s*python-version:\s*[\"']([^\"']+)[\"']\s*$", re.M
)
CLASSIFIER_RX = re.compile(
    r'^\s*"Programming Language :: Python :: (\d+\.\d+)",?\s*$', re.M
)
DOCKER_RX = re.compile(r"^FROM\s+python:(\d+\.\d+)(?:[-@][^\s]*)?\s*$", re.M | re.I)
README_FLOOR_RX = re.compile(r"Python\s+(\d+\.\d+)\+")
VERSION_SHAPE_RX = re.compile(r"^\d+\.\d+$")


def _requires_python() -> tuple[str, Version]:
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    raw = document["project"]["requires-python"]
    assert isinstance(raw, str) and raw.strip(), (
        "pyproject [project].requires-python 缺失或不是字符串"
    )
    match = re.search(r">=\s*(\d+\.\d+)", raw)
    assert match, (
        f"requires-python 没有可解析的下限（期望 >=X.Y）：{raw!r}"
    )
    return raw, Version(match.group(1))


def _classifiers() -> set[Version]:
    text = PYPROJECT.read_text(encoding="utf-8")
    versions = {Version(m.group(1)) for m in CLASSIFIER_RX.finditer(text)}
    assert versions, (
        "pyproject classifiers 没有「Programming Language :: Python :: X.Y」"
        "——支持面判据空转"
    )
    return versions


def _ci_versions() -> dict[str, list[Version]]:
    files = sorted(WORKFLOWS.glob("*.yml"))
    assert files, f"{WORKFLOWS} 下没有任何 workflow——仓库形态不对？"
    out: dict[str, list[Version]] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "python-version-file" not in text, (
            f"{path.name} 使用 python-version-file——P 系判据只解析显式 "
            "python-version，未知写法必须显式红而不是静默漏判"
        )
        for raw in CI_VERSION_RX.findall(text):
            assert VERSION_SHAPE_RX.match(raw), (
                f"{path.name} 的 python-version 不是 X.Y 形状：{raw!r}"
            )
            out.setdefault(path.name, []).append(Version(raw))
    assert out, "所有 workflow 都没有 python-version 声明——P2 会空转"
    return out


def _docker_version() -> Version:
    match = DOCKER_RX.search(DOCKERFILE.read_text(encoding="utf-8"))
    assert match, (
        "Dockerfile 没有「FROM python:X.Y-…」基础镜像——P3 无处落锚"
    )
    return Version(match.group(1))


def _readme_floor(path: Path) -> Version:
    floors = {
        Version(m.group(1))
        for m in README_FLOOR_RX.finditer(path.read_text(encoding="utf-8-sig"))
    }
    assert len(floors) == 1, (
        f"{path.name} 的「Python X.Y+」下限应恰好一个，实际 {sorted(map(str, floors))}"
    )
    return floors.pop()


def test_support_surface_is_parseable() -> None:
    """P1：四处声明都能解析，且语料非空。"""
    raw, floor = _requires_python()
    classifiers = _classifiers()
    ci = _ci_versions()
    docker = _docker_version()
    readme_floors = {path.name: _readme_floor(path) for path in READMES}
    assert floor, f"requires-python 下限为空：{raw!r}"
    assert classifiers, "classifiers 解析为空"
    assert ci, "CI 版本解析为空"
    assert docker, "Dockerfile 版本解析为空"
    assert len(readme_floors) == len(READMES), "README 下限没有全部解析"


def test_ci_python_versions_are_declared_supported() -> None:
    """P2：CI 的每个 python-version ∈ requires-python 且 ∈ classifiers。"""
    raw, _ = _requires_python()
    spec = SpecifierSet(raw)
    classifiers = _classifiers()
    violations: list[str] = []
    for name, versions in _ci_versions().items():
        for version in versions:
            if version not in spec:
                violations.append(
                    f"{name}: {version} 不在 requires-python {raw} 范围内"
                )
            if version not in classifiers:
                violations.append(
                    f"{name}: {version} 不在 classifiers"
                    f"（{sorted(map(str, classifiers))}）"
                )
    assert not violations, (
        "CI 声明的 Python 版本与支持面不同账：\n" + "\n".join(violations)
    )


def test_docker_python_version_is_declared_supported() -> None:
    """P3：Dockerfile 基础镜像版本 ∈ requires-python 且 ∈ classifiers。"""
    raw, _ = _requires_python()
    spec = SpecifierSet(raw)
    version = _docker_version()
    assert version in spec, (
        f"Dockerfile 的 python:{version} 不在 requires-python {raw} 范围内"
    )
    assert version in _classifiers(), (
        f"Dockerfile 的 python:{version} 不在 classifiers——"
        "镜像能跑但 PyPI 元数据不认"
    )


def test_readme_floor_matches_requires_python() -> None:
    """P4：README / README.en 的「Python X.Y+」下限 == requires-python 下限。"""
    _, floor = _requires_python()
    violations = [
        f"{path.name}: 写 {_readme_floor(path)}，requires-python 下限是 {floor}"
        for path in READMES
        if _readme_floor(path) != floor
    ]
    assert not violations, (
        "README 的 Python 下限与 requires-python 不同账：\n"
        + "\n".join(violations)
    )
