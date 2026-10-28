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

import shutil
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

    def resolve_workflow_workspace(self, workflow_id, override=None, create=True):
        target = Path(override) if override else self.root / "default-ws"
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    book = tmp_path / "workspaces" / "books" / "b1"
    book.mkdir(parents=True)
    monkeypatch.setattr(novel_routes, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(novel_routes, "WORKFLOW_WORKSPACES_DIR", tmp_path / "workspaces")
    # B27：PUT /projects 会把工作区写进 _index（真实 data/novel-console/workspaces.json），
    # 不 patch 会把 pytest 临时书路径漏进运行数据索引。
    monkeypatch.setattr(novel_routes, "_index", tmp_path / "data" / "novel-console" / "workspaces.json")
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


# ------------------------------------------------- R38 B26：读端点不再创建目录

def test_resolve_workflow_workspace_create_false_does_not_mkdir(roots):
    """核心层：create=False 只解析不创建，供读端点使用。"""
    project_root, workspaces, manager = roots
    resolved = manager.resolve_workflow_workspace(
        "wf-read", override="data/workspaces/books/phantom", create=False)
    assert resolved == (project_root / "data/workspaces/books/phantom").resolve()
    assert not resolved.exists()
    # 默认语义（任务执行/建书面）仍然创建
    assert manager.resolve_workflow_workspace("wf-task", override=str(
        project_root / "data/workspaces/books/real")).is_dir()


def test_console_get_progress_phantom_workspace_404_without_mkdir(tmp_path, monkeypatch):
    """修复前实测：GET progress 对不存在的书返回 0% 且创建空目录（nope_missing
    残留的根因）；修复后诚实 404，零目录副作用。"""
    client = _client(tmp_path, monkeypatch)
    phantom = tmp_path / "workspaces" / "books" / "phantom-b26"
    response = client.get("/api/novel-console/progress", params={
        "workflow_id": "xs2-novel-flywheel", "workspace": str(phantom)})
    assert response.status_code == 404, response.text
    assert "不存在" in response.json()["detail"]
    assert not phantom.exists()


def test_console_get_progress_missing_book_relative_form_404_without_mkdir(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    phantom = str(tmp_path / "workspaces" / "books" / "phantom-rel")
    response = client.get("/api/novel-console/progress", params={
        "workflow_id": "xs2-novel-flywheel", "workspace": phantom})
    assert response.status_code == 404, response.text
    assert not (tmp_path / "workspaces" / "books" / "phantom-rel").exists()


def test_console_sync_history_phantom_workspace_404_without_mkdir(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    phantom = tmp_path / "workspaces" / "books" / "phantom-sync"
    response = client.post("/api/novel-console/progress/sync-history", json={
        "workflow_id": "xs2-novel-flywheel", "workspace": str(phantom)})
    assert response.status_code == 404, response.text
    assert "作品尚未保存" in response.json()["detail"]
    assert not phantom.exists()


def test_console_delete_project_phantom_workspace_no_mkdir(tmp_path, monkeypatch):
    """DELETE 对不存在的书保持既有 200 成功契约，但不再先建后删。"""
    client = _client(tmp_path, monkeypatch)
    phantom = tmp_path / "workspaces" / "books" / "phantom-del"
    response = client.delete("/api/novel-console/projects", params={
        "workflow_id": "xs2-novel-flywheel", "workspace": str(phantom)})
    assert response.status_code == 200, response.text
    assert not phantom.exists()


def test_console_created_book_progress_still_200(tmp_path, monkeypatch):
    """写路径语义不变：PUT 建书后 GET progress 正常返回（不因 404 化而破坏）。"""
    client = _client(tmp_path, monkeypatch)
    book = str(tmp_path / "workspaces" / "books" / "b2")
    saved = client.put("/api/novel-console/projects", json={
        "workflow_id": "xs2-novel-flywheel", "workspace": book,
        "state": {"title": "x", "mode": "short",
                  "values": {"chapter_number": "1"}, "_revision": 0}})
    assert saved.status_code == 200, saved.text
    assert (tmp_path / "workspaces" / "books" / "b2").is_dir()
    progress = client.get("/api/novel-console/progress", params={
        "workflow_id": "xs2-novel-flywheel", "workspace": book})
    assert progress.status_code == 200, progress.text
    assert progress.json()["percent"] == 0


# --------------------------------- R39 B28：workflow 面读端点不再「查询即建目录」

def _workflow_client(workspaces: WorkspaceManager,
                     task: SimpleNamespace | None = None) -> TestClient:
    """workflow_routes 测试客户端：真实解析器 + stub 任务存储。

    B27 纪律审计：本节用例全部只读（无 PUT/POST/任务落盘），workflow_routes
    的模块级路径常量（SESSIONS_DIR/WORKFLOWS_DIR）不被触达，_load_task 为
    stub，不会写真实 data/ 下任何文件。
    """
    from src.web import workflow_routes

    app = FastAPI()
    app.include_router(workflow_routes.router)
    app.state.workflow_manager = SimpleNamespace(
        _ws_manager=workspaces,
        _load_task=lambda workflow_id, task_id: task,
    )
    with TestClient(app) as test_client:
        return test_client


def test_workspace_files_phantom_404_without_mkdir(roots):
    """修复前实测：GET workspace-files 对幻影工作区 200+空列表 且静默建目录
    （真实数据里 4 个 reference-jobs/job-* 残留的根因——资料蒸馏页每次打开
    都会以新 job-<时间戳> 工作区调本端点）；修复后诚实 404、零目录副作用。"""
    _, _, manager = roots
    phantom = str(manager.base_dir / "books" / "phantom-wf28")
    with _workflow_client(manager) as client:
        response = client.get("/api/workflows/workspace-files", params={
            "workflow_id": "xs2-novel-flywheel-build", "workspace": phantom})
    assert response.status_code == 404, response.text
    assert "作品工作区不存在" in response.json()["detail"]
    assert not Path(phantom).exists()


def test_workspace_files_phantom_relative_form_404_without_mkdir(roots):
    project_root, _, manager = roots
    with _workflow_client(manager) as client:
        response = client.get("/api/workflows/workspace-files", params={
            "workflow_id": "xs2-novel-flywheel-build",
            "workspace": "data/workspaces/books/phantom-wf28-rel"})
    assert response.status_code == 404, response.text
    assert not (project_root / "data/workspaces/books/phantom-wf28-rel").exists()


def test_workspace_files_existing_book_still_lists(roots):
    """翻转不破坏恢复历史内容：真实存在的书照常 200 列文件。"""
    _, _, manager = roots
    book = manager.base_dir / "books" / "b3-wf28"
    (book / "outline").mkdir(parents=True)
    (book / "outline" / "near_term_outline.md").write_text("大纲", encoding="utf-8")
    with _workflow_client(manager) as client:
        response = client.get("/api/workflows/workspace-files", params={
            "workflow_id": "xs2-novel-flywheel-build", "workspace": str(book)})
    assert response.status_code == 200, response.text
    paths = [item["path"] for item in response.json()["files"]]
    assert "outline/near_term_outline.md" in paths


def test_workspace_file_content_phantom_404_without_mkdir(roots):
    _, _, manager = roots
    phantom = str(manager.base_dir / "books" / "phantom-wf28-c")
    with _workflow_client(manager) as client:
        response = client.get("/api/workflows/workspace-files/content", params={
            "workflow_id": "xs2-novel-flywheel-build", "workspace": phantom,
            "path": "outline/near_term_outline.md"})
    assert response.status_code == 404, response.text
    assert "作品工作区不存在" in response.json()["detail"]
    assert not Path(phantom).exists()


def test_task_workspace_file_deleted_workspace_not_recreated(roots):
    """任务在册但工作区已被外部删除：读产物端点不再重建书目录。"""
    _, _, manager = roots
    book = manager.base_dir / "books" / "b4-wf28"
    book.mkdir(parents=True)
    task = SimpleNamespace(workspace_override=str(book))
    with _workflow_client(manager, task=task) as client:
        shutil.rmtree(book)
        response = client.get(
            "/api/workflows/xs2-novel-flywheel-mvp/tasks/t1/workspace-file",
            params={"path": "story/0001/chapter.md"})
    assert response.status_code == 404, response.text
    assert not book.exists()


def test_get_task_result_and_artifact_read_do_not_recreate_workspace(roots):
    """核心层收口：get_task_result / read_task_artifact 的解析翻转 create=False，
    工作区缺失时产物如实报不存在，且不再作为读副作用重建目录。"""
    from src.workflow.task_queries import TaskQueryMixin

    _, _, manager = roots
    phantom = manager.base_dir / "books" / "phantom-wf28-r"
    queries = TaskQueryMixin.__new__(TaskQueryMixin)
    queries._ws_manager = manager
    queries._load_task = lambda workflow_id, task_id: SimpleNamespace(
        name="t", status="completed", workspace_override=str(phantom),
        started_at=None, completed_at=None, updated_at=None,
        snapshot_definition={"nodes": [{"id": "n1"}]},
        disabled_node_ids=set(),
        node_states={"n1": SimpleNamespace(
            status="completed", summary="", error=None,
            outputs={"_output_file": "story/0001/chapter.md"},
            attempt_count=1, token_usage={})})
    result = queries.get_task_result("wf-wf28", "t1")
    assert result is not None and result["status"] == "completed"
    assert result["progress"] == {"completed": 1, "total": 1}
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["exists"] is False
    assert result["artifacts"][0]["relative_path"].replace("\\", "/") == "story/0001/chapter.md"
    artifact = queries.read_task_artifact("wf-wf28", "t1", "t1:n1:output_file")
    assert artifact is not None and artifact["success"] is False
    assert artifact["error"] == "artifact_missing"
    assert not phantom.exists()
