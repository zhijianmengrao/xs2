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
import subprocess
import sys
from pathlib import Path

import pytest

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


class _FakeZipEntry:
    def __init__(self, name: str, data: bytes) -> None:
        self.filename = name
        self._data = data

    def is_dir(self) -> bool:
        return False


class _FakeZip:
    """只实现 ``_extract`` 用到的两个方法，绕开 zipfile 的平台归一化。"""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._entries = [
            _FakeZipEntry(name, data) for name, data in files.items()
        ]

    def infolist(self) -> list[_FakeZipEntry]:
        return list(self._entries)

    def open(self, info: _FakeZipEntry) -> io.BytesIO:
        return io.BytesIO(info._data)


def test_extract_rejects_backslash_traversal(tmp_path: Path) -> None:
    """R104：反斜杠必须先归一，否则 Windows 的 ``..\\`` 会绕过 ``..`` 判定。

    Windows 的 ``zipfile`` 在读取时已经把 ``\\`` 换成 ``/``
    （``_sanitize_filename``），POSIX 不会；用 fake archive 直接驱动，
    两个平台钉住同一条规则。
    """
    archive = _FakeZip({"..\\evil.txt": b"escape"})

    with pytest.raises(fetch.ArtifactInvalid, match="非法路径"):
        fetch._extract(archive, tmp_path / "e2e")  # type: ignore[arg-type]

    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "e2e" / "..\\evil.txt").exists()


@pytest.mark.parametrize("name", [
    "Z:\\evil.txt",
    "Z:evil.txt",
    "dir/Z:\\evil.txt",
])
def test_zip_windows_drive_paths_are_rejected(
        tmp_path: Path, capsys, name: str) -> None:
    """R104：驱动器相对路径在 Windows 上会重置盘符，必须按非法路径拒绝。"""
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({name: b"escape"}))

        assert _run(base, tmp_path) == 1

    assert "非法路径" in capsys.readouterr().err
    destination = tmp_path / "e2e"
    assert not destination.exists() or not any(
        path.is_file() for path in destination.rglob("*")), (
        "被拒绝的 artifact 仍然写出了文件")


def test_missing_repo_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    code = fetch.main([
        "--run-id", RUN_ID,
        "--artifact", "e2e-metrics",
        "--path", str(tmp_path / "e2e"),
    ])
    assert code == 2


# ------------------------------------------------------- 重试与分类（R98）
def _fetch_direct(base: str, tmp_path: Path, **kwargs) -> int:
    return fetch.fetch(
        RUN_ID, "owner/repo", "e2e-metrics", tmp_path / "e2e",
        token="test-token", api_url=base, **kwargs)


def test_fetch_retries_a_transient_5xx(tmp_path: Path) -> None:
    sleeps: list = []
    state = {"calls": 0, "base": ""}
    result = tmp_path / "result.json"

    def listing_route(_handler):
        state["calls"] += 1
        if state["calls"] == 1:
            return 500, {}, b'{"message": "boom"}'
        return (200, {"Content-Type": "application/json"},
                listing(f"{state['base']}/archive"))

    routes = {
        API_PATH: listing_route,
        "/archive": (200, {"Content-Type": "application/zip"},
                     zip_bytes({"e2e-metrics.json": b"{}"})),
    }
    with server(routes) as base:
        state["base"] = base
        assert _fetch_direct(
            base, tmp_path, attempts=3, sleep=sleeps.append,
            result_path=result) == 0

    assert state["calls"] == 2
    assert sleeps == [0.5]
    payload = json.loads(result.read_text(encoding="utf-8"))
    # 列表重试 2 次 + 下载 1 次 = 3 次 HTTP 请求。
    assert payload["attempts"] == 3
    assert payload["reason"] == fetch.REASON_FETCHED


def test_fetch_gives_up_after_the_attempt_cap(tmp_path: Path) -> None:
    sleeps: list = []
    calls = {"count": 0}

    def failing(_handler):
        calls["count"] += 1
        return 500, {}, b'{"message": "boom"}'

    result = tmp_path / "result.json"
    with server({API_PATH: failing}) as base:
        assert _fetch_direct(
            base, tmp_path, attempts=3, sleep=sleeps.append,
            result_path=result) == 1

    assert calls["count"] == 3
    assert sleeps == [0.5, 1.0]
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == fetch.REASON_FAILED
    assert payload["attempts"] == 3


def test_fetch_does_not_retry_auth_errors(tmp_path: Path) -> None:
    sleeps: list = []
    calls = {"count": 0}

    def unauthorized(_handler):
        calls["count"] += 1
        return 401, {}, b'{"message": "bad credentials"}'

    with server({API_PATH: unauthorized}) as base:
        assert _fetch_direct(
            base, tmp_path, attempts=3, sleep=sleeps.append) == 1

    assert calls["count"] == 1
    assert sleeps == []


def test_fetch_result_and_summary_share_reason_and_detail(
        tmp_path: Path) -> None:
    routes: dict = {}
    result = tmp_path / "result.json"
    summary = tmp_path / "summary.md"
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": b"{}"}))
        assert _run(base, tmp_path,
                    "--result-json", str(result),
                    "--summary", str(summary)) == 0

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["schema"] == fetch.RESULT_SCHEMA
    assert payload["reason"] == fetch.REASON_FETCHED
    assert payload["exit_code"] == 0
    assert payload["files"] == 1
    text = summary.read_text(encoding="utf-8")
    assert payload["reason"] in text
    assert payload["detail"] in text


def test_fetch_classifies_missing_and_expired(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            json.dumps({"total_count": 0, "artifacts": []}).encode())
        assert _run(base, tmp_path, "--result-json", str(result)) == 0
        assert json.loads(result.read_text(encoding="utf-8"))[
            "reason"] == fetch.REASON_MISSING

    routes = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive", expired=True))
        assert _run(base, tmp_path, "--result-json", str(result)) == 0
        assert json.loads(result.read_text(encoding="utf-8"))[
            "reason"] == fetch.REASON_EXPIRED


def test_fetch_classifies_a_bad_zip_as_invalid(tmp_path: Path) -> None:
    routes: dict = {}
    result = tmp_path / "result.json"
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"}, b"not a zip")
        assert _run(base, tmp_path, "--result-json", str(result)) == 1

    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["reason"] == fetch.REASON_INVALID
    assert payload["exit_code"] == 1


def test_fetch_result_write_failure_only_warns(
        tmp_path: Path, capsys) -> None:
    routes: dict = {}
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": b"{}"}))
        assert _run(base, tmp_path,
                    "--result-json", str(blocker / "result.json")) == 0

    assert "结果工件写入失败" in capsys.readouterr().err


def test_fetch_runs_as_a_script_not_just_as_an_import(tmp_path: Path) -> None:
    """CI 用 ``python3 scripts/fetch_ci_artifact.py`` 直接执行。

    pytest 会把仓库根目录放进 ``sys.path``，掩盖脚本模式下的 ``scripts``
    导入问题（R98 生产实测 ModuleNotFoundError）；这里用子进程重走一遍。
    """
    script = (Path(__file__).resolve().parents[1]
              / "scripts" / "fetch_ci_artifact.py")
    routes: dict = {}
    with server(routes) as base:
        routes[API_PATH] = (
            200, {"Content-Type": "application/json"},
            listing(f"{base}/archive"))
        routes["/archive"] = (
            200, {"Content-Type": "application/zip"},
            zip_bytes({"e2e-metrics.json": b"{}"}))

        result = subprocess.run([
            sys.executable, "-X", "utf8", str(script),
            "--run-id", RUN_ID,
            "--repo", "owner/repo",
            "--artifact", "e2e-metrics",
            "--path", str(tmp_path / "e2e"),
            "--api-url", base,
            "--token", "test-token",
        ], capture_output=True)

    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert (tmp_path / "e2e" / "e2e-metrics.json").is_file()
