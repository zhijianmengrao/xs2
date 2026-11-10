"""R241：desktop-windows 编排 needs/uses ↔ job 键同账（W 系续 W65）。

背景（实测，R240 §3 登记）：desktop-windows.yml 的 jobs 键恰三个
（``build`` / ``build-macos`` / ``release``）；``release`` 的
``needs: [build, build-macos]``（L155）；``build-macos`` 以
``uses: ./.github/workflows/desktop-macos.yml``（L150）调用可复用
workflow，后者的 job 键恰一个（``build``）。needs 写错 job 名、uses
指向不存在的文件、被调 workflow 没声明 ``workflow_call``——三种漂移
都会让 GitHub 在解析期拒绝**整个** workflow（推 tag 时常规发版全断），
但仓库里此前没有任何判据把编排面与 job 键对账。

W65 钉成两半：

- **W65a 语料守卫**：顶层 job 键恰 3 个；``needs`` 恰 2 项；本地
  ``uses`` 恰 1 处。
- **W65b 编排同账**：needs 名字集合 ⊆ jobs 键集合且不自指；uses 目标
  逐处可解析、目标声明 ``workflow_call``、目标 job 键恰 1 个；调用方
  job 名 == 目标 job 键 + "-" + 平台 token（``build`` + ``-macos``）；
  uses-job 不得同时声明 ``runs-on``/``steps``，普通 job 两者都必须有。

边界：只判 job 键与调用面的名字同账——不判步骤内容、不判 matrix 展开
（W63 钉 artifact 名）、不判 ``if`` 条件的语义（tag-only 由 workflow
自身负责）、不判 GitHub 解析行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WINDOWS = "desktop-windows.yml"
USES_RX = re.compile(
    r"^\s*uses:\s*\"?\./\.github/workflows/([A-Za-z0-9_.-]+\.yml)\"?\s*$", re.M
)

EXPECTED_JOBS = {"build", "build-macos", "release"}
EXPECTED_NEEDS = {"build", "build-macos"}


def _text(name: str) -> str:
    path = WORKFLOWS / name
    assert path.is_file(), f"workflow 不在：{path}"
    return path.read_text(encoding="utf-8")


def _document(name: str) -> dict:
    document = yaml.safe_load(_text(name))
    assert isinstance(document, dict), f"{name} 不是 YAML 映射"
    return document


def _jobs(name: str) -> dict:
    jobs = _document(name).get("jobs")
    assert isinstance(jobs, dict) and jobs, f"{name} 没有 jobs 映射"
    return jobs


def _triggers(name: str) -> dict:
    """``on:`` 的映射。PyYAML 按 YAML 1.1 把裸 ``on`` 解析成布尔 True。"""
    document = _document(name)
    triggers = document.get("on", document.get(True))
    assert isinstance(triggers, dict), f"{name} 的 on: 不是映射——W65 无锚"
    return triggers


def _uses_jobs() -> dict[str, str]:
    """desktop-windows 的 {调用方 job 名: 被调 workflow 文件名}。"""
    found: dict[str, str] = {}
    for job_name, job in _jobs(WINDOWS).items():
        target = job.get("uses")
        if not target:
            continue
        match = USES_RX.match(f"uses: {target}")
        assert match, f"{WINDOWS} 的 {job_name}.uses 不是本地 workflow：{target}"
        found[job_name] = match.group(1)
    return found


def test_windows_orchestration_shape() -> None:
    """W65a：job 键恰 3、needs 恰 2 项、本地 uses 恰 1 处。"""
    jobs = _jobs(WINDOWS)
    assert set(jobs) == EXPECTED_JOBS, (
        f"{WINDOWS} 的顶层 job 键 {sorted(jobs)} != {sorted(EXPECTED_JOBS)}"
        "——W65a 语料守卫"
    )
    needs = jobs["release"].get("needs")
    assert isinstance(needs, list) and len(needs) == 2, (
        f"{WINDOWS} 的 release.needs 应恰 2 项，实测 {needs!r}"
        "——W65a 语料守卫"
    )
    uses_jobs = _uses_jobs()
    assert len(uses_jobs) == 1, (
        f"{WINDOWS} 的本地 uses-job 应恰 1 处，实测 {len(uses_jobs)} 处"
        f"（{uses_jobs}）——W65a 语料守卫"
    )


def test_windows_orchestration_agrees_with_job_keys() -> None:
    """W65b：needs ⊆ jobs、uses 可解析且可调用、调用名 == 目标 job 键 + 平台。"""
    jobs = _jobs(WINDOWS)
    violations: list[str] = []

    needs = set(jobs["release"].get("needs") or [])
    undeclared = sorted(needs - set(jobs))
    if undeclared:
        violations.append(
            f"release.needs 引用了不存在的 job：{undeclared}——GitHub 解析期"
            "拒绝整个 workflow"
        )
    if needs != EXPECTED_NEEDS:
        violations.append(
            f"release.needs {sorted(needs)} != {sorted(EXPECTED_NEEDS)}"
            "——依赖面与登记的编排不同账"
        )
    if "release" in needs:
        violations.append("release.needs 指向自己")

    uses_jobs = _uses_jobs()
    for caller, target_name in uses_jobs.items():
        target_path = WORKFLOWS / target_name
        if not target_path.is_file():
            violations.append(
                f"{caller}.uses 指向不存在的文件：{target_name}"
                "——可复用调用起不来"
            )
            continue
        triggers = _triggers(target_name)
        if "workflow_call" not in triggers:
            violations.append(
                f"{target_name} 未声明 workflow_call——{caller} 的 uses 调用"
                "在解析期被拒"
            )
        target_jobs = set(_jobs(target_name))
        if len(target_jobs) != 1:
            violations.append(
                f"{target_name} 的 job 键应恰 1 个（供 {caller} 对应），实测 "
                f"{sorted(target_jobs)}"
            )
            continue
        (target_job,) = target_jobs
        token = Path(target_name).stem.removeprefix("desktop-")
        expected_caller = f"{target_job}-{token}"
        if caller != expected_caller:
            violations.append(
                f"调用方 job 名 {caller!r} != 目标 job 键 + 平台 "
                f"（{expected_caller!r}，来自 {target_job} + {token}）"
            )

    for job_name, job in jobs.items():
        is_uses = bool(job.get("uses"))
        has_run_fields = bool(job.get("runs-on")) or bool(job.get("steps"))
        if is_uses and has_run_fields:
            violations.append(
                f"{job_name}: uses-job 同时声明了 runs-on/steps——GitHub"
                "解析期拒绝（两者互斥）"
            )
        if not is_uses and not (job.get("runs-on") and job.get("steps")):
            violations.append(
                f"{job_name}: 普通 job 缺 runs-on 或 steps——解析期拒绝"
            )

    assert not violations, (
        "desktop-windows 编排与 job 键不同账：\n" + "\n".join(violations)
    )
