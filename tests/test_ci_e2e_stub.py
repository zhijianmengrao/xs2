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

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from scripts import e2e_workflow_stub as e2e
from scripts import e2e_retry_summary as retry_summary
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


# ---------------------------------------------------------- 故障注入（R50）
def test_injection_markers_map_to_real_http_status_codes() -> None:
    """注入的必须是真实 provider 会发出的状态码，不是自造的失败类型。

    R49 §7-5 拒绝的是「伪造失败语义」；按真实响应格式注入已知错误码是另一
    件事——被注入后走过的仍是 openai SDK → provider_errors → 重试判定的真链路。
    """
    assert stub_module.ERROR_MARKERS == {
        "[stub:5xx]": 503,
        "[stub:429]": 429,
        "[stub:401]": 401,
        "[stub:stall]": 0,
    }


def test_injection_error_codes_are_recognized_by_the_classifier() -> None:
    """注入的错误体里的 code 必须落在分类器认识的集合里。

    否则分类会退化成 unknown，「分类对不对」这件事就失去了判定意义——
    测试会绿，而它测的东西已经不存在了。
    """
    from src.core import provider_errors

    known = (
        provider_errors._QUOTA_CODES
        | provider_errors._RATE_LIMIT_CODES
        | provider_errors._AUTHENTICATION_CODES
        | provider_errors._AUTH_ONLY_CODES
        | provider_errors._PERMISSION_CODES
        | provider_errors._BAD_REQUEST_CODES
        | provider_errors._SERVICE_CODES
    )
    for status, (code, _message) in stub_module._ERROR_BODIES.items():
        assert code in known, f"{status} 的错误码 {code} 不在分类器认识范围内"


def test_injection_is_decided_from_user_messages_only() -> None:
    """``role=tool`` 的追问不得再次触发注入。

    否则「重试成功后的收尾请求」会被同一条标记打回，永远走不到成功路径——
    这种写法在单测里全绿，在真链路上表现为永远失败。
    """
    payload = _payload([
        {"role": "user", "content": "work [stub:5xx]"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "complete_task", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "{}"},
    ], tools=["complete_task"])
    assert stub_module.injection(payload) is None


def test_fail_once_marker_is_parsed_but_state_lives_in_the_server() -> None:
    """``[stub:fail_once]`` 的「只失败一次」不能靠纯函数实现。

    ``decide`` 是纯函数（测试要能直接调它），跨请求状态只能放在服务端；
    这里只钉住「标记被识别」，一次性语义由
    ``test_stub_provider_fails_once_then_succeeds`` 在真实端口上验。
    """
    decision = decide(_payload(
        [{"role": "user", "content": "x [stub:5xx][stub:fail_once]"}],
        tools=["complete_task"],
    ))
    assert decision["kind"] == "error"
    assert decision["fail_budget"] == 1
    # 不带 fail_* 时必须是恒失败（否则「重试救回来了」无法与「本来就没失败」区分）
    always = decide(_payload(
        [{"role": "user", "content": "x [stub:5xx]"}], tools=["complete_task"]))
    assert always["fail_budget"] == 0


def test_fail_twice_marker_grants_a_two_request_budget() -> None:
    """``[stub:fail_twice]`` 的配额是 2（R52）。

    退避**形状**需要两个退避段才可观察；只失败一次时序列里只有一个间隔，
    ``[0.4, 0.8]``、``[0.4, 0.4]``、``[0.8, 0.4]`` 三种配置无法区分。
    """
    decision = decide(_payload(
        [{"role": "user", "content": "x [stub:5xx][stub:fail_twice]"}],
        tools=["complete_task"],
    ))
    assert decision["kind"] == "error"
    assert decision["fail_budget"] == 2


def test_stub_provider_fails_twice_then_succeeds() -> None:
    """真端口上验 fail_twice：前两次 503，第三次 200。

    这是形状场景的前提。若配额实现只记「见过」而不记次数（R52 之前的集合
    写法），第二次就会被当成已用过而直接成功，形状场景会退化成「只有一个
    退避段」然后判不了形状——它自己会红，但红在形状判据上，不容易看出
    根因在这里。
    """
    import urllib.error
    import urllib.request

    def post(base_url: str, text: str) -> int:
        body = json.dumps({
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": text}],
        }).encode("utf-8")
        request = urllib.request.Request(
            base_url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as err:
            return err.code

    with stub_module.StubProvider() as stub:
        url = stub.base_url + "/chat/completions"
        codes = [post(url, "x [stub:5xx][stub:fail_twice]") for _ in range(3)]

    assert codes == [503, 503, 200], f"fail_twice 配额不对：{codes}"


def test_fail_thrice_marker_grants_a_three_request_budget() -> None:
    """``[stub:fail_thrice]`` 的配额是 3（R53）。

    三段形状要三个退避段，因此要三次失败。配额与标记必须一一对应：写 3 段
    ``delays`` 却只失败两次，第三段永远不存在，判据会退化成「段数不够」——
    那时红的是判据而不是配置，最容易误判成实现 bug。
    """
    decision = decide(_payload(
        [{"role": "user", "content": "x [stub:5xx][stub:fail_thrice]"}],
        tools=["complete_task"],
    ))
    assert decision["kind"] == "error"
    assert decision["fail_budget"] == 3


def test_stub_provider_fails_thrice_then_succeeds() -> None:
    """真端口上验 fail_thrice：前三次 503，第四次 200。"""
    import urllib.error
    import urllib.request

    def post(base_url: str, text: str) -> int:
        body = json.dumps({
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": text}],
        }).encode("utf-8")
        request = urllib.request.Request(
            base_url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status
        except urllib.error.HTTPError as err:
            return err.code

    with stub_module.StubProvider() as stub:
        url = stub.base_url + "/chat/completions"
        codes = [post(url, "x [stub:5xx][stub:fail_thrice]") for _ in range(4)]

    assert codes == [503, 503, 503, 200], f"fail_thrice 配额不对：{codes}"


def test_combined_fail_markers_take_the_largest_budget() -> None:
    """同时写多个 fail_* 标记时取**最大**配额，而不是字典序第一个。

    ``[stub:fail_once][stub:fail_thrice]`` 这种组合是复制粘贴的常见残留。若取
    到 1，场景只失败一次，形状判据看到「段数不够」——那是在报告一个与真实
    原因（配额被写小了）不同的缺陷。取最大值让组合至少满足最长的那个要求，
    不会把配置笔误伪装成实现回归。
    """
    decision = decide(_payload(
        [{"role": "user",
          "content": "x [stub:5xx][stub:fail_once][stub:fail_thrice]"}],
        tools=["complete_task"],
    ))
    assert decision["fail_budget"] == 3


def test_stub_provider_fails_once_then_succeeds() -> None:
    """真端口上验 fail_once：第一次 503，第二次 200 且带 SSE 收尾。"""
    import urllib.error
    import urllib.request

    def post(base_url: str, text: str) -> tuple[int, str]:
        body = json.dumps({
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": text}],
        }).encode("utf-8")
        request = urllib.request.Request(
            base_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode("utf-8")

    with stub_module.StubProvider() as stub:
        url = stub.base_url + "/chat/completions"
        first_code, first_body = post(url, "x [stub:5xx][stub:fail_once]")
        second_code, second_body = post(url, "x [stub:5xx][stub:fail_once]")

    assert first_code == 503
    assert json.loads(first_body)["error"]["code"] == "service_unavailable"
    assert second_code == 200
    assert "data: [DONE]" in second_body


def test_stub_provider_returns_401_with_a_recognizable_code() -> None:
    """永久错误的状态码与错误码都要真实可解析（否则「不重试」测的是空气）。"""
    import urllib.error
    import urllib.request

    with stub_module.StubProvider() as stub:
        body = json.dumps({
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": "x [stub:401]"}],
        }).encode("utf-8")
        request = urllib.request.Request(
            stub.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=10)
            raise AssertionError("401 注入没有生效")
        except urllib.error.HTTPError as err:
            assert err.code == 401
            assert json.loads(err.read().decode("utf-8"))["error"]["code"] == "invalid_api_key"


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


# ---------------------------------------------------------------- 重跑指标（R74）
def _result(name: str, passed: bool = True, attempts: int = 1,
            first_failure: str = "") -> "e2e.ScenarioResult":
    return e2e.ScenarioResult(
        name, passed, "detail", attempts=attempts,
        first_failure=first_failure)


def test_metrics_payload_records_attempts_and_first_failure() -> None:
    """重跑频率必须可机读：attempts / first_failure 不能只活在日志正文里。"""
    payload = e2e.metrics_payload([
        _result("clean"),
        _result("flaky", attempts=2, first_failure="第一次红了"),
        _result("broken", passed=False, attempts=2, first_failure="第一次"),
    ])
    assert payload["schema"] == 1
    assert (payload["total"], payload["passed"],
            payload["failed"], payload["retried"]) == (3, 2, 1, 2)
    by_name = {item["name"]: item for item in payload["scenarios"]}
    assert by_name["clean"]["attempts"] == 1
    assert by_name["clean"]["first_failure"] == ""
    assert by_name["flaky"]["attempts"] == 2
    assert by_name["flaky"]["first_failure"] == "第一次红了"
    assert by_name["broken"]["passed"] is False


def test_metrics_payload_counts_zero_retries_for_a_clean_run() -> None:
    """0 次重跑必须是明确的 0，而不是「没有这个字段」。"""
    payload = e2e.metrics_payload([_result("a"), _result("b")])
    assert payload["retried"] == 0
    assert all(item["attempts"] == 1 for item in payload["scenarios"])


def test_write_metrics_creates_parent_and_roundtrips(tmp_path: Path) -> None:
    """CI 用 ``$RUNNER_TEMP/...``，父目录不一定存在。"""
    target = tmp_path / "nested" / "e2e.json"
    payload = e2e.metrics_payload(
        [_result("flaky", attempts=2, first_failure="x")])
    e2e.write_metrics(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_main_passes_the_metrics_path(monkeypatch, tmp_path: Path) -> None:
    """``--metrics-json`` 必须真的传到 ``_run``，不能只是 argparse 里一行。"""
    seen: dict = {}

    async def fake_run(args):
        seen["metrics_json"] = args.metrics_json
        return 0

    monkeypatch.setattr(e2e, "_run", fake_run)
    path = tmp_path / "m.json"
    assert e2e.main(
        ["--only", "happy_path", "--metrics-json", str(path)]) == 0
    assert seen["metrics_json"] == str(path)


def test_retry_summary_reports_retried_scenarios() -> None:
    """step summary 只列重跑过的场景，并给出总尝试次数。"""
    payload = {
        "schema": 1, "total": 3, "passed": 3, "failed": 0, "retried": 1,
        "scenarios": [
            {"name": "clean", "passed": True, "attempts": 1,
             "first_failure": ""},
            {"name": "flaky", "passed": True, "attempts": 2,
             "first_failure": "第一次红了"},
            {"name": "steady", "passed": True, "attempts": 1,
             "first_failure": ""},
        ],
    }
    text = retry_summary.render(payload)
    assert "1 / 3 个场景重跑" in text
    assert "总尝试 4 次" in text
    assert "| flaky | 2 | 第一次红了 |" in text
    assert "clean" not in text and "steady" not in text


def test_retry_summary_tolerates_a_missing_file(
        tmp_path: Path, capsys) -> None:
    """metrics 没写出来时不能静默：打印可见说明，但不让 summary 步骤失败。"""
    assert retry_summary.main([str(tmp_path / "absent.json")]) == 0
    assert "未生成" in capsys.readouterr().out


def test_ci_e2e_writes_metrics_and_renders_a_summary() -> None:
    """接线：e2e 步骤写 metrics，summary 步骤无论成败都把它渲染出来。"""
    run = str(_e2e_step()["run"])
    assert "--metrics-json" in run, "e2e 步骤没有写 metrics"
    assert "e2e-metrics.json" in run

    hits = [
        step for step in _backend_steps()
        if "e2e_retry_summary.py" in str(step.get("run", ""))
    ]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处渲染 e2e metrics"
        f"（实际 {len(hits)} 处）"
    )
    summary_run = str(hits[0]["run"])
    assert "GITHUB_STEP_SUMMARY" in summary_run
    assert hits[0].get("if") == "always()", (
        "summary 步骤必须 always()：e2e 失败时更需要看它重跑了几次")
    assert "secrets." not in json.dumps(hits[0], ensure_ascii=False)


def test_e2e_scenarios_cover_success_failure_and_termination() -> None:
    """每个场景各钉一个命题；少一个就有整类失效回到无覆盖状态。"""
    assert set(e2e.SCENARIOS) == set(e2e.SCENARIO_ORDER)
    assert e2e.SCENARIO_ORDER == [
        "happy_path",
        "failure_propagates",
        "turn_terminates",
        "transient_error_is_retried",
        "permanent_error_is_not_retried",
        "stream_stall_fails_fast",
        "retry_backoff_is_honoured",
        "retry_backoff_shape_is_honoured",
        "retry_backoff_long_chain_shape_is_honoured",
        # R55：四段形状，覆盖「前三段对、第四段错」那类只在长链末端显形的回归。
        "retry_backoff_four_segment_shape_is_honoured",
    ]


def test_e2e_enables_retries_for_the_fault_scenarios() -> None:
    """重试场景要有非零重试预算，否则「重试救回来了」永远判不出来。

    反向也成立：若把 max_retries 写回 0，transient 场景会因为「发一次就失败」
    而红——所以这条不是冗余的配置检查，它守的是场景的前提。
    """
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    assert "max_retries=2" in source, "e2e 没有为非零重试预算留下痕迹"
    assert "delays=[0, 0]" in source, (
        "退避等待会混进 CI 时长；本脚本判语义不判退避策略"
    )


def test_e2e_sets_a_small_stream_chunk_timeout() -> None:
    """停摆场景必须把小超时注入进程环境。

    用默认 120s 会让这一步慢两个数量级，而判据（停摆是否被判失败）与超时
    具体值无关。缺了这一行，stall 场景在 CI 上等于跑不到结论。
    """
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    assert "LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S" in source


# ------------------------------------------------------- 退避场景（R51）
def test_backoff_scenario_disables_the_sdk_retry_layer() -> None:
    """退避场景必须显式 ``sdk_max_retries=0``，否则量到的不是 Core 的 delays。

    ChatOpenAI 自带 ``max_retries=2``，会抢在 Core 包装之前用自身指数退避救回
    瞬时错误。实测 sdk=2 + core delays=[3.0] 时请求间隔只有 0.48s —— Core 的
    3 秒一次都没被等到，场景会量到一个与配置无关的数字然后判定「退避生效」。
    这正是 R50 §3.4「关掉 Core max_retries 后仍绿」的同一个坑。
    """
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    assert "sdk_max_retries=0" in source, (
        "退避场景没有关掉 SDK 重试层：量到的间隔可能来自 SDK 而非 Core delays"
    )


def test_backoff_scenario_uses_a_differential_measurement() -> None:
    """退避判据必须是差分（0 vs 配置值），不能是绝对阈值。

    绝对阈值要吞掉进程启动、日志、调度等不可知开销，只能取很松的数，于是
    「退避被删掉一半」这种回归也能绿。差分比的正是「多出来的等待」。
    """
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    assert "_request_gaps" in source, "退避场景没有量取请求间隔"
    assert '"zero"' in source and '"configured"' in source, (
        "退避场景没有做两次配置的对照"
    )


def test_backoff_scenario_restores_the_baseline_config() -> None:
    """退避场景改写了全局重试配置，必须恢复——否则影响后续场景的判据。"""
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    start = source.index("async def scenario_retry_backoff_is_honoured")
    end = source.index("SCENARIOS = {")
    body = source[start:end]
    assert "max_retries=2, delays=[0, 0]" in body, (
        "退避场景结束后没有恢复 e2e 基准重试配置"
    )


# ------------------------------------------------------- 退避形状（R52）
def _scenario_body(func_name: str, *, until: str) -> str:
    """截取一个场景函数的源码正文。

    用显式的 ``until`` 而不是「到下一个 def 为止」：场景函数之间没有稳定的
    分隔标记，靠名字猜边界正是这类契约测试最容易写歪的地方——切多了会让
    「这条断言只钉这个场景」变成「覆盖半个文件」，切少了则断言永远为真。
    """
    source = (REPO_ROOT / "scripts" / "e2e_workflow_stub.py").read_text(encoding="utf-8")
    start = source.index(f"async def {func_name}")
    return source[start:source.index(until, start)]


def _shape_scenario_body() -> str:
    return _scenario_body(
        "scenario_retry_backoff_shape_is_honoured",
        until="async def scenario_retry_backoff_long_chain_shape_is_honoured")


def _long_chain_scenario_body() -> str:
    return _scenario_body(
        "scenario_retry_backoff_long_chain_shape_is_honoured",
        until="SCENARIOS = {")


def test_shape_scenario_configures_a_rising_backoff() -> None:
    """形状判据要有可判别的配置：两段退避必须显著不同。

    如果配置成 ``[0.4, 0.4]``（恒定），「递增」与「恒定」两种实现都合格，
    判据失去意义。``[0.4, 0.8]`` 的比值是 2.0，与恒定（1.0）、递减（0.5）
    都能分开。
    """
    body = _shape_scenario_body()
    assert "[0.4, 0.8]" in body or "[0.4,0.8]" in body, (
        "形状场景没有配置两段递增的 delays"
    )
    assert "max_retries=2" in body, "形状场景需要两次重试才产生两个退避段"


def test_shape_scenario_uses_the_two_failure_marker() -> None:
    """必须用 ``fail_twice``：``fail_once`` 只产生一个退避段，量不到形状。"""
    body = _shape_scenario_body()
    assert "[stub:fail_twice]" in body, (
        "形状场景没有让两次请求都失败：只有一个退避段时判不了形状"
    )


def test_shape_scenario_uses_the_per_segment_judge() -> None:
    """两段/三段/四段必须共用同一个判据，且不能再留比值门槛的残留。

    R65 把判据从「相邻比值 ≥ 1.5」换成「每段与自己的配置之差在非对称容差内」，
    理由见 ``_rising_shape_violations`` 的 docstring（单段离群会把比值压到门槛
    以下，而延迟其实都被等过了）。这里只钉「场景走的是共享实现」；判据能不能
    分辨对错，由下面那些纯函数用例穷举。
    """
    body = _shape_scenario_body()
    assert "_rising_shape_violations" in body, "形状场景没有走共享的逐段判据"
    assert "min_ratio" not in body, "形状场景还留着比值门槛的残留"


def test_shape_scenario_disables_the_sdk_retry_layer() -> None:
    """与单点场景同一条理由：SDK 层开着就量到 SDK 的指数退避而非 Core delays。"""
    body = _shape_scenario_body()
    assert "sdk_max_retries=0" in body, "形状场景没有关掉 SDK 重试层"


def test_shape_scenario_restores_the_baseline_config() -> None:
    """形状场景同样改写全局重试配置，必须恢复。"""
    body = _shape_scenario_body()
    assert "max_retries=2, delays=[0, 0]" in body, (
        "形状场景结束后没有恢复 e2e 基准重试配置"
    )


# ------------------------------------------------- 三段退避形状（R53）
def test_long_chain_scenario_uses_three_rising_delays() -> None:
    """三段场景的配置必须是可判别的递增序列。

    ``[0.4, 0.8, 1.6]`` 的相邻比值恒为 2.0，与恒定（1.0）分开；若写成
    ``[0.4, 0.8, 0.8]``，第三段就与「第二段对了但第三段没跟上」这个真实缺陷
    同形——判据再也分不清是配置还是实现。
    """
    body = _long_chain_scenario_body()
    assert "[0.4, 0.8, 1.6]" in body or "[0.4,0.8,1.6]" in body, (
        "三段场景没有配置三段递增的 delays"
    )
    assert "max_retries=3" in body, "三段场景需要三次重试才产生三个退避段"


def test_long_chain_scenario_uses_the_three_failure_marker() -> None:
    """必须用 ``fail_thrice``：失败两次只产生两个退避段，第三段不存在。"""
    body = _long_chain_scenario_body()
    assert "[stub:fail_thrice]" in body, (
        "三段场景没有让三次请求都失败：只有两个退避段时判不了第三段"
    )


def test_long_chain_scenario_shares_the_shape_judge() -> None:
    """两段与三段必须共用同一个判据函数。

    各写一份「第二段 ≥ 第一段 1.5 倍」的拷贝，短期没差别，长期必然漂移：
    有人调了门槛只改一处，两套阈值就同时生效，而测试都还是绿的。
    """
    body = _long_chain_scenario_body()
    assert "_rising_shape_violations" in body, (
        "三段场景没有复用共享的形状判据，阈值会与两段场景漂移"
    )
    assert "sdk_max_retries=0" in body, "三段场景没有关掉 SDK 重试层"
    assert "max_retries=2, delays=[0, 0]" in body, (
        "三段场景结束后没有恢复 e2e 基准重试配置"
    )



# ------------------------------------- 形状判据本身（R53~R65，纯函数）
# 上面那些源码契约只钉「场景用了哪个函数」。判据真的能分辨对错，由这里直接
# 测 ``_rising_shape_violations``——它没有 I/O、没有时钟，可以穷举。
#
# R65 把判据从「相邻比值」换成了「逐段 + 非对称容差」。原有行为用例一条没删，
# 只是换了口径重新钉；另补两种旧判据结构性看不见的形状（统一放大、单段离群）。
def test_shape_judge_accepts_a_correctly_configured_chain() -> None:
    assert e2e._rising_shape_violations([0.41, 0.82, 1.63], [0.4, 0.8, 1.6]) == []


def test_shape_judge_rejects_a_constant_backoff() -> None:
    """恒定退避（运维上是轮询而非退避）必须被拒。

    这是 R52/R53 判据存在的首要理由：恒定配置下「某个值被等过」仍然成立，
    单点判据完全看不出问题。R65 之后由**欠睡侧**抓到——第二、三段只量到
    0.42/0.41，比配置的 0.8/1.6 少得远超 0.05s 容差。
    """
    problems = e2e._rising_shape_violations([0.4, 0.42, 0.41], [0.4, 0.8, 1.6])
    assert len(problems) == 2, problems
    assert all("欠睡" in problem for problem in problems), problems


def test_shape_judge_rejects_a_decreasing_chain() -> None:
    """递减（配置写反了）必须被拒，两个方向各自点名。"""
    problems = e2e._rising_shape_violations([1.6, 0.8, 0.4], [0.4, 0.8, 1.6])
    assert len(problems) == 2, problems
    assert "第 1 段超睡" in problems[0], problems
    assert "第 3 段欠睡" in problems[1], problems


def test_shape_judge_catches_a_stale_last_segment() -> None:
    """**R53 的全部价值**：前两段对、第三段没跟上时，只有第 3 段报错。

    这类回归只在三段以上的链上显形——两段判据下第三段根本不存在，它永远绿。
    断言「恰好 1 条、且指向第 3 段」：若判据把前两段也误判成问题，说明它比的
    是相对关系而不是各自的配置值，噪声一进来就会连带假红。
    """
    problems = e2e._rising_shape_violations([0.41, 0.82, 0.85], [0.4, 0.8, 1.6])
    assert len(problems) == 1, problems
    assert "第 3 段" in problems[0], problems[0]


def test_shape_judge_requires_one_segment_per_configured_delay() -> None:
    """段数不足时明确报「判不了」，而不是默默通过。

    这是「永远绿的防护」的入口：少一段却返回空列表，判据会在数据不足时
    判合格。
    """
    problems = e2e._rising_shape_violations([0.41, 0.82], [0.4, 0.8, 1.6])
    assert len(problems) == 1
    assert "只量到 2 个退避段" in problems[0]


# ---- R64/R65：单段离群是旧判据的真正弱点 --------------------------------
def test_shape_judge_tolerates_the_r64_single_segment_outlier() -> None:
    """R64 §11 的真实事故：首段被调度多拖 0.16s，比值掉到 1.45。

    旧判据（相邻比值 >= 1.5）在这组数上判红，而两段延迟其实都被等过了。
    新判据逐段看偏差：+0.16 与 +0.01，都在 0.30s 超睡容差内 → 合格。
    """
    segments = [0.56, 0.81]
    configured = [0.4, 0.8]
    assert segments[1] / segments[0] == pytest.approx(1.446, abs=0.001)
    assert e2e._rising_shape_violations(segments, configured) == []


def test_shape_judge_rejects_an_over_sleep_beyond_the_budget() -> None:
    """同样只慢一段，但慢 0.31s——超过 0.30s 容差必须红，且要点名哪一段。"""
    problems = e2e._rising_shape_violations([0.71, 0.81], [0.4, 0.8])
    assert len(problems) == 1, problems
    assert "第 1 段超睡" in problems[0]
    assert "0.31s" in problems[0]


def test_shape_judge_rejects_under_sleep_tightly() -> None:
    """欠睡侧容差只有 0.05s：0.06s 就红（延迟没被等过），0.04s 放行。

    两侧不对称是量纲决定的：间隔 = 配置的睡眠 + 开销，开销不可能为负，所以
    负偏差只能是实现问题。
    """
    assert e2e._rising_shape_violations([0.34, 0.81], [0.4, 0.8]) != []
    assert e2e._rising_shape_violations([0.36, 0.81], [0.4, 0.8]) == []


def test_shape_judge_rejects_a_uniform_scale_up_the_ratio_could_not_see() -> None:
    """所有段一起放大 2 倍：旧比值判据看到的是 2.0/2.0 → 全绿。

    这是真实的失效形状（把 delays 当「倍数」用，或配置里混进了两次缩放）。
    逐段判在每段都多出 0.4/0.8 时全红——换判据顺带补上的盲区。
    """
    segments = [0.8, 1.6]
    configured = [0.4, 0.8]
    assert segments[1] / segments[0] == pytest.approx(2.0)
    problems = e2e._rising_shape_violations(segments, configured)
    assert len(problems) == 2, problems


# ---- R65：预算与余量 -----------------------------------------------------
def test_segment_budget_pins_the_two_tolerances() -> None:
    """预算把三个数钉死：欠睡 0.05、超睡 0.30、最小相邻差 0.4。"""
    budget = e2e._rising_shape_segment_budget([0.4, 0.8, 1.6])
    assert budget.under_tol == pytest.approx(0.05)
    assert budget.over_tol == pytest.approx(0.30)
    assert budget.min_gap == pytest.approx(0.40)
    assert budget.judgeable is True


def test_segment_budget_loses_the_adjacent_confusion_below_the_tolerance() -> None:
    """超睡容差必须严格小于最小相邻差，否则「下标错一位」落进容差。

    0.2 起（相邻差 0.2s < 0.30s）已经不可判——这正是四段场景不降到 0.2 起的
    算术理由。0.4 起（相邻差 0.4s）才恢复判定力。
    """
    assert e2e._rising_shape_segment_budget([0.2, 0.4]).judgeable is False
    assert e2e._rising_shape_segment_budget([0.4, 0.8]).judgeable is True


def test_segment_budget_rejects_degenerate_configurations() -> None:
    with pytest.raises(ValueError):
        e2e._rising_shape_segment_budget([0.4])
    with pytest.raises(ValueError):
        e2e._rising_shape_segment_budget([0.4, 0.8], over_tol=-0.1)


def test_segment_budget_reports_a_non_rising_config() -> None:
    """配置本身不是递增的：零容差也判不出形状，必须写出来而不是抛异常。"""
    budget = e2e._rising_shape_segment_budget([0.8, 0.4])
    assert budget.min_gap == pytest.approx(-0.4)
    assert budget.judgeable is False
    assert "不是递增的" in e2e._shape_headroom_note([0.9, 0.45], [0.8, 0.4])


def test_worst_deviation_picks_the_max_not_the_median() -> None:
    """R64 的教训：中位数藏着单段离群，最坏情况判据必须看最大值。

    [0.56, 0.81, 1.62] 的偏差是 [+0.16, +0.01, +0.02]，中位数 0.02——而判决
    是被 0.16 那一段决定的。R63 的余量用中位数，正是这一点让「余量 25 倍」读
    起来比实际安全。（R64 实测只记到前两段；第三段的 1.62 是构造值，用来说明
    中位数如何把首段那 0.16 稀释掉。）
    """
    worst = e2e._worst_segment_deviation([0.56, 0.81, 1.62], [0.4, 0.8, 1.6])
    assert worst is not None
    assert worst.index == 0
    assert worst.deviation == pytest.approx(0.16)
    diffs = sorted([0.16, 0.01, 0.02])
    assert diffs[len(diffs) // 2] == pytest.approx(0.02)
    assert e2e._worst_segment_deviation([], [0.4, 0.8]) is None


def test_headroom_note_reports_the_worst_segment_margin() -> None:
    """本机实测 [0.416, 0.818, 1.614]：最大超睡 0.018s（第 2 段），余量 16.7 倍。"""
    note = e2e._shape_headroom_note([0.416, 0.818, 1.614], [0.4, 0.8, 1.6])
    assert "0.30s/段" in note
    assert "0.018s" in note
    assert "第 2 段" in note
    assert "16.7 倍" in note
    assert "诊断用" in note


def test_headroom_note_says_unjudgeable_instead_of_passing_silently() -> None:
    """判不了时必须写出来——『没红』不能被读成『健康』（R62 的同一条纪律）。"""
    crowded = e2e._shape_headroom_note([0.25, 0.35], [0.2, 0.3])
    assert "不小于最小相邻配置差" in crowded
    falling = e2e._shape_headroom_note([0.9, 0.45], [0.8, 0.4])
    assert "不是递增的" in falling


def test_all_shape_scenarios_keep_the_min_gap_above_the_over_sleep_tolerance() -> None:
    """三个形状场景的量级必须让「容差 < 相邻配置差」成立。

    这条是给将来改 ``delays`` 的人看的：降到 0.2 起（相邻差 0.2s < 0.30s），
    判据立刻分不出「下标错一位」与「实现写错」。0.4 起是这条约束的下限。
    """
    for configured in ([0.4, 0.8], [0.4, 0.8, 1.6], [0.4, 0.8, 1.6, 3.2]):
        budget = e2e._rising_shape_segment_budget(configured)
        assert budget.judgeable, configured
        assert budget.min_gap > budget.over_tol, configured


# ------------------------------------------------ 判红后重跑一次（R68）
#
# 计时型场景的失效模式里有一类与代码无关（调度/JIT 造成的单次停顿，R64 实测
# 0.16s 的单段离群）。重跑是处理这类噪声的正确工具：**不动容差**，所以不会
# 削掉「下标错一位」那种真错误的检出力。
#
# 这一组钉住四件事：
#   1. 只有计时型场景在重试集合里（语义型重跑只会展示两遍同一个缺陷）；
#   2. 判定口径是「任一次通过即通过」，且第一次的失败原文必须留下；
#   3. 最多跑 MAX_SCENARIO_ATTEMPTS 次（真实回归不会因为多跑而变绿）；
#   4. 汇总行会报「发生过重跑」——重跑后通过 ≠ 没红过。

_SHAPE_SCENARIOS = {
    "retry_backoff_is_honoured",
    "retry_backoff_shape_is_honoured",
    "retry_backoff_long_chain_shape_is_honoured",
    "retry_backoff_four_segment_shape_is_honoured",
}
_SEMANTIC_SCENARIOS = {
    "happy_path",
    "failure_propagates",
    "turn_terminates",
    "transient_error_is_retried",
    "permanent_error_is_not_retried",
    "stream_stall_fails_fast",
}


def test_retry_policy_covers_exactly_the_timing_scenarios() -> None:
    """重试集合 = 计时型场景，一个不多一个不少。"""
    assert e2e.RETRY_ON_FAILURE == _SHAPE_SCENARIOS
    assert not (e2e.RETRY_ON_FAILURE & _SEMANTIC_SCENARIOS), (
        "语义型场景不得进入重试集合：确定性失败重跑一遍只是把缺陷展示两遍")
    # 集合里的每个名字都必须是真实场景（改名后不能静默退化成「不重试」）。
    assert e2e.RETRY_ON_FAILURE <= set(e2e.SCENARIOS)


def test_combine_attempts_passes_when_any_attempt_passes() -> None:
    """第 1 次判红、第 2 次通过 → 通过，且第一次的原文被保留。"""
    first = e2e.ScenarioResult("retry_backoff_shape_is_honoured", False,
                               "第 1 段超睡：多 0.31s")
    second = e2e.ScenarioResult("retry_backoff_shape_is_honoured", True,
                                "实测 [0.41, 0.8, 1.61]")
    combined = e2e.combine_attempts("retry_backoff_shape_is_honoured",
                                    [first, second])
    assert combined.passed is True
    assert combined.attempts == 2
    assert "第 1 段超睡" in combined.first_failure
    assert "第 2 次尝试通过" in combined.detail
    assert "实测 [0.41, 0.8, 1.61]" in combined.detail


def test_combine_attempts_first_try_pass_keeps_no_failure() -> None:
    """一次就过：attempts=1、first_failure 为空（不能伪造「红过」）。"""
    only = e2e.ScenarioResult("retry_backoff_is_honoured", True, "多出 1.2s")
    combined = e2e.combine_attempts("retry_backoff_is_honoured", [only])
    assert combined.passed is True
    assert combined.attempts == 1
    assert combined.first_failure == ""
    assert combined.detail == "多出 1.2s"


def test_combine_attempts_all_failed_says_how_many_runs() -> None:
    """两次都红：detail 必须写清「共跑 2 次」——否则与「一次就红」分不开。"""
    results = [e2e.ScenarioResult("retry_backoff_is_honoured", False, "少 0.4s")
               for _ in range(2)]
    combined = e2e.combine_attempts("retry_backoff_is_honoured", results)
    assert combined.passed is False
    assert combined.attempts == 2
    assert "共跑 2 次都判红" in combined.detail
    assert combined.first_failure == "少 0.4s"


def test_combine_attempts_rejects_an_empty_list() -> None:
    """没有尝试就没有结论——不返回一个「通过」或「失败」的空壳。"""
    with pytest.raises(ValueError):
        e2e.combine_attempts("happy_path", [])


def test_run_with_retries_retries_a_failing_timing_scenario_once() -> None:
    """计时型场景判红 → 恰好再跑一次；第二次通过则结果通过。"""
    calls: list[int] = []

    async def run_once() -> e2e.ScenarioResult:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            return e2e.ScenarioResult("retry_backoff_shape_is_honoured",
                                      False, "第 1 段超睡 0.31s")
        return e2e.ScenarioResult("retry_backoff_shape_is_honoured",
                                  True, "实测 [0.41, 0.80]")

    result = asyncio.run(
        e2e.run_with_retries("retry_backoff_shape_is_honoured", run_once))
    assert len(calls) == 2
    assert result.passed is True
    assert result.attempts == 2


def test_run_with_retries_stops_at_the_attempt_cap() -> None:
    """稳定回归跑满 MAX_SCENARIO_ATTEMPTS 次就停，不会无限重试。"""
    calls: list[int] = []

    async def run_once() -> e2e.ScenarioResult:
        calls.append(len(calls) + 1)
        return e2e.ScenarioResult("retry_backoff_is_honoured", False, "少 0.4s")

    result = asyncio.run(
        e2e.run_with_retries("retry_backoff_is_honoured", run_once))
    assert len(calls) == e2e.MAX_SCENARIO_ATTEMPTS == 2
    assert result.passed is False
    assert result.attempts == 2


def test_run_with_retries_never_retries_a_semantic_scenario() -> None:
    """语义型场景一次就定论：重跑不改变确定性失败，只会浪费时间。"""
    calls: list[int] = []

    async def run_once() -> e2e.ScenarioResult:
        calls.append(len(calls) + 1)
        return e2e.ScenarioResult("failure_propagates", False, "下游被执行了")

    result = asyncio.run(e2e.run_with_retries("failure_propagates", run_once))
    assert len(calls) == 1
    assert result.passed is False
    assert result.attempts == 1


def test_run_with_retries_does_not_retry_a_passing_scenario() -> None:
    """一次就过就不该有第二次——重试是失败处置，不是采样策略。"""
    calls: list[int] = []

    async def run_once() -> e2e.ScenarioResult:
        calls.append(len(calls) + 1)
        return e2e.ScenarioResult("retry_backoff_shape_is_honoured", True, "ok")

    result = asyncio.run(
        e2e.run_with_retries("retry_backoff_shape_is_honoured", run_once))
    assert len(calls) == 1
    assert result.passed is True
    assert result.attempts == 1


# -------------------------------- 重跑必须能复用已存在的工作流（R68 的坑）
#
# 这一组是本轮最重要的用例。`run_with_retries` 只在本机用假 callable 测过，
# 而真实 Runtime 的 `create_workflow` 对同名 id 返回 `workflow_already_exists`：
# 重跑同一场景时上一次的工作流目录还在，若照旧 raise，重试会把**一次假红**
# 升级成「两次都判红」——机制比不修更糟。本机 e2e 10/10 证明不了它：没有
# 重试时每个场景的工作流 id 都是新的。

class _FakeWorkflowManager:
    """最小的 WorkflowManager 替身：第 2 次 create 复现「已存在」。"""

    def __init__(self, first_error: dict | None = None) -> None:
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
        self._first_error = first_error

    def create_workflow(self, data: dict) -> dict:
        if self._first_error is not None:
            return self._first_error
        if self.created:
            return {"success": False, "error": "workflow_already_exists",
                    "message": f"工作流 {data['workflow_id']} 已存在"}
        self.created.append(data)
        return {"definition": data}

    def update_workflow(self, workflow_id: str, data: dict) -> dict | None:
        self.updated.append((workflow_id, data))
        return {"definition": data}

    async def create_and_run_task(self, workflow_id: str) -> dict:
        return {"success": True, "task_id": "task-1"}

    def _load_task(self, workflow_id: str, task_id: str):
        from types import SimpleNamespace

        return SimpleNamespace(status="completed", node_states={})


class _FakeRuntimeSelf:
    def __init__(self, root: Path, manager: _FakeWorkflowManager) -> None:
        self.data_root = root
        self.workflow_manager = manager


def test_run_workflow_reuses_an_existing_workflow_instead_of_raising(
        tmp_path: Path) -> None:
    """同名工作流第二次 `run_workflow` 必须覆盖定义，而不是抛断言。

    没有这条用例，R68 的重试在真实 Runtime 上会把一次假红变成两次都判红。
    """
    manager = _FakeWorkflowManager()
    fake_self = _FakeRuntimeSelf(tmp_path, manager)
    definition = {"name": "x", "nodes": [], "edges": []}

    async def _twice():
        first = await e2e.Runtime.run_workflow(fake_self, "wf-e2e-retry",
                                               definition)
        second = await e2e.Runtime.run_workflow(fake_self, "wf-e2e-retry",
                                                definition)
        return first, second

    (first_status, _), (second_status, _) = asyncio.run(_twice())
    assert first_status == "completed"
    assert second_status == "completed"
    assert len(manager.created) == 1, "第一次应真的创建"
    assert len(manager.updated) == 1, "第二次应覆盖定义而不是创建第二个"
    assert manager.updated[0][0] == "wf-e2e-retry"


def test_run_workflow_still_raises_on_a_real_creation_error(tmp_path: Path) -> None:
    """除「已存在」以外的创建失败照常抛——不能顺手把所有错误都吞掉。"""
    manager = _FakeWorkflowManager(
        first_error={"success": False, "error": "workflow_disabled",
                     "message": "工作流未启用"})
    fake_self = _FakeRuntimeSelf(tmp_path, manager)

    with pytest.raises(AssertionError):
        asyncio.run(e2e.Runtime.run_workflow(
            fake_self, "wf-e2e-disabled", {"name": "x", "nodes": [], "edges": []}))
