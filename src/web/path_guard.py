"""Windows 文件系统名称约束（跨路由面复用）。

两类名称会让「基于 ``Path.exists()`` 的存在性校验」和「写后读」语义在 Windows 上失真：

1. **保留设备名**：``CON``/``PRN``/``AUX``/``NUL``/``COM1-9``/``LPT1-9``/``CONIN$``/
   ``CONOUT$``（含扩展名与大小写变体，如 ``NUL.txt``、``con.md``）。``Path(".../NUL").exists()``
   恒为 ``True``，写入 ``NUL`` 会静默丢弃内容且不报错——不存在的"工作区"会通过校验，
   用户的正文会被"保存成功"地丢掉。
2. **尾随点/空格**：Windows 在解析路径段时会剥离它们，因此 ``welcome.`` 与 ``welcome``
   指向同一目录（POSIX 上是两个不同名字），可用于绕过名字黑名单或让"不存在的工作区"
   命中真实工作区。

POSIX 平台两者都是合法普通文件名，故仅在 ``nt`` 上判定（返回 ``None``），保持跨平台行为不变。
"""

from __future__ import annotations

import os
import re
from typing import Optional

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


def unsafe_windows_component(name: str) -> Optional[str]:
    """返回路径段 ``name`` 在 Windows 上的问题描述；安全时返回 ``None``。

    非 ``nt`` 平台恒返回 ``None``（这些字符在该平台是合法文件名）。
    """
    if os.name != "nt":
        return None
    if not name:
        return None
    if _RESERVED_WITH_EXT.match(name) or name.upper() in WINDOWS_RESERVED_NAMES:
        return "为 Windows 保留设备名"
    if name != name.rstrip(". "):
        return "以点或空格结尾（Windows 解析时会剥离，形成同名别名）"
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
    if os.name != "nt":
        return None
    for part in getattr(root, "parts", ()) or ():
        # 跳过盘符锚点（"F:\\" / "C:"）等不可命名段
        if part.endswith(("\\", "/")) or part.endswith(":"):
            continue
        reason = unsafe_windows_component(part)
        if reason:
            return f"{part} {reason}"
    return None
