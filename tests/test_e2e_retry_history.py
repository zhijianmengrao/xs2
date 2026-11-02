"""e2e 重跑率的跨 run 趋势（R78）。

R74 只让**单次** run 的重跑频率可机读；本文件钉住跨 run 那一层。判据边界是
用户拍定的：**只判历史数据有效，不判趋势好坏**——因为 e2e 只有 10 个场景，
1 次重跑 = 10 个百分点，样本量撑不起「变差」的判决（R63/R69）。

最容易冒充的三条（R75/R76/R77 的同族教训）：

1. **历史坏了当「没有样本」（3）**——人会更勤快地跑 e2e，而文件根本没被读过；
2. **历史坏了当「趋势不合格」（1）**——人去查 e2e 抖动，处置全歪；
3. **跳过坏条目继续渲染**——趋势表只显示剩下的好条目，「0 次重跑」看起来和
   真实数据一模一样。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import e2e_retry_history as history

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
COMMITTED = (REPO_ROOT / "tests" / "fixtures" / "e2e_retry_history"
             / "history.json")


def _metrics(total: int = 10, retried: int = 0) -> dict:
    """一份合法的 e2e metrics payload；``retried`` 个场景各多跑一次。"""
    scenarios = [
        {
            "name": f"scenario_{index}",
            "passed": True,
            "attempts": 2 if index < retried else 1,
            "first_failure": "第一次红了" if index < retried else "",
        }
        for index in range(total)
    ]
    return {
        "schema": 1,
        "total": total,
        "passed": total,
        "failed": 0,
        "retried": retried,
        "scenarios": scenarios,
    }


def _entry(run_id: str, total: int = 10, retried: int = 0,
           exported_at: str = "2026-11-01T00:00:00+00:00") -> dict:
    return {
        "run_id": run_id,
        "exported_at": exported_at,
        **history.entry_from_metrics(_metrics(total=total, retried=retried)),
    }


def _write_history(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": 1, "history": entries}, ensure_ascii=False),
        encoding="utf-8")


def _metrics_file(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _backend_steps() -> list[dict]:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    return list(workflow["jobs"]["backend"]["steps"])


# ---------------------------------------------------------------- record
def test_record_creates_a_history_with_one_round(tmp_path: Path) -> None:
    source = _metrics_file(tmp_path / "metrics.json", _metrics())
    target = tmp_path / "history.json"

    assert history.record(source, target) == 0

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["schema"] == 1
    assert len(payload["history"]) == 1
    entry = payload["history"][0]
    assert entry["total"] == 10 and entry["attempts"] == 10
    assert entry["retried"] == 0
    assert entry["run_id"] == entry["exported_at"]


def test_record_replaces_the_same_run_id_instead_of_appending(
        tmp_path: Path) -> None:
    target = tmp_path / "history.json"
    assert history.record(
        _metrics_file(tmp_path / "a.json", _metrics(retried=0)), target,
        run_id="round-1") == 0
    assert history.record(
        _metrics_file(tmp_path / "b.json", _metrics(retried=1)), target,
        run_id="round-1") == 0

    entries = history.load_history(target)
    assert len(entries) == 1, "同一个 run_id 必须是覆盖，不是追加"
    assert entries[0]["retried"] == 1


def test_record_keeps_the_first_export_time_when_the_observation_is_identical(
        tmp_path: Path, monkeypatch) -> None:
    """同一 run 重跑且观测一致：文件逐字节不变，CI 写回不会多一次提交。

    R89 实测：``record`` 每次都写新的 ``exported_at``，所以 R88 的「内容不变
    就不提交」在重跑时并不成立——history 多一条时间戳不同的记录，轮数没变
    但会多一次非空提交。修法是重跑且观测一致时保留首次时间戳。
    """
    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T00:00:00+00:00")
    target = tmp_path / "history.json"
    source = _metrics_file(tmp_path / "m.json", _metrics(retried=1))
    assert history.record(source, target, run_id="ci-1") == 0
    first_bytes = target.read_bytes()

    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T09:00:00+00:00")
    assert history.record(source, target, run_id="ci-1") == 0

    assert target.read_bytes() == first_bytes, "观测一致的重跑不应改写时间戳"
    entries = history.load_history(target)
    assert len(entries) == 1
    assert entries[0]["exported_at"] == "2026-11-01T00:00:00+00:00"


def test_record_updates_the_export_time_when_the_observation_changes(
        tmp_path: Path, monkeypatch) -> None:
    """反向边界：重跑真的带来新观测时，时间戳必须更新（不是无条件保留）。"""
    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T00:00:00+00:00")
    target = tmp_path / "history.json"
    assert history.record(
        _metrics_file(tmp_path / "a.json", _metrics(retried=0)), target,
        run_id="ci-1") == 0

    monkeypatch.setattr(
        history, "_iso_now", lambda: "2026-11-01T09:00:00+00:00")
    assert history.record(
        _metrics_file(tmp_path / "b.json", _metrics(retried=2)), target,
        run_id="ci-1") == 0

    entries = history.load_history(target)
    assert len(entries) == 1
    assert entries[0]["retried"] == 2
    assert entries[0]["exported_at"] == "2026-11-01T09:00:00+00:00"


def test_record_trims_to_the_window(tmp_path: Path) -> None:
    """窗口常量是 40：写入第 41 轮时最早一轮必须掉出去。

    两条一起钉：值等于 40（改常量要改这里），以及**边界行为**（多写一轮
    恰好掉最老的一轮）——R69：「数等于常量」不等于「数是判决的边界」。
    """
    assert history.MAX_ROUNDS == 40
    target = tmp_path / "history.json"
    for index in range(history.MAX_ROUNDS + 1):
        assert history.record(
            _metrics_file(tmp_path / f"{index}.json", _metrics()),
            target, run_id=f"r{index}") == 0

    entries = history.load_history(target)
    assert len(entries) == history.MAX_ROUNDS
    assert entries[0]["run_id"] == "r1"
    assert entries[-1]["run_id"] == f"r{history.MAX_ROUNDS}"


def test_max_rounds_env_override_and_invalid(monkeypatch, capsys) -> None:
    """R109：保留期可配置；非法值必须告警并退回默认，不能静默生效。"""
    monkeypatch.delenv(history.MAX_ROUNDS_ENV, raising=False)
    assert history.max_rounds() == history.MAX_ROUNDS == 40

    monkeypatch.setenv(history.MAX_ROUNDS_ENV, "80")
    assert history.max_rounds() == 80

    monkeypatch.setenv(history.MAX_ROUNDS_ENV, "abc")
    assert history.max_rounds() == 40
    assert "不是整数" in capsys.readouterr().err

    monkeypatch.setenv(history.MAX_ROUNDS_ENV, "2")
    assert history.max_rounds() == 40
    assert "超出" in capsys.readouterr().err

    monkeypatch.setenv(history.MAX_ROUNDS_ENV, "1001")
    assert history.max_rounds() == 40
    assert "超出" in capsys.readouterr().err


def test_record_uses_the_configured_window(tmp_path: Path, monkeypatch,
                                          capsys) -> None:
    """R109：record 的裁剪与文案都必须走 max_rounds()，不能各读各的。"""
    monkeypatch.setenv(history.MAX_ROUNDS_ENV, "4")
    target = tmp_path / "history.json"
    for index in range(5):
        assert history.record(
            _metrics_file(tmp_path / f"{index}.json", _metrics()),
            target, run_id=f"r{index}") == 0

    entries = history.load_history(target)
    assert len(entries) == 4
    assert entries[0]["run_id"] == "r1"
    assert entries[-1]["run_id"] == "r4"
    assert "/4 轮" in capsys.readouterr().out


def test_record_check_only_does_not_write(tmp_path: Path, capsys) -> None:
    """PR 预检：校验 + 打印将写入的条目，但一个字节都不落盘（R92）。"""
    source = _metrics_file(tmp_path / "metrics.json", _metrics())
    target = tmp_path / "history.json"

    assert history.record(source, target, run_id="pr-7", check_only=True) == 0

    assert not target.exists(), "check-only 不能创建历史文件"
    out = capsys.readouterr().out
    assert "check-only" in out and "pr-7" in out
    assert f"1/{history.MAX_ROUNDS}" in out

    # 同一份输入随后真的写入：预检说的形状与实际写出来的形状一致。
    assert history.record(source, target, run_id="pr-7") == 0
    assert len(history.load_history(target)) == 1


def test_record_check_only_uses_the_same_exit_codes(tmp_path: Path) -> None:
    """check-only 不发明新码：坏 metrics 仍是 4、缺 metrics 仍是 3。"""
    target = tmp_path / "history.json"
    broken = _metrics(total=10)
    broken["failed"] = 3          # passed + failed != total
    bad = _metrics_file(tmp_path / "bad.json", broken)

    assert history.record(bad, target, run_id="pr-1", check_only=True) == 4
    assert history.record(
        tmp_path / "missing.json", target, run_id="pr-1",
        check_only=True) == 3
    assert not target.exists()


def test_record_validates_the_result_before_writing(
        tmp_path: Path, monkeypatch) -> None:
    """写入前的自校验：算出来的历史过不了校验器时，文件逐字节不动（R92）。"""
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r0")])
    before = target.read_bytes()

    original = history.validate_history
    calls = {"n": 0}

    def flaky(payload: object) -> list[dict]:
        calls["n"] += 1
        if calls["n"] >= 2:       # 1 = 读历史，2 = 写入前自校验
            raise history.HistoryError("注入：算出来的历史无效")
        return original(payload)

    monkeypatch.setattr(history, "validate_history", flaky)

    assert history.record(
        _metrics_file(tmp_path / "m.json", _metrics()), target,
        run_id="r1") == 4
    assert target.read_bytes() == before, "校验失败时不能留下半份历史"


def test_cli_wires_check_only(tmp_path: Path) -> None:
    target = tmp_path / "history.json"
    code = history.main([
        "record", str(_metrics_file(tmp_path / "metrics.json", _metrics())),
        "--history", str(target),
        "--run-id", "pr-1",
        "--check-only",
    ])
    assert code == 0
    assert not target.exists()
def test_record_writes_the_source(tmp_path: Path) -> None:
    """R93：条目自己说清来源；不传就记本机（显式导出的默认路径）。"""
    target = tmp_path / "history.json"
    assert history.record(
        _metrics_file(tmp_path / "a.json", _metrics()), target,
        run_id="ci-1", source="ci") == 0
    assert history.record(
        _metrics_file(tmp_path / "b.json", _metrics()), target,
        run_id="local-1") == 0

    entries = history.load_history(target)
    assert [entry["source"] for entry in entries] == ["ci", "local"]


def test_record_rejects_unknown_source(tmp_path: Path) -> None:
    target = tmp_path / "history.json"
    assert history.record(
        _metrics_file(tmp_path / "m.json", _metrics()), target,
        run_id="r1", source="hosted") == 2
    assert not target.exists()


def test_validate_history_accepts_legacy_entries_without_source() -> None:
    """旧条目没有 source：合法，按「未标注」报告（不猜来源）。"""
    entries = history.validate_history({"schema": 1, "history": [_entry("old")]})
    assert "source" not in entries[0]


def test_validate_history_rejects_unknown_source() -> None:
    bad = _entry("r1")
    bad["source"] = "hosted"
    with pytest.raises(history.HistoryError):
        history.validate_history({"schema": 1, "history": [bad]})


def test_check_reports_the_source_mix(tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    _write_history(target, [
        {**_entry("a"), "source": "ci"},
        {**_entry("b"), "source": "ci"},
        {**_entry("c"), "source": "local"},
        _entry("d"),
    ])

    assert history.check(target) == 0
    out = capsys.readouterr().out
    assert "CI 2" in out and "本机 1" in out and "未标注 1" in out


def test_source_report_does_not_change_the_verdict(tmp_path: Path) -> None:
    """来源是只读展示：有没有 source（或全都没有）退出码都必须是 0。"""
    with_source = tmp_path / "with.json"
    _write_history(with_source, [
        {**_entry("a"), "source": "ci"},
        {**_entry("b"), "source": "local"},
    ])
    legacy = tmp_path / "legacy.json"
    _write_history(legacy, [_entry("a"), _entry("b")])

    assert history.check(with_source) == 0
    assert history.check(legacy) == 0


def test_cli_wires_source(tmp_path: Path) -> None:
    target = tmp_path / "history.json"
    metrics = _metrics_file(tmp_path / "metrics.json", _metrics())
    assert history.main([
        "record", str(metrics), "--history", str(target),
        "--run-id", "ci-1", "--source", "ci",
    ]) == 0
    assert history.load_history(target)[0]["source"] == "ci"

    assert history.main([
        "record", str(metrics), "--history", str(target),
        "--run-id", "ci-2", "--source", "hosted",
    ]) == 2


def test_record_refuses_to_append_onto_a_corrupt_history(
        tmp_path: Path) -> None:
    """坏历史不能被静默覆盖——那会把「数据坏了」改写成「刚记了一轮」。"""
    target = tmp_path / "history.json"
    target.write_text("{not json", encoding="utf-8")

    assert history.record(
        _metrics_file(tmp_path / "m.json", _metrics()), target) == 4
    assert target.read_text(encoding="utf-8") == "{not json"


def test_record_rejects_contradictory_metrics_counts(tmp_path: Path) -> None:
    payload = _metrics()
    payload["failed"] = 1  # passed 10 + failed 1 != total 10
    target = tmp_path / "history.json"

    assert history.record(
        _metrics_file(tmp_path / "m.json", payload), target) == 4
    assert not target.exists(), "坏 metrics 不能留下半份历史"


def test_record_rejects_a_bool_where_a_count_belongs(tmp_path: Path) -> None:
    """``True``/``False`` 是 ``int`` 的子类；当作 1/0 会凭空造出一轮。

    计数必须**自洽**才能咬住这条：``total=False`` 配 0/0/0、空 scenarios 时，
    去掉 ``_is_int`` 的 bool 检查会得到一轮「0 场景 0 重跑」的历史。
    """
    payload = {"schema": 1, "total": False, "passed": 0, "failed": 0,
               "retried": 0, "scenarios": []}
    target = tmp_path / "history.json"
    assert history.record(
        _metrics_file(tmp_path / "m.json", payload), target) == 4
    assert not target.exists()


# ---------------------------------------------------------------- check
def test_check_renders_the_recent_rounds(tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r1"), _entry("r2", retried=1)])
    assert history.check(target) == 0
    out = capsys.readouterr().out
    assert "最近 2 / 2 轮" in out
    assert "| r2 |" in out
    assert "10.0%" in out and "0.0%" in out


def test_check_says_it_has_no_judgement_power(tmp_path: Path, capsys) -> None:
    """0 退出不等于通过：输出必须自己说出「这步没有判定力」。"""
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r1")])
    assert history.check(target) == 0
    out = capsys.readouterr().out
    assert "不判趋势好坏" in out
    assert "1 次重跑 = 10 个百分点" in out
    assert "退出 0 只表示数据可读" in out


def test_check_computes_the_resolution_from_the_latest_total(
        tmp_path: Path, capsys) -> None:
    """分辨率是算出来的，不是写死的 10：20 个场景时 1 次重跑 = 5 个百分点。"""
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r1", total=20)])
    assert history.check(target) == 0
    assert "1 次重跑 = 5 个百分点" in capsys.readouterr().out


def test_check_limit_only_affects_display(tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r1"), _entry("r2")])
    assert history.main(["check", "--history", str(target),
                         "--limit", "1"]) == 0
    out = capsys.readouterr().out
    assert "最近 1 / 2 轮" in out
    assert "| r1 |" not in out and "| r2 |" in out


def test_check_exits_three_without_a_history_file(
        tmp_path: Path, capsys) -> None:
    assert history.check(tmp_path / "absent.json") == 3
    assert "不存在" in capsys.readouterr().err


def test_check_exits_three_for_an_empty_history(tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    _write_history(target, [])
    assert history.check(target) == 3
    assert "历史为空" in capsys.readouterr().err


def test_check_exits_four_on_unparseable_history_not_eight(
        tmp_path: Path, capsys) -> None:
    """坏 JSON 是元数据问题（4），不是「判据算术失败」（8）也不是「无样本」（3）。

    ``json.JSONDecodeError`` 是 ``ValueError`` 的子类；若把解析放在一个
    ``except ValueError`` 的判据外壳里，这一格会变成 8——读的人就去查判据了。
    """
    target = tmp_path / "history.json"
    target.write_text("{not json", encoding="utf-8")
    code = history.check(target)
    assert code == 4 and code != 8
    assert "无法解析" in capsys.readouterr().err


def test_check_exits_four_on_contradictory_counts(
        tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    broken = _entry("r1")
    broken["passed"] = 9  # 9 + 0 != 10
    _write_history(target, [broken])

    code = history.check(target)
    assert code == 4, f"计数矛盾必须是 4（元数据问题），实际 {code}"
    assert "计数矛盾" in capsys.readouterr().err


def test_check_exits_four_on_duplicate_run_ids(tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    _write_history(target, [_entry("r1"), _entry("r1")])
    assert history.check(target) == 4
    assert "重复" in capsys.readouterr().err


def test_check_exits_four_when_the_history_path_is_a_directory(
        tmp_path: Path, capsys) -> None:
    target = tmp_path / "history.json"
    target.mkdir()
    assert history.check(target) == 4
    assert "不是文件" in capsys.readouterr().err


def test_check_rejects_bad_json_even_when_one_entry_would_render(
        tmp_path: Path, capsys) -> None:
    """跳过坏条目继续渲染是最隐蔽的一种：剩下的好条目会装成完整趋势。"""
    target = tmp_path / "history.json"
    payload = {"schema": 1, "history": [_entry("r1"), {"run_id": "r2"}]}
    target.write_text(json.dumps(payload), encoding="utf-8")
    assert history.check(target) == 4
    assert "r2" not in capsys.readouterr().out


# ---------------------------------------------------------------- 接线
def test_ci_checks_the_committed_history_file() -> None:
    """CI 必须只读校验**入库的**历史；文件本身也要能通过 check。

    没有这条，趋势可以悄悄停在某一轮——CI 全绿，而跨 run 那一层早就断了。
    """
    # 只定位 **check** 那一步：R92 之后 backend 里还有一处 `record --check-only`
    # 的 PR 预检（它不读结果、不写文件），不能把两者算成同一处。
    hits = [
        step for step in _backend_steps()
        if "e2e_retry_history.py check" in str(step.get("run", ""))
    ]
    assert len(hits) == 1, (
        "backend job 必须且只能有一处校验重跑历史"
        f"（实际 {len(hits)} 处）")
    run = str(hits[0]["run"])
    assert "check" in run
    assert "tests/fixtures/e2e_retry_history/history.json" in run
    assert "GITHUB_STEP_SUMMARY" in run
    assert hits[0].get("if") == "always()", (
        "e2e 失败时更需要看历史是否有效，校验步骤必须 always()")
    assert "secrets." not in json.dumps(hits[0], ensure_ascii=False)

    assert COMMITTED.is_file(), f"趋势历史没有入库：{COMMITTED}"
    assert history.load_history(COMMITTED), "入库的历史不能是空的"
