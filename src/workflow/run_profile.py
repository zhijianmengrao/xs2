"""供应商失败率画像（R38 §7.4 落地，R40；R43 加跨 run 对比）：每阶段尝试/失败聚合。

run 记录的 node_executions 每个节点自带 attempt_history（逐尝试
trigger/status/error/时间戳），但只散落在 run JSON 里——R38 全流程实跑的
重试画像（build 2 次 / character 3 次）是人工翻文件得出的。本模块把「每阶段
失败率而非只看总耗时」的聚合收敛为纯函数，供三处消费：

- ``scripts/provider_failure_profile.py``：历史 run 挖矿（离线，只读）
- ``workflow_routes`` 的任务 run-profile 端点（在线，任务最新一次运行，
  R41 起 ``?run_id=`` 可查任意历史 run）
- 单测（合成 run 数据，含旧版无 attempt_history 的兼容路径）

错误分类是关键词启发式（timeout / http_5xx / connection / stream_stall /
other），仅供压测参考，不构成失败原因判定；旧数据缺 attempt_history 时
attempt 数回退 attempt_count、成败以节点终态近似。

跨 run 对比（R43）：``compare_run_profiles`` 把「本次 run」与「上一次 run」
的同名阶段并排算出失败率/尝试数差值，供前端抽屉的对比列消费。比较口径与
``scripts/provider_failure_profile.py`` 的 TOTAL 口径一致——差值用未舍入
比值算，展示字段才舍入；任一侧无尝试时该阶段标 ``comparable=False``，不
把「无数据」当成 0%。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# 供应商侧已实测的失败形态（R38 §2.0）：流式停摆表现为 120s/600s 超时打穿、
# 免费档 530/524/502。分类按错误文本关键词，宽松命中。
#
# **顺序即判据**（R47）：同一条真实错误文本常同时含多个桶的关键词，谁先匹配
# 就决定它进哪个桶。R46 §5-2 的实例是 `peer closed connection without sending
# complete message body (incomplete chunked read)`——它既有 connection 也有
# chunk，旧的「stream_stall 在前」把它判成了流式停摆，掩盖了真实的连接层故障。
# 因此改成「强信号优先、宽匹配兜底」两层：
#   1. http_5xx          数字状态码，最无歧义
#   2. connection（强）   peer closed / connection reset|refused|aborted / 连接被重置
#   3. stream_stall（强） no streaming chunk / stream_chunk_timeout / 流式停摆
#   4. timeout           显式超时措辞（供应商原文常写 timed out）
#   5. stream_stall（宽） 仅出现 stream/chunk 字样、没有更强信号
#   6. connection（宽）   仅出现 connection/连接 字样
# 强信号层之所以必须存在：LangChain 的停摆原文里带一句 "The connection may be
# alive at the TCP layer"，若 connection 的宽匹配排在前面，所有流式停摆都会被
# 误判成连接错误——两层结构同时让「真连接故障」和「真流式停摆」各归其位。
_ERROR_CLASS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("http_5xx", re.compile(r"\b(?:500|502|503|504|524|529|530)\b|http 5\d\d", re.IGNORECASE)),
    ("connection", re.compile(
        r"peer closed|connection (?:reset|refused|aborted|closed)"
        r"|incomplete chunked read|连接被?(?:重置|拒绝|中断|断开)", re.IGNORECASE)),
    ("stream_stall", re.compile(
        r"no streaming chunk|stream_chunk_timeout|流式停摆|停摆", re.IGNORECASE)),
    ("timeout", re.compile(r"timed? ?out|timeout|超时", re.IGNORECASE)),
    ("stream_stall", re.compile(r"stream|chunk|流式", re.IGNORECASE)),
    ("connection", re.compile(r"connection|refused|reset|unreachable|连接", re.IGNORECASE)),
]

_COMPLETED = "completed"


def classify_error(error: str) -> str:
    """错误文本 → 粗分类；空文本返回空串（未失败或无信息）。"""
    text = (error or "").strip()
    if not text:
        return ""
    for name, pattern in _ERROR_CLASS_PATTERNS:
        if pattern.search(text):
            return name
    return "other"


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_seconds(start: object, end: object) -> float | None:
    a, b = _parse_iso(start), _parse_iso(end)
    if a is None or b is None or b < a:
        return None
    return round((b - a).total_seconds(), 3)


def _node_profile(entry: dict[str, Any]) -> dict[str, Any]:
    """单节点画像。entry 是 NodeExecutionState 的序列化字典（容忍缺键）。"""
    history = entry.get("attempt_history")
    attempts_detail: list[dict[str, Any]] = []
    if isinstance(history, list) and history:
        for item in history:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", ""))
            error = str(item.get("error", "") or "")
            attempts_detail.append({
                "attempt_number": item.get("attempt_number"),
                "trigger": item.get("trigger", ""),
                # R50：循环轮次（0 = 非循环节点）。旧记录没有这个键，
                # 回落到 0——与「非循环」同一表示，不伪造轮次。
                "loop_iteration": int(item.get("loop_iteration", 0) or 0),
                "status": status,
                "error": error,
                "error_class": classify_error(error),
                "duration_seconds": _duration_seconds(
                    item.get("started_at"), item.get("completed_at")),
            })
    else:
        # 旧数据兼容：无逐尝试历史时以 attempt_count 计数、终态近似成败
        # （detail 只合成终态一条，attempts 计数与 detail 长度解耦）。
        total = int(entry.get("attempt_count", 0) or 0)
        attempts_detail = [{
            "attempt_number": total or None,
            "trigger": entry.get("next_attempt_trigger", ""),
            "status": str(entry.get("status", "")),
            "error": str(entry.get("error", "") or ""),
            "error_class": classify_error(str(entry.get("error", "") or "")),
            "duration_seconds": None,
        }] if total else []

    attempts_total = max(int(entry.get("attempt_count", 0) or 0),
                         len(attempts_detail))
    completed = sum(1 for a in attempts_detail if a["status"] == _COMPLETED)
    failed = attempts_total - completed
    error_classes: dict[str, int] = {}
    for a in attempts_detail:
        cls = a["error_class"]
        if cls:
            error_classes[cls] = error_classes.get(cls, 0) + 1

    return {
        "node_id": entry.get("node_id", ""),
        "attempts": attempts_total,
        "completed": completed,
        "failed": failed,
        "failure_rate": round(failed / attempts_total, 4) if attempts_total else None,
        "automatic_retry_count": entry.get("automatic_retry_count", 0),
        "output_repair_count": entry.get("output_repair_count", 0),
        "first_started_at": entry.get("started_at"),
        "duration_seconds": _duration_seconds(
            entry.get("started_at"), entry.get("completed_at")),
        "error_classes": error_classes,
        "attempts_detail": attempts_detail,
    }


def build_run_profile(
    node_executions: list[dict[str, Any]],
    *,
    run_id: str = "",
    workflow_id: str = "",
    status: str = "",
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """把一次运行的 node_executions 聚合为每阶段尝试/失败画像。

    纯函数：只读入参字典，不触文件系统、不建目录。
    """
    stages = [_node_profile(entry) for entry in node_executions
              if isinstance(entry, dict)]
    attempts_total = sum(s["attempts"] for s in stages)
    completed_total = sum(s["completed"] for s in stages)
    failed_total = attempts_total - completed_total
    error_classes: dict[str, int] = {}
    for s in stages:
        for name, count in s["error_classes"].items():
            error_classes[name] = error_classes.get(name, 0) + count
    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "wall_seconds": _duration_seconds(started_at, completed_at),
        "totals": {
            "stages": len(stages),
            "attempts": attempts_total,
            "completed": completed_total,
            "failed": failed_total,
            "failure_rate": round(failed_total / attempts_total, 4)
                            if attempts_total else None,
            "stages_with_multiple_attempts": [s["node_id"] for s in stages
                                              if s["attempts"] > 1],
            "stages_with_failures": [s["node_id"] for s in stages
                                     if s["failed"] > 0],
            "error_classes": error_classes,
        },
        "stages": stages,
    }


def _order_key(started_at: object, mtime: float) -> float:
    """run 的排序键：优先用 started_at，缺/坏则回落文件 mtime（同为绝对时刻）。

    统一取 ``timestamp()`` 浮点，避免 aware 与 naive datetime 直接比较抛
    TypeError——本仓 run 记录两种都出现过（B31 前 completed_at 恒 null）。
    """
    parsed = _parse_iso(started_at)
    if parsed is None:
        return float(mtime)
    try:
        return parsed.timestamp()
    except (OSError, OverflowError, ValueError):
        return float(mtime)


def pick_previous_run(current: dict[str, Any],
                      candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从候选 run 元数据里挑出「上一次 run」（纯函数，供端点与测试共用）。

    ``current`` 与 ``candidates`` 都是 ``{run_id, started_at, mtime}``。
    「上一次」定义为排序键严格小于当前 run 的那个最大者——没有更早的 run 时
    返回 None（诚实表示无对比对象，不拿更晚的 run 冒充）。
    """
    current_key = _order_key(current.get("started_at"), current.get("mtime", 0.0))
    older = [
        c for c in candidates
        if c.get("run_id") != current.get("run_id")
        and _order_key(c.get("started_at"), c.get("mtime", 0.0)) < current_key
    ]
    if not older:
        return None
    return max(older, key=lambda c: (_order_key(c.get("started_at"),
                                               c.get("mtime", 0.0)),
                                     str(c.get("run_id", ""))))


def _pool_by_node(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """按 node_id 汇总一次 run 的全部执行（同 node 可在一 run 内跑多次）。"""
    pooled: dict[str, dict[str, Any]] = {}
    for stage in profile.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        node_id = str(stage.get("node_id", ""))
        bucket = pooled.setdefault(node_id, {
            "occurrences": 0, "attempts": 0, "completed": 0, "failed": 0})
        bucket["occurrences"] += 1
        for field in ("attempts", "completed", "failed"):
            bucket[field] += int(stage.get(field, 0) or 0)
    return pooled


def _rate(failed: int, attempts: int) -> float | None:
    return failed / attempts if attempts else None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def compare_run_profiles(current: dict[str, Any],
                         previous: dict[str, Any]) -> dict[str, Any]:
    """本次 run 与上一次 run 的逐阶段失败率/尝试数对比（R43）。

    比较口径与 ``scripts/provider_failure_profile.py`` 一致：
    - **按 node_id 汇总**同一 run 内的重复执行（`agent_deep` 可跑 4 次），
      而不是按出现顺序配对——两次 run 的执行次数本就可能不同，按序号配对
      会留下无对应的孤儿条目。
    - 差值一律 **current - previous**：正值=退步，负值=改善。
    - 差值用**未舍入**比值算，展示字段才舍入（与失败率闸门同理）。
    - 任一侧该阶段无尝试时 ``comparable=False``、rate 侧差值为 None——
      「无数据」不等于 0%，不让它冒充 0% 改善或恶化。
    """
    cur_pool = _pool_by_node(current)
    prev_pool = _pool_by_node(previous)

    stages: list[dict[str, Any]] = []
    for node_id in sorted(set(cur_pool) | set(prev_pool)):
        c = cur_pool.get(node_id, {"occurrences": 0, "attempts": 0,
                                   "completed": 0, "failed": 0})
        p = prev_pool.get(node_id, {"occurrences": 0, "attempts": 0,
                                    "completed": 0, "failed": 0})
        cur_rate = _rate(c["failed"], c["attempts"])
        prev_rate = _rate(p["failed"], p["attempts"])
        comparable = cur_rate is not None and prev_rate is not None
        stages.append({
            "node_id": node_id,
            "occurrences_current": c["occurrences"],
            "occurrences_previous": p["occurrences"],
            "attempts_current": c["attempts"],
            "attempts_previous": p["attempts"],
            "failed_current": c["failed"],
            "failed_previous": p["failed"],
            "failure_rate_current": _round(cur_rate),
            "failure_rate_previous": _round(prev_rate),
            "delta_failure_rate": (_round(cur_rate - prev_rate)
                                   if comparable else None),
            "delta_attempts": c["attempts"] - p["attempts"],
            "comparable": comparable,
        })
    # 退步的排前面（与挖矿脚本「失败多的优先」同款顺序），再按 node_id 稳定
    stages.sort(key=lambda s: (-s["failed_current"], -s["failed_previous"],
                               s["node_id"]))

    cur_totals = current.get("totals") or {}
    prev_totals = previous.get("totals") or {}
    cur_attempts, prev_attempts = (int(cur_totals.get("attempts", 0) or 0),
                                   int(prev_totals.get("attempts", 0) or 0))
    cur_failed, prev_failed = (int(cur_totals.get("failed", 0) or 0),
                               int(prev_totals.get("failed", 0) or 0))
    cur_rate = _rate(cur_failed, cur_attempts)
    prev_rate = _rate(prev_failed, prev_attempts)
    comparable = cur_rate is not None and prev_rate is not None
    cur_wall = current.get("wall_seconds")
    prev_wall = previous.get("wall_seconds")

    return {
        "previous_run_id": previous.get("run_id", ""),
        "previous_status": previous.get("status", ""),
        "previous_started_at": previous.get("started_at"),
        "previous_completed_at": previous.get("completed_at"),
        "previous_wall_seconds": prev_wall,
        "delta_wall_seconds": (round(cur_wall - prev_wall, 3)
                               if isinstance(cur_wall, (int, float))
                               and isinstance(prev_wall, (int, float)) else None),
        "totals": {
            "attempts_current": cur_attempts,
            "attempts_previous": prev_attempts,
            "delta_attempts": cur_attempts - prev_attempts,
            "failed_current": cur_failed,
            "failed_previous": prev_failed,
            "delta_failed": cur_failed - prev_failed,
            "failure_rate_current": _round(cur_rate),
            "failure_rate_previous": _round(prev_rate),
            "delta_failure_rate": (_round(cur_rate - prev_rate)
                                   if comparable else None),
            "comparable": comparable,
        },
        "stages": stages,
    }


def pick_recent_runs(current: dict[str, Any],
                     candidates: list[dict[str, Any]],
                     limit: int = 3) -> list[dict[str, Any]]:
    """挑出当前 run 之前最近的 ``limit`` 个 run（按时间**升序**返回）。

    与 ``pick_previous_run`` 同一套排序键与「严格更早」定义，只是从「取一个」
    扩成「取一串」。升序返回是因为趋势判定要从旧到新读——调用方拿到的顺序
    直接就是时间序列，不必再排一次。

    ``limit <= 0`` 返回空列表（不把「要多点对比」误当成「全都要」）。
    """
    if limit <= 0:
        return []
    current_key = _order_key(current.get("started_at"), current.get("mtime", 0.0))
    older = [
        c for c in candidates
        if c.get("run_id") != current.get("run_id")
        and _order_key(c.get("started_at"), c.get("mtime", 0.0)) < current_key
    ]
    older.sort(key=lambda c: (_order_key(c.get("started_at"), c.get("mtime", 0.0)),
                              str(c.get("run_id", ""))))
    return older[-limit:]


TREND_IMPROVING = "improving"
TREND_REGRESSING = "regressing"
TREND_STABLE = "stable"
TREND_INSUFFICIENT = "insufficient"

# 连续退步的判据：最近 ``TREND_STREAK_REQUIRED`` 次相邻对比**全部**为正。
# 用「连续」而不是「与首个基线比」：后者会被一次偶发尖峰带偏——首次 50%、
# 第二次 0%、第三次 10% 明明在退步，与首个基线比却是改善。R47 §8-5 要的正
# 是「连续三次都在退步」这种形状。
TREND_STREAK_REQUIRED = 2


def compare_run_baseline(current: dict[str, Any],
                         previous_runs: list[dict[str, Any]]) -> dict[str, Any]:
    """把「本次 run」与一串历史 run 排成时间序列，判趋势（R50）。

    ``previous_runs`` 是**按时间升序**的历史画像（``pick_recent_runs`` 的输出）。
    差值一律 current - previous，正值=退步（与 ``compare_run_profiles`` 同款）。

    趋势结论（``trend``）:
    - ``insufficient``：没有可比的相邻对比——没有序列就谈不上趋势。
      「无数据」不冒充 ``stable``。
    - ``regressing``：最近 ``TREND_STREAK_REQUIRED`` 次相邻差值**全部 > 0**。
    - ``improving``：同样连续、且全部 < 0。
    - ``stable``：其余（含「有涨有跌」、「持平」、以及只有 1 次对比）。

    这是「多 run 基线」相对「只比上一次」的全部增量：单次对比看不出方向，
    序列才看得出。它**不**替代失败率闸门——闸门判「当前是否超阈」，这里判
    「是否在持续变坏」。
    """
    series = [*(previous_runs or []), current]
    points: list[dict[str, Any]] = []
    for index, profile in enumerate(series):
        totals = profile.get("totals") or {}
        attempts = int(totals.get("attempts", 0) or 0)
        failed = int(totals.get("failed", 0) or 0)
        points.append({
            "run_id": profile.get("run_id", ""),
            "status": profile.get("status", ""),
            "started_at": profile.get("started_at"),
            "attempts": attempts,
            "failed": failed,
            "failure_rate": _round(_rate(failed, attempts)),
            "wall_seconds": profile.get("wall_seconds"),
            "is_current": index == len(series) - 1,
        })

    deltas: list[dict[str, Any]] = []
    for older, newer in zip(points, points[1:]):
        old_rate = _rate(older["failed"], older["attempts"])
        new_rate = _rate(newer["failed"], newer["attempts"])
        comparable = old_rate is not None and new_rate is not None
        deltas.append({
            "from_run_id": older["run_id"],
            "to_run_id": newer["run_id"],
            "failure_rate_from": _round(old_rate),
            "failure_rate_to": _round(new_rate),
            "delta_failure_rate": (_round(new_rate - old_rate)
                                   if comparable else None),
            "comparable": comparable,
        })

    comparable_deltas = [d for d in deltas if d["comparable"]]
    if len(comparable_deltas) < TREND_STREAK_REQUIRED:
        trend = TREND_INSUFFICIENT
    else:
        tail = comparable_deltas[-TREND_STREAK_REQUIRED:]
        if all(d["delta_failure_rate"] > 0 for d in tail):
            trend = TREND_REGRESSING
        elif all(d["delta_failure_rate"] < 0 for d in tail):
            trend = TREND_IMPROVING
        else:
            trend = TREND_STABLE

    return {
        "points": points,
        "deltas": deltas,
        "trend": trend,
        "consecutive_required": TREND_STREAK_REQUIRED,
        "baseline_run_ids": [p["run_id"] for p in series[:-1]],
    }
