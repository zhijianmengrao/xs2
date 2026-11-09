"""R234：create_manifest import 调用面同账（W 系续 W59）。

背景（实测，R232 §3 登记）：replace-desktop-assets.yml 里
``from desktop.scripts.create_update_manifest import create_manifest``
（L70）后按 6 个 keyword-only 实参调用（L92–97：version / installer /
signature / base_url / notes / pub_date）；函数签名
（create_update_manifest.py L11–18）恰为这 6 个 keyword-only 形参；
脚本 ``main()`` 内另一处调用同 6 键（L53–60）。三处任何一处漂移：
workflow 写错 kwarg 名 → 运行时 ``TypeError: unexpected keyword
argument``（发版第 2 步直接失败）；脚本增删形参而 call site 没跟 →
同上。

W59 把这条边钉成两半（W32/W34/W38–W58 同型分工）：

- **W59a 语料守卫**：workflow 里 ``create_manifest`` 调用恰一处；脚本
  里函数定义恰一处且 keyword-only 形参非空；``main()`` 内自调用恰
  一处。
- **W59b 调用面恰等**：两处调用（workflow import 调用 / 脚本自调用）
  的 kwarg 集合都 == 函数 keyword-only 形参集合（逐字恰等）。

边界：只判 kwarg 名的字面同账——不判取值（version/notes 等由其他判据
负责）、不判 ``create_manifest`` 的执行行为（CI 负责）、不判 CLI 面
（W39 已钉 desktop-windows.yml 的 flag）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "create_update_manifest.py"

# workflow 调用块：`create_manifest(...)`（块内无嵌套括号）。
CALL_RX = re.compile(r"create_manifest\(([^)]*)\)", re.S)
# kwarg 名：块首或逗号后的 `name=`。
KWARG_RX = re.compile(r"(?:^|,)\s*(\w+)\s*=", re.S)


def _wf_call_blocks() -> list[str]:
    return CALL_RX.findall(REPLACE_WF.read_text(encoding="utf-8"))


def _wf_kwargs(block: str) -> list[str]:
    return KWARG_RX.findall(block)


def _tree() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def _defs(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_manifest"
    ]


def _signature(tree: ast.Module) -> list[str]:
    defs = _defs(tree)
    assert len(defs) == 1, (
        f"create_update_manifest.py 的 create_manifest 定义应恰 1 处，"
        f"实测 {len(defs)} 处——W59a 语料守卫"
    )
    return [arg.arg for arg in defs[0].args.kwonlyargs]


def _signature_or_none(tree: ast.Module) -> list[str] | None:
    """W59b 用：定义缺失/重复归 W59a，不在这里二次发红。"""
    defs = _defs(tree)
    if len(defs) != 1:
        return None
    return [arg.arg for arg in defs[0].args.kwonlyargs]


def _self_calls(tree: ast.Module) -> list[ast.Call]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_manifest"
    ]


def test_call_sites_exist() -> None:
    """W59a：workflow 调用恰一处、定义恰一处且 kwonly 非空、自调用恰一处。"""
    blocks = _wf_call_blocks()
    assert len(blocks) == 1, (
        f"replace workflow 的 create_manifest 调用应恰 1 处，实测 "
        f"{len(blocks)} 处——W59a 语料守卫"
    )
    tree = _tree()
    signature = _signature(tree)
    assert signature, "create_manifest 没有 keyword-only 形参——W59a 无锚"
    calls = _self_calls(tree)
    assert len(calls) == 1, (
        f"脚本 main() 内的 create_manifest 自调用应恰 1 处，实测 "
        f"{len(calls)} 处——W59a 语料守卫"
    )


def test_call_keywords_agree() -> None:
    """W59b：两处调用的 kwarg 集合都 == 函数 keyword-only 形参集合。

    不做存在守卫（W47/W49 定式）：调用缺失/定义缺失归 W59a 计数，
    这里遍历现有调用判值（空集合自然跳过）。
    """
    tree = _tree()
    signature = _signature_or_none(tree)
    if not signature:
        return
    expected = set(signature)
    for block in _wf_call_blocks():
        wf = set(_wf_kwargs(block))
        assert wf == expected, (
            f"workflow 调用 kwarg 与函数形参不同账：多 "
            f"{sorted(wf - expected)}，缺 {sorted(expected - wf)}"
            "——运行时 TypeError"
        )
    for call in _self_calls(tree):
        kwargs = {kw.arg for kw in call.keywords}
        assert kwargs == expected, (
            f"脚本自调用 kwarg 与函数形参不同账：多 "
            f"{sorted(kwargs - expected)}，缺 {sorted(expected - kwargs)}"
        )
