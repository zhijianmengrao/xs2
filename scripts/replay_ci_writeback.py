"""本地回放一次 CI 写回（R94）。

把「checkout → record → commit → push（含 rebase 重试）」在**临时沙箱**里
走一遍：从 ``--repo`` 克隆一个裸仓作为 origin，再克隆工作区，调用真实的
``ci_writeback_history.writeback()``。源仓库一个字节都不动。

仍然无法本地复现的只剩 ``actions/download-artifact`` 的传输本身——本工具用
``--metrics`` 直接喂文件，覆盖的是它的下游。

用法::

    python scripts/replay_ci_writeback.py --metrics m.json --run-id replay-1
    python scripts/replay_ci_writeback.py --repo . --metrics m.json \\
        --run-id replay-1 --dry-run --keep
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_writeback_history as writeback
from scripts import e2e_retry_history as history

DEFAULT_HISTORY = "tests/fixtures/e2e_retry_history/history.json"


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=None if cwd is None else str(cwd),
        capture_output=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} 失败：{detail}")
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _rounds(path: Path) -> int:
    try:
        return len(history.load_history(path))
    except history.HistoryError:
        return 0


def replay(repo: Path, metrics: Path, run_id: str,
           history_rel: str = DEFAULT_HISTORY, branch: str = "main",
           keep: bool = False, summary_path: Path | None = None,
           dry_run: bool = False) -> int:
    repo = Path(repo).resolve()
    sandbox = Path(tempfile.mkdtemp(prefix="replay-ci-writeback-"))
    code = 1
    try:
        source_head = _git("rev-parse", "HEAD", cwd=repo)
        origin = sandbox / "origin.git"
        _git("clone", "--bare", "-q", str(repo), str(origin))
        work = sandbox / "work"
        _git("clone", "-q", "-b", branch, str(origin), str(work))
        target = work / history_rel
        before = _rounds(target)

        code = writeback.writeback(
            Path(metrics).resolve(), target, run_id, work, branch=branch,
            summary_path=summary_path, dry_run=dry_run)

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
        if keep:
            print(f"replay：沙箱保留在 {sandbox}")
        else:
            shutil.rmtree(sandbox, ignore_errors=True)
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="源仓库（只读，克隆到沙箱）")
    parser.add_argument("--metrics", type=Path, required=True,
                        help="e2e 写出的 metrics JSON")
    parser.add_argument("--run-id", required=True, help="回放轮次的 run_id")
    parser.add_argument("--history", default=DEFAULT_HISTORY,
                        help="仓库内的历史文件相对路径")
    parser.add_argument("--branch", default="main", help="回放的分支")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件（可选）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只算不写（沙箱里也不提交）")
    parser.add_argument("--keep", action="store_true",
                        help="保留沙箱目录以便检查")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return replay(
        args.repo, args.metrics, args.run_id, args.history, args.branch,
        args.keep, args.summary, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
