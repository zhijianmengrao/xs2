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
   全失败 → ``::error::`` + 退出 1。

**写权限与执行面分离不变**：这个脚本只被 ``e2e-history-writeback`` job 调用，
仍然不跑 pytest / e2e / npm / docker（``tests/test_ci_history_writeback.py``
反向钉住）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


def commit_and_push(repo: Path, history_path: Path, message: str,
                    branch: str = "main",
                    attempts: int = DEFAULT_ATTEMPTS) -> int:
    """提交历史文件并推送；返回 0 或 1。没有变化时什么都不做。"""
    _git_checked(repo, "add", "--", str(history_path))
    staged = _git(repo, "diff", "--cached", "--quiet", "--", str(history_path))
    if staged.returncode == 0:
        print("history 没有变化（同一 run 重跑），不提交")
        return EXIT_OK

    # 只提交这个文件：即使工作树里还有别的改动（checkout 残留），也不带进去。
    _git_checked(
        repo, "commit", "-m", message, "--", str(history_path))

    for attempt in range(1, attempts + 1):
        push = _git(repo, "push", "origin", f"HEAD:{branch}")
        if push.returncode == 0:
            print(f"已写回 {branch}（第 {attempt} 次尝试）")
            return EXIT_OK
        detail = _decode(push.stderr)
        if detail:
            print(detail, file=sys.stderr)
        print(f"push 被拒（第 {attempt} 次），rebase 到最新 {branch} 后重试")
        pull = _git(repo, "pull", "--rebase", "origin", branch)
        if pull.returncode != 0:
            _git(repo, "rebase", "--abort")
            raise WritebackError(
                f"pull --rebase 失败，本轮历史未入库："
                f"{_decode(pull.stderr) or _decode(pull.stdout)}")

    print(f"::error::push 连续 {attempts} 次均失败（并发写回），本轮历史未入库")
    return EXIT_FAILED


def writeback(metrics_path: Path, history_path: Path, run_id: str,
              repo: Path, branch: str = "main",
              attempts: int = DEFAULT_ATTEMPTS,
              commit_message: str | None = None) -> int:
    """CI 写回的完整链路：metrics → record → commit → push（带重试）。"""
    if attempts < 1:
        print("--attempts 必须 >= 1", file=sys.stderr)
        return EXIT_USAGE
    if not metrics_path.is_file():
        print(f"没有 {metrics_path}（e2e 环境未启动），本轮不入库")
        return EXIT_OK

    code = history.record(metrics_path, history_path, run_id=run_id)
    if code != history.EXIT_OK:
        return code

    message = commit_message or f"chore(e2e): record CI run {run_id} [skip ci]"
    return commit_and_push(repo, history_path, message, branch, attempts)


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return writeback(
            args.metrics, args.history, args.run_id, args.repo,
            branch=args.branch, attempts=args.attempts,
            commit_message=args.commit_message)
    except WritebackError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
