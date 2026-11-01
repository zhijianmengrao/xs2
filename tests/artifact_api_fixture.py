"""假 GitHub artifact API（R95/R96 共用测试夹具）。

不要命名为 ``test_*``：这是夹具模块，不是用例。``test_fetch_ci_artifact`` 与
``test_replay_ci_writeback`` 共用同一份路由/服务实现，避免 R80 的「同一事实
写两处」。
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def api_path(repo: str, run_id: str, artifact: str) -> str:
    return (f"/repos/{repo}/actions/runs/{run_id}/artifacts"
            f"?name={artifact}")


def listing(archive_url: str, *, name: str = "e2e-metrics",
            expired: bool = False) -> bytes:
    return json.dumps({"total_count": 1, "artifacts": [{
        "id": 7, "name": name, "expired": expired,
        "archive_download_url": archive_url,
    }]}).encode()


@contextmanager
def server(routes: dict, recorded: list | None = None):
    """在 127.0.0.1 的随机端口起服务；``routes`` 可在启动后继续填充。"""

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

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
