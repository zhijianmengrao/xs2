"""本地回放一次 CI 写回（R94/R95/R96）。

把「checkout → (fetch artifact) → record → commit → push（含 rebase 重试）」
在**临时沙箱**里走一遍：从 ``--repo`` 克隆一个裸仓作为 origin，再克隆工作区，
调用真实的 ``ci_writeback_history.writeback()``。源仓库一个字节都不动。

- R94：``--metrics`` 直接喂文件，覆盖 download-artifact 的下游；
- R95：``--from-worktree`` 把已跟踪未提交改动带进沙箱；
- R96：``--fetch-api-url`` 先走真实的 ``fetch_ci_artifact.fetch()``（列表 →
  下载 zip → 解压），再跑 writeback——下载→写回整链本地一次走完。

仍然无法本地复现的只剩上传侧的 ``actions/upload-artifact``。

用法::

    python scripts/replay_ci_writeback.py --metrics m.json --run-id replay-1
    python scripts/replay_ci_writeback.py --repo . --metrics m.json \\
        --run-id replay-1 --dry-run --keep
    python scripts/replay_ci_writeback.py --repo . --run-id replay-1 \\
        --fetch-api-url http://127.0.0.1:9000 --fetch-repo owner/repo
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_writeback_history as writeback
from scripts import e2e_retry_history as history
from scripts import fetch_ci_artifact as artifact_fetch

DEFAULT_HISTORY = "tests/fixtures/e2e_retry_history/history.json"
ARTIFACT_NAME = "e2e-metrics"
METRICS_FILENAME = "e2e-metrics.json"


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=None if cwd is None else str(cwd),
        capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} 失败：{detail}")
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", "replace").strip()


def _apply_worktree_changes(source: Path, work: Path) -> None:
    """把源仓库**已跟踪文件**的未提交改动带进沙箱（R95）。

    用 ``git diff HEAD --binary``：暂存与未暂存都包含，二进制也不丢。未跟踪
    文件不进入——工作区里的杂物（日志、临时脚本）不该被误当成被测状态。
    """
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--binary"], cwd=str(source),
        capture_output=True)
    if diff.returncode != 0:
        raise RuntimeError(f"git diff HEAD 失败：{_decode(diff.stderr)}")
    if diff.stdout:
        applied = subprocess.run(
            ["git", "apply", "--binary", "--whitespace=nowarn", "-"],
            cwd=str(work), input=diff.stdout, capture_output=True)
        if applied.returncode != 0:
            raise RuntimeError(
                f"工作树补丁无法应用到沙箱：{_decode(applied.stderr)}")
        print(f"replay：已把工作树未提交改动带入沙箱"
              f"（{len(diff.stdout)} 字节补丁）")
    else:
        print("replay：工作树没有已跟踪文件的未提交改动")

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(source), capture_output=True)
    if untracked.returncode != 0:
        raise RuntimeError(f"git ls-files 失败：{_decode(untracked.stderr)}")
    names = [line for line in
             untracked.stdout.decode("utf-8", "replace").splitlines() if line]
    if names:
        print(f"replay：提醒：{len(names)} 个未跟踪文件不进入回放"
              f"（只带已跟踪改动）")


def _install_rejection_hook(origin: Path, rejections: int) -> None:
    """在沙箱 origin 上装 pre-receive：前 ``rejections`` 次 push 被拒（R99）。"""
    hook = origin / "hooks" / "pre-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        'counter="$GIT_DIR/replay-reject-count"\n'
        'n=$(cat "$counter" 2>/dev/null || echo 0)\n'
        f'if [ "$n" -lt {rejections} ]; then\n'
        '  echo $((n + 1)) > "$counter"\n'
        '  echo "replay: simulated rejection" >&2\n'
        '  exit 1\n'
        'fi\n'
        'exit 0\n',
        encoding="utf-8",
        # Windows 文本模式会把 shebang 写成 ``#!/bin/sh\r``；Git for Windows
        # 的 sh 对 CRLF 不该赌运气（R103）。
        newline="\n")
    hook.chmod(0o755)
    print(f"replay：已安装拒绝钩子（前 {rejections} 次 push 被拒）")


def _create_conflicting_round(work: Path, origin: Path, branch: str,
                              history_rel: str, sandbox: Path) -> None:
    """让 origin 先前进一轮 history.json，制造 rebase 冲突（R99）。"""
    entries = history.load_history(work / history_rel)
    # 与 record 的窗口语义一致：满 MAX_ROUNDS 时挤掉最早一轮。否则满窗
    # 失败场景（R105 的组合场景）会把 origin 留在 41 轮——生产里 record
    # 永远不会写出这种历史，夹具自己造出来就会让窗口断言失去意义。
    entries = (entries + [{
        "run_id": "replay-conflict",
        "exported_at": "2026-11-02T00:00:00+00:00",
        "source": "local",
        "total": 1, "passed": 1, "failed": 0, "retried": 0, "attempts": 1,
        "scenarios": [{"name": "conflict", "passed": True, "attempts": 1,
                       "first_failure": ""}],
    }])[-history.MAX_ROUNDS:]
    history.validate_history({"schema": history.SCHEMA, "history": entries})
    other = sandbox / "other"
    _git("clone", "-q", str(origin), str(other))
    (other / history_rel).write_text(
        json.dumps({"schema": history.SCHEMA, "history": entries},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    _git("add", "--", history_rel, cwd=other)
    _git("-c", "user.name=replay", "-c", "user.email=replay@example.com",
         "commit", "-q", "-m", "replay: conflicting round", cwd=other)
    _git("push", "-q", "origin", f"HEAD:{branch}", cwd=other)
    print("replay：已在 origin 上制造一轮冲突（history.json）")


def _remove_sandbox(path: Path) -> None:
    """删除沙箱；Windows 上 git 的 pack/object 是只读的。

    ``shutil.rmtree(ignore_errors=True)`` 遇到只读文件会**静默失败**，R94 的
    「默认删除沙箱」因此在 Windows 上一直没真的删掉（R95 的用例发现）。先清
    只读位再删。
    """
    for root, _dirs, files in os.walk(path):
        for name in files:
            target = Path(root) / name
            try:
                # 只补写位、保留其余权限：POSIX 上 chmod(S_IWRITE) 会把
                # 文件/目录改成只写，目录还会丢执行位。
                os.chmod(target, os.stat(target).st_mode | stat.S_IWRITE)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def _rounds(path: Path) -> int:
    try:
        return len(history.load_history(path))
    except history.HistoryError:
        return 0


def replay(repo: Path, metrics: Path | None, run_id: str,
           history_rel: str = DEFAULT_HISTORY, branch: str = "main",
           keep: bool = False, summary_path: Path | None = None,
           dry_run: bool = False, from_worktree: bool = False,
           fetch_api_url: str | None = None,
           artifact: str = ARTIFACT_NAME, fetch_repo: str = "",
           token: str | None = None, reject_pushes: int = 0,
           conflict: bool = False,
           result_path: Path | None = None,
           fetch_run_id: str | None = None) -> int:
    repo = Path(repo).resolve()
    sandbox = Path(tempfile.mkdtemp(prefix="replay-ci-writeback-"))
    code = 1
    try:
        source_head = _git("rev-parse", "HEAD", cwd=repo)
        origin = sandbox / "origin.git"
        _git("clone", "--bare", "-q", str(repo), str(origin))
        work = sandbox / "work"
        _git("clone", "-q", "-b", branch, str(origin), str(work))
        if from_worktree:
            _apply_worktree_changes(repo, work)
        if conflict:
            _create_conflicting_round(work, origin, branch, history_rel, sandbox)
        if reject_pushes:
            _install_rejection_hook(origin, reject_pushes)
        target = work / history_rel
        before = _rounds(target)

        metrics_path = Path(metrics).resolve() if metrics is not None else None
        can_write = True
        if fetch_api_url:
            fetched_dir = sandbox / "e2e"
            fetched = artifact_fetch.fetch(
                fetch_run_id or run_id, fetch_repo, artifact, fetched_dir,
                token=token, api_url=fetch_api_url)
            if fetched != 0:
                code = fetched
                can_write = False
                print("replay：artifact 拉取失败，未进入写回", file=sys.stderr)
            else:
                metrics_path = fetched_dir / METRICS_FILENAME
                if not metrics_path.is_file():
                    print(f"replay：artifact 里没有 {METRICS_FILENAME}，"
                          f"写回会按「没有 metrics」处理", file=sys.stderr)

        if can_write and metrics_path is not None:
            code = writeback.writeback(
                metrics_path, target, run_id, work, branch=branch,
                summary_path=summary_path, dry_run=dry_run,
                result_path=result_path)

        after = _rounds(target)
        head = _git("log", "-1", "--format=%h %s", branch, cwd=origin)
        print(f"replay：历史 {before} → {after} 轮；退出码 {code}；沙箱 HEAD {head}")
        if _git("rev-parse", "HEAD", cwd=repo) != source_head:
            print("replay：源仓库 HEAD 被改动了（不应该发生）", file=sys.stderr)
            code = 1
        else:
            print(f"replay：源仓库 {repo} 未被改动")
    except RuntimeError as exc:
        print(f"replay 失败：{exc}", file=sys.stderr)
        code = 1
    finally:
        # R95：失败时自动保留现场（成功仍删除；--keep 总是保留）。
        if keep or code != 0:
            suffix = "（失败现场）" if code != 0 and not keep else ""
            print(f"replay：沙箱保留在 {sandbox}{suffix}")
        else:
            _remove_sandbox(sandbox)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="源仓库（只读，克隆到沙箱）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--metrics", type=Path, default=None,
                        help="e2e 写出的 metrics JSON（直接喂文件）")
    source.add_argument("--fetch-api-url", default=None,
                        help="先走 fetch_ci_artifact.py 从该 API 拉 artifact（R96）")
    parser.add_argument("--artifact", default=ARTIFACT_NAME,
                        help="--fetch-api-url 的 artifact 名称")
    parser.add_argument("--fetch-repo", default=os.environ.get(
        "GITHUB_REPOSITORY", ""), help="--fetch-api-url 的 owner/name")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"),
                        help="--fetch-api-url 的 token")
    parser.add_argument("--run-id", required=True, help="回放轮次的 run_id")
    parser.add_argument("--fetch-run-id", default=None,
                        help="artifact API 的 run id（默认与 --run-id 相同；"
                             "R103 起生产全链用 GitHub run id）")
    parser.add_argument("--history", default=DEFAULT_HISTORY,
                        help="仓库内的历史文件相对路径")
    parser.add_argument("--branch", default="main", help="回放的分支")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件（可选）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只算不写（沙箱里也不提交）")
    parser.add_argument("--keep", action="store_true",
                        help="保留沙箱目录以便检查")
    parser.add_argument("--from-worktree", action="store_true",
                        help="把源仓库已跟踪文件的未提交改动带进沙箱（R95）")
    parser.add_argument("--reject-pushes", type=int, default=0,
                        help="沙箱 origin 拒绝前 N 次 push（R99）")
    parser.add_argument("--conflict", action="store_true",
                        help="先让 origin 前进一轮冲突历史（R99）")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="写回的机读结果工件（R99）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.reject_pushes < 0:
        print("--reject-pushes 不能为负", file=sys.stderr)
        return 2
    return replay(
        repo=args.repo, metrics=args.metrics, run_id=args.run_id,
        history_rel=args.history, branch=args.branch, keep=args.keep,
        summary_path=args.summary, dry_run=args.dry_run,
        from_worktree=args.from_worktree, fetch_api_url=args.fetch_api_url,
        artifact=args.artifact, fetch_repo=args.fetch_repo, token=args.token,
        reject_pushes=args.reject_pushes, conflict=args.conflict,
        result_path=args.result_json, fetch_run_id=args.fetch_run_id)


if __name__ == "__main__":
    raise SystemExit(main())
