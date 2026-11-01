"""从 GitHub Actions API 拉取 artifact（R95）。

R94 的边界只剩 ``actions/download-artifact`` 的**传输本身**不能本地复现。
本脚本把这段变成可执行、可测试的代码：列出 run 的 artifacts → 下载 zip →
解压到目标目录；YAML 里只保留调用。

语义（与旧的 ``continue-on-error: true`` 接线刻意不同）：

- run 里没有该 artifact（或已过期）→ 打印说明并退出 **0**：e2e 环境没起来
  不是写回 job 的失败，下一步会打印「本轮不入库」；
- 真实传输错误（401/403/5xx/网络/坏 zip/路径穿越）→ ``::error::`` + 退出 **1**。
  旧接线会把它们吞成「没有 metrics」，静默丢掉一轮（R64：同一退出码的不同
  来源不得互相冒充）。

两个实现要点：

1. 认证头用 ``add_unredirected_header``：GitHub 的 artifact 下载会 302 到
   blob 主机，把 ``Authorization`` 带过去会 401（R71 实测）。
2. 解压拒绝绝对路径与 ``..``：artifact 是外部输入，不能让它写出目标目录。
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

DEFAULT_API_URL = "https://api.github.com"
USER_AGENT = "determinflow-fetch-ci-artifact"


class FetchError(RuntimeError):
    """artifact 传输/内容不合法；消息会以 ``::error::`` 出现在 CI 日志里。"""


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


def _select_artifact(payload: object, name: str, run_id: str) -> dict | None:
    if not isinstance(payload, dict):
        raise FetchError("artifacts 列表不是对象")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise FetchError("artifacts 列表缺失或不是列表")
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("name") != name:
            continue
        if artifact.get("expired"):
            print(f"artifact {name} 已过期（run {run_id}），本轮不入库")
            return None
        return artifact
    print(f"run {run_id} 没有 artifact {name}（e2e 环境未启动），本轮不入库")
    return None


def _extract(archive: zipfile.ZipFile, destination: Path) -> list[Path]:
    destination = destination.resolve()
    extracted: list[Path] = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        relative = PurePosixPath(info.filename.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise FetchError(f"artifact 含非法路径：{info.filename!r}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as output:
            shutil.copyfileobj(source, output)
        extracted.append(target)
    if not extracted:
        raise FetchError("artifact 是空 zip")
    return extracted


def fetch(run_id: str, repo: str, artifact: str, destination: Path,
          token: str | None = None, api_url: str | None = None,
          timeout: float = 30.0) -> int:
    if not repo:
        print("缺少仓库（--repo 或 GITHUB_REPOSITORY）", file=sys.stderr)
        return EXIT_USAGE
    if not run_id.strip():
        print("--run-id 不能为空", file=sys.stderr)
        return EXIT_USAGE
    base = (api_url or _api_url()).rstrip("/")
    listing = (
        f"{base}/repos/{repo}/actions/runs/{run_id}/artifacts"
        f"?name={urllib.parse.quote(artifact)}")
    try:
        payload = json.loads(_read(
            listing, token, timeout, "application/vnd.github+json"))
        selected = _select_artifact(payload, artifact, run_id)
        if selected is None:
            return EXIT_OK
        archive_url = selected.get("archive_download_url")
        if not isinstance(archive_url, str) or not archive_url:
            raise FetchError(f"artifact {artifact} 缺少 archive_download_url")
        raw = _read(archive_url, token, timeout, "application/octet-stream")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = _extract(archive, destination)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:300]
        print(f"::error::GitHub API {exc.code}（{listing}）：{detail}",
              file=sys.stderr)
        return EXIT_FAILED
    except (urllib.error.URLError, TimeoutError, OSError,
            http.client.HTTPException) as exc:
        print(f"::error::拉取 artifact 失败（{listing}）：{exc}",
              file=sys.stderr)
        return EXIT_FAILED
    except ValueError as exc:
        # json.JSONDecodeError 是 ValueError 子类：响应不是 JSON 也是传输问题。
        print(f"::error::artifact 响应无法解析（{listing}）：{exc}",
              file=sys.stderr)
        return EXIT_FAILED
    except FetchError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return EXIT_FAILED
    except zipfile.BadZipFile as exc:
        print(f"::error::artifact 不是合法 zip：{exc}", file=sys.stderr)
        return EXIT_FAILED
    print(f"artifact {artifact}：已下载 {len(files)} 个文件到 {destination}")
    return EXIT_OK


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return fetch(
        args.run_id, args.repo, args.artifact, args.path,
        token=args.token, api_url=args.api_url, timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
