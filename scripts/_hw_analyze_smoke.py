"""Add sample references to demo-voice and verify analyze-voice end-to-end."""
import json
import urllib.request
from pathlib import Path

WS = Path("data/workspaces/books/demo-voice")
ref = WS / "references"
ref.mkdir(parents=True, exist_ok=True)
(ref / "sample-novel.md").write_text(
    "# 参考样本\n\n"
    "## 林晚\n\n"
    '"调查结果已经确认，不必再争。"\n'
    '"你先冷静一下。"\n'
    '"这件事到此为止。"\n\n'
    "## 阿柴\n\n"
    '"哇！这也太棒了吧！"\n'
    '"快来看快来看！"\n'
    '"真的假的？我不信！"\n',
    encoding="utf-8",
    newline="\n",
)
print("references written:", (ref / "sample-novel.md").stat().st_size, "bytes")


def post(path, payload):
    req = urllib.request.Request(
        "http://127.0.0.1:8021" + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


result = post(
    "/api/humanware/generate-voice-file",
    {"workspace_id": "demo-voice", "from_references": True},
)
print("analyze-voice:", result)
assert result.get("status") == "success", result
assert result.get("character_count") == 2, result
print("PASS: analyze-voice 200 character_count=2")
