"""R101：生产回放驱动 ``scripts/replay_ci_scenarios.py`` 的行为用例。

这里驱动的是**真实** ``replay_ci_writeback.main``（临时 git 仓），断言三个
场景的退出码/rounds/push_attempts 与源仓库只读；另外用 monkeypatch 证明驱动
不盲信子调用的退出码、且能发现源仓库被改动。CI job 本身的接线契约在
``tests/test_ci_replay_wiring.py``。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import replay_ci_scenarios as scenarios

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


def _argv(repo: Path, result: Path, summary: Path | None = None) -> list[str]:
    argv = ["--repo", str(repo), "--branch", "main",
            "--result-json", str(result)]
    if summary is not None:
        argv += ["--summary", str(summary)]
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


def test_driver_runs_happy_rejected_and_conflict(tmp_path: Path) -> None:
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
    assert list(by_name) == ["happy", "rejected", "conflict"]
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
    for record in payload["scenarios"]:
        assert record["ok"] is True, record["failure"]
        assert record["source_mutated"] is False
        assert record["rounds_clipped"] is False

    # 源仓库一个字节都不该动。
    assert _git("rev-parse", "HEAD", cwd=repo) == head
    assert (repo / HISTORY_REL).read_bytes() == history_bytes
    assert _git("status", "--porcelain", cwd=repo) == ""

    # step summary 每个场景一行，reason 是 ok。
    text = summary.read_text(encoding="utf-8")
    assert text.count("replay-ci-") == 3
    assert "**ok**" in text


def test_driver_does_not_trust_the_replay_exit_code(
        tmp_path: Path, monkeypatch) -> None:
    """子调用退 0 但 result 里的 push_attempts 不对：驱动必须判 1。"""
    repo = _seed(tmp_path)

    def fake_main(argv: list[str]) -> int:
        result_path = Path(argv[argv.index("--result-json") + 1])
        run_id = argv[argv.index("--run-id") + 1]
        name = run_id.split("-")[2]
        # 三个场景一律写「只 push 了一次」：rounds 与输出都正确，让
        # rejected/conflict 的失败**只**能由 push_attempts 断言发现。
        result_path.write_text(json.dumps({
            "schema": 1, "run_id": run_id, "source": "ci",
            "reason": "written", "detail": "", "exit_code": 0,
            "rounds": 2 if name == "conflict" else 1,
            "last_run_id": run_id,
            "push_attempts": 1, "dry_run": False,
        }), encoding="utf-8")
        print("已写回 main（第 1 次尝试）")
        if name == "rejected":
            print("push 被拒（第 1 次），rebase 到最新 main 后重试")
            print("已写回 main（第 2 次尝试）")
        if name == "conflict":
            print("rebase 冲突（第 1 次）：丢弃本次写回提交，按最新 main 重算")
            print("已写回 main（第 2 次尝试）")
        return 0

    monkeypatch.setattr(scenarios.replay, "main", fake_main)
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
    target = repo / HISTORY_REL

    def fake_main(argv: list[str]) -> int:
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["history"].append(_entry("mutated-by-replay"))
        target.write_text(json.dumps(payload), encoding="utf-8")
        result_path = Path(argv[argv.index("--result-json") + 1])
        run_id = argv[argv.index("--run-id") + 1]
        result_path.write_text(json.dumps({
            "schema": 1, "run_id": run_id, "source": "ci", "reason": "written",
            "detail": "", "exit_code": 0, "rounds": 1,
            "last_run_id": run_id,
            "push_attempts": 1, "dry_run": False,
        }), encoding="utf-8")
        print("已写回 main（第 1 次尝试）")
        return 0

    monkeypatch.setattr(scenarios.replay, "main", fake_main)
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


def test_scenario_table_pins_the_r99_counts() -> None:
    """场景表是这张判据的唯一来源；数字漂了必须有人先改这里。"""
    by_name = {scenario.name: scenario for scenario in scenarios.SCENARIOS}
    assert list(by_name) == ["happy", "rejected", "conflict"]

    happy = by_name["happy"]
    assert (happy.rounds_delta, happy.push_attempts) == (1, 1)
    assert happy.reject_pushes == 0 and happy.conflict is False

    rejected = by_name["rejected"]
    assert (rejected.rounds_delta, rejected.push_attempts) == (1, 2)
    assert rejected.reject_pushes == 1 and rejected.conflict is False

    conflict = by_name["conflict"]
    assert (conflict.rounds_delta, conflict.push_attempts) == (2, 2)
    assert conflict.conflict is True


# ------------------------------------- 窗口边界（R102：MAX_ROUNDS 耗尽防护）
@pytest.mark.parametrize("count, expected, clipped", [
    # 38：三个场景的增量都没碰到窗口，rounds 仍是强证据。
    (38, {"happy": 39, "rejected": 39, "conflict": 40},
         {"happy": False, "rejected": False, "conflict": False}),
    # 39：conflict 的 +2 先被压成 +1（40 == 40），只有它能暴露裁剪。
    (39, {"happy": 40, "rejected": 40, "conflict": 40},
         {"happy": False, "rejected": False, "conflict": True}),
    # 40：三个场景的 rounds 全部恒定，只剩 last_run_id 能证明本轮已入库。
    (40, {"happy": 40, "rejected": 40, "conflict": 40},
         {"happy": True, "rejected": True, "conflict": True}),
])
def test_driver_keeps_the_written_round_witness_at_the_window_boundary(
        tmp_path: Path, count: int, expected: dict, clipped: dict) -> None:
    repo = _seed_with_rounds(tmp_path, count)
    head = _git("rev-parse", "HEAD", cwd=repo)
    result = tmp_path / "result.json"
    summary = tmp_path / "summary.md"

    code = scenarios.main(_argv(repo, result, summary))

    assert code == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["before"] == count
    assert payload["max_rounds"] == scenarios.history.MAX_ROUNDS
    assert payload["window_full"] is (count >= scenarios.history.MAX_ROUNDS)
    by_name = {record["name"]: record for record in payload["scenarios"]}
    for name, record in by_name.items():
        assert record["ok"] is True, record["failure"]
        assert record["rounds_clipped"] is clipped[name]
        assert record["expected"]["rounds"] == expected[name]
        assert record["actual"]["rounds"] == expected[name]
        assert record["actual"]["last_run_id"] == (
            f"replay-ci-{name}-{head[:8]}")
    # 摘要必须自己说出「这一项的轮数已被裁剪」，不能只留一个恒等式。
    text = summary.read_text(encoding="utf-8")
    assert text.count("窗口已满") == sum(clipped.values())


def test_window_full_identity_is_the_only_remaining_witness(
        tmp_path: Path, monkeypatch) -> None:
    """满窗时其余四项全对、只有末条不是本轮：必须由 last_run_id 判红。

    这是「rounds 断言在 40/40 时恒真」的反证：若驱动只看
    exit/reason/rounds/push_attempts/输出，这条会全绿。
    """
    repo = _seed_with_rounds(tmp_path, scenarios.history.MAX_ROUNDS)

    def fake_main(argv: list[str]) -> int:
        result_path = Path(argv[argv.index("--result-json") + 1])
        run_id = argv[argv.index("--run-id") + 1]
        name = run_id.split("-")[2]
        result_path.write_text(json.dumps({
            "schema": 1, "run_id": run_id, "source": "ci",
            "reason": "written", "detail": "", "exit_code": 0,
            "rounds": scenarios.history.MAX_ROUNDS,
            "last_run_id": "some-other-round",
            "window_full": True,
            "push_attempts": 1 if name == "happy" else 2,
            "dry_run": False,
        }), encoding="utf-8")
        print("已写回 main（第 1 次尝试）")
        if name == "rejected":
            print("push 被拒（第 1 次），rebase 到最新 main 后重试")
            print("已写回 main（第 2 次尝试）")
        if name == "conflict":
            print("rebase 冲突（第 1 次）：丢弃本次写回提交，按最新 main 重算")
            print("已写回 main（第 2 次尝试）")
        return 0

    monkeypatch.setattr(scenarios.replay, "main", fake_main)
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
