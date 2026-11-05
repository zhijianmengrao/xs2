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
  **至多 1 条**且只能是第 1 条（legacy 种子，防止新条目再以时间戳入库；
  80 条窗口滚动后种子会被裁掉，不要求它回来）。
- **H2 账序**：run_id 无重复；``exported_at`` 单调不减。
- **H3 双账按序后缀**（R152 改）：当前 history 的 ci 条目序列必须等于
  git bot 账本的**最新 N 条、同序**。R136 原判据是「集合恰等」，隐含
  「窗口未滚动」；窗口满 80 后 ``record`` 裁掉最旧条目，集合恰等会把
  正确账本判红。按序后缀仍双向发声音：history 每条都要有 bot 提交，
  bot 的最新 N 条也必须原样在 history 里。**浅检出下显式红**（附
  ``git fetch --unshallow`` 指引）——R136 同时给 backend /
  windows-backend 的 checkout 加了 ``fetch-depth: 0``，CI 里本判据是
  真的，不许降级成 skip。

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


def test_entry_shapes_and_optional_legacy_seed() -> None:
    """H1：ci 条目形状钉死；时间戳形状 run_id 至多 1 条且只能是第 1 条。"""
    entries = _entries()
    timestamp_shaped = [
        i for i, e in enumerate(entries)
        if not RUN_ID_RX.match(str(e.get("run_id", "")))
    ]
    assert len(timestamp_shaped) <= 1, (
        f"run_id 非 ci-形状的条目至多 1 条 legacy 种子，实际位于："
        f"{timestamp_shaped}（{[entries[i].get('run_id') for i in timestamp_shaped]}）"
    )
    if timestamp_shaped:
        assert timestamp_shaped == [0], (
            f"legacy 种子只能是第 1 条，实际位于 {timestamp_shaped}"
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


def _git_bot_run_ids_in_order() -> list[str]:
    """git bot 提交的 run id，按提交时间从旧到新（``--reverse``）。"""
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
        ["git", "log", "--reverse", "--format=%s"], cwd=REPO_ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    return re.findall(r"record CI run (\d+)", log)


def test_history_matches_git_bot_commits_bidirectionally() -> None:
    """H3：history 的 ci 条目 == bot 账本的**连续后缀**（R152 满窗口径）。

    R136 原判据是「集合恰等」——它隐含「窗口未滚动」。窗口满 80 后
    ``record`` 会裁掉最旧条目，当前 history 只是 bot 账本的尾部；集合
    恰等会从 R153 起误判。按序后缀仍然双向发声音：history 的每条 ci
    都必须在 bot 账本里，bot 的最新 N 条也必须原样、按序在 history 里。
    实测口径：唯一可能对不上 bot 的是第 1 条时间戳种子（H1 钉住「至多 1 条」，滚动后可能已被裁掉），
    对账按 **run_id 形状** 取序列，不按 source 标注。
    """
    entries = _entries()
    ci_ids = [
        str(e["run_id"])[3:]
        for e in entries
        if RUN_ID_RX.match(str(e.get("run_id", "")))
    ]
    assert ci_ids, "history 没有 ci- 形状条目——H3 空转"
    bot_ids = _git_bot_run_ids_in_order()
    assert len(ci_ids) <= len(bot_ids), (
        f"history 有 {len(ci_ids)} 条 ci 条目，git bot 提交只有 "
        f"{len(bot_ids)} 个——history 多出了没有第二份账的条目"
    )
    expected = bot_ids[-len(ci_ids):]
    if ci_ids != expected:
        missing = [run_id for run_id in expected if run_id not in set(ci_ids)]
        extra = [run_id for run_id in ci_ids if run_id not in set(expected)]
        mismatched = [
            (position + 1, actual, want)
            for position, (actual, want) in enumerate(zip(ci_ids, expected))
            if actual != want
        ][:5]
        raise AssertionError(
            "history 不是 bot 账本的连续后缀："
            f"缺 {missing[:5]}；多 {extra[:5]}；"
            f"错位（位置, history, bot）{mismatched}"
        )
