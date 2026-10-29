import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.runnables.config import var_child_runnable_config

from src.core.llm_client import _merge_params, _wrap_llm_with_retry, create_llm
from src.core.model_manager import ModelManager
from src.core.provider_adapters import build_provider_request


class FakeModelManager:
    def get_default_params(self):
        return {
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }

    def build_provider_request(
        self, _provider_id, params, provider, *, model_name=None
    ):
        return build_provider_request("gpt", params, provider)


def test_explicit_null_response_format_disables_global_json_mode():
    kwargs = {}

    merged = _merge_params(
        FakeModelManager(),
        "openai",
        "gpt-test",
        {"hyperparameter_values": {}},
        {"response_format": None},
        kwargs,
    )

    assert merged["response_format"] is None
    assert "model_kwargs" not in kwargs


def test_missing_response_format_still_inherits_global_default():
    kwargs = {}

    merged = _merge_params(
        FakeModelManager(),
        "openai",
        "gpt-test",
        {"hyperparameter_values": {}},
        {"temperature": 0.2},
        kwargs,
    )

    assert merged["response_format"] == {"type": "json_object"}
    assert kwargs["model_kwargs"]["response_format"] == {"type": "json_object"}


def test_stream_chunk_timeout_is_forwarded_from_agent_params():
    kwargs = {}

    merged = _merge_params(
        FakeModelManager(),
        "openai",
        "gpt-test",
        {"hyperparameter_values": {}},
        {"stream_chunk_timeout": 300},
        kwargs,
    )

    assert merged["stream_chunk_timeout"] == 300
    assert kwargs["stream_chunk_timeout"] == 300.0


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf")])
def test_stream_chunk_timeout_rejects_non_positive_or_non_finite_values(timeout):
    with pytest.raises(ValueError, match="finite positive number"):
        _merge_params(
            FakeModelManager(),
            "openai",
            "gpt-test",
            {"hyperparameter_values": {}},
            {"stream_chunk_timeout": timeout},
            {},
        )


def test_anthropic_adapter_claims_and_maps_only_supported_fields():
    request = build_provider_request(
        "anthropic",
        {
            "thinking_enabled": True,
            "reasoning_effort": "medium",
            "thinking_budget": 2048,
            "temperature": 0.2,
            "top_p": 0.5,
            "presence_penalty": 1,
            "response_format": {"type": "json_object"},
            "stream_chunk_timeout": 300,
        },
        {"hyperparameter_values": {"max_completion_tokens": 8192}},
    )

    assert request == {
        "client_kwargs": {
            "max_tokens": 8192,
            "thinking": {"type": "enabled", "budget_tokens": 2048},
            "output_config": {"effort": "medium"},
        },
        "extra_body": {},
    }


def test_anthropic_adapter_uses_adaptive_thinking_without_budget():
    request = build_provider_request(
        "anthropic",
        {
            "thinking_enabled": True,
            "thinking_budget": None,
            "reasoning_effort": "high",
        },
        {"hyperparameter_values": {}},
    )

    assert request["client_kwargs"] == {
        "max_tokens": 32768,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "high"},
    }


def test_anthropic_adapter_validates_manual_thinking_budget():
    with pytest.raises(ValueError, match="at least 1024"):
        build_provider_request(
            "anthropic",
            {"thinking_enabled": True, "thinking_budget": 512},
            {"hyperparameter_values": {"max_completion_tokens": 8192}},
        )


def test_openai_compatible_adapter_does_not_claim_vendor_specific_fields():
    request = build_provider_request(
        "openai_compatible",
        {
            "thinking_enabled": True,
            "reasoning_effort": "high",
            "thinking_budget": 4096,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        {
            "hyperparameter_values": {
                "max_completion_tokens": 8192,
                "frequency_penalty": 0.3,
            }
        },
    )

    assert request == {
        "client_kwargs": {
            "temperature": 0.2,
            "max_tokens": 8192,
            "frequency_penalty": 0.3,
        },
        "extra_body": {},
        "model_kwargs": {"response_format": {"type": "json_object"}},
    }


def test_openai_responses_adapter_omits_chat_completion_penalties():
    request = build_provider_request(
        "openai",
        {
            "temperature": 0.2,
            "top_p": 0.5,
            "presence_penalty": 1,
            "reasoning_effort": "medium",
        },
        {"hyperparameter_values": {}},
    )

    assert request["client_kwargs"] == {
        "temperature": 0.2,
        "top_p": 0.5,
        "reasoning_effort": "medium",
    }
    assert "presence_penalty" not in request["client_kwargs"]


def test_create_llm_selects_native_anthropic_client(tmp_path, monkeypatch):
    config_path = tmp_path / "models_config.json"
    config_path.write_text(
        json.dumps({
            "default_params": {
                "thinking_enabled": True,
                "reasoning_effort": "high",
                "temperature": 0.7,
                "top_p": 1,
                "presence_penalty": 0,
                "thinking_budget": None,
            },
            "retry": {"max_retries": 0, "delays": []},
            "providers": {
                "anthropic": {
                    "name": "Anthropic",
                    "category": "anthropic",
                    "api_format": "anthropic",
                    "base_url": "https://api.anthropic.com/v1",
                    "api_key": "test-key",
                    "models": ["claude-sonnet-4-6"],
                    "hyperparameter_values": {"max_completion_tokens": 8192},
                }
            },
        }),
        encoding="utf-8",
    )
    manager = ModelManager(str(config_path))
    monkeypatch.setattr("src.core.model_manager.get_model_manager", lambda: manager)

    llm = create_llm(
        model_override="anthropic:claude-sonnet-4-6",
        model_params={
            "thinking_enabled": True,
            "reasoning_effort": "medium",
            "thinking_budget": 2048,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
    )

    assert isinstance(llm, ChatAnthropic)
    assert llm.thinking == {"type": "enabled", "budget_tokens": 2048}
    assert llm.output_config == {"effort": "medium"}
    assert llm.max_tokens == 8192
    assert llm.temperature is None
    assert llm.model_kwargs == {}
    assert str(llm._client.base_url) == "https://api.anthropic.com"


def test_create_llm_uses_selected_openai_adapter_on_relay(tmp_path, monkeypatch):
    config_path = tmp_path / "models_config.json"
    config_path.write_text(
        json.dumps({
            "default_params": {
                "reasoning_effort": "high",
                "temperature": 0.7,
                "top_p": 1,
                "presence_penalty": 0,
            },
            "retry": {"max_retries": 0, "delays": []},
            "providers": {
                "determinflow-public": {
                    "name": "DeterminFlow 公益模型",
                    "provider_type": "openai_compatible",
                    "base_url": "https://relay.example.test/v1",
                    "api_key": "test-key",
                    "models": ["gpt-5.6-luna"],
                    "models_config": {
                        "gpt-5.6-luna": {
                            "provider_type": "openai",
                        }
                    },
                    "hyperparameter_values": {},
                }
            },
        }),
        encoding="utf-8",
    )
    manager = ModelManager(str(config_path))
    monkeypatch.setattr("src.core.model_manager.get_model_manager", lambda: manager)

    llm = create_llm(
        model_override="determinflow-public:gpt-5.6-luna",
        model_params={"reasoning_effort": "medium"},
    )

    assert llm.use_responses_api is True
    assert llm.reasoning_effort == "medium"
    assert llm.presence_penalty is None
    assert str(llm.root_client.base_url) == "https://relay.example.test/v1/"


class FakeStreamingLlm:
    def __init__(self, *, fail_after_chunk: bool):
        self.fail_after_chunk = fail_after_chunk
        self.astream_calls = 0

    async def ainvoke(self, _input, *args, **kwargs):
        return None

    async def astream(self, _input, *args, **kwargs):
        self.astream_calls += 1
        if self.fail_after_chunk:
            yield "partial"
            raise RuntimeError("stream interrupted")
        if self.astream_calls == 1:
            raise RuntimeError("failed before first chunk")
        yield "complete"


def test_stream_retry_does_not_duplicate_partial_response():
    async def collect():
        llm = FakeStreamingLlm(fail_after_chunk=True)
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 2, "delays": [0, 0]}
        )
        chunks = []
        with pytest.raises(RuntimeError, match="stream interrupted"):
            async for chunk in wrapped.astream("input"):
                chunks.append(chunk)
        return llm.astream_calls, chunks

    calls, chunks = asyncio.run(collect())
    assert calls == 1
    assert chunks == ["partial"]


def test_stream_retry_is_safe_before_first_chunk():
    async def collect():
        llm = FakeStreamingLlm(fail_after_chunk=False)
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 1, "delays": [0]}
        )
        chunks = [chunk async for chunk in wrapped.astream("input")]
        return llm.astream_calls, chunks

    calls, chunks = asyncio.run(collect())
    assert calls == 2
    assert chunks == ["complete"]


class RecordingTokenCallback:
    def __init__(self):
        self.tokens = []

    def on_llm_new_token(self, token, **_kwargs):
        self.tokens.append(token)


class FakeAinvokeStreamingLlm:
    def __init__(self, *, fail_after_chunk: bool):
        self.fail_after_chunk = fail_after_chunk
        self.ainvoke_calls = 0

    async def ainvoke(self, _input, *args, **kwargs):
        self.ainvoke_calls += 1
        if self.fail_after_chunk or self.ainvoke_calls > 1:
            config = args[0] if args else kwargs.get("config", {})
            for callback in config.get("callbacks", []):
                callback.on_llm_new_token(
                    "partial" if self.fail_after_chunk else "complete",
                    run_id=uuid4(),
                )
        if self.fail_after_chunk or self.ainvoke_calls == 1:
            raise RuntimeError("ainvoke stream interrupted")
        return "complete"

    async def astream(self, _input, *args, **kwargs):
        yield "unused"


def test_ainvoke_retry_stops_after_stream_callback_emits_first_chunk(caplog):
    async def invoke():
        llm = FakeAinvokeStreamingLlm(fail_after_chunk=True)
        callback = RecordingTokenCallback()
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 2, "delays": [0, 0]}
        )
        with pytest.raises(RuntimeError, match="ainvoke stream interrupted") as exc:
            await wrapped.ainvoke(
                "input",
                config={"callbacks": [callback]},
            )
        return llm.ainvoke_calls, callback.tokens, exc.value

    calls, tokens, error = asyncio.run(invoke())

    assert calls == 1
    assert tokens == ["partial"]
    assert error.llm_partial_stream_emitted is True
    assert error.llm_provider_usage_status == "unavailable_on_failed_attempt"
    assert "provider_usage_status=unavailable_on_failed_attempt" in caplog.text


def test_ainvoke_retry_remains_safe_before_first_stream_callback(caplog):
    async def invoke():
        llm = FakeAinvokeStreamingLlm(fail_after_chunk=False)
        callback = RecordingTokenCallback()
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 1, "delays": [0]}
        )
        output = await wrapped.ainvoke(
            "input",
            config={"callbacks": [callback]},
        )
        return llm.ainvoke_calls, callback.tokens, output

    calls, tokens, output = asyncio.run(invoke())

    assert calls == 2
    assert tokens == ["complete"]
    assert output == "complete"
    assert "provider_usage_status=unavailable_on_failed_attempt" in caplog.text


def test_ainvoke_retry_preserves_implicit_parent_callbacks():
    async def invoke():
        llm = FakeAinvokeStreamingLlm(fail_after_chunk=True)
        callback = RecordingTokenCallback()
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 1, "delays": [0]}
        )
        context_token = var_child_runnable_config.set(
            {"callbacks": [callback]}
        )
        try:
            with pytest.raises(RuntimeError, match="ainvoke stream interrupted"):
                await wrapped.ainvoke("input")
        finally:
            var_child_runnable_config.reset(context_token)
        return llm.ainvoke_calls, callback.tokens

    calls, tokens = asyncio.run(invoke())

    assert calls == 1
    assert tokens == ["partial"]


# ---------------------------------------------------- 重试分层（R51）
def _retry_config_manager(tmp_path, retry: dict) -> ModelManager:
    """造一个只带 retry 块的 ModelManager（其余字段取最小可加载形状）。"""
    config_path = tmp_path / "models_config.json"
    config_path.write_text(
        json.dumps({
            "default_params": {"temperature": 0.7},
            "retry": retry,
            "providers": {
                "stub": {
                    "name": "Stub",
                    "provider_type": "openai_compatible",
                    "api_format": "openai",
                    "base_url": "http://127.0.0.1:1/v1",
                    "api_key": "k",
                    "models": ["m"],
                    "hyperparameter_values": {},
                }
            },
        }),
        encoding="utf-8",
    )
    return ModelManager(str(config_path))


def test_retry_config_shape_is_unchanged_when_sdk_retries_are_not_configured(tmp_path):
    """默认形状必须与既往逐字节一致：多一个 None 键会让在途任务 resume 被判身份漂移。

    ``build_effective_agent_definition`` 把 get_retry_config() 的返回值纳入
    ``model_runtime_sha256``，那是 fail-closed 的守卫（不匹配即拒绝启动新
    session）。所以「加了一个新配置项」不能改变默认返回值。
    """
    manager = _retry_config_manager(tmp_path, {"max_retries": 3, "delays": [5, 15, 30]})
    assert manager.get_retry_config() == {
        "max_retries": 3,
        "delays": [5, 15, 30],
    }


def test_retry_config_carries_sdk_max_retries_only_when_configured(tmp_path):
    manager = _retry_config_manager(
        tmp_path, {"max_retries": 1, "delays": [0], "sdk_max_retries": 0})
    assert manager.get_retry_config() == {
        "max_retries": 1,
        "delays": [0],
        "sdk_max_retries": 0,
    }


def test_create_llm_disables_the_sdk_retry_layer_when_configured(tmp_path, monkeypatch):
    """``sdk_max_retries=0`` 必须真的落到 ChatOpenAI 上。

    这是「Core 的退避可被观察」的前提：SDK 层若仍开着，它会先用自己的指数
    退避把瞬时错误救回，Core 的 ``delays`` 一次都不会被等到（R50 §3.4 实测
    sdk=2 + core delays=[3.0] 时间隔只有 0.48s）。
    """
    manager = _retry_config_manager(
        tmp_path, {"max_retries": 1, "delays": [0], "sdk_max_retries": 0})
    monkeypatch.setattr("src.core.model_manager.get_model_manager", lambda: manager)

    llm = create_llm(model_override="stub:m")

    assert llm.max_retries == 0, "SDK 重试层没有被关掉，Core 退避无法被观察"


def test_create_llm_leaves_the_sdk_retry_layer_alone_by_default(tmp_path, monkeypatch):
    """不配置该项时不得改动 SDK 策略。

    ChatOpenAI 的 ``max_retries`` 默认是 ``None``（= 沿用 openai 客户端自带的
    2 次），所以「没动它」的正确形状是**仍为 None**，而不是某个具体数字。
    """
    manager = _retry_config_manager(tmp_path, {"max_retries": 1, "delays": [0]})
    monkeypatch.setattr("src.core.model_manager.get_model_manager", lambda: manager)

    llm = create_llm(model_override="stub:m")

    assert llm.max_retries is None, (
        "默认配置下 SDK 重试策略被我们改写了：既有行为应保持不变"
    )


def test_core_retry_sleeps_for_the_configured_delays(monkeypatch):
    """Core 层必须按 ``delays`` 真的 sleep —— 而不是只把值记在日志里。

    这里把 ``asyncio.sleep`` 换成记录器：断言的是「传给 sleep 的秒数序列」，
    与真实墙钟无关，因此不会给测试引入等待。
    """
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def recording_sleep(delay, *args, **kwargs):
        slept.append(float(delay))
        return await real_sleep(0)

    import src.core.llm_client as llm_client_module

    monkeypatch.setattr(llm_client_module.asyncio, "sleep", recording_sleep)

    class AlwaysFails:
        calls = 0

        async def ainvoke(self, _input, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("transient")

        async def astream(self, _input, *args, **kwargs):
            raise RuntimeError("transient")
            yield  # pragma: no cover

    async def run():
        llm = AlwaysFails()
        wrapped = _wrap_llm_with_retry(
            llm, {"max_retries": 2, "delays": [0.7, 1.9]})
        with pytest.raises(RuntimeError, match="transient"):
            await wrapped.ainvoke("input")
        return llm.calls

    calls = asyncio.run(run())

    assert calls == 3
    assert slept == [0.7, 1.9], f"Core 没有按 delays 等待，实际 {slept}"


# ------------------------- sdk_max_retries 的生产取值决策（R53）
def test_production_config_does_not_pin_the_sdk_retry_layer(tmp_path):
    """生产配置**刻意不设** ``sdk_max_retries``（R53 复核结论）。

    这一项是为**可观察性**而加的（R51：关掉 SDK 层才能量到 Core 的 delays，
    e2e 场景用 ``sdk_max_retries=0``）。把它写进生产配置是另一件事——那会改变
    实际的重试行为，而不只是让判据看得见。

    不写的理由：两层叠加的最坏情况是 ``(sdk+1) * (core+1)`` = 12 次请求、
    约 50s 的 Core 退避 + SDK 的指数退避。写 0 会把最坏请求数降到 4，听起来
    更好，但代价是：SDK 层处理的是**连接级**瞬时故障（TCP 重置、读超时），
    它与 Core 处理的是**协议级**错误（HTTP 5xx / 429）。关掉上层会让连接级
    故障直接冒到 Core，由 ``delays=[5,15,30]`` 用掉一次宝贵的重试配额——而
    Core 的配额是给「供应商暂时不可用」这种需要长间隔的场景留的。

    所以生产取值的结论是：**保持不设**，让两层各管各的故障类型。要改这个
    决策，需要的是一次单独的行为评估（含真实供应商的故障画像），不是顺手
    在配置里加一行。
    """
    import json

    repo_root = Path(__file__).resolve().parents[1]
    for name in ("models_config.json", "models_config.example.json"):
        path = repo_root / "config" / name
        if not path.is_file():
            continue
        config = json.loads(path.read_text(encoding="utf-8"))
        retry = config.get("retry")
        if isinstance(retry, dict):
            assert "sdk_max_retries" not in retry, (
                f"{name} 显式钉住了 sdk_max_retries：改生产重试行为需要单独一轮评估")


def test_disabling_the_sdk_layer_is_for_observability_not_production_policy():
    """``sdk_max_retries=0`` 的正确用法是**场景内**，不是全局配置。

    这条测试把两件事分开：e2e 脚本必须显式关掉它（否则量不到 Core 的退避），
    而生产配置必须不设它。两者用同一个开关但目的相反——把它写进生产配置，
    等于为了让测试看得见而改变了产品行为。
    """
    import re

    repo_root = Path(__file__).resolve().parents[1]
    e2e_source = (repo_root / "scripts" / "e2e_workflow_stub.py").read_text(
        encoding="utf-8")
    assert "sdk_max_retries=0" in e2e_source, (
        "e2e 脚本没有显式关掉 SDK 层：量到的间隔可能来自 SDK 而非 Core delays"
    )
    # 生产代码里除 get_retry_config / create_llm 的读取逻辑外，不该出现硬编码的 0。
    for name in ("model_manager.py", "llm_client.py"):
        source = (repo_root / "src" / "core" / name).read_text(encoding="utf-8")
        assert not re.search(r'"sdk_max_retries"\s*:\s*0', source), (
            f"{name} 里硬编码了 sdk_max_retries=0：那会改变生产重试行为"
        )
