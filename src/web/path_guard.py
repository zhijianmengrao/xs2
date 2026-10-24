"""Windows 文件系统名称约束（web 路由面兼容门面）。

规则实现已下沉到 `src.core.win_names`，由 core 与 web 共用**单一源**（R17-3 / R18 O1）。
本模块只做再导出，保留既有 import 路径不变，使 `humanware_routes` / `novel_routes`
无需改动即可复用同一实现。新增调用方请直接依赖 `src.core.win_names`。

它拦的两类名称会让「基于 ``Path.exists()`` 的存在性校验」和「写后读」语义在 Windows 上失真：

1. **保留设备名**（``CON``/``PRN``/``AUX``/``NUL``/``COM1-9``/``LPT1-9``/``CONIN$`` 等，
   含扩展名与大小写变体）：``Path(".../NUL").exists()`` 恒真，写入 ``NUL`` 会静默丢弃
   内容且不报错——不存在的"工作区"会通过校验，用户正文被"保存成功"地丢掉。
2. **尾随点/空格**（``welcome.``）：Windows 解析时剥离，成为真实工作区 ``welcome`` 的
   别名（POSIX 上是两个不同名字），可绕过黑名单并读写到别人的数据。

POSIX 上两者都是合法文件名，故判定仅在 ``nt`` 生效（返回 ``None``），跨平台行为不变。
"""

from __future__ import annotations

from src.core.win_names import (
    REASON_DEVICE_NAME,
    REASON_TRAILING_DOT,
    WINDOWS_RESERVED_NAMES,
    UnsafeWorkspaceIdError,
    is_reserved_device_name,
    unsafe_windows_component,
    unsafe_windows_path,
    unsafe_windows_root,
)

__all__ = [
    "REASON_DEVICE_NAME",
    "REASON_TRAILING_DOT",
    "WINDOWS_RESERVED_NAMES",
    "UnsafeWorkspaceIdError",
    "is_reserved_device_name",
    "unsafe_windows_component",
    "unsafe_windows_path",
    "unsafe_windows_root",
]
