"""把 e2e 的 ``--metrics-json`` 渲染成 CI step summary 的 markdown（R74）。

用法::

    python scripts/e2e_retry_summary.py <metrics.json> >> "$GITHUB_STEP_SUMMARY"

这个脚本**不判失败**：metrics 缺失或损坏时打印一条可见的说明并退出 0。
它只负责把「重跑有多频繁」变得可读；e2e 的判决仍由那一步自己的退出码承担。
静默吞掉缺失会让人把「没有数据」误读成「0 次重跑」——所以两种异常都要在
输出里写出来。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _cell(text: str) -> str:
    """markdown 表格单元格：竖线与换行会破坏表格。"""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def render(payload: dict) -> str:
    """metrics payload → 一段 markdown（只列发生过重跑的场景）。"""
    total = int(payload.get("total") or 0)
    retried = int(payload.get("retried") or 0)
    scenarios = payload.get("scenarios") or []
    attempts = sum(int(item.get("attempts") or 0) for item in scenarios)
    lines = [
        f"**e2e 重跑：{retried} / {total} 个场景重跑**"
        f"（总尝试 {attempts} 次，通过 {int(payload.get('passed') or 0)}）"
    ]
    rows = [item for item in scenarios
            if int(item.get("attempts") or 0) > 1]
    if rows:
        lines += ["", "| 场景 | 尝试次数 | 第一次判红 |", "|---|---|---|"]
        for item in rows:
            lines.append(
                f"| {_cell(str(item.get('name') or ''))} "
                f"| {int(item.get('attempts') or 0)} "
                f"| {_cell(str(item.get('first_failure') or ''))} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("用法：python scripts/e2e_retry_summary.py <metrics.json>",
              file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(f"_e2e metrics 未生成（{path}）：e2e 可能在写出前就退出了_")
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"_e2e metrics 无法解析（{path}）：{exc}_")
        return 0
    if not isinstance(payload, dict):
        print(f"_e2e metrics 形状无效（{path}）：顶层不是对象_")
        return 0
    print(render(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
