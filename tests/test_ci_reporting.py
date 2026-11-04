"""R131：CI 报告层（step summary + 机读工件）的契约。

R98 把「一行 summary + 一份 JSON，且写失败只告警、不改判决」集中到
``scripts/ci_reporting.py``，三个 CI 脚本都依赖它，但这个模块此前零用例。
本文件钉住两件事：

- summary 必须真的是**一行**：git/HTTP 的错误详情常带换行，不压平就会
  在 step summary 里伪造出新的列表项；
- 展示层不得把 job 判死：路径写不进去、payload 序列化不了，都只告警。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import ci_reporting as report


# --------------------------------------------------------------- 环境与空路径
def test_default_summary_path_reads_the_ci_environment(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert report.default_summary_path() is None

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "")
    assert report.default_summary_path() is None, "空串是「没有 summary」，不是当前目录"

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", "step.md")
    assert report.default_summary_path() == Path("step.md")


def test_none_paths_are_no_ops(capsys: pytest.CaptureFixture) -> None:
    report.emit_summary(None, "ci-1", "written", "x")
    report.emit_result(None, {"x": object()})

    assert capsys.readouterr().err == ""


# ------------------------------------------------------------------- step summary
def test_summary_appends_one_exact_bullet(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    summary.write_text("先有的行\n", encoding="utf-8")

    report.emit_summary(summary, "ci-1", "written", "历史 1/80 轮")

    assert summary.read_text(encoding="utf-8") == (
        "先有的行\n"
        "- `ci-1` — **written**：历史 1/80 轮\n")


def test_summary_flattens_newlines_in_every_field(tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"

    report.emit_summary(
        summary, "ci-1\n- forged", "written\n- forged",
        "fatal: one\nfatal: two\r\nthird\rfourth")

    text = summary.read_text(encoding="utf-8")
    assert text.splitlines() == [
        "- `ci-1 - forged` — **written - forged**："
        "fatal: one fatal: two third fourth"]


def test_summary_write_failure_only_warns(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    report.emit_summary(
        tmp_path / "no_such_dir" / "summary.md", "ci-1", "written", "x")

    assert "step summary 写入失败" in capsys.readouterr().err


def test_summary_encoding_failure_only_warns(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    report.emit_summary(tmp_path / "summary.md", "ci-1", "written", "\ud800")

    assert "step summary 写入失败" in capsys.readouterr().err


# -------------------------------------------------------------------- 机读工件
def test_result_writes_exact_bytes_and_replaces_atomically(
        tmp_path: Path) -> None:
    result = tmp_path / "nested" / "result.json"

    report.emit_result(result, {"schema": 1, "detail": "中文\n行", "ok": True})
    report.emit_result(result, {"schema": 2, "ok": False})

    assert result.read_text(encoding="utf-8") == (
        '{\n'
        '  "schema": 2,\n'
        '  "ok": false\n'
        '}\n')
    assert not list(result.parent.glob("*.tmp")), "原子替换后不能留下临时文件"


def test_result_keeps_the_raw_multiline_detail(tmp_path: Path) -> None:
    """summary 压平只影响展示；机读工件的 detail 仍是原文。"""
    result = tmp_path / "result.json"

    report.emit_result(result, {"detail": "fatal: one\nfatal: two"})

    assert json.loads(result.read_text(encoding="utf-8"))["detail"] == (
        "fatal: one\nfatal: two")


def test_result_write_failure_only_warns_and_leaves_no_tmp(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    result = tmp_path / "result.json"
    result.mkdir()

    report.emit_result(result, {"x": 1})

    assert "结果工件写入失败" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.tmp"))


def test_result_encoding_failure_only_warns_and_leaves_no_tmp(
        tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    result = tmp_path / "result.json"

    report.emit_result(result, {"detail": "\ud800"})

    assert "结果工件写入失败" in capsys.readouterr().err
    assert not result.exists()
    assert not list(tmp_path.glob("*.tmp"))


def _circular_payload() -> dict:
    payload: dict = {}
    payload["self"] = payload
    return payload


@pytest.mark.parametrize("payload", [
    pytest.param({"path": Path("x")}, id="not-json-serializable"),
    pytest.param(_circular_payload(), id="circular-reference"),
])
def test_result_serialization_failure_only_warns(
        tmp_path: Path, capsys: pytest.CaptureFixture, payload: dict) -> None:
    result = tmp_path / "result.json"

    report.emit_result(result, payload)

    assert "结果工件序列化失败" in capsys.readouterr().err
    assert not result.exists()
    assert not list(tmp_path.glob("*.tmp"))
