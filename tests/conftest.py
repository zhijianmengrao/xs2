"""Test-process fallback for the community Executor Pool defaults.

Community runtime defaults are process mode with four members. Tests keep the
supported environment-variable rollback to inline/1 unless a case overrides it.
"""

from __future__ import annotations

import os

os.environ.setdefault("DETERMINFLOW_WORKFLOW_EXECUTOR_MODE", "inline")
os.environ.setdefault("DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT", "1")

import pathlib
import re
import sys
import tempfile

import pytest


def _can_create_symlink() -> bool:
    """Probe the actual OS capability without changing production behavior."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="symlink-probe-"))
    link = root / "link"
    target = root / "target"
    target.mkdir()
    try:
        os.symlink(target, link)
        link.unlink(missing_ok=True)
        return True
    except OSError:
        return False
    finally:
        link.unlink(missing_ok=True)
        target.rmdir()
        root.rmdir()


_CAN_CREATE_SYMLINK = _can_create_symlink()


def pytest_collection_modifyitems(config, items):
    # Skip the macOS-only signing tests when Mach-O tooling is absent.
    if sys.platform != "darwin":
        for item in items:
            if "macos_signing" in pathlib.Path(str(item.fspath)).name.lower():
                item.add_marker(
                    pytest.mark.skip(
                        reason="macOS signing tooling is unavailable on this platform"
                    )
                )
    # Symlink-dependent cases opt in explicitly via @pytest.mark.requires_symlink;
    # no fragile source-text scanning. Skip them only when the OS cannot create
    # symlinks (e.g. Windows without the SeCreateSymbolicLinkPrivilege token).
    if _CAN_CREATE_SYMLINK:
        return
    for item in items:
        if item.get_closest_marker("requires_symlink"):
            item.add_marker(
                pytest.mark.skip(
                    reason="OS-level symlink creation is unavailable in this environment"
                )
            )