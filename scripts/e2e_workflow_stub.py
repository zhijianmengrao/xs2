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
    # 流式停摆场景要用小超时：默认 120s 会让 CI 上这一步慢到不像话，而
    # 判据（停摆是否被判失败、是否拒绝原地重试）与超时具体值无关。
    os.environ["LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S"] = "2"
    (data_root / "data" / "workflows").mkdir(parents=True, exist_ok=True)
    (data_root / "logs").mkdir(parents=True, exist_ok=True)


def _write_models_config(path: Path, base_url: str, model_id: str = "stub-model",
                         *, max_retries: int = 0,
                         delays: list[float] | None = None,
                         sdk_max_retries: int | None = None) -> None:
    """写一份只含桩 provider 的模型配置。

    ``api_key`` 是字面量 ``stub-key``：桩不校验鉴权，真实凭据在这里没有任何
    位置——这正是本路线的全部意义（fork PR 无 secrets 也能跑）。

    ``max_retries`` 默认 0：多数场景判的是编排语义，重试层会引入与判据无关的
    等待。只有故障注入场景把它调大，好让「瞬时错误后被重试救回来」可观察。

    ``sdk_max_retries``（R51）默认不写进配置——不写就是沿用 SDK 自有策略
    （ChatOpenAI 默认 2 次）。退避场景必须显式写 0：否则 SDK 层会抢在 Core
    之前用自身指数退避救回，量到的间隔是 SDK 的，不是 Core ``delays`` 的
    （R50 §3.4 的「关掉 Core 重试仍绿」就是这个原因）。
    """
    retry: dict = {"max_retries": max_retries, "delays": list(delays or [])}
    if sdk_max_retries is not None:
        retry["sdk_max_retries"] = sdk_max_retries
    path.write_text(
        json.dumps(
            {
                "default_params": {"temperature": 0.7},
                "retry": retry,
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


async def scenario_transient_error_is_retried(runtime: Runtime, stub) -> ScenarioResult:
    """瞬时错误（503）一次后重试成功：证明瞬时失败最终能被救回来。

    桩用 ``[stub:5xx][stub:fail_once]``：第一发返回真实的 HTTP 503 +
    OpenAI 错误体，第二发起正常回复。断言落在「请求数 ≥ 2 且节点最终
    completed」——只看 completed 无法区分「重试救回来了」与「根本没失败」。

    **它判的是「重试总效果」，不是「Core 层重试」**（R50 实测）：关闭 Core 的
    ``retry.max_retries`` 后场景仍然是 3 次请求，因为 LangChain 的 ChatOpenAI
    自带 ``max_retries=2``。只有同时关掉两层才会红（实测 1 次请求、任务 failed）。
    所以一条「Core 层重试失效」的回归，本场景抓不到——那是单测的地盘
    （``tests/test_llm_client_params.py``）。把这一点写清楚，免得下一轮把它
    当成 Core 层的守卫。
    """
    definition = {
        "name": "transient retry",
        "nodes": [_agent_node("flaky", "task [stub:5xx][stub:fail_once]")],
        "edges": [],
    }
    status, nodes = await runtime.run_workflow("wf-e2e-retry", definition)
    problems: list[str] = []
    node = nodes.get("flaky")
    if node is None:
        problems.append("节点 flaky 没有状态")
    elif node.status != "completed":
        problems.append(f"节点 flaky 状态 {node.status}（error={node.error!r}）")
    if status != "completed":
        problems.append(f"任务状态 {status}，期望 completed")

    injected = stub.error_requests()
    if len(injected) < 1:
        problems.append("桩没有收到注入请求——故障注入没生效，本场景失去意义")
    total = len(stub.requests)
    if total < 2:
        problems.append(
            f"模型请求只有 {total} 次：503 之后没有重试，重试层没接住瞬时错误"
        )
    return ScenarioResult(
        "transient_error_is_retried",
        not problems,
        "; ".join(problems) or (
            f"任务 completed，{total} 次请求（含 1 次注入 503），重试救回"
        ),
    )


async def scenario_permanent_error_is_not_retried(runtime: Runtime, stub) -> ScenarioResult:
    """永久错误（401）不重试：证明「不重试」这个决定也真的生效。

    与上一个场景互为正反面。只验「会重试」而不验「该不重试时不重试」，
    会让「把所有错误都重试一遍」这种退步一路绿灯。
    """
    definition = {
        "name": "permanent error",
        "nodes": [_agent_node("denied", "task [stub:401]")],
        "edges": [],
    }
    status, nodes = await runtime.run_workflow("wf-e2e-denied", definition)
    problems: list[str] = []
    node = nodes.get("denied")
    if node is None:
        problems.append("节点 denied 没有状态")
    elif node.status == "completed":
        problems.append("节点 denied 被判 completed，401 被吞掉了")
    if status == "completed":
        problems.append("任务 completed，永久错误没有传导到任务层")

    total = len(stub.requests)
    if total < 1:
        problems.append("桩没有收到请求")
    elif total > 1:
        problems.append(
            f"模型请求 {total} 次：401 被当成瞬时错误重试了"
            "（is_permanent_provider_error 判定失效）"
        )
    return ScenarioResult(
        "permanent_error_is_not_retried",
        not problems,
        "; ".join(problems) or f"任务 {status}，{total} 次请求（401 未重试）",
    )


async def scenario_stream_stall_fails_fast(runtime: Runtime, stub) -> ScenarioResult:
    """流式停摆必须被判失败，而不是挂到天荒地老。

    ``[stub:stall]`` 让桩发完 SSE 头与一个 chunk 后停住。``stream_chunk_timeout``
    （本脚本设 2s，见 ``_isolate_environment``）会在「解析出的 chunk 之间」超时，
    抛 ``StreamChunkTimeoutError``。

    断言三件事：
    1. 节点 failed —— 停摆不能被当成成功收尾；
    2. 任务在超时预算内到终态 —— 这正是「没有 stream_chunk_timeout 就会挂到
       上游 6 小时上限」的那类失效的反面；
    3. 桩只收到 1 次请求 —— 已经吐出部分流后**拒绝原地重试**是刻意的
       （``llm_client`` 的 ``retry_suppressed=partial_stream``），因为重发会在
       调用方已收到的半截响应后面再拼一段。
    """
    definition = {
        "name": "stream stall",
        "nodes": [_agent_node("stalled", "task [stub:stall]")],
        "edges": [],
    }
    status, nodes = await runtime.run_workflow(
        "wf-e2e-stall", definition, timeout_seconds=90.0
    )
    problems: list[str] = []
    node = nodes.get("stalled")
    if node is None:
        problems.append("节点 stalled 没有状态")
    elif node.status == "completed":
        problems.append("节点 stalled 被判 completed：停摆被当成正常收尾")
    if status == "completed":
        problems.append("任务 completed，停摆没有传导到任务层")

    total = len(stub.requests)
    if total < 1:
        problems.append("桩没有收到请求")
    elif total > 1:
        problems.append(
            f"模型请求 {total} 次：部分流之后仍然重试，会在半截响应后面再拼一段"
        )
    error_text = (node.error if node is not None else "") or ""
    if error_text and "streaming chunk" not in error_text.lower() \
            and "stream" not in error_text.lower():
        problems.append(f"错误文本看不出是流式停摆: {error_text[:120]!r}")
    return ScenarioResult(
        "stream_stall_fails_fast",
        not problems,
        "; ".join(problems) or f"任务 {status}，{total} 次请求（部分流后未重试）",
    )


def _request_gaps(stub) -> list[float]:
    """相邻两次模型请求的到达间隔（秒）。桩在收包时打 monotonic 时间戳。"""
    stamps = [r.get("received_at") for r in stub.requests
              if isinstance(r.get("received_at"), (int, float))]
    return [round(b - a, 3) for a, b in zip(stamps, stamps[1:])]


def _backoff_segments(stub, *, floor: float = 0.2) -> list[float]:
    """把请求间隔里的「退避段」挑出来（按到达顺序）。

    同一场景里除了退避还有别的停顿：工具结果回来后那次收尾请求的间隔通常只有
    几毫秒。``floor`` 以下的间隔不是退避，混进来会让形状判断失真。这个阈值
    只区分量级（毫秒 vs 数百毫秒），不承担判据——判据在调用方。
    """
    return [gap for gap in _request_gaps(stub) if gap >= floor]


def _install_retry_config(runtime: Runtime, *, max_retries: int,
                          delays: list[float],
                          sdk_max_retries: int | None) -> None:
    """改写模型配置并重建 ModelManager 单例（配置在 import 期被读取）。"""
    _write_models_config(
        runtime.data_root / "models_config.json", runtime.base_url,
        max_retries=max_retries, delays=list(delays),
        sdk_max_retries=sdk_max_retries,
    )
    from src.core.model_manager import ModelManager
    import src.core.model_manager as model_manager_module

    model_manager_module._model_manager = ModelManager(
        str(runtime.data_root / "models_config.json"))


async def scenario_retry_backoff_is_honoured(runtime: Runtime, stub) -> ScenarioResult:
    """退避时长必须真的被等过（R51）。

    判据用**差分**：同一场景跑两次，一次 ``delays=[0]``、一次 ``delays=[1.2]``，
    比较两次的请求间隔。差分法绕开了「固定开销有多少」这个不可知量——真正的
    判据是「多出来的等待 ≈ 配置的退避」，而不是「总时长 ≥ 某个绝对值」。

    为什么必须显式关掉 SDK 重试（``sdk_max_retries=0``）：ChatOpenAI 自带
    ``max_retries=2``，它会抢在 Core 包装之前用自身的指数退避救回瞬时错误。
    实测 sdk=2 + core delays=[3.0] 时间隔只有 0.48s——量到的是 SDK 的退避，
    Core 的 3 秒完全不可见。这正是 R50 §3.4「关掉 Core max_retries 后场景仍绿」
    的根因：两层当时不可分。

    本场景因此判的是「**Core 层的** delays」，不是「重试总效果」——
    ``transient_error_is_retried`` 判的是后者，两者互补。

    它只判**单点**幅度（配了 1.2s 就等到 1.2s）。退避的**形状**由
    ``retry_backoff_shape_is_honoured`` 判。
    """
    definition = {
        "name": "retry backoff",
        "nodes": [_agent_node("slow", "task [stub:5xx][stub:fail_once]")],
        "edges": [],
    }
    problems: list[str] = []

    samples: dict[str, float] = {}
    for label, delay in (("zero", 0.0), ("configured", 1.2)):
        _install_retry_config(runtime, max_retries=1, delays=[delay],
                              sdk_max_retries=0)
        stub.requests.clear()
        stub.reset_claims()
        status, nodes = await runtime.run_workflow(f"wf-e2e-backoff-{label}", definition)
        node = nodes.get("slow")
        if status != "completed" or (node is not None and node.status != "completed"):
            problems.append(
                f"[{label}] 任务未 completed（status={status}），退避场景前提不成立")
            continue
        gaps = _request_gaps(stub)
        if not gaps:
            problems.append(f"[{label}] 只收到 1 次请求，没有重试，量不到间隔")
            continue
        samples[label] = max(gaps)

    if len(samples) == 2:
        extra = samples["configured"] - samples["zero"]
        # 容差 0.5s：覆盖进程内调度抖动与日志开销；配置的 1.2s 远大于它。
        if extra < 0.7:
            problems.append(
                f"配置 1.2s 退避后间隔只多了 {extra:.2f}s（zero={samples['zero']:.2f}s, "
                f"configured={samples['configured']:.2f}s）：Core 的 delays 没被等过")

    # 本场景改写了全局重试配置；恢复成 e2e 的基准配置，避免影响后续场景。
    _install_retry_config(runtime, max_retries=2, delays=[0, 0],
                          sdk_max_retries=None)

    detail = "; ".join(problems) or (
        f"退避生效：delays=0 → {samples['zero']:.2f}s，"
        f"delays=1.2 → {samples['configured']:.2f}s"
        f"（多 {samples['configured'] - samples['zero']:.2f}s）")
    return ScenarioResult("retry_backoff_is_honoured", not problems, detail)


async def scenario_retry_backoff_shape_is_honoured(runtime: Runtime, stub) -> ScenarioResult:
    """退避的**形状**必须与配置一致：两次退避递增（R52）。

    R51 的场景判「配的这一个是 1.2s，就真等了 1.2s」，是单点幅度。它对形状是
    失明的：``delays=[0.4, 0.8]``、``[0.4, 0.4]``、``[0.8, 0.4]`` 三种配置在
    单点判据下都只是「某个值被等过」，而它们的运维含义完全不同（指数退避 vs
    恒定轮询 vs 倒着来）。

    做法：``[stub:5xx][stub:fail_twice]`` 让前两次请求都失败，于是序列里出现
    两个退避段；配置 ``delays=[0.4, 0.8]``，断言第二段明显长于第一段。
    用**比值**而不是绝对差值：JIT、日志、调度会让两段同时偏移一个固定量，
    比值对这种共模偏移不敏感，而「恒定/递减」这两种失效形状仍然会被抓到
    （比值分别约 1.0 与 0.5）。

    为什么不加大等待：0.4+0.8=1.2s 与 R51 那个场景同量级，CI 预算不变。
    """
    definition = {
        "name": "retry backoff shape",
        "nodes": [_agent_node("shaped", "task [stub:5xx][stub:fail_twice]")],
        "edges": [],
    }
    problems: list[str] = []
    configured = [0.4, 0.8]
    _install_retry_config(runtime, max_retries=2, delays=configured,
                          sdk_max_retries=0)
    stub.requests.clear()
    stub.reset_claims()
    status, nodes = await runtime.run_workflow("wf-e2e-backoff-shape", definition)
    node = nodes.get("shaped")
    if status != "completed" or (node is not None and node.status != "completed"):
        problems.append(
            f"任务未 completed（status={status}），形状场景前提不成立：两次重试应当救回")
    else:
        segments = _backoff_segments(stub, floor=0.2)
        if len(segments) < 2:
            problems.append(
                f"只量到 {len(segments)} 个退避段（间隔 {_request_gaps(stub)}），"
                "判不了形状——需要两次失败各产生一段等待")
        else:
            first, second = segments[0], segments[1]
            # 配置是 0.4 → 0.8（2 倍）。恒定退避给 1.0，递减给 0.5。
            if second < first * 1.5:
                problems.append(
                    f"退避形状不符：配置递增 {configured}，实测段 {first:.2f}s → "
                    f"{second:.2f}s（比值 {second / first:.2f}，应≥1.5）")

    _install_retry_config(runtime, max_retries=2, delays=[0, 0],
                          sdk_max_retries=None)

    return ScenarioResult(
        "retry_backoff_shape_is_honoured",
        not problems,
        "; ".join(problems) or (
            f"退避形状符合配置 {configured}：实测 "
            f"{_backoff_segments(stub, floor=0.2)[:2]}"),
    )


SCENARIOS = {
    "happy_path": scenario_happy_path,
    "failure_propagates": scenario_failure_propagates,
    "turn_terminates": scenario_turn_terminates,
    "transient_error_is_retried": scenario_transient_error_is_retried,
    "permanent_error_is_not_retried": scenario_permanent_error_is_not_retried,
    "stream_stall_fails_fast": scenario_stream_stall_fails_fast,
    "retry_backoff_is_honoured": scenario_retry_backoff_is_honoured,
    "retry_backoff_shape_is_honoured": scenario_retry_backoff_shape_is_honoured,
}
SCENARIO_ORDER = [
    "happy_path",
    "failure_propagates",
    "turn_terminates",
    "transient_error_is_retried",
    "permanent_error_is_not_retried",
    "stream_stall_fails_fast",
    "retry_backoff_is_honoured",
    "retry_backoff_shape_is_honoured",
]


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
        # 重试配置必须非零：故障注入场景要验「重试层接住了瞬时错误」。
        # delays 全 0 是为了不让等待时间混进判据——本脚本判语义，不判退避策略
        # （退避本身由 tests/test_llm_client_params.py 一类单测覆盖）。
        _write_models_config(
            data_root / "models_config.json", stub.base_url,
            max_retries=2, delays=[0, 0],
        )
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
                # 每个场景清一次请求记录与 fail_once 配额，断言里的计数才有意义
                stub.requests.clear()
                stub.reset_claims()
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
