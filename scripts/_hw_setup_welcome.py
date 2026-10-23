"""Add sample character profiles to the welcome workspace and verify."""
from pathlib import Path

import urllib.request

WS = Path("data/workspaces/books/welcome")
target = WS / "meta" / "character_profiles.md"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    "# 示例角色档案\n\n"
    "## 林晚\n\n"
    "性格：冷静克制，寡言，逻辑主导。\n"
    "说话方式：短句为主，语气平稳，几乎不用感叹。\n\n"
    "## 阿柴\n\n"
    "性格：活泼直率，热情，情绪外露。\n"
    "说话方式：口语化，爱用语气词，句长较短。\n",
    encoding="utf-8",
    newline="\n",
)
print("welcome profiles written, bytes:", target.stat().st_size)

with urllib.request.urlopen("http://127.0.0.1:8021/api/humanware/status/welcome", timeout=20) as r:
    print("status/welcome ->", r.read().decode("utf-8"))
