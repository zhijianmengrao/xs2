"""R94：本地回放工具的行为用例（源仓库只读）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from artifact_api_fixture import api_path, listing, server, zip_bytes
from scripts import e2e_retry_history as history
from scripts import replay_ci_writeback as replay

HISTORY_REL = "tests/fixtures/e2e_retry_history/history.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
SHAPE_FIXTURES = (
    ("failure", "e2e_metrics_failure_shape", ("4", "1", "1", "25.0%", "5"),
     None),
    ("empty", "e2e_metrics_empty", ("0", "0", "0", "n/a", "0"),
     "最近一轮 0 个场景"),
    ("all_failed", "e2e_metrics_all_failed", ("3", "3", "0", "0.0%", "3"),
     None),
)


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


def _metrics_shape(path: Path, total: int) -> Path:
    """任意场景数的合法 metrics（用于证明内容指纹确实来自被写回的文件）。"""
    scenarios = [
        {"name": f"shape_{index}", "passed": True, "attempts": 1,
         "first_failure": ""}
        for index in range(total)
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": total, "passed": total, "failed": 0,
        "retried": 0, "scenarios": scenarios}), encoding="utf-8")
    return path


def _metrics_retry_shape(path: Path) -> Path:
    """失败/重试形状的合法 metrics（R112）。

    4 场景：两个一次通过、一个重跑一次后通过、一个失败；计数为
    passed=3 / failed=1 / retried=1 / attempts=5。与生产 e2e 的 10 场景全过
    形状不同——全链用例要证明语义（场景名、首次失败）真的被读到了。
    """
    scenarios = [
        {"name": "ok_0", "passed": True, "attempts": 1, "first_failure": ""},
        {"name": "retry_1", "passed": True, "attempts": 2,
         "first_failure": "第一次判红：模拟超睡"},
        {"name": "fail_2", "passed": False, "attempts": 1,
         "first_failure": "模拟失败：节点未完成"},
        {"name": "ok_3", "passed": True, "attempts": 1, "first_failure": ""},
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 4, "passed": 3, "failed": 1, "retried": 1,
        "scenarios": scenarios}), encoding="utf-8")
    return path


def _metrics_all_failed(path: Path) -> Path:
    """全失败形状：3 个场景一个都没通过（R113）。"""
    scenarios = [
        {"name": f"fail_{index}", "passed": False, "attempts": 1,
         "first_failure": f"全部失败：节点 {index} 未完成"}
        for index in range(3)
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 3, "passed": 0, "failed": 3, "retried": 0,
        "scenarios": scenarios}), encoding="utf-8")
    return path


def _metrics_empty(path: Path) -> Path:
    """0 场景形状：e2e 一个场景都没跑（合法，trend 用 n/a 表示）。"""
    path.write_text(json.dumps({
        "schema": 1, "total": 0, "passed": 0, "failed": 0, "retried": 0,
        "scenarios": []}), encoding="utf-8")
    return path


def _metrics_multi_retry_failure(path: Path) -> Path:
    """重试多次后仍失败：attempts=3 却 passed=False（R113）。

    两个场景都重跑过（retried=2），其中一个重跑后通过。这条形状专门钉住
    「重试次数」与「最终结论」不是同一件事：attempts 只说明试了几次。
    """
    scenarios = [
        {"name": "never_passes", "passed": False, "attempts": 3,
         "first_failure": "三次都失败：模拟节点崩溃"},
        {"name": "ok_after_retry", "passed": True, "attempts": 2,
         "first_failure": "第一次超时"},
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 2, "passed": 1, "failed": 1, "retried": 2,
        "attempts": 5, "scenarios": scenarios}), encoding="utf-8")
    return path


def _sandbox_from_output(output: str) -> Path:
    """从 ``--keep`` 的收尾行里取出沙箱路径。"""
    prefix = "replay：沙箱保留在 "
    for line in reversed(output.splitlines()):
        if line.startswith(prefix):
            return Path(line[len(prefix):].strip())
    raise AssertionError(f"输出里没有沙箱路径：\n{output}")


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


# ------------------------------------------------- 写回幂等（R127）
def test_replay_same_run_id_rerun_is_a_no_change(
        tmp_path: Path, capsys) -> None:
    """已入库 run_id 的重放必须是无害的 no-change：退 0、不 push、不重写。

    replay 每次都从源仓克隆全新沙箱，所以「同 run_id 重跑」发生在**源仓
    历史里已有这一轮**时（驱动重跑、CI 重放同一 commit）。record 对同键
    且同观测覆盖并保留原条目——历史字节不变 → 「history 没有变化」。
    这条在真实 replay CLI 上钉住该路径（此前只有 writeback() 层的用例），
    防止回放链路单独退化成重复入库。
    """
    repo = _seed(tmp_path)
    metrics = _metrics(tmp_path / "metrics.json")
    # 种子条目必须由 record 自己写出：格式与观测都与回放一致，差异只剩
    # exported_at——而 _same_observation 恰好忽略它。
    assert history.record(
        metrics, repo / HISTORY_REL, run_id="replay-dup",
        source="ci") == history.EXIT_OK
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-q", "-m", "seed replay-dup", cwd=repo)

    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(metrics),
        "--run-id", "replay-dup",
        "--result-json", str(result),
    ]) == 0

    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["reason"] == "no-change"
    assert data["exit_code"] == 0
    assert data["push_attempts"] == 0
    assert data["rounds"] == 1
    assert data["last_run_id"] == "replay-dup"
    assert data["window_full"] is False
    out = capsys.readouterr().out
    assert "history 没有变化" in out


def test_replay_missing_metrics_file_reports_metrics_missing(
        tmp_path: Path, capsys) -> None:
    """--metrics 指向不存在的文件：退 0、metrics-missing、一个字都不写。

    PR 上没有 e2e metrics 是常态（e2e 环境未启动）；这一路径在回放链路
    必须是「静默跳过」而不是失败，也不能碰远端历史。
    """
    repo = _seed(tmp_path)
    result = tmp_path / "result.json"

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(tmp_path / "no-such-metrics.json"),
        "--run-id", "replay-missing",
        "--result-json", str(result),
    ]) == 0

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "metrics-missing"
    assert payload["exit_code"] == 0
    assert payload["push_attempts"] == 0
    assert payload["rounds"] == 0
    assert payload["last_run_id"] is None
    out = capsys.readouterr().out
    assert "e2e 环境未启动" in out


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


def test_replay_reports_the_metrics_content(
        tmp_path: Path, capsys) -> None:
    """R107：写回前的计数指纹必须来自真正被 record 的那份 metrics。"""
    repo = _seed(tmp_path)
    metrics = _metrics_shape(tmp_path / "local-metrics.json", 2)

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(metrics),
        "--run-id", "replay-1",
    ]) == 0

    out = capsys.readouterr().out
    assert ("metrics 内容 total=2 passed=2 failed=0 retried=0 attempts=2"
            in out)


def test_replay_reports_the_fetched_metrics_content(
        tmp_path: Path, capsys) -> None:
    """R107：全链的计数指纹必须来自下载的 artifact，而不是本地夹具。"""
    repo = _seed(tmp_path)
    fetched = _metrics_shape(tmp_path / "artifact-metrics.json", 4)
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": fetched.read_bytes()}))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert ("metrics 内容 total=4 passed=4 failed=0 retried=0 attempts=4"
            in out)


def test_replay_hook_injects_conflict_on_first_rejection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R108：第一次 push 真的走到钩子，并在拒绝时注入冲突轮。

    与 R105 的「writeback 前注入」相反：第一次 push 不是非快进，钩子看到
    了它；预算 3 时三次尝试全失败，`simulated rejection` 是 3（不是 2）。
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
        "--conflict-on-reject",
        "--result-json", str(result),
    ]) == 1

    captured = capsys.readouterr()
    assert "第 1 次拒绝时注入冲突" in captured.out
    assert captured.out.count("push 被拒（第") == 3
    assert captured.out.count("rebase 冲突（第 1 次）") == 1
    assert captured.err.count("simulated rejection") == 3
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "push-rejected"
    assert payload["push_attempts"] == 3
    # 远端只有注入的冲突轮；本轮没有入库。
    assert payload["rounds"] == 1
    assert payload["last_run_id"] == "replay-conflict"
    assert sandbox.exists()
    replay._remove_sandbox(sandbox)


def test_replay_rejection_budget_two_is_a_real_boundary(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R108：预算 2 → 第三次 push 成功，2 与 3 是行为边界。

    同一夹具、同一冲突注入时机，只改 ``--reject-pushes``：2 让第三次尝试
    通过（净 +2：注入轮 + 本轮），3 则三次全失败（见上一条）。
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
        "--reject-pushes", "2",
        "--conflict-on-reject",
        "--result-json", str(result),
    ]) == 0

    captured = capsys.readouterr()
    assert "第 3 次尝试" in captured.out
    assert "已写回" in captured.out
    assert captured.out.count("push 被拒（第") == 2
    assert captured.out.count("rebase 冲突（第 1 次）") == 1
    assert captured.err.count("simulated rejection") == 2
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == 3
    # 注入轮 + 本轮都在远端。
    assert payload["rounds"] == 2
    assert payload["last_run_id"] == "replay-1"
    assert not sandbox.exists(), "成功场景不应保留沙箱"


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


def test_replay_hook_injects_conflict_on_the_second_rejection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R112：注入点可以指定到第 2 次拒绝。

    预算 2：第 1 次普通拒绝，第 2 次拒绝时注入冲突，第三次 push 成功。
    最终轮数/尝试次数与 N=1 相同，唯一可区分的是「rebase 冲突（第 2 次）」
    ——固定第一次注入的实现会在这里判红。
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
        "--reject-pushes", "2",
        "--conflict-on-reject", "2",
        "--result-json", str(result),
    ]) == 0

    captured = capsys.readouterr()
    assert "第 2 次拒绝时注入冲突" in captured.out
    assert captured.out.count("push 被拒（第") == 2
    assert captured.out.count("rebase 冲突（第 2 次）") == 1
    assert "rebase 冲突（第 1 次）" not in captured.out
    assert captured.err.count("simulated rejection") == 2
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == 3
    # 注入轮 + 本轮都在远端。
    assert payload["rounds"] == 2
    assert payload["last_run_id"] == "replay-1"
    assert not sandbox.exists(), "成功场景不应保留沙箱"


def test_replay_rejects_an_unreachable_injection_point(
        tmp_path: Path, capsys) -> None:
    """R112：注入点落在预算之外 = 注入永远不会发生，必须退 2。

    静默退化成「普通拒绝」会让「第 N 次注入」看起来被测过，实际一次都没
    执行——这正是「配置看起来生效了」的典型坑。
    """
    repo = _seed(tmp_path)
    base = [
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
    ]

    assert replay.main([*base, "--reject-pushes", "2",
                        "--conflict-on-reject", "3"]) == 2
    assert "--reject-pushes >= 3" in capsys.readouterr().err

    assert replay.main([*base, "--reject-pushes", "3",
                        "--conflict-on-reject", "0"]) == 2
    assert "N 必须 >= 1" in capsys.readouterr().err

    # 裸开关仍是「第 1 次」，向后兼容（CI 与 R108 的调用都靠它）。
    assert replay.main([*base, "--reject-pushes", "1",
                        "--conflict-on-reject", "--dry-run"]) == 0


def test_replay_rejects_an_injection_point_beyond_the_attempt_budget(
        tmp_path: Path, capsys) -> None:
    """R113：预算够但重试次数不够，注入点同样不可达。

    写回循环最多 push ``attempts`` 次（默认 3）。R112 只查了「拒绝预算 >=
    注入点」，``--reject-pushes 4 --conflict-on-reject 4`` 因此能通过校验却
    永远到不了第 4 次拒绝——和第 N 次注入从未发生完全一样。这条闸门必须
    同时覆盖两个变量。
    """
    repo = _seed(tmp_path)
    base = [
        "--repo", str(repo),
        "--metrics", str(_metrics(tmp_path / "metrics.json")),
        "--run-id", "replay-1",
    ]

    # 默认 attempts=3：预算 4/注入 4 不可达。
    assert replay.main([*base, "--reject-pushes", "4",
                        "--conflict-on-reject", "4"]) == 2
    err = capsys.readouterr().err
    assert "--attempts >= 4" in err and "当前 3" in err

    assert replay.main([*base, "--attempts", "0"]) == 2
    assert "--attempts 必须 >= 1" in capsys.readouterr().err

    # 把重试上限抬到 4，同一配置就可达（dry-run 不真的 push）。
    assert replay.main([*base, "--attempts", "4",
                        "--reject-pushes", "4",
                        "--conflict-on-reject", "4", "--dry-run"]) == 0


def test_replay_hook_injects_conflict_on_the_fourth_rejection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R113：N=4、预算 4、attempts=4——四次全被拒，注入在最后一次。

    R112 的 N=1/2/3 场景都跑在默认 attempts=3 内；这条把「注入点 ==
    重试上限」推到 4，证明 --attempts 真的作用在写回循环上，而钩子的
    第 4 次判据也确实可达。
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
        "--reject-pushes", "4",
        "--attempts", "4",
        "--conflict-on-reject", "4",
        "--result-json", str(result),
    ]) == 1

    captured = capsys.readouterr()
    assert "第 4 次拒绝时注入冲突" in captured.out
    assert captured.out.count("push 被拒（第") == 4
    assert captured.out.count("rebase 冲突（第 4 次）") == 1
    assert "::error::连续 4 次写回均失败" in captured.out
    assert captured.err.count("simulated rejection") == 4
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "rebase-conflict"
    assert payload["push_attempts"] == 4
    assert payload["rounds"] == 1
    assert payload["last_run_id"] == "replay-conflict"
    assert sandbox.exists(), "期望失败场景保留现场"
    replay._remove_sandbox(sandbox)


def test_replay_succeeds_on_the_fifth_attempt_after_late_injection(
        tmp_path: Path, monkeypatch, capsys) -> None:
    """R113：N=4、预算 4、attempts=5——第 5 次 push 成功。

    与上一条只差 attempts：4 时第 4 次注入后没有重试，5 时重算后有一次
    机会。两道结局必须可区分，否则「late injection 必然失败」会被写死。
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
        "--reject-pushes", "4",
        "--attempts", "5",
        "--conflict-on-reject", "4",
        "--result-json", str(result),
    ]) == 0

    captured = capsys.readouterr()
    assert "第 4 次拒绝时注入冲突" in captured.out
    assert captured.out.count("push 被拒（第") == 4
    assert captured.out.count("rebase 冲突（第 4 次）") == 1
    assert "第 5 次尝试" in captured.out
    assert "已写回" in captured.out
    assert captured.err.count("simulated rejection") == 4
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == 5
    # 注入轮 + 本轮都在远端。
    assert payload["rounds"] == 2
    assert payload["last_run_id"] == "replay-1"
    assert not sandbox.exists(), "成功场景不应保留沙箱"


def test_replay_reports_the_metrics_semantics(tmp_path: Path,
                                              capsys) -> None:
    """R112：语义指纹逐场景列出 name=状态/尝试次数与首次失败。"""
    repo = _seed(tmp_path)

    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(_metrics_retry_shape(tmp_path / "retry.json")),
        "--run-id", "replay-1",
    ]) == 0

    out = capsys.readouterr().out
    assert ("metrics 内容 total=4 passed=3 failed=1 retried=1 attempts=5"
            in out)
    assert ("metrics 语义 ok_0=ok/1 retry_1=retry/2 "
            "fail_2=fail/1 ok_3=ok/1") in out
    assert ("metrics 首次失败 retry_1=第一次判红：模拟超睡；"
            "fail_2=模拟失败：节点未完成") in out


def test_replay_fetch_chain_carries_failure_and_retry_semantics(
        tmp_path: Path, capsys) -> None:
    """R112：全链 artifact 用失败/重试形状，语义既进指纹也进历史条目。

    下载 → 写回整链走真实 ``fetch_ci_artifact.fetch()``；artifact 里有一个
    重跑后通过、一个失败。写回成功后读沙箱里的 history，确认 failed/retried/
    attempts 与逐场景 first_failure 都原样落库——只数 total 的指纹做不到这一点。
    """
    repo = _seed(tmp_path)
    fetched = _metrics_retry_shape(tmp_path / "artifact-metrics.json")
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": fetched.read_bytes()}))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
            "--keep",
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert "metrics 语义 ok_0=ok/1 retry_1=retry/2 fail_2=fail/1" in out
    assert "metrics 首次失败" in out

    sandbox = _sandbox_from_output(out)
    try:
        entries = history.load_history(sandbox / "work" / HISTORY_REL)
        last = entries[-1]
        assert last["run_id"] == "replay-fetch"
        assert (last["total"], last["passed"], last["failed"],
                last["retried"], last["attempts"]) == (4, 3, 1, 1, 5)
        by_name = {item["name"]: item for item in last["scenarios"]}
        assert by_name["retry_1"]["attempts"] == 2
        assert by_name["retry_1"]["first_failure"] == "第一次判红：模拟超睡"
        assert by_name["fail_2"]["passed"] is False
        assert by_name["fail_2"]["first_failure"] == "模拟失败：节点未完成"
    finally:
        replay._remove_sandbox(sandbox)


@pytest.mark.parametrize("shape, builder, counts, expected", [
    # 全失败：写回照常记这一轮（失败数据也是数据），计数与逐场景失败原因
    # 必须原样落库。
    ("all_failed", _metrics_all_failed, (3, 0, 3, 0, 3), {
        "fail_0": {"passed": False, "attempts": 1,
                   "first_failure": "全部失败：节点 0 未完成"},
        "fail_1": {"passed": False, "attempts": 1,
                   "first_failure": "全部失败：节点 1 未完成"},
        "fail_2": {"passed": False, "attempts": 1,
                   "first_failure": "全部失败：节点 2 未完成"},
    }),
    # 0 场景：合法形状，不能因为「没东西可写」就悄悄不落库。
    ("empty", _metrics_empty, (0, 0, 0, 0, 0), {}),
    # 重试多次后仍失败：attempts 只说明试了几次，最终结论看 passed。
    ("multi_retry_failure", _metrics_multi_retry_failure, (2, 1, 1, 2, 5), {
        "never_passes": {"passed": False, "attempts": 3,
                         "first_failure": "三次都失败：模拟节点崩溃"},
        "ok_after_retry": {"passed": True, "attempts": 2,
                           "first_failure": "第一次超时"},
    }),
])
def test_replay_fetch_chain_carries_failure_shapes(
        tmp_path: Path, capsys, shape: str, builder, counts: tuple,
        expected: dict) -> None:
    """R113：全链 artifact 的三种失败形状都要原样落进历史。

    生产 artifact 保持真实全过形状（不造假）；失败形状由本地 HTTP artifact
    夹具提供，但走的仍是真实 ``fetch_ci_artifact.fetch()`` → ``writeback()``。
    全失败、0 场景、重试多次仍失败各自钉一组计数与逐场景内容——只数 total
    或只判断「写回成功」都区分不了它们。
    """
    repo = _seed(tmp_path)
    fetched = builder(tmp_path / "artifact-metrics.json")
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": fetched.read_bytes()}))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
            "--keep",
        ]) == 0, shape

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert f"metrics 内容 total={counts[0]}" in out
    if shape == "empty":
        # 空语义行看起来像「指纹没打」；0 场景要显式说出来（R113）。
        assert "metrics 语义 （无场景）" in out
    elif shape == "all_failed":
        assert "fail_0=fail/1 fail_1=fail/1 fail_2=fail/1" in out
    else:
        assert "never_passes=fail/3 ok_after_retry=retry/2" in out

    sandbox = _sandbox_from_output(out)
    try:
        entries = history.load_history(sandbox / "work" / HISTORY_REL)
        last = entries[-1]
        assert last["run_id"] == "replay-fetch"
        assert (last["total"], last["passed"], last["failed"],
                last["retried"], last["attempts"]) == counts
        by_name = {item["name"]: item for item in last["scenarios"]}
        assert set(by_name) == set(expected)
        for name, fields in expected.items():
            for key, value in fields.items():
                assert by_name[name][key] == value
    finally:
        replay._remove_sandbox(sandbox)


@pytest.mark.parametrize("extra, push_attempts, rounds, tokens", [
    # 被拒一次后成功：retry 只影响 push，不影响本轮 metrics 的内容。
    (["--reject-pushes", "1"], 2, 1, ("第 2 次尝试",)),
    # 第一次拒绝时注入冲突，第三次成功：注入轮 + 本轮 = 2。
    (["--reject-pushes", "2", "--conflict-on-reject", "1"],
     3, 2, ("rebase 冲突（第 1 次）", "第 3 次尝试")),
])
def test_failure_shape_survives_retries(
        tmp_path: Path, capsys, extra: list[str], push_attempts: int,
        rounds: int, tokens: tuple[str, ...]) -> None:
    """R116：失败形状 artifact 经过拒绝/注入后，内容必须原样落库。

    R113 证明失败形状能走完 fetch→writeback；R112 证明拒绝/冲突能走完
    重试循环。两者第一次组合：重试只改变 push 次数与远端轮数，不能把
    artifact 里的 failed/retried/attempts 或逐场景 first_failure 重算掉。
    """
    repo = _seed(tmp_path)
    fetched = _metrics_retry_shape(tmp_path / "artifact-metrics.json")
    result = tmp_path / "result.json"
    routes: dict = {}
    with server(routes) as base:
        routes[api_path("owner/repo", "replay-fetch", "e2e-metrics")] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": fetched.read_bytes()}))

        assert replay.main([
            "--repo", str(repo),
            "--run-id", "replay-fetch",
            "--fetch-api-url", base,
            "--fetch-repo", "owner/repo",
            "--token", "test-token",
            "--result-json", str(result),
            "--keep", *extra,
        ]) == 0

    out = capsys.readouterr().out
    assert "已下载 1 个文件" in out
    assert "metrics 语义 ok_0=ok/1 retry_1=retry/2 fail_2=fail/1" in out
    for token in tokens:
        assert token in out
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == "written"
    assert payload["push_attempts"] == push_attempts
    assert payload["rounds"] == rounds
    assert payload["last_run_id"] == "replay-fetch"

    sandbox = _sandbox_from_output(out)
    try:
        entries = history.load_history(sandbox / "work" / HISTORY_REL)
        last = entries[-1]
        assert last["run_id"] == "replay-fetch"
        assert (last["total"], last["passed"], last["failed"],
                last["retried"], last["attempts"]) == (4, 3, 1, 1, 5)
        by_name = {item["name"]: item for item in last["scenarios"]}
        assert by_name["retry_1"]["attempts"] == 2
        assert by_name["retry_1"]["first_failure"] == "第一次判红：模拟超睡"
        assert by_name["fail_2"]["passed"] is False
        assert by_name["fail_2"]["first_failure"] == "模拟失败：节点未完成"
    finally:
        replay._remove_sandbox(sandbox)


@pytest.mark.parametrize("shape, directory, expected, note", SHAPE_FIXTURES)
def test_trend_table_consumes_the_replayed_shapes(
        tmp_path: Path, capsys, shape: str, directory: str,
        expected: tuple[str, ...], note: str | None) -> None:
    """R122：写回产生的失败形状必须被趋势表真的消费。

    R113/R119–R121 证明形状能入库；R115 证明趋势表有失败列。这里把两段
    接起来：用同一组夹具走真实 replay 写回，再从沙箱 history 渲染趋势表，
    断 `场景/失败/重跑/重跑率/总尝试` 五列与 0 场景文案。只断言「写回成功」
    或只断言「表里有失败列」都发现不了「入库的形状在展示层被读错」。
    """
    repo = _seed(tmp_path)
    metrics = REPO_ROOT / "tests" / "fixtures" / directory / "e2e-metrics.json"
    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(metrics),
        "--run-id", "shape",
        "--keep",
    ]) == 0
    out = capsys.readouterr().out
    sandbox = _sandbox_from_output(out)
    try:
        entries = history.load_history(sandbox / "work" / HISTORY_REL)
        assert entries[-1]["run_id"] == "shape"
        trend = history.render_trend(entries)
        assert "| 失败 |" in trend, trend
        row = next(line for line in trend.splitlines()
                   if line.startswith("| shape |"))
        columns = [cell.strip() for cell in row.split("|")]
        assert tuple(columns[3:8]) == expected, row
        if note is not None:
            assert note in trend, trend
    finally:
        replay._remove_sandbox(sandbox)


# ------------------------------------------------- 语义指纹截断（R128）
def test_semantics_line_truncates_display_but_not_the_record(
        tmp_path: Path, capsys) -> None:
    """first_failure 超 160 字符：展示行截断加省略号，history 留全文。

    截断只影响 CI 日志里的一行展示（``SEMANTICS_TEXT_LIMIT=160``），不参与
    判决、更不能改写入库内容——两半都要钉住，否则「为了日志好看」会悄悄
    把数据截了。
    """
    long_text = "模拟失败：" + "超" * 200  # 205 字符，超过 160
    metrics = tmp_path / "long.json"
    metrics.write_text(json.dumps({
        "schema": 1, "total": 2, "passed": 1, "failed": 1, "retried": 0,
        "scenarios": [
            {"name": "ok_0", "passed": True, "attempts": 1,
             "first_failure": ""},
            {"name": "fail_1", "passed": False, "attempts": 1,
             "first_failure": long_text},
        ]}), encoding="utf-8")

    # 展示半边：单元级断言截断形状（前 160 字符 + 省略号，全文不出现）。
    # 期望钉死字面 160：展示参数是政策，漂移必须先改这里（自引用常量
    # 会让「LIMIT 改小」这类变异静默通过，R128 变异 M3 实测踩中）。
    entry = history.entry_from_metrics(
        json.loads(metrics.read_text(encoding="utf-8")))
    semantics, failures = replay._metrics_semantics(entry)
    assert "fail_1=fail/1" in semantics
    assert failures == f"fail_1={long_text[:160]}…"

    # 入库半边：真实写回后 history 里的 first_failure 仍是全文。
    repo = _seed(tmp_path)
    assert replay.main([
        "--repo", str(repo),
        "--metrics", str(metrics),
        "--run-id", "long-failure",
        "--keep",
    ]) == 0
    out = capsys.readouterr().out
    assert f"fail_1={long_text[:160]}…" in out
    assert long_text not in out
    sandbox = _sandbox_from_output(out)
    try:
        entries = history.load_history(sandbox / "work" / HISTORY_REL)
        by_name = {item["name"]: item for item in entries[-1]["scenarios"]}
        assert by_name["fail_1"]["first_failure"] == long_text
    finally:
        replay._remove_sandbox(sandbox)
