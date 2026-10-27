import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.web import novel_routes
from src.web.novel_chapters import chapter_context, chapter_removal_preview, remove_chapter


@pytest.fixture
def support():
    path = Path(__file__).resolve().parents[2] / (
        "DeterminFlow-Plugins/plugins/xs2-novel-flywheel/resources/script-library/xs2/story_support/story_support.py")
    spec = importlib.util.spec_from_file_location("removal_story_support", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def book(tmp_path, support):
    root = tmp_path / "book"
    support.write(root, "story/0001/chapter.md", "第一章原稿")
    support.write(root, "story/0002/chapter.md", "第二章原稿")
    support.write(root, "story/0002/reader_report.json", {"chapter_number": "0002", "verdict": "pass"})
    support.write(root, "quality/reader_report.json", {"chapter_number": "0002", "verdict": "pass"})
    support.write(root, "planning/chapters/0002.json", {"goal": "第二章已采用目标", "title": "原有标题"})
    support.write(root, "outline/near_term_outline.md", "### 第1章\n第一章\n### 第2章\n第二章")
    support.write(root, "export/manuscript.md", "第一章原稿\n第二章原稿")
    support.write(root, "export/manifest.json", {"chapter_count": 2})
    support.write(root, ".novel-project.json", {
        "_revision": 4, "title": "本书", "selected": ["method-one"], "selectedStyles": ["style-one"],
        "values": {"chapter_number": "0002", "latest_chapter": "0002", "target_word_count": "3000-4000"},
        "refs": {"build": {"workflow_id": "build", "task_id": "world"}, "mvp": {"task_id": "old"}},
        "completed": ["build", "mvp", "reader-sim", "post-hoc", "export"], "autoNext": True,
    })
    body = root / "story/0001/chapter.md"
    support.write(root, "story/0001/confirmed_state.json", {
        "chapter": "0001", "body_sha256": hashlib.sha256(body.read_bytes()).hexdigest(),
        "source_hashes": {}, "indexes": {"hooks": [{"id": "first-hook"}], "debts": []}})
    return root, tmp_path / "flows"


def perform(root, flows, operation, support, save_json=novel_routes.atomic_json):
    preview = chapter_removal_preview(root, flows, "0002")
    return remove_chapter(root, flows, "0002", operation, preview["body_sha256"],
                          preview["revision"], support, save_json)


def test_delete_moves_actual_chapter_and_export_preserves_book_and_previous_chapter(book, support):
    root, flows = book
    first = (root / "story/0001/chapter.md").read_bytes()
    result = perform(root, flows, "delete", support)
    assert not (root / "story/0002").exists()
    assert not (root / "export/manuscript.md").exists()
    assert not (root / "quality/reader_report.json").exists()
    backup = root / result["backup_path"]
    assert (backup / "story/0002/chapter.md").read_text(encoding="utf-8").strip() == "第二章原稿"
    assert (backup / "story/0002/reader_report.json").is_file()
    assert (backup / "export/manuscript.md").is_file()
    assert (root / "story/0001/chapter.md").read_bytes() == first
    assert (root / "planning/chapters/0002.json").is_file()
    state = result["state"]
    assert state["selected"] == ["method-one"] and state["selectedStyles"] == ["style-one"]
    assert state["values"]["latest_chapter"] == "0001"
    assert state["refs"] == {"build": {"workflow_id": "build", "task_id": "world"}}
    assert state["completed"] == ["build"] and not state["autoNext"]
    assert support.preflight(root, "0003")["reason_code"] == "chapter_missing"


def test_regenerate_keeps_plan_and_cannot_restore_old_completed_tasks(book, support):
    root, flows = book
    support.write(flows, "xs2-novel-flywheel-mvp/tasks/old.json", {
        "task_id": "old", "workspace_override": str(root), "status": "completed",
        "created_at": "2026-10-09T10:00:00", "parameter_values": {"chapter_number": "0002"}})
    result = perform(root, flows, "regenerate", support)
    assert result["state"]["stageId"] == "mvp"
    assert result["state"]["values"]["human_intent"] == "第二章已采用目标"
    context = chapter_context(root, flows, "0002")
    assert context["refs"] == {} and context["completed"] == [] and not context["has_body"]
    support.write(flows, "xs2-novel-flywheel-mvp/tasks/new.json", {
        "task_id": "new", "workspace_override": str(root), "status": "running",
        "created_at": "2099-10-09T10:00:00+08:00", "parameter_values": {"chapter_number": "0002"}})
    with pytest.raises(ValueError, match="正在处理"):
        chapter_context(root, flows, "0002")

@pytest.mark.parametrize("mode,ending_mode,expected", [
    ("short", "continue", "短篇应完成本篇主要冲突"),
    ("serial", "book_final", "本章是全书终章"),
    ("serial", "continue", "普通长篇章节仅完成局部目标"),
])
def test_regeneration_preserves_pov_and_appropriate_ending(book, support, mode, ending_mode, expected):
    root, flows = book
    state = json.loads((root / ".novel-project.json").read_text(encoding="utf-8"))
    state["mode"] = mode
    state["values"].update(narrative_pov="first_person", chapter_ending_mode=ending_mode)
    novel_routes.atomic_json(root / ".novel-project.json", state)
    result = perform(root, flows, "regenerate", support)
    instructions = (root / result["state"]["values"]["author_feedback_file"]).read_text(encoding="utf-8")
    assert "叙事视角：first_person" in instructions
    assert expected in instructions
    assert "不进入配角内心" not in instructions


def test_later_prose_is_kept_but_old_production_tasks_are_invalidated(book, support):
    root, flows = book
    support.write(root, "story/0003/chapter.md", "第三章保留")
    support.write(flows, "xs2-novel-flywheel-reader-sim/tasks/three.json", {
        "task_id": "three", "workspace_override": str(root), "status": "completed",
        "created_at": "2026-10-09T10:00:00+08:00", "parameter_values": {"chapter_number": "0003"}})
    result = perform(root, flows, "delete", support)
    assert result["later_chapters"] == ["0003"]
    assert (root / "story/0003/chapter.md").read_text(encoding="utf-8").strip() == "第三章保留"
    assert "reader-sim" not in chapter_context(root, flows, "0003")["refs"]


def test_changed_body_or_revision_never_deletes_the_chapter(book, support):
    root, flows = book
    preview = chapter_removal_preview(root, flows, "0002")
    for sha, revision in [("0" * 64, preview["revision"]), (preview["body_sha256"], 3)]:
        with pytest.raises(ValueError, match="已更新"):
            remove_chapter(root, flows, "0002", "delete", sha, revision, support, novel_routes.atomic_json)
        assert (root / "story/0002/chapter.md").is_file()
        assert (root / "export/manuscript.md").is_file()


def test_failed_archive_update_restores_actual_chapter_export_and_state(book, support, monkeypatch):
    root, flows = book
    before = (root / ".novel-project.json").read_bytes()
    monkeypatch.setattr(support, "refresh_archive", lambda root: (_ for _ in ()).throw(OSError("磁盘异常")))
    with pytest.raises(OSError, match="磁盘异常"):
        perform(root, flows, "delete", support)
    assert (root / ".novel-project.json").read_bytes() == before
    assert (root / "story/0002/chapter.md").is_file()
    assert (root / "export/manuscript.md").is_file()
    assert not (root / "archive/chapter_resets/0002.json").exists()


def test_stale_plan_prevents_regeneration_before_any_files_are_moved(book, support):
    root, flows = book
    support.write(root, "planning/chapters/0002.json", {"source_hashes": {"meta/style_profile.md": "old"}})
    with pytest.raises(ValueError, match="重新生成并采用"):
        perform(root, flows, "regenerate", support)
    assert (root / "story/0002/chapter.md").is_file()


def test_route_exposes_preview_and_requires_matching_confirmation(book, support, monkeypatch, tmp_path):
    root, flows = book
    app = FastAPI()
    app.include_router(novel_routes.router)
    app.state.workflow_manager = SimpleNamespace(
        _ws_manager=SimpleNamespace(resolve_workflow_workspace=lambda _workflow, override=None, create=True: Path(override)),
        get_workflow_execution_policy=lambda _workflow: "public", is_workflow_owner_enabled=lambda _workflow: True)
    monkeypatch.setattr(novel_routes, "DATA_DIR", tmp_path)
    monkeypatch.setattr(novel_routes, "WORKFLOW_WORKSPACES_DIR", tmp_path)
    monkeypatch.setattr(novel_routes, "story_support", lambda required=False: support)
    query = {"workflow_id": "test", "workspace": str(root), "chapter": "0002"}
    with TestClient(app) as client:
        preview = client.get("/api/novel-console/chapters/removal-preview", params=query)
        assert preview.status_code == 200
        payload = {**query, "operation": "delete", "expected_sha256": preview.json()["body_sha256"],
                   "expected_revision": preview.json()["revision"]}
        assert client.post("/api/novel-console/chapters/remove", json={**payload, "expected_sha256": "0" * 64}).status_code == 409
        assert client.post("/api/novel-console/chapters/remove", json=payload).status_code == 200
        assert not (root / "story/0002").exists()
        assert client.post("/api/novel-console/chapters/remove", json={**payload, "chapter": "../2"}).status_code == 422
