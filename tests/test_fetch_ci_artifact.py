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

import json
from pathlib import Path

from artifact_api_fixture import api_path, listing, server, zip_bytes
from scripts import fetch_ci_artifact as fetch

RUN_ID = "41300000000"
API_PATH = api_path("owner/repo", RUN_ID, "e2e-metrics")


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
    with server(routes, recorded) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": b'{"schema": 1}'}))

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
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            json.dumps({"total_count": 0, "artifacts": []}).encode())

        assert _run(base, tmp_path) == 0

    assert "没有 artifact e2e-metrics" in capsys.readouterr().out


def test_only_the_named_artifact_is_selected(tmp_path: Path, capsys) -> None:
    """服务端过滤之外再按 name 精确匹配：别的 artifact 不能顶替。"""
    routes: dict = {}
    with server(routes) as base:
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
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive", expired=True))

        assert _run(base, tmp_path) == 0

    assert "已过期" in capsys.readouterr().out


def test_transport_errors_fail_loudly(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            500, {"Content-Type": "application/json"},
            b'{"message": "boom"}')

        assert _run(base, tmp_path) == 1

    captured = capsys.readouterr()
    assert "::error::" in captured.err
    assert "500" in captured.err


def test_download_errors_fail_loudly(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
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
    with server(first_routes, first) as first_base, \
            server(second_routes, second) as second_base:
        first_routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{first_base}/redirect"))
        first_routes["/redirect"] = (
            302, {"Location": f"{second_base}/zip"}, b"")
        second_routes["/zip"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": b"{}"}))

        assert _run(first_base, tmp_path) == 0

    assert first[0][1].get("authorization") == "Bearer test-token"
    # 302 之后是新的主机：带 Authorization 会被 blob 主机 401（R71）。
    assert all("authorization" not in headers for _, headers in second)


def test_zip_path_traversal_is_rejected(tmp_path: Path, capsys) -> None:
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"../evil.txt": b"escape"}))

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
