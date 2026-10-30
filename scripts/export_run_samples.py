"""把真实 run 记录裁剪成可入库样本（R47）。

R46 §2.1 的 fixture 是**手工**裁剪出来的，做法只写在交接文档的表格里。这留下
两个问题（R46 §7-1 自己点出过）：fixture 会随 ``build_run_profile`` 的读取字段
演进慢慢过时，而「怎么重新生成」只有人记得。

本脚本把那次手工操作固化成可复现动作：

    python scripts/export_run_samples.py --source data/workflows --dest tests/fixtures/run_samples/LIMITS 2>/dev/null

用法（仓库根执行）::

    # 从本机真实数据导出全部 workflow 的最近 3 次 run
    python scripts/export_run_samples.py

    # 只导指定的 run（可重复 --run）
    python scripts/export_run_samples.py --workflow xs2-novel-flywheel-build \
        --run run-107de93c --run run-58206be9

    # 先看会写什么，不落盘
    python scripts/export_run_samples.py --dry-run

**正确性判据不是「看起来对」，而是画像逐字段相等**：脚本对每个 run 计算
裁剪前后的 ``build_run_profile`` 结果，任一字段不等就拒绝写入并以退出码 1
结束。这样「裁剪漏了影响成败判定的字段」会在导出时当场炸，而不是等到下一轮
有人发现 fixture 过时。

裁剪纪律（与 R46 §2.1 同表）：保留画像读取的字段，删掉内容载荷（小说正文、
迭代轨迹、token 明细）。载荷字段名见 ``_FORBIDDEN_NODE_FIELDS``，导出后会
再扫一遍，命中即失败。

## 半宽预算检查（R53）

``check_live_snapshot_gate.py --check-sample-size`` 要求失败率的 95% 半宽
≤ margin 才算样本够厚，而 CI 里还跑一次 ``--margin 2`` 的**反向验证**：它
期望那一步以退出码 7 结束，证明判据真的能红。这两个要求方向相反——

- 快照越薄，半宽越大，反向验证越容易触发 7；
- 快照越厚，半宽越小，**半宽一旦 ≤ 2，反向验证就不再触发 7**，那一步从
  「能红的判据」退化成恒绿。

R52 重导时踩到过这个耦合（limit 3 的半宽 2.10 已贴门）。当时的补救是「选
一个余量够的 limit 并把它记进文档」，但那要求下一个人也记得算。本脚本在
**导出时**就把这笔账算出来：半宽 ≤ ``REVERSE_VALIDATION_MARGIN`` 时告警，
因为此时该改的是 ``--limit``，而不是去查闸门代码——CI 那时会红在那一步上，
日志却写着「判据失去判定力」，指向的是错误的东西。

``--strict-half-width`` 把这条告警升级为退出码 1，供想把它当硬闸门用的场合。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import WORKFLOWS_DIR  # noqa: E402
from src.workflow.run_profile import build_run_profile  # noqa: E402

# CI 反向验证用的 margin（``ci.yml`` 的 ``--margin 2``）。半宽必须**严格大于**
# 它，收紧到该值的判定才会以退出码 7 结束。两者是这个脚本里唯一的一对耦合
# 常量：改 CI 的 margin 就要改这里，反之亦然。
REVERSE_VALIDATION_MARGIN = 2.0
# 双侧 95% 正态分位数，与 check_live_snapshot_gate.py 同值。
_Z_95 = 1.959963984540054
# 余量低于这个值就提示「偏薄」——还没失效，但一次重导就可能越线。
_THIN_HEADROOM = 0.5
# 快照元数据里保留的导出历史轮数（R58）。闸门的「连续 3 轮样本不足」提示需要
# 3 轮，5 轮留出两轮余量。封顶是为了控制入库体积：每轮只记 attempts/failed，
# 9 个 workflow 约 600 字节，5 轮不到 3KB。
HISTORY_MAX_ROUNDS = 5

# 画像（build_run_profile）真正读的字段。裁剪只保留这些。
_KEEP_RUN_FIELDS = ("run_id", "workflow_id", "status", "started_at", "completed_at")
_KEEP_NODE_FIELDS = (
    "node_id", "status", "started_at", "completed_at", "error",
    "attempt_count", "automatic_retry_count", "output_repair_count",
    "next_attempt_trigger", "rejection_count", "reject_upstream_count",
)
_KEEP_ATTEMPT_FIELDS = (
    "attempt_number", "trigger", "status", "error", "started_at",
    "completed_at", "automatic_retry_count", "output_repair_count",
)

# 这些载荷一旦出现在裁剪结果里就是漏裁——它们是小说正文/轨迹/token 明细。
_FORBIDDEN_NODE_FIELDS = frozenset({
    "summary", "input_snapshot", "iteration_history", "outputs",
    "token_usage_calls", "upstream_summary_snapshot", "output_repair_history",
})


def trim_run(payload: dict) -> dict:
    """保留画像字段，丢弃内容载荷（结构不变，字段减少）。"""
    trimmed = {key: payload[key] for key in _KEEP_RUN_FIELDS if key in payload}
    nodes = []
    for node in payload.get("node_executions") or []:
        if not isinstance(node, dict):
            continue
        kept = {key: node[key] for key in _KEEP_NODE_FIELDS if key in node}
        history = []
        for attempt in node.get("attempt_history") or []:
            if isinstance(attempt, dict):
                history.append(
                    {key: attempt[key] for key in _KEEP_ATTEMPT_FIELDS
                     if key in attempt})
        kept["attempt_history"] = history
        nodes.append(kept)
    trimmed["node_executions"] = nodes
    return trimmed


def half_width_budget(attempts: int, failed: int,
                      margin: float = REVERSE_VALIDATION_MARGIN) -> tuple[bool, str]:
    """CI 反向验证是否还能触发退出码 7。返回 (是否仍有效, 说明)。

    判据不是自己算一遍半宽，而是**直接问闸门**：``sample_size_margin_needed``
    是 ``--check-sample-size`` 判合格时用的那个量，两者必须一致。各写一份
    公式，迟早出现「导出说还有余量、CI 说太薄」的分裂。

    结论是「所需余量 > margin」——**严格大于**。等于 margin 时闸门判合格
    （``needed <= margin``），收紧到 margin 的那一步就不会以 7 退出。

    这里刻意不判「样本够不够厚」（那是 ``--check-sample-size`` 的职责）：
    两个判据方向相反，混在一起会让人看不懂该调大还是调小 limit。本函数只
    回答一个问题：**收紧到 margin 时，这一步还能红吗？**
    """
    from scripts.check_live_snapshot_gate import sample_size_margin_needed

    needed = sample_size_margin_needed(attempts, failed)
    if needed is None:
        return False, "样本量为 0 或形状无效，所需余量无从计算，反向验证无从触发"
    # 两边都是**百分点**：needed 由闸门按百分点给，margin 也按百分点给
    # （CI 里是 2）。不要在这里乘 100。
    headroom = needed - margin
    if headroom <= 0:
        return False, (
            f"所需余量 {needed:.2f} 个百分点 ≤ 反向验证余量 {margin:.1f}："
            f"重导后 --margin {margin:g} 不再触发退出码 7，CI 那一步会退化成恒绿。"
            f"加大 --limit 重导（所需余量需要 > {margin:g}）")
    if headroom < _THIN_HEADROOM:
        return True, (
            f"所需余量 {needed:.2f} 个百分点，距反向验证余量 {margin:.1f} 只剩 "
            f"{headroom:.2f}：仍能触发 7，但一次重导就可能越线")
    return True, (
        f"所需余量 {needed:.2f} 个百分点 > 反向验证余量 {margin:.1f}"
        f"（余量 {headroom:.2f}），CI 反向验证仍有判定力")


def _profile(payload: dict, fallback_run_id: str) -> dict:
    return build_run_profile(
        payload.get("node_executions") or [],
        run_id=str(payload.get("run_id") or fallback_run_id),
        workflow_id=str(payload.get("workflow_id") or ""),
        status=str(payload.get("status", "")),
        started_at=payload.get("started_at"),
        completed_at=payload.get("completed_at"),
    )


def verify_trim_preserves_profile(original: dict, trimmed: dict,
                                  run_id: str) -> list[str]:
    """裁剪前后画像必须逐字段相同；返不相同的字段路径列表（空=通过）。"""
    before = _profile(original, run_id)
    after = _profile(trimmed, run_id)
    problems: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            problems.append(key)
    return problems


def find_forbidden_fields(payload: dict) -> set[str]:
    """裁剪结果里残留的载荷字段（应为空集）。"""
    leaked: set[str] = set()
    for node in payload.get("node_executions") or []:
        if isinstance(node, dict):
            leaked |= _FORBIDDEN_NODE_FIELDS & set(node)
    return leaked


def _iter_source_runs(workflows_dir: Path, workflow_filter: str,
                      run_filter: set[str], limit: int):
    if not workflows_dir.is_dir():
        return
    for wf_dir in sorted(workflows_dir.iterdir()):
        if not wf_dir.is_dir() or (workflow_filter and wf_dir.name != workflow_filter):
            continue
        runs_dir = wf_dir / "runs"
        if not runs_dir.is_dir():
            continue
        files = sorted(runs_dir.glob("run-*.json"), key=lambda p: p.name, reverse=True)
        accepted = 0
        for run_file in files:
            if run_filter and run_file.stem not in run_filter:
                continue
            if accepted >= limit:
                break
            try:
                payload = json.loads(run_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            accepted += 1
            yield wf_dir.name, run_file, payload


def carry_forward_history(dest_root: Path) -> list[dict]:
    """读目的快照已有的导出历史，供本次导出追加（R58）。

    形状无效的条目直接丢弃并计数交给调用方报告——历史是入库文件，可能被手改；
    猜一个形状比丢掉更糟（会让「连续 N 轮」数在一段编造出来的序列上）。
    """
    meta_path = dest_root / "snapshot-meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(meta, dict):
        return []
    history = meta.get("history")
    if not isinstance(history, list):
        return []
    valid: list[dict] = []
    for entry in history:
        if (isinstance(entry, dict)
                and isinstance(entry.get("per_workflow"), dict)
                and entry["per_workflow"]):
            valid.append(entry)
    return valid


def build_snapshot_meta(workflows_dir: Path, dest_root: Path,
                        exported: list[tuple[str, str, dict]],
                        prior_history: list[dict] | None = None) -> dict:
    """快照元数据：记录这次导出判定的数字，供契约测试与新鲜度检查消费。

    ``exported`` 是 ``(workflow, run_id, 裁剪后 payload)``。这里重算一遍聚合，
    而不是把脚本日志抄下来——元数据必须能从内容复算，否则它只是一句话。

    ``history``（R58）：最近 ``HISTORY_MAX_ROUNDS`` 次导出的 ``attempts/failed``，
    旧→新，最后一条就是本次导出。只记原始计数、不记判决：判决依赖 margin，而
    margin 是调用方的参数；记判决会把某一轮的尺子焊进数据，重导后无法用今天的
    尺子回看历史。带上界是因为这是入库文件，不是日志。
    """
    from datetime import datetime, timezone

    per_workflow: dict[str, dict] = {}
    total_attempts = total_failed = 0
    for wf_name, run_id, payload in exported:
        profile = _profile(payload, run_id)
        totals = profile["totals"]
        bucket = per_workflow.setdefault(
            wf_name, {"runs": 0, "attempts": 0, "failed": 0})
        bucket["runs"] += 1
        bucket["attempts"] += totals["attempts"]
        bucket["failed"] += totals["failed"]
        total_attempts += totals["attempts"]
        total_failed += totals["failed"]
    for bucket in per_workflow.values():
        bucket["failure_rate"] = (
            round(bucket["failed"] / bucket["attempts"], 4)
            if bucket["attempts"] else None)
    exported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    history = list(prior_history or [])[-(HISTORY_MAX_ROUNDS - 1):]
    history.append({
        "exported_at": exported_at,
        "per_workflow": {
            name: {"attempts": bucket["attempts"], "failed": bucket["failed"]}
            for name, bucket in sorted(per_workflow.items())
        },
    })
    return {
        "exported_at": exported_at,
        # 只记目录名，不记绝对路径：快照要入库，机器路径既无意义又会泄露本地布局。
        "source_root": workflows_dir.name,
        "per_workflow": dict(sorted(per_workflow.items())),
        "history": history,
        "totals": {
            "runs": len(exported),
            "attempts": total_attempts,
            "failed": total_failed,
            "failure_rate": (round(total_failed / total_attempts, 4)
                             if total_attempts else None),
        },
    }


def export(workflows_dir: Path, dest_root: Path, workflow_filter: str,
           run_filter: set[str], limit: int, dry_run: bool,
           strict_half_width: bool = False) -> int:
    exported_runs: list[tuple[str, str, dict]] = []
    failures: list[str] = []
    for wf_name, run_file, payload in _iter_source_runs(
            workflows_dir, workflow_filter, run_filter, limit):
        trimmed = trim_run(payload)
        run_id = str(payload.get("run_id") or run_file.stem)
        problems = verify_trim_preserves_profile(payload, trimmed, run_id)
        if problems:
            failures.append(f"{wf_name}/{run_file.name}: 画像字段被裁剪改变 {problems}")
            continue
        leaked = find_forbidden_fields(trimmed)
        if leaked:
            failures.append(f"{wf_name}/{run_file.name}: 载荷字段未裁净 {sorted(leaked)}")
            continue

        target = dest_root / "workflows" / wf_name / "runs" / run_file.name
        before_size = run_file.stat().st_size
        text = json.dumps(trimmed, ensure_ascii=False, indent=2) + "\n"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        exported_runs.append((wf_name, run_id, trimmed))
        print(f"{'[dry] ' if dry_run else ''}"
              f"{wf_name}/{run_file.name}: {before_size} → {len(text.encode('utf-8'))} 字节")

    if failures:
        for message in failures:
            print(f"[error] {message}", file=sys.stderr)
        return 1
    if not exported_runs:
        print("没有可导出的 run（检查 --source 与 --workflow/--run 过滤）", file=sys.stderr)
        return 1

    meta = build_snapshot_meta(workflows_dir, dest_root, exported_runs,
                               carry_forward_history(dest_root))
    meta_path = dest_root / "snapshot-meta.json"
    if not dry_run:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    totals = meta["totals"]
    rate = "-" if totals["failure_rate"] is None else f"{totals['failure_rate'] * 100:.2f}%"
    print(f"共导出 {len(exported_runs)} 个 run 到 {dest_root}"
          f"（{totals['attempts']} 次尝试 / {totals['failed']} 失败 / {rate}）")

    # 半宽预算（R53）：这一句要在**落盘之后**打印，因为结论描述的是刚写下去
    # 的那份快照。dry-run 时同样打——它的价值在于「先看会怎样」。
    ok, message = half_width_budget(totals["attempts"], totals["failed"])
    print(f"[half-width] {message}", file=sys.stderr if not ok else sys.stdout)
    if not ok and strict_half_width:
        print("[half-width] --strict-half-width 生效：按不合格退出", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=WORKFLOWS_DIR,
                        help="真实 run 记录根目录（默认 src.config.WORKFLOWS_DIR）")
    parser.add_argument("--dest", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "tests" / "fixtures" / "run_samples",
                        help="导出目标根目录（应含 workflows/ 结构）")
    parser.add_argument("--workflow", default="", help="只导指定 workflow id")
    parser.add_argument("--run", action="append", default=[],
                        help="只导指定 run_id（可重复）")
    parser.add_argument("--limit", type=int, default=3,
                        help="每个 workflow 最多导 N 个 run（默认 3）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印将写入的内容，不落盘")
    parser.add_argument("--strict-half-width", action="store_true",
                        help="半宽不足以支撑 CI 反向验证时按退出码 1 结束"
                             "（默认只告警）")
    options = parser.parse_args()
    return export(options.source, options.dest, options.workflow,
                  set(options.run), options.limit, options.dry_run,
                  options.strict_half_width)


if __name__ == "__main__":
    raise SystemExit(main())
