"""样本导出脚本（R47）与它的半宽预算检查（R53）。

这个脚本此前**没有测试**——它一直在用，但「怎么用才对」只写在交接文档的
表格里。R53 往它身上加了一条新判据（半宽预算），正好把两条性质一起钉住：

1. **裁剪的正确性判据是画像逐字段相等**，不是「看起来对」。抽掉任何一个
   画像字段都该被拒绝写入。
2. **半宽预算判的是「CI 反向验证还能不能红」**，与 ``--check-sample-size``
   方向相反：后者要求半宽够小（样本够厚），前者要求半宽够大（判据还能触发
   退出码 7）。把两者混成一条，会让人看不懂该调大还是调小 ``--limit``。

两处的阈值都从被测代码里取（``REVERSE_VALIDATION_MARGIN`` / 公式本身），
不在测试里写死数字——写死会在 CI 改 margin 时静默失准。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import export_run_samples as exporter

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# --------------------------------------------------------- 半宽与 CI 的耦合
def test_reverse_validation_margin_matches_the_ci_step() -> None:
    """导出脚本里的 margin 必须与 CI 反向验证用的值一致。

    两者是一对耦合常量：CI 改成 ``--margin 3`` 而这里还是 2，导出时的半宽
    预算就会按错误门槛报警——它会说「还有 0.38 余量」，而 CI 那时已经不触发
    退出码 7 了。这条测试把两处绑在一起，改一处忘另一处会红在这里。
    """
    import yaml

    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    runs: list[str] = []
    for job in document.get("jobs", {}).values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                runs.append(step["run"])
    assert runs, "ci.yml 里没有可解析的 run 步骤"
    combined = "\n".join(runs)

    # CI 的写法是字面量 ``--margin 2``（bash 与 pwsh 两处）。
    expected = exporter.REVERSE_VALIDATION_MARGIN
    assert f"--margin {expected:g}" in combined, (
        f"ci.yml 里找不到 --margin {expected:g}：导出脚本的 REVERSE_VALIDATION_MARGIN "
        "与 CI 反向验证的余量已经漂移"
    )


def test_half_width_is_strictly_greater_than_margin_to_trigger_seven() -> None:
    """所需余量必须**严格大于** margin 才算「反向验证还有判定力」。

    闸门用的是 ``needed <= margin`` 判合格，所以恰好等于 margin 时收紧后的
    那一步会通过（不会以 7 退出）。把边界写成「≥」会让一个刚好在门槛上的
    快照被误判为安全。
    """
    from scripts.check_live_snapshot_gate import sample_size_margin_needed

    margin = exporter.REVERSE_VALIDATION_MARGIN
    attempts, failed = 400, 10  # 所需余量 1.53，明显低于 2.0
    needed = sample_size_margin_needed(attempts, failed)
    assert needed is not None and needed < margin
    ok, message = exporter.half_width_budget(attempts, failed)
    assert ok is False, message
    assert "不再触发" in message

    # 另一侧：所需余量明显大于 margin 时必须判「仍有判定力」。
    ok, message = exporter.half_width_budget(187, 7)  # 2.72
    assert ok is True, message
    assert "仍有判定力" in message


def test_thin_headroom_still_passes_but_warns() -> None:
    """余量很小（但为正）时判合格并告警——不是不合格。

    当前快照 255/10 的所需余量 2.38 距 2.0 只剩 0.38 就是这一档。把它判成
    不合格会让每次正常重导都红，那是不合格的告警噪音；判成合格而不提，则
    下一个人不会知道「再厚一点就失效了」。所以两件事都要：通过 + 明确说余量。
    """
    ok, message = exporter.half_width_budget(255, 10)
    assert ok is True, message
    assert "0.38" in message, message
    assert "越线" in message, message


def test_zero_attempts_is_not_treated_as_safe() -> None:
    """样本为 0 时所需余量算不出来，不能默认「安全」而放过。

    这正是「永远绿的防护」的经典形态：除零回落到 0，0 < margin，于是判合格。
    """
    ok, message = exporter.half_width_budget(0, 0)
    assert ok is False, message
    assert "无从计算" in message


def test_half_width_formula_agrees_with_the_gate() -> None:
    """导出脚本必须**直接复用**闸门的算术，不能各写一份。

    ``check_live_snapshot_gate`` 判「样本够不够厚」，本脚本判「反向验证还能
    不能红」，它们算的是**同一个**量。若一边改了公式（比如换成 Wilson
    区间），两边会得出不同的数字，而两处都还是绿的。
    """
    from scripts import check_live_snapshot_gate as gate

    for attempts, failed in ((255, 10), (187, 7), (400, 10), (1000, 25), (40, 40)):
        needed = gate.sample_size_margin_needed(attempts, failed)
        assert needed is not None
        # 导出脚本的判定必须与该量一致：margin 取 needed 时不触发（<=），
        # 取略小值时触发。
        ok_at, _ = exporter.half_width_budget(attempts, failed, margin=needed)
        assert ok_at is False, (attempts, failed, needed)
        ok_below, _ = exporter.half_width_budget(
            attempts, failed, margin=needed * 0.99)
        assert ok_below is True, (attempts, failed, needed)


# ------------------------------------------------------------- 裁剪正确性
def _run_payload(*, run_id: str = "run-aaaa", status: str = "completed",
                 nodes: list[dict] | None = None) -> dict:
    return {
        "run_id": run_id,
        "workflow_id": "wf-demo",
        "status": status,
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:01:00+00:00",
        "node_executions": nodes if nodes is not None else [{
            "node_id": "n1",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "2026-01-01T00:00:30+00:00",
            "error": None,
            "attempt_count": 2,
            "automatic_retry_count": 1,
            "output_repair_count": 0,
            "next_attempt_trigger": "auto_retry",
            "rejection_count": 0,
            "reject_upstream_count": 0,
            "attempt_history": [{
                "attempt_number": 1,
                "trigger": "initial",
                "status": "failed",
                "error": "boom",
                "started_at": "2026-01-01T00:00:00+00:00",
                "completed_at": "2026-01-01T00:00:10+00:00",
                "automatic_retry_count": 0,
                "output_repair_count": 0,
            }],
            # 载荷字段：裁剪必须丢掉它。
            "summary": "小说正文不该进仓库",
            "outputs": {"x": "y"},
        }],
    }


def test_trim_preserves_the_profile_field_by_field() -> None:
    """裁剪后画像必须逐字段相同——这是「裁剪没漏字段」的唯一硬判据。"""
    payload = _run_payload()
    trimmed = exporter.trim_run(payload)
    assert exporter.verify_trim_preserves_profile(
        payload, trimmed, "run-aaaa") == []


def test_trim_drops_payload_fields() -> None:
    """正文/轨迹/token 明细不进仓库。"""
    trimmed = exporter.trim_run(_run_payload())
    assert exporter.find_forbidden_fields(trimmed) == set()
    node = trimmed["node_executions"][0]
    assert "summary" not in node and "outputs" not in node


def test_trim_dropping_a_profile_field_is_detected() -> None:
    """反向验证：抽掉一个画像字段必须被判出来。

    没有这条，「verify_trim_preserves_profile 会拒绝坏裁剪」就只是一句注释。
    ``automatic_retry_count`` 直接影响失败画像里的重试统计，是典型会被
    「精简」掉的字段。
    """
    payload = _run_payload()
    trimmed = exporter.trim_run(payload)
    for node in trimmed["node_executions"]:
        node.pop("automatic_retry_count", None)
    problems = exporter.verify_trim_preserves_profile(payload, trimmed, "run-aaaa")
    assert problems, "抽掉画像字段后没有报差异"


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """``--dry-run`` 只打印，不落盘——它常被用来「先看看会写什么」。"""
    source = tmp_path / "src"
    runs = source / "wf-demo" / "runs"
    runs.mkdir(parents=True)
    (runs / "run-aaaa.json").write_text(
        json.dumps(_run_payload()), encoding="utf-8")
    dest = tmp_path / "dest"

    code = exporter.export(
        source, dest, "", set(), limit=3, dry_run=True)
    assert code == 0
    assert not dest.exists(), "dry-run 写盘了"


def _all_failed_payload() -> dict:
    """全部尝试都失败的 run：p=1.0 是比例判据的另一处退化点（R53）。"""
    payload = _run_payload(status="failed")
    node = payload["node_executions"][0]
    node["status"] = "failed"
    node["attempt_count"] = 1
    node["automatic_retry_count"] = 0
    node["attempt_history"] = [{
        "attempt_number": 1,
        "trigger": "initial",
        "status": "failed",
        "error": "boom",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:00:10+00:00",
        "automatic_retry_count": 0,
        "output_repair_count": 0,
    }]
    return payload


def test_export_writes_meta_and_reports_half_width(tmp_path: Path, capsys) -> None:
    """正常导出要落 snapshot-meta.json，并打印半宽结论（R53）。"""
    source = tmp_path / "src"
    runs = source / "wf-demo" / "runs"
    runs.mkdir(parents=True)
    (runs / "run-aaaa.json").write_text(
        json.dumps(_run_payload()), encoding="utf-8")
    dest = tmp_path / "dest"

    code = exporter.export(source, dest, "", set(), limit=3, dry_run=False)
    assert code == 0
    meta = json.loads((dest / "snapshot-meta.json").read_text(encoding="utf-8"))
    assert "totals" in meta and meta["totals"]["runs"] == 1
    captured = capsys.readouterr()
    assert "[half-width]" in (captured.out + captured.err), (
        "导出后没有打印半宽结论：重导时最容易忘的就是这笔账"
    )


def _thick_payload(*, attempts: int = 400, failed: int = 10) -> dict:
    """构造一份「厚到反向验证失效」的 run（所需余量 1.53 ≤ margin 2）。

    用 ``attempt_count`` + 完整的 ``attempt_history`` 凑出来：画像的
    ``attempts`` 取 ``max(attempt_count, len(history))``，``failed`` 是
    ``attempts - completed``，所以两边都要给，否则会出现「计数说有 400 次、
    明细里只有 1 条」这种自相矛盾的样本——那是另一个测试的事。
    """
    payload = _run_payload()
    node = payload["node_executions"][0]
    node["status"] = "completed"
    node["attempt_count"] = attempts
    node["automatic_retry_count"] = failed
    history = []
    for index in range(attempts):
        status = "failed" if index < failed else "completed"
        history.append({
            "attempt_number": index + 1,
            "trigger": "initial" if index == 0 else "auto_retry",
            "status": status,
            "error": "boom" if status == "failed" else None,
            "started_at": "2026-01-01T00:00:00+00:00",
            "completed_at": "2026-01-01T00:00:10+00:00",
            "automatic_retry_count": 0,
            "output_repair_count": 0,
        })
    node["attempt_history"] = history
    return payload


def test_strict_half_width_turns_the_warning_into_a_failure(tmp_path: Path) -> None:
    """``--strict-half-width`` 让告警变成退出码 1。

    用的是一份**厚到反向验证失效**的快照（400 次尝试 / 10 失败 → 所需余量
    1.53 ≤ 2）。这正是 R52 §9-7 记下的耦合：样本越厚，``--margin 2`` 那一步
    越不触发 7。默认只告警，strict 时按不合格退出。
    """
    source = tmp_path / "src"
    runs = source / "wf-demo" / "runs"
    runs.mkdir(parents=True)
    (runs / "run-aaaa.json").write_text(
        json.dumps(_thick_payload()), encoding="utf-8")
    dest = tmp_path / "dest"

    code = exporter.export(
        source, dest, "", set(), limit=3, dry_run=False, strict_half_width=True)
    assert code == 1, "strict 模式下所需余量不足 2 仍返回 0"


def test_default_mode_only_warns_when_half_width_is_exhausted(tmp_path: Path) -> None:
    """默认不拦：同样的快照只打告警、仍然落盘成功。

    重导是一个**已经想好了要改快照**的动作，在这一步硬拦会让人反复手动绕开。
    告警的价值在于让人看见「这次重导把反向验证弄失效了」，处置（调 limit
    还是接受）由人决定。
    """
    source = tmp_path / "src"
    runs = source / "wf-demo" / "runs"
    runs.mkdir(parents=True)
    (runs / "run-aaaa.json").write_text(
        json.dumps(_thick_payload()), encoding="utf-8")
    dest = tmp_path / "dest"

    code = exporter.export(source, dest, "", set(), limit=3, dry_run=False)
    assert code == 0
    assert (dest / "snapshot-meta.json").is_file()


def test_strict_half_width_does_not_affect_a_healthy_snapshot(tmp_path: Path) -> None:
    """合格时 strict 不该改变结果——它只把告警升级，不是「一律从严」。"""
    source = tmp_path / "src"
    runs = source / "wf-demo" / "runs"
    runs.mkdir(parents=True)
    # 少量尝试、全部失败 → 所需余量 95，远大于 2 → 反向验证仍有效。
    (runs / "run-aaaa.json").write_text(
        json.dumps(_all_failed_payload()), encoding="utf-8")
    dest = tmp_path / "dest"

    code = exporter.export(
        source, dest, "", set(), limit=3, dry_run=False, strict_half_width=True)
    assert code == 0


def test_exporter_and_gate_agree_on_the_current_snapshot() -> None:
    """当前入库快照上，导出脚本与闸门脚本的结论必须能对上。

    这是这条改动的实战意义：下一轮重导时，导出脚本会在落盘后立刻告诉你
    「所需的余量还剩多少」，而不用等 CI 反向验证那一步红/绿来间接推断。
    """
    from scripts.check_live_snapshot_gate import sample_size_margin_needed

    meta_path = REPO_ROOT / "tests" / "fixtures" / "live_snapshot" / "snapshot-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    totals = meta["totals"]
    ok, message = exporter.half_width_budget(totals["attempts"], totals["failed"])
    # 当前快照（R52 重导，255/10）判「仍能触发 7 但余量很小」。
    assert ok is True, message
    assert "越线" in message, message
    needed = sample_size_margin_needed(totals["attempts"], totals["failed"])
    assert needed is not None and needed > exporter.REVERSE_VALIDATION_MARGIN
