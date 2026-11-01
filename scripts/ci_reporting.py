"""CI 结果报告：step summary 与机读 JSON 的唯一实现（R98）。

写回脚本与 artifact 拉取脚本都需要「一行 summary + 一份 JSON，且写失败只
告警、不改判决」。同一事实写两处就会分裂（R80），所以集中在这里。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def default_summary_path() -> Path | None:
    raw = os.environ.get("GITHUB_STEP_SUMMARY")
    return Path(raw) if raw else None


def emit_summary(summary_path: Path | None, run_id: str, reason: str,
                 detail: str) -> None:
    """把本轮结果追加进 step summary；写不进去只告警。"""
    if summary_path is None:
        return
    line = f"- `{run_id}` — **{reason}**：{detail}\n"
    try:
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        print(f"step summary 写入失败（{summary_path}）：{exc}", file=sys.stderr)


def emit_result(result_path: Path | None, payload: dict) -> None:
    """把本轮结果写成机读 JSON；写不进去只告警。"""
    if result_path is None:
        return
    tmp = result_path.with_name(result_path.name + ".tmp")
    try:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        os.replace(tmp, result_path)
    except OSError as exc:
        print(f"结果工件写入失败（{result_path}）：{exc}", file=sys.stderr)
        try:
            tmp.unlink()
        except OSError:
            pass
