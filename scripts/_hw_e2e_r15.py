# -*- coding: utf-8 -*-
"""Round 15 契约 v3 端到端验收（对运行中的 8021 实例，幂等）。

覆盖：
- E1  generate-voice（welcome/林晚，argv 短路径）→ 200 character_count=2
- E2  score-content 42,000 字符（stdin 通道，修复前 500 WinError 206）→ 200 且四维字段完整
- E3  score-content 短内容（argv 路径，行为不变）→ 200
- E4  check-dialogue 未知角色（修复前 500，B1）→ 409
- E5  check-dialogue 超长 50,000 字符（stdin 通道）→ 200 且契约字段完整
- E6  check-dialogue 未命中口头禅文案（B2 经 runtime-resources 真实 CLI）→ 不含「已命中口头禅」
- E7  score-chapter（O1 新归属算法端到端）→ 200 dialogues_scored>0

用法：.venv python scripts/_hw_e2e_r15.py
退出码：0 全部通过；1 存在失败。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8021"
WS = "welcome"

_failures: list[str] = []


def _post(path: str, payload: dict, timeout: int = 150):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
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


def _check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        _failures.append(name)


DIMS = ["声音一致性", "对话自然度", "情感真实度", "行为一致性"]


def main() -> int:
    # E1 generate（短路径）
    status, body = _post("/api/humanware/generate-voice-file",
                         {"workspace_id": WS, "from_profiles": True})
    _check("E1 generate-voice argv 路径",
           status == 200 and body.get("character_count", 0) >= 1,
           f"HTTP {status} {json.dumps(body, ensure_ascii=False)[:160]}")

    # E2 超长 content 经 stdin（修复前必然 500）
    long_content = "结论已经给出，方案可以执行。" * 3000  # 42,000 字符
    status, body = _post("/api/humanware/score-content",
                         {"workspace_id": WS, "character": "林晚", "content": long_content})
    ok = (status == 200 and "total_score" in body
          and all(d in body.get("detailed_scores", {}) for d in DIMS))
    _check("E2 score-content 42K 字符 stdin 通道", ok,
           f"HTTP {status} total={body.get('total_score')} grade={body.get('grade')}"
           if status == 200 else f"HTTP {status} {json.dumps(body, ensure_ascii=False)[:200]}")

    # E3 短 content 仍走 argv
    status, body = _post("/api/humanware/score-content",
                         {"workspace_id": WS, "character": "林晚",
                          "content": "结论已经给出，方案可以执行。"})
    _check("E3 score-content 短内容 argv", status == 200 and "total_score" in body,
           f"HTTP {status} total={body.get('total_score')}")

    # E4 check-dialogue 未知角色 → 409（修复前 500）
    status, body = _post("/api/humanware/check-dialogue",
                         {"workspace_id": WS, "character": "不存在的人", "dialogue": "你好。"})
    _check("E4 check-dialogue 未知角色透传 409", status == 409,
           f"HTTP {status} {json.dumps(body, ensure_ascii=False)[:160]}")

    # E5 超长 dialogue 经 stdin
    long_dialogue = "此事罢了，不必再提。" * 5000  # 50,000 字符
    status, body = _post("/api/humanware/check-dialogue",
                         {"workspace_id": WS, "character": "林晚", "dialogue": long_dialogue})
    ok = status == 200 and body.get("status") == "success" and isinstance(body.get("violations"), list)
    _check("E5 check-dialogue 50K 字符 stdin 通道", ok,
           f"HTTP {status} matches={body.get('matches')}")

    # E6 未命中口头禅文案（welcome 的 林晚 模板口头禅为空）
    status, body = _post("/api/humanware/check-dialogue",
                         {"workspace_id": WS, "character": "林晚",
                          "dialogue": "先确认现场，再下结论。"})
    suggestion = body.get("suggestion", "") if status == 200 else ""
    _check("E6 check-dialogue 文案不再谎称口头禅", status == 200 and "已命中口头禅" not in suggestion,
           f"HTTP {status} suggestion={suggestion!r}")

    # E7 score-chapter：先验证缺失章节 404（契约正确语义），
    # 再用临时工作区做归属对照（O1 算法正确性：按各自锚点评分应优于全部按默认锚点）
    status, body = _post("/api/humanware/score-chapter",
                         {"workspace_id": WS, "chapter_file": "story/0001/chapter.md"})
    _check("E7a score-chapter 缺失章节 404", status == 404,
           f"HTTP {status} {json.dumps(body, ensure_ascii=False)[:160]}")

    import shutil
    tmp_books_root = r"F:\DeterminFlow x2\xs2\data\workspaces\books"
    tmp_ws = os.path.join(tmp_books_root, "r15-e2e-tmp")
    try:
        os.makedirs(os.path.join(tmp_ws, "meta"), exist_ok=True)
        os.makedirs(os.path.join(tmp_ws, "story", "attributed"), exist_ok=True)
        os.makedirs(os.path.join(tmp_ws, "story", "control"), exist_ok=True)
        # 两个锚点平均句长差异大（14 vs 30）：归属正确时长句归给 30 锚点，
        # 声音一致性应明显高于「全部按默认 14 锚点」的对照章。
        with open(os.path.join(tmp_ws, "meta", "character_voice.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(
                "# 角色声音锚点\n\n## 林晚\n\n### 句法指纹\n"
                "- **平均句长**: 14\n- **问句倾向**: 0.15\n- **叹句倾向**: 0.10\n\n"
                "## 阿柴\n\n### 句法指纹\n"
                "- **平均句长**: 30\n- **问句倾向**: 0.15\n- **叹句倾向**: 0.10\n\n")
        attributed = (
            "## 林晚\n\n林晚说：“此事罢了，不必再提。”\n\n"
            "## 阿柴\n\n阿柴喊：“今天天气不错我们一起去看电影然后顺便吃点东西如何呢。”\n")
        control = (
            "林晚说：“此事罢了，不必再提。”\n\n"
            "阿柴喊：“今天天气不错我们一起去看电影然后顺便吃点东西如何呢。”\n")
        for d, text in (("attributed", attributed), ("control", control)):
            with open(os.path.join(tmp_ws, "story", d, "chapter.md"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

        status, body = _post("/api/humanware/score-chapter",
                             {"workspace_id": "r15-e2e-tmp", "chapter_file": "story/attributed/chapter.md"})
        ok_a = status == 200 and body.get("dialogues_scored") == 2
        voice_attr = body.get("detailed_scores", {}).get("声音一致性", 0) if ok_a else 0
        _check("E7b1 score-chapter 归属章评分（O1）", ok_a,
               f"HTTP {status} scored={body.get('dialogues_scored')} 声音一致性={voice_attr}")

        status, body = _post("/api/humanware/score-chapter",
                             {"workspace_id": "r15-e2e-tmp", "chapter_file": "story/control/chapter.md"})
        voice_ctrl = body.get("detailed_scores", {}).get("声音一致性", 0) if status == 200 else 0
        # 对照章（无标题）长句按默认 14 锚点受罚，声音一致性应明显更低 → 证明标题归属生效
        _check("E7b2 score-chapter 对照章更低（归属生效）",
               status == 200 and voice_attr > voice_ctrl,
               f"HTTP {status} attributed={voice_attr} control={voice_ctrl}")
    finally:
        shutil.rmtree(tmp_ws, ignore_errors=True)

    print("\n===== Round 15 E2E:", "ALL PASS" if not _failures else f"{len(_failures)} FAILED: {_failures}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
