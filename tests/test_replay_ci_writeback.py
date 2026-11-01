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


def _entry(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "exported_at": "2026-11-01T00:00:00+00:00",
        "source": "local",
        "total": 1, "passed": 1, "failed": 0, "retried": 0, "attempts": 1,
        "scenarios": [{"name": "happy", "passed": True, "attempts": 1,
                       "first_failure": ""}],
    }


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


def test_replay_from_worktree_applies_uncommitted_changes(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    target = repo / HISTORY_REL
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["history"].append(_entry("local-edit"))
    target.write_text(json.dumps(payload), encoding="utf-8")
    head = _git("rev-parse", "HEAD", cwd=repo)
    dirty = target.read_bytes()

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--from-worktree",
    ]) == 0

    out = capsys.readouterr().out
    assert "已把工作树未提交改动带入沙箱" in out
    # 未提交的那一轮在沙箱里可见：1（工作树）→ 2（再加 replay-1）
    assert "1 → 2" in out
    # 源仓库仍停在原 HEAD，脏改动一个字节都没动。
    assert _git("rev-parse", "HEAD", cwd=repo) == head
    assert target.read_bytes() == dirty
    assert _git("status", "--porcelain", cwd=repo).strip() != ""


def test_from_worktree_reports_untracked_files(tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    (repo / "notes.txt").write_text("untracked", encoding="utf-8")

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--from-worktree",
    ]) == 0

    assert "1 个未跟踪文件不进入回放" in capsys.readouterr().out


def test_successful_replay_removes_the_sandbox(
        tmp_path: Path, monkeypatch) -> None:
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
    ]) == 0

    assert not sandbox.exists()


def test_failed_replay_keeps_the_sandbox(
        tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    code = replay.main([
        "--repo", str(repo),
        "--metrics", str(bad),
        "--run-id", "replay-1",
    ])

    assert code == 4
    out = capsys.readouterr().out
    assert f"沙箱保留在 {sandbox}" in out
    assert "失败现场" in out
    assert sandbox.exists()
    replay._remove_sandbox(sandbox)
