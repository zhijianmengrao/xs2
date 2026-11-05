"""R151 / R155：Python 支持面同账——CI / Dockerfile / classifiers / README / 锁头。

背景（实测，R148 §7 登记、R151 开工复核；R155 续）：

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

R155 把**锁生成头**也收进来（R152 §7 登记）。两份锁的第二行是 uv 的
生成命令回显，里面的 ``--python-version 3.11`` 记录了**解析这份闭包
时用的解释器版本**——它才是依赖解析的真实锚点。改 requires-python
而不重生成锁时，锁仍按旧解释器编译，闭包可能悄悄漂移；此前这条边
无人对账（W8/W9 只对账包名与钉版，不读生成头）。

- **P5 锁生成头 → 下限**：requirements.lock 与 requirements-dev.lock
  生成头的 ``--python-version X.Y`` == requires-python 的下限。

R157 把**展示层**也收进来（R156 §7 登记）。徽章是 README 里最显眼的
支持面展示，Node 下限是同一问题的非 Python 版——两者此前都靠手抄：

- **P6 徽章 → 下限**：两份 README 的 shields 徽章（URL 的
  ``badge/Python-X.Y-`` 与 ``alt="Python X.Y"``）== requires-python
  的下限。URL 与 alt 双锚：只改其一仍是红。
- **P7 Node 下限 → engines**：README 双语的「Node.js X.Y+」==
  ``web/package.json`` ``engines.node`` 的下限（``>=X.Y.0``）；声明了
  ``node-version`` 的 workflow，其 major 必须等于 engines 的 major。

边界：只判**声明面**（版本字符串），不判 runner 上 ``python3`` /
``python`` 的实际版本——replay 矩阵写的是解释器名，不是版本声明；
不要求每个 classifier 都在 CI 里跑（3.12 由 Dockerfile 覆盖）；
不判 requires-python 的上界（当前没有）。P5 只读生成头这一行，不重放
uv 解析过程（那是包内容的事，W 系已覆盖）；生成头丢失或写法变了要
显式红，不许静默漏判——生成头是 P5 唯一的锚。P6/P7 的语料解析不到
同样显式红（徽章与 Node 下限各是唯一锚）。P7 不判 npm 下限（README
提到 npm 但没有版本声明，无从对账）；不判 desktop 管线的 Node 实际
版本（tag-only 上游继承工作流，声明面已由 major 同账覆盖）。
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
LOCKS = (REPO_ROOT / "requirements.lock", REPO_ROOT / "requirements-dev.lock")
LOCK_HEADER_RX = re.compile(
    r"^#\s{2,}uv pip compile .*--python-version[ =](\d+\.\d+)\s", re.M
)
BADGE_URL_RX = re.compile(r"badge/Python-(\d+\.\d+)-")
BADGE_ALT_RX = re.compile(r'alt="Python (\d+\.\d+)"')
NODE_FLOOR_RX = re.compile(r"Node\.js\s+(\d+)\.(\d+)\+")
ENGINES_FLOOR_RX = re.compile(r"^>=(\d+)\.(\d+)\.0$")
WORKFLOW_NODE_RX = re.compile(
    r"^\s*node-version:\s*[\"'](\d+)(?:\.\d+)?[\"']\s*$", re.M
)
WEB_PACKAGE = REPO_ROOT / "web" / "package.json"


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


def _lock_header_version(path: Path) -> Version:
    """取锁生成头的 ``--python-version``（uv pip compile 的回显行）。"""
    match = LOCK_HEADER_RX.search(path.read_text(encoding="utf-8"))
    assert match, (
        f"{path.name} 的生成头没有「uv pip compile … --python-version X.Y」——"
        "生成头丢失或写法变了，P5 无处落锚（显式红，不静默跳过）"
    )
    return Version(match.group(1))


def test_lock_generator_python_version_matches_floor() -> None:
    """P5：两份锁生成头的 --python-version == requires-python 下限。"""
    _, floor = _requires_python()
    violations = [
        f"{path.name}: 生成头 --python-version {_lock_header_version(path)}，"
        f"requires-python 下限是 {floor}——改下限后需重生成锁"
        for path in LOCKS
        if _lock_header_version(path) != floor
    ]
    assert not violations, (
        "锁生成头与 requires-python 下限不同账（锁仍按旧解释器解析，"
        "依赖闭包可能漂移）：\n" + "\n".join(violations)
    )


def _badge_versions(path: Path) -> tuple[Version, Version]:
    """徽章 URL 与 alt 里的 Python X.Y（各恰好一处，双锚）。"""
    text = path.read_text(encoding="utf-8-sig")
    url_versions = {
        Version(m.group(1)) for m in BADGE_URL_RX.finditer(text)
    }
    alt_versions = {
        Version(m.group(1)) for m in BADGE_ALT_RX.finditer(text)
    }
    assert len(url_versions) == 1, (
        f"{path.name} 的 shields 徽章 URL 应恰好解析出一个 Python X.Y，"
        f"实际 {sorted(map(str, url_versions))}"
    )
    assert len(alt_versions) == 1, (
        f"{path.name} 的徽章 alt 应恰好解析出一个 Python X.Y，"
        f"实际 {sorted(map(str, alt_versions))}"
    )
    return url_versions.pop(), alt_versions.pop()


def test_readme_python_badge_matches_floor() -> None:
    """P6：README 双语徽章（URL 与 alt）== requires-python 下限。"""
    _, floor = _requires_python()
    violations = []
    for path in READMES:
        url_version, alt_version = _badge_versions(path)
        if url_version != floor:
            violations.append(
                f"{path.name}: 徽章 URL 写 {url_version}，requires-python "
                f"下限是 {floor}"
            )
        if alt_version != floor:
            violations.append(
                f"{path.name}: 徽章 alt 写 {alt_version}，requires-python "
                f"下限是 {floor}"
            )
    assert not violations, (
        "README 的 Python 徽章与 requires-python 下限不同账：\n"
        + "\n".join(violations)
    )


def _node_floors() -> tuple[tuple[int, int], int]:
    """(engines 下限 (major, minor), engines major)；解析不到显式红。"""
    import json

    document = json.loads(WEB_PACKAGE.read_text(encoding="utf-8"))
    raw = (document.get("engines") or {}).get("node")
    assert isinstance(raw, str) and raw.strip(), (
        "web/package.json 没有 engines.node——P7 无处落锚"
    )
    match = ENGINES_FLOOR_RX.match(raw.strip())
    assert match, (
        f"engines.node 不是 >=X.Y.0 形状（P7 只认这个写法）：{raw!r}"
    )
    return (int(match.group(1)), int(match.group(2))), int(match.group(1))


def _readme_node_floor(path: Path) -> tuple[int, int]:
    floors = {
        (int(m.group(1)), int(m.group(2)))
        for m in NODE_FLOOR_RX.finditer(path.read_text(encoding="utf-8-sig"))
    }
    assert len(floors) == 1, (
        f"{path.name} 的「Node.js X.Y+」下限应恰好一个，实际 {sorted(floors)}"
    )
    return floors.pop()


def test_readme_node_floor_matches_engines() -> None:
    """P7：README 双语 Node 下限 == engines 下限；CI node-version major 同账。"""
    engines_floor, engines_major = _node_floors()
    violations = []
    for path in READMES:
        floor = _readme_node_floor(path)
        if floor != engines_floor:
            violations.append(
                f"{path.name}: 写 Node.js {floor[0]}.{floor[1]}+，engines 是 "
                f">={engines_floor[0]}.{engines_floor[1]}.0"
            )
    assert not violations, (
        "README 的 Node.js 下限与 web/package.json engines 不同账：\n"
        + "\n".join(violations)
    )

    declared_major: set[int] = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for raw in WORKFLOW_NODE_RX.findall(
            path.read_text(encoding="utf-8")
        ):
            major = int(raw)
            declared_major.add(major)
            if major != engines_major:
                violations.append(
                    f"{path.name}: node-version 声明 major {major}，"
                    f"engines 下限是 {engines_floor[0]}.{engines_floor[1]}"
                )
    assert declared_major, (
        "所有 workflow 都没有 node-version 声明——P7 的 CI 伴生判空转"
    )
    assert not violations, (
        "CI 的 node-version 与 engines 的 major 不同账：\n"
        + "\n".join(violations)
    )
