"""对入库真实快照判失败率闸门（R47）。

R46 的 CI 闸门 step 判的是 ``tests/fixtures/run_samples`` ——**固定**样本，
它保护的命题是「闸门与脚本不退化」，判不了「这批 run 的真实失败率」
（HANDOVER_ROUND46 §2.1 的「判据边界」原话）。本脚本补上真实数据面。

三条设计取舍，都是为了避免「又一个永远绿的防护」：

1. **阈值从快照自身算**，不写死。实测失败率 + 10 个百分点留余量。写死阈值
   会在快照重导后静默失准（数字对了才怪）。
2. **先校验元数据与内容一致**。``snapshot-meta.json`` 是导出时算的；若有人
   改了快照内容却没重导元数据，这里直接失败——否则闸门会拿旧阈值判新内容，
   看起来仍在工作，实际判的是别的数字。
3. **退出码沿用闸门语义**：0=通过，1=超阈，3=无样本。与
   ``provider_failure_profile.py`` 同一套，CI 日志里两种失败可分。

用法（仓库根执行）::

    python scripts/check_live_snapshot_gate.py
    python scripts/check_live_snapshot_gate.py --margin 5   # 收紧余量
    python scripts/check_live_snapshot_gate.py --data-dir tests/fixtures/live_snapshot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.workflow.run_profile import build_run_profile  # noqa: E402

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "live_snapshot"


def _default_data_dir() -> Path:
    """``DETERMINFLOW_DATA_DIR`` 指向 workflows 的上一层，所以快照根 = 它本身。

    CI 里该变量已指到快照根（闸门脚本也读它取 WORKFLOWS_DIR），两处口径一致；
    未设时回落到入库默认路径，本地直接跑也能命中。
    """
    import os

    override = os.environ.get("DETERMINFLOW_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DATA_DIR

EXIT_OK = 0
EXIT_GATE_TRIGGERED = 1
EXIT_NO_SAMPLE = 3
EXIT_META_DRIFT = 4


def recompute_totals(workflows_dir: Path) -> tuple[int, int]:
    """从快照内容复算 (attempts, failed)——与闸门脚本同一口径。"""
    attempts = failed = 0
    if not workflows_dir.is_dir():
        return 0, 0
    for wf_dir in sorted(workflows_dir.iterdir()):
        runs_dir = wf_dir / "runs"
        if not wf_dir.is_dir() or not runs_dir.is_dir():
            continue
        for run_file in sorted(runs_dir.glob("run-*.json")):
            try:
                run = json.loads(run_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            profile = build_run_profile(
                run.get("node_executions") or [],
                run_id=str(run.get("run_id") or run_file.stem),
                workflow_id=wf_dir.name,
                status=str(run.get("status", "")),
                started_at=run.get("started_at"),
                completed_at=run.get("completed_at"),
            )
            attempts += profile["totals"]["attempts"]
            failed += profile["totals"]["failed"]
    return attempts, failed


def evaluate(data_dir: Path, margin: float) -> tuple[int, str]:
    """返回 (退出码, 说明)。纯逻辑，便于测试注入临时目录。"""
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    recorded = meta.get("totals") or {}
    rec_attempts = int(recorded.get("attempts") or 0)
    rec_failed = int(recorded.get("failed") or 0)
    if rec_attempts <= 0:
        return EXIT_NO_SAMPLE, "快照元数据 attempts=0，真实数据面为空"

    actual_attempts, actual_failed = recompute_totals(data_dir / "workflows")
    if actual_attempts != rec_attempts or actual_failed != rec_failed:
        return EXIT_META_DRIFT, (
            f"快照内容与元数据不一致：元数据 {rec_failed}/{rec_attempts}，"
            f"内容复算 {actual_failed}/{actual_attempts}。"
            "改过快照就要重导：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")

    measured = rec_failed / rec_attempts * 100
    threshold = min(100.0, max(0.0, measured + margin))
    if measured > threshold:
        return EXIT_GATE_TRIGGERED, (
            f"失败率 {measured:.2f}% 超出阈值 {threshold:.1f}%"
            f"（{rec_attempts} 次尝试）")
    return EXIT_OK, (
        f"失败率 {measured:.2f}% 未超出阈值 {threshold:.1f}%"
        f"（{rec_attempts} 次尝试，余量 {margin:.1f} 个百分点）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="快照根目录（含 workflows/ 与 snapshot-meta.json）；"
                             "缺省读 DETERMINFLOW_DATA_DIR，再缺省用入库快照路径")
    parser.add_argument("--margin", type=float, default=10.0,
                        help="阈值相对实测失败率的余量（百分比点，默认 10）")
    options = parser.parse_args()
    if options.margin < 0:
        parser.error("--margin 不能为负")

    code, message = evaluate(options.data_dir or _default_data_dir(), options.margin)
    print(f"[live-gate] {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
