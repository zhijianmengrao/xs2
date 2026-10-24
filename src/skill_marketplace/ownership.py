"""Local ownership is authoritative for marketplace installation state."""

from __future__ import annotations

import re
from typing import Any

from src.core.win_names import unsafe_device_name
from src.skills.manager import SkillManager

from .errors import LocalSkillError

SKILL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def skill_id_is_safe(value: str) -> bool:
    """正则 + 设备名的合并判定（不抛错，供需要返回状态而非异常的调用方使用）。"""
    return bool(SKILL_ID_PATTERN.fullmatch(value)) and unsafe_device_name(value) is None


def assert_safe_skill_id(value: str, *, field: str = "Skill 标识") -> str:
    """Skill 标识共用守卫：正则之后追加 Windows 设备名判定。

    ``nul``/``con``/``com1`` 等小写设备名是合法的 kebab-case，却会用作
    ``marketplace-skills/<id>`` 的**目录名**。``NUL`` 是幻影目录：一旦产生，
    ``Path.exists()`` 恒真而目录列表里没有它，``installation_state()`` 便据
    ``exists()`` 判定为 ``conflict``（409「已存在」），而 ``get_skill()`` 永远读不到
    —— 该名字在命名空间里被永久占用，且没有任何可删除的实体。与 B11（插件 id）
    同源，故同样**不按平台门控**：Skill 标识要写进 `skills_config.json` 并在各平台
    共享，条件式校验会让同一份配置在一侧有效、另一侧损坏。
    """
    reason = unsafe_device_name(value)
    if reason is not None:
        raise LocalSkillError("invalid_slug", f"{field}格式无效（{reason}）")
    return value
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def installation_state(
    detail: dict[str, Any],
    *,
    skill_manager: SkillManager,
    marketplace_url: str | None,
) -> dict[str, Any]:
    """Local ownership is authoritative; never relay a registry's local state."""
    resource = _mapping(detail.get("resource"))
    payload = _mapping(detail.get("payload"))
    skill_id = payload.get("name") or detail.get("skill_name") or resource.get("slug") or detail.get("slug")
    state: dict[str, Any] = {"status": "available", "version": None, "enabled": None}
    if not isinstance(skill_id, str) or not skill_id_is_safe(skill_id):
        # 设备名在此也必须是 conflict：幻影目录会让下面的 exists() 恒真，理由不同、
        # 结论一致，但走本谓词可让判定面与 `_validate_slug` 完全对齐。
        return {**state, "status": "conflict"}
    skill = skill_manager.get_skill(skill_id)
    if skill is None:
        if (skill_manager.marketplace_skills_dir / skill_id).exists():
            state["status"] = "conflict"
        return state
    state.update(status="conflict", version=skill.version or None, enabled=skill.enabled)
    provenance = skill.metadata.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    source = _mapping(provenance.get("source"))
    if source.get("kind") == "core":
        state["status"] = "builtin"
    elif (
        source.get("kind") == "marketplace"
        and marketplace_url is not None
        and source.get("registry") == marketplace_url
        and source.get("resource_id") == remote_resource_id(detail)
        and source.get("resource_id") is not None
    ):
        state["status"] = "installed"
        local_version = skill.version or _package_version(provenance)
        comparison = compare_semver(remote_release_version(detail), local_version)
        if comparison is not None:
            state["update_available"] = comparison == 1
    return state


def resolve_openable_skill(
    slug: str,
    *,
    skill_manager: SkillManager,
    marketplace_url: str | None,
) -> str:
    if not SKILL_ID_PATTERN.fullmatch(slug):
        raise LocalSkillError("invalid_slug", "Skill 标识格式无效")
    # 必须先于 exists() 判定：`marketplace-skills/nul` 的 exists() 恒真（幻影），
    # 走下去会得到 409「本地存在同名但来源不同的 Skill」——那里其实什么都没有，
    # 属于对用户的谎报。设备名一律按输入无效处理（400）。
    assert_safe_skill_id(slug)
    skill = skill_manager.get_skill(slug)
    if skill is None:
        if (skill_manager.marketplace_skills_dir / slug).exists():
            raise LocalSkillError(
                "conflict",
                "本地存在同名但来源不同的 Skill",
                status_code=409,
            )
        raise LocalSkillError("not_found", "本地未安装该 Skill", status_code=404)
    provenance = skill.metadata.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    source = _mapping(provenance.get("source"))
    if source.get("kind") == "core":
        return slug
    if (
        source.get("kind") == "marketplace"
        and marketplace_url is not None
        and source.get("registry") == marketplace_url
    ):
        return slug
    raise LocalSkillError(
        "conflict",
        "本地存在同名但来源不同的 Skill",
        status_code=409,
    )


def remote_resource_id(detail: dict[str, Any]) -> Any:
    resource = _mapping(detail.get("resource"))
    return resource.get("id") or detail.get("resource_id")


def remote_release_version(detail: dict[str, Any]) -> str:
    resource = _mapping(detail.get("resource"))
    release = _mapping(resource.get("release"))
    version = (
        release.get("version")
        or detail.get("version")
        or detail.get("declared_version")
        or detail.get("version_number")
    )
    if not isinstance(version, str):
        return ""
    return version.strip()


def is_newer_semver(remote: str | None, local: str | None) -> bool:
    compared = compare_semver(remote, local)
    return compared == 1


def compare_semver(left: str | None, right: str | None) -> int | None:
    parsed_left = parse_semver(left)
    parsed_right = parse_semver(right)
    if parsed_left is None or parsed_right is None:
        return None
    if parsed_left > parsed_right:
        return 1
    if parsed_left < parsed_right:
        return -1
    return 0


def parse_semver(value: str | None) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]] | None:
    if not isinstance(value, str):
        return None
    match = _SEMVER_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    major, minor, patch, prerelease = match.groups()
    if prerelease is None:
        return (int(major), int(minor), int(patch), 1, ())
    parts: list[tuple[int, int | str]] = []
    for identifier in prerelease.split("."):
        if identifier.isdigit():
            if len(identifier) > 1 and identifier.startswith("0"):
                return None
            parts.append((0, int(identifier)))
        else:
            parts.append((1, identifier))
    return (int(major), int(minor), int(patch), 0, tuple(parts))


def _package_version(provenance: dict[str, Any]) -> str:
    package = _mapping(provenance.get("package"))
    version = package.get("version")
    return version.strip() if isinstance(version, str) else ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
