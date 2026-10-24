"""Round 18 核心层（core）Windows 名称语义守卫的回归测试。

对应交接 R17 §8 R17-3 / 本轮 B6/B7/B8。R17 只在 `src/web/` 两个路由面收敛守卫，
本文件证明 core 层（`WorkspaceManager`）自身仍是裸的，因而：

- B8：`create_workflow_workspace("NUL")` 在 Windows 上 mkdir **静默成功**，
  得到一个「幻影目录」（`exists()` 恒真、`is_dir()` 为假），其下写入必然
  FileNotFoundError(3)；`cleanup_workflow_workspace("NUL")` 又返回 **True**（谎报已删）。
- B6：`_sanitize_id` 清洗后为空时抛裸 `ValueError`，web 端点不捕获 → **HTTP 500**
  （应为 4xx 客户端错误）。
- B7：`resolve_workflow_workspace(override=<幻影根>)` 返回该幻影路径，只读端点据此
  返回 **200 + 空文件列表**（谎报工作区存在且为空）。

Windows 特有语义用 `os.name` 门控；平台门控本身用 monkeypatch 直接验证（在任意平台
都可跑），避免「只在某平台才执行」的用例形同虚设。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src import config
from src.core.workspace_manager import WorkspaceManager
from src.core import win_names


IS_NT = os.name == "nt"
RESERVED_IDS = ["NUL", "nul", "CON", "PRN", "AUX", "COM1", "LPT9"]


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkspaceManager:
    project_root = tmp_path / "project"
    data_root = tmp_path / "runtime-data"
    project_root.mkdir()
    data_root.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", project_root)
    monkeypatch.setattr(config, "DATA_DIR", data_root)
    return WorkspaceManager(base_dir=str(tmp_path / "ws"))


# ---------------------------------------------------------------- 平台门控


def test_win_names_gate_is_off_on_posix(monkeypatch):
    """非 nt 平台必须完全放行：NUL/尾随点在 POSIX 是合法文件名。

    打桩平台钩子 `win_names._on_windows`（而非全局 `os.name`），只影响本用例。
    """
    monkeypatch.setattr(win_names, "_on_windows", lambda: False)
    assert win_names.unsafe_windows_component("NUL") is None
    assert win_names.unsafe_windows_component("welcome.") is None
    assert win_names.unsafe_windows_path("references/NUL") is None
    assert win_names.unsafe_windows_root(Path("/srv/data/NUL")) is None


def test_pure_predicates_ignore_platform(monkeypatch):
    """`is_reserved_device_name`/`has_unsafe_trailing_char` 是平台无关纯谓词
    （供 bundle 跨平台复用），注入 posix 也必须照常判定。"""
    monkeypatch.setattr(win_names, "_on_windows", lambda: False)
    assert win_names.is_reserved_device_name("NUL")
    assert win_names.is_reserved_device_name("com1.log")
    assert not win_names.is_reserved_device_name("NULLU")
    assert win_names.has_unsafe_trailing_char("welcome.")


@pytest.mark.skipif(not IS_NT, reason="Windows 保留设备名语义仅在 nt 平台成立")
def test_win_names_gate_is_on_on_windows():
    assert win_names.unsafe_windows_component("NUL") is not None
    assert win_names.is_reserved_device_name("NUL")
    assert not win_names.is_reserved_device_name("NULLU")
    assert not win_names.is_reserved_device_name("COM0")


# ---------------------------------------------------------------- B8：core 拒绝设备名


@pytest.mark.skipif(not IS_NT, reason="幻影目录仅在 Windows 文件系统语义下成立")
def test_core_rejects_device_name_workspace_id(manager):
    """B8：`create_workflow_workspace("NUL")` 必须拒绝，而不是造出幻影目录。"""
    with pytest.raises(ValueError):
        manager.create_workflow_workspace("NUL")
    phantom = manager.base_dir / "NUL"
    # 注意：Windows 上任何以 NUL 结尾的路径 exists() 都恒真（设备本身"存在"），
    # 所以不能用它断言「没建出来」。真正的判据是：父目录里没有这个**目录项**，
    # 且它不是目录——修复前 mkdir 会静默「成功」并留下删不掉的幻影项。
    assert not phantom.is_dir()
    assert "NUL" not in [p.name for p in manager.base_dir.iterdir()]
    with pytest.raises(OSError):
        (phantom / "meta").mkdir(parents=True, exist_ok=True)


@pytest.mark.skipif(not IS_NT, reason="保留设备名仅在 nt 平台特判")
@pytest.mark.parametrize("raw_id", RESERVED_IDS)
def test_core_rejects_every_reserved_device_name_family(manager, raw_id):
    """大小写与常见设备名变体都要拦（清洗后仍是保留名）。"""
    with pytest.raises(ValueError):
        manager.create_workflow_workspace(raw_id)
    with pytest.raises(ValueError):
        manager.create_workspace(raw_id)


@pytest.mark.skipif(not IS_NT, reason="保留设备名仅在 nt 平台特判")
def test_core_still_accepts_safe_ids(manager):
    """守卫不得误伤：常规 id 与设备名前缀名照常可用。"""
    for raw_id in ("welcome", "xs2-novel-flywheel", "wf-1", "b11663a6",
                   "core", "console-NUL", "NULLU", "COM0", "nultxt"):
        path = manager.create_workflow_workspace(raw_id)
        assert path.is_dir(), raw_id
    assert manager.workflow_workspace_exists("welcome")


@pytest.mark.skipif(not IS_NT, reason="幻影目录仅在 Windows 文件系统语义下成立")
def test_phantom_root_would_break_writes_without_guard(tmp_path):
    """证明拒绝的必要性：幻影目录「存在」但任何写入都会失败。"""
    phantom = tmp_path / "NUL"
    phantom.mkdir(parents=True, exist_ok=True)  # 静默成功
    assert phantom.exists() and not phantom.is_dir()
    with pytest.raises(OSError):
        (phantom / "meta").mkdir(parents=True, exist_ok=True)
    # rmtree 也删不掉，故 cleanup 返回 True 属谎报（B8 的另一半）
    import shutil

    shutil.rmtree(phantom, ignore_errors=True)
    assert phantom.exists()


@pytest.mark.skipif(not IS_NT, reason="cleanup 谎报仅在幻影目录场景成立")
def test_cleanup_does_not_lie_about_phantom_workspace(manager):
    """B8：幻影项无法删除，cleanup 不得返回 True。守卫后 id 直接被拒。"""
    with pytest.raises(ValueError):
        manager.cleanup_workflow_workspace("NUL")


# ---------------------------------------------------------------- B6：错误类型必须是 4xx 语义


def test_sanitize_failure_uses_client_error_type(manager):
    """B6：清洗后为空属客户端输入问题，不得以裸 ValueError 逃逸成 HTTP 500。"""
    with pytest.raises(ValueError) as exc:  # 兼容既有 `except ValueError`
        manager.create_workspace("中文")
    assert isinstance(exc.value, win_names.UnsafeWorkspaceIdError)
    assert isinstance(exc.value, ValueError)


@pytest.mark.skipif(not IS_NT, reason="保留设备名仅在 nt 平台特判")
def test_sanitize_device_name_uses_client_error_type(manager):
    with pytest.raises(win_names.UnsafeWorkspaceIdError):
        manager.create_workflow_workspace("NUL")


def test_sanitize_keeps_existing_normalisation(manager):
    """保持既有接口行为：合法 id 的清洗规则不变（本用例在任何平台都跑）。"""
    assert WorkspaceManager._sanitize_id("wf_1") == "wf_1"
    assert WorkspaceManager._sanitize_id("  sp  ") == "sp"
    assert WorkspaceManager._sanitize_id("nul.txt") == "nultxt"


# ---------------------------------------------------------------- B7：不得返回幻影根


@pytest.mark.skipif(not IS_NT, reason="幻影根仅在 Windows 文件系统语义下成立")
def test_resolve_workflow_workspace_refuses_phantom_override(manager, tmp_path):
    """B7：override 指到幻影目录时必须拒绝，不得返回「看起来存在」的路径。"""
    phantom_root = manager.base_dir / "books" / "NUL"
    with pytest.raises(ValueError):
        manager.resolve_workflow_workspace("wf", override=str(phantom_root))
    # 不得留下幻影残骸（books 本身也不该被顺手建出来）
    assert not (manager.base_dir / "books").exists()


@pytest.mark.skipif(not IS_NT, reason="幻影根仅在 Windows 文件系统语义下成立")
def test_resolve_workflow_workspace_does_not_create_phantom_via_id(manager):
    """守卫须在建目录**之前**判定：不得留下无法删除的残骸。"""
    with pytest.raises(ValueError):
        manager.resolve_workflow_workspace("NUL")
    assert "NUL" not in [p.name for p in manager.base_dir.iterdir()]


@pytest.mark.skipif(not IS_NT, reason="幻影根仅在 Windows 文件系统语义下成立")
def test_main_task_workspace_rejects_device_name(manager):
    with pytest.raises(ValueError):
        manager.create_main_task_workspace("session-1", "NUL")
    with pytest.raises(ValueError):
        manager.create_main_task_workspace("NUL", "task-1")
