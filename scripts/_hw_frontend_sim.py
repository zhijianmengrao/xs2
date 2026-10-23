"""Simulate the exact frontend call sequence for the character-voice page.

Idempotent: resets the demo workspace voice file at the start so the run
always starts from the "first time opening the page" state.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8021"
WS = "demo-voice"
WS_FULL = "data/workspaces/books/demo-voice"
# Reset to the initial state (fresh book, no voice anchors yet).
Path("F:/DeterminFlow x2/xs2/data/workspaces/books/demo-voice/meta/character_voice.md").unlink(missing_ok=True)
results = []


def req(method, path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# 1. projects list (page mount)
s, body = req("GET", "/api/novel-console/projects")
results.append(("GET /novel-console/projects", s,
                any(p["workspace"].endswith("demo-voice") for p in body.get("projects", []))))

# 2. workflow catalog
s, body = req("GET", "/api/workflows")
results.append(("GET /workflows (catalog)", s, len(body) > 0))

# 3. workspace files
q = urllib.parse.urlencode({"workflow_id": "xs2-novel-flywheel-build", "workspace": WS_FULL})
s, body = req("GET", f"/api/workflows/workspace-files?{q}")
results.append(("GET workspace-files", s,
                any(f["path"] == "meta/character_profiles.md" for f in body.get("files", []))))

# 4. humanware status (voice page mount)
s, body = req("GET", f"/api/humanware/status/{WS}")
results.append(("GET status", s,
                body.get("profiles_file_exists") is True and body.get("voice_file_exists") is False))

# 5. voice-file initial read
s, body = req("GET", f"/api/humanware/voice-file/{WS}")
results.append(("GET voice-file (initial)", s, body.get("status") == "not_found"))

# 6. generate from profiles (button)
s, body = req("POST", "/api/humanware/generate-voice-file",
              {"workspace_id": WS, "from_profiles": True})
results.append(("POST generate-voice", s, body.get("character_count") == 2))

# 7. status after generation
s, body = req("GET", f"/api/humanware/status/{WS}")
results.append(("GET status (after gen)", s,
                body.get("voice_file_exists") is True and body.get("character_count") == 2))

# 8. editor load content
s, body = req("GET", f"/api/humanware/voice-file/{WS}")
results.append(("GET voice-file (after gen)", s,
                body.get("status") == "success" and "林晚" in (body.get("content") or "")))

# 9. editor save (PUT)
edited = (body.get("content") or "") + "\n## 临时追加角色\n\n### 核心声音定位\n- **表达方式**: 测试角色\n"
s, body = req("PUT", f"/api/humanware/voice-file/{WS}",
              {"workspace_id": WS, "content": edited})
results.append(("PUT voice-file (save)", s, body.get("status") == "success"))

# 10. read back after save
s, body = req("GET", f"/api/humanware/voice-file/{WS}")
results.append(("GET voice-file (verify save)", s, "临时追加角色" in (body.get("content") or "")))

# 11. score-content
s, body = req("POST", "/api/humanware/score-content",
              {"workspace_id": WS, "character": "林晚", "content": "结论已经给出，方案可以执行。"})
results.append(("POST score-content", s,
                s == 200 and set(("声音一致性", "对话自然度", "情感真实度", "行为一致性"))
                <= set(body.get("detailed_scores", {}))))

# 12. score-chapter
s, body = req("POST", "/api/humanware/score-chapter",
              {"workspace_id": WS, "chapter_file": "story/0001/chapter.md"})
results.append(("POST score-chapter", s, body.get("dialogues_scored") == 2))

# 13. check-dialogue
s, body = req("POST", "/api/humanware/check-dialogue",
              {"workspace_id": WS, "character": "林晚", "dialogue": "结论已经给出。"})
results.append(("POST check-dialogue", s, "matches" in body))

failed = [r for r in results if not r[2]]
for name, code, ok in results:
    print(("PASS" if ok else "FAIL") + "  " + name + "  -> " + str(code))
print()
print(f"total={len(results)} passed={len(results) - len(failed)} failed={len(failed)}")
for f in failed:
    print("FAILED:", f)
