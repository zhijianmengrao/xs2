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

## 判红后重跑一次（R68）

**只对计时型场景**（`retry_backoff_*` 四个）重跑：它们判的是「请求到达间隔
是否按配置被等过」，失效模式里有一类与代码无关——调度/JIT/日志造成的单次
停顿（R64 实测过一次 0.16s 的单段离群）。口径是**任一次通过即通过**：真实
回归在两次里都失败（判据要求**每一段**都落在容差内，不靠运气），而单次停顿
的假红从 p 降到约 p²。**容差一个都不动**——重跑不是为了「松一点」，是为了
让「偶尔慢一次」不冒充「退避没被等过」。

第一次判红的原文保留在 `first_failure` 里，汇总行也会报「有几个场景发生过
重跑」：**重跑后通过 ≠ 没红过**。语义型场景（节点流转、失败传播、重试策略、
流停滞）不重跑：确定性失败重跑一遍只是把同一个缺陷展示两遍。

## 重跑指标（R74）

`attempts` / `first_failure` 此前只写进日志（R68 §7-4）：「重跑有多频繁」只能
靠 grep。`metrics_payload()` 把它们整理成稳定 schema，`--metrics-json PATH`
写出 JSON；CI 的 `e2e retry summary` 步骤把它渲染进 step summary，本地排查与
CI 读同一份数据，不各自解析日志文本。汇总行里的 `[e2e-metrics] ...` 是同一份
数据的单行形式，便于 grep。

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
import math
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
    # 这个场景实际跑了几次（R68）。只有计时型场景在判红时会重跑一次，
    # 因此它是「重试是否真的发生过」的唯一证据——不写进结果里，日志里
    # 就只剩一行 PASS，看不出第一次红过。
    attempts: int = 1
    # 第一次判红的详情（R68）。重试后通过**不等于没红过**：把第一次的
    # 失败原文保留下来，读日志的人才能判断那是抖动还是阈值贴着边界。
    first_failure: str = ""


def metrics_payload(results: list[ScenarioResult]) -> dict:
    """把场景结果整理成可机读的重跑报告（R74）。

    每一项都来自 ``ScenarioResult`` 的 ``attempts`` / ``first_failure``：
    这两个字段是「重跑真的发生过」与「第一次为什么红」的唯一证据，不能只活在
    日志正文里（R68 §7-4 的挂账）。
    """
    return {
        "schema": 1,
        "total": len(results),
        "passed": sum(1 for result in results if result.passed),
        "failed": sum(1 for result in results if not result.passed),
        "retried": sum(1 for result in results if result.attempts > 1),
        "scenarios": [
            {
                "name": result.name,
                "passed": result.passed,
                "attempts": result.attempts,
                "first_failure": result.first_failure,
            }
            for result in results
        ],
    }


def write_metrics(path: Path, payload: dict) -> None:
    """写 ``--metrics-json``（父目录不存在就建，便于 CI 用临时路径）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


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
            if created.get("error") != "workflow_already_exists":
                raise AssertionError(f"创建工作流失败: {created}")
            # R68：同一场景判红重跑时，上一次留下的工作流目录还在，``create``
            # 会以 ``workflow_already_exists`` 拒绝。这不是失败——重跑要的是
            # 「再跑一遍」，不是「再造一个同名工作流」。定义是常量，直接覆盖
            # 成同一份；只有真写不进去（返回 None）才算环境坏。
            #
            # 这条路径**只在重试时**才会走到：没有重试时每个场景的工作流 id
            # 都是新的，所以「本机 e2e 10/10」证明不了它——由
            # ``tests/test_ci_e2e_stub.py`` 的同名用例直接钉住。
            updated = self.workflow_manager.update_workflow(
                workflow_id, {"workflow_id": workflow_id, **definition})
            if updated is None:
                raise AssertionError(
                    f"重跑时无法复用已存在的工作流 {workflow_id}: {created}")

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


# ---------------------------------------------- 退避形状：逐段预算（R65）
#
# 形状判据从 R53 起比的是**相邻比值**（第二段 >= 第一段 * min_ratio）。它对共模
# 偏移不敏感，代价是对**单段**偏移极其敏感——比值里只有被拖慢的那一段起作用。
# R64 在 CI 上第一次量到这种失效：配置 [0.4, 0.8, 1.6]、实测 [0.56, 0.81, ...]，
# 第一段被调度多拖 0.16s，比值掉到 1.45，判据报「第 1->2 段未递增」，而每一段
# 延迟其实一分不差地被等过了。R63 算过这条边界：偏移只落在前一段时预算是
# b/r - a，0.4->0.8 那对只有 0.133s，比共模假设的 0.40s 紧三倍。
#
# 换成**逐段**判据：每个测得的段各自与自己的配置值比。两侧容差故意不对称，
# 依据是量的定义——请求间隔 = 配置的睡眠 + 开销，而**开销不可能为负**（除计时器
# 精度与四舍五入）。于是：
#
#   * 欠睡侧卡死在 0.05s：``m_i < c_i - 0.05`` 只可能是「延迟没被等过」或「用了
#     更小的一项」，那是真 bug，不该被抖动之类的理由放过；
#   * 超睡侧放宽到 0.30s：抖动是环境的，容差量级只能由实测决定（最坏 0.16s，
#     见 R64 §11），它与判据的判定力无关。
#
# 超睡容差不能无限放宽：它必须**严格小于相邻配置的最小差**（本项目三个场景都是
# 0.4s），否则「实现里 delays 下标错一位」会落进容差——那是这条判据还需要分辨的
# 唯一相邻混淆，``RisingShapeSegmentBudget.judgeable`` 就是这条约束的化身。
#
# 逐段判还补上比值判据的一个盲区：所有段被同时放大（例如统一 *2）时比值仍是
# 2.0，旧判据全绿；逐段判在每段分别多出 0.4/0.8/1.6 时逐段报红。
UNDER_SLEEP_TOLERANCE = 0.05
OVER_SLEEP_TOLERANCE = 0.30


@dataclass(frozen=True)
class SegmentDeviation:
    """一段退避的实测与配置之差（秒）。``deviation`` 就是「开销 + 误差」。"""

    index: int
    configured: float
    measured: float

    @property
    def deviation(self) -> float:
        return round(self.measured - self.configured, 3)


def _shape_segment_deviations(segments: list[float],
                              configured: list[float]) -> list[SegmentDeviation]:
    """逐段配对（按到达顺序截到较短的一方），只算偏差，不做判决。"""
    return [SegmentDeviation(index=index, configured=target, measured=measured)
            for index, (measured, target) in enumerate(zip(segments, configured))]


def _rising_shape_violations(segments: list[float], configured: list[float],
                             *, under_tol: float = UNDER_SLEEP_TOLERANCE,
                             over_tol: float = OVER_SLEEP_TOLERANCE) -> list[str]:
    """逐段检查退避是否按配置被等过。返回问题列表（空 = 合格）。

    判据是**每一段与它自己配置值**的差，两侧容差不对称：

    - 欠睡侧 ``< -under_tol``：延迟没被等过。量的是「配置的睡眠 + 开销」，开销
      不可能为负，所以负偏差只能来自实现（或计时器精度，0.05s 足够覆盖）。
    - 超睡侧 ``> over_tol``：等得比配置长太多。这一侧是环境噪声（JIT、日志、
      调度），容差只能由实测抖动决定；但它必须小于相邻配置差，否则分不出
      「下标错一位」。

    为什么不再比相邻比值（R53~R64 的写法）：比值只看两段之差，单段被拖慢
    0.16s 就能把 2 倍递增压到 1.45——R64 §11 实测到的那次假红。比值对共模
    偏移不敏感是优点，对单段偏移过敏是缺点，而后者在本项目里真的发生过。
    实测比值仍写进 ``_shape_headroom_note`` 供诊断，但**不参与判定**。

    两段、三段、四段共用这一个函数：各写一份迟早漂移成两套阈值，而它们判的是
    同一件事。
    """
    if len(segments) < len(configured):
        return [
            f"只量到 {len(segments)} 个退避段，配置需要 {len(configured)} 段，"
            f"判不了形状——每段退避都要求一次失败"
        ]
    problems: list[str] = []
    for item in _shape_segment_deviations(segments, configured):
        deviation = item.deviation
        position = item.index + 1
        if deviation < -under_tol:
            problems.append(
                f"第 {position} 段欠睡：配置 {item.configured:.2f}s，"
                f"实测 {item.measured:.2f}s（少 {-deviation:.2f}s，"
                f"超容差 {under_tol:.2f}s）：退避没有被等过")
        elif deviation > over_tol:
            problems.append(
                f"第 {position} 段超睡：配置 {item.configured:.2f}s，"
                f"实测 {item.measured:.2f}s（多 {deviation:.2f}s，"
                f"超容差 {over_tol:.2f}s）")
    return problems


def _worst_segment_deviation(segments: list[float],
                             configured: list[float]) -> SegmentDeviation | None:
    """偏差最大的那一段（超睡得最厉害的一段）——本判据是**最坏情况**判据。

    R63 的余量用中位数（共模偏移的估计），R64 那次假红正好说明中位数在这里
    是错的统计量：三段偏差 [+0.16, +0.01, +0.02] 的中位数是 0.02，而判据是被
    0.16 那一段推翻的。逐段判只看最大值，所以余量也必须按最大值报。
    """
    deviations = _shape_segment_deviations(segments, configured)
    if not deviations:
        return None
    return max(deviations, key=lambda item: item.deviation)


@dataclass(frozen=True)
class RisingShapeSegmentBudget:
    """逐段判据的判定力边界（R65，取代 R63 的 ``RisingShapeOffsetBudget``）。

    两侧容差对称地受同一条约束限制：**必须小于相邻配置的最小差**
    （``min_gap``）。差一个 ``min_gap`` 的实现错误（下标错一位、填充逻辑取错
    源值）是这条判据还存在的主要理由；容差一旦越过去，那种错误就会落在容差
    里，判据退化成「只判延迟有没有被等」。

    ``min_gap <= 0`` 表示配置本身不是递增的——零容差下也判不出形状。与 R63
    的「负预算是合法返回值」同一条纪律：不抛异常，由调用方把话说清楚。
    """

    under_tol: float
    over_tol: float
    min_gap: float

    @property
    def judgeable(self) -> bool:
        """超睡容差是否严格小于最小相邻配置差（否则分不出下标错一位）。"""
        return 0.0 < self.over_tol < self.min_gap


def _rising_shape_segment_budget(
        configured: list[float], *,
        under_tol: float = UNDER_SLEEP_TOLERANCE,
        over_tol: float = OVER_SLEEP_TOLERANCE) -> RisingShapeSegmentBudget:
    """把「这个配置下判据还能分辨什么」算成三个数（R65）。"""
    if len(configured) < 2:
        raise ValueError("形状判据至少要两段配置，单段没有形状可比")
    if under_tol < 0 or over_tol < 0:
        raise ValueError(
            f"容差不能为负（under_tol={under_tol}, over_tol={over_tol}）")
    min_gap = min(second - first
                  for first, second in zip(configured, configured[1:]))
    return RisingShapeSegmentBudget(
        under_tol=under_tol, over_tol=over_tol, min_gap=min_gap)


def _adjacent_ratios(segments: list[float],
                     configured: list[float]) -> list[float]:
    """相邻实测比值（诊断用，不参与判定）。段数不足或首段为 0 时省略该对。"""
    pairs = list(zip(segments, segments[1:]))[:max(len(configured) - 1, 0)]
    return [round(second / first, 2) for first, second in pairs if first > 0]


def _shape_headroom_note(segments: list[float], configured: list[float], *,
                         under_tol: float = UNDER_SLEEP_TOLERANCE,
                         over_tol: float = OVER_SLEEP_TOLERANCE) -> str:
    """PASS 详情里那一句「这个判据还剩下多少余量」（R63 起，R65 换成逐段）。

    一个只说「符合配置」的判据，读日志的人无法区分「离边界很远」与「擦着门槛
    过关」。把容差、本次最大超睡与倍数写进详情，CI 日志自己就能回答「这个门槛
    什么时候会失准」，不必回头翻文档。

    实测比值仍附在末尾并标注「诊断用」：R53~R64 的判决依据是它，换成逐段之后
    它不再是判据，而它恰好能解释「为什么这一段慢」。
    """
    budget = _rising_shape_segment_budget(
        configured, under_tol=under_tol, over_tol=over_tol)
    if not budget.judgeable:
        if budget.min_gap <= 0:
            return (f"配置本身不是递增的：最小相邻差 {budget.min_gap:.2f}s，"
                    f"判据没有形状可比")
        return (f"容差 {budget.over_tol:.2f}s 不小于最小相邻配置差 "
                f"{budget.min_gap:.2f}s：分不出「用错相邻一项」")
    worst = _worst_segment_deviation(segments, configured)
    ratios = _adjacent_ratios(segments, configured)
    tail = f"；参考：相邻比值 {ratios}（诊断用，不参与判定）" if ratios else ""
    if worst is None:
        return f"超睡容差 {budget.over_tol:.2f}s/段（本次没量到段）{tail}"
    if worst.deviation <= 0:
        return (f"超睡容差 {budget.over_tol:.2f}s/段，本次没有超睡"
                f"（最大偏差 {worst.deviation:.3f}s）{tail}")
    return (f"超睡容差 {budget.over_tol:.2f}s/段，本次最大超睡 "
            f"{worst.deviation:.3f}s（第 {worst.index + 1} 段，余量 "
            f"{budget.over_tol / worst.deviation:.1f} 倍）{tail}")


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


# 单点幅度判据的下限（R69）：配置 1.2s 的退避必须让间隔多出 ≥0.7s。
# 0.5s 的余量覆盖进程内调度抖动与日志开销；配置的 1.2s 远大于它。
BACKOFF_EXTRA_MIN_SECONDS = 0.7


def _backoff_amplitude_problems(samples: dict[str, float]) -> list[str]:
    """单点幅度判据（登记页 #9）：``configured`` 比 ``zero`` 多出的间隔够不够大。

    抽成纯函数是为了让**翻转点**可测（R69）：判据是 ``extra < 0.7`` 即失败，
    所以 0.700s 必须通过、0.699s 必须失败。写在场景函数里时，这两个点只能靠
    真机碰运气——而「常量等于 0.7」并不等于「判决真的在 0.7 翻转」。
    """
    if len(samples) != 2:
        return []
    extra = samples["configured"] - samples["zero"]
    if extra < BACKOFF_EXTRA_MIN_SECONDS:
        return [
            f"配置 1.2s 退避后间隔只多了 {extra:.2f}s"
            f"（zero={samples['zero']:.2f}s, "
            f"configured={samples['configured']:.2f}s）：Core 的 delays 没被等过"
        ]
    return []


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
        problems.extend(_backoff_amplitude_problems(samples))

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
    两个退避段；配置 ``delays=[0.4, 0.8]``，逐段判「实测与自己那一项配置之差
    在容差内」（R65 起；R52~R64 比的是相邻比值，换掉的理由见
    ``_rising_shape_violations`` 的 docstring——CI 上真的被单段偏移判红过一次）。

    为什么不加大等待：0.4+0.8=1.2s 与 R51 那个场景同量级，CI 预算不变。
    """
    definition = {
        "name": "retry backoff shape",
        "nodes": [_agent_node("shaped", "task [stub:5xx][stub:fail_twice]")],
        "edges": [],
    }
    problems: list[str] = []
    configured = [0.4, 0.8]
    segments: list[float] = []
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
        problems.extend(_rising_shape_violations(segments, configured))

    _install_retry_config(runtime, max_retries=2, delays=[0, 0],
                          sdk_max_retries=None)

    return ScenarioResult(
        "retry_backoff_shape_is_honoured",
        not problems,
        "; ".join(problems) or (
            f"退避形状符合配置 {configured}：实测 {segments[:2]}；"
            f"{_shape_headroom_note(segments, configured)}"),
    )


async def scenario_retry_backoff_long_chain_shape_is_honoured(
        runtime: Runtime, stub) -> ScenarioResult:
    """三段退避的形状必须与配置一致（R53）。

    两段判据（``retry_backoff_shape_is_honoured``）能抓到「把递增写成恒定」，
    但抓不到**只在长链后段显形**的回归：例如实现里 ``delays`` 只读前两项、
    第三项回落到默认值，或者循环边界少一次导致最后一段用错了下标。这类 bug
    在 ``max_retries=2`` 下完全不可见——那时根本不存在第三段。

    做法：``[stub:5xx][stub:fail_thrice]`` 让前三次请求都失败，产生三个退避段；
    配置 ``delays=[0.4, 0.8, 1.6]``，逐对断言 1→2、2→3 两对都递增。

    代价是约 0.4+0.8+1.6=2.8s 真实等待（R52 §11-1 已算过仍在 CI 预算内）。
    判据与两段场景共用 ``_rising_shape_violations``，避免两处阈值漂移。
    """
    definition = {
        "name": "retry backoff long chain shape",
        "nodes": [_agent_node("shaped3", "task [stub:5xx][stub:fail_thrice]")],
        "edges": [],
    }
    problems: list[str] = []
    configured = [0.4, 0.8, 1.6]
    segments: list[float] = []
    _install_retry_config(runtime, max_retries=3, delays=configured,
                          sdk_max_retries=0)
    stub.requests.clear()
    stub.reset_claims()
    status, nodes = await runtime.run_workflow("wf-e2e-backoff-long-shape", definition)
    node = nodes.get("shaped3")
    if status != "completed" or (node is not None and node.status != "completed"):
        problems.append(
            f"任务未 completed（status={status}），三段形状场景前提不成立："
            "三次重试应当救回")
    else:
        segments = _backoff_segments(stub, floor=0.2)
        problems.extend(_rising_shape_violations(segments, configured))

    _install_retry_config(runtime, max_retries=2, delays=[0, 0],
                          sdk_max_retries=None)

    return ScenarioResult(
        "retry_backoff_long_chain_shape_is_honoured",
        not problems,
        "; ".join(problems) or (
            f"三段退避形状符合配置 {configured}：实测 {segments[:3]}；"
            f"{_shape_headroom_note(segments, configured)}"),
    )


async def scenario_retry_backoff_four_segment_shape_is_honoured(
        runtime: Runtime, stub) -> ScenarioResult:
    """四段退避的形状必须与配置一致（R55）。

    三段场景（``retry_backoff_long_chain_shape_is_honoured``）仍留一个盲区：
    「前三段都对、第四段错」的回归在 ``max_retries=3`` 下不可见——那时不存在
    第四段。典型形态是实现里 ``delays`` 只读前三项、第四项回落到默认值，或者
    ``while len(delays) < max_retries`` 的填充逻辑在尾项上取错了源值。

    做法：``[stub:5xx][stub:fail_four_times]`` 让前四次请求都失败，产生四个
    退避段；配置 ``delays=[0.4, 0.8, 1.6, 3.2]``，逐对断言 1→2、2→3、3→4 三段
    都递增（``_rising_shape_violations`` 按 ``len(configured)`` 逐段判，本就不
    需要为段数改判据）。

    为什么量级与三段场景相同（0.4 起、总 6.0s）而**不**为了省时间降到 0.2 起：
    逐段判据的超睡容差是 0.30s，而 0.2 起时相邻配置差只有 0.2s——容差大于最小
    相邻差，「delays 下标错一位」就会落进容差里（``RisingShapeSegmentBudget``
    的 ``judgeable`` 会判 False）。0.4 起的相邻差是 0.4s > 0.30s，判据仍然分得
    出相邻项。宁可多等 3 秒，也不要一条分不清「配置写错」与「实现写错」的判据。
    """
    definition = {
        "name": "retry backoff four segment shape",
        "nodes": [_agent_node("shaped4", "task [stub:5xx][stub:fail_four_times]")],
        "edges": [],
    }
    problems: list[str] = []
    configured = [0.4, 0.8, 1.6, 3.2]
    segments: list[float] = []
    _install_retry_config(runtime, max_retries=4, delays=configured,
                          sdk_max_retries=0)
    stub.requests.clear()
    stub.reset_claims()
    status, nodes = await runtime.run_workflow(
        "wf-e2e-backoff-four-shape", definition)
    node = nodes.get("shaped4")
    if status != "completed" or (node is not None and node.status != "completed"):
        problems.append(
            f"任务未 completed（status={status}），四段形状场景前提不成立："
            "四次重试应当救回")
    else:
        segments = _backoff_segments(stub, floor=0.2)
        problems.extend(_rising_shape_violations(segments, configured))

    _install_retry_config(runtime, max_retries=2, delays=[0, 0],
                          sdk_max_retries=None)

    return ScenarioResult(
        "retry_backoff_four_segment_shape_is_honoured",
        not problems,
        "; ".join(problems) or (
            f"四段退避形状符合配置 {configured}：实测 {segments[:4]}；"
            f"{_shape_headroom_note(segments, configured)}"),
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
    "retry_backoff_long_chain_shape_is_honoured": (
        scenario_retry_backoff_long_chain_shape_is_honoured),
    "retry_backoff_four_segment_shape_is_honoured": (
        scenario_retry_backoff_four_segment_shape_is_honoured),
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
    "retry_backoff_long_chain_shape_is_honoured",
    "retry_backoff_four_segment_shape_is_honoured",
]


# ============================================================
# 入口
# ============================================================

# ============================================================
# 失败重跑（R68）
# ============================================================
#
# 只对**计时型**场景重跑：它们判的是「请求到达间隔落在配置的睡眠 ± 容差内」，
# 而这一类判据有一条与代码无关的失效路径——调度、JIT、日志造成的单次停顿。
# R64 在 CI 上实测到过一次：三段形状的首段偏移 0.16s，比值判据由此判红；
# R65 把容差做成逐段非对称（欠睡 0.05s / 超睡 0.30s）之后，这一类抖动
# 落在容差里，但**阈值之上永远还有下一次**（R65 §8-9 如实记过：0.30s 是
# 点估计不是分布）。重跑是处理这一类噪声的正确工具：它不动容差，因此不会
# 削掉「下标错一位」这种真错误的检出力。
#
# 语义型场景（节点流转、失败传播、重试策略、流停滞）**不在此列**：它们的
# 失败来自确定性行为，重跑只会把同一个缺陷展示两遍，并把 CI 时间翻倍——
# 而且会让「第一次红了」变成一个可以忽略的噪声，那正是最危险的那种习惯。
RETRY_ON_FAILURE = frozenset({
    "retry_backoff_is_honoured",
    "retry_backoff_shape_is_honoured",
    "retry_backoff_long_chain_shape_is_honoured",
    "retry_backoff_four_segment_shape_is_honoured",
})

# 每个场景最多跑几次（含第一次）。2 是「偶发」与「稳定」的分界：
# 真实回归在两次里都失败（判据要求**每一段**都落在容差内，不靠运气），
# 而单次停顿的假红从 p 降到约 p²（独立假设）。第三次只换 ~p³，
# 收益迅速衰减，CI 时间却线性增长。
MAX_SCENARIO_ATTEMPTS = 2


def combine_attempts(name: str, attempts: list[ScenarioResult]) -> ScenarioResult:
    """把同一场景的多次尝试压成一个结果（R68 的判定口径：**任一次通过即通过**）。

    三条纪律：

    1. **判定口径只有一条**：任一次通过即通过。不是「取平均」、不是「两次都
       要过」——后者会让容差内的正常抖动把 CI 弄红，把重跑变成纯成本。
    2. **第一次的失败原文必须保留**（``first_failure``）。重跑后通过不等于
       没红过；藏掉它，「重跑了几次」就变成日志里看不见的事，R65 §8-9 的
       余量讨论也就失去了数据来源。
    3. **全部失败时写清跑了几次**：否则读日志的人无法区分「一次就红」与
       「跑满两次都红」，而这两件事对「是不是真回归」的置信度不同。
    """
    if not attempts:
        raise ValueError("没有尝试结果，无法合并")
    for index, result in enumerate(attempts):
        if not result.passed:
            continue
        detail = result.detail
        if index > 0:
            detail += (
                f"；第 {index + 1} 次尝试通过（共跑 {len(attempts)} 次；"
                f"第 1 次判红：{attempts[0].detail}）")
        return ScenarioResult(
            name, True, detail,
            attempts=len(attempts),
            first_failure="" if attempts[0].passed else attempts[0].detail,
        )
    last = attempts[-1]
    return ScenarioResult(
        name, False,
        f"{last.detail}（共跑 {len(attempts)} 次都判红）",
        attempts=len(attempts),
        first_failure=attempts[0].detail,
    )


async def run_with_retries(name: str, run_once) -> ScenarioResult:
    """跑一个场景；判红且属于 ``RETRY_ON_FAILURE`` 时再跑一次（R68）。

    ``run_once`` 是一个无参协程函数（由调用方注入，便于测试不依赖 Runtime）。
    """
    attempts: list[ScenarioResult] = []
    while len(attempts) < MAX_SCENARIO_ATTEMPTS:
        attempts.append(await run_once())
        if attempts[-1].passed or name not in RETRY_ON_FAILURE:
            break
    return combine_attempts(name, attempts)


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
                async def _attempt(name: str = name) -> ScenarioResult:
                    # 每次**尝试**都清一次请求记录与 fail_once 配额：重跑时上一次
                    # 的请求不能算进这一次的断言计数（R68）。
                    stub.requests.clear()
                    stub.reset_claims()
                    try:
                        return await SCENARIOS[name](runtime, stub)
                    except Exception as exc:
                        if args.verbose:
                            traceback.print_exc()
                        return ScenarioResult(name, False, f"场景抛异常: {exc!r}")

                results.append(await run_with_retries(name, _attempt))
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
    # 重跑必须出现在汇总里（R68）：只写在单行详情里，快速浏览的人会以为
    # 「10/10」=「一次没红」。发生过重跑就报次数与口径。
    retried = [r for r in results if r.attempts > 1]
    if retried:
        print(
            f"[e2e] 其中 {len(retried)} 个场景发生过重跑（判定口径：任一次通过"
            f"即通过）：" + "、".join(r.name for r in retried),
            flush=True,
        )
    metrics = metrics_payload(results)
    print(
        f"[e2e-metrics] total={metrics['total']} passed={metrics['passed']} "
        f"failed={metrics['failed']} retried={metrics['retried']}",
        flush=True,
    )
    if args.metrics_json:
        write_metrics(Path(args.metrics_json), metrics)
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
    parser.add_argument(
        "--metrics-json", default=None, metavar="PATH",
        help="把重跑指标写成 JSON（CI step summary 与本地排查共用）",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
