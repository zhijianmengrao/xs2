"""R88：CI 回写 e2e 重跑历史的接线契约。

R81 §7 曾给出「不做」的代价表，R85 的用户拍定改为「做」。这里钉住两条底线：

1. **安全**：``contents: write`` 只给独立的写回 job，而它不执行任何仓库测试
   （pytest / e2e / npm / docker）——写权限与不可信代码的执行面不重叠；
   顶层与其它 job 仍是 ``contents: read``。
2. **幂等**：写回只发生在 main 的 push 上；``run_id`` 用 ``github.run_id``
   而不是 ``run_attempt``，同一 run 重跑覆盖同一轮而不是新增一轮。

趋势本身仍不判好坏（R78）：写回只负责「有历史」，判定语义不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
HISTORY = REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history" / "history.json"


def _ci() -> dict:
    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _job(name: str) -> dict:
    jobs = _ci()["jobs"]
    assert name in jobs, f"ci.yml 缺少 {name} job"
    return jobs[name]


def _writeback() -> dict:
    return _job("e2e-history-writeback")


def _text(job: dict) -> str:
    return json.dumps(job, ensure_ascii=False)


def test_write_permission_belongs_only_to_the_writeback_job() -> None:
    """``contents: write`` 只给写回 job；顶层与其它 job 仍是 read。"""
    document = _ci()
    assert (document.get("permissions") or {}).get("contents") == "read"
    writers = [
        name for name, job in document["jobs"].items()
        if (job.get("permissions") or {}).get("contents") == "write"
    ]
    assert writers == ["e2e-history-writeback"], writers


def test_writeback_only_runs_on_main_pushes() -> None:
    condition = str(_writeback().get("if", ""))
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    # backend 失败也要写（失败的轮次对趋势有价值），只有取消才跳过。
    assert "needs.backend.result" in condition


def test_writeback_job_runs_no_repository_tests() -> None:
    """写权限 job 不能执行仓库代码：它只跑历史归档脚本。"""
    text = _text(_writeback())
    for forbidden in ("pytest", "e2e_workflow_stub.py", "npm ", "docker "):
        assert forbidden not in text, f"写回 job 执行了 {forbidden!r}"
    assert "python3 scripts/ci_writeback_history.py" in text


def test_backend_uploads_the_metrics_artifact_only_on_main_pushes() -> None:
    uploads = [
        step for step in _job("backend")["steps"]
        if "upload-artifact" in str(step.get("uses", ""))
        and "e2e-metrics" in json.dumps(step, ensure_ascii=False)
    ]
    assert len(uploads) == 1, uploads
    condition = str(uploads[0].get("if", ""))
    assert "github.event_name == 'push'" in condition
    assert "github.ref == 'refs/heads/main'" in condition


def test_writeback_fetches_the_same_artifact_name() -> None:
    """R95：下载侧也只剩委托——YAML 不再内联 ``download-artifact``。

    传输语义（命名过滤、缺 artifact 退出 0、传输错误退出 1、跳转去认证头）
    由 ``tests/test_fetch_ci_artifact.py`` 用假 HTTP 服务驱动。
    """
    text = _text(_writeback())
    assert "fetch_ci_artifact.py" in text
    assert "--artifact e2e-metrics" in text
    assert "download-artifact" not in text


def test_writeback_can_read_the_actions_api() -> None:
    """显式声明 permissions 后，未列出的 scope 就是 none。"""
    permissions = _writeback().get("permissions") or {}
    assert permissions.get("contents") == "write"
    assert permissions.get("actions") == "read"


def test_fetch_step_is_loud_on_transport_errors() -> None:
    """缺 artifact 不是失败，传输错误必须响亮——不能再有 continue-on-error。"""
    steps = [
        step for step in _writeback()["steps"]
        if "fetch_ci_artifact.py" in str(step.get("run", ""))
    ]
    assert len(steps) == 1, steps
    step = steps[0]
    assert "continue-on-error" not in step
    run = str(step.get("run", ""))
    for required in (
        '--repo "${{ github.repository }}"',
        '--run-id "${{ github.run_id }}"',
        "--artifact e2e-metrics",
        '--path "$RUNNER_TEMP/e2e"',
    ):
        assert required in run, required
    assert "GITHUB_TOKEN" in (step.get("env") or {})


def _record_run() -> str:
    """定位「跑写回脚本的那一步」的 run 正文，不拿注释做断言。"""
    hits = [
        str(step.get("run", "")) for step in _writeback()["steps"]
        if "ci_writeback_history.py" in str(step.get("run", ""))
    ]
    assert len(hits) == 1, hits
    return hits[0]


def test_writeback_uses_run_id_not_run_attempt() -> None:
    """同一 run 重跑覆盖同一轮（R78 的「同 id 覆盖」契约）。"""
    run = _record_run()
    assert '--run-id "ci-${{ github.run_id }}"' in run
    assert "run_attempt" not in run


def test_writeback_delegates_retry_to_the_script() -> None:
    """重试逻辑只有一份：YAML 只调用脚本，不能再内联 git 循环。

    R80 的教训：同一个事实写两处，两处就会分裂。R89 之前重试循环只存在于
    YAML 里（本地跑不了、只能做子串断言），现在它的行为由
    ``tests/test_ci_writeback_history.py`` 用真实 git 仓驱动，YAML 只剩委托。
    """
    text = _text(_writeback())
    assert "ci_writeback_history.py" in text
    assert '--summary "$GITHUB_STEP_SUMMARY"' in _record_run()
    for inlined in ("git push", "pull --rebase", "for attempt"):
        assert inlined not in text, f"重试逻辑又写回 YAML 了：{inlined!r}"
    # [skip ci] 仍在提交信息里：GITHUB_TOKEN 的 push 本不触发 workflow，
    # 这条是为将来换成 PAT 留的保险。
    assert "[skip ci]" in text


def test_backend_prechecks_metrics_on_pull_requests() -> None:
    """R92：PR 上只做 ``--check-only`` 预检，不写、不提交、不推。

    写权限与执行面分离不变：预检跑在 backend（contents: read），
    ``--check-only`` 保证它不会落盘。
    """
    steps = _job("backend")["steps"]
    hits = [
        step for step in steps
        if "--check-only" in json.dumps(step, ensure_ascii=False)
    ]
    assert len(hits) == 1, hits
    step = hits[0]
    assert "github.event_name == 'pull_request'" in str(step.get("if", ""))
    run = str(step.get("run", ""))
    assert "e2e_retry_history.py record" in run
    assert "--check-only" in run
    text = json.dumps(step, ensure_ascii=False)
    for forbidden in ("git commit", "git push", "upload-artifact"):
        assert forbidden not in text, f"预检步骤做了 {forbidden!r}"


def test_writeback_serializes_concurrent_runs() -> None:
    concurrency = _writeback().get("concurrency") or {}
    assert concurrency.get("group") == "e2e-history-writeback"
    assert concurrency.get("cancel-in-progress") is False


def test_committed_history_is_still_valid_for_the_writer() -> None:
    """写回的目标文件必须能被 record/check 原样接受（形状不变）。"""
    from scripts import e2e_retry_history as history

    payload = json.loads(HISTORY.read_text(encoding="utf-8"))
    entries = history.validate_history(payload)
    assert entries, "入库历史为空：写回没有可追加的基线"
