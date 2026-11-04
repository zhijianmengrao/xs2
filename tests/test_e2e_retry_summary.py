"""R130：e2e step summary 的坏数据边界。

``e2e_retry_summary`` 在 CI 里以 ``if: always()`` 追加 step summary，职责是
「把 metrics 变可读」，**不判失败**。R74 只钉住了顶层三种异常（缺文件 /
JSON 坏 / 顶层非对象）；内层字段坏（``scenarios`` 不是列表、条目不是对象、
``attempts`` 不是整数）会抛 ``AttributeError``/``ValueError``，让一个可观测
性步骤以 traceback 判红——而它自己的说明把「损坏」承诺成「可见说明 + 退出
0」。本文件把这条契约补到内层，并钉住表格转义（``_cell`` 此前零覆盖）。

边界不是「校验 metrics 的业务有效性」：缺省字段仍按 0 渲染，与 R74 的兼容
行为一致；只有**出现但形状不对**的值才转成可见说明。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import e2e_retry_summary as summary


def _payload(**overrides) -> dict:
    payload = {
        "schema": 1, "total": 3, "passed": 3, "failed": 0, "retried": 1,
        "scenarios": [
            {"name": "clean", "passed": True, "attempts": 1,
             "first_failure": ""},
            {"name": "flaky", "passed": True, "attempts": 2,
             "first_failure": "第一次红了"},
            {"name": "steady", "passed": True, "attempts": 1,
             "first_failure": ""},
        ],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "e2e-metrics.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 渲染契约


def test_render_escapes_pipes_and_newlines_in_table_cells() -> None:
    """竖线与换行会破坏表格：两个单元格都要转义（R130 前零覆盖）。"""
    payload = _payload(
        retried=1,
        scenarios=[{
            "name": "a|b", "passed": True, "attempts": 2,
            "first_failure": "第一行\n第二行",
        }])
    text = summary.render(payload)
    assert "| a\\|b | 2 | 第一行 第二行 |" in text
    assert "| a|b |" not in text
    assert "第一行\n第二行" not in text


def test_zero_scenarios_renders_zero_without_a_table() -> None:
    """0 场景是合法形状：仍然给一行摘要，但不要空表头。"""
    text = summary.render(
        _payload(total=0, passed=0, failed=0, retried=0, scenarios=[]))
    assert "0 / 0 个场景重跑" in text
    assert "总尝试 0 次" in text
    assert "| 场景 |" not in text


def test_missing_fields_default_to_zero() -> None:
    """缺字段是兼容边界，不是坏形状：保持 R74 的「按 0 显示」。"""
    text = summary.render({})
    assert "0 / 0 个场景重跑" in text
    assert "总尝试 0 次，通过 0" in text


# ---------------------------------------------------------------- 坏形状


@pytest.mark.parametrize("overrides, needle", [
    ({"scenarios": {"flaky": 2}}, "scenarios 不是列表"),
    ({"scenarios": "flaky"}, "scenarios 不是列表"),
    ({"scenarios": ["flaky"]}, "scenarios[0] 不是对象"),
    ({"scenarios": [{"name": "x", "attempts": "2"}]},
     "attempts 不是 >=0 的整数"),
    ({"scenarios": [{"name": "x", "attempts": True}]},
     "attempts 不是 >=0 的整数"),
    ({"scenarios": [{"name": "x", "attempts": -1}]},
     "attempts 不是 >=0 的整数"),
])
def test_malformed_scenarios_are_visible_and_not_fatal(
        tmp_path: Path, capsys, overrides: dict, needle: str) -> None:
    """内层形状坏了：打印可见说明并退出 0，不是 traceback 判红。"""
    path = _write(tmp_path, _payload(**overrides))
    assert summary.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "形状无效" in out
    assert str(path) in out
    assert needle in out


@pytest.mark.parametrize("overrides, needle", [
    ({"total": "10"}, "total 不是 >=0 的整数"),
    ({"total": -1}, "total 不是 >=0 的整数"),
    ({"passed": True}, "passed 不是 >=0 的整数"),
    ({"retried": 1.5}, "retried 不是 >=0 的整数"),
])
def test_malformed_counts_are_visible_and_not_fatal(
        tmp_path: Path, capsys, overrides: dict, needle: str) -> None:
    """``True`` 能冒充 1、``"10"`` 能冒充 10：显示前先拒绝。"""
    path = _write(tmp_path, _payload(**overrides))
    assert summary.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "形状无效" in out
    assert needle in out


def test_render_raises_the_shape_error_instead_of_a_partial_table() -> None:
    """直接调用 render 也不能渲染半张表：异常让调用者看见同一道边界。"""
    with pytest.raises(summary.SummaryShapeError):
        summary.render(_payload(
            scenarios=[{"name": "x", "attempts": "2"}]))


def test_unparseable_payload_is_visible_and_not_fatal(
        tmp_path: Path, capsys) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    assert summary.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "无法解析" in out and str(path) in out


def test_non_object_payload_is_visible_and_not_fatal(
        tmp_path: Path, capsys) -> None:
    path = _write(tmp_path, [1, 2, 3])
    assert summary.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "顶层不是对象" in out


def test_usage_requires_exactly_one_path(capsys) -> None:
    """参数个数是用法错误（2），不是「metrics 坏」（0）。"""
    assert summary.main([]) == 2
    assert "用法" in capsys.readouterr().err
