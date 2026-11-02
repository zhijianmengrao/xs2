"""R101：在 CI 里回放写回的三条路径（happy / 被拒一次 / 冲突）。

R99 已经把「在沙箱 origin 上真实制造 push 拒绝与 rebase 冲突」做成可执行
能力，但那些场景此前只由 ``tests/test_replay_ci_writeback.py`` 在 backend
job 里以 pytest 驱动。pytest 能证明函数行为，**证明不了**「生产 CI 的
checkout、git、shell 钩子、历史文件上，这套回放真的能跑完」。本脚本就是那
个生产 job 的驱动：它对 ``scripts/replay_ci_writeback.py`` 的 ``main()``
逐个跑场景，断言退出码、``reason``、``rounds``、``push_attempts`` 与关键
输出，再把机读结果交给 step summary / artifact。

## 判什么、不判什么

判：回放的**可执行性与链路语义**——写回成功、被拒一次后重试成功、冲突后
丢弃本地提交并按最新分支重算。每个场景都从 ``--repo`` 的 HEAD 克隆出独立
沙箱，源仓库一个字节都不该动。

不判：模型质量、e2e 场景通过率、真实 origin 的推送（写回只推沙箱 origin），
以及永久拒绝（三次全拒）——那条路径按设计保留失败沙箱，pytest 已在两个
平台覆盖，生产 job 不制造需要人工清理的现场。

## 退出码

- 0：三个场景全部符合预期
- 1：至少一个场景的观测与预期不符（真回归；输出里有逐项 expected/actual）
- 2：用法错误（argparse）
- 3：基线不可用——``--repo`` 不是 git 仓库、history 缺失/读不懂。**不是**
  回放语义失败，排查方向是 checkout/git/数据，别把它当 1。

## 为什么不是 pytest

R100 §5 的边界原话是「replay 仍不进 CI；拒绝/冲突场景由 pytest 在 backend
job 里驱动，不是生产 job」。把同样的断言塞回 pytest 只是换了个执行者，
``.github/workflows/ci.yml`` 里的 ``replay-ci-writeback`` job 仍然没有生产
调用者。这里把断言放在独立脚本里，CI 只负责调用与透传退出码（R89 的同一
原则：能本地跑的逻辑不写在 YAML 里）。

用法::

    python scripts/replay_ci_scenarios.py --repo . --branch main
    python scripts/replay_ci_scenarios.py --repo . \\
        --result-json "$RUNNER_TEMP/replay-ci-result.json" \\
        --summary "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_reporting
from scripts import e2e_retry_history as history
from scripts import replay_ci_writeback as replay

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2
EXIT_ENV = 3

RESULT_SCHEMA = 1
DEFAULT_HISTORY = "tests/fixtures/e2e_retry_history/history.json"

# 每个场景的捕获输出写进 result JSON 时截断：失败现场足够诊断，又不至于让
# artifact 里塞进整份 git 输出。
OUTPUT_LIMIT = 8000


@dataclass(frozen=True)
class Scenario:
    """一个回放场景的预期观测。

    ``rounds_delta`` / ``push_attempts`` 来自 R99 的真实行为，不是拍脑袋：
    - happy：一次 push 成功，rounds +1，push_attempts=1；
    - rejected：第 1 次被拒、第 2 次成功，rounds +1，push_attempts=2；
    - conflict：origin 上预置一轮冲突历史 + 本轮，rounds +2；写回同样经历
      被拒→rebase 冲突→按最新分支重算→第 2 次 push，push_attempts=2。
    """

    name: str
    rounds_delta: int
    push_attempts: int
    reject_pushes: int = 0
    conflict: bool = False
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "happy", 1, 1,
        must_contain=("已写回",),
        # 证明这一场景真的没有拒绝；否则「被拒一次」与它无法区分。
        must_not_contain=("push 被拒（第",),
    ),
    Scenario(
        "rejected", 1, 2, reject_pushes=1,
        must_contain=("push 被拒（第 1 次）", "第 2 次尝试"),
    ),
    Scenario(
        "conflict", 2, 2, conflict=True,
        must_contain=("rebase 冲突（第 1 次）", "第 2 次尝试"),
    ),
)


class BaselineError(RuntimeError):
    """无法建立回放基线（repo/git/history）；对应退出码 3。"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True)


def _git_text(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", "replace").strip()
        raise BaselineError(f"git {' '.join(args)} 失败：{detail}")
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _metrics(path: Path) -> Path:
    """与 e2e 相同的 10 场景形状；``record`` 只校验形状，不跑模型。"""
    scenarios = [
        {"name": f"scenario_{index}", "passed": True, "attempts": 1,
         "first_failure": ""}
        for index in range(10)
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 10, "passed": 10, "failed": 0, "retried": 0,
        "scenarios": scenarios}), encoding="utf-8")
    return path


def _baseline(repo: Path, history_rel: str) -> dict:
    """读源仓库的 HEAD、历史轮数与历史字节（用于前后对比）。"""
    if not repo.is_dir():
        raise BaselineError(f"仓库目录不存在：{repo}")
    _git_text(repo, "rev-parse", "--show-toplevel")
    head = _git_text(repo, "rev-parse", "HEAD")
    history_path = repo / history_rel
    try:
        entries = history.load_history(history_path)
    except history.HistoryError as exc:
        raise BaselineError(str(exc)) from exc
    return {
        "head": head,
        "history_path": history_path,
        "history_bytes": history_path.read_bytes(),
        "rounds": len(entries),
    }


def _read_result(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_scenario(scenario: Scenario, repo: Path, branch: str,
                  history_rel: str, before: int, workdir: Path) -> dict:
    """跑一个场景并返回逐项观测；不抛异常，失败写进返回值。"""
    head = _git_text(repo, "rev-parse", "HEAD")
    source_history = repo / history_rel
    history_before = source_history.read_bytes()

    metrics = _metrics(workdir / f"{scenario.name}-metrics.json")
    result_path = workdir / f"{scenario.name}-result.json"
    # run_id 带 HEAD 短 SHA：同一 commit 重跑时稳定，换 commit 自动换键；
    # replay 的 record 对同键是覆盖，不会把一次回放记成两轮。
    run_id = f"replay-ci-{scenario.name}-{head[:8]}"
    argv = [
        "--repo", str(repo),
        "--metrics", str(metrics),
        "--run-id", run_id,
        "--history", history_rel,
        "--branch", branch,
        "--result-json", str(result_path),
    ]
    if scenario.reject_pushes:
        argv += ["--reject-pushes", str(scenario.reject_pushes)]
    if scenario.conflict:
        argv.append("--conflict")

    stdout, stderr = io.StringIO(), io.StringIO()
    code = EXIT_MISMATCH
    try:
        with contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = replay.main(argv)
    except SystemExit as exc:  # argparse 的用法错误
        code = exc.code if isinstance(exc.code, int) else EXIT_MISMATCH
    except Exception as exc:  # noqa: BLE001 - 生产驱动不能因异常丢诊断
        print(f"replay 抛异常：{type(exc).__name__}: {exc}")

    output = stdout.getvalue() + stderr.getvalue()
    result = _read_result(result_path)
    expected_rounds = min(before + scenario.rounds_delta, history.MAX_ROUNDS)
    expected = {
        "exit_code": EXIT_OK,
        "reason": "written",
        "rounds": expected_rounds,
        "push_attempts": scenario.push_attempts,
    }
    actual = {
        "exit_code": code,
        "reason": result.get("reason") if result else None,
        "rounds": result.get("rounds") if result else None,
        "push_attempts": result.get("push_attempts") if result else None,
    }

    problems: list[str] = []
    if code != EXIT_OK:
        problems.append(f"退出码 {code}，期望 0")
    if result is None:
        problems.append("没有写出 --result-json")
    else:
        if result.get("exit_code") != code:
            problems.append(
                f"result.exit_code={result.get('exit_code')!r} 与进程退出码 "
                f"{code} 不一致")
        if result.get("reason") != "written":
            problems.append(
                f"reason={result.get('reason')!r}，期望 'written'")
        if result.get("rounds") != expected_rounds:
            problems.append(
                f"rounds={result.get('rounds')!r}，期望 {expected_rounds}")
        if result.get("push_attempts") != scenario.push_attempts:
            problems.append(
                f"push_attempts={result.get('push_attempts')!r}，"
                f"期望 {scenario.push_attempts}")
    for token in scenario.must_contain:
        if token not in output:
            problems.append(f"输出缺少 {token!r}")
    for token in scenario.must_not_contain:
        if token in output:
            problems.append(f"输出不应包含 {token!r}")

    # 源仓库只读：HEAD 与 history 字节都必须与调用前一致。放在场景内部检查，
    # 失败时能指出是哪个场景越界，而不是只在最后报一句“变了”。
    source_head_after = _git_text(repo, "rev-parse", "HEAD")
    source_mutated = (
        source_head_after != head
        or source_history.read_bytes() != history_before
    )
    if source_mutated:
        problems.insert(0, "源仓库被改动（HEAD 或 history 字节变化）")

    return {
        "name": scenario.name,
        "ok": not problems,
        "exit_code": code,
        "expected": expected,
        "actual": actual,
        "failure": "；".join(problems),
        "source_mutated": source_mutated,
        "output": output[-OUTPUT_LIMIT:],
    }


def run(repo: Path, branch: str, history_rel: str,
        result_path: Path | None = None,
        summary_path: Path | None = None) -> int:
    try:
        baseline = _baseline(repo, history_rel)
    except BaselineError as exc:
        print(f"replay-ci 基线不可用：{exc}", file=sys.stderr)
        ci_reporting.emit_result(result_path, {
            "schema": RESULT_SCHEMA,
            "repo": str(repo),
            "branch": branch,
            "history": history_rel,
            "ok": False,
            "reason": "baseline-unavailable",
            "detail": str(exc),
            "scenarios": [],
        })
        return EXIT_ENV

    print(
        f"replay-ci：源仓库 {repo} HEAD {baseline['head'][:8]}，"
        f"历史 {baseline['rounds']}/{history.MAX_ROUNDS} 轮",
        flush=True)

    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="replay-ci-scenarios-") as tmp:
        workdir = Path(tmp)
        for scenario in SCENARIOS:
            record = _run_scenario(
                scenario, repo, branch, history_rel, baseline["rounds"],
                workdir)
            records.append(record)
            mark = "PASS" if record["ok"] else "FAIL"
            print(
                f"[replay-ci] {mark} {scenario.name}: "
                f"exit={record['exit_code']} "
                f"rounds={record['actual'].get('rounds')} "
                f"push_attempts={record['actual'].get('push_attempts')}",
                flush=True)
            if record["failure"]:
                print(f"[replay-ci]   {record['failure']}", flush=True)
                print(record["output"], flush=True)
            if record["source_mutated"]:
                # 源仓库已不可信，继续跑后面的场景只会把基线污染扩散。
                print("[replay-ci] 源仓库被改动，停止后续场景", file=sys.stderr)
                break

    # 场景没跑完（中途因源仓库被改动而停止）同样算失败：不能因为剩下的
    # 没跑就报通过。
    ok = len(records) == len(SCENARIOS) and all(
        record["ok"] for record in records)
    ci_reporting.emit_result(result_path, {
        "schema": RESULT_SCHEMA,
        "repo": str(repo),
        "branch": branch,
        "history": history_rel,
        "before": baseline["rounds"],
        "source_head": baseline["head"],
        "ok": ok,
        "scenarios": records,
    })
    for record in records:
        reason = "ok" if record["ok"] else "mismatch"
        detail = record["failure"] or (
            f"rounds={record['actual'].get('rounds')} "
            f"push_attempts={record['actual'].get('push_attempts')}")
        ci_reporting.emit_summary(
            summary_path, f"replay-ci-{record['name']}", reason, detail)

    passed = sum(1 for record in records if record["ok"])
    print(f"replay-ci：{passed}/{len(SCENARIOS)} 场景通过", flush=True)
    return EXIT_OK if ok else EXIT_MISMATCH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="源仓库（只读；replay 会克隆到临时沙箱）")
    parser.add_argument("--branch", default="main",
                        help="回放的分支（CI 会先 checkout -B main）")
    parser.add_argument("--history", default=DEFAULT_HISTORY,
                        help="仓库内的历史文件相对路径")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件（可选）")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="机读结果工件（可选）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.repo, args.branch, args.history,
               args.result_json, args.summary)


if __name__ == "__main__":
    raise SystemExit(main())
