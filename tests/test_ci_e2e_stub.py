"""CI e2e（桩 provider）的契约（R49）。

R45/R46/R47 连续三轮把「CI e2e」列为最有价值的缺口，卡点是凭据。R49 用
``scripts/stub_llm_provider.py``（真实 HTTP + SSE 的 OpenAI 兼容桩）解开这个卡点，
``scripts/e2e_workflow_stub.py`` 用它在**独立进程**里真跑一遍工作流编排。

本文件钉住三件在 pytest 里无法直接跑、却最容易悄悄失效的事：

1. **桩的响应语义**（纯函数 ``decide``）。尤其是「收到 tool 结果后必须回文本」：
   写错了不会报错，只会让 agent 图在 llm↔tools 之间空转到轮次上限，CI 表现
   为超时而不是失败。
2. **CI 真的会跑它**。静态解析 ``ci.yml``——「忘了接线」这种回归运行时永远
   看不出来（没跑的那一步当然不会失败）。
3. **接线本身不自相矛盾**：不读 secrets、e2e 的退出码语义（3 = 环境坏，不是
   产品坏）被 CI 当真区分。

e2e 脚本本身**不**在本文件里跑：它要独立进程 + 临时 DATA_DIR（``src/config.py``
在 import 期就把路径求值成常量），在本进程内跑会污染后续用例。它的真实执行
入口是 CI 的 ``Workflow orchestration e2e (stub provider)`` 一步。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import e2e_workflow_stub as e2e
from scripts import stub_llm_provider as stub_module
from scripts.stub_llm_provider import FAIL_MARKER, decide

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------- 桩的语义
def _payload(messages: list[dict], tools: list[str] | None = None) -> dict:
    return {
        "model": "stub-model",
        "messages": messages,
        "tools": [
            {"type": "function", "function": {"name": name, "parameters": {}}}
            for name in (tools or [])
        ],
    }


def test_stub_returns_text_when_last_message_is_a_tool_result() -> None:
    """工具结果回来后必须收尾。

    这是桩最容易写错的一条：若这里仍返回 tool_call，agent 图会在 llm↔tools
    之间空转到轮次上限——CI 上表现为超时，而超时不会被读成「桩写错了」。
    """
    payload = _payload(
        [
            {"role": "user", "content": "do the thing"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "complete_task", "arguments": "{}"}},
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "{\"success\": true}"},
        ],
        tools=["complete_task"],
    )

    assert decide(payload)["kind"] == "text"


def test_stub_calls_the_completion_tool_when_available() -> None:
    """有完成工具就必须调它——否则节点永远等不到完成信号。"""
    for name in ("complete_task", "complete_node_task"):
        decision = decide(_payload([{"role": "user", "content": "work"}], tools=[name]))
        assert decision["kind"] == "tool_call"
        assert decision["tool"] == name
        assert decision["arguments"]["status"] == "success"


def test_stub_emits_failure_status_for_marked_task() -> None:
    """``[stub:fail]`` 必须变成 status=failure，否则失败策略那条路径是死的。"""
    decision = decide(_payload(
        [{"role": "user", "content": f"please break {FAIL_MARKER}"}],
        tools=["complete_task"],
    ))
    assert decision["kind"] == "tool_call"
    assert decision["arguments"]["status"] == "failure"
    assert decision["arguments"]["error"]


def test_stub_does_not_call_tools_absent_from_the_request() -> None:
    """没有完成工具时不得凭空造 tool_call：那会让模型调用一个不存在的工具。"""
    decision = decide(_payload([{"role": "user", "content": "work"}], tools=["read_file"]))
    assert decision["kind"] == "text"


def test_stub_marker_constant_matches_between_modules() -> None:
    """两处各写了一份标记常量；漂移会让失败场景静默变成成功场景。"""
    assert e2e.FAIL_MARKER == stub_module.FAIL_MARKER == "[stub:fail]"


def test_stub_provider_serves_models_and_chat_completions() -> None:
    """真起一个端口，验 GET /models 与 POST /chat/completions（流式与非流式）。

    这不是「再测一遍 decide」：它验的是 HTTP/SSE 那层真的能对接 ChatOpenAI
    期望的形状（``data: [DONE]``、``finish_reason``、usage 收尾块）。协议层
    写错时 decide 全绿也没用。
    """
    import urllib.request

    with stub_module.StubProvider() as stub:
        with urllib.request.urlopen(stub.base_url + "/models", timeout=10) as resp:
            models = json.loads(resp.read().decode("utf-8"))
        assert models["data"][0]["id"] == "stub-model"

        body = json.dumps({
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        }).encode("utf-8")
        request = urllib.request.Request(
            stub.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            stream = resp.read().decode("utf-8")

        assert "data: [DONE]" in stream
        assert '"finish_reason": "stop"' in stream
        assert stub.requests, "桩没有记录到这次请求"


# ---------------------------------------------------------------- CI 接线
def _load_ci() -> dict:
    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _backend_steps() -> list[dict]:
    jobs = _load_ci().get("jobs")
    assert isinstance(jobs, dict)
    backend = jobs.get("backend")
    assert backend is not None, "ci.yml 缺少 backend job"
    steps = backend.get("steps")
    assert isinstance(steps, list)
    return steps


def _e2e_step() -> dict:
    """按 run 内容定位 e2e 步骤，不按名字（改名不该让测试失去意义）。"""
    hits = [
        step for step in _backend_steps()
        if "e2e_workflow_stub.py" in str(step.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处跑 e2e_workflow_stub.py"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def test_ci_runs_the_stub_e2e() -> None:
    """R45/R46/R47 三轮挂着的缺口：CI 上没有任何一步真跑工作流编排。"""
    step = _e2e_step()
    run = str(step["run"])
    assert "python scripts/e2e_workflow_stub.py" in run


def test_ci_e2e_step_takes_no_secrets() -> None:
    """桩路线的全部意义：fork PR 也能跑，所以绝不能引 secrets。"""
    step = _e2e_step()
    text = json.dumps(step, ensure_ascii=False)
    assert "secrets." not in text, (
        "e2e 步骤引用了 secrets：那会让 fork PR 无法运行，等于退回 R48 之前的状态"
    )


def test_ci_e2e_step_distinguishes_environment_from_product_failure() -> None:
    """退出码 3（环境坏）与 1（编排坏）要分开提示，否则排查方向会被带偏。"""
    run = str(_e2e_step()["run"])
    assert '"$code" -eq 3' in run, "e2e 步骤没有区分退出码 3（环境无法启动）"
    assert any(
        token in run for token in ("装配栈", "环境", "environment")
    ), "e2e 步骤没有说明退出码 3 的含义"


def test_ci_e2e_step_is_not_a_permanently_green_step() -> None:
    """这一步必须能红。

    R45/R46/R47 反复批评「永远绿的防护」：写成 ``exit 0`` 或把退出码 3 降级成
    警告，CI 会一直绿，而 e2e 早已失去判定能力。这里反向钉死这件事。
    """
    run = str(_e2e_step()["run"])
    assert "exit 0" not in run, "e2e 步骤以 exit 0 收尾，等于永远绿"
    assert "exit $code" in run or "exit ${code}" in run, (
        "e2e 步骤没有把被测脚本的退出码透传出去"
    )
    assert "::warning::" not in run, (
        "把非零退出码降级成 warning 会让这一步永远绿：环境起不来通常是 import 链断了"
    )


def test_e2e_script_exit_codes_are_stable() -> None:
    """脚本自己的常量与 CI 的解释必须一致——改一处忘另一处会让 3 被当成 bug。"""
    assert e2e.EXIT_OK == 0
    assert e2e.EXIT_ASSERTION_FAILED == 1
    assert e2e.EXIT_ENVIRONMENT_BROKEN == 3


def test_e2e_scenarios_cover_success_failure_and_termination() -> None:
    """三个场景各钉一个命题；少一个就有整类失效回到无覆盖状态。"""
    assert set(e2e.SCENARIOS) == set(e2e.SCENARIO_ORDER)
    assert e2e.SCENARIO_ORDER == [
        "happy_path",
        "failure_propagates",
        "turn_terminates",
    ]
