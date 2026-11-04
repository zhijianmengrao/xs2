"""R136：history.json ↔ git 双账核对。

背景（实测，R135 §7 预告）：``tests/fixtures/e2e_retry_history/history.json``
是写回链路的唯一权威账本（索引 §6.2），但「账本与第二份账（git bot 提交）
是否一致」此前只靠人眼。实测 2026-11-05：

- 63 条中 56 条 ``source=ci``、7 条 legacy（无 source，R93 标注之前的种子）；
- legacy 第 1 条 run_id 是 ISO 时间戳形状（唯一一条非 ``ci-`` 形状）；
- 56 条 ``ci-`` 条目与 git 里 62 个 ``chore(e2e): record CI run <id>`` bot
  提交**双向恰等**（62 = 62，无缺、无多余、无重复）。

本文件把三件事钉住：

- **H1 逐条形状**：``source='ci'`` 条目 run_id 必须是 ``ci-<数字>``；计数
  字段（total/passed/failed/retried/attempts）必须是 int；``scenarios``
  必须是 dict 列表（name/passed/attempts 在场）；时间戳形状的 run_id
  **恰好 1 条**且是第 1 条（legacy 种子，防止新条目再以时间戳入库）。
- **H2 账序**：run_id 无重复；``exported_at`` 单调不减。
- **H3 双账恰等**：git bot 提交的 run id 集合 == ``source='ci'`` 条目的
  run id 集合（双向差额逐一报出）。**浅检出下显式红**（附
  ``git fetch --unshallow`` 指引）——R136 同时给 backend / windows-backend
  的 checkout 加了 ``fetch-depth: 0``，CI 里本判据是真的，不许降级成 skip。

边界：不核对这些 run 的测试结果对不对（那是 R113 失败形状与闸门判据的
职责）；不数 history 长度（每轮自然 +2，无魔法数）；``totals.runs`` 的
内容复算在 R83 已钉，此处不重复。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY = REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history" / "history.json"
RUN_ID_RX = re.compile(r"^ci-\d{8,}$")
TIMESTAMP_RX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
COUNT_FIELDS = ("total", "passed", "failed", "retried", "attempts")


def _entries() -> list[dict]:
    document = json.loads(HISTORY.read_text(encoding="utf-8"))
    entries = document["history"] if isinstance(document, dict) else document
    assert isinstance(entries, list) and entries, "history.json 没有条目"
    return entries


def _entries_by_source(entries: list[dict], source: str | None) -> list[dict]:
    return [e for e in entries if e.get("source") == source]


def test_entry_shapes_and_single_legacy_seed() -> None:
    """H1：ci 条目形状钉死；时间戳形状 run_id 恰好 1 条且是第 1 条。"""
    entries = _entries()
    timestamp_shaped = [
        i for i, e in enumerate(entries)
        if not RUN_ID_RX.match(str(e.get("run_id", "")))
    ]
    assert timestamp_shaped == [0], (
        f"run_id 非 ci-形状的条目应只有第 1 条 legacy 种子，实际位于："
        f"{timestamp_shaped}（{[entries[i].get('run_id') for i in timestamp_shaped]}）"
    )
    assert TIMESTAMP_RX.match(str(entries[0]["run_id"])), (
        f"第 1 条 legacy 种子形状漂移：{entries[0]['run_id']!r}"
    )
    for idx, entry in enumerate(entries):
        where = f"history[{idx}]（{str(entry.get('run_id'))[:30]}）"
        assert entry.get("source") in ("ci", None), f"{where} source 非法：{entry.get('source')!r}"
        for field in COUNT_FIELDS:
            value = entry.get(field)
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{where} 计数字段 {field} 必须是 int，实为 {type(value).__name__}: {value!r}"
            )
        assert entry["passed"] + entry["failed"] == entry["total"], (
            f"{where} passed+failed != total（{entry['passed']}+{entry['failed']}"
            f"!={entry['total']}）——账内自洽被破坏"
        )
        scenarios = entry.get("scenarios")
        assert isinstance(scenarios, list) and all(
            isinstance(s, dict) and {"name", "passed", "attempts"} <= set(s)
            for s in scenarios
        ), f"{where} scenarios 形状不对"


def test_run_ids_unique_and_exported_at_monotonic() -> None:
    """H2：run_id 无重复；exported_at 单调不减（乱序即红）。"""
    entries = _entries()
    ids = [e["run_id"] for e in entries]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"重复 run_id：{dupes}"
    stamps = [e["exported_at"] for e in entries]
    assert stamps == sorted(stamps), (
        "exported_at 不是单调不减——账序被破坏："
        + "; ".join(
            f"{a} -> {b}" for a, b in zip(stamps, stamps[1:]) if b < a
        )
    )


def _git_bot_run_ids() -> set[str]:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if probe.stdout.strip() == "true":
        raise AssertionError(
            "当前检出是浅克隆，无法与 git bot 提交对账（R136 起 CI 的 "
            "backend / windows-backend 已 fetch-depth: 0）。请执行 "
            "`git fetch --unshallow` 后重跑；不许把本判据降级成 skip。"
        )
    log = subprocess.run(
        ["git", "log", "--format=%s"], cwd=REPO_ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    return set(re.findall(r"record CI run (\d+)", log))


def test_history_matches_git_bot_commits_bidirectionally() -> None:
    """H3：git bot 提交 run id 集合 == ci-形状条目集合（双向恰等）。

    实测口径：6 条 R93 前的 legacy 条目虽无 ``source`` 标注，但同样有 bot
    提交在账；唯一对不上 git 的是第 1 条时间戳种子（H1 钉死恰好 1 条）。
    对账按 **run_id 形状** 取集合，不按 source 标注——标注是元数据，账是
    run id 本身。
    """
    entries = _entries()
    ci_ids = {
        str(e["run_id"])[3:] for e in entries if RUN_ID_RX.match(str(e.get("run_id", "")))
    }
    bot_ids = _git_bot_run_ids()
    missing_in_history = sorted(bot_ids - ci_ids)
    missing_in_git = sorted(ci_ids - bot_ids)
    assert not missing_in_history and not missing_in_git, (
        "双账漂移：git bot 提交有而 history.json 无 "
        f"{missing_in_history}；history.json 有而 git 无 {missing_in_git}"
    )
