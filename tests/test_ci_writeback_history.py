"""R89：CI 写回链路的行为用例（真实 git 临时仓）。

R88 的重试循环只写在 ``ci.yml`` 里，测试只能断言「YAML 文本里有
``for attempt in 1 2 3``」。子串断言证明不了「push 被拒之后真的会 rebase 再推」
——R68 的教训是重试路径必须在重试真的发生时被走过一次。本文件建
origin / work / other 三个真实仓库，让拒绝**真的发生**：

- 快进：第 1 次 push 成功；
- 落后一个提交：第 1 次被拒 → ``pull --rebase`` → 第 2 次成功，且没有 merge 提交；
- pre-receive 永久拒绝：恰好尝试 ``DEFAULT_ATTEMPTS`` 次后 ``::error::`` + 退出 1；
- 同一 run 重跑：历史逐字节不变，不产生第二次提交；
- 没有 metrics：退出 0、不入库；
- 远端也改了 history.json：rebase 冲突**响亮失败**，不静默丢轮次；
- 只提交历史文件，不卷走工作树里的其它改动。
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from scripts import ci_writeback_history as writeback
from scripts import e2e_retry_history as history

HISTORY_REL = "tests/fixtures/e2e_retry_history/history.json"
IDENTITY = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=None if cwd is None else str(cwd),
        capture_output=True, env={**os.environ, **IDENTITY})
    assert result.returncode == 0, (
        f"git {' '.join(args)} 失败："
        f"{(result.stderr or result.stdout).decode('utf-8', 'replace')}")
    return (result.stdout or b"").decode("utf-8", "replace")


def _metrics_payload(total: int = 10, retried: int = 0) -> dict:
    scenarios = [
        {
            "name": f"scenario_{index}",
            "passed": True,
            "attempts": 2 if index < retried else 1,
            "first_failure": "第一次红了" if index < retried else "",
        }
        for index in range(total)
    ]
    return {
        "schema": 1,
        "total": total,
        "passed": total,
        "failed": 0,
        "retried": retried,
        "scenarios": scenarios,
    }


def _write_metrics(path: Path, retried: int = 0) -> Path:
    path.write_text(
        json.dumps(_metrics_payload(retried=retried), ensure_ascii=False),
        encoding="utf-8")
    return path


def _seed(tmp_path: Path) -> Path:
    """建 bare origin 并推一次初始提交（history.json 已入库）。"""
    origin = tmp_path / "origin.git"
    _git("init", "-q", "-b", "main", "--bare", str(origin))
    seed = tmp_path / "seed"
    _git("clone", "-q", str(origin), str(seed))
    target = seed / HISTORY_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"schema": 1, "history": []}), encoding="utf-8")
    _git("add", "-A", cwd=seed)
    _git("commit", "-q", "-m", "seed", cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    return origin


def _clone(tmp_path: Path, origin: Path, name: str) -> Path:
    work = tmp_path / name
    _git("clone", "-q", str(origin), str(work))
    return work


def _history_path(repo: Path) -> Path:
    return repo / HISTORY_REL


def _origin_log(origin: Path, *args: str) -> str:
    return _git("--git-dir", str(origin), *args)


def _origin_history(origin: Path) -> dict:
    raw = _origin_log(origin, "show", f"main:{HISTORY_REL}")
    return json.loads(raw)


# ------------------------------------------------------------ 快进 / 重试
def test_push_succeeds_on_the_first_attempt(
        tmp_path: Path, capsys) -> None:
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")

    code = writeback.writeback(
        _write_metrics(tmp_path / "metrics.json"),
        _history_path(work), "ci-1", work)

    assert code == 0
    out = capsys.readouterr().out
    assert "第 1 次尝试" in out
    subjects = _origin_log(origin, "log", "--format=%s", "main").splitlines()
    assert subjects[0].startswith("chore(e2e)"), subjects
    assert subjects[0].endswith("[skip ci]"), subjects
    assert _origin_history(origin)["history"][-1]["run_id"] == "ci-1"


def test_rejected_push_rebases_and_succeeds_on_the_second_attempt(
        tmp_path: Path, capsys) -> None:
    """落后一个提交时 push 必被拒：必须 rebase 后重试，而不是硬推或放弃。"""
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    other = _clone(tmp_path, origin, "other")
    (other / "README.md").write_text("advance\n", encoding="utf-8")
    _git("add", "-A", cwd=other)
    _git("commit", "-q", "-m", "advance main", cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)

    code = writeback.writeback(
        _write_metrics(tmp_path / "metrics.json"),
        _history_path(work), "ci-1", work)

    assert code == 0
    out = capsys.readouterr().out
    assert "push 被拒（第 1 次）" in out
    assert "第 2 次尝试" in out

    # rebase 而不是 merge：远端不能出现合并提交，写回提交在顶端。
    assert _origin_log(origin, "rev-list", "--merges", "main").strip() == ""
    subjects = _origin_log(origin, "log", "--format=%s", "main").splitlines()
    assert subjects[0].startswith("chore(e2e)"), subjects
    assert "advance main" in subjects
    assert _origin_history(origin)["history"][-1]["run_id"] == "ci-1"


def test_permanent_rejection_stops_after_the_attempt_cap(
        tmp_path: Path, capsys) -> None:
    """持续被拒：恰好尝试 DEFAULT_ATTEMPTS 次，然后响亮失败（不静默丢历史）。"""
    assert writeback.DEFAULT_ATTEMPTS == 3
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    code = writeback.writeback(
        _write_metrics(tmp_path / "metrics.json"),
        _history_path(work), "ci-1", work)

    assert code == 1
    out = capsys.readouterr().out
    assert out.count("push 被拒") == writeback.DEFAULT_ATTEMPTS
    assert "::error::" in out
    # 远端没有多出提交：失败的轮次没有半提交上去。
    assert len(_origin_log(origin, "log", "--format=%s", "main").splitlines()) == 1


# ---------------------------------------------------------------- 幂等
def test_same_run_rerun_does_not_create_a_second_commit(
        tmp_path: Path, capsys, monkeypatch) -> None:
    """同一 run 重跑且观测一致：历史逐字节不变，不产生第二次提交。

    R89 实测：``record`` 原先每次写新的 ``exported_at``，所以 R88 文案里的
    「内容不变就不提交」在重跑时并不成立。这条用例同时钉住修复与写回链路；
    第二次重跑的时间戳**必须**被推后，否则同秒内会假绿（变异 M7 实测）。
    """
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    metrics = _write_metrics(tmp_path / "metrics.json")

    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T00:00:00+00:00")
    assert writeback.writeback(metrics, _history_path(work), "ci-1", work) == 0
    head = _git("rev-parse", "HEAD", cwd=work)

    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T09:00:00+00:00")
    assert writeback.writeback(metrics, _history_path(work), "ci-1", work) == 0

    out = capsys.readouterr().out
    assert "没有变化" in out
    assert _git("rev-parse", "HEAD", cwd=work) == head
    assert len(_origin_history(origin)["history"]) == 1
    assert _origin_history(origin)["history"][0]["exported_at"] == (
        "2026-11-01T00:00:00+00:00")


def test_commit_does_not_sweep_unrelated_changes(tmp_path: Path) -> None:
    """工作树里已暂存的杂项也不能被写回提交卷走（commit 必须带 pathspec）。"""
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    (work / "stray.txt").write_text("dirty\n", encoding="utf-8")
    _git("add", "stray.txt", cwd=work)

    assert writeback.writeback(
        _write_metrics(tmp_path / "metrics.json"),
        _history_path(work), "ci-1", work) == 0

    committed = _origin_log(
        origin, "show", "--name-only", "--format=", "main").split()
    assert committed == [HISTORY_REL], committed


# ------------------------------------------------------------ 跳过与失败
def test_missing_metrics_is_not_a_failure(
        tmp_path: Path, capsys) -> None:
    """环境没起来（没有 metrics）不是写回的失败：退出 0，历史不动。"""
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    head = _git("rev-parse", "HEAD", cwd=work)

    code = writeback.writeback(
        tmp_path / "missing.json", _history_path(work), "ci-1", work)

    assert code == 0
    assert "本轮不入库" in capsys.readouterr().out
    assert _git("rev-parse", "HEAD", cwd=work) == head


def test_rebase_conflict_fails_loudly_instead_of_losing_the_round(
        tmp_path: Path, capsys) -> None:
    """远端也改了 history.json：rebase 冲突必须响亮失败（::error:: + 退出 1）。"""
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")
    other = _clone(tmp_path, origin, "other")
    # 模拟「有人在 main 上手工写入了另一轮」。
    other_history = _history_path(other)
    payload = json.loads(other_history.read_text(encoding="utf-8"))
    payload["history"].append({
        "run_id": "manual-1", "exported_at": "2026-11-01T00:00:00+00:00",
        **history.entry_from_metrics(_metrics_payload())})
    other_history.write_text(json.dumps(payload), encoding="utf-8")
    _git("add", "-A", cwd=other)
    _git("commit", "-q", "-m", "manual round", cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)

    code = writeback.main([
        "--metrics", str(_write_metrics(tmp_path / "metrics.json")),
        "--history", str(_history_path(work)),
        "--run-id", "ci-1",
        "--repo", str(work),
    ])

    assert code == 1
    captured = capsys.readouterr()
    assert "::error::" in captured.err
    assert "历史未入库" in captured.err


# ------------------------------------------------------------------ CLI
def test_cli_has_the_same_semantics_as_the_function(tmp_path: Path) -> None:
    origin = _seed(tmp_path)
    work = _clone(tmp_path, origin, "work")

    code = writeback.main([
        "--metrics", str(_write_metrics(tmp_path / "metrics.json")),
        "--history", str(_history_path(work)),
        "--run-id", "ci-9",
        "--repo", str(work),
        "--commit-message", "chore(e2e): record CI run 9 [skip ci]",
    ])

    assert code == 0
    assert _origin_history(origin)["history"][-1]["run_id"] == "ci-9"
    subjects = _origin_log(origin, "log", "--format=%s", "main").splitlines()
    assert subjects[0] == "chore(e2e): record CI run 9 [skip ci]"
