"""供应商失败率画像挖矿（R38 §7.4 落地，R40）：扫描历史 run 记录产出每阶段失败率。

只读工具：遍历 data/workflows/<wf>/runs/run-*.json，用 run_profile.build_run_profile
聚合逐 run 画像，并给出跨 run 的按阶段汇总（供应商压测参考基线）。

用法（仓库根执行）：
    python scripts/provider_failure_profile.py                     # 全部 workflow 最近各 3 次 run
    python scripts/provider_failure_profile.py --workflow xs2-novel-flywheel-build
    python scripts/provider_failure_profile.py --limit 10 --json   # 机器可读输出
    python scripts/provider_failure_profile.py --summary           # 每 workflow 一行，供交接时间序列
    python scripts/provider_failure_profile.py --fail-if-above 5   # 总失败率 > 5% 时非零退出

轮次收官固定动作（R41 起）：每轮收官跑一次 ``--summary``，把输出行贴进交接
文档的「供应商失败率时间序列」表——同一口径逐轮累积即为时间序列。脚本自身
严格只读（不写任何文件），「每轮固定跑」的记录责任在交接文档，不在脚本。

告警闸门（R42）：``--fail-if-above PCT`` 把「人工比对」升级为可挂 CI 的硬闸门。
判据是**总失败率**（全部入选 run 的 failed/attempts），严格大于阈值才失败；
verdict 写 stderr，stdout 的表格/JSON 保持机器可读不变。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import WORKFLOWS_DIR  # noqa: E402
from src.workflow.run_profile import build_run_profile  # noqa: E402


def _iter_run_files_in(workflows_dir: Path, workflow_filter: str, limit: int):
    """按目录扫描 run 文件（抽出来供 collect_profiles 测试注入临时目录）。

    ``limit`` 按**成功解析的 run 数**计——坏 JSON 与读失败不占配额，
    否则一条损坏记录会让「最近 N 次 run」的采样面静默缩小。
    """
    if not workflows_dir.is_dir():
        return
    for wf_dir in sorted(workflows_dir.iterdir()):
        if not wf_dir.is_dir() or (workflow_filter and wf_dir.name != workflow_filter):
            continue
        runs_dir = wf_dir / "runs"
        if not runs_dir.is_dir():
            continue
        files = sorted(runs_dir.glob("run-*.json"), key=lambda p: p.name,
                       reverse=True)
        accepted = 0
        for run_file in files:
            if accepted >= limit:
                break
            try:
                run = json.loads(run_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            accepted += 1
            yield wf_dir.name, run_file, run


def _iter_run_files(workflow_filter: str, limit: int):
    yield from _iter_run_files_in(WORKFLOWS_DIR, workflow_filter, limit)


def _aggregate(workflow: str, profiles: list[dict]) -> dict:
    """同 workflow 多次 run 的按阶段汇总：每阶段尝试/完成/失败的总量与比率。"""
    per_stage: dict[str, dict] = {}
    for profile in profiles:
        for stage in profile["stages"]:
            bucket = per_stage.setdefault(stage["node_id"], {
                "runs": 0, "attempts": 0, "completed": 0, "failed": 0,
                "error_classes": {}})
            bucket["runs"] += 1
            bucket["attempts"] += stage["attempts"]
            bucket["completed"] += stage["completed"]
            bucket["failed"] += stage["failed"]
            for name, count in stage["error_classes"].items():
                bucket["error_classes"][name] = \
                    bucket["error_classes"].get(name, 0) + count
    stages = []
    for node_id, b in per_stage.items():
        stages.append({
            "node_id": node_id, **b,
            "failure_rate": round(b["failed"] / b["attempts"], 4)
                            if b["attempts"] else None,
        })
    stages.sort(key=lambda s: (-s["failed"], s["node_id"]))
    return {"workflow": workflow, "runs": len(profiles), "stages": stages}


def collect_profiles(workflows_dir: Path, workflow_filter: str = "",
                     limit: int = 3) -> dict[str, list[dict]]:
    """扫描 run 记录 → {workflow: [run 画像]}（纯读取，不写任何文件）。"""
    by_workflow: dict[str, list[dict]] = {}
    for wf_name, run_file, run in _iter_run_files_in(
            workflows_dir, workflow_filter, limit):
        profile = build_run_profile(
            run.get("node_executions", []),
            run_id=str(run.get("run_id") or run_file.stem),
            workflow_id=wf_name,
            status=str(run.get("status", "")),
            started_at=run.get("started_at"),
            completed_at=run.get("completed_at"),
        )
        by_workflow.setdefault(wf_name, []).append(profile)
    return by_workflow


def summarize(by_workflow: dict[str, list[dict]]) -> list[dict]:
    """每 workflow 一行的紧凑汇总（R41 时间序列口径）。

    只输出可逐轮比对的关键量：run 数、总尝试、总失败、总失败率、
    失败阶段与错误分类合计。
    """
    rows = []
    for wf, profiles in sorted(by_workflow.items()):
        attempts = sum(p["totals"]["attempts"] for p in profiles)
        failed = sum(p["totals"]["failed"] for p in profiles)
        error_classes: dict[str, int] = {}
        failing_stages: set[str] = set()
        for p in profiles:
            for name, count in p["totals"]["error_classes"].items():
                error_classes[name] = error_classes.get(name, 0) + count
            failing_stages.update(p["totals"]["stages_with_failures"])
        rows.append({
            "workflow": wf,
            "runs": len(profiles),
            "attempts": attempts,
            "failed": failed,
            "failure_rate": round(failed / attempts, 4) if attempts else None,
            "failing_stages": sorted(failing_stages),
            "error_classes": error_classes,
        })
    return rows


def evaluate_gate(rows: list[dict], threshold_pct: float) -> dict:
    """告警闸门判定（纯函数，供测试与 main 共用）。

    判据是**总失败率**：所有入选 run 的 failed 之和 / attempts 之和，与
    ``--summary`` 的 TOTAL 行同一口径（逐 workflow 平均会让小样本 workflow
    与大数据集等权，失真）。严格大于阈值才触发——阈值 5.0 表示「5.0% 通过」。

    比较用**未舍入**的比值：先 ``round(..., 4)`` 再比较会让 1/3（33.3333%）
    这类边界值被舍成 33.33% 而与阈值 33.33 判平，与真实比率不符。舍入只用于
    展示字段 ``failure_rate``。

    无任何尝试时 ``failure_rate`` 为 None：没有样本就没有可判定的失败率，
    诚实放行（``triggered=False``），而不是把「无数据」当成 0% 或 100%。
    """
    attempts = sum(r["attempts"] for r in rows)
    failed = sum(r["failed"] for r in rows)
    exact = failed / attempts if attempts else None
    triggered = exact is not None and exact * 100 > threshold_pct
    return {
        "threshold_pct": threshold_pct,
        "attempts": attempts,
        "failed": failed,
        "failure_rate": round(exact, 4) if exact is not None else None,
        "triggered": triggered,
        "reason": _gate_reason(exact, threshold_pct, attempts),
    }


def _gate_reason(rate: float | None, threshold_pct: float,
                 attempts: int) -> str:
    if rate is None:
        return f"无 run 样本（attempts=0），跳过失败率闸门（阈值 {threshold_pct}%）"
    pct = f"{rate * 100:.2f}%"
    verdict = "超出" if rate * 100 > threshold_pct else "未超出"
    return (f"总失败率 {pct} {verdict}阈值 {threshold_pct}%"
            f"（{attempts} 次尝试）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default="", help="只看指定 workflow id")
    parser.add_argument("--limit", type=int, default=3,
                        help="每个 workflow 取最近 N 次 run（默认 3）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--summary", action="store_true",
                        help="每 workflow 一行的紧凑汇总（轮次收官用）")
    parser.add_argument("--fail-if-above", type=float, default=None,
                        metavar="PCT",
                        help="总失败率严格大于 PCT 时以退出码 1 结束（CI 硬闸门）")
    args = parser.parse_args()
    if args.fail_if_above is not None and not 0 <= args.fail_if_above <= 100:
        parser.error("--fail-if-above 需在 0..100 之间（单位是百分比）")

    by_workflow = collect_profiles(WORKFLOWS_DIR, args.workflow, args.limit)
    rows = summarize(by_workflow)

    exit_code = 0
    if args.fail_if_above is not None:
        verdict = evaluate_gate(rows, args.fail_if_above)
        # 闸门结论写 stderr：stdout 的表格/JSON 是机器可读出口，不能被结论行污染。
        print(f"[gate] {verdict['reason']}", file=sys.stderr)
        if verdict["triggered"]:
            exit_code = 1

    if args.summary:
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return exit_code
        if not rows:
            print("未找到 run 记录（检查 --workflow 过滤与 data/workflows 布局）")
            return exit_code
        for row in rows:
            rate = "-" if row["failure_rate"] is None else f"{row['failure_rate'] * 100:.1f}%"
            print(f"{row['workflow']}: runs={row['runs']} attempts={row['attempts']}"
                  f" failed={row['failed']} failure_rate={rate}"
                  f" failing_stages={','.join(row['failing_stages']) or '-'}"
                  f" error_classes={json.dumps(row['error_classes'], ensure_ascii=False)}")
        total_attempts = sum(r["attempts"] for r in rows)
        total_failed = sum(r["failed"] for r in rows)
        overall = (f"{total_failed / total_attempts * 100:.1f}%"
                   if total_attempts else "-")
        print(f"TOTAL: runs={sum(r['runs'] for r in rows)} attempts={total_attempts}"
              f" failed={total_failed} failure_rate={overall}")
        return exit_code

    if args.json:
        print(json.dumps({
            wf: {"runs": profiles,
                 "aggregate": _aggregate(wf, profiles)}
            for wf, profiles in by_workflow.items()},
            ensure_ascii=False, indent=2))
        return exit_code

    for wf, profiles in by_workflow.items():
        print(f"\n=== {wf}（最近 {len(profiles)} 次 run）===")
        for p in profiles:
            t = p["totals"]
            print(f"  run {p['run_id']} [{p['status']}] "
                  f"阶段 {t['stages']} / 尝试 {t['attempts']} / 失败 {t['failed']}"
                  f"（失败率 {t['failure_rate']}）"
                  f" 多次尝试阶段: {t['stages_with_multiple_attempts'] or '无'}"
                  f" 失败阶段: {t['stages_with_failures'] or '无'}"
                  f" 错误分类: {t['error_classes'] or '无'}")
            for s in p["stages"]:
                if s["attempts"] > 1 or s["failed"]:
                    print(f"    - {s['node_id']}: 尝试 {s['attempts']}"
                          f"（成 {s['completed']} / 败 {s['failed']}）"
                          f" 分类 {s['error_classes'] or '-'}"
                          f" 时长 {s['duration_seconds']}s")
        agg = _aggregate(wf, profiles)
        print(f"  -- 跨 run 汇总（{agg['runs']} runs）--")
        for s in agg["stages"]:
            print(f"    {s['node_id']}: 尝试 {s['attempts']} / 失败 {s['failed']}"
                  f"（失败率 {s['failure_rate']}）")
    if not by_workflow:
        print("未找到 run 记录（检查 --workflow 过滤与 data/workflows 布局）")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
