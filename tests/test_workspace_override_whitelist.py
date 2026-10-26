"""R37 B24：workspace 覆盖白名单回归。

两层语义：
- 核心解析器（resolve_workflow_workspace_path）：相对 override 只允许落在
  BASE_DIR/data 之内，越界回退默认路径（与既有「穿越出 BASE_DIR 回退」同款
  语义）；绝对路径的 BASE_DIR/DATA_DIR 允许面保持不变（插件批处理等在用）。
- console 面（novel_routes._console_root）：白名单外的 workspace 覆盖一律
  400 明确拒因，不再把默认工作区冒充用户请求的位置（谎报 0% 书）。

修复前实测（活体 8021）：GET /api/novel-console/progress?workspace=data/workspaces/
../../r37-escape-probe → 200 且仓库根出现 r37-escape-probe/ 目录。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import config
from src.core.workspace_manager import WorkspaceManager
from src.web import novel_routes


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """BASE_DIR / DATA_DIR / 工作区根三件套，全部指向临时目录。"""
    project_root = tmp_path / "project"
    data_root = project_root / "data"
    workspaces = data_root / "workspaces"
    project_root.mkdir()
    monkeypatch.setattr(config, "BASE_DIR", project_root)
    monkeypatch.setattr(config, "DATA_DIR", data_root)
    return project_root, workspaces, WorkspaceManager(base_dir=str(workspaces))


# ------------------------------------------------------------- 核心解析器层

def test_relative_override_under_data_is_allowed(roots):
    project_root, workspaces, manager = roots
    resolved = manager.resolve_workflow_workspace("wf-a", override="data/workspaces/books/x")
    assert resolved == (project_root / "data/workspaces/books/x").resolve()
    assert resolved.is_dir()


def test_relative_override_to_bare_name_falls_back(roots):
    project_root, workspaces, manager = roots
    resolved = manager.resolve_workflow_workspace("wf-b", override="foo")
    assert resolved == workspaces / "wf-b"
    assert not (project_root / "foo").exists()


def test_relative_override_traversing_out_of_data_falls_back(roots):
    """修复前实测的逃逸形态：以 data/ 开头但用 .. 折回仓库根。"""
    project_root, workspaces, manager = roots
    resolved = manager.resolve_workflow_workspace(
        "wf-c", override="data/workspaces/../../escape-probe")
    assert resolved == workspaces / "wf-c"
    assert not (project_root / "escape-probe").exists()


def test_relative_override_legacy_data_book_form_still_resolves(roots):
    """既有钉值形态（test_pure_workspace_resolver...）：data/book/<uuid>。"""
    project_root, _, manager = roots
    override = "data/book/00000000-0000-0000-0000-000000000001"
    resolved = manager.resolve_workflow_workspace("wf-d", override=override)
    assert resolved == (project_root / override).resolve()


def test_absolute_override_allowances_unchanged(roots):
    """绝对路径的 BASE_DIR/DATA_DIR 允许面是既有钉值语义，白名单不得收紧。"""
    project_root, workspaces, manager = roots
    legacy = project_root / "data" / "legacy-workspace"
    plugin = project_root / "data" / "plugins" / "example" / "batches"
    assert manager.resolve_workflow_workspace(
        "wf-e", override=str(legacy)) == legacy.resolve()
    assert manager.resolve_workflow_workspace(
        "wf-f", override=str(plugin)) == plugin.resolve()
    # 默认路径（无 override）不受影响
    assert manager.resolve_workflow_workspace("wf-g") == workspaces / "wf-g"


# ------------------------------------------------------------- console 路由层

class _FakeWorkspaces:
    def __init__(self, root: Path):
        self.root = root

    def resolve_workflow_workspace(self, workflow_id, override=None):
        target = Path(override) if override else self.root / "default-ws"
        target.mkdir(parents=True, exist_ok=True)
        return target


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    book = tmp_path / "workspaces" / "books" / "b1"
    book.mkdir(parents=True)
    monkeypatch.setattr(novel_routes, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(novel_routes, "WORKFLOW_WORKSPACES_DIR", tmp_path / "workspaces")
    app = FastAPI()
    app.include_router(novel_routes.router)
    app.state.workflow_manager = SimpleNamespace(
        _ws_manager=_FakeWorkspaces(tmp_path / "workspaces"),
        get_workflow_execution_policy=lambda _workflow: "public",
        is_workflow_owner_enabled=lambda _workflow: True,
    )
    with TestClient(app) as test_client:
        return test_client


def test_console_rejects_escaping_relative_override(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for workspace in ("foo", "data/workspaces/../../escape-probe", "../outside"):
        response = client.get("/api/novel-console/progress", params={
            "workflow_id": "xs2-novel-flywheel", "workspace": workspace})
        assert response.status_code == 400, (workspace, response.text)
        assert "必须位于" in response.json()["detail"]
    assert not (tmp_path / "escape-probe").exists()


def test_console_rejects_outside_absolute_override(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/api/novel-console/progress", params={
        "workflow_id": "xs2-novel-flywheel",
        "workspace": str(tmp_path / "elsewhere" / "book")})
    assert response.status_code == 400, response.text


def test_console_allows_workspace_under_workspaces_root(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/api/novel-console/progress", params={
        "workflow_id": "xs2-novel-flywheel",
        "workspace": str(tmp_path / "workspaces" / "books" / "b1")})
    assert response.status_code == 200, response.text


def test_console_save_project_rejects_escaping_override(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.put("/api/novel-console/projects", json={
        "workflow_id": "xs2-novel-flywheel",
        "workspace": "data/workspaces/../../sneaky",
        "state": {"title": "x", "mode": "serial", "_revision": 0}})
    assert response.status_code == 400, response.text
    assert not (tmp_path / "sneaky").exists()
