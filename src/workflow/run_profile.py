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

# 「最近 N 次全失败」的判据（R52）。与 ``trend`` 是两个正交的信号，不能并进
# 同一个字段（R51 §10-7 已经因为「两个指标混进一个 trend 会让退步语义变糊」
# 拒绝过耗时趋势，这里是同一个理由的第二次实例）。
#
# 为什么 ``trend`` 判不到这件事：``trend`` 看的是失败率的**相邻差值**。一个
# 每次都 100% 失败的工作流，相邻差值恒为 0，于是 ``regressing`` 永远不触发，
# 判出来是 ``stable``——「一直在全挂」被读成「没有变化」。这正是 R45/R46/R47
# 反复批评的那类盲区：判据只回答了「有没有在变坏」，没回答「现在是不是全坏」。
#
# 取值 3 的依据（R55 用真实数据复核，取代 R53 的「3 合理」这个无数据的结论）：
# 本机 8 个有 run 记录的 workflow、共 40 次 run。把它们当作历史时刻逐点回放，
# ``required=2`` 会触发 2 次——一次是 ``flywheel-build`` 真实的 6 连败，另一次
# 是 ``flywheel-character`` 的 2 连败，而那之后紧接着一次 run 就成功了。取 2
# 等于把「重试一次就恢复」报成运维告警，是噪声。``required=3`` 与 ``4`` 在本
# 数据上都只触发 1 次（同一个 6 连败事件），但 4 会把发现时点推迟一次 run，
# 没有任何额外精度收益。所以 3 是「能抓住真实事件、又不报 2 连败」的最小取值。
FAILURE_STREAK_REQUIRED = 3

# 门槛与默认回溯窗口放在同一处（R55）。R53 只用一条测试钉住了「N 必须 ≤
# 窗口点数」这个耦合，两个数仍分散在两个文件里——改任一处都不会碰到另一处，
# 测试红了也只是红在远处。这里建立单一来源：``workflow_routes`` 的
# ``baseline_limit`` 默认值直接引用 ``DEFAULT_BASELINE_LIMIT``。
#
# 约束本身：序列里最多 ``baseline_limit + 1`` 个点（历史 N 条 + 当前一条），
# 所以 ``FAILURE_STREAK_REQUIRED <= DEFAULT_BASELINE_LIMIT + 1`` 才可能成立。
# 由 ``tests/test_run_profile.py`` 钉住，而且现在两边读的是同一个常量。
DEFAULT_BASELINE_LIMIT = 5
MAX_BASELINE_LIMIT = 20


def failure_streak(points: list[dict[str, Any]],
                   required: int = FAILURE_STREAK_REQUIRED) -> dict[str, Any]:
    """从时间序列尾部数「连续失败的 run 数」（纯函数）。

    ``points`` 是 ``compare_run_baseline`` 产出的时间序列（旧→新）。从尾部往
    回数 ``status == "failed"`` 的连续条数，遇到第一个非 failed 就停。

    只认 ``failed``：``stopped``（人工停止）与 ``running``/``pending``（还没
    结论）都不是失败证据。把它们算进连续失败会让「我手动停了一个任务」变成
    运维告警。
    """
    consecutive = 0
    for point in reversed(points or []):
        if str(point.get("status") or "") != "failed":
            break
        consecutive += 1
    return {
        "consecutive_failed": consecutive,
        "required": required,
        # required <= 0 时永远不判成立：配置成 0 不该等于「一律告警」。
        "all_failed": required > 0 and consecutive >= required,
    }


def workflow_health(runs: list[dict[str, Any]],
                    required: int = FAILURE_STREAK_REQUIRED) -> dict[str, Any]:
    """把一个 workflow 的 run 序列聚合成「这个 workflow 现在健康吗」（R54）。

    ``runs`` 是 ``[{run_id, status, started_at, mtime}]``，顺序不限——内部按
    ``_order_key`` 排序后再从尾部数连续失败，调用方不必自己保证升序。

    为什么不能在任务级解决：``failure_streak`` 判的是「**这一条任务**引用的
    run 序列」。工作流列表要回答的是另一个问题——「**这个 workflow** 最近是不是
    一直在挂」。两者的差集正是本函数存在的理由：

    - 任务级只在当前页任务（``page_size`` 默认 20）范围内聚合，跨页、已删任务
      引用的 run 都不在其中；
    - 三个任务各跑过一次、各失败一次，任务级每条只看得到 1 连败，而 workflow
      整体已经连续输了 3 次 —— 这正是需要被看见的那一类。

    与 ``failure_streak`` 共用同一份判据（只认 ``failed``，``stopped`` /
    ``running`` / ``pending`` 都不算失败证据），不另写一份，否则两条路径迟早
    对「什么算失败」产生分歧。

    ``required <= 0`` 时永不判成立，与 ``failure_streak`` 一致：配置成 0 不该
    等于「一律告警」。
    """
    ordered = sorted(
        (r for r in (runs or []) if isinstance(r, dict)),
        key=lambda r: (_order_key(r.get("started_at"), r.get("mtime", 0.0)),
                       str(r.get("run_id", ""))),
    )
    # failure_streak 读 ``status``；这里把 run 元数据映射成它要的形状，避免
    # 在 run_profile 里出现第二套「连续失败」计数逻辑。
    points = [{"run_id": r.get("run_id", ""), "status": r.get("status", "")}
              for r in ordered]
    streak = failure_streak(points, required=required)
    latest = ordered[-1] if ordered else {}
    return {
        "run_count": len(ordered),
        "latest_run_id": latest.get("run_id") if ordered else None,
        "latest_status": latest.get("status") if ordered else None,
        "latest_started_at": latest.get("started_at") if ordered else None,
        "consecutive_failed": streak["consecutive_failed"],
        "required": streak["required"],
        "all_failed": streak["all_failed"],
    }


def workflow_trend(profiles: list[dict[str, Any]],
                   limit: int = DEFAULT_BASELINE_LIMIT) -> dict[str, Any]:
    """把一个 workflow 的 run 画像序列判成趋势（R55）。

    ``profiles`` 是 ``build_run_profile`` 的产物列表，**顺序不限**——与
    ``workflow_health`` 同一纪律：内部按 ``_order_key`` 排序，不信调用方给的
    顺序。文件名字典序会把 ``run-10`` 排在 ``run-9`` 前面（R54 §2.2 的实例），
    不排序就会把「最新的 run」认成错的那一条，于是判的是另一端的方向。

    与任务级 ``trend`` 的差别只在**输入范围**：任务级只沿一条任务的 run 序列
    看（``_collect_workflow_trends``），workflow 级沿整个 workflow 的 run 序列
    看。同一个 workflow 里多个任务交替跑时，任务级每条只看到自己那截，任何
    单条任务都判不出「这个 workflow 整体在变坏」——这正是本函数存在的理由，
    与 ``workflow_health`` 补的是同一层盲区（一个判状态，一个判方向）。

    判据**复用** ``compare_run_baseline`` 而不是另写一份：趋势的定义（相邻差值
    连续 N 次同向、``insufficient`` 不冒充 ``stable``）已经在那一处定型，重写
    一份会让两条路径对「什么叫退步」产生分歧——R53 §2.3 抽
    ``_rising_shape_violations``、R54 §2.2 复用 ``failure_streak`` 都是同一条
    理由。

    ``limit`` 只取最近的部分：趋势问的是「最近在不在变坏」，把五年前的 run
    算进序列既不改结论又白读文件。``limit <= 0`` 时取全部（与 ``health_limit``
    的 0 = 全部同义）。

    没有 run 记录时 ``trend=insufficient``、``points=[]``——「没有序列」不等于
    ``stable``，与 ``compare_run_baseline`` 的诚实缺席一致。
    """
    ordered = sorted(
        (p for p in (profiles or []) if isinstance(p, dict)),
        key=lambda p: (_order_key(p.get("started_at"), p.get("mtime", 0.0)),
                       str(p.get("run_id", ""))),
    )
    if limit and limit > 0:
        ordered = ordered[-limit:]
    if not ordered:
        return {
            "trend": TREND_INSUFFICIENT,
            "consecutive_required": TREND_STREAK_REQUIRED,
            "points_considered": 0,
            "comparisons": 0,
            "delta_failure_rate": None,
            "latest_run_id": None,
            "failure_rate_current": None,
            "failure_rate_previous": None,
        }
    baseline = compare_run_baseline(ordered[-1], ordered[:-1])
    deltas = baseline.get("deltas") or []
    return {
        "trend": baseline["trend"],
        "consecutive_required": baseline["consecutive_required"],
        "points_considered": len(baseline["points"]),
        "comparisons": len([d for d in deltas if d["comparable"]]),
        "delta_failure_rate": (deltas[-1]["delta_failure_rate"]
                               if deltas else None),
        "latest_run_id": ordered[-1].get("run_id") or None,
        "failure_rate_current": (baseline.get("totals") or {}).get(
            "failure_rate_current"),
        "failure_rate_previous": (baseline.get("totals") or {}).get(
            "failure_rate_previous"),
    }


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
        # 与 trend 正交的第二个信号（R52）：「最近 N 次全失败」。放在同一个
        # 基线块里是因为它要的正是这条时间序列，另开一次目录扫描没有意义；
        # 但它有独立的字段与判据，调用方可以只用其中一个。
        "failure_streak": failure_streak(points),
    }
