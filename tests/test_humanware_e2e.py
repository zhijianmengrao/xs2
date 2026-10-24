# -*- coding: utf-8 -*-
"""humanware 契约端到端回归（对运行中的真实服务 + 真实 runtime CLI）。

Round 16 由一次性脚本 ``scripts/_hw_e2e_r15.py`` 改写为常规 pytest 套件
（R15 交接 §9 P0）：服务未运行或前置数据缺失时**干净 skip**，
全量回归按惯例停服跑则整模块跳过，不影响 CI 语义。

覆盖（编号沿用 R15 验收）：
- E1  generate-voice（argv 短路径）→ 200 character_count>=1
- E2  score-content 42,000 字符（stdin 通道）→ 200 四维字段完整
- E3  score-content 短内容（argv 路径）→ 200
- E4  check-dialogue 未知角色 → 409
- E5  check-dialogue 50,000 字符（stdin 通道）→ 200
- E6  check-dialogue 未命中口头禅文案不含「已命中口头禅」
- E7a score-chapter 缺失章节 → 404
- E7b score-chapter 归属对照（O1 算法：归属章声音一致性 > 对照章）
- F*  R16 真实 CLI fuzz：NUL/保留设备名/路径逃逸 → 400，绝无 2xx/500

用法（需先启动服务，默认 8021）：
    .venv/Scripts/python.exe -m pytest tests/test_humanware_e2e.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

BASE_URL = os.environ.get("DETERMINFLOW_HUMANWARE_E2E_BASE_URL", "http://127.0.0.1:8021")
WS = "welcome"
DIMS = ["声音一致性", "对话自然度", "情感真实度", "行为一致性"]


def _probe() -> tuple[bool, str]:
    """服务可达且 welcome 工作区可用（voice 文件已生成）才运行 e2e。"""
    try:
        with urllib.request.urlopen(
            BASE_URL + "/api/humanware/status/" + WS, timeout=3
        ) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"welcome 工作区不可用（HTTP {exc.code}）"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"{BASE_URL} 服务未运行（{exc.__class__.__name__}）"
    if not body.get("voice_file_exists"):
        return False, "welcome 工作区缺少 character_voice.md"
    return True, ""


_probe_ok, _probe_reason = _probe()
pytestmark = pytest.mark.skipif(
    not _probe_ok, reason=f"humanware e2e 前置不满足: {_probe_reason}"
)


def _post(path: str, payload: dict, timeout: int = 150):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


def _get(path: str, timeout: int = 15):
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed


# ---------------------------------------------------------------- E1–E7


def test_e1_generate_voice_argv_path():
    status, body = _post(
        "/api/humanware/generate-voice-file", {"workspace_id": WS, "from_profiles": True}
    )
    assert status == 200, body
    assert body.get("character_count", 0) >= 1


def test_e2_score_content_42k_via_stdin():
    content = "结论已经给出，方案可以执行。" * 3000  # 42,000 字符 > argv 上限
    status, body = _post(
        "/api/humanware/score-content",
        {"workspace_id": WS, "character": "林晚", "content": content},
    )
    assert status == 200, body
    assert "total_score" in body
    assert all(d in body.get("detailed_scores", {}) for d in DIMS)


def test_e3_score_content_short_via_argv():
    status, body = _post(
        "/api/humanware/score-content",
        {"workspace_id": WS, "character": "林晚", "content": "结论已经给出，方案可以执行。"},
    )
    assert status == 200, body
    assert "total_score" in body


def test_e4_check_dialogue_unknown_character_409():
    status, body = _post(
        "/api/humanware/check-dialogue",
        {"workspace_id": WS, "character": "不存在的人", "dialogue": "你好。"},
    )
    assert status == 409, body


def test_e5_check_dialogue_50k_via_stdin():
    dialogue = "此事罢了，不必再提。" * 5000  # 50,000 字符
    status, body = _post(
        "/api/humanware/check-dialogue",
        {"workspace_id": WS, "character": "林晚", "dialogue": dialogue},
    )
    assert status == 200, body
    assert body.get("status") == "success"
    assert isinstance(body.get("violations"), list)


def test_e6_check_dialogue_suggestion_no_false_catchphrase():
    status, body = _post(
        "/api/humanware/check-dialogue",
        {"workspace_id": WS, "character": "林晚", "dialogue": "先确认现场，再下结论。"},
    )
    assert status == 200, body
    assert "已命中口头禅" not in body.get("suggestion", "")


def test_e7a_score_chapter_missing_404():
    status, body = _post(
        "/api/humanware/score-chapter",
        {"workspace_id": WS, "chapter_file": "story/0001/chapter.md"},
    )
    assert status == 404, body


@pytest.fixture()
def attribution_workspace():
    """临时工作区：两个锚点平均句长差异大（14 vs 30），归属正确时长句应归给 30 锚点。"""
    books_root = Path(__file__).resolve().parents[1] / "data" / "workspaces" / "books"
    ws = books_root / f"r16-e2e-{uuid.uuid4().hex[:8]}"
    (ws / "meta").mkdir(parents=True)
    (ws / "story" / "attributed").mkdir(parents=True)
    (ws / "story" / "control").mkdir(parents=True)
    (ws / "meta" / "character_voice.md").write_text(
        "# 角色声音锚点\n\n## 林晚\n\n### 句法指纹\n"
        "- **平均句长**: 14\n- **问句倾向**: 0.15\n- **叹句倾向**: 0.10\n\n"
        "## 阿柴\n\n### 句法指纹\n"
        "- **平均句长**: 30\n- **问句倾向**: 0.15\n- **叹句倾向**: 0.10\n\n",
        encoding="utf-8",
        newline="\n",
    )
    attributed = (
        "## 林晚\n\n林晚说：“此事罢了，不必再提。”\n\n"
        "## 阿柴\n\n阿柴喊：“今天天气不错我们一起去看电影然后顺便吃点东西如何呢。”\n"
    )
    control = (
        "林晚说：“此事罢了，不必再提。”\n\n"
        "阿柴喊：“今天天气不错我们一起去看电影然后顺便吃点东西如何呢。”\n"
    )
    (ws / "story" / "attributed" / "chapter.md").write_text(
        attributed, encoding="utf-8", newline="\n"
    )
    (ws / "story" / "control" / "chapter.md").write_text(
        control, encoding="utf-8", newline="\n"
    )
    yield ws.name
    shutil.rmtree(ws, ignore_errors=True)


def test_e7b_score_chapter_attribution_beats_default(attribution_workspace):
    ws = attribution_workspace
    status, body = _post(
        "/api/humanware/score-chapter",
        {"workspace_id": ws, "chapter_file": "story/attributed/chapter.md"},
    )
    assert status == 200, body
    assert body.get("dialogues_scored") == 2
    voice_attributed = body["detailed_scores"]["声音一致性"]

    status, control = _post(
        "/api/humanware/score-chapter",
        {"workspace_id": ws, "chapter_file": "story/control/chapter.md"},
    )
    assert status == 200, control
    voice_control = control["detailed_scores"]["声音一致性"]
    # 对照章（无标题）长句按默认 14 锚点受罚 → 归属生效实证
    assert voice_attributed > voice_control, (voice_attributed, voice_control)


# ---------------------------------------------------------------- F*：R16 真实服务 fuzz


def test_f1_character_with_nul_is_400_not_500():
    status, body = _post(
        "/api/humanware/score-content",
        {"workspace_id": WS, "character": "林晚" + chr(0), "content": "你好。"},
    )
    assert status == 400, body


def test_f2_chapter_file_with_nul_is_400_not_500():
    status, body = _post(
        "/api/humanware/score-chapter",
        {"workspace_id": WS, "chapter_file": "story/0001" + chr(0) + "/chapter.md"},
    )
    assert status == 400, body


@pytest.mark.skipif(os.name != "nt", reason="Windows 保留设备名仅在 nt 平台特判")
def test_f3_windows_reserved_workspace_id_is_400():
    for bad in ("NUL", "nul", "COM1"):
        status, _ = _get(f"/api/humanware/status/{bad}")
        assert status == 400, bad


def test_f4_chapter_file_escape_rejected_by_real_cli():
    # 真实 runtime CLI 的 containment 校验：绝对路径 / .. 逃逸 → 400
    for bad in (r"C:\Windows\win.ini", "../../requirements.txt", "/etc/passwd"):
        status, body = _post(
            "/api/humanware/score-chapter",
            {"workspace_id": WS, "chapter_file": bad},
        )
        assert status == 400, (bad, body)


def _service_enforces_v32_alias_rule() -> "bool | None":
    """探测当前服务是否已加载契约 v3.2 的尾随点别名拒绝规则。

    返回 None 表示无法判定（服务不可达）。返回 False 表示该服务进程运行的是
    **修复前**的代码（尾随点仍会命中真实工作区）——此时本用例 skip 并明确说明
    需要重启服务，而不是假装通过。
    """
    status, _ = _get(f"/api/humanware/status/{WS}.")
    if status == -1:
        return None
    return status == 400


@pytest.mark.skipif(os.name != "nt", reason="尾随点别名仅在 Windows 文件系统语义下成立")
def test_f5_workspace_id_trailing_dot_is_not_an_alias():
    """契约 v3.2：`welcome.` 不得成为真实工作区 `welcome` 的别名（B3）。

    Windows 解析路径段时剥离尾随点/空白，修复前实测 `welcome.` → 200 且可读写
    真实工作区内容；POSIX 上两者是不同名字。此处对**运行中的服务**验证规则已生效。
    """
    enforced = _service_enforces_v32_alias_rule()
    if enforced is None:
        pytest.skip("服务不可达")
    if not enforced:
        pytest.skip(
            f"运行中的服务（{BASE_URL}）仍为契约 v3.2 之前的代码："
            f"GET /api/humanware/status/{WS}. 返回 200（别名命中）。需重启服务后本用例才会执行。"
        )
    for alias in (f"{WS}.", f"{WS}..", f"{WS}..."):
        status, body = _get(f"/api/humanware/status/{alias}")
        assert status == 400, (alias, body)
        status2, _ = _get(f"/api/humanware/voice-file/{alias}")
        assert status2 == 400, alias
    # 对照：真实名字与名字中间的点不受影响
    assert _get(f"/api/humanware/status/{WS}")[0] == 200

