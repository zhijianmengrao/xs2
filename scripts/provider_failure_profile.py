"""供应商失败率画像挖矿（R38 §7.4 落地，R40）：扫描历史 run 记录产出每阶段失败率。

只读工具：遍历 data/workflows/<wf>/runs/run-*.json，用 run_profile.build_run_profile
聚合逐 run 画像，并给出跨 run 的按阶段汇总（供应商压测参考基线）。

用法（仓库根执行）：
    python scripts/provider_failure_profile.py                     # 全部 workflow 最近各 3 次 run
    python scripts/provider_failure_profile.py --workflow xs2-novel-flywheel-build
    python scripts/provider_failure_profile.py --limit 10 --json   # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import WORKFLOWS_DIR  # noqa: E402
from src.workflow.run_profile import build_run_profile  # noqa: E402


def _iter_run_files(workflow_filter: str, limit: int):
    for wf_dir in sorted(WORKFLOWS_DIR.iterdir()):
        if not wf_dir.is_dir() or (workflow_filter and wf_dir.name != workflow_filter):
            continue
        runs_dir = wf_dir / "runs"
        if not runs_dir.is_dir():
            continue
        files = sorted(runs_dir.glob("run-*.json"), key=lambda p: p.name,
                       reverse=True)[:limit]
        for run_file in files:
            try:
                yield wf_dir.name, run_file, json.loads(
                    run_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default="", help="只看指定 workflow id")
    parser.add_argument("--limit", type=int, default=3,
                        help="每个 workflow 取最近 N 次 run（默认 3）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    by_workflow: dict[str, list[dict]] = {}
    for wf_name, run_file, run in _iter_run_files(args.workflow, args.limit):
        profile = build_run_profile(
            run.get("node_executions", []),
            run_id=str(run.get("run_id") or run_file.stem),
            workflow_id=wf_name,
            status=str(run.get("status", "")),
            started_at=run.get("started_at"),
            completed_at=run.get("completed_at"),
        )
        by_workflow.setdefault(wf_name, []).append(profile)

    if args.json:
        print(json.dumps({
            wf: {"runs": profiles,
                 "aggregate": _aggregate(wf, profiles)}
            for wf, profiles in by_workflow.items()},
            ensure_ascii=False, indent=2))
        return 0

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
