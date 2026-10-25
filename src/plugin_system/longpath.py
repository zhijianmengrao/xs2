r"""Windows 长路径支持。

插件 checkout 树（checkouts/<id>/<commit>-<digest16>/...）叠加深层 vendor
资源后可能逼近或超过 MAX_PATH（260）：目录路径达到 254 字符时，
iterdir/scandir 追加通配符后即越界并抛 WinError 3。因此所有针对
checkout 树的遍历、复制、删除与哈希操作都必须经 extended_path() 转为
\\\\?\ 扩展路径；非 Windows 平台原样返回。

约束：扩展路径仅用作文件系统调用参数，禁止写入持久化记录
（lock/manifest/marker），也不要与未加前缀的路径做 relative_to 比较。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

_PathLike = Union[str, "os.PathLike[str]"]


def extended_path(path: _PathLike) -> Path:
    """Return a MAX_PATH-safe path for filesystem calls on Windows."""
    raw = os.fspath(path)
    if os.name != "nt":
        return Path(raw)
    if raw.startswith("\\\\?\\"):
        return Path(raw)
    absolute = os.path.abspath(raw)
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC" + absolute[1:])
    return Path("\\\\?\\" + absolute)
