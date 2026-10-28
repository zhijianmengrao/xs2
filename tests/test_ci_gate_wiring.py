"""CI 接线契约（R46）：失败率闸门真的挂在 CI 上，R2 发布真的有门控。

R45 把「闸门在 CI 上静默空转」做成了可发现的退出码 3（见
``test_provider_failure_profile.py`` 的 R45 段），但闸门本身仍然**没有任何
自动使用者**——HANDOVER_ROUND45 §2.4 原话：「退出码 3 已就位，接下来说无论走
哪条路都只需要加一步即可」。本文件钉住那「一步」，以及 R2 应急通道的门控。

两类断言都是**静态**的（解析 yml，不跑 GitHub）——这正是它们的价值所在：
「CI 忘了调用闸门」「手动 workflow 又能无条件写线上」这两种回归，只能在
代码评审阶段被静态发现，运行时永远看不出来（跑通的 CI 会一直绿）。

## fixture 的边界（重要）

``tests/fixtures/run_samples/`` 是从真实 run 记录裁剪出的**固定**样本：
保留 ``build_run_profile`` 读的字段（node_id / status / attempt_count /
attempt_history 等），删掉小说正文、迭代轨迹、token 明细等内容载荷。
裁剪后生成的画像与原始记录**逐字段相同**（由
``test_run_sample_fixture_matches_real_shape`` 守着）。

因此该 fixture 保护的命题是「闸门与脚本行为不退化」，**不是**「供应商今天
健康」。真实数据的失败率判定需要 run 记录进 CI，尚未接线。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
REPLACE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
DESKTOP_WINDOWS_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "run_samples"


def _load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def _steps(path: Path, job_name: str) -> list[dict]:
    jobs = _load(path).get("jobs")
    assert isinstance(jobs, dict), f"{path.name} 没有 jobs"
    job = jobs.get(job_name)
    assert job is not None, f"{path.name} 缺少 job {job_name}"
    steps = job.get("steps")
    assert isinstance(steps, list)
    return steps


def _gate_step() -> dict:
    """在 CI 里找到那个调用失败率闸门的步骤（按 run 内容定位，不按名字）。"""
    hits = [s for s in _steps(CI_WORKFLOW, "backend")
            if "provider_failure_profile.py" in str(s.get("run", ""))]
    assert len(hits) == 1, (
        "ci.yml 的 backend job 必须且只能有一处调用 provider_failure_profile.py"
        f"（实际 {len(hits)} 处）"
    )
    return hits[0]


def _logical_commands(script: str) -> list[str]:
    """把 run 脚本按「续行合并」切成逻辑命令行（``\\`` 结尾的行属于同一条）。"""
    commands: list[str] = []
    buffer = ""
    for raw in script.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        buffer += line
        commands.append(buffer.strip())
        buffer = ""
    if buffer.strip():
        commands.append(buffer.strip())
    return commands


def _gate_invocations() -> list[str]:
    """CI 里真正调用闸门脚本的逻辑命令（含 shell 函数体里的那一处）。"""
    return [cmd for cmd in _logical_commands(str(_gate_step()["run"]))
            if "provider_failure_profile.py" in cmd]


# ------------------------------------------------- CI 真的会判闸门
def test_ci_backend_job_invokes_the_failure_gate() -> None:
    """闸门必须在 CI 上真的被调用——R45 的退出码 3 在此之前无人使用。

    脚本被包在一个 shell 函数里（``run_gate``），参数由调用点传入，所以
    「每次调用都带全参数」不能靠逐行字符串匹配来断言：函数定义那一行天然
    不含 ``--fail-if-above``。这里分开验两件事——
    1. 函数定义带 ``--require-sample``（它对每次调用都生效）；
    2. 每个审计上下文的调用点都带 ``--fail-if-above``（阈值必须显式给定）。
    """
    invocations = _gate_invocations()
    assert invocations, "ci.yml 里没有任何地方调用闸门脚本"

    definitions = [c for c in invocations if "$@" in c]
    assert definitions, (
        "没找到可复用的闸门调用定义；若改成逐条手写，下面的逐调用断言需要重写"
    )
    for cmd in definitions:
        assert "--require-sample" in cmd, (
            f"闸门调用未带 --require-sample，回到 R45 之前的静默空转（无数据也绿）：{cmd}"
        )

    call_sites = [cmd for cmd in _logical_commands(str(_gate_step()["run"]))
                  if "run_gate " in cmd]
    assert call_sites, "闸门函数定义了却没有调用点"
    for cmd in call_sites:
        assert "--fail-if-above" in cmd, (
            f"闸门调用点没给阈值，等于只打印报表：{cmd}"
        )

    # 三态自检至少需要「带 fixture 的判定」与「空数据的空转」两种上下文
    assert len(call_sites) >= 2, (
        f"只有 {len(call_sites)} 处判定调用，无法同时覆盖有样本与无样本两种上下文"
    )


def test_ci_gate_points_at_the_fixture_data_dir() -> None:
    """闸门必须指向入库 fixture：CI 克隆没有 data/workflows（被 gitignore）。"""
    step = _gate_step()
    env = step.get("env") or {}
    data_dir = str(env.get("DETERMINFLOW_DATA_DIR", ""))
    assert "run_samples" in data_dir, (
        "DETERMINFLOW_DATA_DIR 必须指到 tests/fixtures/run_samples，否则闸门在 CI 上无样本"
    )
    assert str(step["run"]).count("DETERMINFLOW_DATA_DIR") >= 1, (
        "空数据态需要一个显式改指到空目录的调用，才能证明退出码 3 可达"
    )


def test_ci_gate_asserts_all_three_exit_codes() -> None:
    """0/1/3 三态都要被断言：只断言 0 等于又造了一个恒真闸门。"""
    run = str(_gate_step()["run"])
    for wanted in ("0", "1", "3"):
        assert f"expect_exit {wanted} " in run, (
            f"CI 未断言退出码 {wanted}，闸门的一态没被证明可达"
        )


# ------------------------------------------------- fixture 自身可用且真实
def _fixture_runs() -> list[Path]:
    return sorted(FIXTURE_ROOT.glob("workflows/*/runs/run-*.json"))


def test_run_sample_fixture_exists_and_is_small() -> None:
    """fixture 要小到适合入库（真实 run 单个可到 290KB，含小说正文）。"""
    files = _fixture_runs()
    assert files, "fixture 为空，CI 闸门会退化成退出码 3"
    total = sum(p.stat().st_size for p in files)
    assert total < 200_000, f"fixture 总量 {total} 字节，过大会拖慢 clone 且难审阅"


def test_run_sample_fixture_matches_real_shape() -> None:
    """fixture 必须保持 run 记录的真实形状——裁字段可以，改结构不行。

    这里不做「画像等于某个写死数字」的断言：那种断言改一次真实数据就要跟着改，
    会诱使人调数字而不是看语义。改为断言**画像算得出来且自洽**，以及失败样本
    里确实带真实错误文本（否则错误分类那条代码路径在 CI 上是死的）。
    """
    from src.workflow.run_profile import build_run_profile

    attempts = failed = 0
    errored_texts: list[str] = []
    saw_retry_history = False
    for path in _fixture_runs():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert {"run_id", "status", "node_executions"} <= payload.keys(), (
            f"{path.name} 缺少 run 记录的关键字段"
        )
        nodes = payload["node_executions"]
        assert nodes, f"{path.name} 没有 node_executions"
        profile = build_run_profile(
            nodes,
            run_id=str(payload.get("run_id") or path.stem),
            status=str(payload.get("status", "")),
            started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"),
        )
        totals = profile["totals"]
        attempts += totals["attempts"]
        failed += totals["failed"]
        assert totals["attempts"] >= 1, f"{path.name} 画像没有尝试数"
        for stage in profile["stages"]:
            detail = stage["attempts_detail"]
            if len(detail) > 1:
                saw_retry_history = True
            for item in detail:
                if item["error"]:
                    errored_texts.append(item["error"])

    # 闸门判的是「attempts=0 → 是否空转」，所以 fixture 必须真有尝试
    assert attempts > 0
    # 三态自检里的「阈值 1 必须触发」依赖至少一次真实失败
    assert failed > 0, "fixture 没有任何失败尝试，CI 的退出码 1 断言会失效"
    # 错误分类（timeout / http_5xx / stream_stall / connection）需要真实错误文本
    assert errored_texts, "fixture 没有错误文本，错误分类路径在 CI 上形同未测"
    # 逐尝试历史（多 attempt）是画像与「重试语义」的核心输入
    assert saw_retry_history, "fixture 没有多 attempt 节点，重试画像路径在 CI 上形同未测"


def test_run_sample_fixture_has_no_content_payload() -> None:
    """裁剪纪律：正文/轨迹/token 明细这类内容载荷不得进 fixture（含用户小说内容）。"""
    forbidden = {"summary", "input_snapshot", "iteration_history", "outputs",
                 "token_usage_calls", "upstream_summary_snapshot", "output_repair_history"}
    for path in _fixture_runs():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for node in payload["node_executions"]:
            leaked = forbidden & set(node)
            assert not leaked, f"{path.name} 的 {node.get('node_id')} 仍带载荷字段 {leaked}"


# ------------------------------------------------- R2 应急通道门控
def _r2_step(path: Path, job_name: str) -> dict:
    hits = [s for s in _steps(path, job_name)
            if "publish_r2_release.py" in str(s.get("run", ""))]
    assert len(hits) == 1, f"{path.name} 应有且仅有一个 R2 发布步骤（实际 {len(hits)}）"
    return hits[0]


def test_manual_workflow_r2_step_is_gated() -> None:
    """手动触发的 workflow 不得无条件写 R2 —— 它曾被漏掉门控（R45 §8-2）。"""
    step = _r2_step(REPLACE_WORKFLOW, "replace")
    assert step.get("if") == "vars.R2_DISTRIBUTION_ENABLED == 'true'", (
        "replace-desktop-assets 的 R2 步骤缺少与常规发版相同的门控："
        "任何人手动触发都会写线上并切换 stable manifest"
    )


def test_regular_release_r2_step_keeps_its_gate() -> None:
    """常规发版路径的门控不能被反向改掉（两条路径必须一致）。"""
    step = _r2_step(DESKTOP_WINDOWS_WORKFLOW, "release")
    assert step.get("if") == "vars.R2_DISTRIBUTION_ENABLED == 'true'"


def test_both_r2_steps_take_base_url_from_variable() -> None:
    """分发域名取变量：硬编码会让改域名必须改代码，且两处容易漂移。"""
    for path, job in ((REPLACE_WORKFLOW, "replace"), (DESKTOP_WINDOWS_WORKFLOW, "release")):
        step = _r2_step(path, job)
        env = step.get("env") or {}
        base = str(env.get("R2_PUBLIC_BASE_URL", ""))
        assert "vars.R2_PUBLIC_BASE_URL" in base, (
            f"{path.name} 的 R2 步骤应从 vars.R2_PUBLIC_BASE_URL 取分发域名"
        )
        assert "downloads.determinflow.com" in base, (
            f"{path.name} 的域名变量需要保留既有域名作为回落值"
        )
        assert '--public-base-url "$R2_PUBLIC_BASE_URL"' in str(step["run"]), (
            f"{path.name} 必须把变量真的传给脚本，而不是只声明不用"
        )
