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

R47 §7-2 记过一个本脚本**结构上判不到**的失效：快照不会自动更新，旧数据自身
仍自洽（元数据与内容一致、失败率没恶化），于是闸门看着在工作，判的却是越来越
旧的数字。``--check-stale``（R48）补这一半：拿快照的 ``exported_at`` 与真实
``data/workflows`` 里最新一次 run 的时间比，滞后超过容忍天数即报过期（退出码 5）。

``--check-coverage``（R49）补另一半：``--check-stale`` 只判时间，判不到「新增了
一个 workflow 但快照里没有它」——那时快照可能仍然「尚新」，却已不代表真实覆盖面
（HANDOVER_ROUND48 §8-2）。覆盖度单独成退出码 6：它与 5 的处置不同（5 是重导
一次就好，6 还要看新工作流是不是真的进了样本）。

**``--check-stale`` / ``--check-coverage`` 刻意不接进 CI**：CI 检出里没有
``data/workflows``，接进去只会永远「无法判定」，那是又一个永远绿的防护。它们
是轮次收官动作，不是 CI 步骤。

用法（仓库根执行）::

    python scripts/check_live_snapshot_gate.py
    python scripts/check_live_snapshot_gate.py --margin 5   # 收紧余量
    python scripts/check_live_snapshot_gate.py --data-dir tests/fixtures/live_snapshot

    # 快照保鲜（轮次收官跑；真实数据落后快照超过 7 天即报过期）
    python scripts/check_live_snapshot_gate.py --check-stale
    python scripts/check_live_snapshot_gate.py --check-stale --max-lag-days 3

    # 快照覆盖度（轮次收官跑；真实跑过的工作流缺样本即报缺口）
    python scripts/check_live_snapshot_gate.py --check-coverage
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
EXIT_STALE = 5
EXIT_COVERAGE_GAP = 6


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


def _parse_ts(value: object) -> "datetime | None":
    """解析 ISO 时间串；无时区按 UTC 处理，解析不了给 None（不猜）。"""
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_real_run_time(workflows_dir: Path) -> "datetime | None":
    """真实 run 记录里最晚的时间戳（started_at 与 completed_at 取最大）。

    两者都要看：只读 ``completed_at`` 会漏掉正在进行中的新 run，而那个 run
    恰恰是「快照已经没覆盖到」的证据。B31 修复前 ``completed_at`` 恒空，
    历史数据里大量为 None，只读它等于对旧数据失明。
    """
    latest = None
    if not workflows_dir.is_dir():
        return None
    for wf_dir in sorted(workflows_dir.iterdir()):
        runs_dir = wf_dir / "runs"
        if not wf_dir.is_dir() or not runs_dir.is_dir():
            continue
        for run_file in runs_dir.glob("run-*.json"):
            try:
                run = json.loads(run_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key in ("started_at", "completed_at"):
                stamp = _parse_ts(run.get(key))
                if stamp is not None and (latest is None or stamp > latest):
                    latest = stamp
    return latest


def check_stale(data_dir: Path, source_dir: Path,
                max_lag_days: float) -> tuple[int, str]:
    """快照保鲜判定：真实数据比快照新出多少天。返回 (退出码, 说明)。

    三种「判不到」都单列，不挤进通过：元数据缺/坏（3）、真实数据缺（3）、
    真实数据全无可用时间戳（3）。过期是 5，与超阈（1）分开——「判了且不合格」
    与「样本过期了」需要不同处置。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判新鲜度：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    exported = _parse_ts(meta.get("exported_at"))
    if exported is None:
        return EXIT_NO_SAMPLE, (
            f"快照元数据缺 exported_at 或无法解析（{meta.get('exported_at')!r}），"
            "无法判新鲜度；重导一次即可补上")

    latest = latest_real_run_time(source_dir)
    if latest is None:
        return EXIT_NO_SAMPLE, (
            f"真实数据里没有可用时间戳（{source_dir}），无法判新鲜度。"
            "本机无 run 记录时这是预期结果，不是故障")

    lag_days = (latest - exported).total_seconds() / 86400.0
    if lag_days > max_lag_days:
        return EXIT_STALE, (
            f"快照已过期：导出时间 {exported.isoformat()}，真实数据最新 "
            f"{latest.isoformat()}，滞后 {lag_days:.1f} 天 > 容忍 {max_lag_days:.1f}"
            " 天。重导：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")
    return EXIT_OK, (
        f"快照尚新：导出 {exported.isoformat()}，真实数据最新 {latest.isoformat()}，"
        f"滞后 {lag_days:.1f} 天 ≤ 容忍 {max_lag_days:.1f} 天")


def _workflow_names_with_runs(root: Path) -> set[str]:
    """``root`` 下真正产生过 run 记录的工作流名集合。"""
    names: set[str] = set()
    if not root.is_dir():
        return names
    for wf_dir in root.iterdir():
        if not wf_dir.is_dir():
            continue
        runs_dir = wf_dir / "runs"
        if not runs_dir.is_dir():
            continue
        if any(runs_dir.glob("run-*.json")):
            names.add(wf_dir.name)
    return names


def check_coverage(data_dir: Path, source_dir: Path) -> tuple[int, str]:
    """快照覆盖度：真实数据里跑过的工作流，快照里是否都有样本。

    ``--check-stale``（R48）只看时间，判不到「新增了一个 workflow 但快照里没有
    它」——那种情况下快照可能仍然「尚新」，而它已经不再代表真实覆盖面
    （HANDOVER_ROUND48 §8-2）。这里补的正是那一问。

    为什么单独成码 6 而不并入 5：两者的处置**不同**。5 是「重导一次就好」，
    6 是「快照的 workflow 集合已经不完整，重导后还要看新工作流是不是真的进了
    样本」——并进 5 会让人对着一个只差一条 workflow 的快照去查导出脚本。
    两者都与 1（失败率不合格，要查供应商）不同，这是同一条纪律的第三次延伸。

    只判「真实有、快照没有」。反方向（快照里有、真实已删）不报：删掉的工作流
    留在快照里只是冗余样本，不影响判据的代表性。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判覆盖度：{meta_path}"

    snapshot_names = _workflow_names_with_runs(data_dir / "workflows")
    if not snapshot_names:
        return EXIT_NO_SAMPLE, (
            f"快照里没有任何带 run 记录的工作流（{data_dir / 'workflows'}）")

    real_names = _workflow_names_with_runs(source_dir)
    if not real_names:
        return EXIT_NO_SAMPLE, (
            f"真实数据里没有任何带 run 记录的工作流（{source_dir}），"
            "无法判覆盖度。本机无 run 记录时这是预期结果，不是故障")

    missing = sorted(real_names - snapshot_names)
    if missing:
        return EXIT_COVERAGE_GAP, (
            f"快照覆盖不全：真实数据有 {len(real_names)} 个工作流，快照缺 "
            f"{len(missing)} 个 {missing}。重导：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")
    return EXIT_OK, (
        f"快照覆盖完整：真实数据 {len(real_names)} 个工作流全部在快照内"
        f"（快照含 {len(snapshot_names)} 个）")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="快照根目录（含 workflows/ 与 snapshot-meta.json）；"
                             "缺省读 DETERMINFLOW_DATA_DIR，再缺省用入库快照路径")
    parser.add_argument("--margin", type=float, default=10.0,
                        help="阈值相对实测失败率的余量（百分比点，默认 10）")
    parser.add_argument("--check-stale", action="store_true",
                        help="改判快照新鲜度：真实数据比快照新多少天（不判失败率）")
    parser.add_argument("--check-coverage", action="store_true",
                        help="改判快照覆盖度：真实数据跑过的工作流是否都在快照内")
    parser.add_argument("--source", type=Path, default=None,
                        help="真实 run 记录根目录（默认 src.config.WORKFLOWS_DIR），"
                             "仅 --check-stale / --check-coverage 使用")
    parser.add_argument("--max-lag-days", type=float, default=7.0,
                        help="快照允许落后真实数据的天数（默认 7）")
    options = parser.parse_args()
    if options.margin < 0:
        parser.error("--margin 不能为负")
    if options.max_lag_days < 0:
        parser.error("--max-lag-days 不能为负")
    if options.check_stale and options.check_coverage:
        parser.error("--check-stale 与 --check-coverage 是两种判据，不能同时使用")

    if options.check_stale or options.check_coverage:
        source = options.source
        if source is None:
            from src.config import WORKFLOWS_DIR

            source = WORKFLOWS_DIR
        snapshot = options.data_dir or _default_data_dir()
        if options.check_coverage:
            code, message = check_coverage(snapshot, Path(source))
        else:
            code, message = check_stale(snapshot, Path(source), options.max_lag_days)
        print(f"[live-gate] {message}", file=sys.stderr)
        return code

    code, message = evaluate(options.data_dir or _default_data_dir(), options.margin)
    print(f"[live-gate] {message}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
