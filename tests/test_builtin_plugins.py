"""内置插件与免 Git 本地插件源。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.extension_host import source_config as source_config_module
from src.extension_host.source_config import fetch_plugin_catalog, load_plugin_sources
from src.plugin_system import builtin as builtin_module
from src.plugin_system.builtin import ensure_builtin_plugins, ensure_enabled_plugins
from src.plugin_system.store import PluginStore


def _write_plugin(directory: Path, plugin_id: str = "demo-plugin") -> Path:
    directory.mkdir(parents=True)
    (directory / "extension.toml").write_text(
        "\n".join(
            [
                "[extension]",
                f'id = "{plugin_id}"',
                'name = "Demo Plugin"',
                'version = "1.0.0"',
                'api_version = "1"',
                'description = "Demo"',
                "",
                "[resource_namespace]",
                f'prefix = "{plugin_id}"',
            ]
        ),
        encoding="utf-8",
    )
    (directory / "resource.txt").write_text("payload", encoding="utf-8")
    return directory


def test_plugin_store_installs_a_plain_directory_without_git(tmp_path: Path) -> None:
    source = _write_plugin(tmp_path / "source")
    store = PluginStore(
        tmp_path / "plugins",
        git_binary="determinflow-missing-git-binary",
        official_sources=[source.as_uri()],
    )

    record = store.install("demo-plugin", source.as_uri(), ref="main")

    checkout = Path(record.active_revision.checkout_path)
    assert (checkout / "resource.txt").read_text(encoding="utf-8") == "payload"
    assert len(record.active_revision.commit) == 40
    assert store.verify("demo-plugin").plugin_id == "demo-plugin"


def test_local_catalog_reads_the_directory_without_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "plugin-repository.toml").write_text(
        "\n".join(
            [
                'schema_version = "1"',
                'name = "Builtin Catalog"',
                "",
                "[[plugins]]",
                'id = "demo-plugin"',
                'subdirectory = "plugins/demo-plugin"',
            ]
        ),
        encoding="utf-8",
    )
    _write_plugin(repository / "plugins" / "demo-plugin")

    config_file = tmp_path / "config" / "plugin-sources.json"
    config_file.parent.mkdir()
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "official_sources": [
                    {"name": "Local", "url": str(repository), "ref": "main"}
                ],
            }
        ),
        encoding="utf-8",
    )

    def forbidden_git(*_args, **_kwargs):
        raise AssertionError("local catalog must not invoke git")

    monkeypatch.setattr(source_config_module, "_run_git", forbidden_git)
    catalog = fetch_plugin_catalog(load_plugin_sources(config_file))

    assert catalog["sources"][0]["error"] == ""
    assert catalog["sources"][0]["transport"] == "directory"
    assert len(catalog["sources"][0]["resolved_commit"]) == 40
    assert [plugin["id"] for plugin in catalog["plugins"]] == ["demo-plugin"]
    assert catalog["plugins"][0]["version"] == "1.0.0"


def test_builtin_plugin_is_installed_and_enabled_without_installer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builtin_root = tmp_path / "builtin-plugins"
    _write_plugin(builtin_root / "demo-plugin")
    monkeypatch.setattr(
        builtin_module,
        "builtin_plugins_root",
        lambda: builtin_root,
    )

    plugins_root = tmp_path / "data" / "plugins"
    assert ensure_builtin_plugins(
        plugins_root,
        plugin_ids=("demo-plugin",),
    ) == ["demo-plugin"]
    assert ensure_builtin_plugins(
        plugins_root,
        plugin_ids=("demo-plugin",),
    ) == []

    config_file = tmp_path / "config" / "extensions.json"
    config_file.parent.mkdir()
    config_file.write_text(
        json.dumps({"enabled": ["existing"], "strict_startup": False}),
        encoding="utf-8",
    )
    assert ensure_enabled_plugins(config_file, ("demo-plugin",)) == ["demo-plugin"]
    assert ensure_enabled_plugins(config_file, ("demo-plugin",)) == []
    assert json.loads(config_file.read_text(encoding="utf-8"))["enabled"] == [
        "existing",
        "demo-plugin",
    ]


def test_builtin_source_supports_update_from_the_bundled_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builtin_root = tmp_path / "builtin-plugins"
    _write_plugin(builtin_root / "demo-plugin")
    monkeypatch.setattr(
        builtin_module,
        "builtin_plugins_root",
        lambda: builtin_root,
    )
    store = PluginStore(
        tmp_path / "plugins",
        official_sources=["builtin://demo-plugin"],
    )
    first = store.install("demo-plugin", "builtin://demo-plugin", ref="main")

    (builtin_root / "demo-plugin" / "resource.txt").write_text(
        "updated",
        encoding="utf-8",
    )
    second = store.update("demo-plugin")

    assert first.active_revision.content_sha256 != second.active_revision.content_sha256
    assert (
        Path(second.active_revision.checkout_path) / "resource.txt"
    ).read_text(encoding="utf-8") == "updated"


def test_builtin_plugin_repairs_a_missing_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    builtin_root = tmp_path / "builtin-plugins"
    _write_plugin(builtin_root / "demo-plugin")
    monkeypatch.setattr(
        builtin_module,
        "builtin_plugins_root",
        lambda: builtin_root,
    )

    plugins_root = tmp_path / "data" / "plugins"
    ensure_builtin_plugins(plugins_root, plugin_ids=("demo-plugin",))
    store = PluginStore(plugins_root)
    record = store.get("demo-plugin")
    shutil.rmtree(record.active_revision.checkout_path)

    assert ensure_builtin_plugins(
        plugins_root,
        plugin_ids=("demo-plugin",),
    ) == ["demo-plugin"]
    store.verify("demo-plugin")
