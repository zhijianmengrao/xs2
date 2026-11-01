"""R94：本地回放工具的行为用例（源仓库只读）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import replay_ci_writeback as replay

HISTORY_REL = "tests/fixtures/e2e_retry_history/history.json"


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=None if cwd is None else str(cwd),
        capture_output=True)
    assert result.returncode == 0, (
        (result.stderr or result.stdout).decode("utf-8", "replace"))
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _metrics(path: Path) -> Path:
    scenarios = [
        {"name": f"scenario_{index}", "passed": True, "attempts": 1,
         "first_failure": ""}
        for index in range(10)
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 10, "passed": 10, "failed": 0, "retried": 0,
        "scenarios": scenarios}), encoding="utf-8")
    return path


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


def test_replay_leaves_the_source_repo_untouched(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    head = _git("rev-parse", "HEAD", cwd=repo)
    history_bytes = (repo / HISTORY_REL).read_bytes()

    code = replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
    ])

    assert code == 0
    out = capsys.readouterr().out
    assert "replay" in out
    assert "0 → 1" in out
    assert _git("rev-parse", "HEAD", cwd=repo) == head
    assert _git("status", "--porcelain", cwd=repo) == ""
    assert (repo / HISTORY_REL).read_bytes() == history_bytes


def test_replay_reports_the_writeback_commit(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
    ]) == 0

    out = capsys.readouterr().out
    assert "chore(e2e): record CI run replay-1" in out


def test_replay_dry_run_does_not_commit(tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--dry-run",
    ]) == 0

    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "0 → 0" in out
