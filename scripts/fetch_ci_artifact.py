"""从 GitHub Actions API 拉取 artifact（R95/R98）。

R94 的边界只剩 ``actions/download-artifact`` 的**传输本身**不能本地复现。
本脚本把这段变成可执行、可测试的代码：列出 run 的 artifacts → 下载 zip →
解压到目标目录；YAML 里只保留调用。

语义（与旧的 ``continue-on-error: true`` 接线刻意不同）：

- run 里没有该 artifact（或已过期）→ 打印说明并退出 **0**：e2e 环境没起来
  不是写回 job 的失败，下一步会打印「本轮不入库」；
- 真实传输错误（401/403/5xx/网络/坏 zip/路径穿越）→ ``::error::`` + 退出 **1**。
  旧接线会把它们吞成「没有 metrics」，静默丢掉一轮（R64：同一退出码的不同
  来源不得互相冒充）。

实现要点：

1. 认证头用 ``add_unredirected_header``：GitHub 的 artifact 下载会 302 到
   blob 主机，把 ``Authorization`` 带过去会 401（R71 实测）。
2. 解压拒绝绝对路径与 ``..``：artifact 是外部输入，不能让它写出目标目录。
3. R98：429/5xx/网络错误按 ``DEFAULT_ATTEMPTS`` 重试（退避可注入），4xx
   （除 429）**不重试**；结果分 ``artifact-fetched`` / ``missing`` / ``expired`` /
   ``fetch-failed`` / ``invalid`` / ``usage``，与 summary 共用同一组字符串。
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_reporting

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_API_URL = "https://api.github.com"
USER_AGENT = "determinflow-fetch-ci-artifact"

# 传输重试：只重试幂等的 GET 与瞬时错误。401/403 重试没有意义（R98）。
DEFAULT_ATTEMPTS = 3
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

REASON_FETCHED = "artifact-fetched"
REASON_MISSING = "artifact-missing"
REASON_EXPIRED = "artifact-expired"
REASON_FAILED = "artifact-fetch-failed"
REASON_INVALID = "artifact-invalid"
REASON_USAGE = "usage"

RESULT_SCHEMA = 1


class FetchError(RuntimeError):
    """传输失败；``attempts`` 是这次失败前实际发起的请求次数。"""

    def __init__(self, message: str, attempts: int = 0) -> None:
        super().__init__(message)
        self.attempts = attempts


class ArtifactInvalid(FetchError):
    """artifact 内容/形状不合法（坏 zip、路径穿越、缺 archive_url）。"""


def _api_url() -> str:
    return os.environ.get("GITHUB_API_URL") or DEFAULT_API_URL


def _request(url: str, token: str | None, timeout: float,
             accept: str) -> urllib.request.Request:
    request = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        # 关键：跳转后不再携带。302 到 blob 主机时带 Authorization 会 401。
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    return request


def _read(url: str, token: str | None, timeout: float,
          accept: str) -> bytes:
    with urllib.request.urlopen(
            _request(url, token, timeout, accept), timeout=timeout) as response:
        return response.read()


def _read_with_retries(url: str, token: str | None, timeout: float,
                       accept: str, attempts: int,
                       sleep) -> tuple[bytes, int]:
    """GET 一次，瞬时错误重试；返回 ``(body, 实际尝试次数)``。"""
    used = 0
    for attempt in range(1, attempts + 1):
        used = attempt
        try:
            return _read(url, token, timeout, accept), used
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace").strip()[:300]
            exc.close()
            if exc.code in RETRY_STATUS and attempt < attempts:
                print(f"GitHub API {exc.code}（{url}），第 {attempt} 次失败，重试",
                      file=sys.stderr)
                sleep(min(0.5 * (2 ** (attempt - 1)), 5.0))
                continue
            raise FetchError(
                f"GitHub API {exc.code}（{url}）：{detail}", used) from exc
        except (urllib.error.URLError, TimeoutError, OSError,
                http.client.HTTPException) as exc:
            if attempt >= attempts:
                raise FetchError(f"拉取失败（{url}）：{exc}", used) from exc
            print(f"拉取失败（{url}）：{exc}，第 {attempt} 次，重试",
                  file=sys.stderr)
            sleep(min(0.5 * (2 ** (attempt - 1)), 5.0))
    raise AssertionError("unreachable")


def _select_artifact(payload: object, name: str,
                     run_id: str) -> tuple[dict | None, str]:
    """返回 ``(artifact, reason)``；没有可选时 artifact 为 None。"""
    if not isinstance(payload, dict):
        raise ArtifactInvalid("artifacts 列表不是对象")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ArtifactInvalid("artifacts 列表缺失或不是列表")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("name") != name:
            continue
        if artifact.get("expired"):
            return None, REASON_EXPIRED
        return artifact, REASON_FETCHED
    return None, REASON_MISSING


def _extract(archive: zipfile.ZipFile, destination: Path) -> list[Path]:
    destination = destination.resolve()
    extracted: list[Path] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        relative = PurePosixPath(info.filename.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactInvalid(f"artifact 含非法路径：{info.filename!r}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        extracted.append(target)
    if not extracted:
        raise ArtifactInvalid("artifact 是空 zip")
    return extracted


def fetch(run_id: str, repo: str, artifact: str, destination: Path,
          token: str | None = None, api_url: str | None = None,
          timeout: float = 30.0, attempts: int = DEFAULT_ATTEMPTS,
          sleep=time.sleep, result_path: Path | None = None,
          summary_path: Path | None = None) -> int:
    attempts_used = 0
    files = 0
    detail = ""
    reason = REASON_FAILED

    def finish(code: int) -> int:
        ci_reporting.emit_summary(summary_path, run_id, reason, detail)
        ci_reporting.emit_result(result_path, {
            "schema": RESULT_SCHEMA,
            "run_id": run_id,
            "repo": repo,
            "artifact": artifact,
            "reason": reason,
            "detail": detail,
            "exit_code": code,
            "attempts": attempts_used,
            "files": files,
            "path": str(destination),
        })
        return code

    if not repo:
        reason = REASON_USAGE
        detail = "缺少仓库（--repo 或 GITHUB_REPOSITORY）"
        print(detail, file=sys.stderr)
        return finish(EXIT_USAGE)
    if not run_id.strip():
        reason = REASON_USAGE
        detail = "--run-id 不能为空"
        print(detail, file=sys.stderr)
        return finish(EXIT_USAGE)
    if attempts < 1:
        reason = REASON_USAGE
        detail = "--attempts 必须 >= 1"
        print(detail, file=sys.stderr)
        return finish(EXIT_USAGE)

    base = (api_url or _api_url()).rstrip("/")
    listing = (
        f"{base}/repos/{repo}/actions/runs/{run_id}/artifacts"
        f"?name={urllib.parse.quote(artifact)}")
    try:
        raw, used = _read_with_retries(
            listing, token, timeout, "application/vnd.github+json",
            attempts, sleep)
        attempts_used += used
        payload = json.loads(raw)
        selected, reason = _select_artifact(payload, artifact, run_id)
        if selected is None:
            if reason == REASON_EXPIRED:
                detail = f"artifact {artifact} 已过期（run {run_id}），本轮不入库"
            else:
                detail = (f"run {run_id} 没有 artifact {artifact}"
                          f"（e2e 环境未启动），本轮不入库")
            print(detail)
            return finish(EXIT_OK)
        archive_url = selected.get("archive_download_url")
        if not isinstance(archive_url, str) or not archive_url:
            raise ArtifactInvalid(
                f"artifact {artifact} 缺少 archive_download_url")
        # GitHub 的 artifact 下载端点只接受 JSON Accept（octet-stream 会 415），
        # 真正的 zip 由 302 后的 blob 主机返回。
        raw, used = _read_with_retries(
            archive_url, token, timeout, "application/vnd.github+json",
            attempts, sleep)
        attempts_used += used
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = len(_extract(archive, destination))
    except ArtifactInvalid as exc:
        attempts_used += exc.attempts
        reason = REASON_INVALID
        detail = str(exc)
        print(f"::error::{detail}", file=sys.stderr)
        return finish(EXIT_FAILED)
    except FetchError as exc:
        attempts_used += exc.attempts
        reason = REASON_FAILED
        detail = str(exc)
        print(f"::error::{detail}", file=sys.stderr)
        return finish(EXIT_FAILED)
    except ValueError as exc:
        # json.JSONDecodeError 是 ValueError 子类：响应不是 JSON 也是传输问题。
        reason = REASON_FAILED
        detail = f"artifact 响应无法解析（{listing}）：{exc}"
        print(f"::error::{detail}", file=sys.stderr)
        return finish(EXIT_FAILED)
    except zipfile.BadZipFile as exc:
        reason = REASON_INVALID
        detail = f"artifact 不是合法 zip：{exc}"
        print(f"::error::{detail}", file=sys.stderr)
        return finish(EXIT_FAILED)

    reason = REASON_FETCHED
    detail = f"已下载 {files} 个文件到 {destination}"
    print(f"artifact {artifact}：{detail}")
    return finish(EXIT_OK)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True,
                        help="workflow run id（CI 用 github.run_id）")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                        help="owner/name；缺省读 GITHUB_REPOSITORY")
    parser.add_argument("--artifact", required=True, help="artifact 名称")
    parser.add_argument("--path", type=Path, required=True,
                        help="解压目标目录")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"),
                        help="GitHub token；缺省读 GITHUB_TOKEN")
    parser.add_argument("--api-url", default=None,
                        help="API 基址；缺省读 GITHUB_API_URL 或 api.github.com")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="单次 HTTP 超时（秒）")
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS,
                        help="传输重试上限（只重试 429/5xx/网络）")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件；缺省读 GITHUB_STEP_SUMMARY")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="机读结果工件；写失败只告警")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return fetch(
        args.run_id, args.repo, args.artifact, args.path,
        token=args.token, api_url=args.api_url, timeout=args.timeout,
        attempts=args.attempts,
        summary_path=args.summary or ci_reporting.default_summary_path(),
        result_path=args.result_json)


if __name__ == "__main__":
    raise SystemExit(main())
