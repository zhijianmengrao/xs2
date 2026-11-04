"""R135：CI 闸门形状——job 清单恰等与欠引用 job 的形状。

背景（实测，R134 §9）：`.github/workflows/` 的四个 workflow 里，
``desktop-macos.yml``（test_desktop_packaging）、``replace-desktop-assets.yml``
（test_ci_gate_wiring）、replay/writeback/fetch-chain 与 backend 的接线
（test_ci_replay_wiring / test_ci_history_writeback / test_ci_gate_wiring）
都已有钉测，但 **ci.yml 的顶层 job 清单没有一处「恰等」断言**：
``test_write_permission_belongs_only_to_the_writeback_job`` 只遍历在册 job
查写权限归属，删除一个 job 其余照旧通过。逐名 grep 实测：``frontend`` 在
tests/ 里 **零引用**——今天删掉 frontend job，全套 2902 条用例照样全绿。

本文件补两条不变量：

- **I1 清单恰等**：ci.yml 顶层 job 键集合必须**恰好**等于八个在册 job
  （矩阵展开后即索引 §1 的「10 个 job」口径）；多出的 job（哪怕不带写
  权限）与缺失的 job 都判红。新 job 必须走「改清单 + handover 记账」的
  显式路径，不允许悄悄出现/消失。
- **I2 欠引用 job 的形状**：对零引用的 ``frontend`` 与引用最少的
  ``windows-backend``，钉住 runs-on 与关键步骤（前端四连、Windows 五个
  快照闸门 + 存量名字审计）——这两个 job 是 web 面与 Windows 闸门面在
  CI 里的唯一载体，步骤被删不再隐形。

边界：不判 job 的业务输出好坏（那是闸门脚本自己的判据，R51–R60）；不钉
非关键步骤的顺序与超时数——本文件只守「闸门还在、载体没空」。
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# 顶层 job 键（矩阵 job 在 CI 展开后各占 2 个 run，见 I1/展开口径）。
EXPECTED_JOBS = frozenset(
    {
        "backend",
        "windows-backend",
        "frontend",
        "container-config",
        "container-build",
        "replay-ci-writeback",
        "replay-ci-fetch-chain",
        "e2e-history-writeback",
    }
)
MATRIX_PLATFORMS = {"ubuntu-24.04", "windows-latest"}
FRONTEND_STEPS = ("npm ci", "npm run lint", "npm test", "npm run build")
WINDOWS_GATE_STEPS = (
    "Provider failure-rate gate against real snapshot",
    "Snapshot historical-baseline regression gate",
    "Snapshot per-workflow regression gate",
    "Snapshot sample-size gate",
    "Snapshot per-workflow failure-rate gate",
    "Storage name audit (read-only)",
)


def _load(name: str) -> dict:
    path = WORKFLOWS / name
    assert path.exists() and path.stat().st_size > 0, f"workflow 缺失或为空：{path}"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{name} 顶层不是映射"
    return document


def _ci_jobs() -> dict:
    jobs = _load("ci.yml").get("jobs")
    assert isinstance(jobs, dict) and jobs, "ci.yml 没有 jobs 映射"
    return jobs


def test_all_four_workflow_files_exist_and_parse() -> None:
    """四个 workflow 文件在库且可解析（删除任何一个文件都直接红）。"""
    for name in (
        "ci.yml",
        "desktop-macos.yml",
        "desktop-windows.yml",
        "replace-desktop-assets.yml",
    ):
        _load(name)


def test_ci_job_inventory_is_exact() -> None:
    """I1：顶层 job 键集合恰等——多一个、少一个都红（frontend 零引用的补牢）。"""
    actual = set(_ci_jobs())
    missing = sorted(EXPECTED_JOBS - actual)
    extra = sorted(actual - EXPECTED_JOBS)
    assert not missing and not extra, (
        "ci.yml job 清单漂移："
        f"缺失 {missing}，多出 {extra}。新 job 必须同步更新本清单并在 "
        "handover 记账（R135 实测 frontend 零测试引用，删除曾无任何用例判红）。"
    )


def test_matrix_jobs_expand_to_ten_runs() -> None:
    """矩阵展开口径：replay/fetch-chain 各两平台，合计 10 个 job run。"""
    expanded = 0
    for name, job in _ci_jobs().items():
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        include = matrix.get("include") or []
        if include:
            platforms = {entry.get("os") for entry in include}
            assert platforms == MATRIX_PLATFORMS, (name, platforms)
            expanded += len(include)
        else:
            expanded += 1
    assert expanded == 10, f"矩阵展开后应为 10 个 job run，实为 {expanded}"


def test_frontend_job_shape() -> None:
    """I2a：frontend（零引用 job）——ubuntu + 前端四连按序在场。"""
    job = _ci_jobs()["frontend"]
    assert job.get("runs-on") == "ubuntu-latest", job.get("runs-on")
    runs = [
        (step.get("run") or "").strip()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]
    cursor = 0
    for needle in FRONTEND_STEPS:
        while cursor < len(runs) and needle not in runs[cursor]:
            cursor += 1
        assert cursor < len(runs), (
            f"frontend job 缺步骤或顺序漂移：{needle!r}（steps={runs}）"
        )
        cursor += 1


def test_windows_backend_job_shape() -> None:
    """I2b：windows-backend——windows runner + 五个快照闸门与名字审计在场。"""
    job = _ci_jobs()["windows-backend"]
    assert str(job.get("runs-on", "")).startswith("windows-"), job.get("runs-on")
    names = [
        (step.get("name") or "").strip()
        for step in job.get("steps", [])
        if isinstance(step, dict)
    ]
    missing = [n for n in WINDOWS_GATE_STEPS if n not in names]
    assert not missing, f"windows-backend 缺闸门/审计步骤：{missing}（steps={names}）"
