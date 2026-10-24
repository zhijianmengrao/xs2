"""Web 层统一错误映射——把 core 的输入类异常收敛为 4xx。

R18 B6：`WorkspaceManager._sanitize_id` 在 id 清洗后为空（如纯中文）时抛 `ValueError`，
而 novel/workflow 端点不捕获它，Starlette 兜底成 **HTTP 500**——把客户端输入错误
报成服务端故障，前端只看到 "Internal Server Error"，作者无从知道是自己填的名字不对。

本模块把 `UnsafeWorkspaceIdError`（`ValueError` 子类）统一映射为 **400**，并在响应
里保留拒因，便于前端给出可执行的指引。`create_app` 与单测都调用 `install_*`，保证
被测代码路径与线上一致。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.core.win_names import UnsafeWorkspaceIdError

logger = logging.getLogger(__name__)


def install_workspace_error_handlers(application: FastAPI) -> None:
    """注册 core 输入类异常 → HTTP 状态码的映射。幂等（重复注册覆盖同一 key）。"""

    @application.exception_handler(UnsafeWorkspaceIdError)
    async def _unsafe_workspace_id(_request, exc: UnsafeWorkspaceIdError):  # noqa: ANN001
        logger.warning("工作区/会话 id 被拒绝: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})
