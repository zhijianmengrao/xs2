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


def _symlink_dependent_test_names(source: str) -> set[str]:
    """Return test function names whose body references symlink creation."""
    result: set[str] = set()
    # Match top-level async/test functions; bodies run to the next top-level def/class.
    for match in re.finditer(
        r"^(?:async\s+)?def\s+(test_[A-Za-z0-9_]*)\b.*?^(?=(?:async\s+)?def\s+|\Z)",
        source,
        re.MULTILINE | re.DOTALL,
    ):
        name, body = match.group(1), match.group(0)
        if "symlink" in body.lower():
            result.add(name)
    return result


def pytest_collection_modifyitems(config, items):
    if _CAN_CREATE_SYMLINK:
        return
    for item in items:
        source_path = pathlib.Path(str(item.fspath))
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError:
            source = ""
        # Skip the macOS-only signing tests when Mach-O tooling is absent.
        if (
            sys.platform != "darwin"
            and "macos_signing" in source_path.name.lower()
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason="macOS signing tooling is unavailable on this platform"
                )
            )
            continue
        base_name = item.name.split("[", 1)[0]
        if base_name not in _symlink_dependent_test_names(source):
            continue
        item.add_marker(
            pytest.mark.skip(
                reason="OS-level symlink creation is unavailable in this environment"
            )
        )