"""R95：artifact 拉取脚本的行为用例（假 HTTP 服务，不走真实 GitHub）。

钉住四件事：

1. 命名 artifact 会被下载并解压到目标目录；
2. 没有 artifact / 已过期 → 退出 0（e2e 环境没起来不是写回失败）；
3. 真实传输错误 → ``::error::`` + 退出 1（旧接线的 continue-on-error
   会把它吞成「没有 metrics」，静默丢一轮）；
4. 302 到别的 blob 主机时不带 Authorization（R71 实测会 401），
   以及 zip 里的 ``..`` 不能写出目标目录。
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts import fetch_ci_artifact as fetch

RUN_ID = "41300000000"
API_PATH = f"/repos/owner/repo/actions/runs/{RUN_ID}/artifacts?name=e2e-metrics"


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@contextmanager
def _server(routes: dict, recorded: list | None = None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server 的约定
            if recorded is not None:
                recorded.append(
                    (self.path, {key.lower(): value
                                 for key, value in self.headers.items()}))
            route = routes.get(self.path)
            if route is None:
                self.send_response(404)
                self.end_headers()
                return
            status, headers, body = route
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _listing(archive_url: str, *, expired: bool = False) -> bytes:
    return json.dumps({"total_count": 1, "artifacts": [{
        "id": 7, "name": "e2e-metrics", "expired": expired,
        "archive_download_url": archive_url,
    }]}).encode()


def _run(base: str, tmp_path: Path, *extra: str) -> int:
    return fetch.main([
        "--run-id", RUN_ID,
        "--repo", "owner/repo",
        "--artifact", "e2e-metrics",
        "--path", str(tmp_path / "e2e"),
        "--api-url", base,
        "--token", "test-token",
        *extra,
    ])


def test_fetch_extracts_the_named_artifact(tmp_path: Path) -> None:
    recorded: list = []
    routes: dict = {}
    with _server(routes, recorded) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            _listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            _zip({"e2e-metrics.json": b'{"schema": 1}'}))

        assert _run(base, tmp_path) == 0

    assert (tmp_path / "e2e" / "e2e-metrics.json").read_bytes() == b'{"schema": 1}'
    # 列表请求带认证头；查询参数把 artifact 名交给服务端过滤。
    assert recorded[0][0] == API_PATH
    assert recorded[0][1].get("authorization") == "Bearer test-token"
    # R95 生产实测：下载端点用 octet-stream 会 415，两个请求都必须是 JSON Accept。
    assert recorded[0][1].get("accept") == "application/vnd.github+json"
    assert recorded[1][1].get("accept") == "application/vnd.github+json"


def test_missing_artifact_is_not_a_failure(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            json.dumps({"total_count": 0, "artifacts": []}).encode())

        assert _run(base, tmp_path) == 0

    assert "没有 artifact e2e-metrics" in capsys.readouterr().out


def test_only_the_named_artifact_is_selected(tmp_path: Path, capsys) -> None:
    """服务端过滤之外再按 name 精确匹配：别的 artifact 不能顶替。"""
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            json.dumps({"total_count": 1, "artifacts": [{
                "id": 1, "name": "other", "expired": False,
                "archive_download_url": f"{base}/wrong",
            }]}).encode())

        assert _run(base, tmp_path) == 0

    assert "没有 artifact e2e-metrics" in capsys.readouterr().out


def test_expired_artifact_is_not_a_failure(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            _listing(f"{base}/archive", expired=True))

        assert _run(base, tmp_path) == 0

    assert "已过期" in capsys.readouterr().out


def test_transport_errors_fail_loudly(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            500, {"Content-Type": "application/json"},
            b'{"message": "boom"}')

        assert _run(base, tmp_path) == 1

    captured = capsys.readouterr()
    assert "::error::" in captured.err
    assert "500" in captured.err


def test_download_errors_fail_loudly(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            _listing(f"{base}/archive"))
        routes["/archive"] = (
            403, {"Content-Type": "application/json"},
            b'{"message": "forbidden"}')

        assert _run(base, tmp_path) == 1

    assert "403" in capsys.readouterr().err


def test_redirect_to_another_host_drops_the_token(tmp_path: Path) -> None:
    first: list = []
    second: list = []
    first_routes: dict = {}
    second_routes: dict = {}
    with _server(first_routes, first) as first_base, \
            _server(second_routes, second) as second_base:
        first_routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            _listing(f"{first_base}/redirect"))
        first_routes["/redirect"] = (
            302, {"Location": f"{second_base}/zip"}, b"")
        second_routes["/zip"] = (
            200, {"Content-Type": "application/zip"},
            _zip({"e2e-metrics.json": b"{}"}))

        assert _run(first_base, tmp_path) == 0

    assert first[0][1].get("authorization") == "Bearer test-token"
    # 302 之后是新的主机：带 Authorization 会被 blob 主机 401（R71）。
    assert all("authorization" not in headers for _, headers in second)


def test_zip_path_traversal_is_rejected(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with _server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            _listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            _zip({"../evil.txt": b"escape"}))

        assert _run(base, tmp_path) == 1

    assert "非法路径" in capsys.readouterr().err
    assert not (tmp_path / "evil.txt").exists()


def test_missing_repo_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    code = fetch.main([
        "--run-id", RUN_ID,
        "--artifact", "e2e-metrics",
        "--path", str(tmp_path / "e2e"),
    ])
    assert code == 2
