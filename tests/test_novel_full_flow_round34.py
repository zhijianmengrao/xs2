"""R34: 小说创作全流程确定性回归（无 LLM 依赖）。

覆盖创作主链：建档 → 分章上下文 → 正文 → 读者报告 → 返修 → 删章 → 进度/导出，
以及边界（路径逃逸/设备名/超长/脏 JSON）与异常（并发写 409、修订号冲突）语义。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web import novel_routes


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeWorkspaces:
    def __init__(self, root):
        self.root = root

    def resolve_workflow_workspace(self, workflow_id, override=None):
        target = self.root if override else self.root / "default-ws"
        target.mkdir(parents=True, exist_ok=True)
        return target


class FakeManager:
    def __init__(self, root):
        self._ws_manager = FakeWorkspaces(root)
        self.tasks = []

    def is_workflow_owner_enabled(self, workflow_id):
        return True

    def get_workflow_execution_policy(self, workflow_id):
        return "public"

    def list_all_tasks(self, page=1, page_size=2000):
        return {"tasks": self.tasks}


@pytest.fixture()
def flows(tmp_path):
    return tmp_path / "flows"


@pytest.fixture()
def book(tmp_path):
    root = tmp_path / "book"
    save(root / ".novel-project.json",
         {"values": {"chapter_number": "1"}, "_revision": 1, "mode": "serial"})
    return root


@pytest.fixture()
def client(book, flows):
    app = FastAPI()
    app.include_router(novel_routes.router)
    app.state.workflow_manager = FakeManager(book)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def patch_workflows_dir(flows, monkeypatch):
    # 路由内部统一使用 DATA_DIR / 'workflows'；把它指到临时目录。
    # known_workspaces() 走 WORKFLOW_WORKSPACES_DIR，也必须隔离，
    # 否则 /projects 会扫到真实 data/workspaces 与上一轮 pytest 残留目录。
    monkeypatch.setattr(novel_routes, "DATA_DIR", flows)
    monkeypatch.setattr(novel_routes, "WORKFLOW_WORKSPACES_DIR", flows.parent)
    monkeypatch.setattr(novel_routes, "_index", flows.parent / "workspaces.json")
    return flows


def task_json(flows, root, stage, chapter, task_id, status="completed", **extra):
    # 路由统一以 DATA_DIR / "workflows" 作为 workflows_dir（DATA_DIR 已被指向 flows）。
    save(flows / "workflows" / f"xs2-novel-flywheel-{stage}/tasks/{task_id}.json",
         {"task_id": task_id, "status": status, "workspace_override": str(root),
          "created_at": "2026-10-09T10:00:00", "completed_at": "2026-10-09T10:00:01",
          "parameter_values": {"chapter_number": chapter, "human_intent": f"第{chapter}章意图"}, **extra})


def write_body(root, chapter, text=None):
    path = root / f"story/{chapter}/chapter.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text is not None else f"第{chapter}章正文", encoding="utf-8")
    return path


# ---------------------------------------------------------------- C1 建档
def test_c1_save_project_creates_manifest_and_revision(client, book):
    response = client.put("/api/novel-console/projects",
                          json={"workflow_id": "xs2-novel-flywheel-mvp",
                                "workspace": str(book),
                                "state": {"title": "测试书", "_revision": 1}})
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    assert json.loads((book / ".novel-project.json").read_text(encoding="utf-8"))["title"] == "测试书"


def test_c2_stale_revision_rejected(client, book):
    payload = {"workflow_id": "xs2-novel-flywheel-mvp", "workspace": str(book),
               "state": {"title": "旧快照", "_revision": 0}}
    response = client.put("/api/novel-console/projects", json=payload)
    assert response.status_code == 409
    assert "刷新" in response.json()["detail"]


def test_c3_oversized_state_rejected(client, book):
    payload = {"workflow_id": "xs2-novel-flywheel-mvp", "workspace": str(book),
               "state": {"blob": "x" * 500_001, "_revision": 1}}
    assert client.put("/api/novel-console/projects", json=payload).status_code == 413


def test_c4_corrupt_manifest_does_not_500(client, book):
    (book / "story/0001").mkdir(parents=True, exist_ok=True)
    (book / ".novel-project.json").write_text("{broken", encoding="utf-8")
    response = client.get("/api/novel-console/projects")
    assert response.status_code == 200
    # 损坏清单不得 500；修复后仍列出该作品并打上 _corrupt 标记（详见 C21）。
    workspaces = [item["workspace"] for item in response.json()["projects"]]
    assert str(book) in workspaces
    assert all(Path_workspace(item).is_relative_to(book.parent) for item in response.json()["projects"])


def Path_workspace(item):
    from pathlib import Path as _Path
    return _Path(item["workspace"])


# --------------------------------------- R34-B1 清单损坏后可恢复（P1）
def _corrupt(book):
    (book / ".novel-project.json").write_text(
        '{"title":"我的书","_rev', encoding="utf-8")


def test_c21_corrupt_manifest_book_still_listed(client, book):
    """清单损坏不等于作品消失：前端靠 /projects 找回当前作品。"""
    write_body(book, "0001")
    _corrupt(book)
    data = client.get("/api/novel-console/projects").json()
    entry = next((item for item in data["projects"] if item["workspace"] == str(book)), None)
    assert entry is not None, "清单损坏后作品从列表消失，前端将无从恢复"
    # 不回退成空对象：要能提示「清单损坏」而不是伪装成新作品
    assert entry["state"].get("_corrupt") is True
    assert entry["progress"]["chapter_count"] == 1


def test_c22_corrupt_manifest_save_is_accepted_with_true_revision(client, book):
    """前端手头的 _revision 是对的（清单只是被截断），保存必须成功。"""
    _corrupt(book)
    response = client.put("/api/novel-console/projects",
                          json={"workflow_id": "xs2-novel-flywheel-mvp",
                                "workspace": str(book),
                                "state": {"title": "我的书", "_revision": 7}})
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 8
    saved = json.loads((book / ".novel-project.json").read_text(encoding="utf-8"))
    assert saved["title"] == "我的书"


def test_c23_corrupt_manifest_is_backed_up_not_silently_dropped(client, book):
    _corrupt(book)
    client.put("/api/novel-console/projects",
               json={"workflow_id": "xs2-novel-flywheel-mvp",
                     "workspace": str(book),
                     "state": {"title": "我的书", "_revision": 3}})
    backups = list(book.glob(".novel-project.json.corrupt-*"))
    assert len(backups) == 1
    assert "我的书" in backups[0].read_text(encoding="utf-8")


def test_c24_stale_revision_still_rejected_when_manifest_is_valid(client, book):
    """恢复逻辑不能放宽正常的并发保护。"""
    save(book / ".novel-project.json", {"title": "v2", "_revision": 5})
    response = client.put("/api/novel-console/projects",
                          json={"workflow_id": "xs2-novel-flywheel-mvp",
                                "workspace": str(book),
                                "state": {"title": "旧", "_revision": 2}})
    assert response.status_code == 409
    assert json.loads((book / ".novel-project.json").read_text(encoding="utf-8"))["title"] == "v2"


# ------------------------------------------------- C5 分章上下文（续写不串章）
def test_c5_second_chapter_does_not_inherit_first_chapter(client, book, flows):
    write_body(book, "0001")
    task_json(flows, book, "mvp", "0001", "body-one")
    save(book / "planning/chapters/0002.json", {"goal": "第二章目标"})
    response = client.get("/api/novel-console/chapters/context",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0002"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["values"]["human_intent"] == "第二章目标"
    assert body["refs"] == {}


@pytest.mark.parametrize("chapter", ["0000", "12", "abcd", "10000", ""])
def test_c6_invalid_chapter_id_is_409(client, book, chapter):
    response = client.get("/api/novel-console/chapters/context",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": chapter})
    assert response.status_code == 409, response.text


def test_c7_running_task_blocks_new_plan(client, book, flows):
    """HTTP 侧也必须被运行中任务拦住（ensure_idle 经 chapter_context 生效）。"""
    write_body(book, "0001")
    task_json(flows, book, "mvp", "0001", "running-task", status="running")
    response = client.get("/api/novel-console/chapters/context",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "正在处理" in response.json()["detail"]


# ---------------------------------------------------------- C8 读者报告/返修
def test_c8_reader_report_requires_body(client, book, flows):
    response = client.get("/api/novel-console/reader-report",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "正文" in response.json()["detail"]


def test_c9_reader_report_requires_report_file(client, book, flows):
    write_body(book, "0001")
    response = client.get("/api/novel-console/reader-report",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "模拟读者" in response.json()["detail"]


def test_c10_reader_report_happy_path(client, book, flows):
    write_body(book, "0001")
    task_json(flows, book, "reader-sim", "0001", "sim-1")
    report = book / "story/0001/reader_report.json"
    save(report, {"chapter_number": "0001", "verdict": "通过", "summary": "结构完整"})
    response = client.get("/api/novel-console/reader-report",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 200, response.text
    assert response.json()["report"]["verdict"] == "通过"


def test_c11_report_from_other_chapter_not_applied(client, book, flows):
    write_body(book, "0001")
    save(book / "story/0001/reader_report.json",
         {"chapter_number": "0002", "verdict": "通过"})
    response = client.get("/api/novel-console/reader-report",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "其他章节" in response.json()["detail"]


def test_c12_body_changed_after_report_is_stale(client, book, flows):
    body = write_body(book, "0001")
    save(book / "story/0001/reader_report.json",
         {"chapter_number": "0001", "verdict": "通过",
          "body_sha256": "0" * 64})
    response = client.get("/api/novel-console/reader-report",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "重新评估" in response.json()["detail"]


def test_c13_repair_apply_unknown_entry_404(client, book):
    response = client.post("/api/novel-console/repair/apply",
                           json={"workflow_id": "xs2-novel-flywheel-mvp",
                                 "workspace": str(book),
                                 "entry_id": "00000000-0000-0000-0000-000000000000",
                                 "plan": "加强冲突"})
    assert response.status_code == 404


# ------------------------------------------------------------- C14 删章
def test_c14_removal_preview_requires_body(client, book, flows):
    response = client.get("/api/novel-console/chapters/removal-preview",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book), "chapter": "0001"})
    assert response.status_code == 409
    assert "无需删除" in response.json()["detail"]


def test_c15_remove_requires_matching_digest(client, book, flows):
    write_body(book, "0001")
    response = client.post("/api/novel-console/chapters/remove",
                           json={"workflow_id": "xs2-novel-flywheel-mvp",
                                 "workspace": str(book), "chapter": "0001",
                                 "operation": "delete",
                                 "expected_sha256": "a" * 64, "expected_revision": 1})
    # 剧情支持脚本未加载时按契约优先报 409（模块缺失而非操作被拒）；
    # 已加载时必须是摘要不匹配的「重新确认」提示。两种都是 409，且正文必须保留。
    assert response.status_code == 409
    assert ("重新确认" in response.json()["detail"]
            or "剧情支持模块尚未加载" in response.json()["detail"])
    assert (book / "story/0001/chapter.md").is_file()


# ------------------------------------------------------ C16/C17 进度与版本
def test_c16_progress_reflects_artifacts(client, book, flows):
    write_body(book, "0001")
    (book / "meta").mkdir(parents=True, exist_ok=True)
    (book / "meta/world_foundation.md").write_text("世界观" * 50, encoding="utf-8")
    # 进度以 .novel-project.json 的 refs 定位任务；只有产物不算完成
    # （防止历史残留正文被误认成本轮成果）。
    save(book / ".novel-project.json",
         {"values": {"chapter_number": "1"}, "_revision": 1, "mode": "serial",
          "refs": {"build": {"workflow_id": "xs2-novel-flywheel-build",
                             "task_id": "build-1"}}})
    task_json(flows, book, "build", "", "build-1")
    response = client.get("/api/novel-console/progress",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": str(book)})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["chapter_count"] == 1
    stages = {item["id"]: item["completed"] for item in data["stages"]}
    assert stages["build"] is True
    assert data["completed_count"] == 1
    assert data["percent"] == round(1 / 9 * 100)

    # 去掉 refs 后同一份产物必须变成「未完成」，证明不会被残留文件骗过。
    save(book / ".novel-project.json",
         {"values": {"chapter_number": "1"}, "_revision": 1, "mode": "serial"})
    again = client.get("/api/novel-console/progress",
                       params={"workflow_id": "xs2-novel-flywheel-mvp",
                               "workspace": str(book)}).json()
    assert {item["id"]: item["completed"] for item in again["stages"]}["build"] is False


def test_c17_progress_rejects_traversal_workspace(client):
    response = client.get("/api/novel-console/progress",
                          params={"workflow_id": "xs2-novel-flywheel-mvp",
                                  "workspace": "../../../etc"})
    # 解析器把逃逸回退到默认路径（不落盘到仓库外）；路由自身不得 500。
    assert response.status_code in (200, 400, 403), response.text


# --------------------------------------------------------------- C18 写文本
def test_c18_write_text_only_reference_and_console_paths(client, book):
    ok = client.put("/api/novel-console/text",
                    json={"workflow_id": "xs2-novel-flywheel-mvp", "workspace": str(book),
                          "path": "references/note.md", "content": "参考"})
    assert ok.status_code == 200, ok.text
    blocked = client.put("/api/novel-console/text",
                         json={"workflow_id": "xs2-novel-flywheel-mvp", "workspace": str(book),
                               "path": "story/0001/chapter.md", "content": "改写"})
    assert blocked.status_code == 403


@pytest.mark.parametrize("relative", ["../escape.md", "references/../../escape.md", "/abs.md",
                                      "C:/Windows/x.md", "references/NUL", "references/tail. "])
def test_c19_write_text_rejects_unsafe_paths(client, book, relative):
    response = client.put("/api/novel-console/text",
                          json={"workflow_id": "xs2-novel-flywheel-mvp", "workspace": str(book),
                                "path": relative, "content": "x"})
    assert response.status_code in (403, 422), (relative, response.text)


# ---------------------------------------------------------------- C20 删除作品
def test_c20_delete_project_refuses_when_running(client, book, flows, tmp_path):
    write_body(book, "0001")
    manager = client.app.state.workflow_manager
    manager.tasks = [{"status": "running", "workspace_override": str(book),
                      "workflow_id": "xs2-novel-flywheel-mvp"}]
    response = client.delete("/api/novel-console/projects",
                             params={"workflow_id": "xs2-novel-flywheel-mvp",
                                     "workspace": str(book)})
    assert response.status_code in (403, 409), response.text
    assert book.exists()
