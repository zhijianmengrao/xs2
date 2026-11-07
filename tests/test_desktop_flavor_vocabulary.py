"""R194：desktop flavor 词表五源闭包（W 系续 W29）。

背景（实测，R192 §3 登记、R194 开工补面）：flavor 词表登记时数到四处——
``desktop/scripts/build_macos.py`` 的 ``choices=("core", "full")`` 与运行时
集合 ``if flavor not in {...}``、``desktop/scripts/build_backend.py`` 的
``choices``、``desktop-macos.yml`` 与 ``desktop-windows.yml`` 的
``matrix.flavor``；开工实测补上第五处——
``desktop/scripts/verify_bundle.py`` 的 ``--expected-flavor`` choices
（W18/W13/W25 同型的实测补面先例）。五处现均为 ``{core, full}``。加第三
个 flavor 时五处会各自漂移：脚本 ``choices`` 拒绝新值、矩阵不展开新组合、
``verify_bundle`` 的期望值对不上候选包。W24 只钉了 macOS 范围行与 macos
矩阵的词表（``⊆ {core, full}``），Windows 矩阵与三个构建脚本没有锚。

W29 把五处钉成两半：

- **W29a 语料守卫**：五处各恰一处、可解析、非空，值都在登记词表
  ``{core, full}`` 内——扩充 flavor 先红词表，强制显式扩表并同步 README
  范围行（W24 同型）；两份 workflow 恰一个 job 带 ``flavor`` 矩阵（结构
  守卫，防「首 job 改名/换位」让锚落空）。
- **W29b 五源恰等**：五处解析出的集合两两恰等——任一处加减值显式红。

边界：只判这五处词表——不判 README 范围行与叙述段（W24 射程）、不判
矩阵的展开行为与 job 数（CI 负责）、不判 flavor 的语义（full 多捆绑
什么）、不判 ``verify_bundle`` 的其余参数。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "desktop" / "scripts"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

CHOICES_RX = re.compile(r'--(?:expected-)?flavor",\s*choices=\(([^)]*)\)')
RUNTIME_SET_RX = re.compile(r"if flavor not in \{([^}]*)\}")
TOKEN_SPLIT_RX = re.compile(r"[\"'\s,]+")

KNOWN_FLAVORS = frozenset({"core", "full"})


def _parse_vocab(raw: str) -> set[str]:
    return {token for token in TOKEN_SPLIT_RX.split(raw) if token}


def _script_vocabs() -> dict[str, set[str]]:
    vocabs: dict[str, set[str]] = {}
    sources = {
        "build_macos.py": SCRIPTS / "build_macos.py",
        "build_backend.py": SCRIPTS / "build_backend.py",
        "verify_bundle.py": SCRIPTS / "verify_bundle.py",
    }
    for filename, path in sources.items():
        text = path.read_text(encoding="utf-8")
        choices = CHOICES_RX.findall(text)
        assert len(choices) == 1, (
            f"{filename} 的 --flavor choices 应恰一处，实测 {choices}——W29 无锚"
        )
        vocabs[f"{filename} choices"] = _parse_vocab(choices[0])
    macos_text = (SCRIPTS / "build_macos.py").read_text(encoding="utf-8")
    runtime = RUNTIME_SET_RX.findall(macos_text)
    assert len(runtime) == 1, (
        f"build_macos.py 的运行时 flavor 集合应恰一处，实测 {runtime}"
        "——W29 无锚"
    )
    vocabs["build_macos.py runtime"] = _parse_vocab(runtime[0])
    return vocabs


def _workflow_flavor_matrix(path: Path) -> set[str]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    jobs = document.get("jobs") if isinstance(document, dict) else None
    assert isinstance(jobs, dict) and jobs, (
        f"{path.name} 没有 jobs 映射——W29 无锚"
    )
    found = []
    for name, job in jobs.items():
        strategy = (job or {}).get("strategy") or {}
        matrix = strategy.get("matrix") or {}
        if isinstance(matrix, dict) and "flavor" in matrix:
            found.append((name, matrix["flavor"]))
    assert len(found) == 1, (
        f"{path.name} 应恰一个 job 带 flavor 矩阵，实测 {[n for n, _ in found]}"
        "——W29 无锚"
    )
    flavors = found[0][1]
    assert isinstance(flavors, list) and flavors, (
        f"{path.name} 的 flavor 矩阵不是非空列表——W29 无锚"
    )
    return {str(flavor) for flavor in flavors}


def _all_vocabs() -> dict[str, set[str]]:
    vocabs = _script_vocabs()
    vocabs["desktop-macos.yml matrix"] = _workflow_flavor_matrix(
        WORKFLOWS / "desktop-macos.yml"
    )
    vocabs["desktop-windows.yml matrix"] = _workflow_flavor_matrix(
        WORKFLOWS / "desktop-windows.yml"
    )
    return vocabs


def test_flavor_sources_stay_in_the_registered_vocabulary() -> None:
    """W29a：五处各恰一处、非空、值都在词表 {core, full} 内。"""
    vocabs = _all_vocabs()
    for name, vocab in vocabs.items():
        assert vocab, f"{name} 解析出空 flavor 词表——W29 无锚"
        unknown = sorted(vocab - KNOWN_FLAVORS)
        assert not unknown, (
            f"{name} 出现词表外的 flavor {unknown}（词表 "
            f"{sorted(KNOWN_FLAVORS)}）——扩充 flavor 必须先显式扩词表，"
            "再同步五源与 README 范围行"
        )


def test_flavor_vocabulary_is_the_same_across_all_sources() -> None:
    """W29b：五源集合两两恰等——任一处加减值显式红。"""
    vocabs = _all_vocabs()
    distinct = {name: sorted(vocab) for name, vocab in vocabs.items()}
    reference_name = "build_macos.py choices"
    reference = vocabs[reference_name]
    for name, vocab in vocabs.items():
        assert vocab == reference, (
            f"flavor 词表不同账：{reference_name} {sorted(reference)}，"
            f"{name} {distinct[name]}——任一源加减 flavor 必须五源同步"
        )
