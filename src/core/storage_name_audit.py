"""存储名只读审计——Windows 保留设备名在历史数据中的遗留检测（R21，B13 纵深）。

R20（B11/B12/B13）在三个「名字变目录」的入口统一拒绝了设备名 id，此后新数据
不会再写入；但**历史数据**（旧版本写入、或 POSIX 平台写入后同步到 Windows 的
配置/锁文件）仍可能包含此类 id。危害回顾：

- 目录侧：``checkouts/<id>``、``runtime-resources/<id>``、``skills/<area>/<id>``
  在 Windows 上成为幻影或异常目录（``NUL`` 的 ``exists()`` 恒真而实体不可达，
  ``rmtree`` 静默无效，见 PROJECT_INFO 平台注意事项 12/13）；
- 配置侧：``plugins.lock.json`` / ``skills_config.json`` 的键是跨平台共享键，
  单个设备名 id 会使整份锁文件/配置在 Windows 上失效（``_parse_registry_plugin``
  对任一非法 id 判定整份清单无效）。

本模块**只读**：列出命中面与整改建议，不修改任何文件。设备名的删除在 Windows
上需要 ``\\\\?\\`` 前缀路径手工处理（幻影目录甚至无实体可删），故清理不自动化。

只扫描**承载 id 的层级**（各存储面的顶层目录项、配置文件的 id 键），不深入
插件仓库内部——后者内容不是由本项目的命名面派生的。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.core.win_names import is_reserved_device_name

# 配置文件 → (id 所在的 section, 面描述)。缺文件时静默跳过（CI 克隆不含 data/）。
_CONFIG_SURFACES: tuple[tuple[str, str, str], ...] = (
    ("config/skills_config.json", "skill_configs", "Skill 启用配置键（Skill id）"),
    ("data/plugins/plugins.lock.json", "plugins", "插件锁文件键（插件 id）"),
)

# 目录面 → 目录项即 id 的存储位置。
_DIR_SURFACES: tuple[str, ...] = (
    "data/plugins/checkouts",
    "data/plugins/runtime-resources",
    "data/skills/builtin",
    "data/skills/local",
    "data/skills/marketplace",
)

_REMEDIATION_CONFIG = (
    "手工从该配置文件删除此键（R20 守卫已上线，合法入口不会再写入设备名 id）"
)
_REMEDIATION_DIR = (
    "Windows 下用 ``\\\\?\\`` 前缀路径手工删除该目录后经正规入口重装；"
    "POSIX 下可直接删除（设备名在该平台是普通名字）"
)


@dataclass(frozen=True)
class StorageNameFinding:
    """一条设备名遗留命中。"""

    surface: str  # 命中面（配置文件路径或目录路径，相对仓库根）
    name: str  # 命中的名字
    kind: str  # config-key / storage-entry
    detail: str  # 面描述与整改建议


def scan_storage_names(root: Path) -> list[StorageNameFinding]:
    """只读扫描仓库根下的配置与存储面，返回全部设备名命中。

    缺失的文件/目录按无命中处理（只读诊断不因布局不全而报错）；无法解析的
    JSON 同样跳过——损坏配置的修复不是本诊断的职责。
    """
    root = Path(root)
    findings: list[StorageNameFinding] = []
    for relative, section, detail in _CONFIG_SURFACES:
        findings.extend(
            _scan_json_keys(root / relative, section=section, surface=relative, detail=detail)
        )
    for relative in _DIR_SURFACES:
        findings.extend(_scan_dir_entries(root / relative, surface=relative))
    return findings


def _scan_json_keys(
    path: Path, *, section: str, surface: str, detail: str
) -> list[StorageNameFinding]:
    if not path.is_file():
        return []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    keys = document.get(section) if isinstance(document, dict) else None
    if not isinstance(keys, dict):
        return []
    return [
        StorageNameFinding(
            surface=surface, name=name, kind="config-key",
            detail=f"{detail}：{_REMEDIATION_CONFIG}",
        )
        for name in sorted(keys)
        if is_reserved_device_name(name)
    ]


def _scan_dir_entries(path: Path, *, surface: str) -> list[StorageNameFinding]:
    if not path.is_dir():
        return []
    try:
        entries = sorted(path.iterdir(), key=lambda item: item.name)
    except OSError:
        return []
    return [
        StorageNameFinding(
            surface=surface, name=entry.name,
            kind="storage-entry" if entry.is_dir() else "storage-file",
            detail=f"目录项名字（id）为保留设备名：{_REMEDIATION_DIR}",
        )
        for entry in entries
        if is_reserved_device_name(entry.name)
    ]
