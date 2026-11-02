"""R101：``replay-ci-writeback`` job 的接线契约。

这些断言是**静态**的（解析 yml，不跑 GitHub）：R100 §5 的边界是「replay
不进 CI」，所以这里钉住「CI 里真的有一个生产调用者」，以及它与既有写回
job 的安全边界——写权限仍只属于 ``e2e-history-writeback``，replay job 只读、
不跑仓库测试、不引 secrets、PR 也跑。

R103 加了 ``replay-ci-fetch-chain``（下载 artifact → 写回）；R104 把这条全链
与 replay 主 job 对齐到同一组平台矩阵。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
JOB = "replay-ci-writeback"
WRITEBACK_JOB = "e2e-history-writeback"
FETCH_JOB = "replay-ci-fetch-chain"


def _load() -> dict:
    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _job(name: str) -> dict:
    jobs = _load().get("jobs")
    assert isinstance(jobs, dict)
    assert name in jobs, f"ci.yml 缺少 {name} job"
    return jobs[name]


def _text(job: dict) -> str:
    return json.dumps(job, ensure_ascii=False)


def _matrix(job: dict) -> set[tuple[str, str]]:
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    include = matrix.get("include") or []
    return {(entry.get("os"), entry.get("python")) for entry in include}


def _driver_steps() -> list[dict]:
    return [
        step for step in _job(JOB)["steps"]
        if "scripts/replay_ci_scenarios.py" in str(step.get("run", ""))
    ]


def test_replay_job_exists_and_is_bounded() -> None:
    """R99 的能力必须有一个生产调用者；R103 起两平台同定义。"""
    job = _job(JOB)
    assert job.get("runs-on") == "${{ matrix.os }}"
    include = (job.get("strategy") or {}).get("matrix", {}).get("include", [])
    assert {(entry.get("os"), entry.get("python")) for entry in include} == {
        ("ubuntu-24.04", "python3"),
        ("windows-latest", "python"),
    }
    env = job.get("env") or {}
    assert env.get("PYTHONUTF8") == "1", "Windows 控制台默认编码会打穿中文输出"
    timeout = job.get("timeout-minutes")
    assert isinstance(timeout, int) and 0 < timeout <= 30, timeout


def test_replay_job_is_read_only() -> None:
    """写权限只能属于 e2e-history-writeback（既有契约有硬断言）。"""
    document = _load()
    top = document.get("permissions") or {}
    assert top.get("contents") == "read"
    permissions = _job(JOB).get("permissions") or {}
    assert permissions.get("contents") != "write", (
        "replay job 声明了 contents: write；写权限与仓库代码执行面必须分离")
    writers = [
        name for name, job in document["jobs"].items()
        if (job.get("permissions") or {}).get("contents") == "write"
    ]
    assert writers == [WRITEBACK_JOB], writers


def test_replay_job_invokes_the_driver_once() -> None:
    steps = _driver_steps()
    assert len(steps) == 1, f"replay 驱动调用点应恰好一处，实际 {len(steps)} 处"
    run = str(steps[0]["run"])
    for token in (
        "--repo .",
        "--branch main",
        "--summary",
        "--result-json",
    ):
        assert token in run, f"replay 驱动调用缺少 {token!r}"
    assert "exit $code" in run, "没有把驱动的退出码透传出去"


def test_replay_job_does_not_run_repository_tests() -> None:
    """生产 job 只跑回放驱动；回到 pytest 就等于 R100 §5 的边界没消掉。"""
    text = _text(_job(JOB))
    for forbidden in (
        "pytest", "e2e_workflow_stub.py", "npm ", "docker ",
        "continue-on-error", "secrets.",
    ):
        assert forbidden not in text, f"replay job 出现了 {forbidden!r}"


def test_replay_job_runs_on_pull_requests_too() -> None:
    """合入前就要跑：不能把 job 限死在 main push。"""
    assert _job(JOB).get("if") is None, (
        "replay job 加了 if 条件；PR 将失去这条回放覆盖")


def test_replay_job_uploads_its_result_even_on_failure() -> None:
    uploads = [
        step for step in _job(JOB)["steps"]
        if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert len(uploads) == 1, uploads
    upload = uploads[0]
    assert "replay-ci-result" in _text({"upload": upload})
    assert upload.get("if") == "always()", (
        "失败时不上传 result 工件，现场只能靠翻日志")


def test_replay_job_materializes_main_for_the_sandbox_clone() -> None:
    """PR 的 checkout 是 detached HEAD；replay 需要本地 main 分支。"""
    runs = [str(step.get("run", "")) for step in _job(JOB)["steps"]]
    assert any("git checkout -B main" in run for run in runs), (
        "没有为 replay 的 clone -b main 准备本地分支")


def test_replay_job_is_not_permanently_green() -> None:
    """非零退出必须让这一步红，不能降级成 warning/exit 0。"""
    run = str(_driver_steps()[0]["run"])
    assert "::error::" in run
    assert "exit $code" in run
    assert "exit 0" not in run


def test_writeback_job_still_does_not_run_replay() -> None:
    """写权限 job 不执行仓库代码；replay 不能塞进 e2e-history-writeback。"""
    assert "replay_ci_scenarios.py" not in _text(_job(WRITEBACK_JOB))


# ------------------------------------------- 全链 job（R103）
def _fetch_steps() -> list[dict]:
    return [
        step for step in _job(FETCH_JOB)["steps"]
        if "scripts/replay_ci_scenarios.py" in str(step.get("run", ""))
    ]


def test_fetch_chain_job_is_push_only_and_waits_for_the_uploader() -> None:
    """artifact 只在 main push 的 backend 里产生：不能提前、不能跑 PR。"""
    job = _job(FETCH_JOB)
    assert job.get("needs") == "backend"
    condition = str(job.get("if"))
    for token in (
        "github.event_name == 'push'",
        "github.ref == 'refs/heads/main'",
        "needs.backend.result == 'success'",
    ):
        assert token in condition, f"全链 job 条件缺少 {token!r}"


def test_fetch_chain_job_runs_on_the_same_platforms_as_replay() -> None:
    """R104：全链不能再是单平台；否则 Windows 只覆盖了 replay 的一半链路。"""
    job = _job(FETCH_JOB)
    assert job.get("runs-on") == "${{ matrix.os }}"
    assert _matrix(job) == _matrix(_job(JOB)) == {
        ("ubuntu-24.04", "python3"),
        ("windows-latest", "python"),
    }
    assert (job.get("strategy") or {}).get("fail-fast") is False, (
        "一条平台腿失败不应取消另一条")
    env = job.get("env") or {}
    assert env.get("PYTHONUTF8") == "1", "Windows 控制台默认编码会打穿中文输出"
    assert env.get("PYTHONIOENCODING") == "utf-8"
    timeout = job.get("timeout-minutes")
    assert isinstance(timeout, int) and 0 < timeout <= 30, timeout


def test_fetch_chain_job_uses_bash_and_the_matrix_python() -> None:
    """Windows 默认 shell 是 pwsh：bash 写法与解释器名都必须显式。"""
    step = _fetch_steps()[0]
    assert step.get("shell") == "bash", (
        "全链驱动步骤没有 shell: bash；Windows 上 exit $code 会变成 pwsh 语法")
    env = step.get("env") or {}
    assert env.get("PYTHON") == "${{ matrix.python }}"
    run = str(step["run"])
    assert '"$PYTHON" scripts/replay_ci_scenarios.py' in run
    assert "python3 scripts/replay_ci_scenarios.py" not in run, (
        "windows-latest 没有 python3 这个命令名")


def test_fetch_chain_job_is_read_only_but_can_read_actions() -> None:
    permissions = _job(FETCH_JOB).get("permissions") or {}
    assert permissions.get("contents") == "read"
    assert permissions.get("actions") == "read"
    assert permissions.get("contents") != "write"


def test_fetch_chain_job_uses_the_real_api_and_a_separate_run_id() -> None:
    steps = _fetch_steps()
    assert len(steps) == 1, f"全链驱动调用点应恰好一处，实际 {len(steps)} 处"
    step = steps[0]
    run = str(step["run"])
    for token in (
        "--fetch-api-url",
        "--fetch-run-id",
        "--fetch-repo",
        "${{ github.run_id }}",
        "${{ github.repository }}",
        "--result-json",
        "exit $code",
    ):
        assert token in run, f"全链驱动调用缺少 {token!r}"
    env = step.get("env") or {}
    assert env.get("GITHUB_TOKEN") == "${{ github.token }}", (
        "全链只允许用仓库 token；用 secrets 会让 fork PR 不可复现")
    text = _text(_job(FETCH_JOB))
    for forbidden in ("pytest", "continue-on-error", "secrets."):
        assert forbidden not in text, f"全链 job 出现了 {forbidden!r}"


def test_fetch_chain_job_uploads_its_result_even_on_failure() -> None:
    uploads = [
        step for step in _job(FETCH_JOB)["steps"]
        if "upload-artifact" in str(step.get("uses", ""))
    ]
    assert len(uploads) == 1, uploads
    upload = uploads[0]
    assert "replay-fetch-result-${{ matrix.os }}" in _text({"upload": upload}), (
        "两条矩阵腿的上传名会撞车")
    assert upload.get("if") == "always()", (
        "失败时不上传全链 result 工件，现场只能靠翻日志")
