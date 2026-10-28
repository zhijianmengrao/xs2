"""CI e2e（R49）：用桩 provider 真跑一遍工作流编排，不依赖任何真实凭据。

## 这个脚本判什么、不判什么

R45/R46/R47 连续三轮把 CI e2e 列为最有价值的缺口，卡点是凭据：真实 e2e 要
一家供应商的 key，而 key 不能进 CI（fork PR 拿不到 secrets），也不该为了跑测试
去烧额度。桩 provider（``scripts/stub_llm_provider.py``）把这个卡点换成两个
可控的量：**协议是真的**（真实 HTTP + SSE，走的是 ChatOpenAI SDK、LangGraph、
引擎回调的完整链路），**判定是真的**（断言落在节点流转、失败策略、变量传递上）。

它**不**判：模型质量、提示词优劣、供应商健康。那三件事分别属于人工验收、
``provider_failure_profile.py``、以及真实快照闸门（R47/R48）。

## 场景

| 场景 | 输入 | 断言 |
|---|---|---|
| ``happy_path`` | 两个 agent 节点串行 + 一个 script 节点 | 全部 completed；下游首条消息拿到上游输出 |
| ``failure_propagates`` | 首个 agent 节点带 ``[stub:fail]`` | 该节点 failed，下游未执行，任务不报 completed |
| ``turn_terminates`` | 单 agent 节点，auto_flow 关闭 | 节点仍 completed——桩在收到工具结果后回文本，图不空转 |

第三个场景是桩最容易写错的地方：若桩对 ``role=tool`` 的请求仍返回 tool_call，
agent 图会在 llm↔tools 之间空转到轮次上限，CI 表现为超时而不是失败。测试
``tests/test_ci_e2e_stub.py`` 里有对应契约钉住。

## 为什么是独立脚本 + 子进程

``src/config.py`` 在 import 期就把 ``DATA_DIR`` / ``WORKFLOWS_DIR`` 求值成常量。
在 pytest 进程内改 env 已经太晚，只能逐个 monkeypatch 十来个模块常量——那种
写法每加一个模块就漏一处，且跑完会污染同进程后续用例。独立进程 + 临时
``DETERMINFLOW_DATA_DIR`` 从根上避免这两个问题，也让 CI 里这一步是**真的**
端到端（跨进程），而不是同进程内的函数调用。

## 退出码

0 = 全部场景通过
1 = 场景断言失败（有 bug）
3 = 环境无法启动（导入失败、端口起不来等，**不是**产品缺陷）

用法::

    python scripts/e2e_workflow_stub.py
    python scripts/e2e_workflow_stub.py --only happy_path --verbose
    python scripts/e2e_workflow_stub.py --keep-data   # 保留临时 data 目录以便查看
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EXIT_OK = 0
EXIT_ASSERTION_FAILED = 1
EXIT_ENVIRONMENT_BROKEN = 3

FAIL_MARKER = "[stub:fail]"  # 与 scripts/stub_llm_provider.py 同名常量保持一致


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    detail: str = ""


# ============================================================
# 环境隔离
# ============================================================

def _isolate_environment(data_root: Path) -> None:
    """把所有可写路径指到临时目录。

    必须在 import 任何 ``src.*`` 之前调用：``src/config.py`` 在 import 期就把
    DATA_DIR/LOGS_DIR/CONFIG_DIR 求值成模块常量。CONFIG_DIR 保持指向仓库里
    真实的 ``config/``——本 e2e 要验的是真实配置能否驱动真实编排，配置被替换
    成假的就是另一个测试了（模型供应商那一条由 MODELS_CONFIG_FILE 单独覆盖）。
    """
    os.environ["DETERMINFLOW_DATA_DIR"] = str(data_root / "data")
    os.environ["DETERMINFLOW_LOGS_DIR"] = str(data_root / "logs")
    os.environ["DETERMINFLOW_CONFIG_DIR"] = str(REPO_ROOT / "config")
    os.environ["MODELS_CONFIG_FILE"] = str(data_root / "models_config.json")
    # 用 inline/1 而不是社区默认的 process/4：本脚本判的是编排语义，
    # 进程池启动会引入与判据无关的抖动（其自身行为由 pool 场景测试覆盖）。
    os.environ["DETERMINFLOW_WORKFLOW_EXECUTOR_MODE"] = "inline"
    os.environ["DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT"] = "1"
    (data_root / "data" / "workflows").mkdir(parents=True, exist_ok=True)
    (data_root / "logs").mkdir(parents=True, exist_ok=True)


def _write_models_config(path: Path, base_url: str, model_id: str = "stub-model") -> None:
    """写一份只含桩 provider 的模型配置。

    ``api_key`` 是字面量 ``stub-key``：桩不校验鉴权，真实凭据在这里没有任何
    位置——这正是本路线的全部意义（fork PR 无 secrets 也能跑）。
    """
    path.write_text(
        json.dumps(
            {
                "default_params": {"temperature": 0.7},
                "retry": {"max_retries": 0, "delays": []},
                "providers": {
                    "stub": {
                        "name": "Stub Provider",
                        "provider_type": "openai_compatible",
                        "api_format": "openai",
                        "base_url": base_url,
                        "api_key": "stub-key",
                        "models": [model_id],
                        "hyperparameter_values": {},
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_agents_config(path: Path, model: str) -> None:
    """基于仓库真实 agents 配置，只把 default 子代理的模型指到桩。

    其他字段（tools / max_turns / prompt_template / model_params）原样保留：
    节点流转依赖的是真实工具集与真实提示词装配，改掉它们就变成测另一套东西了。
    """
    source = json.loads((REPO_ROOT / "config" / "agents_config.json").read_text(encoding="utf-8"))
    source.setdefault("agents", {}).setdefault("default", {})["model"] = model
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 运行时装配
# ============================================================

class Runtime:
    """把真实组件按 web_server.lifespan 的顺序装起来（去掉与编排无关的部分）。"""

    def __init__(self, *, data_root: Path, base_url: str, verbose: bool = False):
        self.data_root = data_root
        self.base_url = base_url
        self.verbose = verbose
        self.session_manager = None
        self.workflow_manager = None

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"    · {message}", flush=True)

    async def start(self) -> None:
        models_path = self.data_root / "models_config.json"
        agents_path = self.data_root / "agents_config.json"

        # 模型配置在 import 期被读取，所以必须先建单例再 import 上层模块。
        from src.core.model_manager import ModelManager
        import src.core.model_manager as model_manager_module

        model_manager_module._model_manager = ModelManager(str(models_path))

        from src.agent.config_manager import AgentConfigManager
        from src.agent.definition import set_agent_config_manager
        agent_config_manager = AgentConfigManager(agents_path)
        set_agent_config_manager(agent_config_manager)
        self.log("AgentConfigManager 已装载")

        from src.core.llm_client import create_startup_llm
        from src.prompts import PromptManager
        from src.session import PromptBuilder, ToolAssembler
        from src.tools import register_all_tool_factories
        from src.tools.registry import ToolRegistry

        prompt_manager = PromptManager(
            config_file=REPO_ROOT / "config" / "prompts_config.json",
        )
        prompt_builder = PromptBuilder(prompt_manager=prompt_manager)

        from src.agent.session_manager import SessionManager
        self.session_manager = SessionManager()

        from src.core.approval_manager import ApprovalManager
        from src.core.workspace_manager import WorkspaceManager
        self.session_manager.inject_dependencies(
            workspace_manager=WorkspaceManager(),
            approval_manager=ApprovalManager(),
            agent_config_manager=agent_config_manager,
        )

        from src.workflow.manager import WorkflowManager
        self.workflow_manager = WorkflowManager(self.session_manager)
        self.session_manager.inject_dependencies(workflow_manager=self.workflow_manager)
        self.log("WorkflowManager 已初始化")

        class _EmptyMCP:
            """没有外部 MCP server 时的空实现（真跑时装的是真 MCP 客户端）。"""

            @staticmethod
            def get_tools() -> list:
                return []

        startup_llm = create_startup_llm(streaming=True)
        registry = ToolRegistry(str(REPO_ROOT / "config" / "tool_groups_config.json"))
        register_all_tool_factories(
            registry,
            mcp_client=_EmptyMCP(),
            session_manager=self.session_manager,
            prompt_manager=prompt_manager,
            skill_manager=None,
            rule_manager=None,
            approval_manager=None,
            llm_client=startup_llm,
        )
        self.session_manager.set_builders(
            prompt_builder,
            ToolAssembler(
                session_manager=self.session_manager,
                registry=registry,
                llm_client=startup_llm,
            ),
        )
        self.log(f"ToolRegistry 已注册 {len(registry.get_tools())} 个工具")

    async def stop(self) -> None:
        if self.session_manager is not None:
            try:
                await self.session_manager.shutdown()
            except Exception:
                self.log("SessionManager 关闭异常（忽略）")
        if self.workflow_manager is not None:
            try:
                await self.workflow_manager.shutdown_running_tasks()
            except Exception:
                self.log("WorkflowManager 关闭异常（忽略）")

    async def run_workflow(
        self,
        workflow_id: str,
        definition: dict,
        *,
        timeout_seconds: float = 120.0,
        scripts: dict[str, str] | None = None,
    ) -> tuple[str, dict]:
        """建工作流 → 落脚本 → 起任务 → 等终态，返回 (task 状态, 节点状态映射)。"""
        created = self.workflow_manager.create_workflow(
            {"workflow_id": workflow_id, **definition}
        )
        if created.get("success") is False:
            raise AssertionError(f"创建工作流失败: {created}")

        # inline 脚本必须在起任务前落盘：runtime_guards 会在冻结运行身份时
        # 计算脚本文件的 sha256，文件缺失会直接拒绝启动 Task。
        for name, body in (scripts or {}).items():
            script_path = self.data_root / "data" / "workflows" / workflow_id / "script" / f"{name}.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(body, encoding="utf-8")

        started = await self.workflow_manager.create_and_run_task(workflow_id)
        if not started.get("success"):
            raise AssertionError(f"启动任务失败: {started}")
        task_id = started["task_id"]

        terminal = {"completed", "failed", "cancelled", "retry_waiting"}
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        task = None
        while asyncio.get_running_loop().time() < deadline:
            task = self.workflow_manager._load_task(workflow_id, task_id)
            if task is not None and task.status in terminal:
                break
            await asyncio.sleep(0.1)
        if task is None:
            raise AssertionError(f"任务 {task_id} 从未落盘")
        if task.status not in terminal:
            raise AssertionError(
                f"任务在 {timeout_seconds:.0f}s 内未到终态（当前 {task.status}）"
            )
        return task.status, {
            node_id: state for node_id, state in task.node_states.items()
        }


def _agent_node(node_id: str, message: str, **extra) -> dict:
    """agent 节点。``output_variable`` 让它的末轮回复成为下游可引用的变量。"""
    node = {
        "id": node_id,
        "node_type": "agent",
        "agent_type": "default",
        "first_message": message,
        "auto_flow": True,
        "output_variable": f"{node_id}_output",
    }
    node.update(extra)
    return node


def _request_text(request: dict) -> str:
    """把一次桩请求的所有消息内容拼成一段文本，供「上游产出是否传到下游」断言。"""
    parts: list[str] = []
    for message in (request.get("payload") or {}).get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
        for call in message.get("tool_calls") or []:
            arguments = (call.get("function") or {}).get("arguments")
            if arguments:
                parts.append(str(arguments))
    return "\n".join(parts)


def _script_node(node_id: str, script: str) -> tuple[dict, dict]:
    """inline script 节点 + 它要落盘的脚本文件。

    ``script_name`` 不含扩展名，且必须过 ``runtime_guards._SCRIPT_NAME_RE``；
    脚本正文在**建工作流之后、起任务之前**写到 ``{workflow}/script/{name}.py``
    ——这正是 UI 里保存脚本的真实形态，不是本脚本发明的捷径。
    """
    node = {
        "id": node_id,
        "node_type": "script",
        "node_params": {
            "script_source": "inline",
            "script_type": "python",
            "script_name": node_id,
        },
    }
    return node, {node_id: script}


# ============================================================
# 场景
# ============================================================

async def scenario_happy_path(runtime: Runtime, stub) -> ScenarioResult:
    """两个 agent 节点串一个 script 节点：验流转 + 输出变量传递。"""
    archivist, scripts = _script_node(
        "archivist",
        'from pathlib import Path\n'
        'Path("archive.txt").write_text("archived", encoding="utf-8")\n'
        'print("<script_out>archived</script_out>")\n',
    )
    definition = {
        "name": "happy path",
        "nodes": [
            _agent_node("writer", "write a short line"),
            # 占位符 {{writer_output}} 由引擎从 writer 的 outputs 合并进
            # parameter_values 后解析。这里刻意用它，好让「上游产出真的流到
            # 下游提示词里」成为可观察事实（下面断言桩收到了这段文本）。
            _agent_node("reviewer", "review this draft: {{writer_output}}"),
            archivist,
        ],
        "edges": [
            {"source": "writer", "target": "reviewer"},
            {"source": "reviewer", "target": "archivist"},
        ],
    }
    status, nodes = await runtime.run_workflow(
        "wf-e2e-happy", definition, scripts=scripts
    )
    problems: list[str] = []
    if status != "completed":
        problems.append(f"任务状态 {status}，期望 completed")
    for node_id in ("writer", "reviewer", "archivist"):
        state = nodes.get(node_id)
        if state is None:
            problems.append(f"节点 {node_id} 没有状态")
        elif state.status != "completed":
            problems.append(
                f"节点 {node_id} 状态 {state.status}（error={state.error!r}）"
            )
    if not stub.requests:
        problems.append("桩 provider 一次请求都没收到——被测链路没走真实 HTTP")
    if not stub.tool_call_requests():
        problems.append(
            "桩没有任何 tool_call 请求：说明 complete_task 工具没进模型上下文"
        )
    # 上游产出必须真的进了下游的模型请求。桩里的 summary 由任务文本前缀生成，
    # 而 writer 的 summary 就是 "stub completed: <它的首条消息>"，所以下游请求
    # 里应当能看到这段内容；占位符没解析时会原样出现 "{{writer_output}}"。
    reviewer_texts = [
        _request_text(request)
        for request in stub.requests
        if "review this draft" in _request_text(request)
    ]
    if not reviewer_texts:
        problems.append("没找到 review 节点的模型请求")
    else:
        if any("{{writer_output}}" in text for text in reviewer_texts):
            problems.append("{{writer_output}} 未被解析，上游产出没传下游")
        elif not any("stub completed" in text for text in reviewer_texts):
            problems.append("下游请求里看不到上游产出文本")
    return ScenarioResult(
        "happy_path",
        not problems,
        "; ".join(problems) or f"{len(stub.requests)} 次模型请求，3 节点 completed，上游产出已传下游",
    )


async def scenario_failure_propagates(runtime: Runtime, stub) -> ScenarioResult:
    """首节点带 [stub:fail]：该节点必须失败，下游不得执行。"""
    definition = {
        "name": "failure propagation",
        "nodes": [
            _agent_node("broken", f"this one must fail {FAIL_MARKER}"),
            _agent_node("downstream", "must never run"),
        ],
        "edges": [{"source": "broken", "target": "downstream"}],
    }
    status, nodes = await runtime.run_workflow("wf-e2e-fail", definition)
    problems: list[str] = []
    broken = nodes.get("broken")
    downstream = nodes.get("downstream")
    if broken is None:
        problems.append("节点 broken 没有状态")
    elif broken.status == "completed":
        problems.append("节点 broken 被判 completed，失败信号被吞掉了")
    if downstream is not None and downstream.status == "completed":
        problems.append("下游节点在下游上游失败后仍然 completed")
    if status == "completed":
        problems.append("任务整体 completed，失败没有传导到任务层")
    return ScenarioResult(
        "failure_propagates",
        not problems,
        "; ".join(problems) or f"任务 {status}，broken={broken.status if broken else 'missing'}",
    )


async def scenario_turn_terminates(runtime: Runtime, stub) -> ScenarioResult:
    """关闭 auto_flow 的单 agent 节点：桩在 tool 结果后回文本，图必须收敛。"""
    definition = {
        "name": "turn termination",
        "nodes": [
            _agent_node("solo", "single turn task", auto_flow=False),
        ],
        "edges": [],
    }
    status, nodes = await runtime.run_workflow(
        "wf-e2e-terminate", definition, timeout_seconds=90.0
    )
    solo = nodes.get("solo")
    problems: list[str] = []
    if solo is None:
        problems.append("节点 solo 没有状态")
    elif solo.status != "completed":
        problems.append(f"节点 solo 状态 {solo.status}（error={solo.error!r}）")
    # 空转会表现为请求数暴涨；上限按「每次模型调用最多两跳」给宽裕余量
    if len(stub.requests) > 8:
        problems.append(
            f"模型请求 {len(stub.requests)} 次，疑似 llm↔tools 空转到轮次上限"
        )
    return ScenarioResult(
        "turn_terminates",
        not problems,
        "; ".join(problems) or f"任务 {status}，{len(stub.requests)} 次模型请求",
    )


SCENARIOS = {
    "happy_path": scenario_happy_path,
    "failure_propagates": scenario_failure_propagates,
    "turn_terminates": scenario_turn_terminates,
}
SCENARIO_ORDER = ["happy_path", "failure_propagates", "turn_terminates"]


# ============================================================
# 入口
# ============================================================

async def _run(args) -> int:
    from scripts.stub_llm_provider import StubProvider

    keep = args.keep_data
    data_root = Path(tempfile.mkdtemp(prefix="determinflow-e2e-"))
    _isolate_environment(data_root)

    results: list[ScenarioResult] = []
    stub = StubProvider().start()
    try:
        _write_models_config(data_root / "models_config.json", stub.base_url)
        _write_agents_config(data_root / "agents_config.json", "stub:stub-model")

        runtime = Runtime(
            data_root=data_root, base_url=stub.base_url, verbose=args.verbose
        )
        try:
            await runtime.start()
        except Exception:
            traceback.print_exc()
            print("[e2e] 环境装配失败，无法判定编排行为（退出码 3）", flush=True)
            return EXIT_ENVIRONMENT_BROKEN

        wanted = SCENARIO_ORDER if args.only is None else [args.only]
        try:
            for name in wanted:
                # 每个场景清一次请求记录，断言里的计数才有意义
                stub.requests.clear()
                try:
                    result = await SCENARIOS[name](runtime, stub)
                except Exception as exc:
                    result = ScenarioResult(name, False, f"场景抛异常: {exc!r}")
                    if args.verbose:
                        traceback.print_exc()
                results.append(result)
        finally:
            await runtime.stop()
    finally:
        stub.stop()
        if not keep:
            shutil.rmtree(data_root, ignore_errors=True)
        else:
            print(f"[e2e] 数据目录保留在 {data_root}", flush=True)

    print("", flush=True)
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"[e2e] {mark} {result.name}: {result.detail}", flush=True)
    failed = [r for r in results if not r.passed]
    print(
        f"[e2e] {len(results) - len(failed)}/{len(results)} 场景通过",
        flush=True,
    )
    return EXIT_OK if not failed else EXIT_ASSERTION_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="桩 provider 驱动的工作流编排 e2e（R49）"
    )
    parser.add_argument(
        "--only", choices=SCENARIO_ORDER, default=None, help="只跑一个场景"
    )
    parser.add_argument("--verbose", action="store_true", help="打印装配过程与异常栈")
    parser.add_argument(
        "--keep-data", action="store_true", help="保留临时 data 目录（排查用）"
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
