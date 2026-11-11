"""Public plugin package storage and process lifecycle interfaces."""

from .builtin import (
    BUILTIN_PLUGIN_IDS,
    builtin_plugin_ids,
    builtin_plugins_root,
    ensure_builtin_plugins,
    ensure_enabled_plugins,
)
from .dependencies import (
    PluginDependencyError,
    install_applied_plugin_requirements,
    install_plugin_requirements,
)
from .longpath import extended_path
from .models import (
    PluginLockRecord,
    PluginRevision,
    ProcessHealthCheck,
    ProcessSpec,
    validate_plugin_id,
    validate_plugin_ref,
    validate_plugin_subdirectory,
    validate_resource_prefix,
)
from .processes import ProcessManager, ProcessManagerError, ProcessStartError
from .registry import PluginRegistryConfig, PluginRegistryError
from .store import (
    InvalidPluginPackageError,
    PluginStore,
    PluginStoreError,
    SourceTrustError,
)

__all__ = [
    "BUILTIN_PLUGIN_IDS",
    "InvalidPluginPackageError",
    "PluginLockRecord",
    "PluginDependencyError",
    "PluginRegistryConfig",
    "PluginRegistryError",
    "PluginRevision",
    "PluginStore",
    "PluginStoreError",
    "ProcessHealthCheck",
    "ProcessManager",
    "ProcessManagerError",
    "ProcessSpec",
    "ProcessStartError",
    "SourceTrustError",
    "builtin_plugin_ids",
    "builtin_plugins_root",
    "ensure_builtin_plugins",
    "ensure_enabled_plugins",
    "extended_path",
    "install_applied_plugin_requirements",
    "install_plugin_requirements",
    "validate_plugin_id",
    "validate_plugin_ref",
    "validate_plugin_subdirectory",
    "validate_resource_prefix",
]
