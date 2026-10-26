"""
Workspace 管理器 - 统一管理 Chat 和 Workflow 的工作空间生命周期

职责：
- Chat Session: 统一使用 data/workspaces/{session_id}
- Workflow: data/workspaces/{workflow_id}/（共享根，所有节点统一使用）
- Workspace 的创建、查询、清理
"""
import os
import re
import shutil
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import src.config as config
from src.core.win_names import (
    UnsafeWorkspaceIdError,
    unsafe_windows_component,
    unsafe_windows_root,
)

logger = logging.getLogger(__name__)

_DEFAULT_WORKSPACE_RELATIVE_PATH = Path("data") / "workspaces"


def resolve_workspace_base_path(base_dir: str | Path | None = None) -> Path:
    """Resolve the configured Workspace root to a writable absolute path."""
    configured = config.CODING_WORKSPACE_BASE if base_dir is None else base_dir
    raw_path = str(configured).strip()
    if not raw_path:
        return (config.DATA_DIR / "workspaces").resolve()

    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    if candidate == _DEFAULT_WORKSPACE_RELATIVE_PATH:
        return (config.DATA_DIR / "workspaces").resolve()

    desktop_mode = os.getenv("DETERMINFLOW_DESKTOP", "").strip().lower()
    anchor = (
        config.DATA_DIR.parent
        if desktop_mode in {"1", "true", "yes", "on"}
        else config.BASE_DIR
    )
    return (anchor / candidate).resolve()


def _ensure_resolvable_root(resolved: Path, anchor: Path) -> Path:
    """拒绝落在 Windows「幻影目录」上的 workspace 覆盖路径（R18 B7）。

    只检查 ``anchor`` **以下**由调用方提供的那几段，不复查祖先目录——仓库自身所在
    路径不属于本次输入，检查它会把正常部署整体打死。

    为何必须在 core 拦：``NUL`` 段 `mkdir` 静默成功、`exists()` 恒真，因此
    `resolve_workflow_workspace` 会把这条「看起来存在」的路径返回给调用方；只读端点
    据此返回 200 + 空列表（谎报工作区存在且为空），写入端点则必然 WinError 3 崩溃。
    """
    reason = unsafe_windows_root(resolved.relative_to(anchor))
    if reason:
        raise UnsafeWorkspaceIdError(f"工作区路径名不安全：{reason}")
    return resolved


def resolve_workflow_workspace_path(
    workflow_id: str,
    override: str | None = None,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    """Purely resolve a Workflow workspace path without creating it."""
    safe_workflow_id = WorkspaceManager._sanitize_id(workflow_id)
    workspace_root = resolve_workspace_base_path(base_dir)
    default_path = workspace_root / safe_workflow_id

    override_path = override.strip() if override else ""
    if not override_path:
        return default_path

    if Path(override_path).is_absolute():
        resolved = Path(override_path).expanduser().resolve()
        allowed_roots = (
            config.BASE_DIR.resolve(),
            config.DATA_DIR.resolve(),
            workspace_root,
        )
        if not any(resolved.is_relative_to(root) for root in allowed_roots):
            logger.error(
                "绝对路径 override 逃逸出允许目录: %s 不在 %s 内，回退到默认路径",
                resolved,
                allowed_roots,
            )
            return default_path
        anchor = next(root for root in allowed_roots if resolved.is_relative_to(root))
        return _ensure_resolvable_root(resolved, anchor)

    resolved = (config.BASE_DIR / override_path).resolve()
    if not resolved.is_relative_to(config.BASE_DIR.resolve()):
        logger.error(
            "相对路径 override 穿越出 BASE_DIR: %s 解析为 %s，回退到默认路径",
            override_path,
            resolved,
        )
        return default_path
    # R37 B24：相对 override 只允许落在运行数据目录（BASE_DIR/data）之内。
    # 一切合法相对形态（data/workspaces/...、data/book/...、data/plugins/...）
    # 都以 data/ 开头；放行其余位置会在仓库根静默创建目录（实测
    # data/workspaces/../../<name> → 仓库根 <name>），只读端点还会把该位置
    # 谎报成一本 0% 的书。
    data_boundary = (config.BASE_DIR / "data").resolve()
    if not resolved.is_relative_to(data_boundary):
        logger.warning(
            "相对路径 override 落在运行数据目录 data/ 之外: %s 解析为 %s，回退到默认路径",
            override_path,
            resolved,
        )
        return default_path
    return _ensure_resolvable_root(resolved, config.BASE_DIR.resolve())


@dataclass
class WorkspaceInfo:
    """Workspace 信息"""
    session_id: str
    path: str
    size_bytes: int


class WorkspaceManager:
    """统一 Workspace 生命周期管理器，覆盖 chat 和 workflow 两种场景。"""

    def __init__(self, base_dir: str | None = None):
        """初始化 WorkspaceManager

        Args:
            base_dir: Workspace 存储根目录，默认从配置读取
        """
        # Session → workspace 路径映射（chat 场景）
        self._workspaces: dict[str, Path] = {}

        self.base_dir = resolve_workspace_base_path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"WorkspaceManager 初始化完成，base_dir={self.base_dir}")

    def set_base_dir(self, base_dir: str | Path | None = None) -> Path:
        """Update the default root used for workspaces created from now on."""
        resolved = resolve_workspace_base_path(base_dir)
        resolved.mkdir(parents=True, exist_ok=True)
        self.base_dir = resolved
        logger.info("WorkspaceManager base_dir 已更新: %s", resolved)
        return resolved

    # ============================================================
    # 安全工具
    # ============================================================

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        """过滤 session/workflow ID，仅保留安全字符，防止路径穿越。

        仅允许字母、数字、下划线、连字符。空结果抛 ValueError。

        额外拦 Windows 保留设备名（R17-3 / R18 B8）：``NUL`` 等清洗后原样保留，
        Windows 下 ``mkdir`` 会静默「成功」出一个幻影目录（``exists()`` 恒真、
        ``is_dir()`` 为假、其下写入必然失败、``shutil.rmtree`` 删不掉），
        既污染 ``data/workspaces/`` 又让后续读写与清理全部失真。
        尾随点/空白不在此拒：清洗本身已把它们剥掉（``welcome.`` → ``welcome``），
        返回值与落盘名一致，不构成读写错位；非规范名的原始字符串仍由各 web 面
        在解析入参时按 path_guard 拒绝（R17 v3.2）。
        """
        safe = re.sub(r"[^a-zA-Z0-9_-]", "", raw_id)
        if not safe:
            raise UnsafeWorkspaceIdError(f"无效的 ID（清洗后为空）: {raw_id!r}")
        reason = unsafe_windows_component(safe)
        if reason:
            raise UnsafeWorkspaceIdError(f"无效的 ID（{raw_id!r}）：{safe} {reason}")
        return safe

    # ============================================================
    # Chat session workspace（data/workspaces/{session_id}）
    # ============================================================

    def create_workspace(self, session_id: str, source_path: str | None = None) -> Path:
        """为 Session 创建 workspace

        Args:
            session_id: 会话 ID（仅允许 [a-zA-Z0-9_-]）
            source_path: 源目录路径，若指定则复制内容到新 workspace

        Returns:
            新创建的 workspace 路径: base_dir/{session_id}
        """
        session_id = self._sanitize_id(session_id)
        workspace_dir = self.base_dir / session_id
        workspace_dir.mkdir(parents=True, exist_ok=True)

        if source_path:
            source = Path(source_path)
            if source.exists() and source.is_dir():
                self._copy_workspace(source, workspace_dir)
            else:
                logger.warning(f"源目录不存在或不是目录: {source}")

        self._workspaces[session_id] = workspace_dir
        logger.info(f"Chat workspace 已创建: {session_id} -> {workspace_dir}")
        return workspace_dir

    def get_workspace(self, session_id: str) -> Path | None:
        """获取 Session 的 workspace 路径"""
        session_id = self._sanitize_id(session_id)
        # 先查缓存
        if session_id in self._workspaces:
            return self._workspaces[session_id]
        # 再查磁盘
        workspace_dir = self.base_dir / session_id
        if workspace_dir.exists():
            self._workspaces[session_id] = workspace_dir
            return workspace_dir
        return None

    def cleanup_workspace(self, session_id: str, force: bool = False) -> bool:
        """清理 Session 的 workspace

        Args:
            session_id: 会话 ID
            force: 是否强制删除（忽略错误）

        Returns:
            是否清理成功
        """
        session_id = self._sanitize_id(session_id)
        workspace_dir = self.base_dir / session_id
        if not workspace_dir.exists():
            self._workspaces.pop(session_id, None)
            return True

        try:
            shutil.rmtree(workspace_dir, ignore_errors=force)
            self._workspaces.pop(session_id, None)
            logger.info(f"Workspace 已清理: {session_id}")
            return True
        except Exception as e:
            logger.error(f"清理 workspace {session_id} 失败: {e}")
            return False

    def list_workspaces(self) -> list[WorkspaceInfo]:
        """列出所有 workspace"""
        workspaces = []
        if not self.base_dir.exists():
            return workspaces
        for item in self.base_dir.iterdir():
            if item.is_dir():
                size = self._get_dir_size(item)
                workspaces.append(WorkspaceInfo(
                    session_id=item.name,
                    path=str(item),
                    size_bytes=size,
                ))
        return workspaces

    def get_workspace_size(self, session_id: str) -> int:
        """获取 workspace 大小（字节）"""
        session_id = self._sanitize_id(session_id)
        workspace_dir = self.base_dir / session_id
        if workspace_dir.exists():
            return self._get_dir_size(workspace_dir)
        return 0

    # ============================================================
    # Workflow workspace
    #   目录结构: data/workspaces/{workflow_id}/
    #   所有节点统一使用共享 workspace 根目录
    # ============================================================

    def create_workflow_workspace(self, workflow_id: str) -> Path:
        """创建工作流 workspace 根目录（即共享 workspace）。

        Returns:
            workflow_root: base_dir/{workflow_id}/
        """
        workflow_id = self._sanitize_id(workflow_id)
        workflow_root = self.base_dir / workflow_id
        workflow_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workflow workspace 已创建: {workflow_root}")
        return workflow_root

    def create_main_task_workspace(
        self,
        session_id: str,
        task_id: str,
        *,
        mode: str = "task_isolated",
        workspace_ref: str | None = None,
    ) -> Path:
        """为 Chat Main 创建受控的工作流任务空间。

        ``task_isolated`` 为默认模式，每个任务独立目录；``named_shared``
        仅允许同一 Main 会话下通过安全名称显式共享。路径始终位于
        ``data/workspaces/_main`` 下，调用方不能注入任意文件系统路径。
        """
        safe_session_id = self._sanitize_id(session_id)
        safe_task_id = self._sanitize_id(task_id)
        main_root = self.base_dir / "_main" / safe_session_id

        if mode == "task_isolated":
            workspace = main_root / "tasks" / safe_task_id
        elif mode == "named_shared":
            if not workspace_ref:
                raise ValueError("named_shared 模式必须提供 workspace_ref")
            safe_ref = self._sanitize_id(workspace_ref)
            workspace = main_root / "shared" / safe_ref
        else:
            raise ValueError(f"不支持的 Main 任务工作空间模式: {mode}")

        workspace.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Main task workspace 已创建: session=%s task=%s mode=%s path=%s",
            safe_session_id,
            safe_task_id,
            mode,
            workspace,
        )
        return workspace

    def get_workflow_shared_workspace(self, workflow_id: str) -> Path | None:
        """获取工作流共享 workspace 路径: base_dir/{workflow_id}"""
        workflow_id = self._sanitize_id(workflow_id)
        shared = self.base_dir / workflow_id
        if shared.exists():
            return shared
        return None

    def get_workflow_root(self, workflow_id: str) -> Path:
        """获取工作流 workspace 根目录。"""
        workflow_id = self._sanitize_id(workflow_id)
        return self.base_dir / workflow_id

    def resolve_workflow_workspace(self, workflow_id: str,
                                   override: str | None = None) -> Path:
        """解析工作流 workspace 路径，支持覆盖。

        规则：
        - 若提供 override 绝对路径 → 仅允许项目根目录或运行数据目录内
        - 若提供 override 相对路径 → 相对于项目根目录（config.BASE_DIR）解析
        - 未提供 override → 使用默认路径 base_dir/{workflow_id}/
        - 自动创建目录（exist_ok=True）

        Returns:
            解析后的 workspace 绝对路径
        """
        ws_path = resolve_workflow_workspace_path(
            workflow_id,
            override=override,
            base_dir=self.base_dir,
        )
        ws_path.mkdir(parents=True, exist_ok=True)
        if override and override.strip():
            logger.info("Workflow workspace (override): %s", ws_path)
        return ws_path

    def cleanup_workflow_workspace(self, workflow_id: str) -> bool:
        """清理整个工作流的 workspace 目录。"""
        workflow_id = self._sanitize_id(workflow_id)
        workflow_root = self.base_dir / workflow_id
        if not workflow_root.exists():
            return True
        try:
            shutil.rmtree(workflow_root, ignore_errors=True)
            logger.info(f"Workflow workspace 已清理: {workflow_id}")
            return True
        except Exception:
            logger.exception(f"清理 workflow workspace {workflow_id} 失败")
            return False

    def workflow_workspace_exists(self, workflow_id: str) -> bool:
        """检查工作流 workspace 是否存在。"""
        workflow_id = self._sanitize_id(workflow_id)
        return (self.base_dir / workflow_id).exists()

    # ============================================================
    # 内部方法
    # ============================================================

    def _copy_workspace(self, source: Path, dest: Path) -> None:
        """复制 workspace 目录内容（带排除规则和大小限制）"""
        excludes = set(
            e.strip() for e in config.CODING_WORKSPACE_COPY_EXCLUDES.split(",") if e.strip()
        )
        max_size = config.CODING_WORKSPACE_MAX_SIZE
        copied_size = 0

        for item in source.iterdir():
            if item.name in excludes:
                logger.debug(f"跳过排除项: {item.name}")
                continue

            dest_item = dest / item.name
            try:
                if item.is_dir():
                    # 检查大小限制（计算一次 size 并复用）
                    dir_size = self._get_dir_size(item)
                    if copied_size + dir_size > max_size:
                        logger.warning(f"跳过目录 {item.name}：超出大小限制 ({max_size} bytes)")
                        continue
                    shutil.copytree(item, dest_item, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns(*excludes))
                    copied_size += dir_size
                elif item.is_file():
                    file_size = item.stat().st_size
                    if copied_size + file_size > max_size:
                        logger.warning(f"跳过文件 {item.name}：超出大小限制")
                        continue
                    shutil.copy2(item, dest_item)
                    copied_size += file_size
            except Exception as e:
                logger.error(f"复制 {item.name} 失败: {e}")

        logger.info(f"Workspace 复制完成: {source} -> {dest}, 大小: {copied_size} bytes")

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        """计算目录总大小"""
        total = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file():
                    total += entry.stat().st_size
        except (OSError, PermissionError):
            pass
        return total
