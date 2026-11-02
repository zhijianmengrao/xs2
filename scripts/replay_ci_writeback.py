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
    python scripts/replay_ci_writeback.py --repo . --metrics m.json \\
        --run-id replay-1 --reject-pushes 2 --conflict-on-reject 2
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


def _conflict_hook_source(branch: str, history_rel: str) -> str:
    """在第 N 次拒绝时在 origin 上追加冲突轮（R108/R112）。

    在 ``pre-receive`` 里用 plumbing 直接更新 ref：``read-tree`` 到临时
    index → 替换 history blob → ``write-tree`` → ``commit-tree`` →
    ``update-ref``。不走工作树，Windows 上也没有 checkout 的路径问题。

    Git 在钩子里会设置 quarantine 的对象目录；写进去的 blob/commit 会在
    钩子失败（exit 1）后被丢弃，``update-ref`` 就指向不存在的对象。因此
    必须显式移除 ``GIT_OBJECT_DIRECTORY`` 等变量，让对象写进真实库。
    """
    entry = repr(_conflict_entry())
    return f'''import json
import os
import subprocess

GIT_DIR = os.environ["GIT_DIR"]
BRANCH = {branch!r}
HISTORY = {history_rel!r}
MAX_ROUNDS = {history.max_rounds()}
ENTRY = {entry}

env = os.environ.copy()
for _key in ("GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
             "GIT_QUARANTINE_PATH"):
    env.pop(_key, None)
env.update({{
    "GIT_AUTHOR_NAME": "replay",
    "GIT_AUTHOR_EMAIL": "replay@example.com",
    "GIT_COMMITTER_NAME": "replay",
    "GIT_COMMITTER_EMAIL": "replay@example.com",
}})


def git(*args, input=None, index=None):
    run_env = env
    if index is not None:
        run_env = dict(env)
        run_env["GIT_INDEX_FILE"] = index
    return subprocess.run(
        ["git", "--git-dir", GIT_DIR, *args], input=input,
        capture_output=True, check=True, env=run_env)


ref = "refs/heads/" + BRANCH
old = git("rev-parse", ref).stdout.strip()
raw = git("show", ref + ":" + HISTORY).stdout
payload = json.loads(raw)
entries = (payload["history"] + [ENTRY])[-MAX_ROUNDS:]
blob = (json.dumps({{"schema": payload["schema"], "history": entries}},
                   ensure_ascii=False, indent=2) + "\\n").encode("utf-8")
blob_sha = git("hash-object", "-w", "--stdin",
               input=blob).stdout.strip().decode()
index_file = os.path.join(GIT_DIR, "hooks", "replay-conflict.index")
try:
    git("read-tree", ref, index=index_file)
    git("update-index", "--add", "--cacheinfo", "100644", blob_sha, HISTORY,
        index=index_file)
    tree = git("write-tree", index=index_file).stdout.strip().decode()
finally:
    if os.path.exists(index_file):
        os.unlink(index_file)
commit = git("commit-tree", tree, "-p", old.decode(),
             "-m", "replay: hook-conflicting round").stdout.strip().decode()
git("update-ref", ref, commit, old.decode())
'''


def _install_rejection_hook(origin: Path, rejections: int,
                            inject_conflict_at: int = 0,
                            branch: str = "main",
                            history_rel: str = DEFAULT_HISTORY) -> None:
    """在沙箱 origin 上装 pre-receive：前 ``rejections`` 次 push 被拒（R99）。

    ``inject_conflict_at=N``（R108/R112）时，**第 N 次拒绝**会先在 origin 上
    追加一轮冲突历史再拒绝。N=1 即 R108 的「第一次拒绝时注入」；N>1 覆盖
    预算中途耗尽的时间线（钩子先正常拒绝几次，直到第 N 次才推进 origin）。
    调用方必须保证 ``rejections >= N``，否则注入点永远到不了——那会静默
    退化成「没有注入」的普通拒绝。
    """
    hook = origin / "hooks" / "pre-receive"
    hook.parent.mkdir(parents=True, exist_ok=True)
    inject = ""
    if inject_conflict_at:
        script = origin / "hooks" / "replay_conflict_inject.py"
        script.write_text(_conflict_hook_source(branch, history_rel),
                          encoding="utf-8", newline="\n")
        script.chmod(0o755)
        python = Path(sys.executable).as_posix().replace('"', '\\"')
        # ``$n`` 是**此前**已被拒的次数（0 起算），所以第 N 次拒绝对应 n=N-1。
        inject = (
            f'  if [ "$n" -eq {inject_conflict_at - 1} ]; then\n'
            f'    "{python}" "$GIT_DIR/hooks/replay_conflict_inject.py"'
            ' || exit 1\n'
            '  fi\n')
    hook.write_text(
        "#!/bin/sh\n"
        'counter="$GIT_DIR/replay-reject-count"\n'
        'n=$(cat "$counter" 2>/dev/null || echo 0)\n'
        f'if [ "$n" -lt {rejections} ]; then\n'
        '  echo $((n + 1)) > "$counter"\n'
        + inject +
        '  echo "replay: simulated rejection" >&2\n'
        '  exit 1\n'
        'fi\n'
        'exit 0\n',
        encoding="utf-8",
        # Windows 文本模式会把 shebang 写成 ``#!/bin/sh\r``；Git for Windows
        # 的 sh 对 CRLF 不该赌运气（R103）。
        newline="\n")
    hook.chmod(0o755)
    injected_at = (f"，第 {inject_conflict_at} 次拒绝时注入冲突"
                   if inject_conflict_at else "")
    print(f"replay：已安装拒绝钩子（前 {rejections} 次 push 被拒{injected_at}）")


CONFLICT_RUN_ID = "replay-conflict"


def _conflict_entry() -> dict:
    return {
        "run_id": CONFLICT_RUN_ID,
        "exported_at": "2026-11-02T00:00:00+00:00",
        "source": "local",
        "total": 1, "passed": 1, "failed": 0, "retried": 0, "attempts": 1,
        "scenarios": [{"name": "conflict", "passed": True, "attempts": 1,
                       "first_failure": ""}],
    }


def _create_conflicting_round(work: Path, origin: Path, branch: str,
                              history_rel: str, sandbox: Path) -> None:
    """让 origin 先前进一轮 history.json，制造 rebase 冲突（R99）。"""
    entries = history.load_history(work / history_rel)
    # 与 record 的窗口语义一致：满 MAX_ROUNDS 时挤掉最早一轮。否则满窗
    # 失败场景（R105 的组合场景）会把 origin 留在 41 轮——生产里 record
    # 永远不会写出这种历史，夹具自己造出来就会让窗口断言失去意义。
    entries = (entries + [_conflict_entry()])[-history.max_rounds():]
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


def _metrics_content(metrics_path: Path) -> dict | None:
    """读 metrics 的计数指纹；坏了返回 None（record 会给出正式错误）。"""
    try:
        return history.entry_from_metrics(
            json.loads(metrics_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, history.HistoryError):
        return None


# 首次失败文本在指纹行里的上限：CI 日志要能一眼读完，又不至于把整段
# e2e 详情塞进一行。截断只影响展示，不参与任何判决。
SEMANTICS_TEXT_LIMIT = 160


def _metrics_semantics(entry: dict) -> tuple[str, str]:
    """逐场景语义指纹：``name=ok/1``、``name=retry/2``、``name=fail/1``。

    计数指纹只能证明「形状对」，不能证明「内容对」：同样 total=10、
    passed/failed/retried 也相同的两份 metrics，场景名或首次失败可以完全
    不同（R107 的 M110 正是这一类）。全链场景据此断言 artifact 的语义，
    而不是只数总数（R112）。
    """
    states: list[str] = []
    failures: list[str] = []
    for item in entry["scenarios"]:
        if not item["passed"]:
            state = "fail"
        elif item["attempts"] > 1:
            state = "retry"
        else:
            state = "ok"
        states.append(f"{item['name']}={state}/{item['attempts']}")
        text = item.get("first_failure") or ""
        if text:
            if len(text) > SEMANTICS_TEXT_LIMIT:
                text = text[:SEMANTICS_TEXT_LIMIT] + "…"
            failures.append(f"{item['name']}={text}")
    return " ".join(states), "；".join(failures)


def replay(repo: Path, metrics: Path | None, run_id: str,
           history_rel: str = DEFAULT_HISTORY, branch: str = "main",
           keep: bool = False, summary_path: Path | None = None,
           dry_run: bool = False, from_worktree: bool = False,
           fetch_api_url: str | None = None,
           artifact: str = ARTIFACT_NAME, fetch_repo: str = "",
           token: str | None = None, reject_pushes: int = 0,
           conflict: bool = False, conflict_on_reject: int = 0,
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
            _install_rejection_hook(
                origin, reject_pushes, inject_conflict_at=conflict_on_reject,
                branch=branch, history_rel=history_rel)
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
            # R107：把**实际被写回的那份 metrics** 的计数指纹打出来。全链场景
            # 断言它等于 artifact 的形状；若误用本地夹具（形状故意不同），
            # 「已下载 1 个文件」仍在，但这一行会露馅。
            content = _metrics_content(metrics_path)
            if content is not None:
                print(f"replay：metrics 内容 total={content['total']} "
                      f"passed={content['passed']} failed={content['failed']} "
                      f"retried={content['retried']} "
                      f"attempts={content['attempts']}")
                semantics, first_failures = _metrics_semantics(content)
                print(f"replay：metrics 语义 {semantics}")
                if first_failures:
                    print(f"replay：metrics 首次失败 {first_failures}")
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
    parser.add_argument("--conflict-on-reject", nargs="?", const=1, type=int,
                        default=None, metavar="N",
                        help="第 N 次 push 被拒时在 origin 上注入冲突轮"
                             "（默认 1；R112 起可指定）")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="写回的机读结果工件（R99）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.reject_pushes < 0:
        print("--reject-pushes 不能为负", file=sys.stderr)
        return 2
    if args.conflict and args.conflict_on_reject:
        print("--conflict 与 --conflict-on-reject 不能同时使用",
              file=sys.stderr)
        return 2
    if args.conflict_on_reject is not None and args.conflict_on_reject < 1:
        print("--conflict-on-reject 的 N 必须 >= 1", file=sys.stderr)
        return 2
    if args.conflict_on_reject and args.reject_pushes < args.conflict_on_reject:
        # 注入点落在预算之外 = 注入永远不会发生；那会静默退化成普通拒绝，
        # 让人以为「第 N 次注入」被测过（R112）。
        print(f"--conflict-on-reject {args.conflict_on_reject} 需要 "
              f"--reject-pushes >= {args.conflict_on_reject}",
              file=sys.stderr)
        return 2
    return replay(
        repo=args.repo, metrics=args.metrics, run_id=args.run_id,
        history_rel=args.history, branch=args.branch, keep=args.keep,
        summary_path=args.summary, dry_run=args.dry_run,
        from_worktree=args.from_worktree, fetch_api_url=args.fetch_api_url,
        artifact=args.artifact, fetch_repo=args.fetch_repo, token=args.token,
        reject_pushes=args.reject_pushes, conflict=args.conflict,
        conflict_on_reject=args.conflict_on_reject or 0,
        result_path=args.result_json, fetch_run_id=args.fetch_run_id)


if __name__ == "__main__":
    raise SystemExit(main())
