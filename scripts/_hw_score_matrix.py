"""Matrix check for the retuned emotion scoring.

Verifies direction-aware behaviour:
- calm character, calm line: high 情感真实度 (previously penalised ~45pts)
- calm character, spirited spike: clearly penalised (voice break)
- lively character matching baseline: high
- lively character too flat: mild penalty only
"""
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

BASE = Path("F:/DeterminFlow x2/DeterminFlow-Plugins/plugins/xs2-novel-flywheel/resources/script-library/xs2/humanware_helper/humanware_helper.py")
spec = importlib.util.spec_from_file_location("humanware_helper", BASE)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

CALM = {"style": "冷静克制", "avg_sentence_length": 14.0, "question_ratio": 0.15,
        "exclamation_ratio": 0.10, "tone_words": [], "banned_words": [], "cognition": ""}
LIVELY = {"style": "活泼外放", "avg_sentence_length": 8.0, "question_ratio": 0.4,
          "exclamation_ratio": 0.5, "tone_words": [], "banned_words": [], "cognition": ""}

cases = [
    ("冷静角色·平稳对白（修复前 emotion≈55）", CALM, "结论已经给出，方案可以执行。"),
    ("冷静角色·情绪爆发（应扣分）", CALM, "凭什么！我绝不允许！快收手！"),
    ("活泼角色·符合基线（应高分）", LIVELY, "哇！真的假的？我太高兴了！"),
    ("活泼角色·过于平淡（轻微扣分）", LIVELY, "结果已经出来，大家可以看了。"),
]

for label, anchor, content in cases:
    result = cli._score_text(anchor, content)
    d = result["detailed_scores"]
    print(f"{label}: total={result['total_score']} {result['grade']} "
          f"emotion={d['情感真实度']} voice={d['声音一致性']} "
          f"issues={[i['type'] for i in result['issues']]}")