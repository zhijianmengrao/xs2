"""R94：本地回放工具的行为用例（源仓库只读）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from artifact_api_fixture import api_path, listing, server, zip_bytes
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


def _archive(tmp_path: Path) -> bytes:
    metrics = _metrics(tmp_path / "metrics.json")
    return zip_bytes({"e2e-metrics.json": metrics.read_bytes()})


def test_replay_fetches_the_artifact_before_writeback(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, _archive(tmp_path))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert "0 → 1" in out
    assert "chore(e2e): record CI run replay-fetch" in out


def test_replay_separates_the_fetch_run_id_from_the_history_run_id(
        tmp_path: Path, capsys) -> None:
    """R103：artifact API 的 run id 与历史 run id 是两件事。"""
    repo = _seed(tmp_path)
    routes: dict = {}
    recorded: list = []
    result = tmp_path / "result.json"
    with server(routes, recorded) as base:
        routes[api_path("owner/repo", "gh-run-42", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, _archive(tmp_path))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-writeback-id",
            "--fetch-api-url", base,
            "--fetch-run-id", "gh-run-42",
            "--fetch-repo", "owner/repo",
            "--result-json", str(result),
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert "chore(e2e): record CI run replay-writeback-id" in out
    # 列表请求命中的是 GitHub run id；历史条目用的是写回 run id。
    assert any("/gh-run-42/" in path for path, _headers in recorded)
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["run_id"] == "replay-writeback-id"
    assert payload["last_run_id"] == "replay-writeback-id"


def test_replay_missing_artifact_does_not_write(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            json.dumps({"total_count": 0, "artifacts": []}).encode())

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
        ]) == 0

    out = capsys.readouterr().out
    assert "没有 artifact e2e-metrics" in out
    assert "0 → 0" in out


def test_replay_fetch_failure_stops_before_writeback(
        tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            500, {"Content-Type": "application/json"},
            b'{"message": "boom"}')

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
        ]) == 1

    captured = capsys.readouterr()
    assert "artifact 拉取失败，未进入写回" in captured.err
    assert sandbox.exists()
    assert "失败现场" in captured.out
    replay._remove_sandbox(sandbox)


def test_replay_requires_a_metrics_source(tmp_path: Path) -> None:
    repo = _seed(tmp_path)
    with pytest.raises(SystemExit) as exc:
        replay.main(["--repo", str(repo), "--run-id", "replay-1"])
    assert exc.value.code == 2


# ------------------------------------------------- 拒绝/冲突演练（R99）
def test_replay_simulates_a_rejected_push_once(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--reject-pushes", "1",
        "--result-json", str(result),
    ]) == 0

    out = capsys.readouterr().out
    assert "前 1 次 push 被拒" in out
    assert "push 被拒（第 1 次）" in out
    assert "第 2 次尝试" in out
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == 2
    assert payload["rounds"] == 1
    assert payload["last_run_id"] == "replay-1"


def test_replay_simulates_permanent_rejection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))
    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--reject-pushes", "3",
        "--result-json", str(result),
    ]) == 1

    out = capsys.readouterr().out
    assert out.count("push 被拒（第") == 3
    assert "失败现场" in out
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "push-rejected"
    assert payload["push_attempts"] == 3
    assert payload["rounds"] == 0
    assert payload["last_run_id"] is None
    assert sandbox.exists()
    replay._remove_sandbox(sandbox)


def test_replay_simulates_a_conflicting_history(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--conflict",
        "--result-json", str(result),
    ]) == 0

    out = capsys.readouterr().out
    assert "已在 origin 上制造一轮冲突" in out
    assert "rebase 冲突（第 1 次）" in out
    assert "第 2 次尝试" in out
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == 2
    # 冲突那一轮（replay-conflict）+ 本轮（replay-1）都在远端历史里。
    assert payload["rounds"] == 2
    assert payload["last_run_id"] == "replay-1"


def test_replay_combines_conflict_with_permanent_rejection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R105：冲突注入 + 三次尝试全被拒，末条仍是注入的冲突轮。

    第一次 push 是被冲突注入造成的非快进拒绝（不是钩子），所以
    ``simulated rejection`` 只能是 2 次；把它当成 3 次会掩盖「第一次其实
    没走到钩子」这一事实。
    """
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))
    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--reject-pushes", "3",
        "--conflict",
        "--result-json", str(result),
    ]) == 1

    captured = capsys.readouterr()
    assert captured.out.count("push 被拒（第") == 3
    assert captured.out.count("rebase 冲突（第 1 次）") == 1
    assert "::error::连续 3 次写回均失败" in captured.out
    assert "已写回" not in captured.out
    # git 的 push stderr 由 writeback 打到 stderr，钩子的消息也只在这里。
    assert captured.err.count("simulated rejection") == 2
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "push-rejected"
    assert payload["push_attempts"] == 3
    # 远端只有注入的冲突轮；本轮写回没有入库。
    assert payload["rounds"] == 1
    assert payload["last_run_id"] == "replay-conflict"
    assert sandbox.exists(), "期望失败场景保留现场"
    replay._remove_sandbox(sandbox)


def test_replay_fetch_and_rejection_work_together(
        tmp_path: Path, capsys) -> None:
    repo = _seed(tmp_path)
    routes: dict = {}
    result = tmp_path / "result.json"
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, _archive(tmp_path))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
            "--reject-pushes", "1",
            "--result-json", str(result),
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert "第 2 次尝试" in out
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["push_attempts"] == 2
    assert payload["reason"] == "written"


def test_replay_fetch_conflict_and_rejection_work_together(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R106：artifact 下载成功后再走三次拒绝 + 冲突。

    fetch 只换 metrics 来源；写回语义必须与本地组合场景完全一致——第一次
    是非快进拒绝（钩子只看到第 2、3 次），远端只多出注入的冲突轮。
    """
    repo = _seed(tmp_path)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(replay.tempfile, "mkdtemp",
                        lambda **kwargs: str(sandbox))
    routes: dict = {}
    result = tmp_path / "result.json"
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, _archive(tmp_path))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
            "--reject-pushes", "3",
            "--conflict",
            "--result-json", str(result),
        ]) == 1

    captured = capsys.readouterr()
    assert "已下载 1 个文件" in captured.out
    assert captured.out.count("push 被拒（第") == 3
    assert captured.out.count("rebase 冲突（第 1 次）") == 1
    assert "::error::连续 3 次写回均失败" in captured.out
    assert "已写回" not in captured.out
    # 第一次是非快进拒绝；钩子只拒绝第 2、3 次。
    assert captured.err.count("simulated rejection") == 2
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "push-rejected"
    assert payload["push_attempts"] == 3
    assert payload["rounds"] == 1
    assert payload["last_run_id"] == "replay-conflict"
    assert sandbox.exists(), "期望失败场景保留现场"
    replay._remove_sandbox(sandbox)


def test_replay_rejects_a_negative_rejection_count(tmp_path: Path) -> None:
    repo = _seed(tmp_path)
    code = replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
        "--reject-pushes=-1",
    ])
    assert code == 2
