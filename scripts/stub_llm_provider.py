"""OpenAI 兼容桩 provider —— 让 CI 能验编排而不依赖任何真实凭据（R49）。

## 为什么要它

R45/R46/R47 连续三轮把「CI e2e」列为最有价值的缺口。它一直没做，卡的不是
工作量，是凭据：真实 e2e 要一家供应商的 key，而 key 不能进 CI（fork PR
拿不到 secrets），也不该为了跑测试去消耗额度。

桩 provider 把这个卡点换成两件可控的事：

- **协议是真的**：一个真实监听 127.0.0.1 的 HTTP 服务，吐出真实的
  ``text/event-stream`` 分块。被测代码走的是完整链路——ChatOpenAI SDK、
  流式解析、LangGraph 节点、工具调用、引擎回调——只有「谁生成的这些 token」
  是假的。
- **判定是真的**：桩按请求内容决定回什么（有 ``complete_task`` 工具就调用它，
  任务描述里带 ``[stub:fail]`` 就报失败），所以断言可以落在「节点是否真的流转
  到下一个」「失败是否真的被策略接住」上，而不是「有没有返回 200」。

它**不**验证模型质量、不验证提示词好坏、不验证供应商健康——那是
``provider_failure_profile.py`` 与真实快照闸门的事。

## 用法

进程内（pytest，推荐）：

    from scripts.stub_llm_provider import StubProvider
    with StubProvider() as stub:
        stub.base_url          # http://127.0.0.1:<port>/v1
        stub.requests          # 收到的请求体列表，供断言

命令行（手动排查 / 想让被测进程独占一个端口时）：

    python scripts/stub_llm_provider.py --port 0
    # 打印 "listening http://127.0.0.1:PORT/v1" 后阻塞，Ctrl+C 退出
    # --record path.jsonl 把每个请求体写下来

## 行为约定（判定依赖它，改之前先看这里）

1. 请求里最后一条是 ``role=tool`` → 回纯文本收尾。工具结果已经回来了，模型
   该总结而不是再调一次工具；否则 agent 图会在 llm↔tools 之间空转到轮次上限。
2. 请求里提供了名为 ``complete_task`` 或 ``complete_node_task`` 的工具（且不是
   情况 1）→ 回一个指向它的 tool_call。这是「节点完成任务」的唯一信号，
   引擎靠它流转。
3. 任务描述（首条 user 消息）含 ``[stub:fail]`` → 同 2，但 ``status="failure"``，
   用来验失败策略。
4. 其他情况 → 回一句固定文本。

## 故障注入（R50）

除上述语义外，任务文本里的标记可以让桩**按真实 provider 的响应格式**报错，
用来验重试与错误分类在真实 chain 上的行为（此前只在单测层验）：

| 标记 | 桩行为 | 期望被测行为 |
|---|---|---|
| ``[stub:5xx]`` | HTTP 503 + OpenAI 错误体 | 瞬时错误 → 按 ``retry.max_retries`` 重试 |
| ``[stub:429]`` | HTTP 429 + ``rate_limit_exceeded`` | 瞬时错误 → 重试 |
| ``[stub:401]`` | HTTP 401 + ``invalid_api_key`` | **永久**错误 → 不重试，立即失败 |
| ``[stub:stall]`` | SSE 头已发、正文停住 ``stall_seconds`` 秒 | 触发 ``stream_chunk_timeout`` |

``[stub:fail_once]`` 与该标记组合（如 ``[stub:5xx][stub:fail_once]``）表示
**只在前一次请求上失败**，之后正常回复——这是「重试确实救回来了」的唯一可
观察证据（一直失败只能证明它最终失败）。

**这不是伪造失败语义**（R49 §7-5 拒绝的那件事）：注入的是真实 provider 会
发出的 HTTP 状态码与错误体，经过的是真实的 ``openai`` SDK → ``provider_errors``
分类 → ``_should_retry_provider_error`` 判定链路。桩不发明新的失败类型，只
决定「这一发返回什么状态码」。
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 桩里出现的 tool_call id 前缀。测试用它区分「桩伪造的调用」与真实调用。
CALL_ID_PREFIX = "call_stub_"
FAIL_MARKER = "[stub:fail]"
DEFAULT_TEXT = "stub-provider: no-op completion"
_MODEL = "stub-model"

# 故障注入标记（R50）。值是「要返回的 HTTP 状态码」；0 表示不返回错误状态，
# 而是发完 SSE 头之后停住（stream_chunk_timeout 路径）。
ERROR_MARKERS: dict[str, int] = {
    "[stub:5xx]": 503,
    "[stub:429]": 429,
    "[stub:401]": 401,
    "[stub:stall]": 0,
}
# 只让第一次注入生效；之后正常回复。没有它就是「每次请求都失败」。
FAIL_ONCE_MARKER = "[stub:fail_once]"
STALL_SECONDS_DEFAULT = 3.0

# 各状态码对应的 OpenAI 风格错误体。code 必须落在 src/core/provider_errors.py
# 认识的集合里，否则分类会退化成 unknown——那会让「分类对不对」这件事失去意义。
_ERROR_BODIES: dict[int, tuple[str, str]] = {
    503: ("service_unavailable", "stub injected 503: service unavailable"),
    429: ("rate_limit_exceeded", "stub injected 429: rate limit exceeded"),
    401: ("invalid_api_key", "stub injected 401: invalid api key"),
}

_MARKER_RE = re.compile(r"\[stub:[a-z0-9_]+\]")


def _last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict)
                )
    return ""


def _tool_names(payload: dict) -> set[str]:
    names: set[str] = set()
    for tool in payload.get("tools") or []:
        function = (tool or {}).get("function") or {}
        name = function.get("name")
        if name:
            names.add(str(name))
    return names


def injection(payload: dict) -> dict | None:
    """请求是否命中故障注入标记（纯函数）。未命中返回 None。

    只看 ``user`` 消息：``role=tool`` 的追问不该再触发注入，否则「重试成功后
    的收尾请求」会被同一条标记再次打回，永远走不到成功路径。
    """
    messages = payload.get("messages") or []
    last_role = str((messages[-1] or {}).get("role", "")) if messages else ""
    if last_role == "tool":
        return None

    task_text = _last_user_text(messages)
    markers = set(_MARKER_RE.findall(task_text))
    fail_once = FAIL_ONCE_MARKER in markers
    for marker, status in ERROR_MARKERS.items():
        if marker not in markers:
            continue
        if status == 0:
            return {
                "kind": "stall",
                "seconds": STALL_SECONDS_DEFAULT,
                "marker": marker,
                "fail_once": fail_once,
            }
        code, message = _ERROR_BODIES[status]
        return {
            "kind": "error",
            "status": status,
            "code": code,
            "message": message,
            "marker": marker,
            "fail_once": fail_once,
        }
    return None


def _completion_decision(payload: dict) -> dict:
    """正常回复意图（不含故障注入）。"""
    messages = payload.get("messages") or []
    last_role = str((messages[-1] or {}).get("role", "")) if messages else ""
    if last_role == "tool":
        return {"kind": "text", "content": DEFAULT_TEXT}

    names = _tool_names(payload)
    completion_tool = next(
        (name for name in ("complete_task", "complete_node_task") if name in names),
        None,
    )
    if completion_tool is None:
        return {"kind": "text", "content": DEFAULT_TEXT}

    task_text = _last_user_text(messages)
    failed = FAIL_MARKER in task_text
    summary = f"stub completed: {task_text.strip()[:60] or 'no task text'}"
    arguments = {
        "summary": summary,
        "status": "failure" if failed else "success",
    }
    if failed:
        arguments["error"] = "stub induced failure"
    return {"kind": "tool_call", "tool": completion_tool, "arguments": arguments}


def decide(payload: dict) -> dict:
    """把一次请求映射成响应意图。纯函数，测试可直接调它验行为契约。

    命中故障注入标记时返回注入意图（``kind`` 为 ``error`` 或 ``stall``）；
    否则返回正常完成意图。``[stub:fail_once]`` 的「只失败一次」需要跨请求
    状态，由 ``_Handler`` 用 ``StubProvider`` 上的计数器实现——纯函数这一层
    始终按「该注入」返回，测试因此能直接验注入语义本身。
    """
    injected = injection(payload)
    if injected is not None:
        return injected
    return _completion_decision(payload)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    # 静音 BaseHTTPRequestHandler 的默认 stderr access log（CI 日志会很吵）
    def log_message(self, *_args) -> None:  # noqa: D102
        return

    def _json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": _MODEL, "object": "model"}]})
            return
        self._json(404, {"error": {"message": f"unknown path {self.path}"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            self._json(400, {"error": {"message": "malformed JSON body"}})
            return

        server = self.server
        record = {
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "payload": payload,
        }
        server.record(record)

        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": f"unknown path {self.path}"}})
            return

        decision = decide(payload)
        # ``[stub:fail_once]``：只有第一条命中注入的请求真的失败，之后照常回复。
        # 键按「注入标记 + 消息摘要」记，避免同进程里两个场景互相吃掉配额。
        if decision["kind"] in {"error", "stall"} and decision.get("fail_once"):
            key = (decision.get("marker", ""),
                   json.dumps(payload.get("messages") or [], sort_keys=True)[:400])
            if not server.claim(key):
                decision = _completion_decision(payload)

        if decision["kind"] == "error":
            self._error(decision)
            return
        if decision["kind"] == "stall":
            self._stall(decision, payload)
            return
        if payload.get("stream"):
            self._stream(decision, payload)
        else:
            self._complete(decision, payload)

    # ---- 故障注入 ----
    def _error(self, decision: dict) -> None:
        """按 OpenAI 的错误响应形状返回状态码（真实 SDK 才能解析出 code）。"""
        self._json(decision["status"], {
            "error": {
                "message": decision["message"],
                "type": "stub_injected_error",
                "code": decision["code"],
            }
        })

    def _stall(self, decision: dict, payload: dict) -> None:
        """发完 SSE 头与一个 chunk 后停住，让 stream_chunk_timeout 真的触发。

        必须**先**发一个 content chunk：``stream_chunk_timeout`` 量的是「解析出的
        chunk 之间」的间隔，一个 chunk 都不发的路径走的是 httpx 读超时，那条
        路不经过被测的 ``stream_stall`` 分类。
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._chunk(payload, choices=[{
            "index": 0,
            "delta": {"role": "assistant", "content": "partial"},
            "finish_reason": None,
        }])
        time.sleep(float(decision.get("seconds") or STALL_SECONDS_DEFAULT))

    # ---- 非流式 ----
    def _complete(self, decision: dict, payload: dict) -> None:
        message: dict = {"role": "assistant", "content": ""}
        finish_reason = "stop"
        if decision["kind"] == "tool_call":
            message["content"] = None
            message["tool_calls"] = [{
                "id": f"{CALL_ID_PREFIX}1",
                "type": "function",
                "function": {
                    "name": decision["tool"],
                    "arguments": json.dumps(decision["arguments"], ensure_ascii=False),
                },
            }]
            finish_reason = "tool_calls"
        else:
            message["content"] = decision["content"]
        self._json(200, {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", _MODEL),
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        })

    # ---- 流式（SSE）----
    def _chunk(self, payload: dict, **fields) -> None:
        chunk = {
            "id": "chatcmpl-stub",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": payload.get("model", _MODEL),
            **fields,
        }
        self.wfile.write(
            b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n"
        )
        self.wfile.flush()

    def _stream(self, decision: dict, payload: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        if decision["kind"] == "tool_call":
            self._chunk(payload, choices=[{
                "index": 0,
                "delta": {"role": "assistant", "content": None, "tool_calls": [{
                    "index": 0,
                    "id": f"{CALL_ID_PREFIX}1",
                    "type": "function",
                    "function": {
                        "name": decision["tool"],
                        "arguments": json.dumps(decision["arguments"], ensure_ascii=False),
                    },
                }]},
                "finish_reason": None,
            }])
            finish_reason = "tool_calls"
        else:
            self._chunk(payload, choices=[{
                "index": 0,
                "delta": {"role": "assistant", "content": decision["content"]},
                "finish_reason": None,
            }])
            finish_reason = "stop"

        self._chunk(payload, choices=[{
            "index": 0, "delta": {}, "finish_reason": finish_reason,
        }])
        # include_usage 的收尾分块：空 choices + usage（create_llm 在流式下总会请求它）
        self._chunk(payload, choices=[], usage={
            "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
        })
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class StubProvider:
    """进程内桩 provider。既做上下文管理器，也可以手动 start/stop。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, record_path=None):
        self._host = host
        self._port = port
        self._record_path = record_path
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._claims: set[tuple[str, str]] = set()
        self.requests: list[dict] = []

    # -- 生命周期 --
    def start(self) -> "StubProvider":
        server = ThreadingHTTPServer((self._host, self._port), _Handler)
        server.daemon_threads = True
        server.record = self._record  # 绑定实例方法，见 _Handler.do_POST
        server.claim = self.claim    # 同上，供 [stub:fail_once] 用
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="stub-llm-provider",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "StubProvider":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    # -- 观察面 --
    @property
    def port(self) -> int:
        assert self._server is not None, "StubProvider 尚未启动"
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}/v1"

    def _record(self, record: dict) -> None:
        with self._lock:
            self.requests.append(record)
            if self._record_path is not None:
                with open(self._record_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def claim(self, key: tuple[str, str]) -> bool:
        """``[stub:fail_once]`` 的一次性配额：首次 True，之后 False。

        跨请求状态只能放在服务端（纯函数决定「该注入什么」，服务端决定
        「这次还算不算首次」），否则同一进程里两个场景会互相吃掉配额。
        """
        with self._lock:
            if key in self._claims:
                return False
            self._claims.add(key)
            return True

    def reset_claims(self) -> None:
        """清掉 fail_once 配额（每场景开始时调用，与 ``requests.clear()`` 配套）。"""
        with self._lock:
            self._claims.clear()

    def error_requests(self) -> list[dict]:
        """桩判定要报错的那些请求（含 stall），供重试类断言用。"""
        with self._lock:
            return [
                r for r in self.requests
                if decide(r["payload"])["kind"] in {"error", "stall"}
            ]

    def tool_call_requests(self) -> list[dict]:
        """其中桩判定要「调工具」的那些请求，供 e2e 断言用。"""
        with self._lock:
            return [r for r in self.requests if decide(r["payload"])["kind"] == "tool_call"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAI 兼容桩 provider（R49）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--record", default=None, help="把每个请求体写成 JSONL")
    args = parser.parse_args(argv)

    stub = StubProvider(host=args.host, port=args.port, record_path=args.record).start()
    print(f"listening {stub.base_url}", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("stopping", flush=True)
    finally:
        stub.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
