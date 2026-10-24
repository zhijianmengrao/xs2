# -*- coding: utf-8 -*-
"""Round 16：humanware score-content 并发性能基线（R15-6 / R16 P1-1）。

对运行中的服务（默认 8021）以 N 路并发请求 POST /api/humanware/score-content，
测量短内容（argv 路径）与长内容（42K 字符，stdin 通道）两场景的延迟分布，
量化 `_CLI_SEMAPHORE=4` 的排队行为，为是否需要调参提供数据。

用法：.venv/Scripts/python.exe scripts/_hw_bench_r16.py
退出码 0 = 全部请求成功且产出数据表；非 0 = 存在失败请求。
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8021"
WS = "welcome"
CHARACTER = "林晚"
SHORT = "结论已经给出，方案可以执行。"  # 14 字符，argv 路径
LONG = "结论已经给出，方案可以执行。" * 3000  # 42,000 字符，stdin 路径
LEVELS = (1, 2, 4, 8, 16)


def _post_once(payload: dict) -> tuple[int, float]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/humanware/score-content",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            resp.read()
            return resp.status, time.perf_counter() - start
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, time.perf_counter() - start


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[idx]


def _run_level(label: str, payload: dict, n: int) -> str:
    with ThreadPoolExecutor(max_workers=n) as pool:
        latencies: list[float] = []
        statuses: list[int] = []
        start = time.perf_counter()
        for status, latency in pool.map(lambda _: _post_once(payload), range(n)):
            statuses.append(status)
            latencies.append(latency)
        wall = time.perf_counter() - start
    ok = all(s == 200 for s in statuses)
    line = (
        f"| {label} | {n} | {wall:.2f} | {n / wall:.2f} "
        f"| {statistics.mean(latencies)*1000:.0f} "
        f"| {_percentile(latencies, 50)*1000:.0f} "
        f"| {_percentile(latencies, 95)*1000:.0f} "
        f"| {max(latencies)*1000:.0f} "
        f"| {'OK' if ok else 'FAIL ' + str(statuses)} |"
    )
    print(line)
    return "OK" if ok else "FAIL"


def main() -> int:
    # 就绪检查 + 预热（排除首请求的解释器冷启动噪声）
    status, _ = _post_once({"workspace_id": WS, "character": CHARACTER, "content": SHORT})
    if status != 200:
        print(f"服务不可用（HTTP {status}），请先启动 8021 实例")
        return 1
    _post_once({"workspace_id": WS, "character": CHARACTER, "content": SHORT})
    _post_once({"workspace_id": WS, "character": CHARACTER, "content": LONG})

    print(f"目标: {BASE}/api/humanware/score-content  workspace={WS}  并发闸门: Semaphore(4)\n")
    print("| 场景 | N | 墙钟(s) | 吞吐(req/s) | 均值(ms) | P50(ms) | P95(ms) | Max(ms) | 结果 |")
    print("|---|---|---|---|---|---|---|---|---|")
    outcomes = []
    for level in LEVELS:
        outcomes.append(_run_level("短内容 argv", {"workspace_id": WS, "character": CHARACTER, "content": SHORT}, level))
    for level in LEVELS:
        outcomes.append(_run_level("长内容 42K stdin", {"workspace_id": WS, "character": CHARACTER, "content": LONG}, level))
    return 0 if all(o == "OK" for o in outcomes) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
