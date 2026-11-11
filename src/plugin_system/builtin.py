"""Plugins shipped with the application itself.

Built-in Plugin packages live in ``builtin-plugins/<plugin-id>`` inside the
source tree. They are installed into the content-addressed PluginStore on
first start, without Git, without network access and without any explicit
user installation step.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Iterable

from .store import PluginStore, PluginStoreError

BUILTIN_PLUGIN_IDS: tuple[str, ...] = ("xs2-novel-flywheel",)

BUILTIN_PLUGINS_DIR_ENV = "DETERMINFLOW_BUILTIN_PLUGINS_DIR"


def builtin_plugins_root() -> Path:
    override = (os.environ.get(BUILTIN_PLUGINS_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / (
            "builtin-plugins"
        )
    return Path(__file__).resolve().parents[2] / "builtin-plugins"


def builtin_plugin_ids() -> tuple[str, ...]:
    root = builtin_plugins_root()
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            path.name
            for path in root.iterdir()
            if path.is_dir() and (path / "extension.toml").is_file()
        )
    )


def ensure_builtin_plugins(
    plugins_root: Path,
    *,
    plugin_ids: Iterable[str] = BUILTIN_PLUGIN_IDS,
    preflight: Callable[[str, Path], None] | None = None,
) -> list[str]:
    """Install missing built-in Plugin packages into ``plugins_root``.

    Existing valid installs are left untouched. A lock record whose checkout
    is gone or corrupt is dropped and re-installed from the bundled copy.
    """
    root = builtin_plugins_root()
    available = {
        plugin_id: root / plugin_id
        for plugin_id in plugin_ids
        if (root / plugin_id / "extension.toml").is_file()
    }
    if not available:
        return []
    store = PluginStore(
        plugins_root,
        official_sources=(directory.as_uri() for directory in available.values()),
    )
    installed: list[str] = []
    for plugin_id, directory in available.items():
        record = store.get(plugin_id)
        if record is not None:
            try:
                store.verify(plugin_id)
                continue
            except PluginStoreError:
                store.remove_record(plugin_id)
        store.install(
            plugin_id,
            directory.as_uri(),
            ref="main",
            subdirectory="",
            preflight=(
                None
                if preflight is None
                else (lambda checkout, pid=plugin_id: preflight(pid, checkout))
            ),
        )
        installed.append(plugin_id)
    return installed


def ensure_enabled_plugins(
    config_path: Path,
    plugin_ids: Iterable[str],
) -> list[str]:
    """Add missing Plugin ids to ``extensions.json`` without reordering."""
    config_path = Path(config_path)
    document: dict[str, object] = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            document = loaded
    raw_enabled = document.get("enabled", [])
    if not isinstance(raw_enabled, list):
        raw_enabled = []
    enabled = [item for item in raw_enabled if isinstance(item, str)]
    added = [plugin_id for plugin_id in plugin_ids if plugin_id not in enabled]
    if not added:
        return []
    document["enabled"] = [*enabled, *added]
    document.setdefault("strict_startup", False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, config_path)
    return added
