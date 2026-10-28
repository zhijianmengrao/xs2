"""Build the standard container image and verify it actually runs (R44).

背景：``container-config`` job 只跑 ``docker compose config -q``，Dockerfile 的
多阶段构建（前端 ``npm ci`` + ``npm run build``、``pip install -r requirements.lock``、
gunicorn 启动）在 CI 上零覆盖（HANDOVER_ROUND43 §2.2 缺口 1）。本脚本把「构建出来
的镜像是否真的有行为」变成可判定断言：

1. ``/api/system/status`` 返回 200 且 Workflow Executor 池 4/4 ready、未降级；
2. ``/`` 返回内置前端产物（证明 ``COPY --from=frontend-builder`` 真搬来了 dist）；
3. ``/docs`` 可达，且镜像自带的 ``HEALTHCHECK`` 真报 healthy；
4. entrypoint 先跑 session 裁剪再 ``exec``（容器日志里有裁剪完成行）；
5. 镜像不含 ``tests/`` / ``pytest.ini``（``.dockerignore`` 的定位是「运行载体
   而非开发环境」）；
6. 镜像不烘焙凭据：``config/models_config.json`` 不在构建上下文里，运行期由
   ``config/models_config.example.json`` 生成。

判定逻辑与 docker/HTTP 交互分离：纯函数（``evaluate_status`` / ``evaluate_index_html``
/ ``evaluate_layout`` / ``find_entrypoint_evidence``）可在没有 docker 的机器上单测。
docker 不可用时退出码 **2**，与「镜像有问题」的退出码 **1** 分开——否则环境缺失
会被误读成产品缺陷。
"""

from __future__ import annotations

import argparse
import json
import logging
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


LOGGER = logging.getLogger("smoke_container")

CONTAINER_PORT = 8020
EXPECTED_EXECUTOR_COUNT = 4
ENTRYPOINT_EVIDENCE = "Session 启动前裁剪完成"
EXIT_ENV_MISSING = 2

# 与 docker-compose.yml 的 app 服务保持同一组运行期开关，冒烟跑的就是文档里的
# 生产配置，而不是恰好一致的默认值。
CONTAINER_ENV: dict[str, str] = {
    "WEB_HOST": "0.0.0.0",
    "WEB_PORT": str(CONTAINER_PORT),
    "LOG_LEVEL": "INFO",
    "DETERMINFLOW_WORKFLOW_EXECUTOR_MODE": "process",
    "DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT": str(EXPECTED_EXECUTOR_COUNT),
}

# 镜像布局契约：path -> 是否应当存在。两侧都写进来，才不会有人用「镜像变大」
# 的方式把开发面悄悄带进生产镜像。
IMAGE_LAYOUT_PROBES: dict[str, bool] = {
    "/app/run.py": True,
    "/app/src/web_server.py": True,
    "/app/src/core/defaults/skills": True,
    "/app/scripts/docker-entrypoint.sh": True,
    "/app/web/dist/index.html": True,
    "/app/config/models_config.json": False,
    "/app/tests": False,
    "/app/tests/test_plugin_docker_contract.py": False,
    "/app/pytest.ini": False,
}


# --------------------------------------------------------------------------- #
# 纯判定层（无 docker、无网络依赖，直接单测）
# --------------------------------------------------------------------------- #
def evaluate_status(status: Mapping[str, Any]) -> list[str]:
    """Return contract violations for one ``/api/system/status`` payload."""
    violations: list[str] = []
    for key in ("workflow_executor", "main_session", "main_sessions", "total_sessions"):
        if key not in status:
            violations.append(f"status 缺少字段: {key}")
    pool = status.get("workflow_executor")
    if not isinstance(pool, Mapping):
        violations.append(f"workflow_executor 不是对象: {type(pool).__name__}")
        return violations
    expected: dict[str, Any] = {
        "mode": "process",
        "configured_count": EXPECTED_EXECUTOR_COUNT,
        "member_count": EXPECTED_EXECUTOR_COUNT,
        "ready_count": EXPECTED_EXECUTOR_COUNT,
        "reachable_count": EXPECTED_EXECUTOR_COUNT,
    }
    for key, value in expected.items():
        if pool.get(key) != value:
            violations.append(
                f"workflow_executor.{key} 期望 {value!r} 实际 {pool.get(key)!r}"
            )
    if pool.get("available") is not True:
        violations.append(
            f"workflow_executor.available={pool.get('available')!r} "
            f"reason={pool.get('reason')!r}"
        )
    if pool.get("degraded") is not False:
        violations.append(
            f"workflow_executor.degraded={pool.get('degraded')!r} "
            f"reason={pool.get('reason')!r}"
        )
    return violations


def find_frontend_asset(html: str) -> str | None:
    """Return the first ``/assets/...`` reference in index.html, if any."""
    marker = "/assets/"
    index = html.find(marker)
    if index < 0:
        return None
    end = index
    while end < len(html) and html[end] not in "\"' \n>":
        end += 1
    return html[index:end]


def _is_built_asset(asset: str) -> bool:
    return asset.endswith(".js") or ".js?" in asset


def evaluate_index_html(html: str) -> list[str]:
    """Return contract violations for the served frontend entry document."""
    violations: list[str] = []
    if 'id="root"' not in html:
        violations.append("index.html 缺少 #root 挂载点")
    if "<title>" not in html or "DeterminFlow" not in html:
        violations.append("index.html 缺少 DeterminFlow 标题")
    if "/src/main.tsx" in html:
        violations.append("index.html 指向未构建的 /src/main.tsx（构建阶段未执行）")
    asset = find_frontend_asset(html)
    if asset is None:
        violations.append("index.html 未引用 /assets/ 构建产物")
    elif not _is_built_asset(asset):
        violations.append(f"前端入口不是 JS 构建产物: {asset}")
    return violations


def find_entrypoint_evidence(log_text: str) -> bool:
    """Whether the entrypoint's pre-start session prune actually ran."""
    return ENTRYPOINT_EVIDENCE in log_text


def evaluate_layout(exists: Mapping[str, bool]) -> list[str]:
    """Return violations for the in-image layout probes."""
    violations: list[str] = []
    for path, should_exist in IMAGE_LAYOUT_PROBES.items():
        actual = exists.get(path)
        if actual is None:
            violations.append(f"未探测到镜像路径: {path}")
            continue
        if actual is not should_exist:
            verb = "应存在" if should_exist else "不应存在"
            violations.append(f"镜像路径 {path} {verb}，实际 exists={actual}")
    return violations


# --------------------------------------------------------------------------- #
# docker / HTTP 交互层
# --------------------------------------------------------------------------- #
def _run(
    args: Sequence[str],
    *,
    timeout: float = 300.0,
    check: bool = True,
) -> subprocess.CompletedProcess:
    LOGGER.debug("run: %s", " ".join(args))
    completed = subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"命令失败({completed.returncode}): {' '.join(args)}\n"
            f"stdout:\n{completed.stdout[-4000:]}\n"
            f"stderr:\n{completed.stderr[-4000:]}"
        )
    return completed


def docker_available(docker: str) -> bool:
    try:
        completed = _run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            check=False,
            timeout=120.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def build_image(
    docker: str,
    *,
    context: Path,
    image: str,
    dockerfile: Path,
    cache_from: str | None = None,
    cache_to: str | None = None,
) -> None:
    args = [docker, "build", "-t", image, "-f", str(dockerfile)]
    if cache_from:
        args += ["--cache-from", cache_from]
    if cache_to:
        args += ["--cache-to", cache_to]
    args.append(str(context))
    _run(args, timeout=3600.0)
    LOGGER.info("镜像构建完成: %s", image)


def _request(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def wait_for_status(
    base_url: str,
    *,
    deadline_seconds: float = 240.0,
    container_gone: Any = None,
) -> dict[str, Any]:
    """Poll ``/api/system/status`` until the payload satisfies the contract."""
    url = f"{base_url}/api/system/status"
    deadline = time.monotonic() + deadline_seconds
    last_error: Exception | str | None = None
    while time.monotonic() < deadline:
        if callable(container_gone) and container_gone():
            raise RuntimeError(f"容器在就绪前退出（探测地址 {url}）")
        try:
            status_code, body = _request(url, timeout=5.0)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            time.sleep(0.5)
            continue
        if status_code != 200:
            last_error = f"HTTP {status_code}: {body[:500]}"
            time.sleep(0.5)
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            last_error = f"响应不是 JSON: {exc}: {body[:500]}"
            time.sleep(0.5)
            continue
        if not isinstance(payload, dict):
            last_error = f"响应不是 JSON 对象: {type(payload).__name__}"
            time.sleep(0.5)
            continue
        # 200 + JSON 还不够：池成员可能仍在 starting，继续等到契约成立或超时。
        violations = evaluate_status(payload)
        if violations:
            last_error = "; ".join(violations)
            time.sleep(0.5)
            continue
        return payload
    raise RuntimeError(f"等待 {url} 就绪超时: {last_error}")


def _container_running(docker: str, container: str) -> bool:
    completed = _run(
        [docker, "inspect", "-f", "{{.State.Running}}", container],
        check=False,
        timeout=60.0,
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def wait_for_healthy(
    docker: str,
    container: str,
    *,
    deadline_seconds: float = 180.0,
) -> str:
    """Wait until the image's own HEALTHCHECK reports healthy.

    这才是「Dockerfile 的 HEALTHCHECK 指令真的能用」，而不是「我们自己 curl
    /docs 有响应」。
    """
    deadline = time.monotonic() + deadline_seconds
    last = ""
    while time.monotonic() < deadline:
        completed = _run(
            [docker, "inspect", "-f", "{{.State.Health.Status}}", container],
            check=False,
            timeout=60.0,
        )
        last = completed.stdout.strip() or completed.stderr.strip()
        if last == "healthy":
            return last
        if last == "unhealthy":
            raise RuntimeError("镜像 HEALTHCHECK 报 unhealthy")
        if not _container_running(docker, container):
            raise RuntimeError(f"容器在 HEALTHCHECK 达成前退出，最后状态={last!r}")
        time.sleep(2.0)
    raise RuntimeError(f"等待 HEALTHCHECK healthy 超时，最后状态={last!r}")


def parse_probe_output(stdout: str) -> dict[str, bool]:
    """Parse ``<path>=<0|1>`` lines emitted by the in-image layout probe."""
    observed: dict[str, bool] = {}
    for line in stdout.splitlines():
        path, _, flag = line.strip().rpartition("=")
        if path in IMAGE_LAYOUT_PROBES and flag in {"0", "1"}:
            observed[path] = flag == "1"
    return observed


def probe_image_layout(docker: str, image: str) -> dict[str, bool]:
    """Probe the *image as built*, before anything starts inside it.

    必须独立于运行中的容器：``ModelManager`` 在缺失时会把
    ``config/models_config.json`` 从模板生成出来，跑起来之后再探测，这条「镜像不
    烘焙凭据」的断言就必然假红。
    """
    script = "\n".join(
        f'if [ -e "{path}" ]; then echo "{path}=1"; else echo "{path}=0"; fi'
        for path in IMAGE_LAYOUT_PROBES
    )
    completed = _run(
        [
            docker, "run", "--rm", "--entrypoint", "/bin/sh", image,
            "-c", script,
        ],
        timeout=180.0,
    )
    return parse_probe_output(completed.stdout)


def container_logs(docker: str, container: str) -> str:
    completed = _run([docker, "logs", container], check=False, timeout=120.0)
    return f"{completed.stdout}\n{completed.stderr}"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _dump_logs(logs: str, logs_dir: Path | None) -> Path | None:
    if logs_dir is None:
        return None
    logs_dir.mkdir(parents=True, exist_ok=True)
    target = logs_dir / "container-smoke.log"
    target.write_text(logs, encoding="utf-8", errors="replace")
    return target


def smoke(
    docker: str,
    *,
    context: Path,
    image: str,
    dockerfile: Path,
    timeout: float = 240.0,
    keep: bool = False,
    cache_from: str | None = None,
    cache_to: str | None = None,
    skip_build: bool = False,
    logs_dir: Path | None = None,
) -> None:
    if not docker_available(docker):
        LOGGER.error(
            "docker 不可用（runner 未安装或 daemon 未启动）；容器冒烟需要真实 "
            f"docker，退出码 {EXIT_ENV_MISSING} 表示环境问题而非镜像问题"
        )
        raise SystemExit(EXIT_ENV_MISSING)

    if skip_build:
        # CI 用 buildx + GHA 层缓存构建并 load 进 daemon，这里只消费镜像。
        _run([docker, "image", "inspect", image], timeout=120.0)
        LOGGER.info("复用已构建镜像: %s", image)
    else:
        build_image(
            docker,
            context=context,
            image=image,
            dockerfile=dockerfile,
            cache_from=cache_from,
            cache_to=cache_to,
        )

    host_port = _free_port()
    container = f"determinflow-smoke-{int(time.time())}"
    run_args = [
        docker, "run", "-d", "--name", container,
        "-p", f"127.0.0.1:{host_port}:{CONTAINER_PORT}",
    ]
    for key, value in CONTAINER_ENV.items():
        run_args += ["-e", f"{key}={value}"]
    run_args.append(image)
    _run(run_args, timeout=120.0)

    base_url = f"http://127.0.0.1:{host_port}"
    try:
        status = wait_for_status(
            base_url,
            deadline_seconds=timeout,
            container_gone=lambda: not _container_running(docker, container),
        )
        pool = status["workflow_executor"]
        LOGGER.info(
            "status 契约成立: mode=%s ready=%s/%s degraded=%s",
            pool.get("mode"),
            pool.get("ready_count"),
            pool.get("member_count"),
            pool.get("degraded"),
        )

        status_code, html = _request(f"{base_url}/")
        if status_code != 200:
            raise RuntimeError(f"GET / 返回 {status_code}")
        violations = evaluate_index_html(html)
        if violations:
            raise RuntimeError("前端产物契约不成立: " + "; ".join(violations))
        LOGGER.info("内置前端产物可用: %s", find_frontend_asset(html))

        docs_code, _ = _request(f"{base_url}/docs")
        if docs_code != 200:
            raise RuntimeError(f"HEALTHCHECK 路径 /docs 返回 {docs_code}")

        # HEALTHCHECK 是 interval=30s / start-period=15s，最多等约 45s。
        LOGGER.info("镜像 HEALTHCHECK=%s", wait_for_healthy(docker, container))

        logs = container_logs(docker, container)
        if not find_entrypoint_evidence(logs):
            raise RuntimeError(
                "entrypoint 未留下 session 裁剪日志（先裁剪再 exec 的契约失效）"
            )
        LOGGER.info("entrypoint 先裁剪再 exec 已验证")
    except BaseException as exc:
        logs = container_logs(docker, container)
        dumped = _dump_logs(logs, logs_dir)
        if dumped is not None:
            LOGGER.error("容器日志已写入: %s", dumped)
        if isinstance(exc, (SystemExit, KeyboardInterrupt)):
            raise
        raise RuntimeError(f"容器冒烟失败: {exc}\n--- container logs ---\n{logs[-8000:]}")
    finally:
        if keep:
            LOGGER.warning("按 --keep 保留容器: %s", container)
        else:
            _run([docker, "rm", "-f", container], check=False, timeout=120.0)

    # 镜像布局必须在运行痕迹出现之前探测（见 probe_image_layout 的说明），
    # 因此放在容器删除之后、以一次性 --rm 容器对镜像本体取证。
    violations = evaluate_layout(probe_image_layout(docker, image))
    if violations:
        raise RuntimeError("镜像布局契约不成立: " + "; ".join(violations))
    LOGGER.info("镜像布局契约成立（不含 tests 与预先烘焙的凭据）")
    LOGGER.info("容器镜像冒烟全部通过: %s", image)


def main(argv: Iterable[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="determinflow-core:smoke")
    parser.add_argument("--context", type=Path, default=repo_root)
    parser.add_argument("--dockerfile", type=Path, default=repo_root / "Dockerfile")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--cache-from")
    parser.add_argument("--cache-to")
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="镜像已构建并 load 进 daemon（CI 用 buildx 缓存构建时使用）",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="失败时把容器日志写到该目录（CI 用 upload-artifact 收集）",
    )
    options = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        smoke(
            options.docker,
            context=options.context.resolve(),
            image=options.image,
            dockerfile=options.dockerfile.resolve(),
            timeout=options.timeout,
            keep=options.keep,
            cache_from=options.cache_from,
            cache_to=options.cache_to,
            skip_build=options.skip_build,
            logs_dir=options.logs_dir,
        )
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001 - CI 需要完整失败原因
        LOGGER.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
