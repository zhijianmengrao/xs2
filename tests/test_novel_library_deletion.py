"""Shared-library deletion must leave book-owned snapshots usable."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.web import novel_routes
from src.web.novel_library import adopted_writing, fingerprint


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def entry(root, item_id, source="sample"):
    folder = root / item_id
    candidates = {"source": {"text_sha256": source}, "candidates": [
        {"candidate_id": "one", "mechanism": "以人物选择引出代价"}]}
    save(folder / "manifest.json", {"id": item_id, "name": item_id, "source_sha256": source})
    save(folder / "candidates.json", candidates)
    save(folder / "profile.json", {"markdown": "原分析"})
    return candidates


@pytest.fixture
def library_client(tmp_path, monkeypatch):
    library = tmp_path / "library"
    book = tmp_path / "book"
    library.mkdir(); book.mkdir()
    tasks = {}
    manager = SimpleNamespace(
        _ws_manager=SimpleNamespace(resolve_workflow_workspace=lambda _workflow, override=None: Path(override) if override else book),
        get_workflow_execution_policy=lambda _workflow: "public",
        is_workflow_owner_enabled=lambda _workflow: True,
        get_task=lambda _workflow, task_id: tasks.get(task_id),
    )
    app = FastAPI(); app.include_router(novel_routes.router)
    app.state.workflow_manager = manager
    monkeypatch.setattr(novel_routes, "_library_root", library)
    # R37 B24：console 面 workspace 白名单锚在 WORKFLOW_WORKSPACES_DIR 上，
    # publish/delete 等端点带 workspace，临时书目录必须落在被补丁的根之下。
    monkeypatch.setattr(novel_routes, "WORKFLOW_WORKSPACES_DIR", tmp_path)
    with TestClient(app) as client:
        yield client, library, book, tasks, manager


def delete(client, ids):
    return client.post("/api/novel-console/library/delete", json={
        "workflow_id": "test", "library_ids": ids,
    })


def test_batch_physically_deletes_entries_but_preserves_adopted_book(library_client):
    client, library, book, _, _ = library_client
    candidates = entry(library, "first")
    entry(library, "second", "other")
    entry(library, "keep", "third")
    save(book / "learning/candidates.json", candidates)
    blueprint = {"source": candidates["source"], "selected_candidate_ids": ["one"],
                 "mechanisms": candidates["candidates"], "styles": [{"title": "本书风格"}]}
    save(book / "learning/blueprints/v0001.json", blueprint)
    save(book / "learning/active.json", {"blueprint_path": "learning/blueprints/v0001.json",
                                      "blueprint_sha256": fingerprint(blueprint)})
    save(book / "learning/library_refs.json", {"items": ["first"]})
    before = {file.relative_to(book): file.read_bytes() for file in book.rglob("*") if file.is_file()}
    result = delete(client, ["first", "second", "first"]).json()
    assert result == {"success": True, "deleted_ids": ["first", "second"], "missing_ids": [], "failed": []}
    assert not (library / "first").exists() and not (library / "second").exists()
    assert (library / "keep/manifest.json").is_file()
    assert before == {file.relative_to(book): file.read_bytes() for file in book.rglob("*") if file.is_file()}
    assert adopted_writing(book)["selected_candidate_ids"] == ["one"]
    assert [item["id"] for item in client.get("/api/novel-console/library").json()["items"]] == ["keep"]
    assert client.get("/api/novel-console/library/first").status_code == 404
    assert delete(client, ["first"]).json()["missing_ids"] == ["first"]


@pytest.mark.parametrize("invalid", ["..", "../first", "first/..", r"first\..", "FIRST", " first ", "C:drive", "x" * 81])
def test_whole_batch_is_validated_before_any_deletion(library_client, invalid):
    client, library, _, _, _ = library_client
    entry(library, "first")
    response = delete(client, ["first", invalid])
    assert response.status_code == 400
    assert (library / "first/manifest.json").is_file()


def test_unknown_directories_are_not_removed_and_empty_batches_rejected(library_client):
    client, library, _, _, _ = library_client
    entry(library, "first")
    (library / "unrelated").mkdir()
    response = delete(client, ["first", "unrelated"])
    assert response.status_code == 409
    assert (library / "first").is_dir() and (library / "unrelated").is_dir()
    assert delete(client, []).status_code == 422
    assert delete(client, [f"item-{i}" for i in range(201)]).status_code == 422


def test_deletion_path_cannot_resolve_to_another_directory(library_client):
    client, library, book, _, _ = library_client
    entry(library, "first")
    original = Path.resolve
    def resolve(path, *args, **kwargs):
        return book if path == library / "escape" else original(path, *args, **kwargs)
    with patch.object(Path, "resolve", resolve):
        assert delete(client, ["first", "escape"]).status_code == 403
    assert (library / "first").is_dir() and book.is_dir()


def test_file_failure_reports_partial_success_and_can_retry(library_client):
    client, library, _, _, _ = library_client
    entry(library, "first"); entry(library, "locked", "locked-source")
    original = novel_routes.shutil.rmtree
    def remove(path, *args, **kwargs):
        if Path(path).name == "locked": raise PermissionError("in use")
        return original(path, *args, **kwargs)
    with patch.object(novel_routes.shutil, "rmtree", remove):
        result = delete(client, ["first", "locked"]).json()
    assert result["success"] is False and result["deleted_ids"] == ["first"]
    assert result["failed"][0]["id"] == "locked"
    assert (library / "locked/manifest.json").is_file()
    assert delete(client, ["locked"]).json()["deleted_ids"] == ["locked"]


def test_invalid_deletion_record_aborts_before_removing_files(library_client):
    client, library, _, _, _ = library_client
    entry(library, "first")
    (library / ".deleted-sources.json").write_text("{broken", encoding="utf-8")
    assert delete(client, ["first"]).status_code == 409
    assert (library / "first/manifest.json").is_file()


def test_old_automatic_publication_cannot_resurrect_deleted_result(library_client):
    client, library, book, tasks, _ = library_client
    candidates = entry(library, "first")
    save(book / "learning/candidates.json", candidates)
    tasks["old"] = {"status": "completed", "workspace_override": str(book),
                    "completed_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    assert delete(client, ["first"]).json()["deleted_ids"] == ["first"]
    payload = {"workflow_id": "test", "workspace": str(book), "name": "restored",
               "automatic": True, "task_id": "old"}
    for _ in range(2):
        response = client.post("/api/novel-console/library/publish", json=payload)
        assert response.status_code == 200
        assert response.json() == {"item": None, "removed": True}
        assert client.get("/api/novel-console/library").json()["items"] == []
    # A new real analysis and an explicit manual save remain available.
    tasks["new"] = {"status": "completed", "workspace_override": str(book),
                    "completed_at": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()}
    response = client.post("/api/novel-console/library/publish", json={**payload, "task_id": "new"})
    assert response.status_code == 200 and response.json()["item"]["id"] == "restored"
    delete(client, ["restored"])
    manual = {key: value for key, value in payload.items() if key not in ("automatic", "task_id")}
    assert client.post("/api/novel-console/library/publish", json=manual).json()["item"]["id"] == "restored"
    # The old task stays suppressed even after a manual restore.
    assert client.post("/api/novel-console/library/publish", json=payload).json()["removed"] is True


def test_automatic_publication_requires_completed_matching_task(library_client):
    client, library, book, tasks, _ = library_client
    save(book / "learning/candidates.json", entry(library, "first"))
    payload = {"workflow_id": "test", "workspace": str(book), "name": "result", "automatic": True}
    assert client.post("/api/novel-console/library/publish", json=payload).status_code == 409
    tasks["running"] = {"status": "running"}
    assert client.post("/api/novel-console/library/publish", json={**payload, "task_id": "running"}).status_code == 409
    tasks["wrong"] = {"status": "completed", "workspace_override": str(book / "other")}
    assert client.post("/api/novel-console/library/publish", json={**payload, "task_id": "wrong"}).status_code == 409


def test_result_without_source_hash_is_also_protected_from_old_auto_save(library_client):
    client, library, book, tasks, _ = library_client
    candidates = entry(library, "first")
    candidates.pop("source")
    save(library / "first/candidates.json", candidates)
    save(book / "learning/candidates.json", candidates)
    tasks["old"] = {"status": "completed", "workspace_override": str(book),
                    "completed_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    delete(client, ["first"])
    payload = {"workflow_id": "test", "workspace": str(book), "name": "restored",
               "automatic": True, "task_id": "old"}
    assert client.post("/api/novel-console/library/publish", json=payload).json()["removed"] is True


def test_delete_uses_existing_workflow_mutation_policy(library_client):
    client, library, _, _, manager = library_client
    entry(library, "first")
    manager.get_workflow_execution_policy = lambda _workflow: "internal_only"
    assert delete(client, ["first"]).status_code == 403
    assert (library / "first").is_dir()
