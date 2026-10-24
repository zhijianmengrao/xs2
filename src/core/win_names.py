"""Windows 文件系统名称约束——**单一规则源**（core 与 web 共用）。

为什么放在 core 而不是 web：约束的根源是 Windows 文件系统语义，凡是要在工作区根
目录下 `mkdir` / 写文件的调用方都受影响。R17 只在两个 web 路由面（humanware、
novel-console）收敛，本模块把同一套规则下沉到 core，供
`src.core.workspace_manager.WorkspaceManager` 使用；`src/web/path_guard.py` 退为
纯兼容门面（保持既有 import 路径与错误文案不变）。

三类问题名字（实测，见 docs/HANDOVER_ROUND18.md §4）：

1. **保留设备名**：``CON``/``PRN``/``AUX``/``NUL``/``COM1-9``/``LPT1-9``/``CONIN$``/
   ``CONOUT$``/``CLOCK$``（含带扩展名与大小写变体，如 ``NUL.txt``、``con.md``）。
   其中 ``NUL`` 最危险：``Path("<x>/NUL").exists()`` 恒真、``mkdir`` 静默「成功」，
   但其下任何真实写入都以 WinError 3 失败，``shutil.rmtree`` 也删不掉——得到一个
   既「存在」又不可用、且无法清理的**幻影目录**；把正文写到 ``NUL`` 文件则内容被
   静默丢弃且不报错。
   注：本机实测 ``CON``/``COM1``/``PRN``/``LPT1``/``AUX``/``CONIN$`` 作为**目录**
   可创建且能正常读写，但这是可版本/工具而异的宽松行为（资源管理器拒绝创建、
   Win32 部分 API 仍按设备解析），故一律拒绝，与 R17 已上线的 web 面保持一致。
2. **尾随点/空格**：Windows 解析路径段时剥离它们，``welcome.`` 成为真实工作区
   ``welcome`` 的**别名**（POSIX 上两者是不同名字），可用于绕过黑名单并以另一个
   id 读写真实数据。
3. **清洗后为空**：只含非 `[A-Za-z0-9_-]` 字符的 id（如纯中文）。这类输入属客户端
   错误，须以 ``UnsafeWorkspaceIdError``（``ValueError`` 子类）表达，避免 web 端点
   因裸 ``ValueError`` 逃逸而返回 500。

POSIX 上 1、2 都是合法普通文件名，故判定仅在 ``nt`` 生效（返回 ``None``/放行），
跨平台行为不变。`is_reserved_device_name` 是**平台无关**的纯谓词，供需要跨平台
一致拒绝的场景（Skill 包路径校验）复用同一份设备名集合。
"""

from __future__ import annotations

import os
import re
from typing import Optional


def _on_windows() -> bool:
    """平台钩子（唯一读取点）：集中判定以便测试注入，不改全局 ``os.name``。"""
    return os.name == "nt"

# Microsoft 官方保留名集合（固定，无需维护）。
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)

# 设备名后允许带扩展名（NUL.txt），与 skill_marketplace.bundle 的同型规则保持一致。
# 注：Windows 只保留 COM1-9 / LPT1-9（COM0 合法），故数字位用 [1-9]。
_RESERVED_WITH_EXT = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]|CONIN\$|CONOUT\$|CLOCK\$)(?:\.|$)",
    re.IGNORECASE,
)

# 供调用方复用的稳定拒因关键词（既有测试断言依赖「设备名」/「剥离」字样）。
REASON_DEVICE_NAME = "为 Windows 保留设备名"
REASON_TRAILING_DOT = "以点或空格结尾（Windows 解析时会剥离，形成同名别名）"


class UnsafeWorkspaceIdError(ValueError):
    """工作区/会话 id 在当前平台上不可安全使用。

    继承 ``ValueError`` 以保持既有 `except ValueError` 的行为；web 面据此统一映射
    为 HTTP 400（客户端输入错误），而不是 500。
    """


def is_reserved_device_name(name: str) -> bool:
    """**平台无关**判定：``name`` 是否命中 Windows 保留设备名规则。

    供 `skill_marketplace.bundle` 复用同一份集合——Skill 包需要跨平台一致的可移植
    校验，因此此处不按 ``os.name`` 门控。
    """
    if not name:
        return False
    return bool(_RESERVED_WITH_EXT.match(name)) or name.upper() in WINDOWS_RESERVED_NAMES


def has_unsafe_trailing_char(name: str) -> bool:
    """**平台无关**判定：``name`` 是否以点或空格结尾（Windows 会剥离）。"""
    if not name:
        return False
    return name != name.rstrip(". ")


def unsafe_windows_component(name: str) -> Optional[str]:
    """返回路径段 ``name`` 在 Windows 上的问题描述；安全时返回 ``None``。

    非 ``nt`` 平台恒返回 ``None``（这些字符在该平台是合法文件名）。
    """
    if not _on_windows():
        return None
    if not name:
        return None
    if is_reserved_device_name(name):
        return REASON_DEVICE_NAME
    if has_unsafe_trailing_char(name):
        return REASON_TRAILING_DOT
    return None


def unsafe_windows_path(relative: str) -> Optional[str]:
    """逐段检查相对路径；返回首个问题段的描述，安全时返回 ``None``。"""
    for part in relative.replace("\\", "/").split("/"):
        reason = unsafe_windows_component(part)
        if reason:
            return f"{part} {reason}"
    return None


def unsafe_windows_root(root) -> Optional[str]:
    """检查工作区根路径自身的各段名字（仅拦设备名）。

    ``workspace`` 覆盖参数由调用方提供，Windows 下若某段是设备名（如
    ``data/workspaces/books/NUL``），该段是「幻影目录」：``mkdir`` 静默成功、
    ``exists()`` 恒真，但其下任何真实写入都会以 WinError 3 失败（未捕获即 HTTP 500）。

    尾随点不在此检测：调用方传入的 root 已先经 ``Path.resolve()``，Windows 会把尾随点
    规范化掉（``book.`` → ``book``），后续各端一致使用该规范名，不构成读写错位。
    安全时返回 ``None``。
    """
    if not _on_windows():
        return None
    for part in getattr(root, "parts", ()) or ():
        # 跳过盘符锚点（"F:\\" / "C:"）等不可命名段
        if part.endswith(("\\", "/")) or part.endswith(":"):
            continue
        reason = unsafe_windows_component(part)
        if reason:
            return f"{part} {reason}"
    return None


def ensure_safe_component(name: str, *, label: str = "ID") -> str:
    """校验并返回 ``name``；不安全时抛 ``UnsafeWorkspaceIdError``。

    供 core 层在清洗 id 之后调用（清洗已剥掉点/空格，故此处实际只会命中设备名规则，
    尾随点的「非规范名拒绝」仍由 web 面在解析原始输入时负责）。
    """
    reason = unsafe_windows_component(name)
    if reason:
        raise UnsafeWorkspaceIdError(f"无效的 {label}（{name!r}）：{reason}")
    return name
