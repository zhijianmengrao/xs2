"""CI 写回 e2e 重跑历史（R89：从 ci.yml 提取的可执行链路）。

R88 把写回做成独立 job，但「提交 → push → 被拒 → rebase 重试」只写在 YAML
里：本地跑不了，测试只能对 YAML 文本做子串断言。子串断言证明不了「被拒之后
真的会 rebase 再推」——R68 的教训是重试路径必须在重试真的发生时被走过一次。

本模块把这段逻辑搬进可执行代码，``tests/test_ci_writeback_history.py`` 用
真实 git 临时仓驱动每一条分支（快进、被拒一次后成功、三次全失败、无变化、
无 metrics）。行为与 R88 的 YAML 步骤逐条对应：

1. metrics 不存在 → 打印「本轮不入库」并退出 0（环境没起来不是写回的失败）；
2. ``record``（同一 run_id 覆盖同一轮，R78 契约）；
3. 历史无变化 → 不提交、退出 0；
4. 有变化 → 提交（信息带 ``[skip ci]``，防止将来换 PAT 后自触发）；
5. push 被拒 → ``pull --rebase`` 后重试，最多 ``DEFAULT_ATTEMPTS`` 次；
   rebase 成功只需重推，**rebase 冲突则丢弃本地提交、按最新分支重算**
   （R90：否则一次并发编辑就让这一轮永久丢失）；全失败 → ``::error::`` + 退出 1。
6. 每轮结果（``written`` / ``no-change`` / ``metrics-missing`` /
   ``record-invalid`` / ``push-rejected`` / ``rebase-conflict`` / ``git-error``）
   以**固定类别**追加进 step summary（R91）：同一个退出码可能来自不同原因，
   类别必须让处置各不相同（R64 教训）。
7. ``--dry-run`` 只在历史副本上算一遍并报告将写入的轮次，不写文件、不提交、
   不推送（R94）——用于本地预演，也是 ``scripts/replay_ci_writeback.py`` 的底座。

**写权限与执行面分离不变**：这个脚本只被 ``e2e-history-writeback`` job 调用，
仍然不跑 pytest / e2e / npm / docker（``tests/test_ci_history_writeback.py``
反向钉住）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_reporting
from scripts import e2e_retry_history as history

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"

# push 重试上限。这是**判决边界**（第 3 次失败就报错），所以既有值断言也有
# 行为用例：被拒 1 次必须在第 2 次成功，持续被拒必须恰好尝试 3 次后失败（R69）。
DEFAULT_ATTEMPTS = 3


class WritebackError(RuntimeError):
    """git 操作失败；消息会以 ``::error::`` 形式出现在 CI 日志里。"""


def _decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", "replace").strip()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    # 身份走环境变量而不是 `git config`：pull --rebase 会重写提交、也需要
    # committer 身份，而它不在我们显式 commit 的那条命令上（R89 实测：
    # 只给 commit 加 -c 时，被拒后的 rebase 仍会因缺身份而失败）。
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": BOT_NAME,
        "GIT_AUTHOR_EMAIL": BOT_EMAIL,
        "GIT_COMMITTER_NAME": BOT_NAME,
        "GIT_COMMITTER_EMAIL": BOT_EMAIL,
    }
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, env=env)


def _git_checked(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = _git(repo, *args)
    if result.returncode != 0:
        detail = _decode(result.stderr) or _decode(result.stdout)
        raise WritebackError(f"git {' '.join(args)} 失败：{detail}")
    return result


# 失败/结果的**类别**：写进 step summary，也进 ``::error::`` 文案。
# 同一退出码可能来自不同原因（R64 教训），所以类别必须是单独的、固定的字符串，
# 不能让「record 坏了」和「push 被拒」共用一句话。
REASON_WRITTEN = "written"
REASON_NO_CHANGE = "no-change"
REASON_METRICS_MISSING = "metrics-missing"
REASON_RECORD_INVALID = "record-invalid"
REASON_PUSH_REJECTED = "push-rejected"
REASON_REBASE_CONFLICT = "rebase-conflict"
REASON_GIT_ERROR = "git-error"
REASON_USAGE = "usage"
REASON_DRY_RUN = "dry-run"

# 机读结果工件的 schema（R97）。类别字面值与 summary 共用同一份常量。
RESULT_SCHEMA = 1


def _rounds(history_path: Path) -> str:
    try:
        return str(len(history.load_history(history_path)))
    except history.HistoryError:
        return "?"


def _remote_rounds(repo: Path, branch: str, history_path: Path) -> int | None:
    """机读工件的轮数：读 ``origin/<branch>`` 的**已入库**历史。

    push 被拒时本地文件可能已经写上这一轮；直接读本地会把「本轮未入库」
    报成比远端多一。git 不可用/路径不在仓库内时给 null，不猜。
    """
    try:
        relative = history_path.resolve().relative_to(Path(repo).resolve())
    except (OSError, ValueError):
        relative = history_path
    result = _git(repo, "show", f"origin/{branch}:{relative.as_posix()}")
    if result.returncode != 0:
        return None
    try:
        return len(history.validate_history(json.loads(result.stdout)))
    except (ValueError, history.HistoryError):
        return None


def _has_staged_change(repo: Path, history_path: Path) -> bool:
    result = _git(repo, "diff", "--cached", "--quiet", "--", str(history_path))
    return result.returncode != 0


def _writeback_steps(metrics_path: Path, history_path: Path, run_id: str,
                     repo: Path, branch: str, attempts: int,
                     commit_message: str | None) -> tuple[int, str, str, int]:
    """执行写回，返回 ``(退出码, 类别, 说明, push 尝试次数)``。

    类别用于 summary、报错与机读结果工件（R97）；``push_attempts`` 只统计
    真正发起的 push（缺 metrics / 无变化 / 用法错误都是 0）。
    """
    attempts_made = 0
    if attempts < 1:
        print("--attempts 必须 >= 1", file=sys.stderr)
        return EXIT_USAGE, REASON_USAGE, "--attempts 必须 >= 1", attempts_made
    if not metrics_path.is_file():
        print(f"没有 {metrics_path}（e2e 环境未启动），本轮不入库")
        return (EXIT_OK, REASON_METRICS_MISSING,
                "e2e 环境未启动，本轮不入库", attempts_made)

    message = commit_message or f"chore(e2e): record CI run {run_id} [skip ci]"
    prepared = False
    last_failure = REASON_PUSH_REJECTED
    for attempt in range(1, attempts + 1):
        if not prepared:
            code = history.record(metrics_path, history_path, run_id=run_id,
                                  source="ci")
            if code != history.EXIT_OK:
                return (code, REASON_RECORD_INVALID,
                        f"record 退出 {code}，本轮不入库", attempts_made)
            _git_checked(repo, "add", "--", str(history_path))
            if not _has_staged_change(repo, history_path):
                print("history 没有变化（同一 run 重跑），不提交")
                return (EXIT_OK, REASON_NO_CHANGE,
                        f"历史已含这一轮（{_rounds(history_path)}/"
                        f"{history.MAX_ROUNDS} 轮），不提交", attempts_made)
            # 只提交这个文件：即使工作树里还有别的改动（checkout 残留），也不带进去。
            _git_checked(
                repo, "commit", "-m", message, "--", str(history_path))
            prepared = True

        attempts_made = attempt
        push = _git(repo, "push", "origin", f"HEAD:{branch}")
        if push.returncode == 0:
            print(f"已写回 {branch}（第 {attempt} 次尝试）")
            return (EXIT_OK, REASON_WRITTEN,
                    f"第 {attempt} 次尝试，历史 {_rounds(history_path)}/"
                    f"{history.MAX_ROUNDS} 轮", attempts_made)
        detail = _decode(push.stderr)
        if detail:
            print(detail, file=sys.stderr)
        print(f"push 被拒（第 {attempt} 次），rebase 到最新 {branch} 后重试")
        last_failure = REASON_PUSH_REJECTED
        pull = _git(repo, "pull", "--rebase", "origin", branch)
        if pull.returncode == 0:
            # 提交已被 rebase 到最新分支：下一次只需重推，不要再 record
            # （再 record 会得到「没有变化」并提前返回 0，把这一轮丢掉）。
            continue

        _git(repo, "rebase", "--abort")
        print(f"rebase 冲突（第 {attempt} 次）：丢弃本次写回提交，"
              f"按最新 {branch} 重算")
        _git_checked(repo, "fetch", "origin", branch)
        _git_checked(repo, "reset", "--hard", f"origin/{branch}")
        prepared = False
        last_failure = REASON_REBASE_CONFLICT

    print(f"::error::连续 {attempts} 次写回均失败"
          f"（最后一次：{last_failure}），本轮历史未入库")
    return (EXIT_FAILED, last_failure,
            f"连续 {attempts} 次写回均失败（最后一次：{last_failure}）",
            attempts_made)


def _rehearse(metrics_path: Path, history_path: Path, run_id: str,
              source: str) -> tuple[int, str, str, int]:
    """dry-run：在历史**副本**上真算一遍，不碰仓库、不落盘（R94）。

    dry-run 不发起 push，所以尝试次数固定是 0。
    """
    if not metrics_path.is_file():
        print(f"没有 {metrics_path}（e2e 环境未启动），本轮不入库（dry-run）")
        return (EXIT_OK, REASON_METRICS_MISSING,
                "e2e 环境未启动，本轮不入库", 0)
    before = history_path.read_bytes() if history_path.is_file() else b""
    try:
        previous = len(history.load_history(history_path)) if before else 0
    except history.HistoryError as exc:
        print(str(exc), file=sys.stderr)
        return history.EXIT_META_DRIFT, REASON_RECORD_INVALID, str(exc), 0

    with tempfile.TemporaryDirectory(prefix="ci-writeback-dry-run-") as tmp:
        copy = Path(tmp) / history_path.name
        if before:
            copy.write_bytes(before)
        code = history.record(metrics_path, copy, run_id=run_id, source=source)
        if code != history.EXIT_OK:
            return (code, REASON_RECORD_INVALID,
                    f"record 退出 {code}，本轮不入库", 0)
        after = copy.read_bytes()
        rounds = len(history.load_history(copy))

    if after == before:
        print(f"dry-run：history 没有变化（run_id={run_id} 已在历史里）")
        return (EXIT_OK, REASON_NO_CHANGE,
                f"历史已含这一轮（{rounds}/{history.MAX_ROUNDS} 轮），未提交", 0)
    print(f"dry-run：将记录 run_id={run_id}（来源 {source}），"
          f"历史 {rounds}/{history.MAX_ROUNDS} 轮"
          f"（+{rounds - previous}，未写入）")
    return (EXIT_OK, REASON_DRY_RUN,
            f"将写入历史 {rounds}/{history.MAX_ROUNDS} 轮"
            f"（+{rounds - previous}，未提交）", 0)


def writeback(metrics_path: Path, history_path: Path, run_id: str,
              repo: Path, branch: str = "main",
              attempts: int = DEFAULT_ATTEMPTS,
              commit_message: str | None = None,
              summary_path: Path | None = None,
              dry_run: bool = False,
              result_path: Path | None = None) -> int:
    """CI 写回的完整链路：metrics → record → commit → push（带重试与重算）。

    每一轮 ``record`` 都在**当前历史**上重算：push 被拒后 rebase 成功时提交
    已经在最新分支上，只需重推；rebase 冲突时本地提交是在旧历史上算的，丢弃
    它、回到最新分支后重算（R90）——否则一轮历史会因为一次并发编辑而丢失。

    ``result_path``（R97）写机读 JSON：与 summary 共用同一组 ``reason`` /
    ``detail``，含 ``exit_code`` / ``rounds`` / ``push_attempts`` / ``dry_run``。
    写失败只告警，不改变退出码。
    """
    push_attempts = 0
    if dry_run:
        code, reason, detail, push_attempts = _rehearse(
            metrics_path, history_path, run_id, source="ci")
    else:
        try:
            code, reason, detail, push_attempts = _writeback_steps(
                metrics_path, history_path, run_id, repo, branch, attempts,
                commit_message)
        except WritebackError as exc:
            print(f"::error::{exc}", file=sys.stderr)
            code, reason, detail = EXIT_FAILED, REASON_GIT_ERROR, str(exc)
    ci_reporting.emit_summary(summary_path, run_id, reason, detail)
    ci_reporting.emit_result(result_path, {
        "schema": RESULT_SCHEMA,
        "run_id": run_id,
        "source": "ci",
        "reason": reason,
        "detail": detail,
        "exit_code": code,
        "rounds": _remote_rounds(repo, branch, history_path),
        "push_attempts": push_attempts,
        "dry_run": dry_run,
    })
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, required=True,
                        help="e2e 写出的 metrics JSON")
    parser.add_argument("--history", type=Path, required=True,
                        help="入库的重跑历史")
    parser.add_argument("--run-id", required=True,
                        help="历史键（CI 用 ci-<github.run_id>）")
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="执行 git 的仓库目录")
    parser.add_argument("--branch", default="main", help="推送目标分支")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS,
                        help="push 重试上限")
    parser.add_argument("--commit-message", default=None,
                        help="提交信息（默认带 run_id 与 [skip ci]）")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件；缺省读 GITHUB_STEP_SUMMARY")
    parser.add_argument("--dry-run", action="store_true",
                        help="只在历史副本上算一遍并报告，不写文件、不提交（R94）")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="机读结果工件（R97）；写失败只告警")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return writeback(
        args.metrics, args.history, args.run_id, args.repo,
        branch=args.branch, attempts=args.attempts,
        commit_message=args.commit_message,
        summary_path=args.summary or ci_reporting.default_summary_path(),
        dry_run=args.dry_run, result_path=args.result_json)


if __name__ == "__main__":
    raise SystemExit(main())
