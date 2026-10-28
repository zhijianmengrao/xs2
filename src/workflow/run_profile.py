"""供应商失败率画像（R38 §7.4 落地，R40）：每阶段尝试/失败聚合。

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
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# 供应商侧已实测的失败形态（R38 §2.0）：流式停摆表现为 120s/600s 超时打穿、
# 免费档 530/524/502。分类按错误文本关键词，宽松命中。
_ERROR_CLASS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("http_5xx", re.compile(r"\b(?:500|502|503|504|524|529|530)\b|http 5\d\d", re.IGNORECASE)),
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
