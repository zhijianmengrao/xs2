"""对入库真实快照判失败率闸门（R47）。

R46 的 CI 闸门 step 判的是 ``tests/fixtures/run_samples`` ——**固定**样本，
它保护的命题是「闸门与脚本不退化」，判不了「这批 run 的真实失败率」
（HANDOVER_ROUND46 §2.1 的「判据边界」原话）。本脚本补上真实数据面。

四条设计取舍，都是为了避免「又一个永远绿的防护」：

1. **阈值来自外部给定的政策上限**（``--fail-if-above PCT``，R57 修）。R47 的
   原始写法是「实测失败率 + margin 当阈值」，判据又是「实测 > 阈值」——而
   ``--margin`` 禁止为负，于是阈值恒 ≥ 实测，**任何数据都判不出超阈**（R57
   实测：20 次尝试全失败仍判退出 0）。阈值里含着被判的那个数，闸门就成了
   同义反复。修法是把阈值移出被测量的量：上限由调用方给（CI 里是一个写明数字
   的开关），精度那一半仍由快照自身算——``--check-sample-size`` 不写死任何
   常量，所以 R47 担心的「写死阈值在重导后静默失准」不成立：政策上限不随
   数据漂移，数据越过政策就该红，那正是它的用途。
2. **先校验元数据与内容一致**。``snapshot-meta.json`` 是导出时算的；若有人
   改了快照内容却没重导元数据，这里直接失败——否则闸门会拿旧阈值判新内容，
   看起来仍在工作，实际判的是别的数字。
3. **退出码沿用闸门语义**：0=通过，1=超阈，3=无样本。与
   ``provider_failure_profile.py`` 同一套，CI 日志里两种失败可分。R64 补了
   8=**判据算术失败、未作判定**——它必须与 1 分开，否则一次崩溃会被读成「失败率
   突破政策」（实测形状见 ``EXIT_NUMERIC_FAILURE``）。
4. **三分法**（R56 的判据形状沿用到这里）：95% 区间整体在上限之上才判
   ``exceeds``，整体在限内才判 ``normal``，横跨上限则 ``undetermined``——判不了
   既不冒充合格也不冒充不合格。``undetermined`` 不判失败：样本精度是另一件事，
   由 ``--check-sample-size`` 单独判（退出码 7），两处都红会让人对着一个只差
   精度的快照去查供应商。

R61 对 8% 做了首次校准（``docs/failure-ceiling-calibration.md``）。结论是维持，
但它该被读成**突破线**而不是健康线：n=255 时判 ``normal`` 的实际门槛是
k≤13（5.10%），14~28（5.49%~10.98%）判不了，k≥29（11.37%）才判超阈；真实
失败率恰为 8% 时 P(判 normal) 只有 4.9%——点估计落在上限上时上界必然高于
上限，任何样本量都如此。它也不是漂移探测器：2 倍基线 7.84% 的检出率只有
2.85%，50%/80% 功效分别要真实值到 11.25%/12.96%（漂移归
``--fail-on-regression``）。维持 8% 的三条依据：①全历史 16/297 的 95% 上界
8.07%，8% 是它的整数化；②上限压到 6.56% 及以下（当前快照上界）时当前数据
立刻判不了；③7% 时政策带与回归带在 n=255 下逐 k 相同（normal≤10 / exceeds≥26），
8% 是第一个让政策层有独立判决带的整数（隔 3 次失败）。改这个数字要重跑那份校准。

不给 ``--fail-if-above`` 时是**报告模式**：打印实测失败率与 95% 区间，退出 0，
并在说明里显式写明「未给上限，政策上限这一层只报告不判定」——静默当通过正是本轮修掉的
那个缺陷的另一种写法，不能靠沉默表达。

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

``--check-sample-size``（R51）与上面两个不同：它**只读快照自身**，不需要真实
数据面，所以能在 CI 检出里真判。它补的是 R49 §7-6 明确挂账的那一问——
``--check-coverage`` 只判集合差（哪个 workflow 缺样本），判不到「这个 workflow
的样本薄到看不出失败率」。两者判的是同一个方向的深浅两面：缺整个 workflow 是 6，
有 workflow 但样本不足以支撑判断是 7。退出码单列而不并入 6，原因是处置不同：
6 是「新工作流没进样本」，7 是「进了但太薄」——后者可能要调 ``--limit`` 重导。**CI 接的就是它**，见
``.github/workflows/ci.yml`` 的 ``Snapshot sample-size gate`` 一步。

用法（仓库根执行）::

    # 默认判定模式：阈值是外部给定的政策上限（百分比点，0..100）
    python scripts/check_live_snapshot_gate.py --fail-if-above 8
    # 只报告不判定：不给上限就打印实测值与 95% 区间（退出 0，不等于合格）
    python scripts/check_live_snapshot_gate.py
    python scripts/check_live_snapshot_gate.py --data-dir tests/fixtures/live_snapshot

    # 快照保鲜（轮次收官跑；真实数据落后快照超过 7 天即报过期）
    python scripts/check_live_snapshot_gate.py --check-stale
    python scripts/check_live_snapshot_gate.py --check-stale --max-lag-days 3

    # 快照覆盖度（轮次收官跑；真实跑过的工作流缺样本即报缺口）
    python scripts/check_live_snapshot_gate.py --check-coverage

    # 样本量厚度（CI 跑；只读快照自身，不需要真实数据面）
    python scripts/check_live_snapshot_gate.py --check-sample-size

    # 按 workflow 判失败率（R56；R58 起 CI 用 --fail-on-exceeds 做硬门槛）
    python scripts/check_live_snapshot_gate.py --check-per-workflow-rate
    python scripts/check_live_snapshot_gate.py --check-per-workflow-rate --fail-on-exceeds

    # 主闸门加判历史基线回归（R59；可与 --fail-if-above 并存）
    python scripts/check_live_snapshot_gate.py --fail-on-regression
    python scripts/check_live_snapshot_gate.py --fail-if-above 8 --fail-on-regression

    # 逐 workflow 判相对上一轮是否回归（R62；只读快照自身，CI 可跑）
    python scripts/check_live_snapshot_gate.py --check-per-workflow-regression

    # 复算逐 workflow 层的「提前量」（R67；只读，不作判定）
    python scripts/check_live_snapshot_gate.py --calibrate-lead-time

R58 补的是 ``undetermined`` 的**次级信号**：一份快照里判不了是正常的（样本薄），
但**连续多份快照都判不了**就不再是「这一轮样本薄」，而是「这个 workflow 的
真实数据量支撑不了逐 workflow 判决」。快照元数据的 ``history`` 块记录最近几次
导出的原始计数（``attempts/failed``，由导出脚本追加、封顶 5 轮），闸门据此
数出「连续 N 轮 undetermined」并以 ``UNDETERMINED_ROUND_STREAK`` 为界给出
重导提示。

历史放在快照元数据里、而不是一个单独的运行时状态文件，理由是 CI：CI 检出是
临时的，任何在 CI 里写下的状态都会在 job 结束时消失。跨轮状态必须随那份被
判的数据一起入库，否则「连续 3 轮」在 CI 里永远等于「1 轮」——那又是一个
写着「在看趋势」的恒绿防护。历史条目只用于数连续性，**不参与**漂移校验：
它们描述的是过去几轮各自的快照，拿它们跟当前内容比是拿错了尺。

R59 给主闸门补上**历史基线模式**（``--fail-on-regression``）。R57 只有政策
上限，它判的是「绝对失败率是否不可接受」；这一层判的是「相对上一轮是否显著
变坏」——一次从 2% 抬到 7% 的回归仍在 8% 上限之内，上限判不出来。两条判据
并存，退出码都是 1，所以说明里必须写清 **1 的来源**（政策突破 / 回归），否则
日志里分不清该查供应商还是查回归。

基线取快照 ``history`` 里的**上一轮**，不取多轮合并：相邻两次导出常常包含
同一批 run，把重叠样本当独立样本会伪造精度（区间假性收窄）。同一份数据里的
两轮仍有重叠，忽略重叠只会让区间偏宽——偏向「判不出回归」而不是「误报回归」，
这是刻意选的方向。基线本身太薄（``sample_size_margin_needed`` 超过回归余量）
或两轮 workflow 集合不同（覆盖变化，失败率不可比）时一律判 ``undetermined``，
不拿一个不可信的数字去比。

R62 把历史基线扩到**逐 workflow**（``--check-per-workflow-regression``）。合并
层判不出「一个 workflow 在变坏、被其余几个摊薄」：入库快照的 character 占
79/255，它涨到 16/79（20.3%）时全局才 9.41%，95% 下界 6.57% 仍低于回归阈值
6.92%——合并层要到 18/79（22.8%）才开口。逐 workflow 层在同一份数据上是
16/79 就判回归，**早 2 次失败**；mvp 上早 5 次（15/56 = 26.8% vs 20/56 =
35.7%）。这是它真实的增量，不是「更细所以更好」之类的空话。

它不是「每个 workflow 都判」。基线精度不够（95% 半宽 > margin）的 workflow
一律 ``undetermined``——拿 0/5（95% 上界 45 个百分点）当阈值，当前只要出现
一次失败就会被判回归，那是「向错方向的假红」。**可判集合与
``--check-per-workflow`` 判「精度达标」的那批完全重合**，两处共用
``sample_size_margin_needed``：各定一个门槛，迟早出现「诊断说够厚、回归说
判不了」的分裂。入库快照上可判的只有 2/9（character 2/79、mvp 4/56），且两轮
计数完全相同——报告里逐字给出 ``unchanged`` 计数，把「自比自」写成文字，不让
它被读成质量结论。判定力由 ``live_snapshot_exceeds`` 反向验证：wf-bad 从
0/40 跳到 40/40 必须判 1。``undetermined`` 与「可判 0 个」都不判失败，但都要
在输出里写明「本步没有判定力」，否则又是一个写着在看回归的恒绿步骤。

R67 把 R62 §2 的「提前量」表变成可复算命令（``--calibrate-lead-time``），并
顺带纠正那一节里一句**会误导**的话：「与合并层同一把尺」。两层用**不同的**
阈值增量——逐 workflow 是 ``--margin``（默认 10），合并层是
``--regression-margin``（默认 3）——所以「早 2 次」是跨阈值量出来的，不是
「同样严格之下早 2 次」。这个差值不是随手取的：逐 workflow 的阈值**必须 ≥
基线自身的 95% 半宽**，否则「两轮计数完全相同」也会被判 ``undetermined``。
入库快照上 character 的 95% 上界 7.75% 高于 5.53%（= 2.53% + 3），mvp 的
14.2% 高于 10.14%——真按 +3 判，这两个可判的 workflow 会从「没有回归」整批
变成「判不了」。把阈值压到 +3 换来的提前量是 9 次（16→9 / 15→11），代价是
这一层在真实数据上**永远说不出 normal**。R67 的新增用例把这条不变量钉住：
可判 + 计数不变 ⇒ 必须判 ``normal``。
"""

from __future__ import annotations

import argparse
import json
import math
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
EXIT_THIN_SAMPLE = 7
# 判据自己算不下去（R64）。必须与 1 分开：1 的含义是「判了，结论是不合格」，
# 处置是查数据/供应商；8 的含义是「**没判**，算术失败」，处置是修判据。
#
# 为什么这不是假想的码：R64 实测 CP 精确界在 n≈1030、p≈0.5 时抛 OverflowError，
# 而 ``main`` 里没有任何捕获——进程按 Python 默认以 **1** 退出，与政策超阈
# 完全同码，日志里只差一行 traceback。CI 里两种处置会互相冒充：看着是「失败率
# 突破政策」，实际是判据崩了。修了溢出之后这条路径不再出现，但「未捕获异常 =
# 不合格」这个形状还在，所以边界上仍然要有一个只属于它的码。
EXIT_NUMERIC_FAILURE = 8

# 连续多少轮（含当前这一轮）都判 ``undetermined`` 才提示重导（R58，用户拍定 3）。
# 它不是判据：提示不改变任何退出码。定成常量而不是开关，是因为「连续几轮才算
# 长期」在数据积累到能回答之前只能先取一个值；多一个参数就多一个要在 CI 与
# 测试里同步的口径。
UNDETERMINED_ROUND_STREAK = 3

# 回归判据的默认余量（百分点，R59）：当前失败率相对历史基线高出这么多、且 95%
# 区间下界仍在阈值之上，才判回归。取 3 的依据是入库快照当前的估计噪声——
# 10/255 的精确界半宽是 2.64 个百分点，再小就会被重导噪声触发。它**不是**
# ``--margin``（精度余量）的别名：后者问「估计够不够准」，这里问「变化够不够
# 大」，两个量混用一个开关就会出现「调精度顺手改了判据」的暗耦合。
#
# 3 也让回归判据有真实的判定窗口：入库快照基线 3.92% + 3 = 阈值 6.92%，低于
# 8% 政策上限——约 10% 的失败率会先触发回归，11.4% 才触发上限。若余量取 10
# （per-workflow 诊断的历史默认值），阈值 13.92% 恒高于上限，回归这一层就永远
# 轮不到它开口，等于一个写着「在看回归」的恒绿步骤。
REGRESSION_MARGIN = 3.0

# 两个 ``--check-*`` 判据的默认容忍量（R69 起具名，原先只写在 ``main()`` 里）。
# 具名的理由与 ``REGRESSION_MARGIN`` 相同：登记页把它们写成「10 个百分点」与
# 「7 天」，而翻转点用例要用**同一个**数去构造边界两侧——两处各写一份字面量，
# 改了默认值之后登记页会继续原样撒谎。
DEFAULT_MARGIN = 10.0          # --margin：精度余量 / 逐 workflow 变化阈值
DEFAULT_MAX_LAG_DAYS = 7.0     # --max-lag-days：快照允许滞后的天数


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


def evaluate(data_dir: Path, ceiling: float | None = None,
             regression_margin: float | None = None) -> tuple[int, str]:
    """返回 (退出码, 说明)。纯逻辑，便于测试注入临时目录。

    ``ceiling`` 是外部给定的失败率政策上限（百分点），判决算术见
    ``_ceiling_verdict``。``None`` 表示报告模式：仍然判漂移（4）与无样本（3），
    但不把「调用方没给上限」沉默成通过——说明里会写明本轮没有判定。

    ``regression_margin`` 非 ``None`` 时加判**历史基线回归**（R59）：当前失败率
    相对快照 ``history`` 上一轮（且 workflow 集合相同）的合并失败率高出这么多，
    且 95% 区间下界仍在阈值之上，才判回归。``None`` 表示不判回归，说明里同样
    写明这一层没有判定——「没给开关」与「判了通过」是两件事。
    """
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

    policy_verdict, policy_detail = _ceiling_verdict(
        rec_attempts, rec_failed, ceiling)
    parts = [policy_detail]
    regression_verdict = "report"
    if regression_margin is not None:
        # 与 ``snapshot_rounds`` 同一口径：当前轮取快照**内容**复算的分组计数，
        # 不取元数据里的一句话。全局漂移校验只比总数，把一次失败从 A 挪到 B
        # 它看不出来，而那种改动恰好会改变「当前这一轮」的身份。
        current = recompute_per_workflow(data_dir / "workflows")
        baseline, invalid_history, note = historical_baseline(meta, current)
        if baseline is None:
            regression_verdict = "undetermined"
            reg_detail = f"判不了回归：{note}"
        else:
            baseline_rate = baseline["failed"] / baseline["attempts"] * 100.0
            regression_verdict, reg_detail = _baseline_verdict(
                rec_attempts, rec_failed,
                baseline["attempts"], baseline["failed"], regression_margin)
            reg_detail = f"{note}；{reg_detail}"
            if ceiling is not None and baseline_rate + regression_margin >= ceiling:
                # 配置层就能看出这一层不会先开口。不报的话，日志里永远是政策
                # 上限先红，而回归判据看起来「在工作」——那是恒绿防护的另一种
                # 形状（永远被别的判据挡在前面）。
                reg_detail += (
                    f"。注意：基线 {baseline_rate:.2f}% + 回归余量 "
                    f"{regression_margin:g} ≥ 政策上限 {ceiling:g}%，"
                    "回归判据不会先于政策上限触发")
        if invalid_history:
            reg_detail += (
                f"（另有 {invalid_history} 条历史形状无效已跳过，"
                "基线可能不是紧邻的一轮）")
        parts.append(f"[历史基线回归] {reg_detail}")
    else:
        parts.append(
            "[历史基线回归] 未给 --fail-on-regression，本步不判回归"
            "（退出 0 不代表没有回归）")

    sources: list[str] = []
    if policy_verdict == "exceeds":
        sources.append("政策突破")
    if regression_verdict == "exceeds":
        sources.append("回归")
    if sources:
        # 两条判据都退出 1，日志里必须能分清是哪一个——否则「查供应商」与
        # 「查回归」两种处置会互相冒充。
        parts.append("退出码 1 的来源：" + "；".join(sources))
    elif ceiling is not None or regression_margin is not None:
        parts.append("退出码 1 的来源：无（已启用的判据都没有判失败）")

    return (EXIT_GATE_TRIGGERED if sources else EXIT_OK), "。".join(parts)


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


# 样本量的判据不是「attempts ≥ 某个数」这类经验阈值，而是问一个更窄、更诚实的
# 问题：**这份快照的失败率估计，精度够不够支撑闸门拿它当基线？**
#
# 闸门（``evaluate``）用「实测失败率 + margin 个百分点」当阈值。如果快照只有
# 14 次尝试、1 次失败，实测 7.1% 也只是一个粗估——重导一次就可能变 0% 或 21%，
# 阈值跟着漂。样本量判据要抓的正是这件事，所以它判的是**估计量的精度**，
# 与「有多少条 run」无关：一次 run 里有 50 次尝试，精度并不比 5 次 run 共 10 次
# 尝试差。
#
# 两种情形分开判，因为「有失败」与「零失败」的估计量形状不同：
#
# - 有失败：用正态近似的 95% 置信区间半宽 ``1.96 * sqrt(p(1-p)/n)``。要求它
#   不超过闸门余量 ``margin``——也就是「取样误差不该大到把 margin 吃干净」。
# - 零失败：比例的点估计恒为 0，正态近似退化（半宽恒 0，永远合格）。这正是
#   「永远绿」的陷阱：2 次尝试 0 失败也会判合格，而零失败的 95% 上界其实是
#   ``1 - 0.05**(1/n)``，n=2 时高达 78%。所以零失败时要求**单侧上界** ≤ margin。
# - 全部失败（R53 补）：``p=1`` 时 ``p(1-p)=0``，正态近似同样退化成半宽 0——
#   这零失败那条的镜像，之前漏了。一个「每次尝试都失败」的快照会在样本量判据
#   下判「样本足够」，而它恰好是最需要被看见的运维状况。这里要求**单侧下界到
#   1 的距离** ``1 - 0.05**(1/n)`` ≤ margin，与零失败那条完全对称。
#
# 第三次修同一个坑（R52 §4 的 ``trend`` 对全失败序列判 ``stable`` 是同一家族
# 的另一个形状）说明：**比例类判据的退化点在两端，只补一端就会留下另一个
# 永远绿的角**。
#
# 阈值因此没有常量：它完全由快照自身的 ``attempts/failed`` 与 margin 决定，
# 重导后自动跟着变，不存在「数字对了才怪」的失准。
# 第三种形状（R55 补）：``0 < p < 1`` 的中段原来用正态近似 ``1.96*sqrt(p(1-p)/n)``，
# 两端用 Clopper-Pearson。三条式子拼在一起会在 ``p`` 从 0 跳到 ``1/n`` 处留下一个
# **方向错误**的台阶：n=10 时零失败需 25.89 个百分点，一次失败反而只要 18.59——
# 「多了一次失败」让样本显得更可信。那不是保守与否的问题，是判据在说反话，它会让
# 「刚出现失败」的样本比「零失败」的样本更容易过闸门。
#
# 修法是**全线用同一个精确界**：Clopper-Pearson 的单侧界可以写成二项分布的精确
# 分位数求解（下面 ``_cp_bounds``），两端恰好有闭式 ``1 - 0.05**(1/n)``——这正是
# 那个闭式的来历，不是另一个估计。于是三条式子合并成一条，台阶消失，且整段
# 对 ``k`` 单调（失败越多要求越厚），不会出现「说反话」的形状。
#
# 代价（如实记录）：区间比正态近似宽，因此**已经够厚的快照可能被判薄**。实测
# 入库快照全局 10/255：2.38 → 2.64 个百分点，仍远小于 margin=10，全局闸门不受
# 影响；per-workflow 诊断里 build（9.81→12.76）与 post-hoc（7.99→14.12）会从
# 「达标」变「不达标」——但那一块本就恒退出 0（R54 §1），变的是诊断文字不是结论。
Z_95 = 1.959963984540054  # 双侧 95% 正态分位数（保留：外部测试仍引用它）

# 二分求解的迭代次数：区间 [0,1] 上 80 次 → 约 1e-24 的分辨率，远超所需的
# 1e-4 个百分点精度。不用 scipy：CI 环境未装，判据不该依赖可选包。
_CP_BISECTION_STEPS = 80


def _binomial_cdf_le(attempts: int, k: int, p: float) -> float:
    """``P(X <= k)``，X ~ Binomial(attempts, p)，**整个求和在对数空间做**（R64）。

    为什么不能直接按 pmf 求和：``math.comb(attempts, i)`` 是 Python 大整数，
    一旦与浮点相乘就要转成 double——``comb(1030, 515)`` 已经是 1e308 量级，
    转 float 直接抛 ``OverflowError``。这个边界**不是一个样本量数字，而是一条
    （样本量 × 失败率）的曲线**，实测：失败率 50%/75%/90% 从 **1030** 起溢出、
    25% 从 1270、10% 从 2200、5% 从 3600、本项目当前的 3.92% 形状要 **4317**。
    R61 记的「n=4000 时 4% 形状仍可算」是对的（那条形状的边界就是 4317），
    R62 把它抄成了「4000+ 才需要处理」——于是漏掉了曲线的另一半：**最小值在
    1030，而它出现在失败率很高的一端**，也就是最需要判据说得出话的时候。修在
    现在而不是等到 4000 次尝试，理由就是这条曲线，不是那个单一数字。

    也不能只把 ``comb`` 换成 ``lgamma``：``q ** (attempts - i)`` 在 n 上千时
    会下溢到 0.0（0.5**2000 远小于最小正规 double），于是「不抛异常」变成
    「静默返回 0」——一个恒等于 0 的 CDF 会让二分把上界钉在 0，判据比崩溃更
    安静地错。所以乘法的每一步都取对数：``comb``、``p**i``、``q**(n-i)`` 各自
    的对数相加，再逐项 ``exp`` 回来累加。

    没有 max-shift：每一项都是概率，对数 ≤ 0，``exp`` 回来 ≤ 1，累加不可能
    溢出；下溢只出现在真实概率远小于 1e-308 的位置，那里返回 0 就是正确舍入
    （不是算术失败）。变异验证里把缩放加回去，153 条用例全绿、与精确有理数的
    误差仍在 1e-15 量级——缩放保护的是一个这里不存在的失效模式。少一层机制，
    就少一处将来会被误以为「必须保留」的代码。

    单一路径，不按 n 分「小 n 直算 / 大 n 换算法」：R55 的教训是两套式子迟早
    对同一个量给出两个答案（那一轮就是正态近似与精确界在 p 从 0 跳到 1/n 处
    互相打架）。这里一份式子跑全区间，代价只是 n 上的线性循环——n=10000 时
    单次 CDF 实测 0.7ms，而一次 ``_cp_bounds`` 是 160 次，仍不到 0.2s。

    精度：对 ``Fraction`` 精确值的最大绝对误差 4.4e-15（n≤80 全 k）；与旧直接
    求和在双方都不溢出的 n≤1029 上最大差 2.6e-12（2268 组）——判决与两位小数
    的显示值都不变（有测试钉住）。事故形状（崩溃退出 1 与「政策超阈」同码）见
    ``EXIT_NUMERIC_FAILURE``。
    """
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0 if k < attempts else 1.0
    k = min(k, attempts)
    if k < 0:
        return 0.0
    # log1p 而不是 log(1 - p)：p 很小时 1 - p 会丢掉有效位，而这里正需要它。
    log_p = math.log(p)
    log_q = math.log1p(-p)
    # 第 0 项的对数，以及逐项累加（每一项都是概率，见 docstring：不需要缩放）。
    log_term = attempts * log_q
    total = math.exp(log_term)
    for i in range(1, k + 1):
        # pmf 的相邻比：(n-i+1)/i * p/q，取对数后逐项累加。
        log_term += (math.log(attempts - i + 1) - math.log(i)
                     + log_p - log_q)
        total += math.exp(log_term)
    return total


def _cp_bounds(attempts: int, failed: int) -> tuple[float, float]:
    """Clopper-Pearson 的 95% 单侧界 ``(下界, 上界)``。

    上界是满足 ``P(X <= failed) = 0.05`` 的那个 p，下界是满足
    ``P(X >= failed) = 0.05``（即 ``P(X <= failed-1) = 0.95``）的那个 p。
    两端恰好等于闭式 ``1 - 0.05**(1/n)`` 到 0/1 的距离——闭式不是另一个估计，
    就是这个精确界在 ``failed`` 取 0 或 n 时的解析解。
    """
    if failed <= 0:
        lower = 0.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(_CP_BISECTION_STEPS):
            mid = (lo + hi) / 2
            if 1.0 - _binomial_cdf_le(attempts, failed - 1, mid) < 0.05:
                lo = mid
            else:
                hi = mid
        lower = (lo + hi) / 2
    if failed >= attempts:
        upper = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(_CP_BISECTION_STEPS):
            mid = (lo + hi) / 2
            if _binomial_cdf_le(attempts, failed, mid) > 0.05:
                lo = mid
            else:
                hi = mid
        upper = (lo + hi) / 2
    return lower, upper


def sample_size_margin_needed(attempts: int, failed: int) -> float | None:
    """这段样本的失败率估计「需要多宽的余量」才可信（百分点）。

    返回的是**必须 ≤ margin 的那个量**：Clopper-Pearson 95% 单侧界到点估计
    ``failed/attempts`` 的最大距离。三种形状（零失败 / 全部失败 / 中间）用的是
    **同一个**精确界，只是两端可以走闭式快路径（R55 合并，见上方注释）:

    - ``p == 0`` 或 ``p == 1``：闭式 ``1 - 0.05**(1/n)``。它与精确界在两端
      完全相等（有测试钉住），用闭式是为了不为一个能写成解析式的值做二分。
    - ``0 < p < 1``：两侧精确界里的较大者。

    单独抽成函数是为了让**导出脚本**能复用同一份算术
    （``scripts/export_run_samples.py`` 用它判「CI 反向验证还能不能触发退出码
    7」）。两处各写一份公式，迟早出现「导出说没事、CI 说太薄」的分裂。
    """
    if attempts <= 0 or failed < 0 or failed > attempts:
        return None
    p_hat = failed / attempts
    if failed == 0 or failed == attempts:
        return (1 - 0.05 ** (1.0 / attempts)) * 100
    lower, upper = _cp_bounds(attempts, failed)
    return max(upper - p_hat, p_hat - lower) * 100


def _failure_rate_precision(attempts: int, failed: int,
                            margin_pct: float) -> tuple[bool, str]:
    """样本量是否足以支撑闸门用这个失败率当基线。返回 (是否足够, 说明)。"""
    if attempts <= 0:
        return False, "attempts=0"
    needed = sample_size_margin_needed(attempts, failed)
    if needed is None:
        return False, f"样本形状无效（failed={failed}, attempts={attempts}）"
    ok = needed <= margin_pct
    if failed == 0:
        detail = (
            f"零失败时 95% 上界 {needed:.2f} 个百分点"
            f"{'≤' if ok else '>'} 余量 {margin_pct:.1f}（n={attempts}）")
    elif failed == attempts:
        detail = (
            f"全部失败时到 100% 的 95% 单侧距离 {needed:.2f} 个百分点"
            f"{'≤' if ok else '>'} 余量 {margin_pct:.1f}（n={attempts}）")
    else:
        detail = (
            f"失败率 {failed / attempts * 100:.2f}% 的 95% 半宽 {needed:.2f} 个百分点"
            f"{'≤' if ok else '>'} 余量 {margin_pct:.1f}（n={attempts}, 失败 {failed}）")
    if not ok and margin_pct > 0:
        # 所需样本量只在判不合格时给：判合格时它只是一个无关的门槛数字。
        detail += (
            f"，达到余量需要约 "
            f"{math.ceil(math.log(0.05) / math.log(1 - margin_pct / 100))} 次尝试")
    return ok, detail


def check_sample_size(data_dir: Path, margin: float) -> tuple[int, str]:
    """快照本身的样本厚度是否足以支撑失败率判定（R51）。

    与 ``--check-stale`` / ``--check-coverage`` 的根本差别：**它不读真实数据面**，
    只读快照内容与它自己的元数据。因此它能在 CI 检出里真判——那条「CI 里没有
    ``data/workflows``，接进去只会永远无法判定」的限制对它不成立。

    为什么单列退出码 7 而不并入 1（超阈）或 6（覆盖缺口）：
    - 1 是「判了且失败率太高」，处置是查供应商；
    - 6 是「某个工作流整个没进样本」，处置是重导并确认新工作流确实该进；
    - 7 是「样本进来了但太薄，失败率估计不可靠」，处置是调 ``--limit`` 重导
     更多 run。三者混在一起会让人对着一个只差精度的快照去查供应商。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判样本量：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    recorded = meta.get("totals") or {}
    attempts = int(recorded.get("attempts") or 0)
    failed = int(recorded.get("failed") or 0)
    if attempts <= 0:
        return EXIT_NO_SAMPLE, "快照元数据 attempts=0，没有可判的样本量"

    # 与 ``evaluate`` 同一条纪律：内容必须与元数据复算一致，否则判的是别的数字。
    actual_attempts, actual_failed = recompute_totals(data_dir / "workflows")
    if (actual_attempts, actual_failed) != (attempts, failed):
        return EXIT_META_DRIFT, (
            f"快照内容与元数据不一致：元数据 {failed}/{attempts}，"
            f"内容复算 {actual_failed}/{actual_attempts}。改过快照就要重导")

    ok, detail = _failure_rate_precision(attempts, failed, margin)
    if not ok:
        return EXIT_THIN_SAMPLE, (
            f"快照样本太薄，失败率估计不足以当闸门基线：{detail}。"
            "重导更多 run：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 5")
    return EXIT_OK, f"快照样本量足够支撑失败率判定：{detail}"


def recompute_per_workflow(workflows_dir: Path) -> dict[str, dict]:
    """按 workflow 复算 ``(runs, attempts, failed)``——``recompute_totals`` 的分组版。

    为什么需要分组复算而不是只信全局合计：``recompute_totals`` 只比总数。
    一次「把 A 工作流的一次失败改成 B 工作流的」改动不会改变全局 attempts/failed，
    于是全局漂移校验通过，而 ``snapshot-meta.json`` 的 ``per_workflow`` 块已经
    在说谎。R54 补的正是这一层（见 ``check_per_workflow``）。

    坏 JSON 与读失败一律跳过，与 ``recompute_totals`` 同一取舍。
    """
    buckets: dict[str, dict] = {}
    if not workflows_dir.is_dir():
        return buckets
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
            bucket = buckets.setdefault(
                wf_dir.name, {"runs": 0, "attempts": 0, "failed": 0})
            bucket["runs"] += 1
            bucket["attempts"] += profile["totals"]["attempts"]
            bucket["failed"] += profile["totals"]["failed"]
    return buckets


def _per_workflow_drift(recorded: dict, actual: dict[str, dict]) -> list[str]:
    """``per_workflow`` 元数据与内容复算的差集（空列表=一致）。

    三条判据（``check_per_workflow`` / ``check_per_workflow_rate`` /
    ``check_per_workflow_regression``）共用这一份检查：三处各写一份，迟早
    出现「这条判据信元数据、那条信内容」的分裂——而这一层的全部意义就是
    别拿一句写在元数据里的话当数据。
    """
    drifts: list[str] = []
    for name in sorted(set(recorded) | set(actual)):
        rec = recorded.get(name) or {}
        act = actual.get(name)
        if act is None:
            drifts.append(f"{name}: 元数据有、内容无")
            continue
        rec_key = (int(rec.get("runs") or 0), int(rec.get("attempts") or 0),
                   int(rec.get("failed") or 0))
        act_key = (act["runs"], act["attempts"], act["failed"])
        if rec_key != act_key:
            drifts.append(
                f"{name}: 元数据 runs/attempts/failed={rec_key}，"
                f"内容复算={act_key}")
    return drifts


def _drift_message(drifts: list[str]) -> str:
    """漂移差集 → 统一说明（三条判据的退出码 4 文案必须是同一句）。"""
    return (
        "per-workflow 元数据与内容不一致（全局合计可能仍然相等，所以全局校验"
        "看不出来）：" + "；".join(drifts) +
        "。重导：python scripts/export_run_samples.py "
        "--dest tests/fixtures/live_snapshot --limit 2")


def check_per_workflow(data_dir: Path, margin: float) -> tuple[int, str]:
    """按 workflow 分别判「失败率估计精度够不够」（R54）。

    补的是 R51 §12-2 挂账的那一问：全局厚度合格时，单个 workflow 可能薄到
    看不出失败率，而全局判据对它完全失明（全局 255 次尝试掩盖了某个只有 5 次
    尝试的 workflow）。

    **它判的不是「任一 workflow 太薄就失败」**。这样做会得到一个恒红的步骤：
    真实快照里 ``xs2-novel-flywheel-export`` 只有 5 次尝试、零失败，零失败时
    95% 上界高达 45 个百分点，而要把它压到 margin=10 需要 29 次尝试——真实数据
    里那个 workflow 总共只有 10 个 run，物理上补不到。把「补不到的东西」做成
    门槛，等于把一个永远红的步骤冒充成防护，这与 R45-R53 反复批评的「永远绿
    的防护」是同一个错误的两面。

    所以本函数有两件事，只有第一件能红：

    1. **``per_workflow`` 元数据必须与内容一致**（不做就无法判 2）→ 不一致时
       退出码 4（``EXIT_META_DRIFT``），与全局漂移同一处置：重导。
       这是比全局校验更严的一层：把一次失败从 A 工作流挪到 B 工作流，全局
       attempts/failed 分毫不动，全局校验通过，而 per-workflow 元数据已经在说谎。
    2. **逐 workflow 报告精度**，薄的那些列出来，说明「这些 workflow 级的失败率
       不可信」，全局闸门不受影响（闸门用的是全局合计当基线）。这一部分恒退出 0
       ——它是诊断信息，不是判据。叫它判据就会变成第二个恒绿/恒红的假防护。

    真要按 workflow 判失败率，得先让闸门本身改成 per-workflow 基线，那是另一
    次改动（HANDOVER_ROUND53 §12-3 明确列为候选而非本轮范围）。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判 per-workflow 样本量：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    recorded = meta.get("per_workflow") or {}
    if not isinstance(recorded, dict) or not recorded:
        return EXIT_NO_SAMPLE, (
            "快照元数据缺 per_workflow 块，无法判 per-workflow 样本量。"
            "重导一次即可补上：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")

    actual = recompute_per_workflow(data_dir / "workflows")
    if not actual:
        return EXIT_NO_SAMPLE, (
            f"快照里没有任何带 run 记录的工作流（{data_dir / 'workflows'}）")

    drifts = _per_workflow_drift(recorded, actual)
    if drifts:
        return EXIT_META_DRIFT, _drift_message(drifts)

    thin: list[str] = []
    thick: list[str] = []
    for name in sorted(actual):
        bucket = actual[name]
        needed = sample_size_margin_needed(bucket["attempts"], bucket["failed"])
        if needed is None:
            thin.append(f"{name}（样本形状无效：{bucket['failed']}/{bucket['attempts']}）")
            continue
        if needed <= margin:
            thick.append(f"{name}（{needed:.2f} ≤ {margin:g}）")
        else:
            thin.append(
                f"{name}（需 {needed:.2f} > {margin:g}，"
                f"n={bucket['attempts']}, 失败 {bucket['failed']}）")

    summary = (f"per-workflow 样本量：{len(thick)} 个 workflow 的失败率估计"
               f"精度达标，{len(thin)} 个不达标")
    if thin:
        summary += (
            "。不达标的这些 workflow **不该**被当作逐 workflow 的失败率基线"
            "（全局闸门用全局合计，不受影响）：" + "；".join(thin))
    if thick:
        summary += "。达标的：" + "；".join(thick)
    return EXIT_OK, summary


def per_workflow_baselines(buckets: dict[str, dict]) -> dict[str, float | None]:
    """每个 workflow 的**留一法基线税率**（百分点），不含它自己（R56）。

    为什么不能用全局合计当基线——这是本轮最重要的一处设计取舍，理由与
    ``evaluate`` 那条自指阈值是同一个错误的两个实例：

    全局合计 ``failed_all / attempts_all`` 里**包含了被判的那个 workflow 自己**。
    一个 workflow 全挂时，它既抬高了自己的观测失败率，也同时抬高了拿它比的
    那条基线，两者一起涨，于是「比自己所在的总体的平均高」这个条件天然难以成立
    ——**最该被看见的那一条，恰恰是它自己把自己藏起来的那一条**。留一法把自
    己那份从基线里扣掉，两者才可比。

    留一法在数学上也正是这个问题该用的估计量：问的是「这个 workflow 的失效率
    是否高于**其余** workflow 的合并失效率」，其余部分正是 ``(F - k) / (A - n)``。

    返回 ``None`` 当且仅当其余 workflow 一次尝试都没有（只剩一个 workflow 的
    快照），此时基线无从计算，调用方须把它报成「无法判定」而不是拿 0 当基线。
    """
    total_attempts = sum(int(b.get("attempts") or 0) for b in buckets.values())
    total_failed = sum(int(b.get("failed") or 0) for b in buckets.values())
    baselines: dict[str, float | None] = {}
    for name, bucket in buckets.items():
        rest_attempts = total_attempts - int(bucket.get("attempts") or 0)
        rest_failed = total_failed - int(bucket.get("failed") or 0)
        baselines[name] = (rest_failed / rest_attempts * 100.0
                           if rest_attempts > 0 else None)
    return baselines


def _cp_interval(attempts: int, failed: int) -> tuple[float, float]:
    """Clopper-Pearson 95% 单侧界 ``(下界, 上界)``，单位百分点，两端走闭式。

    主闸门与 per-workflow 判决共用这一份区间：两处各写一份算术，迟早出现
    「这边说超、那边说不超」（R56 §4 的纪律）。两端用闭式是为了不为一个能写成
    解析式的值做二分——它与 ``_cp_bounds`` 在两端完全相等（有测试钉住）。
    """
    if attempts <= 0:
        return 0.0, 100.0
    if failed <= 0:
        return 0.0, (1 - 0.05 ** (1.0 / attempts)) * 100
    if failed >= attempts:
        return 0.05 ** (1.0 / attempts) * 100, 100.0
    lower, upper = _cp_bounds(attempts, failed)
    return lower * 100.0, upper * 100.0


def _verdict_of_interval(lower_pct: float, upper_pct: float,
                         threshold_pct: float) -> str:
    """区间与阈值的关系 → ``exceeds`` / ``normal`` / ``undetermined``。

    三分法本身（R56）：整个区间在阈值之上才敢说超，整个区间在阈值之内才敢说
    正常，横跨则判不了。用下界而不是点估计，因为它抓的是一个具体命题——
    「真实失败率高于阈值」——点估计判它等于「样本越小越容易被判坏」。
    """
    if lower_pct > threshold_pct:
        return "exceeds"
    if upper_pct <= threshold_pct:
        return "normal"
    return "undetermined"


def _rate_verdict(attempts: int, failed: int, baseline_pct: float,
                  margin_pct: float) -> tuple[str, str]:
    """单个 workflow 相对基线的判决：``exceeds`` / ``normal`` / ``undetermined``。

    三分法而不是二分的过／不过，是这份快照的实测逼出来的（R56）：真实快照 9 个
    workflow 里，除 character 外每一个的 95% 区间都横跨阈值——区间 [0%, 45%] 与
    阈值 14% 的关系不是「合格」也不是「不合格」，是**这份样本不足以回答**。
    强行二分只有两个结果：恒红（把「判不了」当「不合格」）或恒绿（把「判不了」
    当「合格」），两者都是历轮反复批评的假防护。

    ``undetermined`` 因此是一等判决，不是失败也不是通过的别名。它的处置与
    两者都不同：调大 ``--limit`` 重导更多 run，而不是去查供应商（1 号退出码的
    处置）或确认新 workflow 该不该进样本（6 号）。

    判定用**单侧**精确界，与 ``sample_size_margin_needed`` 同一把尺：

    - ``exceeds``：95% 下界 > 基线 + margin。整个区间都在阈值之上，才敢说超。
    - ``normal``：95% 上界 ≤ 基线 + margin。整个区间都在阈值之内，才敢说正常。
    - 其余：区间横跨阈值 → ``undetermined``。
    """
    if attempts <= 0:
        return "undetermined", "attempts=0，无观测"
    threshold = baseline_pct + margin_pct
    p_hat = failed / attempts * 100.0
    lower, upper = _cp_interval(attempts, failed)
    detail = (f"失败率 {p_hat:.2f}%（n={attempts}, 失败 {failed}），"
              f"95% 区间 [{lower:.2f}%, {upper:.2f}%]，"
              f"基线 {baseline_pct:.2f}% + 余量 {margin_pct:g} = 阈值 {threshold:.2f}%")
    return _verdict_of_interval(lower, upper, threshold), detail


def _ceiling_verdict(attempts: int, failed: int,
                     ceiling_pct: float | None) -> tuple[str, str]:
    """主闸门对外部政策上限的三分判决：``exceeds`` / ``normal`` / ``undetermined``。

    这是 R57 修的缺陷的正身。此前 ``evaluate`` 用 ``measured + margin`` 当阈值，
    判据再问 ``measured > threshold``；``--margin`` 禁止为负，阈值因此恒 ≥ 实测，
    **任何数据都判不出超阈**——闸门看着在工作，实际是同义反复（20 次尝试全失败
    仍判退出 0）。阈值必须来自被测量的量之外，否则它只会跟着一起动。

    判据与 per-workflow 判决是同一把尺（``_cp_interval`` + 三分法）：

    - ``exceeds``：95% 下界 > 上限。整个区间都在上限之上，才敢说超。
    - ``normal``：95% 上界 ≤ 上限。整个区间都在限内，才敢说正常。
    - 其余：区间横跨上限 → ``undetermined``，判不了。

    ``undetermined`` 不判失败：样本精度由 ``--check-sample-size``（退出码 7）
    单独判。两处都红，会让人对着一个只差精度的快照去查供应商。

    ``ceiling_pct is None`` 是报告模式：照旧给出实测值与区间，但明确写出本轮
    没有判定。「没给阈值」不能用沉默表达成通过——那正是本轮修掉的缺陷的另一种
    写法。
    """
    if attempts <= 0:
        return "undetermined", "attempts=0，无观测"
    p_hat = failed / attempts * 100.0
    lower, upper = _cp_interval(attempts, failed)
    measured = (f"失败率 {p_hat:.2f}%（n={attempts}, 失败 {failed}），"
                f"95% 区间 [{lower:.2f}%, {upper:.2f}%]")
    if ceiling_pct is None:
        return "report", (
            f"{measured}；未给 --fail-if-above，政策上限这一层只报告不判定"
            "（退出 0 不代表失败率合格）")
    threshold_text = f"阈值（政策上限）{ceiling_pct:.2f}%"
    verdict = _verdict_of_interval(lower, upper, ceiling_pct)
    if verdict == "exceeds":
        detail = f"{measured}，{threshold_text}：整个区间都在阈值之上，判超阈"
    elif verdict == "normal":
        detail = f"{measured}，{threshold_text}：整个区间都在阈值之内，判正常"
    else:
        detail = (f"{measured}，{threshold_text}：区间横跨阈值，样本不足以判是否"
                  "超阈（不判失败；精度由 --check-sample-size 单独判）")
    return verdict, detail


def per_workflow_rate_report(buckets: dict[str, dict],
                             margin: float) -> dict[str, dict]:
    """逐 workflow 的失败率判决表（纯函数，便于测试与复用）。

    返回 ``{workflow: {attempts, failed, rate_pct, baseline_pct, verdict, detail}}``。
    排序由调用方决定（报告里按 workflow 名，测试里可任意取）。
    """
    baselines = per_workflow_baselines(buckets)
    report: dict[str, dict] = {}
    for name, bucket in buckets.items():
        attempts = int(bucket.get("attempts") or 0)
        failed = int(bucket.get("failed") or 0)
        baseline = baselines.get(name)
        if baseline is None:
            report[name] = {
                "attempts": attempts, "failed": failed,
                "rate_pct": (failed / attempts * 100.0) if attempts else None,
                "baseline_pct": None, "verdict": "undetermined",
                "detail": "其余 workflow 没有任何尝试，留一法基线无从计算",
            }
            continue
        verdict, detail = _rate_verdict(attempts, failed, baseline, margin)
        report[name] = {
            "attempts": attempts, "failed": failed,
            "rate_pct": (failed / attempts * 100.0) if attempts else None,
            "baseline_pct": baseline, "verdict": verdict, "detail": detail,
        }
    return report


def _counts_of(buckets: dict[str, dict]) -> dict[str, tuple[int, int]]:
    """``{workflow: (attempts, failed)}``——判决只看这两个数，``runs`` 不参与。"""
    return {name: (int(bucket.get("attempts") or 0),
                   int(bucket.get("failed") or 0))
            for name, bucket in buckets.items()}


def _history_entry_counts(entry: object) -> dict[str, tuple[int, int]] | None:
    """一条历史记录 → ``{workflow: (attempts, failed)}``；形状无效给 ``None``。

    历史块是导出脚本写的，但它是入库文件、可能被人手改。形状不对时返回 ``None``
    而不是抛异常或猜一个 0：连续轮数会被低估，报告里会写明跳过了几条——低估
    比编造一个「看起来连续」的序列诚实。
    """
    if not isinstance(entry, dict):
        return None
    per_workflow = entry.get("per_workflow")
    if not isinstance(per_workflow, dict) or not per_workflow:
        return None
    counts: dict[str, tuple[int, int]] = {}
    for name, bucket in per_workflow.items():
        if not isinstance(bucket, dict):
            return None
        try:
            counts[str(name)] = (int(bucket.get("attempts") or 0),
                                 int(bucket.get("failed") or 0))
        except (TypeError, ValueError):
            return None
    return counts


def snapshot_rounds(meta: dict, current: dict[str, dict]
                    ) -> tuple[list[dict[str, tuple[int, int]]], int]:
    """把快照历史整理成「轮」序列（旧→新），并保证当前这一轮在最后。

    返回 ``(rounds, invalid_entries)``。三种情形：

    - 历史以当前这份快照收尾（导出脚本的写法：每次导出把本轮追加进去）：
      直接用它，当前轮就是最后一条，不会重复计数。
    - 历史缺失、为空、或最后一条与当前内容不一致（旧快照、手改过内容）：
      把当前内容补成新的一轮。**不能因为「历史里没有当前这轮」就少算一轮**，
      那会让提示晚一轮出现，而且让「当前是不是判不了」取决于历史是否完整。
    - 形状无效的条目跳过并计数，由报告说明。

    为什么要跟当前内容做一次相等比较，而不是无条件追加：导出脚本写历史时
    已经把本轮写进去了，无条件追加会把同一轮数两次。
    """
    current_counts = _counts_of(current)
    rounds: list[dict[str, tuple[int, int]]] = []
    invalid = 0
    history = meta.get("history")
    if isinstance(history, list):
        for entry in history:
            counts = _history_entry_counts(entry)
            if counts is None:
                invalid += 1
                continue
            rounds.append(counts)
    if not rounds or rounds[-1] != current_counts:
        rounds.append(current_counts)
    return rounds, invalid


def _verdicts_of_round(counts: dict[str, tuple[int, int]],
                       margin_pct: float) -> dict[str, str]:
    """一轮快照里每个 workflow 的三分判决。

    基线必须在**那一轮**里算：留一法基线是本轮其余 workflow 的合并失效率，
    用今天的其余 workflow 去判历史轮，比的就不是当时的那个问题了。
    """
    buckets = {name: {"attempts": attempts, "failed": failed}
               for name, (attempts, failed) in counts.items()}
    baselines = per_workflow_baselines(buckets)
    verdicts: dict[str, str] = {}
    for name, (attempts, failed) in counts.items():
        baseline = baselines.get(name)
        if baseline is None:
            verdicts[name] = "undetermined"
            continue
        verdicts[name] = _rate_verdict(attempts, failed, baseline, margin_pct)[0]
    return verdicts


def undetermined_streaks(rounds: list[dict[str, tuple[int, int]]],
                         margin_pct: float) -> dict[str, int]:
    """每个 workflow 以当前轮结尾的连续 ``undetermined`` 轮数（含当前轮）。

    它只回答「连续几轮判不了」，不重复当前轮的判决（那由
    ``per_workflow_rate_report`` 给）。当前轮判不了 → 至少 1 轮；上一轮判出了
    结论就中断，不再往前数。

    某个 workflow 在历史轮里缺席（覆盖变化）时中断计数而不是跳过：缺席说明
    那一轮的样本集合不同，「连续」的前提不成立。
    """
    if not rounds:
        return {}
    verdicts = [_verdicts_of_round(counts, margin_pct) for counts in rounds]
    streaks: dict[str, int] = {}
    for name in rounds[-1]:
        streak = 0
        for round_verdicts in reversed(verdicts):
            if round_verdicts.get(name) == "undetermined":
                streak += 1
            else:
                break
        streaks[name] = streak
    return streaks


def historical_baseline(meta: dict, current: dict[str, dict]
                        ) -> tuple[dict | None, int, str]:
    """当前这一轮之前的最近一轮合计，用作回归判据的基线（R59）。

    返回 ``(baseline, invalid_entries, note)``；``baseline`` 形如
    ``{"attempts": n, "failed": k, "workflows": m}``，没有可用基线时给 ``None``，
    ``note`` 说明原因。三种「没有基线」都显式成文字，不拿 0 或当前轮顶替：

    - 历史只有当前这一轮（刚重导过、或旧快照没有 ``history`` 块）；
    - 两轮的 workflow 集合不同。覆盖变化会让两个失败率不可比（新工作流带着
      自己的失败率进来，旧的又可能因为窗口滚动而消失），此时判「回归」等于
      把一次覆盖面变化说成「东西在变坏」。与 ``undetermined_streaks`` 的
      「缺席即中断」同一条纪律。
    - 形状无效的历史条目被跳过并计数，由调用方在报告里写明——跳过之后基线
      可能不是紧邻的一轮。

    **只取上一轮，不合并多轮**：相邻两次导出常常包含同一批 run，把重叠样本
    当独立样本会伪造精度（区间假性收窄），从而把噪声判成回归。单轮比较在
    同一份数据内仍有重叠，但忽略重叠只会让区间偏宽，方向偏向「判不出」。
    """
    rounds, invalid = snapshot_rounds(meta, current)
    if len(rounds) < 2:
        return None, invalid, (
            "快照历史只有当前这一轮，没有可比的上一轮"
            "（重导一次后下一轮才有基线）")
    previous = rounds[-2]
    current_names = set(rounds[-1])
    previous_names = set(previous)
    if current_names != previous_names:
        added = sorted(current_names - previous_names)
        gone = sorted(previous_names - current_names)
        return None, invalid, (
            f"上一轮与当前的 workflow 集合不同（新增 {added or '无'}，"
            f"消失 {gone or '无'}），失败率不可比，判不了回归")
    attempts = sum(a for a, _ in previous.values())
    failed = sum(f for _, f in previous.values())
    note = (f"基线取自历史上一轮（{len(previous)} 个 workflow，"
            f"{failed}/{attempts}）")
    return {"attempts": attempts, "failed": failed,
            "workflows": len(previous)}, invalid, note


def _baseline_verdict(attempts: int, failed: int,
                      baseline_attempts: int, baseline_failed: int,
                      margin_pct: float) -> tuple[str, str]:
    """当前轮相对历史基线是否回归：``exceeds`` / ``normal`` / ``undetermined``。

    与 ``_rate_verdict`` 共用同一把尺（同一条 Clopper-Pearson 区间、同一个三分
    法），只是「基线」换成上一轮的真实失败率。判决名沿用 ``exceeds``——对
    调用方来说它就是「超出基线」，报告层再翻成「回归」。

    基线本身太薄时先判 ``undetermined``：拿一个 ``0/10``（95% 上界 25.9 个
    百分点）当阈值，当前只要不是零失败就会被判回归，而那个基线根本区分不了
    0% 与 20%。判定用的是 ``_failure_rate_precision``——与 ``--check-sample-size``
    同一把尺，不在这里另发明一个样本量门槛。

    ``margin_pct`` 同时是「精度门槛」与「变化阈值」。这不是省一个参数，而是
    「计数不变 ⇒ normal」这条不变量的**充要条件**（R67）：阈值 = 基线 + margin，
    而可判条件保证基线的 95% 上界 ≤ 基线 + margin；两轮计数相同时当前区间与
    基线区间逐位相同，上界必然 ≤ 阈值。把两个量拆开（精度 10、阈值 3）得到的
    不是「更严的判据」，而是一个在**没有变化时也说不出 normal** 的判据——
    可判的 workflow 会整批从「没有回归」变成「判不了」。这条代价由
    ``--calibrate-lead-time`` 算成具体次数，并由
    ``tests/test_live_snapshot_gate.py`` 的不变量用例钉住。
    """
    if baseline_attempts <= 0:
        return "undetermined", "历史基线没有尝试，判不了回归"
    ok, precision_detail = _failure_rate_precision(
        baseline_attempts, baseline_failed, margin_pct)
    if not ok:
        return "undetermined", (
            f"历史基线本身的失败率估计太薄，判不了回归：{precision_detail}")
    baseline_rate = baseline_failed / baseline_attempts * 100.0
    verdict, detail = _rate_verdict(attempts, failed, baseline_rate, margin_pct)
    # 判决措辞必须写出来：只有阈值数字时，日志里「没红」会被读成「判过了」，
    # 而 ``undetermined`` 既不是过也不是不过。
    if verdict == "exceeds":
        detail += "：整个区间都在阈值之上，判回归"
    elif verdict == "normal":
        detail += "：整个区间都在阈值之内，判没有回归"
    else:
        detail += "：区间横跨阈值，样本不足以判是否回归（不判失败）"
    return verdict, detail


def check_per_workflow_rate(data_dir: Path, margin: float,
                            fail_on_exceeds: bool = False) -> tuple[int, str]:
    """按 workflow 判失败率是否高于**其余** workflow 的合并基线（R56）。

    这是 R54 §1 与 R53 §12-3 一路挂账到现在的「真正增量」：此前 per-workflow
    只做样本量诊断，闸门本身仍用全局合计，而全局合计对「某个 workflow 在变坏」
    是结构性失明的（一个全挂的 workflow 会把自己拉进基线里，见
    ``per_workflow_baselines`` 的注释）。

    落地形态分两步：R56 先只报告（恒退出 0），让真实结论在 CI 日志里跑一轮；
    R58 用户拍定上硬门槛，``--fail-on-exceeds`` 接进两个 runner。硬门槛的
    前提在 R57 之后已经具备：主闸门的自指阈值修掉之后，「判不了」与「不合格」
    是两种结论，per-workflow 这边用同一把尺（``_cp_interval`` + 三分法）。

    ``undetermined`` 在任何模式下都不判失败：它是「判不了」，处置是重导更多
    run，不是「不合格」。R58 给它加了次级信号：快照历史里连续
    ``UNDETERMINED_ROUND_STREAK`` 轮（含当前）都判不了，就在报告里提示重导。
    这条提示不改变退出码——把「判不了」做成失败，就是 R56 §2 批评过的
    「向错方向的假红」，只是换成了时间维度。

    能红的路径（与 ``check_per_workflow`` 同一纪律）：
    1. ``per_workflow`` 元数据与内容不一致 → 4（重导）；
    2. 无样本 → 3；
    3. 有 workflow 判 ``exceeds`` 且给了 ``--fail-on-exceeds`` → 1。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判 per-workflow 失败率：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    recorded = meta.get("per_workflow") or {}
    if not isinstance(recorded, dict) or not recorded:
        return EXIT_NO_SAMPLE, (
            "快照元数据缺 per_workflow 块，无法判 per-workflow 失败率。"
            "重导一次即可补上：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")

    actual = recompute_per_workflow(data_dir / "workflows")
    if not actual:
        return EXIT_NO_SAMPLE, (
            f"快照里没有任何带 run 记录的工作流（{data_dir / 'workflows'}）")

    # 与 --check-per-workflow 完全同一层校验：判失败率之前，先确认判的是内容
    # 而不是一句写在元数据里的话。两处各写一份漂移检查会各自演化出差异。
    drifts = _per_workflow_drift(recorded, actual)
    if drifts:
        return EXIT_META_DRIFT, _drift_message(drifts)

    report = per_workflow_rate_report(actual, margin)
    exceeds = [n for n in sorted(report) if report[n]["verdict"] == "exceeds"]
    normal = [n for n in sorted(report) if report[n]["verdict"] == "normal"]
    undetermined = [n for n in sorted(report)
                    if report[n]["verdict"] == "undetermined"]

    summary = (
        f"per-workflow 失败率（留一法基线，margin={margin:g}）："
        f"{len(exceeds)} 个超出 / {len(normal)} 个正常 / "
        f"{len(undetermined)} 个样本不足无法判定")
    if exceeds:
        summary += "。超出基线的：" + "；".join(
            f"{n}（{report[n]['detail']}）" for n in exceeds)
    if normal:
        summary += "。正常的：" + "；".join(
            f"{n}（{report[n]['detail']}）" for n in normal)
    if undetermined:
        summary += (
            "。样本不足的（**不是**合格也不是不合格，处置是重导更多 run）："
            + "；".join(f"{n}（{report[n]['detail']}）" for n in undetermined))
    # 次级信号（R58）：单轮判不了是样本薄，连续多轮判不了是数据量本身不够。
    # 这段文案只提示，不改变退出码；下面 report-mode 的文案与它并列，两者都
    # 是「这一步没有失败、但也没有通过」的不同原因。
    rounds, invalid_history = snapshot_rounds(meta, actual)
    streaks = undetermined_streaks(rounds, margin)
    chronic = sorted(name for name, streak in streaks.items()
                     if streak >= UNDETERMINED_ROUND_STREAK)
    summary += f"。快照历史 {len(rounds)} 轮（含当前）"
    if invalid_history:
        summary += (f"，另有 {invalid_history} 条历史形状无效已跳过"
                    "（连续轮数可能被低估，重导会在最新一条上重新积累）")
    if chronic:
        summary += (
            f"。连续 {UNDETERMINED_ROUND_STREAK} 轮以上样本不足："
            + "；".join(f"{n}（连续 {streaks[n]} 轮）" for n in chronic)
            + "。**这不是失败**（退出码不受影响），处置是重导更多 run："
            "python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 5"
            "；若重导后仍连续不足，说明这些 workflow 的真实数据量本身支撑不了"
            "逐 workflow 判决，需要在文档里接受该限制")
    elif len(rounds) < UNDETERMINED_ROUND_STREAK:
        summary += (f"——「连续 {UNDETERMINED_ROUND_STREAK} 轮样本不足」的提示"
                    f"需要 ≥{UNDETERMINED_ROUND_STREAK} 轮历史，当前未生效")
    if not fail_on_exceeds:
        summary += "。本轮为**报告模式**：不因超出而失败（加 --fail-on-exceeds 才判）"

    if exceeds and fail_on_exceeds:
        return EXIT_GATE_TRIGGERED, summary
    return EXIT_OK, summary


def per_workflow_regression_report(previous: dict[str, tuple[int, int]],
                                   current: dict[str, tuple[int, int]],
                                   margin_pct: float) -> dict[str, dict]:
    """逐 workflow 相对上一轮基线是否回归（纯函数，便于测试与复用）。

    每项返回::

        {"attempts", "failed",                 # 当前轮该 workflow 的计数
         "baseline_attempts", "baseline_failed" # 上一轮的基线计数
         "baseline_rate_pct",                  # 上一轮失败率（无可比基线为 None）
         "eligible",                           # 基线精度够不够判
         "unchanged",                          # 两轮计数是否完全相同
         "verdict",                            # exceeds / normal / undetermined
         "reason"}                             # 判决理由，报告层直接用

    阈值是「上一轮失败率 + ``margin_pct``」。三分法与合并层 ``_baseline_verdict``
    相同，但**阈值增量不同**（合并层是 ``--regression-margin``，默认 3；这里是
    ``--margin``，默认 10）——R62 写过的「同一把尺」是错的（R67 更正）：两层
    判的是同一个问题（变化够不够大），严格程度却不一样。差 7 个百分点不是
    随手取的，它是「计数不变 ⇒ normal」的充要条件：阈值必须 ≥ 基线自身的
    95% 半宽，否则无变化也会判 ``undetermined``（见 ``_baseline_verdict``）。
    ``eligible`` 用的是 ``_failure_rate_precision``——与 ``--check-per-workflow`` /
    ``--sample-size`` 完全同一把尺，可判集合因此与「精度达标」的那批重合；
    而「精度达标」正好保证上面那条不变量的前提成立。

    ``unchanged`` 单独给出而不是折进 ``normal``：两轮计数一模一样时判决必然
    是「没有回归」，但那**不是质量结论，是本轮没有新增样本**。把它写成计数，
    读日志的人一眼能看出这一层当前有多少判定力，而不必去猜。
    """
    report: dict[str, dict] = {}
    for name in sorted(set(previous) | set(current)):
        prev = previous.get(name)
        cur = current.get(name)
        entry: dict = {
            "attempts": cur[0] if cur else 0,
            "failed": cur[1] if cur else 0,
            "baseline_attempts": prev[0] if prev else 0,
            "baseline_failed": prev[1] if prev else 0,
            "baseline_rate_pct": (prev[1] / prev[0] * 100.0
                                  if prev and prev[0] else None),
            "eligible": False,
            "unchanged": bool(cur is not None and prev is not None and cur == prev),
            "verdict": "undetermined",
            "reason": "",
        }
        if prev is None:
            entry["reason"] = (
                "上一轮没有这个 workflow（覆盖变化），失败率不可比，判不了回归")
            report[name] = entry
            continue
        if cur is None:
            entry["reason"] = (
                "当前轮没有这个 workflow（覆盖变化），失败率不可比，判不了回归")
            report[name] = entry
            continue
        ok = _failure_rate_precision(prev[0], prev[1], margin_pct)[0]
        if not ok:
            # 这里不复用 ``_failure_rate_precision`` 的完整文案：它会给每个
            # workflow 都追加一句「达到余量需要约 N 次尝试」，而 N 只由 margin
            # 决定、跟 workflow 无关——9 个 workflow 拼起来就是同一句话重复 9 遍。
            # 判决口径仍是同一个 ``sample_size_margin_needed``，只是 N 在汇总里
            # 说一次。
            needed = sample_size_margin_needed(prev[0], prev[1])
            shape = ("样本形状无效" if needed is None
                     else f"95% 半宽 {needed:.2f} 个百分点")
            entry["reason"] = (
                f"上一轮基线本身太薄，判不了回归（{shape} > 余量 {margin_pct:g}，"
                f"n={prev[0]}, 失败 {prev[1]}）")
            report[name] = entry
            continue
        entry["eligible"] = True
        verdict, detail = _baseline_verdict(
            cur[0], cur[1], prev[0], prev[1], margin_pct)
        entry["verdict"], entry["reason"] = verdict, detail
        report[name] = entry
    return report


def check_per_workflow_regression(data_dir: Path,
                                  margin: float) -> tuple[int, str]:
    """逐 workflow 判「相对上一轮是否显著变坏」（R62）。

    合并层的回归判据（``--fail-on-regression``）对「一个 workflow 在变坏、被
    其余几个摊薄」是结构性失明的：character 涨到 16/79（20.3%）时全局才
    9.41%，95% 下界 6.57% 仍在回归阈值 6.92% 之下；合并层要到 18/79（22.8%）
    才开口。这一步在 16/79 就判回归（早 2 次失败），mvp 上早 5 次。

    三条设计取舍：

    1. **只在基线够厚时判**：``eligible`` 由 ``_failure_rate_precision`` 决定，
       与 ``--check-per-workflow`` 的「精度达标」完全同一把尺。拿 0/5（95%
       上界 45 个百分点）当阈值，当前只要出现一次失败就会判回归——那是向
       错方向的假红，比判不了更糟。
    2. **``undetermined`` 不判失败**：区间横跨阈值、覆盖变化、基线太薄都归
       这一类，处置是重导更多 run，不是「不合格」。
    3. **「没有判定力」必须写成文字**：可判 0 个、或可判的那几个两轮计数完全
       相同（没有新增样本）时，退出码仍是 0，但输出里逐字写明这是「判不了/
       没什么可判」，不是「判过了」。这一步能红的前提是反向验证真能触发：
       ``live_snapshot_exceeds`` 的 wf-bad 从 0/40 跳到 40/40 必须判 1。

    能红的路径只有一条：某个 ``eligible`` 的 workflow 判 ``exceeds`` → 1。
    其余（无样本 3 / 元数据漂移 4）与其它判据同一套退出码。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法判逐 workflow 回归：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    recorded = meta.get("per_workflow") or {}
    if not isinstance(recorded, dict) or not recorded:
        return EXIT_NO_SAMPLE, (
            "快照元数据缺 per_workflow 块，无法判逐 workflow 回归。"
            "重导一次即可补上：python scripts/export_run_samples.py "
            "--dest tests/fixtures/live_snapshot --limit 2")

    actual = recompute_per_workflow(data_dir / "workflows")
    if not actual:
        return EXIT_NO_SAMPLE, (
            f"快照里没有任何带 run 记录的工作流（{data_dir / 'workflows'}）")

    # 与另两条 per-workflow 判据同一层校验：先确认判的是内容而不是元数据里
    # 的一句话，再谈回归。
    drifts = _per_workflow_drift(recorded, actual)
    if drifts:
        return EXIT_META_DRIFT, _drift_message(drifts)

    rounds, invalid_history = snapshot_rounds(meta, actual)
    if len(rounds) < 2:
        return EXIT_OK, (
            "逐 workflow 回归：快照历史只有当前这一轮，没有可比的上一轮"
            "（重导一次后下一轮才有基线）。**本步没有判定力**，"
            "退出 0 不代表没有回归")

    report = per_workflow_regression_report(rounds[-2], rounds[-1], margin)
    eligible = sorted(n for n in report if report[n]["eligible"])
    exceeds = [n for n in eligible if report[n]["verdict"] == "exceeds"]
    normal = [n for n in eligible if report[n]["verdict"] == "normal"]
    straddle = [n for n in eligible if report[n]["verdict"] == "undetermined"]
    unchanged = [n for n in eligible if report[n]["unchanged"]]
    ineligible = sorted(n for n in report if not report[n]["eligible"])

    summary = (
        f"逐 workflow 回归（基线=历史上一轮，阈值=基线+{margin:g}；"
        f"合并层阈值=基线+{REGRESSION_MARGIN:g}）："
        f"{len(report)} 个 workflow 里 {len(eligible)} 个可判"
        f"（{len(exceeds)} 个判回归 / {len(normal)} 个没有回归 / "
        f"{len(straddle)} 个区间横跨阈值），{len(ineligible)} 个基线太薄判不了")
    if exceeds:
        summary += "。判回归的：" + "；".join(
            f"{n}（{report[n]['reason']}）" for n in exceeds)
    if normal:
        summary += "。没有回归的：" + "；".join(
            f"{n}（{report[n]['reason']}）" for n in normal)
    if straddle:
        summary += "。区间横跨阈值的（判不了回归，不判失败）：" + "；".join(
            f"{n}（{report[n]['reason']}）" for n in straddle)
    if unchanged:
        summary += (
            f"。其中 {len(unchanged)} 个可判 workflow 两轮计数完全相同"
            f"（{'、'.join(unchanged)}）：**这是样本没有新增，不是质量结论**")
    if ineligible:
        summary += (
            "。基线太薄的（**不该**被当作逐 workflow 的比较基线，处置是重导"
            "更多 run）：" + "；".join(
                f"{n}（{report[n]['reason']}）" for n in ineligible))
        if margin > 0:
            # 补齐精度需要多少次尝试只由 margin 决定，与 workflow 无关：
            # 在汇总里说一次，不在每条里重复。
            summary += (
                f"。要把这些基线压到余量 {margin:g} 以内需要约 "
                f"{math.ceil(math.log(0.05) / math.log(1 - margin / 100))} 次尝试")
    if not eligible:
        summary += (
            "。**本步没有判定力**：没有任何 workflow 的上一轮基线精度达到 "
            f"margin={margin:g}，退出 0 不代表没有回归")
    if invalid_history:
        summary += (f"（另有 {invalid_history} 条历史形状无效已跳过，"
                    "基线可能不是紧邻的一轮）")

    # R67：两个阈值增量不是同一个量，必须写进输出。逐 workflow 的增量等于
    # 基线精度余量，才保证「计数不变 ⇒ normal」可达；合并层的 3 是另一件事
    # （「变化够不够大」的政策余量）。只写一个数字会让读日志的人以为两层同样
    # 严格，进而把「提前 2 次」误读成「同样严格下早 2 次」。
    if eligible:
        summary += (
            f"。两层的阈值增量不是同一个量：逐 workflow {margin:g}（= 基线精度"
            f"余量，保证「计数不变⇒normal」可达）、合并层 {REGRESSION_MARGIN:g}"
            "（--regression-margin 的默认值）；提前量用 --calibrate-lead-time 复算")

    if exceeds:
        summary += "。退出码 1 的来源：逐 workflow 回归（" + "、".join(exceeds) + "）"
        return EXIT_GATE_TRIGGERED, summary
    return EXIT_OK, summary


def _first_red_k(attempts: int, baseline_pct: float,
                 delta_pct: float) -> int | None:
    """在固定尝试数下，第几次失败会让三分法判 ``exceeds``（R67）。

    「第几次失败开口」= 最小的 ``k``，使 ``k/attempts`` 的 95% 下界高于
    ``baseline_pct + delta_pct``。只用于校准：它不改任何判决，也不读别的状态。
    没有这样的 ``k``（阈值高到整段样本都够不着）时返回 ``None``，不返回一个
    假装能判的哨兵值。
    """
    for failed in range(attempts + 1):
        verdict, _ = _rate_verdict(attempts, failed, baseline_pct, delta_pct)
        if verdict == "exceeds":
            return failed
    return None


def lead_time_report(previous: dict[str, tuple[int, int]],
                     current: dict[str, tuple[int, int]],
                     precision_margin_pct: float,
                     per_workflow_delta_pct: float,
                     merged_delta_pct: float) -> dict[str, dict]:
    """逐 workflow 层比合并层早多少次失败开口（R67，R62 §2 的可复算版）。

    R62 §2 那张「提前 2 次 / 5 次」的表此前是手算的，而这份仓库的纪律是
    **文档里的数必须能被判据自己的算术复算**（R63 的教训：文档会替判据吹牛）。
    这里只用闸门自己的三个零件——``_cp_interval`` / ``_verdict_of_interval`` /
    ``sample_size_margin_needed``（经 ``_rate_verdict`` 与 ``_failure_rate_precision``）
    ——不写第二份公式。

    口径固定成「**同样长的样本**」：当前轮的 attempts 保持不变，只在失败次数
    ``k`` 上从 0 扫到 attempts。比较的是两条判据各自在哪一个 ``k`` 上第一次
    判 ``exceeds``：

    - 逐 workflow：``k`` 只加在**该 workflow 自己**的计数上，阈值 = 该
      workflow 上一轮失败率 + ``per_workflow_delta_pct``；
    - 合并层：``k`` 加进全局合计（其余 workflow 的失败数保持不变），阈值 =
      上一轮全局失败率 + ``merged_delta_pct``。

    两项的增量**不一样**（R67 更正 R62 的「同一把尺」）：逐 workflow 用的是
    ``--margin``，合并层用 ``--regression-margin``。原因见
    ``_baseline_verdict``——逐 workflow 的增量必须不小于基线自身的 95% 半宽，
    否则「计数不变 ⇒ normal」不成立。

    ``eligible`` 沿用 ``_failure_rate_precision``：基线太薄的 workflow 本层
    根本不参与，给它算出来的 ``k`` 只是「假如能判」的假设值，报告层必须把
    它和可判的分开写。覆盖变化（只在一边出现）的 workflow 不可比，单独标记。
    """
    previous_total_attempts = sum(a for a, _ in previous.values())
    previous_total_failed = sum(f for _, f in previous.values())
    current_total_attempts = sum(a for a, _ in current.values())
    current_total_failed = sum(f for _, f in current.values())
    merged_baseline_pct = (
        previous_total_failed / previous_total_attempts * 100.0
        if previous_total_attempts else None)

    report: dict[str, dict] = {}
    for name in sorted(set(previous) | set(current)):
        prev = previous.get(name)
        cur = current.get(name)
        entry: dict = {
            "comparable": bool(prev is not None and cur is not None),
            "baseline_attempts": prev[0] if prev else 0,
            "baseline_failed": prev[1] if prev else 0,
            "baseline_rate_pct": (prev[1] / prev[0] * 100.0
                                  if prev and prev[0] else None),
            "attempts": cur[0] if cur else 0,
            "failed": cur[1] if cur else 0,
            "unchanged": bool(prev is not None and cur is not None and prev == cur),
            "precision_needed_pct": None,
            "eligible": False,
            "per_workflow_threshold_pct": None,
            "per_workflow_first_red_k": None,
            "merged_threshold_pct": None,
            "merged_first_red_k": None,
            "lead_failures": None,
            "current_verdict": None,
            "reason": "",
        }
        if prev is None:
            entry["reason"] = "上一轮没有这个 workflow（覆盖变化），失败率不可比"
            report[name] = entry
            continue
        if cur is None:
            entry["reason"] = "当前轮没有这个 workflow（覆盖变化），失败率不可比"
            report[name] = entry
            continue
        if prev[0] <= 0:
            entry["reason"] = "上一轮 attempts=0，没有基线"
            report[name] = entry
            continue

        needed = sample_size_margin_needed(prev[0], prev[1])
        entry["precision_needed_pct"] = needed
        entry["eligible"] = needed is not None and needed <= precision_margin_pct
        baseline_pct = entry["baseline_rate_pct"]
        entry["per_workflow_threshold_pct"] = baseline_pct + per_workflow_delta_pct
        entry["current_verdict"] = _rate_verdict(
            cur[0], cur[1], baseline_pct, per_workflow_delta_pct)[0]
        if entry["eligible"]:
            entry["per_workflow_first_red_k"] = _first_red_k(
                cur[0], baseline_pct, per_workflow_delta_pct)
        if merged_baseline_pct is not None:
            entry["merged_threshold_pct"] = merged_baseline_pct + merged_delta_pct
            # 合并层要挪的是**全局**计数，不是该 workflow 自己的 attempts：
            # 逐 k 扫到该 workflow 的上限为止（再多就不是「这个 workflow 变坏」）。
            base = current_total_failed - cur[1]
            for k in range(cur[0] + 1):
                verdict, _ = _rate_verdict(
                    current_total_attempts, base + k,
                    merged_baseline_pct, merged_delta_pct)
                if verdict == "exceeds":
                    entry["merged_first_red_k"] = k
                    break
            if (entry["per_workflow_first_red_k"] is not None
                    and entry["merged_first_red_k"] is not None):
                entry["lead_failures"] = (
                    entry["merged_first_red_k"]
                    - entry["per_workflow_first_red_k"])
            else:
                entry["reason"] = (
                    "两层里至少有一层在整段样本内都不会开口，提前量不可定义")
        else:
            entry["reason"] = "上一轮全局没有尝试，合并层基线不可用"
        report[name] = entry
    return report


def check_lead_time(data_dir: Path, precision_margin: float,
                    per_workflow_delta: float,
                    merged_delta: float) -> tuple[int, str]:
    """复算「逐 workflow 层比合并层早几次失败开口」（R67；只读，**不作判定**）。

    为什么给它一个独立模式，而不是并进 ``--check-per-workflow-regression`` 的
    输出：那条判据在真实快照上的说明已经很长，而提前量是**校准数据**——它与
    本轮判了什么无关。做成命令有三个直接理由：

    1. R62 §2 的「提前 2 / 5 次」是手算的。按本仓库的纪律（R63：文档会替判据
       吹牛），它必须能被判据自己的算术复算；
    2. 阈值增量换一个数，提前量就变（10 → 3 时 2 → 9），这个取舍要能被量化，
       而不是写在文档里让读者自己推；
    3. 它只读快照自身，不需要真实数据面，所以能进 CI。

    **本模式不作判定**：没有任何输入会让它退出 1。退出 0 只表示「算出来了」，
    不表示提前量够大、也不表示判据健康。无样本（3）与元数据漂移（4）沿用闸门
    自己的码——它们描述「算不了」，与「算出来是不合格」是两件事。
    """
    meta_path = data_dir / "snapshot-meta.json"
    if not meta_path.is_file():
        return EXIT_NO_SAMPLE, f"快照元数据缺失，无法复算提前量：{meta_path}"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return EXIT_META_DRIFT, f"快照元数据无法解析：{exc}"

    actual = recompute_per_workflow(data_dir / "workflows")
    if not actual:
        return EXIT_NO_SAMPLE, (
            f"快照里没有任何带 run 记录的工作流（{data_dir / 'workflows'}）")
    drifts = _per_workflow_drift(meta.get("per_workflow") or {}, actual)
    if drifts:
        return EXIT_META_DRIFT, _drift_message(drifts)

    rounds, invalid_history = snapshot_rounds(meta, actual)
    if len(rounds) < 2:
        return EXIT_NO_SAMPLE, (
            "提前量校准：快照历史只有当前这一轮，没有可比的上一轮"
            "（重导一次后下一轮才有基线）。**本步没有算出任何数**，"
            "退出 3 表示算不了，不是判了不合格")

    previous, current = rounds[-2], rounds[-1]
    report = lead_time_report(previous, current, precision_margin,
                              per_workflow_delta, merged_delta)
    # 「若把逐 workflow 阈值对齐到合并层」的反事实：同一个函数、同一把尺，
    # 换个 delta 再算一次。文档里「压到 +3 会变成 9 次」这句话就是这条输出。
    aligned = lead_time_report(previous, current, precision_margin,
                               merged_delta, merged_delta)

    baseline_failed = sum(f for _, f in previous.values())
    baseline_attempts = sum(a for a, _ in previous.values())
    lines = [
        "逐 workflow 提前量校准（只读，**不作判定**：退出 0 只表示算出来了）",
        f"逐 workflow 阈值 = 基线 + {per_workflow_delta:g}（--margin，同时是基线"
        f"精度余量）；合并层阈值 = 基线 + {merged_delta:g}（--regression-margin）",
        f"基线取自历史上一轮（{len(previous)} 个 workflow，"
        f"{baseline_failed}/{baseline_attempts}）",
    ]

    eligible_names: list[str] = []
    ineligible: list[str] = []
    for name in sorted(current):
        entry = report[name]
        if not entry["comparable"]:
            lines.append(f"  {name}: {entry['reason']}")
            continue
        needed = entry["precision_needed_pct"]
        needed_text = "形状无效" if needed is None else f"{needed:.2f}"
        if not entry["eligible"]:
            ineligible.append(f"{name}（95% 半宽 {needed_text} > "
                              f"{precision_margin:g}）")
            continue
        eligible_names.append(name)
        k_flow = entry["per_workflow_first_red_k"]
        k_merged = entry["merged_first_red_k"]
        lead = entry["lead_failures"]
        lines.append(
            f"  {name}: 基线 {entry['baseline_failed']}/"
            f"{entry['baseline_attempts']}（{entry['baseline_rate_pct']:.2f}%），"
            f"95% 半宽 {needed_text} ≤ {precision_margin:g} → 可判；"
            f"逐 workflow 阈值 {entry['per_workflow_threshold_pct']:.2f}%，"
            + (f"第 {k_flow} 次失败开口"
               f"（{k_flow / entry['attempts'] * 100:.2f}%）"
               if k_flow is not None else "整段样本内不会开口")
            + "；合并层"
            + (f"第 {k_merged} 次"
               f"（{k_merged / entry['attempts'] * 100:.2f}%）"
               if k_merged is not None else "整段样本内不会开口")
            + (f"，提前 {lead} 次" if lead is not None else "，提前量不可定义")
            + f"；当前计数{'不变' if entry['unchanged'] else '有变化'} → "
            f"{entry['current_verdict']}")

    if ineligible:
        lines.append("  基线太薄、本层不参与（算出的开口点只是假设）："
                     + "、".join(ineligible))
    if eligible_names:
        leads = [(n, report[n]["lead_failures"]) for n in eligible_names
                 if report[n]["lead_failures"] is not None]
        if leads:
            lines.append(f"能提前开口的 {len(leads)} 个："
                         + "、".join(f"{n}（{lead} 次）" for n, lead in leads))
        else:
            lines.append("**没有一个可判 workflow 能提前开口**：这一层在当前"
                         "样本上没有增量（退出 0 不代表增量存在）")
    else:
        lines.append("**没有任何 workflow 可判**：这一层在当前样本上没有判定力")

    # 反事实：阈值对齐合并层。只打印可判的那些，并把「说不出 normal」写出来。
    aligned_notes: list[str] = []
    for name in eligible_names:
        entry = aligned[name]
        k_flow = entry["per_workflow_first_red_k"]
        if k_flow is None:
            continue
        note = (f"{name} 第 {k_flow} 次"
                f"（{k_flow / entry['attempts'] * 100:.2f}%）"
                f"→ 提前 {entry['lead_failures']} 次，当前计数"
                f"{'不变' if entry['unchanged'] else '有变化'} → "
                f"{entry['current_verdict']}")
        if entry["current_verdict"] != "normal":
            note += "（说不出 normal）"
        aligned_notes.append(note)
    if aligned_notes:
        lines.append(
            f"反事实：若把逐 workflow 阈值压到与合并层一致（+{merged_delta:g}）："
            + "；".join(aligned_notes))
        lines.append("取舍：压小阈值换来更早开口，代价是「计数不变」也可能判不了——"
                     "判据只有在阈值 ≥ 基线精度时才能说 normal，所以默认不压")

    if invalid_history:
        lines.append(f"（另有 {invalid_history} 条历史形状无效已跳过）")
    return EXIT_OK, "\n".join(lines)


def _run_judgement(judgement) -> int:
    """跑一个判据，把「算不下去」与「判了且不合格」分开（R64）。

    退出码 1 的含义是「判了，结论是不合格」，处置是查数据/供应商；判据在算的
    过程中抛算术异常时，进程按 Python 默认以 1 退出，于是两种处置共用一个码。
    R64 修掉的那条路径（CP 精确界在 n≈1030 溢出）正是如此：CI 里读起来是
    「失败率突破政策」，实际是判据自己崩了。

    只捕获算术类异常（``ArithmeticError`` 含 OverflowError/ZeroDivisionError，
    外加 ``ValueError``——``log``/``exp`` 的定义域错误也落在这里）。类型错误之类
    的代码 bug 仍然照常崩掉，那是开发期信号，不该被降级成一个退出码。
    """
    try:
        code, message = judgement()
    except (ArithmeticError, ValueError) as exc:
        print(f"[live-gate] 判据算术失败，**未作判定**（退出码 "
              f"{EXIT_NUMERIC_FAILURE}，不等于任何不合格判决）："
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_NUMERIC_FAILURE
    print(f"[live-gate] {message}", file=sys.stderr)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="快照根目录（含 workflows/ 与 snapshot-meta.json）；"
                             "缺省读 DETERMINFLOW_DATA_DIR，再缺省用入库快照路径")
    parser.add_argument("--margin", type=float, default=None,
                        help=f"精度余量（百分点，默认 {DEFAULT_MARGIN:g}），用于 --check-* 判据与"
                             "--calibrate-lead-time：样本量厚度、per-workflow 判决"
                             "与可判集合都拿它当尺（逐 workflow 的**变化阈值**也"
                             "等于它——两个量必须相同，见 _baseline_verdict）")
    parser.add_argument("--fail-if-above", type=float, default=None,
                        help="默认判定模式的政策上限（百分点，0 到 100 之间且不含 "
                             "100）：失败率 95%% 区间下界高于它才退出 1；不给则只报告不判定")
    parser.add_argument("--check-stale", action="store_true",
                        help="改判快照新鲜度：真实数据比快照新多少天（不判失败率）")
    parser.add_argument("--check-coverage", action="store_true",
                        help="改判快照覆盖度：真实数据跑过的工作流是否都在快照内")
    parser.add_argument("--check-sample-size", action="store_true",
                        help="改判样本量厚度：失败率估计的精度是否够当闸门基线"
                             "（只读快照自身，CI 可跑）")
    parser.add_argument("--check-per-workflow", action="store_true",
                        help="按 workflow 分别报告失败率估计精度，并校验 per_workflow "
                             "元数据与内容一致（只读快照自身，CI 可跑）")
    parser.add_argument("--check-per-workflow-rate", action="store_true",
                        help="按 workflow 判失败率是否高于其余 workflow 的合并基线"
                             "（留一法；只读快照自身，CI 可跑）")
    parser.add_argument("--check-per-workflow-regression", action="store_true",
                        help="按 workflow 判失败率是否显著高于快照上一轮基线"
                             "（只读快照自身，CI 可跑；基线太薄的 workflow "
                             "判不了，不判失败）")
    parser.add_argument("--calibrate-lead-time", action="store_true",
                        help="复算逐 workflow 层比合并层早几次失败开口（只读，"
                             "**不作判定**：退出 0 只表示算出来了）")
    parser.add_argument("--fail-on-exceeds", action="store_true",
                        help="--check-per-workflow-rate 时把 exceeds 判为退出码 1"
                             "（默认只报告，恒退出 0）")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="默认判定模式加判历史基线回归：当前失败率相对快照"
                             "上一轮高出 --regression-margin 且 95%% 区间下界仍在"
                             "阈值之上才退出 1（可与 --fail-if-above 并存）")
    parser.add_argument("--regression-margin", type=float, default=None,
                        help="回归判据允许的基线抬升（百分点，默认 "
                             f"{REGRESSION_MARGIN:g}）；不能用来替代 --margin")
    parser.add_argument("--source", type=Path, default=None,
                        help="真实 run 记录根目录（默认 src.config.WORKFLOWS_DIR），"
                             "仅 --check-stale / --check-coverage 使用")
    parser.add_argument("--max-lag-days", type=float,
                        default=DEFAULT_MAX_LAG_DAYS,
                        help="快照允许落后真实数据的天数（默认 7）")
    options = parser.parse_args()
    margin = DEFAULT_MARGIN if options.margin is None else options.margin
    if margin < 0:
        parser.error("--margin 不能为负")
    if options.fail_if_above is not None and not 0.0 <= options.fail_if_above < 100.0:
        # 100 与 >100 都永远判不出超阈：Clopper-Pearson 上界最多到 100%，而判据
        # 要求**整个区间**都在上限之上。那是写着「容忍一切」的恒绿配置，不是闸门
        # ——与 R57 修掉的自指阈值同一类失效，不能在参数层放它进来。
        parser.error("--fail-if-above 需在 0 到 100 之间（不含 100，单位是百分比）")
    if options.max_lag_days < 0:
        parser.error("--max-lag-days 不能为负")
    # 四种判据互斥：一次调用判一件事，混判会让人看不出是哪种不合格。
    # ``--fail-on-exceeds`` 不是判据而是 ``--check-per-workflow-rate`` 的修饰，
    # 所以不列入互斥表——它与任何判据同时出现都只是"这个开关没用上"，
    # 由下面的显式检查报错，而不是静默忽略。
    chosen = [
        flag for flag, on in (
            ("--check-stale", options.check_stale),
            ("--check-coverage", options.check_coverage),
            ("--check-sample-size", options.check_sample_size),
            ("--check-per-workflow", options.check_per_workflow),
            ("--check-per-workflow-rate", options.check_per_workflow_rate),
            ("--check-per-workflow-regression",
             options.check_per_workflow_regression),
            ("--calibrate-lead-time", options.calibrate_lead_time),
        ) if on
    ]
    if len(chosen) > 1:
        parser.error(f"{' 与 '.join(chosen)} 是不同的判据，不能同时使用")
    if options.fail_on_exceeds and not options.check_per_workflow_rate:
        # 静默忽略会让「我加了 --fail-on-exceeds，CI 却没红」变成一个无人排查
        # 的谜。显式报错，与上一行的互斥检查同一纪律。
        parser.error("--fail-on-exceeds 只能配合 --check-per-workflow-rate 使用")
    if options.fail_on_regression and chosen:
        # 回归是默认判定模式的一部分，与四条 --check-* 判据互斥：混在一次调用
        # 里会让人看不出红的是哪一层（与「一次调用判一件事」同一纪律）。
        parser.error(
            f"--fail-on-regression 不能与 {' 与 '.join(chosen)} 同时使用")
    if options.regression_margin is not None:
        if not (options.fail_on_regression or options.calibrate_lead_time):
            # 与 --margin/--fail-on-exceeds 同一纪律：不确定的配置在参数层炸掉，
            # 而不是静默忽略。**逐 workflow 层不在可配置范围**：它的阈值必须
            # 等于 --margin（基线精度余量），否则「计数不变 ⇒ normal」不成立
            # （见 _baseline_verdict）；放开这个开关等于允许一个说不出 normal
            # 的判据上线。
            parser.error(
                "--regression-margin 只用于合并层（--fail-on-regression）与校准"
                "（--calibrate-lead-time）；逐 workflow 层的阈值必须等于 --margin")
        if not 0.0 <= options.regression_margin < 100.0:
            # 100 与 >100 永远等不到「整个区间在阈值之上」，是写着「不判回归」
            # 的恒绿配置；负数则相当于把阈值压到基线以下，任何持平都算回归。
            parser.error("--regression-margin 需在 0 到 100 之间（不含 100，单位是百分比）")
    if options.fail_if_above is not None and chosen:
        # 上限只属于默认判定模式。混着给会让人以为「样本量判据也按这个上限判」，
        # 而它判的是精度，与上限无关。
        parser.error(
            "--fail-if-above 只用于默认判定模式，不能与 "
            f"{' 与 '.join(chosen)} 同时使用")
    if options.margin is not None and not chosen:
        # 默认模式的阈值只来自 --fail-if-above / --regression-margin（R57/R59）。
        # 静默忽略会让「我把余量收紧到 2，CI 却没变」变成一个无人排查的谜——
        # 与 --fail-on-exceeds 同一纪律：不确定的配置在参数层就炸掉。
        parser.error("--margin 只用于 --check-* 判据；"
                     "默认判定模式的阈值请用 --fail-if-above / --regression-margin")

    if options.calibrate_lead_time:
        # 逐 workflow 层的增量就是 --margin（同一个量），合并层用
        # --regression-margin 的默认值或显式值——校准必须与真判据同参。
        return _run_judgement(lambda: check_lead_time(
            options.data_dir or _default_data_dir(), margin, margin,
            REGRESSION_MARGIN if options.regression_margin is None
            else options.regression_margin))

    if options.check_per_workflow_rate:
        # 与 --check-sample-size 同理：只读快照自身，不需要 --source。
        return _run_judgement(lambda: check_per_workflow_rate(
            options.data_dir or _default_data_dir(), margin,
            fail_on_exceeds=options.fail_on_exceeds))

    if options.check_per_workflow_regression:
        # 只读快照自身（内容 + 元数据里的 history），与 --check-* 同一前提。
        return _run_judgement(lambda: check_per_workflow_regression(
            options.data_dir or _default_data_dir(), margin))

    if options.check_per_workflow:
        # 与 --check-sample-size 同理：只读快照自身，不需要 --source。
        return _run_judgement(lambda: check_per_workflow(
            options.data_dir or _default_data_dir(), margin))

    if options.check_sample_size:
        # 只读快照自身，不需要 --source：这是它能进 CI 的全部原因。
        return _run_judgement(lambda: check_sample_size(
            options.data_dir or _default_data_dir(), margin))

    if options.check_stale or options.check_coverage:
        source = options.source
        if source is None:
            from src.config import WORKFLOWS_DIR

            source = WORKFLOWS_DIR
        snapshot = options.data_dir or _default_data_dir()
        if options.check_coverage:
            return _run_judgement(
                lambda: check_coverage(snapshot, Path(source)))
        return _run_judgement(
            lambda: check_stale(snapshot, Path(source), options.max_lag_days))

    regression_margin = None
    if options.fail_on_regression:
        regression_margin = (REGRESSION_MARGIN if options.regression_margin is None
                             else options.regression_margin)
    return _run_judgement(lambda: evaluate(
        options.data_dir or _default_data_dir(), options.fail_if_above,
        regression_margin=regression_margin))


if __name__ == "__main__":
    raise SystemExit(main())
