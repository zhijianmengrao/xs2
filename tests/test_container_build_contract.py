"""容器构建面契约（R44）：``container-build`` job 与冒烟脚本的静态钉测。

R43 调研发现的最大单项缺口是「镜像从未被构建验证」。R44 用 ``container-build``
job + ``scripts/smoke_container.py`` 补上，本文件钉住三件事：

1. **CI 真的会构建**——``ci.yml`` 里存在一个 ``load: true`` 的 build-push 步骤
   并在其后跑冒烟脚本；只写 ``compose config -q`` 不算覆盖。
2. **冒烟的判据自身可用**——纯函数用真实形状的载荷验证（含反例），避免「脚本
   永远返回空违规」这种假绿。
3. **Dockerfile 与判据不脱钩**——判据里断言的路径/端口/entrypoint 证据必须真的
   来自 Dockerfile 与 entrypoint 脚本，改了一边另一边必须跟着变。

全部为静态/纯函数断言：本机无 docker 也能跑，真实构建验证在 CI 的 job 里。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "smoke_container.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _load_smoke():
    spec = importlib.util.spec_from_file_location("smoke_container", SMOKE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["smoke_container"] = module
    spec.loader.exec_module(module)
    return module


def _jobs() -> dict[str, Any]:
    document = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    jobs = document.get("jobs")
    assert isinstance(jobs, dict)
    return jobs


def _healthy_status(**overrides: Any) -> dict[str, Any]:
    pool = {
        "mode": "process",
        "configured_count": 4,
        "member_count": 4,
        "ready_count": 4,
        "reachable_count": 4,
        "available": True,
        "degraded": False,
        "members": [],
    }
    pool.update(overrides)
    return {
        "workflow_executor": pool,
        "main_session": None,
        "main_sessions": [],
        "total_sessions": 0,
    }


# --------------------------------------------------------------------------- #
# 1. CI 真的构建镜像
# --------------------------------------------------------------------------- #
def test_ci_builds_the_image_and_smokes_it() -> None:
    job = _jobs().get("container-build")
    assert isinstance(job, dict), "ci.yml 缺少 container-build job"
    steps = job.get("steps")
    assert isinstance(steps, list)

    build_index = smoke_index = None
    build_step: dict[str, Any] = {}
    smoke_step: dict[str, Any] = {}
    for index, step in enumerate(steps):
        uses = str(step.get("uses", ""))
        if uses.startswith("docker/build-push-action"):
            build_index = index
            build_step = step
        if "scripts/smoke_container.py" in str(step.get("run", "")):
            smoke_index = index
            smoke_step = step

    assert build_index is not None, "缺少 docker/build-push-action 构建步骤"
    assert smoke_index is not None, "缺少 scripts/smoke_container.py 冒烟步骤"
    assert build_index < smoke_index, "冒烟必须在构建之后"
    # load: true 是「构建结果能被本地 docker 运行」的前提，漏了会去 pull 同名镜像。
    assert build_step["with"]["load"] is True
    assert build_step["with"]["file"] == "./Dockerfile"
    # 冒烟必须消费构建出的同一个 tag，且不重复构建（避免两套判据）。
    assert "--image determinflow-core:ci" in smoke_step["run"]
    assert "--skip-build" in smoke_step["run"]
    assert build_step["with"]["tags"] == "determinflow-core:ci"


def test_container_build_job_keeps_existing_container_config_job() -> None:
    jobs = _jobs()
    # 两个 job 职责不同：语法校验快、构建慢。合并会让「compose 拼错」也要等构建。
    assert isinstance(jobs.get("container-config"), dict)
    config_run = " ".join(
        str(step.get("run", "")) for step in jobs["container-config"]["steps"]
    )
    assert "docker compose config -q" in config_run


def test_container_build_uploads_logs_on_failure() -> None:
    job = _jobs()["container-build"]
    steps = job["steps"]
    uploads = [
        step for step in steps
        if str(step.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert uploads, "失败时必须上传容器日志，否则 CI 只有一行 exit 1"
    assert uploads[0]["if"] == "failure()"
    assert "--logs-dir container-logs" in next(
        str(step.get("run", "")) for step in steps
        if "smoke_container.py" in str(step.get("run", ""))
    )


# --------------------------------------------------------------------------- #
# 2. 判据自身可用（含反例）
# --------------------------------------------------------------------------- #
def test_status_contract_accepts_healthy_payload() -> None:
    smoke = _load_smoke()
    assert smoke.evaluate_status(_healthy_status()) == []


def test_status_contract_rejects_degraded_pool() -> None:
    smoke = _load_smoke()
    violations = smoke.evaluate_status(_healthy_status(ready_count=3))
    assert any("ready_count" in item for item in violations)


def test_status_contract_rejects_inline_mode_and_unavailable_pool() -> None:
    smoke = _load_smoke()
    inline = smoke.evaluate_status(_healthy_status(mode="inline"))
    assert any("mode" in item for item in inline)
    unavailable = smoke.evaluate_status(
        _healthy_status(available=False, reason="pool_unavailable"),
    )
    assert any("available" in item and "pool_unavailable" in item for item in unavailable)


def test_status_contract_reports_missing_sections() -> None:
    smoke = _load_smoke()
    violations = smoke.evaluate_status({"workflow_executor": "not-a-mapping"})
    # 缺字段与类型错误都要报，且不能抛异常。
    assert any("workflow_executor 不是对象" in item for item in violations)
    assert any("total_sessions" in item for item in violations)


def test_index_html_contract_requires_built_assets() -> None:
    smoke = _load_smoke()
    built = (
        '<!doctype html><html><head><title>DeterminFlow</title></head>'
        '<body><div id="root"></div>'
        '<script type="module" src="/assets/index-a1b2c3.js"></script></body></html>'
    )
    assert smoke.evaluate_index_html(built) == []
    assert smoke.find_frontend_asset(built) == "/assets/index-a1b2c3.js"

    dev_html = (
        '<html><head><title>DeterminFlow</title></head><body><div id="root"></div>'
        '<script type="module" src="/src/main.tsx"></script></body></html>'
    )
    violations = smoke.evaluate_index_html(dev_html)
    assert any("main.tsx" in item for item in violations)
    assert any("/assets/" in item for item in violations)


def test_index_html_contract_rejects_missing_mount_point() -> None:
    smoke = _load_smoke()
    violations = smoke.evaluate_index_html("<html><title>DeterminFlow</title></html>")
    assert any("#root" in item for item in violations)


def test_entrypoint_evidence_requires_the_real_log_line() -> None:
    smoke = _load_smoke()
    assert smoke.find_entrypoint_evidence("... Session 启动前裁剪完成: scanned=3\n")
    assert not smoke.find_entrypoint_evidence("Starting gunicorn\n")


def test_layout_contract_is_two_sided() -> None:
    smoke = _load_smoke()
    compliant = {path: expected for path, expected in smoke.IMAGE_LAYOUT_PROBES.items()}
    assert smoke.evaluate_layout(compliant) == []

    leaked = dict(compliant)
    leaked["/app/tests"] = True
    violations = smoke.evaluate_layout(leaked)
    assert len(violations) == 1 and "/app/tests" in violations[0]

    unprobed = dict(compliant)
    del unprobed["/app/web/dist/index.html"]
    assert any("未探测到" in item for item in smoke.evaluate_layout(unprobed))


def test_layout_probe_output_parsing_ignores_noise() -> None:
    smoke = _load_smoke()
    stdout = "\n".join([
        "/app/run.py=1",
        "/app/tests=0",
        "shell: /bin/sh started",
        "/app/web/dist/index.html=1",
        "",
    ])
    observed = smoke.parse_probe_output(stdout)
    assert observed["/app/run.py"] is True
    assert observed["/app/tests"] is False
    # 未出现在输出里的路径不能被当成 False——那会把「探测失败」误判成合规。
    assert "/app/pytest.ini" not in observed
    violations = smoke.evaluate_layout(observed)
    assert any("/app/pytest.ini" in item for item in violations)


def test_credentials_probe_runs_against_image_not_running_container() -> None:
    smoke = _load_smoke()
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    # ModelManager 会在启动时从模板生成 models_config.json，因此布局取证必须在
    # 容器启动/退出之后对镜像本体做一次性 --rm 探测。
    assert "def probe_image_layout(" in source
    assert '"--rm", "--entrypoint", "/bin/sh"' in source
    body = source.split("def smoke(", 1)[1]
    teardown = body.index('"rm", "-f", container')
    assert body.index("probe_image_layout(docker, image)") > teardown
    assert hasattr(smoke, "probe_image_layout")


# --------------------------------------------------------------------------- #
# 3. 判据与 Dockerfile / entrypoint / compose 不脱钩
# --------------------------------------------------------------------------- #
def test_smoke_contract_matches_dockerfile() -> None:
    smoke = _load_smoke()
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (REPO_ROOT / "scripts" / "docker-entrypoint.sh").read_text(
        encoding="utf-8",
    )
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    # 冒烟起的端口 / HEALTHCHECK 路径必须和镜像声明一致。
    # CMD 是 exec 数组形态（"--bind", "0.0.0.0:8020"），按元素比对。
    assert f'"0.0.0.0:{smoke.CONTAINER_PORT}"' in dockerfile
    assert f"http://localhost:{smoke.CONTAINER_PORT}/docs" in dockerfile
    assert f'"{smoke.CONTAINER_PORT}:{smoke.CONTAINER_PORT}"' in compose

    # entrypoint 证据行必须真的由 entrypoint 调用的模块打印，否则断言会空转。
    assert "python -m src.agent.session_retention" in entrypoint
    retention = (REPO_ROOT / "src" / "agent" / "session_retention.py").read_text(
        encoding="utf-8",
    )
    assert smoke.ENTRYPOINT_EVIDENCE in retention

    # 布局探针里「应当存在」的运行期文件必须真被 COPY 进镜像。
    assert "COPY run.py ./" in dockerfile
    assert "COPY src/ ./src/" in dockerfile
    assert "COPY scripts/docker-entrypoint.sh" in dockerfile
    assert "COPY --from=frontend-builder /app/web/dist ./web/dist" in dockerfile


def test_smoke_layout_expects_no_credentials_baked_in() -> None:
    smoke = _load_smoke()
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    # .dockerignore 排除 models_config.json 后，构建上下文里没有凭据；镜像内该路径
    # 只能由运行期从模板生成，所以冒烟断言它「不应预先存在」。
    assert "config/models_config.json" in dockerignore
    assert smoke.IMAGE_LAYOUT_PROBES["/app/config/models_config.json"] is False
    assert smoke.IMAGE_LAYOUT_PROBES["/app/tests"] is False
    assert "tests/" in dockerignore and "pytest.ini" in dockerignore


def test_smoke_env_matches_compose_service_settings() -> None:
    smoke = _load_smoke()
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    env = compose["services"]["app"]["environment"]
    for key, value in smoke.CONTAINER_ENV.items():
        # compose 里的值可能是 "${X:-default}" 形态，取默认值比对。
        raw = str(env[key])
        default = raw.split(":-", 1)[1].rstrip("}") if ":-" in raw else raw
        assert default == value, f"{key} 与 compose 默认值不一致: {default} != {value}"


def test_smoke_script_is_stdlib_only_so_ci_needs_no_pip() -> None:
    smoke = _load_smoke()
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    # CI 的冒烟步骤不装依赖，因此脚本不得 import 第三方包。
    for forbidden in ("import requests", "import httpx", "import docker"):
        assert forbidden not in source
    assert hasattr(smoke, "EXIT_ENV_MISSING")
    # 环境缺失与镜像缺陷必须用不同退出码，否则 runner 缺 docker 会被当产品故障。
    assert smoke.EXIT_ENV_MISSING == 2
