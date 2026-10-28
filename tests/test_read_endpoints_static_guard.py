"""B26/B28 同族缺陷机械化终局（R40）：GET 路由处理链不得携带 create=True。

R38 B26（console 面）与 R39 B28（workflow 面 + agent 工具底座）是两次同族
缺陷：读端点复用任务执行面「解析即 mkdir」语义，幻影工作区查询即建目录。
本钉测以纯 stdlib AST 静态扫描 src/ 全部含 HTTP 路由装饰器的模块，断言：

1. 任何 GET 路由处理函数（含模块内助手的调用闭包）可达的
   ``resolve_workflow_workspace`` 调用点，create 实参必须解析为字面量 False；
2. 经 create 形参参数化的模块内助手（如 novel_routes._console_root），
   GET 链上的调用点必须显式传字面量 False——缺省（解析器缺省即 True）、
   字面量 True、非字面量（UNKNOWN）一律判违规；
3. 跨模块锚点：src/workflow/task_queries.py 两个 agent 工具底座调用点
   （B28）逐点钉字面量 False。

防空转（防重构改名让扫描静默变空假通过）：路由模块数、GET 处理函数数、
resolver 调用点总数、关键助手存在性均钉下限；扫描发现数低于下限即 fail。

已知局限（docstring 记录，非漏洞）：调用图只解析模块内顶层函数引用，
跨模块导入的助手不在闭包内——B26/B28 两轮的实际缺陷面（web 各路由模块
内助手 + task_queries 方法）均为同模块或已单独钉死，超出现面时补钉。

可用 ``python tests/test_read_endpoints_static_guard.py`` 直接输出审计表。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}
RESOLVER = "resolve_workflow_workspace"  # 缺省 create=True（任务执行面语义）
_ABSENT = object()
_UNKNOWN = "UNKNOWN"
# bound 取值：None（无 create 形参）/ True / False / _UNKNOWN


@dataclass
class _FlowItem:
    kind: str          # "resolve" | "call"
    lineno: int
    callee: str        # resolve 用 RESOLVER 占位；call 用被调函数名
    create_expr: object = _ABSENT


@dataclass
class _Func:
    name: str
    node: ast.AST
    methods: set = field(default_factory=set)
    flows: list = field(default_factory=list)
    create_default: object = None  # None=无 create 形参；True/False=缺省值；_UNKNOWN=非字面量或必填

    @property
    def has_create_param(self) -> bool:
        return self.create_default is not None


def _kw_expr(call: ast.Call, name: str) -> object:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return _ABSENT


def _callee_name(func_expr: ast.AST) -> str | None:
    if isinstance(func_expr, ast.Name):
        return func_expr.id
    if isinstance(func_expr, ast.Attribute):
        return func_expr.attr
    return None


def _create_param_default(node) -> object:
    """函数的 create 形参缺省值；无该形参返回 None，非字面量/必填返回 _UNKNOWN。"""
    args = node.args
    pos = args.posonlyargs + args.args
    for index, arg in enumerate(pos):
        if arg.arg != "create":
            continue
        di = index - (len(pos) - len(args.defaults))
        if 0 <= di < len(args.defaults):
            d = args.defaults[di]
            if isinstance(d, ast.Constant) and isinstance(d.value, bool):
                return d.value
            return _UNKNOWN
        return _UNKNOWN  # 必填位置参数
    for arg, kd in zip(args.kwonlyargs, args.kw_defaults):
        if arg.arg == "create":
            if kd is None:
                return _UNKNOWN  # 必填 kw-only
            if isinstance(kd, ast.Constant) and isinstance(kd.value, bool):
                return kd.value
            return _UNKNOWN
    return None


def _parse_module(path: Path) -> tuple[dict[str, _Func], list[tuple[str, int, object]]]:
    """返回 (顶层函数表, 全模块 resolver 调用点列表)。

    GET 可达图只建在顶层函数上（方法调用无法按名静态解析，见 docstring 局限）；
    调用点清单则全树收集——类方法内的 resolver 调用（如 task_queries 的
    agent 工具底座）计入审计总数与跨模块钉测。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs: dict[str, _Func] = {}
    for body in tree.body:
        if not isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn = _Func(body.name, body)
        fn.create_default = _create_param_default(body)
        for dec in body.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                method = dec.func.attr.lower()
                if method in HTTP_METHODS:
                    fn.methods.add(method)
        funcs[body.name] = fn
    # 闭包内（含嵌套函数体）收集调用流；callee 只解析模块内顶层函数与 resolver。
    for fn in funcs.values():
        for sub in ast.walk(fn.node):
            if not isinstance(sub, ast.Call):
                continue
            callee = _callee_name(sub.func)
            if callee is None:
                continue
            if callee == RESOLVER:
                fn.flows.append(_FlowItem("resolve", sub.lineno, RESOLVER,
                                          _kw_expr(sub, "create")))
            elif callee in funcs:
                fn.flows.append(_FlowItem("call", sub.lineno, callee,
                                          _kw_expr(sub, "create")))
    all_sites: list[tuple[str, int, object]] = []
    for sub in ast.walk(tree):
        if isinstance(sub, ast.Call) and _callee_name(sub.func) == RESOLVER:
            all_sites.append((path.name, sub.lineno, _kw_expr(sub, "create")))
    return funcs, all_sites


def _effective_create(callee: _Func, expr: object, caller: _Func,
                      caller_bound: object) -> object:
    """求值某调用点传给被调者 create 形参的有效值。

    缺省 → 被调者缺省值（resolver 恒为 True）；字面量 → 该值；
    引用调用者自身 create 形参 → 调用者的 bound；其余 → _UNKNOWN（保守按 True）。
    """
    if expr is _ABSENT:
        return callee.create_default if callee.create_default is not None else _UNKNOWN
    if isinstance(expr, ast.Constant) and isinstance(expr.value, bool):
        return expr.value
    if (isinstance(expr, ast.Name) and expr.id == "create"
            and caller.has_create_param):
        return caller_bound if caller_bound in (True, False, _UNKNOWN) else _UNKNOWN
    return _UNKNOWN


def _verdict(fn: _Func, bound: object, funcs: dict[str, _Func],
             memo: dict, stack: frozenset) -> list[str]:
    """返回该函数（在 create 形参绑定 bound 下）可达的违规 resolver 调用点描述。

    bound 仅对含 create 形参的函数有意义；None 表示无该形参。
    递归边跳过（栈上函数体已由本次入口的求值覆盖），不影响可达性结论。
    """
    key = (fn.name, bound)
    if key in memo:
        return memo[key]
    memo[key] = []  # 先占位防环
    findings: list[str] = []
    for item in fn.flows:
        if item.kind == "resolve":
            eff = _effective_create(_Func("resolver", None, create_default=True),
                                    item.create_expr, fn, bound)
            if eff is not False:
                findings.append(
                    f"{fn.name}:{item.lineno} resolver create={eff!r}（须显式 False）")
        else:
            callee = funcs[item.callee]
            if callee.has_create_param:
                eff = _effective_create(callee, item.create_expr, fn, bound)
                sub = _verdict(callee, eff, funcs, memo, stack | {fn.name})
            elif callee.name in stack:
                continue
            else:
                sub = _verdict(callee, None, funcs, memo, stack | {fn.name})
            findings.extend(sub)
    memo[key] = findings
    return findings


def _scan_src() -> tuple[list[tuple[Path, dict[str, _Func]]], list[tuple[str, int, object]]]:
    """解析 src/ 全部模块；返回 (含 HTTP 路由的模块列表, 全部 resolver 调用点)。"""
    routed: list[tuple[Path, dict[str, _Func]]] = []
    all_sites: list[tuple[str, int, object]] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        funcs, sites = _parse_module(path)
        all_sites.extend(sites)
        if any(f.methods for f in funcs.values()):
            routed.append((path, funcs))
    return routed, all_sites


def _audit() -> tuple[list[tuple[Path, dict[str, _Func]]], list[str], int]:
    routed, all_sites = _scan_src()
    violations: list[str] = []
    for path, funcs in routed:
        rel = path.relative_to(SRC_ROOT).as_posix()
        memo: dict = {}
        for fn in funcs.values():
            if "get" not in fn.methods:
                continue
            for finding in _verdict(fn, None, funcs, memo, frozenset()):
                violations.append(f"{rel} GET {fn.name} → {finding}")
    return routed, violations, len(all_sites)


def test_get_route_chains_never_create_workspace_dirs():
    """B26/B28 防复发主断言：GET 链可达的 resolver 调用点必须显式 create=False。"""
    routed, violations, _ = _audit()
    assert not violations, (
        "GET 路由处理链存在 create=True 的 workspace 解析（B26/B28 同族复发）：\n"
        + "\n".join(violations))


def test_scan_is_not_vacuous():
    """防空转：模块数 / GET 处理函数数 / resolver 调用点数 / 关键助手均钉下限。"""
    routed, all_sites = _scan_src()
    get_handlers = sum(
        1 for _, funcs in routed for f in funcs.values() if "get" in f.methods)
    by_name = {p.relative_to(SRC_ROOT).as_posix(): funcs for p, funcs in routed}
    total_sites = len(all_sites)

    assert len(routed) >= 13, f"路由模块数骤降：仅 {len(routed)} 个，扫描面疑似失效"
    assert get_handlers >= 60, f"GET 处理函数仅 {get_handlers} 个，装饰器解析疑似失效"
    assert total_sites >= 9, (
        f"resolver 调用点仅 {total_sites} 处（R39 基线 9 处：web 4 + workflow 层 5），"
        "重命名会使本守卫静默失效")

    novel = by_name.get("web/novel_routes.py", {})
    workflow = by_name.get("web/workflow_routes.py", {})
    queries = by_name.get("workflow/task_queries.py", {})
    # B26/B28 修复引入的读端点助手必须存在且安全
    for module, anchor in ((novel, "_console_existing_root"),
                           (novel, "_console_root"),
                           (workflow, "_existing_workspace_root")):
        assert anchor in module, f"关键读端点助手缺失：{anchor}（重构后请同步本钉测）"
    assert novel["_console_existing_root"].create_default is None
    assert novel["_console_root"].create_default is True  # 缺省 True 是写面语义
    assert workflow["_existing_workspace_root"].create_default is None

    # novel_routes 自身 3 处 resolver 调用（_console_root 内 1 + 任务登记面 2）
    novel_sites = sum(1 for f in novel.values()
                      for item in f.flows if item.kind == "resolve")
    assert novel_sites >= 3, f"novel_routes resolver 调用点仅 {novel_sites} 处"


def test_task_queries_agent_tool_base_pins_create_false():
    """B28 跨模块锚点：task_queries 两个 agent 工具底座调用点逐点字面量 False。"""
    path = SRC_ROOT / "workflow" / "task_queries.py"
    _, sites = _parse_module(path)
    assert len(sites) == 2, (
        f"task_queries resolver 调用点应为 2 处（get_task_result/read_task_artifact），"
        f"实为 {len(sites)}：{sites}")
    for owner, lineno, expr in sites:
        assert isinstance(expr, ast.Constant) and expr.value is False, (
            f"task_queries {owner}:{lineno} create 实参未显式 False（B28 回归）")


if __name__ == "__main__":  # pragma: no cover — 手工审计输出
    routed, violations, total_sites = _audit()
    print(f"路由模块 {len(routed)} 个，resolver 调用点 {total_sites} 处")
    for path, funcs in routed:
        handlers = [f.name for f in funcs.values() if "get" in f.methods]
        sites = [(f.name, i.lineno) for f in funcs.values()
                 for i in f.flows if i.kind == "resolve"]
        if handlers or sites:
            print(f"  {path.relative_to(SRC_ROOT).as_posix()}: "
                  f"GET×{len(handlers)} sites={sites}")
    print("违规：" + ("无" if not violations else "\n".join(violations)))
