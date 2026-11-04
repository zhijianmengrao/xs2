"""把 e2e 的 ``--metrics-json`` 渲染成 CI step summary 的 markdown（R74）。

用法::

    python scripts/e2e_retry_summary.py <metrics.json> >> "$GITHUB_STEP_SUMMARY"

这个脚本**不判失败**：metrics 缺失或损坏时打印一条可见的说明并退出 0。
它只负责把「重跑有多频繁」变得可读；e2e 的判决仍由那一步自己的退出码承担。
静默吞掉缺失会让人把「没有数据」误读成「0 次重跑」——所以两种异常都要在
输出里写出来。

R130：损坏不只在顶层。``scenarios`` 不是列表、条目不是对象、``attempts``
不是整数，此前会以 ``AttributeError``/``ValueError`` 的 traceback 让这个
可观测性步骤判红——它把「损坏 → 可见说明 + 退出 0」的承诺只兑现到 JSON
解析那一层。现在渲染前先校验它真正要读的字段（``SummaryShapeError``）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


class SummaryShapeError(ValueError):
    """metrics 的内层形状坏了（R130）。

    摘要的契约是「不判失败」：坏数据必须变成一条**可见说明**并退出 0，
    而不是让 traceback 把可观测性步骤判红。顶层 JSON 解析与顶层对象检查
    在 ``main`` 里；这里管的是渲染真正会读的字段。
    """


def _cell(text: str) -> str:
    """markdown 表格单元格：竖线与换行会破坏表格。"""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _count(payload: dict, field: str) -> int:
    """读一个展示用计数：缺省按 0；出现就必须是 >=0 的整数。

    ``bool`` 是 ``int`` 的子类：``True`` 冒充一次通过/重跑，会让「通过 1」
    看起来像真实数据（与 ``e2e_retry_history._is_int`` 同一条边界）。
    """
    value = payload.get(field)
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SummaryShapeError(f"{field} 不是 >=0 的整数：{value!r}")
    return value


def _scenarios(payload: dict) -> list[tuple[str, int, str]]:
    """校验并展开 ``scenarios``：``(name, attempts, first_failure)``。

    只校验渲染真正会读的字段。``attempts`` 缺失按 0（保留旧行为），但出现
    时必须是 >=0 的整数——``"2"`` / ``true`` / 负数会让「重跑了几次」变成
    另一个数，或者直接把整行表打崩。
    """
    raw = payload.get("scenarios")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SummaryShapeError(
            f"scenarios 不是列表（{type(raw).__name__}）")
    rows: list[tuple[str, int, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise SummaryShapeError(f"scenarios[{index}] 不是对象")
        attempts = item.get("attempts")
        if attempts is None:
            attempts = 0
        if (isinstance(attempts, bool) or not isinstance(attempts, int)
                or attempts < 0):
            raise SummaryShapeError(
                f"scenarios[{index}].attempts 不是 >=0 的整数："
                f"{attempts!r}")
        rows.append((str(item.get("name") or ""), attempts,
                     str(item.get("first_failure") or "")))
    return rows


def render(payload: dict) -> str:
    """metrics payload → 一段 markdown（只列发生过重跑的场景）。

    渲染前先过 ``_count`` / ``_scenarios``：坏形状抛 ``SummaryShapeError``，
    由 ``main`` 变成可见说明；直接调用者看到的也是同一个异常，而不是半张表。
    """
    total = _count(payload, "total")
    retried = _count(payload, "retried")
    passed = _count(payload, "passed")
    scenarios = _scenarios(payload)
    attempts = sum(row[1] for row in scenarios)
    lines = [
        f"**e2e 重跑：{retried} / {total} 个场景重跑**"
        f"（总尝试 {attempts} 次，通过 {passed}）"
    ]
    rows = [row for row in scenarios if row[1] > 1]
    if rows:
        lines += ["", "| 场景 | 尝试次数 | 第一次判红 |", "|---|---|---|"]
        for name, count, failure in rows:
            lines.append(
                f"| {_cell(name)} | {count} | {_cell(failure)} |")
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
    try:
        print(render(payload))
    except SummaryShapeError as exc:
        print(f"_e2e metrics 形状无效（{path}）：{exc}_")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
