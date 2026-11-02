"""R101/R103：生产回放驱动 ``scripts/replay_ci_scenarios.py`` 的行为用例。

这里驱动的是**真实** ``replay_ci_writeback`` 子进程（临时 git 仓），断言五个
本地场景（``--fetch-api-url`` 时再追加两个全链场景）的退出码/rounds/
push_attempts/失败沙箱与源仓库只读；另外用 monkeypatch 证明驱动不盲信子调用
的退出码、且能发现源仓库被改动。CI job 本身的接线契约在
``tests/test_ci_replay_wiring.py``。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from scripts import replay_ci_scenarios as scenarios
from artifact_api_fixture import api_path, listing, server, zip_bytes

HISTORY_REL = "tests/fixtures/e2e_retry_history/history.json"


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=None if cwd is None else str(cwd),
        capture_output=True)
    assert result.returncode == 0, (
        (result.stderr or result.stdout).decode("utf-8", "replace"))
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _seed(tmp_path: Path) -> Path:
    """一个普通的、带一次提交的源仓库（历史为空）。"""
    repo = tmp_path / "source"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    target = repo / HISTORY_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"schema": 1, "history": []}), encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "seed", cwd=repo)
    return repo


def _entry(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "exported_at": "2026-11-02T00:00:00+00:00",
        "source": "local",
        "total": 1, "passed": 1, "failed": 0, "retried": 0, "attempts": 1,
        "scenarios": [{"name": "happy", "passed": True, "attempts": 1,
                       "first_failure": ""}],
    }


def _argv(repo: Path, result: Path, summary: Path | None = None,
          extra: list[str] | None = None) -> list[str]:
    argv = ["--repo", str(repo), "--branch", "main",
            "--result-json", str(result)]
    if summary is not None:
        argv += ["--summary", str(summary)]
    if extra:
        argv += extra
    return argv


def _seed_with_rounds(tmp_path: Path, count: int) -> Path:
    """带 count 轮既有历史的源仓库（用于窗口边界）。"""
    repo = _seed(tmp_path)
    target = repo / HISTORY_REL
    target.write_text(json.dumps({
        "schema": 1,
        "history": [_entry(f"seed-{index}") for index in range(count)],
    }), encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", f"seed {count} rounds", cwd=repo)
    return repo


def _metrics_file(tmp_path: Path) -> Path:
    """测试用 artifact：10 场景，与生产 e2e metrics 同形（R107）。

    驱动自己的本地夹具是 3 场景；全链场景钉 total=10，所以夹具必须与生产
    artifact 同形，否则「来源」断言测的就不是生产形状。
    """
    path = tmp_path / "fetched-metrics.json"
    scenarios = [
        {"name": f"fetched_{index}", "passed": True, "attempts": 1,
         "first_failure": ""}
        for index in range(10)
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 10, "passed": 10, "failed": 0, "retried": 0,
        "scenarios": scenarios}), encoding="utf-8")
    return path


def _scenario_name(run_id: str) -> str:
    return run_id[len("replay-ci-"):].rsplit("-", 1)[0]


def _fake_invoke(*, push_attempts: int | None = None,
                 last_run_id: str | None = None,
                 rounds: int | None = None,
                 mutate: Path | None = None,
                 rejection_lines: int = 3):
    """模拟 replay 子进程：写 result JSON 与关键输出，返回 (code, output)。"""

    def invoke(argv: list[str]) -> tuple[int, str]:
        result_path = Path(argv[argv.index("--result-json") + 1])
        run_id = argv[argv.index("--run-id") + 1]
        name = _scenario_name(run_id)

        if mutate is not None:
            payload = json.loads(mutate.read_text(encoding="utf-8"))
            payload["history"].append(_entry("mutated-by-replay"))
            mutate.write_text(json.dumps(payload), encoding="utf-8")

        if name == "permanently-rejected":
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "push-rejected", "detail": "", "exit_code": 1,
                "rounds": 0 if rounds is None else rounds,
                "last_run_id": last_run_id,
                "window_full": False, "push_attempts": 3, "dry_run": False,
            }
            lines = []
            for attempt in range(1, rejection_lines + 1):
                lines.append(f"push 被拒（第 {attempt} 次），"
                             f"rebase 到最新 main 后重试")
                lines.append("simulated rejection")
            lines.append("::error::连续 3 次写回均失败"
                         "（最后一次：push-rejected），本轮历史未入库")
            sandbox = Path(tempfile.mkdtemp(prefix="fake-replay-sandbox-"))
            lines.append(f"replay：沙箱保留在 {sandbox}（失败现场）")
            output = "\n".join(lines) + "\n"
        elif name == "rejected-conflict":
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "push-rejected", "detail": "", "exit_code": 1,
                "rounds": 1 if rounds is None else rounds,
                "last_run_id": ("replay-conflict" if last_run_id is None
                                else last_run_id),
                "window_full": False, "push_attempts": 3, "dry_run": False,
            }
            lines = ["rebase 冲突（第 1 次）：丢弃本次写回提交，"
                     "按最新 main 重算"]
            for attempt in range(1, 4):
                lines.append(f"push 被拒（第 {attempt} 次），"
                             f"rebase 到最新 main 后重试")
            # 第一次是非快进拒绝，钩子只拒绝后两次（与真实观测一致）。
            lines.extend(["simulated rejection"] * max(rejection_lines - 1, 0))
            lines.append("::error::连续 3 次写回均失败"
                         "（最后一次：push-rejected），本轮历史未入库")
            sandbox = Path(tempfile.mkdtemp(prefix="fake-replay-sandbox-"))
            lines.append(f"replay：沙箱保留在 {sandbox}（失败现场）")
            output = "\n".join(lines) + "\n"
        elif name == "rejected-hook-conflict":
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "push-rejected", "detail": "", "exit_code": 1,
                "rounds": 1 if rounds is None else rounds,
                "last_run_id": ("replay-conflict" if last_run_id is None
                                else last_run_id),
                "window_full": False, "push_attempts": 3, "dry_run": False,
            }
            lines = ["rebase 冲突（第 1 次）：丢弃本次写回提交，"
                     "按最新 main 重算"]
            for attempt in range(1, 4):
                lines.append(f"push 被拒（第 {attempt} 次），"
                             f"rebase 到最新 main 后重试")
                lines.append("simulated rejection")
            lines.append("::error::连续 3 次写回均失败"
                         "（最后一次：push-rejected），本轮历史未入库")
            sandbox = Path(tempfile.mkdtemp(prefix="fake-replay-sandbox-"))
            lines.append(f"replay：沙箱保留在 {sandbox}（失败现场）")
            output = "\n".join(lines) + "\n"
        elif name == "rejected-hook-budget-2":
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "written", "detail": "", "exit_code": 0,
                "rounds": 2 if rounds is None else rounds,
                "last_run_id": run_id if last_run_id is None else last_run_id,
                "window_full": False,
                "push_attempts": 3 if push_attempts is None else push_attempts,
                "dry_run": False,
            }
            output = (
                "rebase 冲突（第 1 次）：丢弃本次写回提交，"
                "按最新 main 重算\n"
                "push 被拒（第 1 次），rebase 到最新 main 后重试\n"
                "simulated rejection\n"
                "push 被拒（第 2 次），rebase 到最新 main 后重试\n"
                "simulated rejection\n"
                "已写回 main（第 3 次尝试）\n")
        elif name in ("rejected-hook-conflict-at-2",
                      "rejected-hook-inject-at-3"):
            # R112：注入点在第 N 次拒绝；失败结局与 N=1 相同（远端只多出
            # 注入轮），区别只在「rebase 冲突（第 N 次）」和安装行的 N。
            conflict_at = 2 if name.endswith("at-2") else 3
            # 注入在最后一次拒绝时，重试循环看到的最后一次失败是 rebase
            # 冲突，不是 push 被拒（R112 实测）。
            last_reason = ("rebase-conflict" if conflict_at == 3
                           else "push-rejected")
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": last_reason, "detail": "", "exit_code": 1,
                "rounds": 1 if rounds is None else rounds,
                "last_run_id": ("replay-conflict" if last_run_id is None
                                else last_run_id),
                "window_full": False, "push_attempts": 3, "dry_run": False,
            }
            lines = [f"replay：已安装拒绝钩子（前 3 次 push 被拒，"
                     f"第 {conflict_at} 次拒绝时注入冲突）"]
            for attempt in range(1, 4):
                lines.append(f"push 被拒（第 {attempt} 次），"
                             f"rebase 到最新 main 后重试")
                lines.append("simulated rejection")
                if attempt == conflict_at:
                    lines.append(f"rebase 冲突（第 {conflict_at} 次）："
                                 f"丢弃本次写回提交，按最新 main 重算")
            lines.append("::error::连续 3 次写回均失败"
                         f"（最后一次：{last_reason}），本轮历史未入库")
            sandbox = Path(tempfile.mkdtemp(prefix="fake-replay-sandbox-"))
            lines.append(f"replay：沙箱保留在 {sandbox}（失败现场）")
            output = "\n".join(lines) + "\n"
        elif name == "rejected-hook-budget-2-at-2":
            # R112：注入点与预算都在第 2 次拒绝；第三次 push 成功。
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "written", "detail": "", "exit_code": 0,
                "rounds": 2 if rounds is None else rounds,
                "last_run_id": run_id if last_run_id is None else last_run_id,
                "window_full": False,
                "push_attempts": 3 if push_attempts is None else push_attempts,
                "dry_run": False,
            }
            output = (
                "replay：已安装拒绝钩子（前 2 次 push 被拒，"
                "第 2 次拒绝时注入冲突）\n"
                "push 被拒（第 1 次），rebase 到最新 main 后重试\n"
                "simulated rejection\n"
                "push 被拒（第 2 次），rebase 到最新 main 后重试\n"
                "simulated rejection\n"
                "rebase 冲突（第 2 次）：丢弃本次写回提交，"
                "按最新 main 重算\n"
                "已写回 main（第 3 次尝试）\n")
        else:
            expected_pushes = 2 if name in ("rejected", "conflict") else 1
            payload = {
                "schema": 1, "run_id": run_id, "source": "ci",
                "reason": "written", "detail": "", "exit_code": 0,
                "rounds": (2 if name == "conflict" else 1)
                          if rounds is None else rounds,
                "last_run_id": run_id if last_run_id is None else last_run_id,
                "window_full": False,
                "push_attempts": (expected_pushes
                                  if push_attempts is None
                                  else push_attempts),
                "dry_run": False,
            }
            output = "已写回 main（第 1 次尝试）\n"
            if name == "rejected":
                output += ("simulated rejection\n"
                           "push 被拒（第 1 次），rebase 到最新 main 后重试\n"
                           "已写回 main（第 2 次尝试）\n")
            if name == "conflict":
                output += ("rebase 冲突（第 1 次）：丢弃本次写回提交，"
                           "按最新 main 重算\n"
                           "已写回 main（第 2 次尝试）\n")

        result_path.write_text(json.dumps(payload), encoding="utf-8")
        failed = name in ("permanently-rejected", "rejected-conflict",
                          "rejected-hook-conflict",
                          "rejected-hook-conflict-at-2",
                          "rejected-hook-inject-at-3")
        return (1 if failed else 0), output

    return invoke


def test_driver_runs_all_local_scenarios(tmp_path: Path) -> None:
    repo = _seed(tmp_path)
    head = _git("rev-parse", "HEAD", cwd=repo)
    short = head[:8]
    history_bytes = (repo / HISTORY_REL).read_bytes()
    result = tmp_path / "result.json"
    summary = tmp_path / "summary.md"

    code = scenarios.main(_argv(repo, result, summary))

    assert code == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["before"] == 0
    assert payload["max_rounds"] == scenarios.history.MAX_ROUNDS
    assert payload["window_full"] is False
    assert payload["source_head"] == head
    by_name = {record["name"]: record for record in payload["scenarios"]}
    assert list(by_name) == [
        "happy", "rejected", "conflict", "permanently-rejected",
        "rejected-conflict", "rejected-hook-conflict",
        "rejected-hook-budget-2", "rejected-hook-conflict-at-2",
        "rejected-hook-budget-2-at-2", "rejected-hook-inject-at-3"]
    assert by_name["happy"]["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 1,
        "last_run_id": f"replay-ci-happy-{short}",
        "push_attempts": 1}
    assert by_name["rejected"]["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 1,
        "last_run_id": f"replay-ci-rejected-{short}",
        "push_attempts": 2}
    assert by_name["conflict"]["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 2,
        "last_run_id": f"replay-ci-conflict-{short}",
        "push_attempts": 2}
    assert by_name["permanently-rejected"]["actual"] == {
        "exit_code": 1, "reason": "push-rejected", "rounds": 0,
        "last_run_id": None,
        "push_attempts": 3}
    # R105：组合场景远端只多出注入的冲突轮，本轮没有入库。
    assert by_name["rejected-conflict"]["actual"] == {
        "exit_code": 1, "reason": "push-rejected", "rounds": 1,
        "last_run_id": "replay-conflict",
        "push_attempts": 3}
    # R108：钩子首次拒绝时注入冲突；预算 3 全失败。
    assert by_name["rejected-hook-conflict"]["actual"] == {
        "exit_code": 1, "reason": "push-rejected", "rounds": 1,
        "last_run_id": "replay-conflict",
        "push_attempts": 3}
    # R108：同一夹具预算 2 → 第三次 push 成功，注入轮 + 本轮 = 2。
    assert by_name["rejected-hook-budget-2"]["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 2,
        "last_run_id": f"replay-ci-rejected-hook-budget-2-{short}",
        "push_attempts": 3}
    # R112：注入点第 2 次、预算 3 → 仍在第 3 次耗尽；冲突轮进远端。
    assert by_name["rejected-hook-conflict-at-2"]["actual"] == {
        "exit_code": 1, "reason": "push-rejected", "rounds": 1,
        "last_run_id": "replay-conflict",
        "push_attempts": 3}
    # R112：注入点第 2 次、预算 2 → 第三次成功；注入轮 + 本轮 = 2。
    assert by_name["rejected-hook-budget-2-at-2"]["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 2,
        "last_run_id": f"replay-ci-rejected-hook-budget-2-at-2-{short}",
        "push_attempts": 3}
    # R112：预算与注入点都在第 3 次；没有下一次重试去消化冲突，
    # 因此最后一次失败是 rebase 冲突（不是 push 被拒）。
    assert by_name["rejected-hook-inject-at-3"]["actual"] == {
        "exit_code": 1, "reason": "rebase-conflict", "rounds": 1,
        "last_run_id": "replay-conflict",
        "push_attempts": 3}
    for record in payload["scenarios"]:
        assert record["ok"] is True, record["failure"]
        assert record["source_mutated"] is False
        assert record["rounds_clipped"] is False
    # 失败沙箱必须真的留下过，再被驱动清理；不能只在输出里说一句。
    for name in ("permanently-rejected", "rejected-conflict",
                 "rejected-hook-conflict",
                 "rejected-hook-conflict-at-2",
                 "rejected-hook-inject-at-3"):
        failed = by_name[name]
        assert failed["sandbox_cleaned"] is True
        assert failed["sandbox"] is not None
        assert not Path(failed["sandbox"]).exists(), (
            "驱动报告已清理，但失败沙箱仍在磁盘上")

    # 源仓库一个字节都不该动。
    assert _git("rev-parse", "HEAD", cwd=repo) == head
    assert (repo / HISTORY_REL).read_bytes() == history_bytes
    assert _git("status", "--porcelain", cwd=repo) == ""

    # step summary 每个场景一行，reason 是 ok。
    text = summary.read_text(encoding="utf-8")
    assert text.count("replay-ci-") == 10
    assert "**ok**" in text


def test_driver_counts_the_simulated_rejections(
        tmp_path: Path, monkeypatch) -> None:
    """永久拒绝必须看到 3 次钩子拒绝；1 次传输故障不能冒充。"""
    repo = _seed(tmp_path)
    monkeypatch.setattr(scenarios, "_invoke_replay",
                        _fake_invoke(rejection_lines=1))
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 1
    payload = json.loads(result.read_text(encoding="utf-8"))
    by_name = {record["name"]: record for record in payload["scenarios"]}
    permanent = by_name["permanently-rejected"]
    assert permanent["ok"] is False
    assert "出现 1 次，期望 3 次" in permanent["failure"]


def test_driver_does_not_trust_the_replay_exit_code(
        tmp_path: Path, monkeypatch) -> None:
    """子调用退 0 但 result 里的 push_attempts 不对：驱动必须判 1。"""
    repo = _seed(tmp_path)
    monkeypatch.setattr(scenarios, "_invoke_replay",
                        _fake_invoke(push_attempts=1))
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 1
    payload = json.loads(result.read_text(encoding="utf-8"))
    by_name = {record["name"]: record for record in payload["scenarios"]}
    assert by_name["happy"]["ok"] is True
    assert by_name["rejected"]["ok"] is False
    assert "push_attempts=1，期望 2" in by_name["rejected"]["failure"]
    assert payload["ok"] is False


def test_driver_stops_when_the_source_repo_is_mutated(
        tmp_path: Path, monkeypatch) -> None:
    """源仓库 HEAD/历史被改动 → 1，且不继续跑后续场景。"""
    repo = _seed(tmp_path)
    monkeypatch.setattr(scenarios, "_invoke_replay",
                        _fake_invoke(mutate=repo / HISTORY_REL))
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 1
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert len(payload["scenarios"]) == 1, (
        "源仓库被改动后驱动仍在跑后续场景，基线已污染")
    record = payload["scenarios"][0]
    assert record["source_mutated"] is True
    assert "源仓库被改动" in record["failure"]
    assert payload["ok"] is False


def test_driver_returns_3_when_the_repo_is_not_a_git_repository(
        tmp_path: Path, monkeypatch) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    # tmp_path 可能落在仓库内；挡住 git 向上发现父仓库。
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(outside, result))

    assert code == 3
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["reason"] == "baseline-unavailable"


def test_driver_returns_3_when_history_is_unreadable(tmp_path: Path) -> None:
    repo = _seed(tmp_path)
    (repo / HISTORY_REL).write_text("{not json", encoding="utf-8")
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 3
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "baseline-unavailable"


def test_scenario_table_pins_the_replay_counts() -> None:
    """场景表是这张判据的唯一来源；数字漂了必须有人先改这里。"""
    by_name = {scenario.name: scenario for scenario in scenarios.SCENARIOS}
    assert list(by_name) == [
        "happy", "rejected", "conflict", "permanently-rejected",
        "rejected-conflict", "rejected-hook-conflict",
        "rejected-hook-budget-2", "rejected-hook-conflict-at-2",
        "rejected-hook-budget-2-at-2", "rejected-hook-inject-at-3"]

    happy = by_name["happy"]
    assert (happy.rounds_delta, happy.push_attempts) == (1, 1)
    assert happy.reject_pushes == 0 and happy.conflict is False
    assert happy.expected_exit == 0 and happy.expected_reason == "written"

    rejected = by_name["rejected"]
    assert (rejected.rounds_delta, rejected.push_attempts) == (1, 2)
    assert rejected.reject_pushes == 1 and rejected.conflict is False

    conflict = by_name["conflict"]
    assert (conflict.rounds_delta, conflict.push_attempts) == (2, 2)
    assert conflict.conflict is True
    assert conflict.injected_rounds == 1

    permanent = by_name["permanently-rejected"]
    assert (permanent.rounds_delta, permanent.push_attempts) == (0, 3)
    assert permanent.reject_pushes == 3
    assert permanent.expected_exit == 1
    assert permanent.expected_reason == "push-rejected"
    assert permanent.expect_sandbox is True
    assert permanent.injected_rounds == 0
    # 失败场景的末条身份：没有注入时仍是基线那一条（None = 空历史）。
    assert permanent.expected_last_run_id is None

    # R105：三次尝试全被拒 + 冲突注入；远端只多出注入的那一轮。
    combined = by_name["rejected-conflict"]
    assert (combined.rounds_delta, combined.push_attempts) == (0, 3)
    assert combined.reject_pushes == 3 and combined.conflict is True
    assert combined.injected_rounds == 1
    assert combined.expected_exit == 1
    assert combined.expected_reason == "push-rejected"
    assert combined.expect_sandbox is True
    assert combined.expected_last_run_id == "replay-conflict"
    assert combined.output_counts == (
        ("push 被拒（第", 3), ("simulated rejection", 2))

    # R108：钩子在第一次拒绝时注入冲突。预算 3 全失败；预算 2 第三次成功.
    hook = by_name["rejected-hook-conflict"]
    assert (hook.rounds_delta, hook.push_attempts) == (0, 3)
    assert hook.reject_pushes == 3 and hook.conflict_on_reject == 1
    assert hook.conflict is False
    assert hook.injected_rounds == 1
    assert hook.expected_exit == 1
    assert hook.expected_last_run_id == "replay-conflict"
    assert hook.output_counts == (
        ("push 被拒（第", 3), ("simulated rejection", 3))

    budget2 = by_name["rejected-hook-budget-2"]
    assert (budget2.rounds_delta, budget2.push_attempts) == (2, 3)
    assert budget2.reject_pushes == 2 and budget2.conflict_on_reject == 1
    assert budget2.conflict is False
    assert budget2.expected_exit == 0
    assert budget2.expected_reason == "written"
    assert budget2.expect_sandbox is False
    assert budget2.output_counts == (
        ("push 被拒（第", 2), ("simulated rejection", 2))

    # R112：注入点第 2 次 + 预算 3（仍耗尽）/ 预算 2（第三次成功）。
    at2 = by_name["rejected-hook-conflict-at-2"]
    assert (at2.rounds_delta, at2.push_attempts) == (0, 3)
    assert at2.reject_pushes == 3 and at2.conflict_on_reject == 2
    assert at2.injected_rounds == 1
    assert at2.expected_exit == 1
    assert at2.expected_last_run_id == "replay-conflict"
    assert "rebase 冲突（第 2 次）" in at2.must_contain

    budget2_at2 = by_name["rejected-hook-budget-2-at-2"]
    assert (budget2_at2.rounds_delta, budget2_at2.push_attempts) == (2, 3)
    assert (budget2_at2.reject_pushes
            == 2 and budget2_at2.conflict_on_reject == 2)
    assert budget2_at2.expected_exit == 0
    assert "rebase 冲突（第 2 次）" in budget2_at2.must_contain

    # R112：注入点与预算都在第 3 次——冲突后没有下一次重试。
    at3 = by_name["rejected-hook-inject-at-3"]
    assert (at3.rounds_delta, at3.push_attempts) == (0, 3)
    assert at3.reject_pushes == 3 and at3.conflict_on_reject == 3
    assert at3.injected_rounds == 1
    assert at3.expected_exit == 1
    # 注入在最后一次拒绝：最后一次失败是 rebase 冲突，不是 push 被拒。
    assert at3.expected_reason == "rebase-conflict"
    assert at3.expected_last_run_id == "replay-conflict"
    assert "rebase 冲突（第 3 次）" in at3.must_contain

    # R106：全链版本必须与本地组合场景同语义，只多出「真的下载了」这一项。
    triple = scenarios.FETCH_REJECTED_CONFLICT_SCENARIO
    assert triple.name == "fetched-rejected-conflict"
    assert triple.fetch is True
    assert (triple.rounds_delta, triple.push_attempts) == (0, 3)
    assert triple.reject_pushes == 3 and triple.conflict is True
    assert triple.injected_rounds == 1
    assert triple.expected_exit == 1
    assert triple.expected_reason == "push-rejected"
    assert triple.expect_sandbox is True
    assert triple.expected_last_run_id == "replay-conflict"
    assert triple.output_counts == (
        ("push 被拒（第", 3), ("simulated rejection", 2))
    assert "已下载 1 个文件" in triple.must_contain


def test_local_metrics_shape_is_deliberately_different(
        tmp_path: Path) -> None:
    """R107：本地夹具与生产 artifact 形状必须不同，否则内容来源不可辨。

    全链场景钉 ``metrics 内容 total=10``；本地夹具是 3 场景/1 次重跑。如果
    fetch 成功却回退到本地 metrics，计数指纹会变成 total=3，断言应判红。
    """
    path = scenarios._metrics(tmp_path / "metrics.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["total"] == 3
    assert payload["passed"] == 3
    assert payload["retried"] == 1
    assert sum(item["attempts"] for item in payload["scenarios"]) == 4
    for scenario in (scenarios.FETCH_SCENARIO,
                     scenarios.FETCH_REJECTED_CONFLICT_SCENARIO):
        assert "metrics 内容 total=10" in scenario.must_contain


def test_driver_rejects_half_a_fetch_configuration(tmp_path: Path) -> None:
    repo = _seed(tmp_path)
    result = tmp_path / "result.json"

    assert scenarios.main(_argv(
        repo, result, extra=["--fetch-api-url", "http://127.0.0.1:1"])) == 2
    assert scenarios.main(_argv(
        repo, result, extra=["--fetch-run-id", "42"])) == 2


def test_driver_runs_the_fetch_chain_end_to_end(tmp_path: Path) -> None:
    """下载真实 artifact → 写回：fetch run id 与历史 run id 必须分开。"""
    repo = _seed(tmp_path)
    head = _git("rev-parse", "HEAD", cwd=repo)
    short = head[:8]
    archive = zip_bytes({"e2e-metrics.json": _metrics_file(tmp_path).read_bytes()})
    routes: dict = {}
    recorded: list = []
    result = tmp_path / "result.json"

    with server(routes, recorded) as base:
        routes[api_path("owner/repo", "987654", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, archive)

        code = scenarios.main(_argv(
            repo, result,
            extra=["--fetch-api-url", base,
                   "--fetch-run-id", "987654",
                   "--fetch-repo", "owner/repo"]))

    assert code == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    by_name = {record["name"]: record for record in payload["scenarios"]}
    assert list(by_name) == [
        "happy", "rejected", "conflict", "permanently-rejected",
        "rejected-conflict", "rejected-hook-conflict",
        "rejected-hook-budget-2", "rejected-hook-conflict-at-2",
        "rejected-hook-budget-2-at-2", "rejected-hook-inject-at-3",
        "fetched", "fetched-rejected-conflict"]
    fetched = by_name["fetched"]
    assert fetched["ok"] is True, fetched["failure"]
    assert fetched["actual"] == {
        "exit_code": 0, "reason": "written", "rounds": 1,
        "last_run_id": f"replay-ci-fetched-{short}",
        "push_attempts": 1}
    # R107：两份全链场景的计数指纹都必须来自生产 artifact（total=10），
    # 而不是驱动自己的 3 场景本地夹具。
    assert "metrics 内容 total=10" in fetched["output"]
    # R112：语义行逐场景列出 name=状态/尝试次数，证明内容被读进来了。
    assert "metrics 语义" in fetched["output"]
    assert "fetched_0=ok/1" in fetched["output"]
    # R106：下载真的成功后再叠加三次拒绝 + 冲突，期望与本地组合场景一致；
    # fetch 只换 metrics 来源，不能改变写回语义。
    triple = by_name["fetched-rejected-conflict"]
    assert triple["ok"] is True, triple["failure"]
    assert triple["actual"] == {
        "exit_code": 1, "reason": "push-rejected", "rounds": 1,
        "last_run_id": "replay-conflict",
        "push_attempts": 3}
    assert "metrics 内容 total=10" in triple["output"]
    assert "metrics 语义" in triple["output"]
    assert triple["sandbox_cleaned"] is True
    assert triple["sandbox"] is not None
    assert not Path(triple["sandbox"]).exists()
    # artifact API 用的是 GitHub run id，不是历史 run id；两个全链场景
    # 都必须真的走 API，而不是本地 metrics。
    assert sum("/987654/" in path for path, _headers in recorded) >= 2
    assert not any("replay-ci-" in path for path, _headers in recorded)


def test_driver_runs_as_a_script_not_just_as_an_import(tmp_path: Path) -> None:
    """R98 同型：脚本模式的 ``sys.path`` 引导必须自己成立。"""
    repo = _seed(tmp_path)
    result = tmp_path / "result.json"
    completed = subprocess.run(
        [sys.executable, "-X", "utf8",
         str(scenarios.REPO_ROOT / "scripts" / "replay_ci_scenarios.py"),
         "--repo", str(repo), "--branch", "main",
         "--result-json", str(result)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(scenarios.REPO_ROOT))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert len(payload["scenarios"]) == 10


# ------------------------------------- 窗口边界（R102：MAX_ROUNDS 耗尽防护）
@pytest.mark.parametrize("count, expected, clipped", [
    # 38：四个成功场景的增量都没碰到窗口，rounds 仍是强证据。
    (38, {"happy": 39, "rejected": 39, "conflict": 40,
          "permanently-rejected": 38, "rejected-conflict": 39,
          "rejected-hook-conflict": 39,
          "rejected-hook-budget-2": 40,
          "rejected-hook-conflict-at-2": 39,
          "rejected-hook-budget-2-at-2": 40,
          "rejected-hook-inject-at-3": 39},
         {"happy": False, "rejected": False, "conflict": False,
          "permanently-rejected": False, "rejected-conflict": False,
          "rejected-hook-conflict": False,
          "rejected-hook-budget-2": False,
          "rejected-hook-conflict-at-2": False,
          "rejected-hook-budget-2-at-2": False,
          "rejected-hook-inject-at-3": False}),
    # 39：conflict / budget-2 的 +2 先被压成 +1（40 == 40），只有它们能暴露裁剪。
    (39, {"happy": 40, "rejected": 40, "conflict": 40,
          "permanently-rejected": 39, "rejected-conflict": 40,
          "rejected-hook-conflict": 40,
          "rejected-hook-budget-2": 40,
          "rejected-hook-conflict-at-2": 40,
          "rejected-hook-budget-2-at-2": 40,
          "rejected-hook-inject-at-3": 40},
         {"happy": False, "rejected": False, "conflict": True,
          "permanently-rejected": False, "rejected-conflict": False,
          "rejected-hook-conflict": False,
          "rejected-hook-budget-2": True,
          "rejected-hook-conflict-at-2": False,
          "rejected-hook-budget-2-at-2": True,
          "rejected-hook-inject-at-3": False}),
    # 40：四个成功场景的 rounds 全部恒定，只剩 last_run_id 能证明本轮已入库。
    # 失败场景也恒定在 40——冲突注入遵守窗口，不会把远端撑到 41。
    (40, {"happy": 40, "rejected": 40, "conflict": 40,
          "permanently-rejected": 40, "rejected-conflict": 40,
          "rejected-hook-conflict": 40,
          "rejected-hook-budget-2": 40,
          "rejected-hook-conflict-at-2": 40,
          "rejected-hook-budget-2-at-2": 40,
          "rejected-hook-inject-at-3": 40},
         {"happy": True, "rejected": True, "conflict": True,
          "permanently-rejected": False, "rejected-conflict": False,
          "rejected-hook-conflict": False,
          "rejected-hook-budget-2": True,
          "rejected-hook-conflict-at-2": False,
          "rejected-hook-budget-2-at-2": True,
          "rejected-hook-inject-at-3": False}),
])
def test_driver_keeps_the_written_round_witness_at_the_window_boundary(
        tmp_path: Path, monkeypatch, count: int, expected: dict,
        clipped: dict) -> None:
    # 窗口边界用显式配置的 40，不跟默认值走：这组用例钉的是「满窗前 2 轮 /
    # 满窗前 1 轮 / 满窗」的相对几何，默认值改政策（R112 40→80）不应重写
    # 边界算术。默认值本身由 test_e2e_retry_history 单独钉住。
    monkeypatch.setenv(scenarios.history.MAX_ROUNDS_ENV, "40")
    repo = _seed_with_rounds(tmp_path, count)
    head = _git("rev-parse", "HEAD", cwd=repo)
    result = tmp_path / "result.json"
    summary = tmp_path / "summary.md"

    code = scenarios.main(_argv(repo, result, summary))

    assert code == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["before"] == count
    # 断言对「生效窗口」而不是常量：本组用例显式配置 40，默认值（80）不该
    # 参与这里的边界算术。
    window = scenarios.history.max_rounds()
    assert window == 40
    assert payload["max_rounds"] == window
    assert payload["window_full"] is (count >= window)
    by_name = {record["name"]: record for record in payload["scenarios"]}
    for name, record in by_name.items():
        assert record["ok"] is True, record["failure"]
        assert record["rounds_clipped"] is clipped[name]
        assert record["expected"]["rounds"] == expected[name]
        assert record["actual"]["rounds"] == expected[name]
        if name == "permanently-rejected":
            # 失败场景：远端末条仍是基线那一条，不是本轮。
            assert record["actual"]["last_run_id"] == f"seed-{count - 1}"
        elif name in ("rejected-conflict", "rejected-hook-conflict",
                      "rejected-hook-conflict-at-2",
                      "rejected-hook-inject-at-3"):
            # 失败场景：远端只多出注入的冲突轮，末条就是它。
            assert record["actual"]["last_run_id"] == "replay-conflict"
        else:
            assert record["actual"]["last_run_id"] == (
                f"replay-ci-{name}-{head[:8]}")
    # 摘要必须自己说出「这一项的轮数已被裁剪」，不能只留一个恒等式。
    text = summary.read_text(encoding="utf-8")
    assert text.count("窗口已满") == sum(clipped.values())


def test_driver_uses_the_configured_window(
        tmp_path: Path, monkeypatch) -> None:
    """R109：驱动、record、冲突夹具必须共用一个保留期读取点。

    把窗口设成 8、基线也是 8：冲突场景 +2 会被裁剪（8+2 > 8），失败场景的
    注入也必须裁到 8（不能造出 9 轮）；如果某处还在读默认值（R112 起 80），
    rounds/window_full/rounds_clipped 会互相矛盾，驱动会判 1。
    """
    monkeypatch.setenv(scenarios.history.MAX_ROUNDS_ENV, "8")
    repo = _seed_with_rounds(tmp_path, 8)
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["max_rounds"] == 8
    assert payload["window_full"] is True
    by_name = {record["name"]: record for record in payload["scenarios"]}
    # 8 + 2 被压到 8：裁剪标记必须出现。
    assert by_name["conflict"]["actual"]["rounds"] == 8
    assert by_name["conflict"]["rounds_clipped"] is True
    assert by_name["rejected-conflict"]["actual"]["rounds"] == 8
    # 失败场景的注入也裁到 8，不能造出第 9 轮。
    assert by_name["rejected-hook-conflict"]["actual"]["rounds"] == 8


def test_window_full_identity_is_the_only_remaining_witness(
        tmp_path: Path, monkeypatch) -> None:
    """满窗时其余四项全对、只有末条不是本轮：必须由 last_run_id 判红。

    这是「rounds 断言在满窗（MAX_ROUNDS/MAX_ROUNDS）时恒真」的反证：若驱动只看
    exit/reason/rounds/push_attempts/输出，这条会全绿。
    """
    repo = _seed_with_rounds(tmp_path, scenarios.history.MAX_ROUNDS)
    monkeypatch.setattr(scenarios, "_invoke_replay", _fake_invoke(
        last_run_id="some-other-round", rounds=scenarios.history.MAX_ROUNDS))
    result = tmp_path / "result.json"

    code = scenarios.main(_argv(repo, result))

    assert code == 1
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["window_full"] is True
    for record in payload["scenarios"]:
        assert record["ok"] is False
        assert "last_run_id" in record["failure"]
        # 其余四项都符合满窗时的真实观测：失败只能来自末条身份。
        assert "退出码" not in record["failure"]
        assert "reason=" not in record["failure"]
        assert "rounds=" not in record["failure"]
        assert "push_attempts=" not in record["failure"]
