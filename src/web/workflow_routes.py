"""
工作流 REST API 路由

提供工作流定义 CRUD、运行控制、状态查询和历史记录接口。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..config import SESSIONS_DIR, WORKFLOWS_DIR
from ..workflow.definition import WorkflowDef
from ..workflow.task_overrides import TASK_OVERRIDE_ERROR_CODES
from .workflow_access import (
    _ensure_http_mutation_allowed,
    _ensure_workflow_writable,
    _get_manager,
)
from .workflow_request_models import (
    PreStartRequest,
    TaskCreateRequest,
    WorkflowCreateRequest,
    WorkflowRunRequest,
    WorkflowUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _existing_workspace_root(mgr, workflow_id: str, workspace: str | None) -> Path:
    """读端点专用解析：只解析不创建，工作区不存在时诚实 404。

    与 R38 B26 的 console 面 `_console_existing_root` 同语义；修复前 GET
    workspace-files 系列对幻影工作区「查询即建目录」（如资料蒸馏页每次
    打开都会留下 job-* 空目录）。
    """
    root = mgr._ws_manager.resolve_workflow_workspace(
        workflow_id, override=workspace, create=False)
    if not root.exists():
        raise HTTPException(status_code=404, detail="作品工作区不存在")
    return root


@router.get("/workspace-files")
async def list_workspace_files(
    request: Request,
    workflow_id: str = Query(..., min_length=1),
    workspace: str | None = Query(default=None),
    prefix: str = Query(default=""),
    limit: int = Query(default=500, ge=1, le=2000),
):
    """列出小说工作区中的可读文件，供作品控制台恢复历史内容。"""
    mgr = _get_manager(request)
    root = _existing_workspace_root(mgr, workflow_id, workspace)
    from src.core.workspace_guard import WorkspaceGuard

    guard = WorkspaceGuard()
    checked = guard.validate_path(str(root), prefix or ".")
    if not checked.allowed:
        raise HTTPException(status_code=403, detail=checked.reason)
    base = guard.get_effective_path(str(root), prefix or ".")
    if base is None or not base.exists():
        return {"workspace": str(root), "files": []}
    files = []
    for target in sorted(base.rglob("*"), key=lambda item: str(item).lower()):
        if not target.is_file():
            continue
        relative = target.relative_to(root).as_posix()
        if relative.startswith("cache/"):
            continue
        try:
            stat = target.stat()
        except OSError:
            continue
        character_count = None
        if re.fullmatch(r"story/\d{4}/chapter\.md", relative) and stat.st_size <= 2_000_000:
            try:
                character_count = len(re.sub(r"\s", "", target.read_text(encoding="utf-8-sig")))
            except (OSError, UnicodeError):
                pass
        files.append({
            "path": relative,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "character_count": character_count,
        })
        if len(files) >= limit:
            break
    return {"workspace": str(root), "files": files}


@router.get("/workspace-files/content")
async def read_workspace_file(
    request: Request,
    workflow_id: str = Query(..., min_length=1),
    workspace: str | None = Query(default=None),
    path: str = Query(..., min_length=1),
):
    """读取工作区内的 UTF-8 文本，供作品历史和审核页面展示。"""
    mgr = _get_manager(request)
    root = _existing_workspace_root(mgr, workflow_id, workspace).resolve()
    from src.core.workspace_guard import WorkspaceGuard

    guard = WorkspaceGuard()
    checked = guard.validate_path(str(root), path)
    if not checked.allowed:
        raise HTTPException(status_code=403, detail=checked.reason)
    target = guard.get_effective_path(str(root), path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="工作区文件不存在")
    if target.stat().st_size > 2_000_000:
        raise HTTPException(status_code=413, detail="预览文件超过 2 MB")
    try:
        content = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="文件不是 UTF-8 文本") from exc
    return {
        "workspace": str(root),
        "path": path,
        "content": content,
        "size_bytes": target.stat().st_size,
    }


# 变量 key 不允许以 _ 开头（保留给 _system.xxx 系统变量）
_VAR_KEY_RE = re.compile(r"^[a-zA-Z0-9][\w\-]*$")


def _raise_runtime_draining(result: dict) -> None:
    if result.get("error") != "runtime_draining":
        return
    raise HTTPException(
        status_code=503,
        detail={"code": "runtime_draining", "message": result.get("message")},
        headers={"Retry-After": str(result["retry_after_seconds"])},
    )


def _raise_task_override_error(result: dict) -> None:
    error = result.get("error")
    if error not in TASK_OVERRIDE_ERROR_CODES:
        return
    raise HTTPException(
        status_code=422,
        detail={"code": error, "message": result.get("message")},
    )


def _raise_task_freeze_error(result: dict) -> None:
    # 2026-10-26 B19：任务冻结失败（如定义引用不存在的 Script Library 脚本）
    # 此前被误报为 404「工作流不存在」；改为 409 透出真实原因。
    if result.get("error") != "task_freeze_failed":
        return
    raise HTTPException(
        status_code=409,
        detail={"code": "task_freeze_failed", "message": result.get("message")},
    )


def _raise_unknown_parameter_error(result: dict) -> None:
    # 2026-10-26 B21：parameter_values 用错键（传变量显示名而非 key）时，
    # manager 曾返回 None → 被报成 404「工作流不存在」。改为 422 并列出未知键。
    if result.get("error") != "unknown_parameters":
        return
    raise HTTPException(
        status_code=422,
        detail={"code": "unknown_parameters", "message": result.get("message")},
    )


def _load_session_file(session_id: str) -> dict | None:
    """从持久化文件读取 session，避免跨进程时只能看到当前内存态。"""
    if not session_id:
        return None
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", session_id)
    if not safe_id:
        return None
    path = SESSIONS_DIR / f"{safe_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("读取 session 文件失败: session_id=%s path=%s", session_id, path, exc_info=True)
        return None


def _last_assistant_message(record: list[dict]) -> str:
    for msg in reversed(record or []):
        if msg.get("type") == "assistant" and msg.get("content"):
            return str(msg.get("content", ""))[:200]
    return ""


def _session_summary_from_data(session_id: str, data: dict | None) -> dict | None:
    if not data:
        return None
    record = data.get("record") or []
    msg_count = len([m for m in record if m.get("type") not in ("system_prompt", "compression_divider")])
    summary = {
        "session_id": session_id,
        "type": data.get("session_type", ""),
        "parent_id": data.get("parent_id"),
        "status": data.get("status", ""),
        "task": str(data.get("task_description", ""))[:100],
        "message_count": msg_count,
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "last_message": _last_assistant_message(record),
        "agent_type": data.get("agent_type", ""),
        "workspace_path": data.get("workspace_path"),
        "workflow_id": data.get("workflow_id", ""),
        "task_id": data.get("task_id", ""),
        "node_id": data.get("node_id", ""),
    }
    return {k: v for k, v in summary.items() if v not in (None, "")}


def _node_meta_from_definition(definition: dict) -> dict[str, dict]:
    meta: dict[str, dict] = {}
    for node in definition.get("nodes", []) or []:
        node_id = node.get("id")
        if not node_id:
            continue
        meta[node_id] = {
            "node_id": node_id,
            "label": node.get("label", node_id),
            "node_type": node.get("node_type", ""),
            "agent_type": node.get("agent_type", ""),
        }
    return meta


def _validate_variable_keys(variables: list[dict]) -> None:
    """校验变量 key：不允许以 _ 开头（保留给 _system.xxx 系统变量）。"""
    for v in variables:
        key = v.get("key", "")
        if key and key.startswith("_"):
            raise HTTPException(
                status_code=400,
                detail=f"变量 key 不能以下划线开头（保留给系统变量）: {key}",
            )


# ============================================================
# 工作流定义 API
# ============================================================

@router.get("")
async def list_workflows(request: Request,
                         with_health: bool = False,
                         health_limit: int = 0):
    """列出所有工作流。

    Query params:
        with_health: 是否给每个 workflow 附 ``health`` 块（R54，默认关）
        health_limit: 每个 workflow 回溯多少个 run（0 = 全部；正数取最近 N 个）

    为什么 ``with_health`` 默认关：默认路径（资源选择器、侧栏）只要定义概要，
    这个开关要逐 workflow 扫 ``runs/`` 并解析 JSON，是列表端点里最重的一段
    与 ``list_tasks`` 的 ``with_trend`` 取舍完全相同。

    ``health_limit`` 默认 0（全部）而 ``baseline_limit`` 默认 5，是因为两者问的
    问题不同：``baseline_limit`` 是「够不够判趋势」，样本少了趋势判不出来；
    这里问「这个 workflow 最近是不是一直在挂」，样本越少越可能误判成「没有
    连续失败」——把窗口裁短正好会把全失败序列的头部截掉，反而不安全。所以
    默认看全量，需要限流时由调用方显式给 N。
    """
    mgr = _get_manager(request)
    workflows = mgr.list_workflows()
    if with_health and isinstance(workflows, list):
        limit_n = max(0, int(health_limit))
        for summary in workflows:
            if not isinstance(summary, dict):
                continue
            workflow_id = str(summary.get("workflow_id") or "")
            if not workflow_id:
                continue
            summary["health"] = _collect_workflow_health(workflow_id, limit_n)
    return workflows


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, request: Request):
    """获取单个工作流定义和状态。"""
    mgr = _get_manager(request)
    result = mgr.get_workflow(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return result


@router.post("")
async def create_workflow(request: Request, body: WorkflowCreateRequest):
    """创建新工作流。"""
    mgr = _get_manager(request)
    requested_id = str(getattr(body, "workflow_id", "") or "")
    if requested_id:
        _ensure_http_mutation_allowed(request, requested_id)
    _validate_variable_keys(body.variables)
    data = body.model_dump()
    validation = mgr.validate_workflow(data)
    if not validation.get("valid"):
        raise HTTPException(
            status_code=400,
            detail="\n".join(validation.get("errors", ["校验失败"])),
        )
    result = mgr.create_workflow(data)
    if not result.get("definition"):
        raise HTTPException(status_code=409, detail=result)
    return result


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, request: Request, body: WorkflowUpdateRequest):
    """更新工作流定义。保存前自动校验连线完整性。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)

    _validate_variable_keys(body.variables)

    data = body.model_dump()

    # 校验
    result = mgr.validate_workflow(data)
    if not result.get("valid"):
        raise HTTPException(status_code=400, detail="\n".join(result.get("errors", ["校验失败"])))

    result2 = mgr.update_workflow(workflow_id, data)
    if result2 is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return result2


@router.post("/validate")
async def validate_workflow(request: Request, body: WorkflowUpdateRequest):
    """校验工作流定义完整性（不保存）。返回 valid 和 errors 列表。"""
    mgr = _get_manager(request)
    _validate_variable_keys(body.variables)
    return mgr.validate_workflow(body.model_dump())


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request):
    """删除工作流。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    success = await mgr.delete_workflow(workflow_id)
    if not success:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return {"success": True}


# ============================================================
# 运行控制 API
# ============================================================

@router.post("/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: Request, body: WorkflowRunRequest = WorkflowRunRequest()):
    """启动工作流运行。可指定 from_node_id 从某节点重新开始（回滚）。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = await mgr.run_workflow(workflow_id, from_node_id=body.from_node_id)
    if not result.get("success"):
        _raise_runtime_draining(result)
        raise HTTPException(status_code=400, detail=result.get("message", "启动失败"))
    return result


@router.post("/{workflow_id}/stop")
async def stop_workflow(workflow_id: str, request: Request):
    """停止正在运行的工作流。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    return await mgr.stop_workflow(workflow_id)


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: str, request: Request):
    """查询工作流当前运行状态。"""
    mgr = _get_manager(request)
    result = mgr.get_workflow_status(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="工作流状态不存在")
    return result


@router.get("/{workflow_id}/runs")
async def get_run_history(workflow_id: str, request: Request, limit: int = 20):
    """获取工作流运行历史记录。"""
    mgr = _get_manager(request)
    return mgr.get_run_history(workflow_id, limit=limit)


# ============================================================
# 任务管理 API（编辑与运行分离架构）
# ============================================================

@router.post("/{workflow_id}/tasks")
async def create_task(workflow_id: str, request: Request,
                      body: TaskCreateRequest = TaskCreateRequest()):
    """创建新任务（不启动）。接受 parameter_values 用于变量填参。
    返回 task_id，前端随后调用 run 接口启动。
    如果 workflow 没有定义变量，则 parameter_values 可留空。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = mgr.create_task(workflow_id, from_node_id=body.from_node_id,
                              parameter_values=body.parameter_values,
                              node_model_overrides=body.node_model_overrides,
                              node_model_params_overrides=body.node_model_params_overrides,
                              disabled_node_ids=body.disabled_node_ids,
                              scheme_id=body.scheme_id,
                              selected_node_ids=body.selected_node_ids,
                              workspace_override=body.workspace_override)
    if result is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    _raise_runtime_draining(result)
    _raise_task_override_error(result)
    _raise_task_freeze_error(result)
    _raise_unknown_parameter_error(result)
    return result


@router.post("/{workflow_id}/tasks/{task_id}/run")
async def run_task(workflow_id: str, task_id: str, request: Request,
                   body: WorkflowRunRequest = WorkflowRunRequest()):
    """启动一个已创建的任务。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = await mgr.run_task(workflow_id, task_id, from_node_id=body.from_node_id)
    if not result.get("success"):
        _raise_runtime_draining(result)
        status_code = 409 if result.get("error") == "task_state_conflict" else 400
        raise HTTPException(
            status_code=status_code,
            detail=result.get("message", "启动失败"),
        )
    return result


@router.get("/{workflow_id}/variables")
async def get_workflow_variables(workflow_id: str, request: Request):
    """获取工作流定义的变量列表（用于任务填参表单）。"""
    mgr = _get_manager(request)
    wf_data = mgr.get_workflow(workflow_id)
    if wf_data is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf_data["definition"].get("variables", [])


@router.get("/{workflow_id}/variable-references")
async def get_variable_references(workflow_id: str, request: Request):
    """获取工作流的变量→节点引用映射（用于参数过滤和引用计数显示）。"""
    mgr = _get_manager(request)
    wf_data = mgr.get_workflow(workflow_id)
    if wf_data is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    definition = WorkflowDef.from_dict(wf_data["definition"])
    return definition.get_variable_references()


@router.get("/{workflow_id}/tasks")
async def list_tasks(workflow_id: str, request: Request,
                     limit: int = 50,
                     status: str = "",
                     search: str = "",
                     sort_by: str = "created_at",
                     sort_order: str = "desc",
                     page: int = 1,
                     page_size: int = 20,
                     with_trend: bool = False,
                     baseline_limit: int = 5):
    """列出工作流的所有任务（支持筛选/排序/搜索/分页）。

    Query params:
        status: 状态过滤（空字符串表示全部）
        search: 搜索关键词（匹配名称和 task_id）
        sort_by: 排序字段（created_at/started_at/completed_at/status/name）
        sort_order: asc 或 desc
        page: 页码（从 1 开始）
        page_size: 每页条数（新参数，替代旧的 limit）
        with_trend: 是否给每条任务附 ``trend`` 块（R51，默认关）
        baseline_limit: 趋势要回溯多少个历史 run（默认 5，上限 20）

    为什么 ``with_trend`` 默认关：要算趋势就必须扫 workflow 的 ``runs/``
    目录并解析 run JSON，是列表端点里最重的一段 I/O。列表本身的用途（找任务、
    点进去）不需要它，默认关上让常见路径保持轻量；要标注「连续退步」的视图
    才显式打开。
    """
    mgr = _get_manager(request)
    result = mgr.list_tasks(
        workflow_id,
        limit=limit,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    if with_trend and isinstance(result, dict) and result.get("tasks"):
        limit_n = max(1, min(int(baseline_limit), 20))
        trends = _collect_workflow_trends(
            workflow_id,
            [{"task_id": t.get("task_id"), "run_id": t.get("run_id")}
             for t in result["tasks"]],
            limit_n,
        )
        for task in result["tasks"]:
            task["trend"] = trends.get(str(task.get("task_id") or ""))
    return result


@router.get("/{workflow_id}/tasks/{task_id}")
async def get_task(workflow_id: str, task_id: str, request: Request):
    """获取任务运行状态 + 工作流定义。"""
    mgr = _get_manager(request)
    result = mgr.get_task_with_definition(workflow_id, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return result


@router.get("/{workflow_id}/tasks/{task_id}/workspace-file")
async def get_task_workspace_file(
    workflow_id: str,
    task_id: str,
    request: Request,
    path: str,
):
    """读取任务工作区内的 UTF-8 文本，供本地工作台预览产物。"""
    mgr = _get_manager(request)
    task = mgr._load_task(workflow_id, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    workspace = _existing_workspace_root(
        mgr, workflow_id, task.workspace_override).resolve()
    from src.core.workspace_guard import WorkspaceGuard

    guard = WorkspaceGuard()
    checked = guard.validate_path(str(workspace), path)
    if not checked.allowed:
        raise HTTPException(status_code=403, detail=checked.reason)
    target = guard.get_effective_path(str(workspace), path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="工作区文件不存在")
    if target.stat().st_size > 2_000_000:
        raise HTTPException(status_code=413, detail="预览文件超过 2 MB")
    try:
        content = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="文件不是 UTF-8 文本") from exc
    return {
        "workflow_id": workflow_id,
        "task_id": task_id,
        "path": path,
        "content": content,
        "size_bytes": target.stat().st_size,
    }


@router.get("/{workflow_id}/tasks/{task_id}/sessions")
async def get_task_sessions(workflow_id: str, task_id: str, request: Request):
    """获取工作流任务关联的持久化 session 列表。

    与 `/api/sessions` 不同，本接口不依赖当前进程内存态，优先从任务文件
    的 `main_session_id` / `node_states[*].session_id` 反查 `data/sessions/*.json`。
    这使任务历史页即使在多进程或重启后，也能稳定跳转到对应 workflow 会话。
    """
    task_file = WORKFLOWS_DIR / workflow_id / "tasks" / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        raise HTTPException(status_code=500, detail="任务文件损坏")

    definition = task_data.get("snapshot_definition") or {}
    if not definition:
        def_file = WORKFLOWS_DIR / workflow_id / "definition.json"
        if def_file.exists():
            try:
                definition = json.loads(def_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                definition = {}
    node_meta = _node_meta_from_definition(definition)

    node_sessions: list[dict] = []
    parent_ids: set[str] = set()
    for node_id, state in (task_data.get("node_states") or {}).items():
        session_id = state.get("session_id") or ""
        meta = node_meta.get(node_id, {"node_id": node_id, "label": node_id})
        entry = {
            **meta,
            "status": state.get("status", ""),
            "started_at": state.get("started_at"),
            "completed_at": state.get("completed_at"),
            "summary": str(state.get("summary", ""))[:500],
            "error": str(state.get("error", ""))[:500],
            "session_id": session_id,
            "session_found": False,
        }
        if session_id:
            session_data = _load_session_file(session_id)
            session_summary = _session_summary_from_data(session_id, session_data)
            if session_summary:
                entry["session_found"] = True
                entry["session"] = session_summary
                parent_id = session_summary.get("parent_id")
                if parent_id:
                    parent_ids.add(parent_id)
        node_sessions.append({k: v for k, v in entry.items() if v not in (None, "")})

    main_session_id = task_data.get("main_session_id") or ""
    if not main_session_id and parent_ids:
        # API 直接启动的任务历史上未把 workflow-main session_id 写回 task；
        # 用节点 sub session 的 parent_id 反推。
        main_session_id = sorted(parent_ids)[0]

    main_session = None
    if main_session_id:
        main_session = _session_summary_from_data(main_session_id, _load_session_file(main_session_id))

    return {
        "workflow_id": workflow_id,
        "task_id": task_id,
        "task_name": task_data.get("name", ""),
        "status": task_data.get("status", ""),
        "main_session_id": main_session_id or None,
        "main_session_found": bool(main_session),
        "main_session": main_session,
        "node_sessions": node_sessions,
        "node_session_count": len([n for n in node_sessions if n.get("session_id")]),
    }


@router.get("/{workflow_id}/tasks/{task_id}/token-usage")
async def get_task_token_usage(workflow_id: str, task_id: str, request: Request):
    """获取任务的 Token 消耗详情。

    从任务持久化 JSON 中读取各节点的 token_usage 数据，
    按节点、模型和 agent 类型分别汇总返回。

    Returns:
        {
            "workflow_id": str,
            "task_id": str,
            "task_name": str,
            "status": str,
            "calls": [{timestamp, provider, model, token counts, cost, ...}],
            "rejections": [{error_codes, reason, retry_usage, retry_cost, ...}],
            "nodes": [{node_id, agent_type, status, token_usage, calls, cost}],
            "by_model": {model_id: {token counts, cost}},
            "by_agent_type": {agent_type: {token counts, cost}},
            "total": {token counts, cost},
            "cost_status": "priced | partially_priced | unpriced | no_usage",
            "currency": str,
            "pricing_snapshot": {...}
        }
    """
    from src.config import WORKFLOWS_DIR
    from src.workflow.token_usage import aggregate_token_usage
    import json

    task_file = WORKFLOWS_DIR / workflow_id / "tasks" / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        raise HTTPException(status_code=500, detail="任务文件损坏")

    # 优先使用任务创建时的定义快照，确保工作流后续编辑不会改变历史统计。
    def_file = WORKFLOWS_DIR / workflow_id / "definition.json"
    node_agent_map: dict[str, str] = {}
    snapshot_definition = task_data.get("snapshot_definition")
    if isinstance(snapshot_definition, dict):
        for node in snapshot_definition.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                node_agent_map[node_id] = node.get("agent_type", "unknown")
    elif def_file.exists():
        try:
            def_data = json.loads(def_file.read_text(encoding="utf-8"))
            for node in def_data.get("nodes", []):
                node_id = node.get("id", "")
                if node_id:
                    node_agent_map[node_id] = node.get("agent_type", "unknown")
        except (json.JSONDecodeError, IOError):
            pass

    task_name = task_data.get("task_name", task_data.get("name", ""))
    task_status = task_data.get("status", "unknown")
    node_states_raw = task_data.get("node_states", {})

    aggregation = aggregate_token_usage(node_states_raw, node_agent_map)

    return {
        "workflow_id": workflow_id,
        "task_id": task_id,
        "task_name": task_name,
        "status": task_status,
        **aggregation,
    }


# run_id 是查询串入参（R41 扩展），进路径拼接前须过单规则校验：与
# _SCRIPT_NAME_RE 同款字符集（无点无斜杠），路径穿越无从构造。
_RUN_ID_RE = re.compile(r"^[\w][\w\-]*$")


@router.get("/{workflow_id}/tasks/{task_id}/run-profile")
async def get_task_run_profile(workflow_id: str, task_id: str, request: Request,
                               run_id: str | None = None,
                               compare: bool = False,
                               baseline_limit: int = 0):
    """获取任务一次运行的每阶段尝试/失败画像（R38 §7.4 落地，R40）。

    缺省取任务最新一次运行；``?run_id=run-xxx``（R41）查询任意历史 run
    （前端画像可视化按 run 切换）。``?compare=true``（R43）额外返回
    ``comparison`` 块：本次 run 与「上一次 run」的逐阶段失败率/尝试数差值。
    ``?baseline_limit=N``（R50）额外返回 ``baseline`` 块：本次 run 与最近 N 次
    历史 run 的时间序列与趋势判定（``regressing``/``improving``/``stable``/
    ``insufficient``）。两者独立：``compare`` 判「这一步退步了吗」，
    ``baseline_limit`` 判「是否在连续变坏」。
    与 token-usage 同款只读文件模式：任务 JSON → runs/{run_id}.json →
    run_profile.build_run_profile 纯函数聚合。不建目录、不写状态——本端点是
    GET，读端点「查询即建目录」属 B26/B28 同族缺陷（有静态钉测守卫）。非法
    run_id 拒 400，run 文件缺失拒 404（任务不存在 / 尚无运行记录语义不变）。

    Returns:
        {run_id, workflow_id, status, started_at, completed_at, wall_seconds,
         totals: {stages, attempts, completed, failed, failure_rate,
                  stages_with_retry, error_classes},
         stages: [{node_id, attempts, completed, failed, failure_rate,
                   automatic_retry_count, output_repair_count,
                   first_started_at, duration_seconds, error_classes,
                   attempts_detail: [{attempt_number, trigger, status,
                                      error, error_class, duration_seconds}]}],
         comparison: null | {previous_run_id, previous_status, ...,
                             totals: {...delta 字段...},
                             stages: [{node_id, ..., delta_failure_rate,
                                       comparable}]}}（仅 ``?compare=true``）
         baseline: null | {points: [{run_id, status, attempts, failed,
                                     failure_rate, is_current}],
                           deltas: [{from_run_id, to_run_id,
                                     failure_rate_from, failure_rate_to,
                                     delta_failure_rate, comparable}],
                           trend, consecutive_required,
                           baseline_run_ids}（仅 ``?baseline_limit=N>0``）
    """
    task_file = WORKFLOWS_DIR / workflow_id / "tasks" / f"{task_id}.json"
    if not task_file.exists():
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        task_data = json.loads(task_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        raise HTTPException(status_code=500, detail="任务文件损坏")

    if run_id:
        if not _RUN_ID_RE.match(run_id):
            raise HTTPException(status_code=400, detail="run_id 包含非法字符")
        target_run_id = run_id
    else:
        target_run_id = task_data.get("run_id")
        if not target_run_id:
            raise HTTPException(status_code=404, detail="任务尚无运行记录")
    run_file = WORKFLOWS_DIR / workflow_id / "runs" / f"{target_run_id}.json"
    if not run_file.is_file():
        raise HTTPException(status_code=404, detail="运行记录不存在")
    try:
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        raise HTTPException(status_code=500, detail="运行记录损坏")

    from src.workflow.run_profile import build_run_profile

    profile = build_run_profile(
        run_data.get("node_executions", []),
        run_id=str(target_run_id),
        workflow_id=workflow_id,
        status=str(run_data.get("status", "")),
        started_at=run_data.get("started_at"),
        completed_at=run_data.get("completed_at"),
    )
    if not compare and baseline_limit <= 0:
        return profile

    from src.workflow.run_profile import (
        compare_run_baseline,
        compare_run_profiles,
        pick_previous_run,
        pick_recent_runs,
    )

    runs_dir = WORKFLOWS_DIR / workflow_id / "runs"
    current_meta = {
        "run_id": str(target_run_id),
        "started_at": run_data.get("started_at"),
        "mtime": run_file.stat().st_mtime,
    }
    metas = None
    if compare:
        metas = _iter_run_metadata(runs_dir)
        previous_meta = pick_previous_run(current_meta, metas)
        previous_profile = _load_run_profile(runs_dir, previous_meta, workflow_id)
        profile["comparison"] = (
            compare_run_profiles(profile, previous_profile)
            if previous_profile is not None else None)

    if baseline_limit > 0:
        # 上限 20：与 ``--limit`` 一类「最近 N 次」口径一致，也避免一次请求
        # 扫遍整个 runs/ 目录（跑得久的工作流可能有上百条记录）。
        limit = min(baseline_limit, 20)
        if metas is None:
            metas = _iter_run_metadata(runs_dir)
        history: list[dict] = []
        for meta in pick_recent_runs(current_meta, metas, limit):
            loaded = _load_run_profile(runs_dir, meta, workflow_id)
            if loaded is not None:
                history.append(loaded)
        profile["baseline"] = compare_run_baseline(profile, history)
    return profile


def _iter_run_metadata(runs_dir: Path) -> list[dict]:
    """扫 runs/ 目录的 run 元数据（只读 stat/JSON，不建目录不写文件）。

    坏 JSON 与读失败一律跳过：对比对象的选择不该被一条损坏记录带歪，
    这与挖矿脚本「坏记录不占配额」同一取舍。
    """
    if not runs_dir.is_dir():
        return []
    metas: list[dict] = []
    for run_file in runs_dir.glob("run-*.json"):
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            mtime = run_file.stat().st_mtime
        except (OSError, ValueError):
            continue
        metas.append({
            "run_id": str(data.get("run_id") or run_file.stem),
            "started_at": data.get("started_at"),
            "mtime": mtime,
            # status 供 workflow 级健康度聚合用（R54）。同一次 JSON 解析顺手取，
            # 不额外读一遍文件。
            "status": str(data.get("status", "")),
        })
    return metas


def _load_run_profile(runs_dir: Path, meta: dict | None,
                      workflow_id: str) -> dict | None:
    """按元数据载入该 run 的画像；meta 为空或文件损坏时返回 None（诚实无对比）。"""
    if not meta:
        return None
    from src.workflow.run_profile import build_run_profile

    run_file = runs_dir / f"{meta['run_id']}.json"
    try:
        run_data = json.loads(run_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return build_run_profile(
        run_data.get("node_executions", []),
        run_id=str(meta["run_id"]),
        workflow_id=workflow_id,
        status=str(run_data.get("status", "")),
        started_at=run_data.get("started_at"),
        completed_at=run_data.get("completed_at"),
    )


def _collect_workflow_health(workflow_id: str, limit: int = 0) -> dict:
    """单个 workflow 的运行健康度（R54）：最近是不是一直在挂。

    与 ``_collect_workflow_trends`` 的分工：
    - ``trends`` 是**任务级**，按 ``task_id`` 返回，回答「这条任务在退步吗」；
    - ``health`` 是**workflow 级**，回答「这个 workflow 整体最近全挂了吗」。

    后者不能由前者合并出来：任务级只覆盖当前页的任务（``page_size`` 默认 20），
    跨页任务与被删任务引用的 run 都不在其中，而「三个任务各失败一次」在任务级
    看着是三条 1 连败、在 workflow 级才是连续 3 次全失败。

    ``limit <= 0`` 表示不裁剪（全部 run）。裁剪取最近 N 个**之后**再数连续失败，
    这与 ``pick_recent_runs`` 的「取尾部 N 个」同向：保留最新的一段，正是判
    「最近是否全挂」需要的那一端。

    扫不到 run 目录 / 无 run 记录时返回 ``run_count=0`` 且 ``all_failed=False``
    ——没有证据不等于全失败，这与 ``failure_streak`` 的诚实缺席同一条纪律。
    """
    from src.workflow.run_profile import workflow_health

    runs_dir = WORKFLOWS_DIR / workflow_id / "runs"
    metas = _iter_run_metadata(runs_dir)
    if limit and limit > 0:
        # 与 run_profile 的排序键一致：先按时间升序，再取尾部 N 个。
        from src.workflow.run_profile import _order_key

        metas = sorted(
            metas,
            key=lambda m: (_order_key(m.get("started_at"), m.get("mtime", 0.0)),
                           str(m.get("run_id", ""))),
        )[-limit:]
    return workflow_health(metas)


def _collect_workflow_trends(workflow_id: str, entries: list[dict],
                             limit: int) -> dict[str, dict]:
    """给同一 workflow 的一批任务各算 trend（R51 批量，非逐任务扫目录）。

    ``entries`` 是 ``[{task_id, run_id}]``。返回 ``{task_id: trend_block}``，
    其中 trend_block 只保留趋势判定需要的字段——列表视图不需要每阶段明细，
    把完整 baseline 塞进列表响应会让一页 20 条变成几十 MB。

    为什么按 workflow 分组：``runs/`` 目录的扫描与 JSON 解析是这里的主开销。
    逐任务扫一遍等于把同一个目录读 20 次（N+1）。分组后每目录只扫一次，
    run 画像按 run_id 缓存复用——多个任务常常指向同一批 run。
    """
    from src.workflow.run_profile import (
        compare_run_baseline,
        pick_recent_runs,
    )

    runs_dir = WORKFLOWS_DIR / workflow_id / "runs"
    metas = _iter_run_metadata(runs_dir)
    if not metas:
        return {}
    metas_by_id = {m["run_id"]: m for m in metas}
    profile_cache: dict[str, dict | None] = {}

    def profile_of(run_id: str) -> dict | None:
        if run_id in profile_cache:
            return profile_cache[run_id]
        loaded = _load_run_profile(runs_dir, metas_by_id.get(run_id), workflow_id)
        profile_cache[run_id] = loaded
        return loaded

    results: dict[str, dict] = {}
    for entry in entries:
        run_id = str(entry.get("run_id") or "")
        task_id = str(entry.get("task_id") or "")
        if not run_id or not task_id:
            continue
        meta = metas_by_id.get(run_id)
        if meta is None:
            # 任务引用的 run 文件不在 runs/ 里：不猜，不给趋势（诚实缺席）。
            continue
        current = profile_of(run_id)
        if current is None:
            continue
        history: list[dict] = []
        for older in pick_recent_runs(
                {"run_id": run_id, "started_at": meta.get("started_at"),
                 "mtime": meta.get("mtime", 0.0)}, metas, limit):
            loaded = profile_of(older["run_id"])
            if loaded is not None:
                history.append(loaded)
        baseline = compare_run_baseline(current, history)
        streak = baseline.get("failure_streak") or {}
        results[task_id] = {
            "run_id": run_id,
            "trend": baseline["trend"],
            "consecutive_required": baseline["consecutive_required"],
            "points_considered": len(baseline["points"]),
            "comparisons": len([d for d in baseline["deltas"] if d["comparable"]]),
            "delta_failure_rate": (baseline["deltas"][-1]["delta_failure_rate"]
                                   if baseline["deltas"] else None),
            # R52：与 trend 正交的第二个信号。trend 看「失败率在不在上升」，
            # 一个每次都 100% 失败的工作流相邻差值恒为 0 → trend=stable。
            # 这里补的正是那一半：最近 N 次是不是全挂。
            "consecutive_failed": streak.get("consecutive_failed", 0),
            "all_failed": streak.get("all_failed", False),
            "all_failed_required": streak.get("required", 0),
        }
    return results


@router.post("/{workflow_id}/tasks/{task_id}/stop")
async def stop_task(workflow_id: str, task_id: str, request: Request):
    """停止正在运行的任务。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    return await mgr.stop_task(workflow_id, task_id)


@router.get("/{workflow_id}/tasks/{task_id}/nodes/{node_id}/messages")
async def get_node_messages(workflow_id: str, task_id: str, node_id: str, request: Request):
    """获取任务中某个节点的 Agent 会话消息历史和推理链路。"""
    mgr = _get_manager(request)
    result = mgr.get_node_messages(workflow_id, task_id, node_id)
    if result is None:
        raise HTTPException(status_code=404, detail="任务或节点不存在")
    return result


# ============================================================
# Agent 类型查询 API（供前端节点库使用）
# ============================================================

@router.get("/agent-types/list")
async def list_agent_types(request: Request):
    """列出可用的 Agent 类型（供前端画布节点库）。

    返回每个 agent 类型的信息，包括其 prompt template 的自定义变量块声明。
    """
    from src.agent.definition import list_available_sub_session_types, get_agent_definition
    from src.prompts.manager import PromptManager

    pm = getattr(request.app.state, "prompt_manager", None)

    types = []
    for at in list_available_sub_session_types():
        ad = get_agent_definition(at)
        agent_info = {
            "agent_type": at,
            "description": ad.description if ad else "",
        }

        # 获取该 agent 的 prompt template 的自定义变量块声明
        if ad and ad.prompt_template and pm:
            try:
                template_vars = pm.get_template_variables(ad.prompt_template)
                agent_info["template_variables"] = template_vars
            except Exception:
                agent_info["template_variables"] = []
        else:
            agent_info["template_variables"] = []

        types.append(agent_info)
    return types


# ============================================================
# 节点类型查询 API（供前端节点面板使用）
# ============================================================

@router.get("/node-types/list")
async def list_node_types(request: Request):
    """列出所有已注册的节点类型（供前端画布节点面板渲染）。"""
    from src.workflow.nodes import registry
    return registry.list_all()


# ============================================================
# 子流程节点 API（可见变量）
# ============================================================

@router.get("/{workflow_id}/visible-variables")
async def get_visible_variables(workflow_id: str, request: Request):
    """获取指定工作流的可见变量列表（供子流程节点填参使用）。

    可见变量定义：source_type="input" 且 hidden!=true 的变量。
    返回每个变量的 key、name、type、default、required、description、options。
    """
    mgr = _get_manager(request)
    wf_data = mgr.get_workflow(workflow_id)
    if wf_data is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    variables = wf_data["definition"].get("variables", [])
    visible = [
        v for v in variables
        if v.get("source_type", "input") == "input" and not v.get("hidden", False)
    ]
    return visible


# ============================================================
# 执行方案 API
# ============================================================

class SchemeCreateRequest(BaseModel):
    name: str = Field(description="方案名称")
    selected_node_ids: list[str] = Field(description="选中的节点 ID 列表")


class SchemeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, description="方案名称")
    selected_node_ids: list[str] | None = Field(default=None, description="选中的节点 ID 列表")


@router.get("/{workflow_id}/schemes")
async def list_schemes(workflow_id: str, request: Request):
    """列出工作流的所有执行方案。"""
    mgr = _get_manager(request)
    result = mgr.get_schemes(workflow_id)
    if result is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return result


@router.post("/{workflow_id}/schemes")
async def create_scheme(workflow_id: str, request: Request, body: SchemeCreateRequest):
    """创建新的执行方案。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    try:
        result = mgr.create_scheme(workflow_id, body.name, body.selected_node_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return result


@router.put("/{workflow_id}/schemes/{scheme_id}")
async def update_scheme(workflow_id: str, scheme_id: str, request: Request,
                         body: SchemeUpdateRequest):
    """更新执行方案。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    try:
        result = mgr.update_scheme(workflow_id, scheme_id,
                                    name=body.name,
                                    selected_node_ids=body.selected_node_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="工作流或方案不存在")
    return result


@router.delete("/{workflow_id}/schemes/{scheme_id}")
async def delete_scheme(workflow_id: str, scheme_id: str, request: Request):
    """删除执行方案。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    success = mgr.delete_scheme(workflow_id, scheme_id)
    if not success:
        raise HTTPException(status_code=404, detail="方案不存在")
    return {"success": True}


# ============================================================
# 审批节点 API（人工审批）
# ============================================================

class ResolveApprovalRequest(BaseModel):
    approved: bool = Field(description="是否通过：true=通过，false=驳回")
    reason: str = Field(default="", description="驳回原因")


@router.post("/{workflow_id}/tasks/{task_id}/resolve-approval/{node_id}")
async def resolve_approval(workflow_id: str, task_id: str, node_id: str,
                            request: Request, body: ResolveApprovalRequest):
    """人工审批节点决策（审批节点使用）。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = await mgr.approve_node_async(
        workflow_id=workflow_id, task_id=task_id,
        node_id=node_id, approved=body.approved, feedback=body.reason,
    )
    return result


# ============================================================
# Main 接管模式 API
# ============================================================

class VariableUpdateRequest(BaseModel):
    parameter_values: dict[str, str] = Field(default_factory=dict)


@router.post("/{workflow_id}/pre-start")
async def pre_start_workflow(workflow_id: str, request: Request,
                               body: PreStartRequest = PreStartRequest()):
    """预启动工作流：创建 pending task + workspace + workflow-main session。
    返回 task_id 和 session_id，前端随后可连接 WebSocket 与 main 对话填参。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = await mgr.pre_start_task(workflow_id,
                                       workspace_override=body.workspace_override,
                                       main_takeover=body.main_takeover)
    if not result.get("success"):
        _raise_runtime_draining(result)
        raise HTTPException(status_code=400, detail=result.get("message", "预启动失败"))
    return result


@router.put("/{workflow_id}/tasks/{task_id}/variables")
async def update_task_variables(workflow_id: str, task_id: str,
                                 request: Request, body: VariableUpdateRequest):
    """更新任务的全局变量参数值（用于手动填参后更新 pending task）。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    if not mgr.update_task_variables(workflow_id, task_id, body.parameter_values or {}):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "message": "参数已更新", "task_id": task_id}


@router.post("/{workflow_id}/tasks/{task_id}/start")
async def start_pre_running_task(workflow_id: str, task_id: str, request: Request):
    """从预启动状态正式启动任务执行。仅对 pre_running 状态的任务有效。"""
    mgr = _ensure_http_mutation_allowed(request, workflow_id)
    result = await mgr.start_pre_running_task(workflow_id, task_id)
    if not result.get("success"):
        _raise_runtime_draining(result)
        raise HTTPException(status_code=400, detail=result.get("message", "启动失败"))
    return result


# ============================================================
# 脚本文件管理 API
# ============================================================

_SCRIPT_NAME_RE = re.compile(r"^[\w][\w\-]*$")

def _get_script_path(workflow_id: str, script_name: str, script_type: str = "shell") -> Path:
    """构建脚本文件路径，含安全校验。"""
    from src.config import WORKFLOWS_DIR
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", workflow_id)
    if not safe_id:
        raise HTTPException(status_code=400, detail=f"workflow_id 包含非法字符: {workflow_id}")
    if not _SCRIPT_NAME_RE.match(script_name):
        raise HTTPException(status_code=400, detail=f"脚本名包含非法字符: {script_name}")
    ext_map = {"shell": "sh", "python": "py"}
    if script_type not in ext_map:
        raise HTTPException(status_code=400, detail=f"不支持的脚本类型: {script_type}，可选: {', '.join(ext_map)}")
    ext = ext_map[script_type]
    wf_dir = (WORKFLOWS_DIR / safe_id).resolve()
    if not wf_dir.is_relative_to(WORKFLOWS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="workflow_id 路径越界")
    return wf_dir / "script" / f"{script_name}.{ext}"


class ScriptContentRequest(BaseModel):
    content: str = Field(description="脚本内容")


@router.get("/{workflow_id}/script/{script_name}")
async def get_script_content(workflow_id: str, script_name: str,
                              request: Request, type: str = "shell"):
    """读取脚本文件内容。"""
    script_path = _get_script_path(workflow_id, script_name, type)
    if not script_path.exists():
        return {"content": "", "exists": False}
    try:
        content = script_path.read_text(encoding="utf-8")
        return {"content": content, "exists": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取脚本失败: {e}")


@router.put("/{workflow_id}/script/{script_name}")
async def update_script_content(workflow_id: str, script_name: str,
                                 request: Request, body: ScriptContentRequest,
                                 type: str = "shell"):
    """写入/更新脚本文件内容。"""
    _ensure_http_mutation_allowed(request, workflow_id)
    _ensure_workflow_writable(request, workflow_id)
    script_path = _get_script_path(workflow_id, script_name, type)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        script_path.write_text(body.content, encoding="utf-8")
        return {"success": True, "message": f"脚本 {script_name} 已保存"}
    except Exception as e:
        logger.exception("保存脚本失败")
        raise HTTPException(status_code=500, detail="保存脚本失败，请查看服务日志")


@router.delete("/{workflow_id}/script/{script_name}")
async def delete_script(workflow_id: str, script_name: str,
                         request: Request, type: str = "shell"):
    """删除脚本文件。"""
    _ensure_http_mutation_allowed(request, workflow_id)
    _ensure_workflow_writable(request, workflow_id)
    script_path = _get_script_path(workflow_id, script_name, type)
    if not script_path.exists():
        return {"success": True, "message": "脚本文件不存在"}
    try:
        script_path.unlink()
        return {"success": True, "message": f"脚本 {script_name} 已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除脚本失败: {e}")


# ============================================================
# 全局任务历史 API（跨工作流）
# ============================================================

tasks_router = APIRouter(prefix="/api", tags=["tasks"])


# ============================================================
# 脚本库 API（data/script-library/）
# ============================================================

import shutil
from src.workflow.script_library import get_script_library


@router.get("/script-library/groups")
async def list_script_library_groups(request: Request):
    """列出脚本库所有分组（子目录名）。"""
    return get_script_library().list_groups()


@router.get("/script-library/scripts")
async def list_script_library_scripts(request: Request, group: str = ""):
    """列出脚本库所有脚本（含分组信息），可按分组过滤。

    返回格式：[{group: "utils", name: "deploy", script_type: "shell"}, ...]
    """
    return get_script_library().list_scripts(group)


@router.get("/script-library/{group}/{script_name}/script")
async def get_library_script_content(group: str, script_name: str,
                                      request: Request, type: str = "shell"):
    """读取脚本库脚本文件内容。"""
    if not _SCRIPT_NAME_RE.match(script_name):
        raise HTTPException(status_code=400, detail=f"脚本名包含非法字符: {script_name}")
    ext_map = {"shell": "sh", "python": "py"}
    if type not in ext_map:
        raise HTTPException(status_code=400, detail=f"不支持的脚本类型: {type}")
    ext = ext_map[type]
    try:
        location = get_script_library().resolve_file(group, script_name, f"{script_name}.{ext}")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库路径: {group}/{script_name}")
    if location is None:
        return {"content": "", "exists": False}
    script_path = location.directory / f"{script_name}.{ext}"
    try:
        content = script_path.read_text(encoding="utf-8")
        return {"content": content, "exists": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取脚本失败: {e}")


class LibraryScriptUpdateRequest(BaseModel):
    content: str = Field(description="脚本内容")


@router.put("/script-library/{group}/{script_name}/script")
async def update_library_script_content(group: str, script_name: str,
                                         request: Request, body: LibraryScriptUpdateRequest,
                                         type: str = "shell"):
    """创建/更新脚本库脚本文件。"""
    if not _SCRIPT_NAME_RE.match(script_name):
        raise HTTPException(status_code=400, detail=f"脚本名包含非法字符: {script_name}")
    ext_map = {"shell": "sh", "python": "py"}
    if type not in ext_map:
        raise HTTPException(status_code=400, detail=f"不支持的脚本类型: {type}")
    ext = ext_map[type]
    try:
        script_dir = get_script_library().writable_directory(group, script_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库路径: {group}/{script_name}")
    script_path = script_dir / f"{script_name}.{ext}"
    script_dir.mkdir(parents=True, exist_ok=True)
    try:
        script_path.write_text(body.content, encoding="utf-8")
        return {"success": True, "message": f"脚本已保存: {script_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存脚本失败: {e}")


@router.delete("/script-library/{group}/{script_name}")
async def delete_library_script(group: str, script_name: str,
                                 request: Request):
    """删除脚本库脚本（含整个子目录）。"""
    if not _SCRIPT_NAME_RE.match(script_name):
        raise HTTPException(status_code=400, detail=f"脚本名包含非法字符: {script_name}")
    catalog = get_script_library()
    try:
        script_dir = catalog.writable_directory(group, script_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库路径: {group}/{script_name}")
    if not script_dir.exists():
        return {"success": True, "message": "脚本不存在"}
    try:
        shutil.rmtree(script_dir)
        # 如果分组目录为空，也清理它
        group_dir = catalog.writable_group(group)
        if group_dir.exists() and not any(group_dir.iterdir()):
            group_dir.rmdir()
        return {"success": True, "message": f"脚本已删除: {group}/{script_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除脚本失败: {e}")


@router.get("/script-library/{group}/{script_name}/meta")
async def get_library_script_meta(group: str, script_name: str,
                                   request: Request):
    """读取脚本库脚本的 SCRIPT.md 元信息。"""
    try:
        location = get_script_library().resolve_file(group, script_name, "SCRIPT.md")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库路径: {group}/{script_name}")
    if location is None:
        return {"content": "", "exists": False}
    meta_path = location.directory / "SCRIPT.md"
    try:
        content = meta_path.read_text(encoding="utf-8")
        return {"content": content, "exists": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取元信息失败: {e}")


class LibraryMetaUpdateRequest(BaseModel):
    content: str = Field(description="SCRIPT.md 内容")


@router.put("/script-library/{group}/{script_name}/meta")
async def update_library_script_meta(group: str, script_name: str,
                                      request: Request, body: LibraryMetaUpdateRequest):
    """更新脚本库脚本的 SCRIPT.md 元信息。"""
    try:
        script_dir = get_script_library().writable_directory(group, script_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库路径: {group}/{script_name}")
    script_dir.mkdir(parents=True, exist_ok=True)
    meta_path = script_dir / "SCRIPT.md"
    try:
        meta_path.write_text(body.content, encoding="utf-8")
        return {"success": True, "message": f"元信息已保存: {meta_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存元信息失败: {e}")


@router.delete("/script-library/{group}")
async def delete_library_group(group: str, request: Request):
    """删除脚本库分组（仅当分组为空时允许）。"""
    try:
        group_dir = get_script_library().writable_group(group)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法的脚本库分组: {group}")
    if not group_dir.exists():
        return {"success": True, "message": "分组不存在"}
    if any(group_dir.iterdir()):
        raise HTTPException(status_code=400, detail="分组不为空，请先删除组内所有脚本")
    try:
        group_dir.rmdir()
        return {"success": True, "message": f"分组已删除: {group}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除分组失败: {e}")


@tasks_router.get("/tasks")
async def list_all_tasks(request: Request,
                         status: str = "",
                         search: str = "",
                         sort_by: str = "created_at",
                         sort_order: str = "desc",
                         page: int = 1,
                         page_size: int = 20,
                         workflow_id: str = "",
                         main_session_id: str = "",
                         with_trend: bool = False,
                         baseline_limit: int = 5):
    """列出全部工作流的所有任务（全局任务历史），支持筛选/排序/搜索/分页。

    Query params:
        status: 状态过滤
        search: 搜索关键词（匹配名称/task_id/模板名称/workflow_id）
        sort_by: 排序字段（created_at/started_at/completed_at/status/name/workflow_name）
        sort_order: asc 或 desc
        page / page_size: 分页
        workflow_id: 按工作流过滤（可选）
        main_session_id: 按任务所属 Main 会话过滤（可选）
        with_trend: 是否给每条任务附 ``trend`` 块（R51，默认关）
        baseline_limit: 趋势要回溯多少个历史 run（默认 5，上限 20）
    """
    mgr = _get_manager(request)
    result = mgr.list_all_tasks(
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
        workflow_id=workflow_id,
        main_session_id=main_session_id,
    )
    if with_trend and isinstance(result, dict) and result.get("tasks"):
        limit_n = max(1, min(int(baseline_limit), 20))
        # 按 workflow 分组：一页 20 条可能跨十几个 workflow，逐条扫目录是
        # N 次全目录解析；分组后每个 workflow 只扫一次（``_collect_workflow_trends``
        # 内部还按 run_id 缓存画像，因为多个任务常指向同一批 run）。
        grouped: dict[str, list[dict]] = {}
        by_key: dict[tuple[str, str], dict] = {}
        for task in result["tasks"]:
            wf = str(task.get("workflow_id") or "")
            task_id = str(task.get("task_id") or "")
            if not wf:
                continue
            grouped.setdefault(wf, []).append(
                {"task_id": task_id, "run_id": task.get("run_id")})
            by_key[(wf, task_id)] = task
        for wf, entries in grouped.items():
            trends = _collect_workflow_trends(wf, entries, limit_n)
            for task_id, block in trends.items():
                task = by_key.get((wf, task_id))
                if task is not None:
                    task["trend"] = block
    return result
