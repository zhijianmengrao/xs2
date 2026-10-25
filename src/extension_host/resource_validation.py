"""Validation for file-backed Plugin resource bundles."""

from __future__ import annotations

from pathlib import Path

from src.extension_api.registrar import ExtensionContributions, OwnedPath
from src.plugin_system import extended_path
from src.rules.loader import RuleLoader
from src.skills.loader import SkillLoader
from src.workflow.script_library import ScriptLibraryCatalog


def _extended_roots(
    roots: list[OwnedPath] | None,
) -> list[OwnedPath]:
    return [
        OwnedPath(root.owner, extended_path(root.path), root.revision)
        for root in (roots or [])
    ]


def validate_file_resources(
    data_dir: Path,
    existing: ExtensionContributions,
    pending: ExtensionContributions,
) -> None:
    """Validate bundles and script libraries across all active owners."""

    def owner_enabled(_owner: str) -> bool:
        return True

    skill_roots = [
        *existing.resource_paths.get("skill_bundles", []),
        *pending.resource_paths.get("skill_bundles", []),
    ]
    if skill_roots:
        SkillLoader(
            data_dir / "skills",
            resource_roots=_extended_roots(skill_roots),
            owner_enabled=owner_enabled,
        ).validate_sources()

    rule_roots = [
        *existing.resource_paths.get("rule_bundles", []),
        *pending.resource_paths.get("rule_bundles", []),
    ]
    if rule_roots:
        RuleLoader(
            data_dir / "rules",
            resource_roots=_extended_roots(rule_roots),
            owner_enabled=owner_enabled,
        ).validate_sources()

    script_roots = [
        *existing.resource_paths.get("script_libraries", []),
        *pending.resource_paths.get("script_libraries", []),
    ]
    if script_roots:
        ScriptLibraryCatalog(
            data_dir / "script-library",
            extension_roots=_extended_roots(script_roots),
            owner_enabled=owner_enabled,
        ).validate_sources()
