"""R145：依赖四源同账——pyproject / requirements / requirements-dev / 锁。

背景（实测，R144 §7 登记、R145 开工复核）：依赖账有四个写入点，此前只有
R143 的 W1/W2 把守 requirements.txt ↔ requirements-dev.lock 这一条边。

- ``pyproject.toml [project].dependencies``：17 个 ``==`` 钉版（打包元数据）；
- ``requirements.txt``：19 个 ``==`` 钉版（本地开发安装源）；
- ``requirements-dev.txt``：``-r requirements.txt`` + ``pytest==9.1.1``
  （开发/CI 顶层依赖）；
- ``requirements.lock`` / ``requirements-dev.lock``：uv 编出的闭包，分别是
  Docker/桌面管线与 CI 的**实际安装源**。

两个未被把守的边（实测成立、但此前无判据）：pyproject 的 17 个依赖是否
真的都在 requirements.txt 且版本逐字相等；requirements-dev.txt 的
``-r`` 展开是否恰等于 requirements.txt ∪ dev extra。另有第三条边
requirements.txt → requirements.lock 只被 Docker 间接使用——某人只刷
dev lock 不刷 runtime lock 时，容器构建仍会装旧版本。

本文件把四条边钉住（**W 系判据**，续 R143 的 W1/W2）：

- **W3 语料守卫**：四源都能解析、非空，且每项都是 ``==`` 钉版（范围规格
  会让同账判据失去意义）；``-r`` 递归展开，重复声明的版本冲突当场红。
- **W4 名字覆盖**：pyproject 的每个运行时依赖（extras 剥离、名字归一）都
  必须出现在 requirements.txt。
- **W5 版本同账**：同一包在 pyproject 与 requirements.txt 的 ``==`` 钉版
  逐字相等。
- **W6 允许集**：requirements.txt 有而 pyproject 没有的包必须**恰等于**
  ``REQUIREMENTS_ONLY``（tzdata / uvicorn-worker，服务与 Windows 运行时
  补充），且钉版与登记值相同——新增或删除都必须连动登记表。
- **W7 dev 展开**：展开 ``-r`` 后的 requirements-dev.txt 恰等于
  requirements.txt ∪ pyproject dev extra（名字与钉版都同账）。
- **W8 dev → CI 锁**：requirements-dev.txt 的每个包都在
  requirements-dev.lock 且钉版逐字相等。
- **W9 runtime → 运行时锁**：requirements.txt 的每个包都在
  requirements.lock 且钉版逐字相等（Dockerfile 与桌面管线直接安装它）。

边界：不要求锁文件 ⊆ requirements（闭包是超集，常态）；不判
``build-system.requires``（构建隔离环境自管，且是范围规格）；不判
``uv.lock``——仓库内零引用（CI/Docker/scripts 均不读它），是否删除留给
R148 收口决定。环境标记行按整行接受（``; sys_platform …`` 不参与判决）。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_DEV = REPO_ROOT / "requirements-dev.txt"
RUNTIME_LOCK = REPO_ROOT / "requirements.lock"
DEV_LOCK = REPO_ROOT / "requirements-dev.lock"

# requirements.txt 允许有、pyproject 没有的包：服务/Windows 运行时补充。
# 值与 requirements.txt 的钉版同账；集合按「恰等」判——增删都必须改这里。
REQUIREMENTS_ONLY = {
    "tzdata": "2026.3",          # Windows 无系统 tzdata；zoneinfo 运行时依赖
    "uvicorn-worker": "0.4.0",   # gunicorn worker class（Dockerfile 使用）
}

Pin = str | None


def _pinned(requirement: Requirement, where: str) -> Pin:
    """取 ``==`` 钉版；多个 ``==`` 是不合法的同账输入。"""
    pins = [spec.version for spec in requirement.specifier if spec.operator == "=="]
    assert len(pins) <= 1, f"{where}：{requirement} 声明了多个 == 钉版：{pins}"
    return pins[0] if pins else None


def _parse_spec_list(specs: list[str], where: str) -> dict[str, Pin]:
    """解析 pyproject 的依赖字符串列表（name[extras]==V）。"""
    out: dict[str, Pin] = {}
    for spec in specs:
        requirement = Requirement(spec)
        name = canonicalize_name(requirement.name)
        assert name not in out, f"{where} 重复声明 {name}：{spec!r}"
        out[name] = _pinned(requirement, where)
    return out


def _parse_requirements(path: Path) -> dict[str, Pin]:
    """解析 requirements 文件；``-r <file>`` 递归展开，版本冲突当场红。"""
    out: dict[str, Pin] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-"):
            assert line.startswith("-r "), (
                f"{path.name} 有不支持的选项行（判据只展开了 -r）：{line!r}"
            )
            include = path.parent / line[3:].strip()
            assert include.is_file(), f"{path.name} 的 -r 目标不存在：{include}"
            for name, pin in _parse_requirements(include).items():
                if name in out and out[name] != pin:
                    raise AssertionError(
                        f"{path.name} 展开 {include.name} 后 {name} 版本冲突："
                        f"{out[name]} vs {pin}"
                    )
                out[name] = pin
            continue
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        assert name not in out, f"{path.name} 重复声明 {name}：{line!r}"
        out[name] = _pinned(requirement, path.name)
    return out


def _pyproject() -> tuple[dict[str, Pin], dict[str, Pin]]:
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = document["project"]
    runtime = _parse_spec_list(
        project["dependencies"], "pyproject [project].dependencies"
    )
    dev = _parse_spec_list(
        project["optional-dependencies"]["dev"], "pyproject dev extra"
    )
    return runtime, dev


def test_all_sources_pin_every_dependency() -> None:
    """W3：四源可解析、非空、全部 ``==`` 钉版（判据不得空转）。"""
    pyproject, dev_extra = _pyproject()
    sources = {
        "pyproject [project].dependencies": pyproject,
        "pyproject dev extra": dev_extra,
        "requirements.txt": _parse_requirements(REQUIREMENTS),
        "requirements-dev.txt（-r 展开）": _parse_requirements(REQUIREMENTS_DEV),
        "requirements.lock": _parse_requirements(RUNTIME_LOCK),
        "requirements-dev.lock": _parse_requirements(DEV_LOCK),
    }
    for label, table in sources.items():
        assert table, f"{label} 没有解析到依赖——同账判据空转"
        unpinned = sorted(name for name, pin in table.items() if pin is None)
        assert not unpinned, (
            f"{label} 有未钉版的依赖：{unpinned}——范围规格不属于四源同账"
            f"（无法逐字比对版本）"
        )


def test_pyproject_dependencies_are_declared_in_requirements() -> None:
    """W4：pyproject 的每个运行时依赖都在 requirements.txt（名字覆盖）。"""
    pyproject, _ = _pyproject()
    requirements = _parse_requirements(REQUIREMENTS)
    missing = sorted(set(pyproject) - set(requirements))
    assert not missing, (
        f"pyproject 声明了但 requirements.txt 没有的依赖：{missing}——"
        "本地开发从 requirements.txt 安装，会漏装打包元数据里的包"
    )


def test_pyproject_pins_agree_with_requirements() -> None:
    """W5：同一包在 pyproject 与 requirements.txt 的钉版逐字相等。"""
    pyproject, _ = _pyproject()
    requirements = _parse_requirements(REQUIREMENTS)
    drift = {
        name: (pin, requirements.get(name))
        for name, pin in pyproject.items()
        if requirements.get(name) != pin
    }
    assert not drift, (
        "pyproject 与 requirements.txt 版本漂移（两处安装会得到不同版本）："
        + "; ".join(
            f"{name}: pyproject=={pin} vs requirements=={other}"
            for name, (pin, other) in drift.items()
        )
    )


def test_requirements_only_packages_are_a_registered_allowlist() -> None:
    """W6：requirements.txt 多出的包恰等于登记允许集，且钉版同账。"""
    pyproject, _ = _pyproject()
    requirements = _parse_requirements(REQUIREMENTS)
    extra = set(requirements) - set(pyproject)
    assert extra == set(REQUIREMENTS_ONLY), (
        f"requirements.txt 独有包与登记允许集不一致：多出 {sorted(extra - set(REQUIREMENTS_ONLY))}、"
        f"登记未用 {sorted(set(REQUIREMENTS_ONLY) - extra)}——"
        "新增运行时补充必须写进 REQUIREMENTS_ONLY，删除必须连动登记表"
    )
    drift = {
        name: (pin, requirements.get(name))
        for name, pin in REQUIREMENTS_ONLY.items()
        if requirements.get(name) != pin
    }
    assert not drift, (
        "requirements.txt 独有包与登记钉版不一致（登记表在替依赖吹牛）："
        + "; ".join(
            f"{name}: 登记=={pin} vs requirements=={other}"
            for name, (pin, other) in drift.items()
        )
    )


def test_requirements_dev_expands_to_requirements_plus_dev_extra() -> None:
    """W7：展开 ``-r`` 后的 requirements-dev 恰等于 requirements ∪ dev extra。"""
    _, dev_extra = _pyproject()
    requirements = _parse_requirements(REQUIREMENTS)
    requirements_dev = _parse_requirements(REQUIREMENTS_DEV)

    expected = dict(requirements)
    for name, pin in dev_extra.items():
        if name in expected and expected[name] != pin:
            raise AssertionError(
                f"dev extra 与 requirements.txt 的 {name} 版本冲突："
                f"{pin} vs {expected[name]}"
            )
        expected[name] = pin

    assert set(requirements_dev) == set(expected), (
        f"requirements-dev.txt（-r 展开）与 requirements.txt ∪ dev extra 不一致："
        f"缺 {sorted(set(expected) - set(requirements_dev))}、"
        f"多 {sorted(set(requirements_dev) - set(expected))}"
    )
    drift = {
        name: (pin, requirements_dev.get(name))
        for name, pin in expected.items()
        if requirements_dev.get(name) != pin
    }
    assert not drift, (
        "requirements-dev.txt 与 pyproject dev extra 版本漂移："
        + "; ".join(
            f"{name}: 期望=={pin} vs requirements-dev=={other}"
            for name, (pin, other) in drift.items()
        )
    )


def test_requirements_dev_is_covered_by_the_dev_lock() -> None:
    """W8：requirements-dev 的每包都在 requirements-dev.lock，钉版同账。"""
    requirements_dev = _parse_requirements(REQUIREMENTS_DEV)
    lock = _parse_requirements(DEV_LOCK)
    missing = sorted(set(requirements_dev) - set(lock))
    assert not missing, (
        f"requirements-dev.txt 有而 requirements-dev.lock 没有：{missing}——"
        "CI 从 lock 安装，顶层依赖不在锁里会直接 ModuleNotFound"
    )
    drift = {
        name: (pin, lock.get(name))
        for name, pin in requirements_dev.items()
        if lock.get(name) != pin
    }
    assert not drift, (
        "requirements-dev.txt 与 requirements-dev.lock 版本漂移："
        + "; ".join(
            f"{name}: req-dev=={pin} vs lock=={other}"
            for name, (pin, other) in drift.items()
        )
    )


def test_runtime_lock_covers_requirements() -> None:
    """W9：requirements.txt 的每包都在 requirements.lock，钉版同账。"""
    requirements = _parse_requirements(REQUIREMENTS)
    lock = _parse_requirements(RUNTIME_LOCK)
    missing = sorted(set(requirements) - set(lock))
    assert not missing, (
        f"requirements.txt 有而 requirements.lock 没有：{missing}——"
        "Dockerfile 与桌面管线安装运行时锁，漏刷会在镜像启动时才炸"
    )
    drift = {
        name: (pin, lock.get(name))
        for name, pin in requirements.items()
        if lock.get(name) != pin
    }
    assert not drift, (
        "requirements.txt 与 requirements.lock 版本漂移："
        + "; ".join(
            f"{name}: requirements=={pin} vs runtime-lock=={other}"
            for name, (pin, other) in drift.items()
        )
    )
