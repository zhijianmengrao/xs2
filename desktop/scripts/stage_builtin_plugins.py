"""Stage the built-in Plugin packages as an immutable release snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.extension_host.plugin_preflight import validate_plugin_checkout
from src.plugin_system import extended_path
from src.plugin_system.release import prepare_release_snapshot
from src.plugin_system.store import PluginStore


def _builtin_plugin_dirs(repo_root: Path) -> list[tuple[str, Path]]:
    root = repo_root / "builtin-plugins"
    if not root.is_dir():
        raise RuntimeError(f"内置插件目录不存在: {root}")
    plugins = [
        (path.name, path)
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "extension.toml").is_file()
    ]
    if not plugins:
        raise RuntimeError(f"内置插件目录为空: {root}")
    return plugins


def stage_builtin_plugins(repo_root: Path, output_dir: Path) -> dict[str, object]:
    """Install bundled plugins into a release snapshot without Git or network."""
    plugins = _builtin_plugin_dirs(repo_root)
    plugin_ids = [plugin_id for plugin_id, _ in plugins]

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="builtin-plugins-", dir=output_dir.parent)
    )
    try:
        store_root = temporary_root / "store"
        store = PluginStore(
            store_root,
            official_sources=(directory.as_uri() for _, directory in plugins),
        )
        for plugin_id, directory in plugins:
            store.install(
                plugin_id,
                directory.as_uri(),
                ref="main",
                preflight=lambda checkout, pid=plugin_id: validate_plugin_checkout(
                    pid, checkout
                ),
            )
        store.apply_pending()

        snapshot = temporary_root / "snapshot"
        metadata = prepare_release_snapshot(
            store_root,
            snapshot,
            required_plugins=plugin_ids,
        )

        # The build machine path must not leak into the shipped lock. Built-in
        # plugins are owned by the application and cannot be re-fetched by URL.
        lock_path = snapshot / "plugins.lock.json"
        document = json.loads(lock_path.read_text(encoding="utf-8"))
        for plugin_id in plugin_ids:
            document["plugins"][plugin_id]["source"] = f"builtin://{plugin_id}"
            document["plugins"][plugin_id]["source_kind"] = "local"
            document["plugins"][plugin_id]["trust"] = "official"
        lock_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for plugin_id in plugin_ids:
            metadata["plugins"][plugin_id]["source"] = f"builtin://{plugin_id}"
        metadata["builtin"] = True
        (snapshot / "release-plugins.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if output_dir.exists():
            shutil.rmtree(extended_path(output_dir))
        snapshot.replace(output_dir)
        return metadata
    finally:
        shutil.rmtree(extended_path(temporary_root), ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    repo_root = options.repo_root.resolve()
    output = options.output or repo_root / "desktop" / "generated" / "bundled-plugins"
    stage_builtin_plugins(repo_root, output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
