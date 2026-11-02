"""e2e 重跑率的跨 run 趋势（R78）。

R74 让**单次** run 的重跑频率可机读（``--metrics-json`` + step summary），但
每次 run 都是孤立的：没有历史就说不出「这轮比上轮差」。本脚本把每次入库的
运行追加成一轮，历史随被判数据入库（快照式），本机显式 ``record`` 后随提交
进入仓库；R88 起 CI 的独立 ``e2e-history-writeback`` job 在 main 的 push 上
``record`` 并回写（``run_id=ci-<run_id>``，同 run 重跑覆盖同一轮），写权限只给
那个 job——``backend`` 的 ``check`` 仍是只读。

**判据边界（R78 用户拍定）**：只判「历史数据有效」，不判「趋势变差」。

- e2e 只有 10 个场景，**1 次重跑 = 10 个百分点**：任何「变差」阈值都会被这
  个分辨率压成单点窗口（R63/R69 的教训），样本量根本撑不起趋势判决；
- 所以 ``check`` 的 0 退出**只表示数据可读**，输出必须写出「本步不判趋势」，
  否则一次恒绿就会被读成「重跑率没变差」。

退出码（与 ``docs/JUDGEMENT_LEDGER.md`` §5 同一套语义）：

- 0 通过（数据有效；**不是**「趋势合格」）
- 2 用法错误（``--run-id`` 为空）
- 3 无样本（历史文件不存在或为空，还没有任何一轮入库）
- 4 元数据问题（JSON 读不懂、形状无效、计数自相矛盾）→ 重录/修历史
- 8 不适用：这里没有可失败的判据算术，所有失败都是数据问题（4），
  留一个走不到的 8 只会让人去查判据

用法::

    # 本机跑完 e2e 后（显式入库，不会自动发生）
    python scripts/e2e_retry_history.py record "$TMP/e2e-metrics.json" \\
        --history tests/fixtures/e2e_retry_history/history.json

    # CI：只读校验并渲染趋势（损坏/矛盾 → 非零退出）
    python scripts/e2e_retry_history.py check \\
        --history tests/fixtures/e2e_retry_history/history.json \\
        >> "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1

# 历史窗口：80 轮。与快照 ``history`` 的 5 轮不是同一个量——那个是「上一轮
# 基线」的材料，只需要相邻两次；这里是**保留期**，不是判决门槛（趋势仍不判
# 好坏，R78）。窗口是常量就必有翻转点用例（R69）。
#
# R89 从 20 提到 40：R88 把「一轮 = 一次显式导出」改成「一轮 = 一次 main push」，
# doc-only 提交也占一格。R88 自己就吃掉 3 轮（2 次 CI + 之前本机导出），20 轮
# 只剩 6~7 个工作轮的量。40 ≈ 13 轮，回到 R88 前的日历跨度。
# R112 从 40 提到 80（用户拍板）：R111 时已用到 39/40，而 39 条只覆盖
# 2026-11-01 01:51 ～ 11-02 13:32（约 1.5 天）——每个工作轮约 3 次 push
# （实现/CI/文档），40 格只剩 ~13 个工作轮。80 格把趋势跨度扩到 ~26 个
# 工作轮，而 JSON 体积与裁剪成本都可忽略。
MAX_ROUNDS = 80

# R109：保留期可配置，默认值见上（R112 起 80）。环境变量是**部署策略**，
# 不是判据：所有运行期入口（record / writeback / replay 驱动 / 冲突夹具）
# 都必须走 ``max_rounds()`` 这同一个读取点，否则「裁剪按环境变量、期望按
# 默认值算」这类两个事实两种说法会立刻出现。
MAX_ROUNDS_ENV = "XS2_MAX_ROUNDS"
MAX_ROUNDS_FLOOR = 3
MAX_ROUNDS_CEILING = 1000


def max_rounds() -> int:
    """当前历史保留期：``XS2_MAX_ROUNDS`` 覆盖，非法值退回 80 并告警。

    非法值不静默生效：写错的环境变量会让策略悄悄回到默认，正是「配置
    看起来生效了」的典型坑。范围夹在 [3, 1000]：低于 3 撑不起相邻两轮
    趋势，高于 1000 已超出趋势样本的合理规模。
    """
    raw = os.environ.get(MAX_ROUNDS_ENV, "").strip()
    if not raw:
        return MAX_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        print(f"::warning::{MAX_ROUNDS_ENV}={raw!r} 不是整数，"
              f"保留期退回 {MAX_ROUNDS}", file=sys.stderr)
        return MAX_ROUNDS
    if value < MAX_ROUNDS_FLOOR or value > MAX_ROUNDS_CEILING:
        print(f"::warning::{MAX_ROUNDS_ENV}={value} 超出 "
              f"[{MAX_ROUNDS_FLOOR}, {MAX_ROUNDS_CEILING}]，"
              f"保留期退回 {MAX_ROUNDS}", file=sys.stderr)
        return MAX_ROUNDS
    return value

# 条目来源（R93）：CI 写回与本机显式导出是两个不同的入口，历史要能自己说清
# 哪一轮来自哪。旧条目没有这个字段——按「未标注」报告，**不猜**（不拿 run_id
# 的形状反推来源：那会把命名习惯变成事实）。
SOURCES = ("ci", "local")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_SAMPLE = 3
EXIT_META_DRIFT = 4

INT_FIELDS = ("total", "passed", "failed", "retried")


class HistoryError(Exception):
    """历史或 metrics 的元数据问题：处置是重录/修文件，不是改判据（退出 4）。"""


def _is_int(value: object) -> bool:
    """``bool`` 是 ``int`` 的子类：``True`` 不能冒充一次重跑计数。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _scenario_error(item: object, index: int) -> str | None:
    if not isinstance(item, dict):
        return f"scenarios[{index}] 不是对象"
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return f"scenarios[{index}].name 不是非空字符串"
    if not isinstance(item.get("passed"), bool):
        return f"scenarios[{index}].passed 不是布尔值"
    attempts = item.get("attempts")
    if not _is_int(attempts) or attempts < 1:
        return f"scenarios[{index}].attempts 不是 >=1 的整数"
    if not isinstance(item.get("first_failure", ""), str):
        return f"scenarios[{index}].first_failure 不是字符串"
    return None


def _counts_error(entry: dict, label: str) -> str | None:
    """计数一致性：``passed + failed == total`` 且尝试次数撑得起重跑数。

    这些是**算术**上的自相矛盾，属于数据坏了（退出 4），不是「判据算不出来」
    （退出 8）：把处置写成 8，读的人会去修一个没坏的判据。
    """
    for field in INT_FIELDS:
        value = entry.get(field)
        if not _is_int(value) or value < 0:
            return f"{label}.{field} 不是 >=0 的整数"
    total = entry["total"]
    passed = entry["passed"]
    failed = entry["failed"]
    retried = entry["retried"]
    if passed + failed != total:
        return (f"{label} 计数矛盾：passed {passed} + failed {failed} "
                f"!= total {total}")
    if retried > total:
        return f"{label} 计数矛盾：retried {retried} > total {total}"
    attempts = entry.get("attempts")
    if not _is_int(attempts) or attempts < 0:
        return f"{label}.attempts 不是 >=0 的整数"
    # 每个重跑过的场景至少 2 次尝试（多出的那次就是重跑本身），没重跑的
    # 至少 1 次；所以总尝试次数不可能少于 total + retried。
    if attempts < total + retried:
        return (f"{label} 计数矛盾：总尝试 {attempts} < total + retried "
                f"{total + retried}")
    scenarios = entry.get("scenarios")
    if not isinstance(scenarios, list):
        return f"{label}.scenarios 不是列表"
    if len(scenarios) != total:
        return f"{label}.scenarios 有 {len(scenarios)} 项，total 是 {total}"
    for index, item in enumerate(scenarios):
        reason = _scenario_error(item, index)
        if reason:
            return f"{label}.{reason}"
        if item["attempts"] > 1 and entry["retried"] < 1:
            return f"{label} 计数矛盾：有场景重跑，retried 却是 {retried}"
    rows = sum(int(item["attempts"]) for item in scenarios)
    if rows != attempts:
        return f"{label} 计数矛盾：scenarios 尝试次数求和 {rows} != attempts {attempts}"
    if sum(1 for item in scenarios if item["passed"]) != passed:
        return f"{label} 计数矛盾：通过场景数与 passed {passed} 不符"
    if sum(1 for item in scenarios if item["attempts"] > 1) != retried:
        return f"{label} 计数矛盾：尝试次数 >1 的场景数≠retried {retried}"
    return None


def entry_from_metrics(payload: object) -> dict:
    """``--metrics-json`` 的 payload → 一条历史条目（不含 run_id/exported_at）。

    校验落在**同一组计数**上：payload 自己说 ``passed+failed==total``，再用
    ``scenarios`` 逐项反算一遍；两边对不上就是数据坏了，而不是「趋势判不出来」。
    """
    if not isinstance(payload, dict):
        raise HistoryError("metrics 顶层不是对象")
    entry = {field: payload.get(field) for field in INT_FIELDS}
    entry["schema"] = payload.get("schema")
    if entry["schema"] != SCHEMA:
        raise HistoryError(
            f"metrics schema 是 {entry['schema']!r}，期望 {SCHEMA}")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise HistoryError("metrics.scenarios 不是列表")
    entry["scenarios"] = scenarios
    entry["attempts"] = sum(
        int(item["attempts"]) for item in scenarios
        if isinstance(item, dict) and _is_int(item.get("attempts")))
    reason = _counts_error(entry, "metrics")
    if reason:
        raise HistoryError(reason)
    return {
        "total": entry["total"],
        "passed": entry["passed"],
        "failed": entry["failed"],
        "retried": entry["retried"],
        "attempts": entry["attempts"],
        "scenarios": [
            {
                "name": item["name"],
                "passed": item["passed"],
                "attempts": item["attempts"],
                "first_failure": item.get("first_failure", ""),
            }
            for item in scenarios
        ],
    }


def validate_history(payload: object) -> list[dict]:
    """历史文件形状校验，返回条目列表；任何问题都抛 ``HistoryError``。"""
    if not isinstance(payload, dict):
        raise HistoryError("顶层不是对象")
    if payload.get("schema") != SCHEMA:
        raise HistoryError(
            f"schema 是 {payload.get('schema')!r}，期望 {SCHEMA}")
    history = payload.get("history")
    if not isinstance(history, list):
        raise HistoryError("history 不是列表")
    seen: set[str] = set()
    for index, entry in enumerate(history):
        label = f"history[{index}]"
        if not isinstance(entry, dict):
            raise HistoryError(f"{label} 不是对象")
        run_id = entry.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise HistoryError(f"{label}.run_id 不是非空字符串")
        if run_id in seen:
            raise HistoryError(f"{label}.run_id 重复：{run_id}")
        seen.add(run_id)
        if _parse_ts(entry.get("exported_at")) is None:
            raise HistoryError(
                f"{label}.exported_at 不是可解析的 ISO 时间："
                f"{entry.get('exported_at')!r}")
        source = entry.get("source")
        if source is not None and source not in SOURCES:
            raise HistoryError(
                f"{label}.source 是 {source!r}，期望 {'/'.join(SOURCES)} 或缺失")
        reason = _counts_error(entry, label)
        if reason:
            raise HistoryError(reason)
    return history


def _read_json(path: Path, what: str) -> object:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HistoryError(f"{what}无法读取（{path}）：{exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        # json.JSONDecodeError 是 ValueError 的子类；这里归成元数据问题（4），
        # 不往上冒成「判据算术失败」（R77 的教训）。
        raise HistoryError(f"{what}无法解析（{path}）：{exc}") from exc


def load_history(path: Path) -> list[dict]:
    return validate_history(_read_json(path, "历史"))


def _write_history(path: Path, history: list[dict]) -> None:
    """先写临时文件再 ``os.replace``：中途失败不会留下半份历史。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "history": history}
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _same_observation(existing: dict, entry: dict) -> bool:
    """除 ``run_id`` / ``exported_at`` 外完全一致：重跑没有带来新观测。

    ``record`` 只在这一天成立时保留首次的 ``exported_at``——否则同一 run
    重跑会把时间戳改写，CI 写回因此产生一次**内容其实没变**的提交（R89）。
    """
    return all(
        existing.get(field) == entry.get(field)
        for field in ("total", "passed", "failed", "retried", "attempts",
                      "scenarios"))


def record(metrics_path: Path, history_path: Path,
           run_id: str | None = None, check_only: bool = False,
           source: str = "local") -> int:
    if not metrics_path.is_file():
        print(f"metrics 未生成（{metrics_path}）：e2e 可能在写出前就退出了",
              file=sys.stderr)
        return EXIT_NO_SAMPLE
    if history_path.exists() and not history_path.is_file():
        print(f"历史路径不是文件（{history_path}）", file=sys.stderr)
        return EXIT_META_DRIFT
    try:
        entry = entry_from_metrics(_read_json(metrics_path, "metrics"))
        history = (load_history(history_path)
                   if history_path.is_file() else [])
    except HistoryError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_META_DRIFT

    exported_at = _iso_now()
    if run_id is None:
        run_id = exported_at
    elif not run_id.strip():
        print("--run-id 不能为空", file=sys.stderr)
        return EXIT_USAGE
    if source not in SOURCES:
        print(f"--source 必须是 {'/'.join(SOURCES)}，收到 {source!r}",
              file=sys.stderr)
        return EXIT_USAGE
    record_entry = {"run_id": run_id, "exported_at": exported_at,
                    "source": source, **entry}

    replaced = False
    unchanged = False
    for index, existing in enumerate(history):
        if existing["run_id"] == run_id:
            replaced = True
            if _same_observation(existing, entry):
                # 同一 run 重跑且观测一致：保留首次的时间戳，文件逐字节不变。
                # 否则 CI 写回的「没有变化就不提交」永远不成立（R89 实测）。
                unchanged = True
                record_entry = existing
            history[index] = record_entry
            break
    else:
        history.append(record_entry)
    window = max_rounds()
    trimmed = history[-window:]
    # 写入前自校验（R92）：算出来的历史必须能通过自己的校验器。这条覆盖
    # record 自己的算术（覆盖/去重/裁剪），不是再验一遍输入——输入已经验过。
    try:
        validate_history({"schema": SCHEMA, "history": trimmed})
    except HistoryError as exc:
        print(f"算出来的历史没有通过校验（不写入）：{exc}", file=sys.stderr)
        return EXIT_META_DRIFT
    if check_only:
        print(f"check-only：将写入 run_id={run_id}："
              f"{entry['retried']}/{entry['total']} 个场景重跑"
              f"（总尝试 {entry['attempts']} 次），历史 {len(trimmed)}/"
              f"{window} 轮（未写入）")
        return EXIT_OK
    try:
        _write_history(history_path, trimmed)
    except OSError as exc:
        print(f"历史写入失败（{history_path}）：{exc}", file=sys.stderr)
        return EXIT_META_DRIFT

    if unchanged:
        action = "覆盖（观测无变化，保留首次 exported_at）"
    else:
        action = "覆盖" if replaced else "记录"
    print(f"已{action} run_id={run_id}：{entry['retried']}/{entry['total']} "
          f"个场景重跑（总尝试 {entry['attempts']} 次），"
          f"历史 {len(trimmed)}/{window} 轮")
    return EXIT_OK


def _rate(retried: int, total: int) -> str:
    return f"{retried * 100.0 / total:.1f}%" if total else "n/a"


def render_trend(history: list[dict], limit: int = 5) -> str:
    """最近 ``limit`` 轮的 markdown；``check`` 的 step summary 正文。

    R115：表里补 ``失败`` 列——失败数从 R112 起就随条目入库，但趋势表一直
    没显示它，等于「写了没人看」。0 场景的合法轮次与「历史为空」必须分开
    说话：前者是可读数据、只是重跑率不可计算，后者才是没有判定力。
    """
    rounds = history[-limit:] if limit > 0 else history
    latest_total = int(rounds[-1]["total"]) if rounds else 0
    lines = [f"**e2e 重跑趋势：最近 {len(rounds)} / {len(history)} 轮**", "",
             "| 轮次 | 时间 | 场景 | 失败 | 重跑 | 重跑率 | 总尝试 |",
             "|---|---|---|---|---|---|---|"]
    for entry in rounds:
        stamp = str(entry["exported_at"])[:16].replace("T", " ")
        run_id = str(entry["run_id"])
        shown = run_id if len(run_id) <= 24 else run_id[:21] + "..."
        lines.append(
            f"| {shown} | {stamp} | {int(entry['total'])} "
            f"| {int(entry['failed'])} "
            f"| {int(entry['retried'])} "
            f"| {_rate(int(entry['retried']), int(entry['total']))} "
            f"| {int(entry['attempts'])} |")
    lines.append("")
    if not rounds:
        lines.append("_本步没有判定力：历史里没有可读的轮次。_")
    elif latest_total:
        lines.append(
            "_本步只校验历史有效性，不判趋势好坏：最近一轮 "
            f"{latest_total} 个场景，1 次重跑 = "
            f"{100.0 / latest_total:.0f} 个百分点；样本量不足以得出"
            "「变差」的结论，退出 0 只表示数据可读。_")
    else:
        lines.append(
            "_本步只校验历史有效性，不判趋势好坏：最近一轮 0 个场景，"
            "重跑率不可计算（n/a）；退出 0 只表示这一轮数据可读，"
            "不代表通过。_")
    return "\n".join(lines)


def render_sources(history: list[dict]) -> str:
    """来源分布（R93）：只展示，不参与判决。

    旧条目没有 ``source`` → 计入「未标注」，**不根据 run_id 形状猜**。
    """
    counts = {source: 0 for source in SOURCES}
    unmarked = 0
    for entry in history:
        source = entry.get("source")
        if source in counts:
            counts[source] += 1
        else:
            unmarked += 1
    return (f"来源：CI {counts['ci']} / 本机 {counts['local']} / "
            f"未标注 {unmarked}（共 {len(history)} 轮）")


def check(history_path: Path, limit: int = 5) -> int:
    if history_path.exists() and not history_path.is_file():
        print(f"历史路径不是文件（{history_path}）", file=sys.stderr)
        return EXIT_META_DRIFT
    if not history_path.is_file():
        print(f"历史文件不存在（{history_path}）：还没有任何一轮 e2e 重跑率入库",
              file=sys.stderr)
        return EXIT_NO_SAMPLE
    try:
        history = load_history(history_path)
    except HistoryError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_META_DRIFT
    if not history:
        print(f"历史为空（{history_path}）：还没有任何一轮 e2e 重跑率入库",
              file=sys.stderr)
        return EXIT_NO_SAMPLE
    print(render_trend(history, limit))
    print(render_sources(history))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="e2e 重跑率的跨 run 趋势：record 入库、check 只读校验")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="把一次 e2e 的 metrics 追加成一轮历史")
    rec.add_argument("metrics", type=Path, help="e2e --metrics-json 写出的文件")
    rec.add_argument("--history", type=Path, required=True,
                     help="历史文件（不存在则创建）")
    rec.add_argument("--run-id", default=None,
                     help="轮次标识（默认取入库时间的 UTC 时间戳）；"
                          "同一个 id 重复写入是覆盖而不是追加")
    rec.add_argument("--check-only", action="store_true",
                     help="只校验并打印将写入的条目，不写历史（PR 预检，R92）")
    rec.add_argument("--source", default="local",
                     help=f"条目来源：{'/'.join(SOURCES)}（默认 local；R93）")

    chk = sub.add_parser("check", help="只读校验历史并渲染趋势（损坏 → 非零）")
    chk.add_argument("--history", type=Path, required=True,
                     help="历史文件")
    chk.add_argument("--limit", type=int, default=5,
                     help=f"趋势表最多显示最近几轮（默认 5；只影响显示，"
                          f"不改历史窗口 {max_rounds()}）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "record":
        return record(args.metrics, args.history, args.run_id,
                      check_only=args.check_only, source=args.source)
    return check(args.history, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
