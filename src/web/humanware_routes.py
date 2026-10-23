"""Humanware Engine API Routes

提供角色声音管理和人味评分的 Web API 接口
调用 xs2-novel-flywheel 插件中的 humanware_helper 脚本
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/humanware", tags=["humanware"])

# ===== Request Models =====


class GenerateVoiceFileRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    from_profiles: bool = True
    from_references: bool = False


class CheckDialogueRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    character: str = Field(max_length=200)
    dialogue: str = Field(max_length=200_000)


class ScoreContentRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    character: str = Field(max_length=200)
    content: str = Field(max_length=10_000_000)
    content_type: str = "dialogue"


class ScoreChapterRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    chapter_file: str = Field(min_length=1, max_length=500)  # 相对于工作区的路径


# ===== Helper Functions =====

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_BOOKS_ROOT = _PROJECT_ROOT / "data" / "workspaces" / "books"
# 单进程并发执行 CLI 的上限（防止数十个请求同时拉起解释器）
_CLI_SEMAPHORE = asyncio.Semaphore(4)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$")
# 前端传 workspace 完整相对路径（data/workspaces/books/<id>）的前缀
_WORKSPACE_PATH_PREFIX = "data/workspaces/books/"
_VOICE_FILE_LOCK = asyncio.Lock()


def _get_workspace_root(workspace_id: str) -> Path:
    """获取工作区根目录（带路径穿越防护）。

    兼容两种输入格式：
    - 纯 id：``welcome`` → ``data/workspaces/books/welcome``
    - 完整相对路径：``data/workspaces/books/welcome``（前端实际发送的格式）
    """
    raw = (workspace_id or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="workspace_id 为空")
    candidate = raw.replace("\\", "/")
    if candidate.startswith(_WORKSPACE_PATH_PREFIX):
        candidate = candidate[len(_WORKSPACE_PATH_PREFIX):]
    candidate = candidate.strip("/")
    if not candidate:
        raise HTTPException(status_code=400, detail="workspace_id 非法")
    if not _SAFE_ID_RE.match(candidate):
        raise HTTPException(status_code=400, detail="workspace_id 含非法字符")
    books_root = _WORKSPACE_BOOKS_ROOT.resolve()
    root = (books_root / candidate).resolve()
    # 双重校验：解析结果必须仍位于 books 根下
    if root != books_root and books_root not in root.parents:
        raise HTTPException(status_code=400, detail="workspace_id 非法")
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"工作区 {workspace_id} 不存在")
    return root


def _get_humanware_cli_path() -> Path:
    """获取 humanware CLI 脚本路径"""
    cli_path = (
        _PROJECT_ROOT
        / "data"
        / "plugins"
        / "runtime-resources"
        / "xs2-novel-flywheel"
        / "script-libraries"
        / "0"
        / "xs2-novel-flywheel-xs2"
        / "humanware_helper"
        / "humanware_helper.py"
    )
    if not cli_path.exists():
        # 501：功能尚未就绪（插件未发布该脚本库），区别于 500 内部错误
        raise HTTPException(
            status_code=501,
            detail="Humanware CLI 未部署（当前插件版本未包含 humanware_helper 脚本库）",
        )
    return cli_path


def _run_humanware_command_blocking(command: str, *args) -> Dict[str, Any]:
    """运行 humanware CLI 命令（阻塞版，仅在线程池中调用）。

    演进说明：上游 API 需要 humanware CLI 按约定输出 JSON。这里只做输入
    校验和输出转译；CLI 尚未随插件发布时返回 501 让前端给出明确指引，
    而不是让页面一直转圈。
    """
    try:
        cli_path = _get_humanware_cli_path()
    except HTTPException as exc:
        return {"status": "error", "message": exc.detail, "code": exc.status_code}

    cmd = [sys.executable, str(cli_path), command] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=False, timeout=120)
    except subprocess.TimeoutExpired:
        logger.error("humanware 命令超时: %s", command)
        return {"status": "error", "message": f"命令执行超时: {command}", "code": 500}
    except OSError as exc:
        logger.error("humanware 命令启动失败: %s", exc)
        return {"status": "error", "message": f"命令启动失败: {exc}", "code": 500}

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="ignore")
        logger.error("命令执行失败: %s", stderr)
        return {"status": "error", "message": f"执行失败: {stderr}", "code": 500}

    try:
        stdout = result.stdout.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 - 解码失败按无输出处理
        stdout = ""
    if not stdout or not stdout.strip():
        logger.error("命令没有输出: %s", command)
        return {"status": "error", "message": "命令执行成功但没有输出", "code": 500}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        logger.error("无法解析输出: %s", result.stdout)
        return {"status": "error", "message": "无法解析命令输出", "code": 500, "raw_output": result.stdout}


async def _run_humanware_command(command: str, *args) -> Dict[str, Any]:
    """运行 humanware CLI 命令（异步版，在线程池中执行，不阻塞事件循环）"""
    async with _CLI_SEMAPHORE:
        return await asyncio.to_thread(_run_humanware_command_blocking, command, *args)


def _voice_file_path(workspace_root: Path) -> Path:
    return workspace_root / "meta" / "character_voice.md"


async def _generate_voice_file(request: GenerateVoiceFileRequest) -> Dict[str, Any]:
    workspace_root = _get_workspace_root(request.workspace_id)

    if request.from_references:
        # 从参考资料分析生成
        result = await _run_humanware_command("analyze-voice", str(workspace_root))
    else:
        # 从 character_profiles.md 生成模板
        result = await _run_humanware_command("generate-voice", str(workspace_root))

    if result.get("status") == "error":
        code = int(result.get("code", 500))
        # CLI 未部署（501）或业务失败（409+）直接透传状态码，前端可据此给出指引
        raise HTTPException(status_code=code, detail=result.get("message", "生成失败"))

    voice_file = _voice_file_path(workspace_root)

    return {
        "status": "success",
        "message": result.get("message", "生成成功"),
        "file_path": str(voice_file),
        "exists": voice_file.exists(),
        "character_count": result.get("character_count", 0),
    }


# ===== API Endpoints =====


@router.post("/generate-voice-file")
async def generate_voice_file(request: GenerateVoiceFileRequest) -> Dict[str, Any]:
    """生成 character_voice.md 文件

    Args:
        request: 包含工作区ID和生成选项

    Returns:
        生成结果
    """
    try:
        return await _generate_voice_file(request)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 兜底转为 500
        logger.error("生成角色声音文件失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {exc}") from exc


@router.get("/voice-file/{workspace_id}")
async def get_voice_file(workspace_id: str) -> Dict[str, Any]:
    """获取 character_voice.md 文件内容

    Args:
        workspace_id: 工作区ID

    Returns:
        文件内容和状态
    """
    try:
        workspace_root = _get_workspace_root(workspace_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("读取角色声音文件失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取失败: {exc}") from exc

    voice_file = _voice_file_path(workspace_root)

    if not voice_file.exists():
        return {
            "status": "not_found",
            "message": "character_voice.md 文件不存在",
            "content": None,
        }

    try:
        content = voice_file.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("读取角色声音文件失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取失败: {exc}") from exc

    return {
        "status": "success",
        "content": content,
        "file_path": str(voice_file),
    }


class VoiceFileSaveRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=1_000_000)


async def _save_voice_file(request: VoiceFileSaveRequest) -> Dict[str, Any]:
    workspace_root = _get_workspace_root(request.workspace_id)
    voice_file = _voice_file_path(workspace_root)
    async with _VOICE_FILE_LOCK:
        voice_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            voice_file.write_text(request.content, encoding="utf-8")
        except OSError as exc:
            logger.error("保存角色声音文件失败: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"保存失败: {exc}") from exc
    return {
        "status": "success",
        "message": "保存成功",
        "file_path": str(voice_file),
    }


@router.put("/voice-file/{workspace_id}")
async def save_voice_file(workspace_id: str, request: VoiceFileSaveRequest) -> Dict[str, Any]:
    """保存 character_voice.md 文件内容（前端编辑器保存）

    Args:
        workspace_id: 工作区ID
        request: 包含待保存内容

    Returns:
        保存结果
    """
    try:
        # URL 路径中的 workspace_id 优先于 body；两者不一致时以 URL 为准并提示
        if request.workspace_id and request.workspace_id != workspace_id:
            logger.warning("voice-file 保存路径与 body workspace_id 不一致: %s vs %s", workspace_id, request.workspace_id)
        return await _save_voice_file(VoiceFileSaveRequest(workspace_id=workspace_id, content=request.content))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("保存角色声音文件失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存失败: {exc}") from exc


@router.post("/check-dialogue")
async def check_dialogue(request: CheckDialogueRequest) -> Dict[str, Any]:
    """检查对话是否符合角色声音定义

    Args:
        request: 包含工作区ID、角色名和对话内容

    Returns:
        检查结果
    """
    try:
        workspace_root = _get_workspace_root(request.workspace_id)

        result = await _run_humanware_command(
            "check-dialogue",
            str(workspace_root),
            request.character,
            request.dialogue,
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("message", "检查失败"))

        return result

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("检查对话失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {exc}") from exc


@router.post("/score-content")
async def score_content(request: ScoreContentRequest) -> Dict[str, Any]:
    """评估内容的人味得分

    Args:
        request: 包含工作区和评分参数

    Returns:
        评分结果
    """
    try:
        workspace_root = _get_workspace_root(request.workspace_id)

        # 调用评分命令
        result = await _run_humanware_command(
            "score-text",
            str(workspace_root),
            request.character,
            request.content,
        )

        if result.get("status") == "error":
            code = int(result.get("code", 500))
            raise HTTPException(status_code=code, detail=result.get("message", "评分失败"))

        return result

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("评分失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"评分失败: {exc}") from exc


@router.post("/score-chapter")
async def score_chapter(request: ScoreChapterRequest) -> Dict[str, Any]:
    """批量评估章节中所有对话

    Args:
        request: 包含工作区ID和章节文件路径

    Returns:
        批量评分结果
    """
    try:
        workspace_root = _get_workspace_root(request.workspace_id)

        # 调用批量评分命令
        result = await _run_humanware_command(
            "score-chapter",
            str(workspace_root),
            request.chapter_file,
        )

        if result.get("status") == "error":
            code = int(result.get("code", 500))
            raise HTTPException(status_code=code, detail=result.get("message", "评分失败"))

        return result

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("批量评分失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量评分失败: {exc}") from exc


@router.get("/status/{workspace_id}")
async def get_humanware_status(workspace_id: str) -> Dict[str, Any]:
    """获取人味功能的启用状态

    Args:
        workspace_id: 工作区ID

    Returns:
        状态信息
    """
    try:
        workspace_root = _get_workspace_root(workspace_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("获取状态失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取状态失败: {exc}") from exc

    voice_file = _voice_file_path(workspace_root)
    profiles_file = workspace_root / "meta" / "character_profiles.md"

    status: Dict[str, Any] = {
        "voice_file_exists": voice_file.exists(),
        "profiles_file_exists": profiles_file.exists(),
        "humanware_enabled": voice_file.exists(),
    }

    if voice_file.exists():
        try:
            content = voice_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("读取角色声音文件失败: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"读取失败: {exc}") from exc
        # 统计角色数量（简单计数 ## 开头的行）
        character_count = len(re.findall(r"^## [^#\s]", content, re.MULTILINE))
        status["character_count"] = character_count
    else:
        status["character_count"] = 0

    return status