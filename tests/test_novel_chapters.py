import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.web import novel_routes
from src.web.novel_chapters import chapter_context
from src.web.novel_repair import digest, repair_context, prepare_repair, preserve_legacy_report


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def task(flows, root, stage, chapter, task_id, status="completed"):
    save(flows / f"xs2-novel-flywheel-{stage}/tasks/{task_id}.json",
         {"task_id":task_id, "status":status, "workspace_override":str(root),
          "created_at":"2026-10-09T10:00:00", "completed_at":"2026-10-09T10:00:01",
          "parameter_values":{"chapter_number":chapter, "human_intent":f"第{chapter}章意图"}})


def body(root, chapter):
    path = root / f"story/{chapter}/chapter.md"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(f"第{chapter}章正文", encoding="utf-8")
    return path


def test_second_chapter_uses_plan_without_inheriting_first_production(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows"
    body(root,"0001"); task(flows,root,"mvp","0001","body-one")
    save(root/"planning/chapters/0002.json",{"goal":"第二章目标"})
    result=chapter_context(root,flows,"0002")
    assert result["values"]["human_intent"] == "第二章目标"
    assert result["refs"] == {} and result["completed"] == []
    assert not (root/"story/0002/chapter.md").exists()


def test_old_chapter_restores_only_its_tasks_and_warns_about_later_chapters(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows"
    body(root,"0001"); body(root,"0002")
    task(flows,root,"mvp","0001","one");task(flows,root,"mvp","0002","two")
    task(flows,root,"polish","0001","polish-one")
    result=chapter_context(root,flows,"0001","repair")
    assert result["refs"]["mvp"]["task_id"]=="one"
    assert "polish" not in result["refs"]
    assert result["later_chapters"]==["0002"]
    assert "不会自动重写" in result["message"]


def test_global_export_is_restored_only_for_a_current_included_chapter(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows"; first=body(root,"0001")
    save(root/"export/manifest.json",{"chapters":[{"chapter":"0001"}]})
    manuscript=root/"export/manuscript.md";manuscript.write_text("第一章成品",encoding="utf-8")
    os.utime(first,(100,100));os.utime(manuscript,(200,200))
    task(flows,root,"export","","export-one")
    assert chapter_context(root,flows,"0001")["refs"]["export"]["task_id"]=="export-one"
    os.utime(first,(300,300))
    assert "export" not in chapter_context(root,flows,"0001")["refs"]


def test_scoped_report_survives_later_evaluation_and_revision_uses_exact_report(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows"
    first=body(root,"0001");body(root,"0002")
    save(root/"story/0001/reader_report.json",{"chapter_number":"0001","body_sha256":digest(first),"verdict":"revise","summary":"第一章问题"})
    save(root/"quality/reader_report.json",{"chapter_number":"0002","verdict":"pass","summary":"第二章已通过"})
    task(flows,root,"reader-sim","0001","first");task(flows,root,"reader-sim","0002","second")
    source=repair_context(root,"0001",flows)
    assert source["report"]["summary"]=="第一章问题"
    assert source["reader_task_id"]=="first"
    before=first.read_bytes()
    result=prepare_repair(root,{"id":"repair-one","status":"completed","purpose":"reader_repair","repair_source":source},"只修改第一章")
    backup=json.loads((root/result["feedback_path"]).parent.joinpath("reader-before.json").read_text(encoding="utf-8"))
    assert backup["summary"]=="第一章问题" and first.read_bytes()==before
    first.write_text("修订稿",encoding="utf-8")
    with pytest.raises(ValueError,match="重新评估"):
        repair_context(root,"0001",flows)


def test_legacy_report_is_migrated_only_when_chapter_and_body_are_verified(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows"
    first=body(root,"0001");task(flows,root,"reader-sim","0001","one")
    save(root/"quality/reader_report.json",{"verdict":"pass","summary":"旧版报告"})
    preserve_legacy_report(root,flows)
    saved=json.loads((root/"story/0001/reader_report.json").read_text(encoding="utf-8"))
    assert saved["chapter_number"]=="0001" and saved["body_sha256"]==digest(first)
    assert repair_context(root,"0001",flows)["report"]["summary"]=="旧版报告"


def test_active_chapter_work_blocks_production_switch(tmp_path):
    root=tmp_path/"book"; flows=tmp_path/"flows";body(root,"0001")
    task(flows,root,"polish","0001","running","running")
    with pytest.raises(ValueError,match="任务正在处理"):
        chapter_context(root,flows,"0002")


def test_chapter_open_route_validates_and_does_not_create_or_overwrite_prose(tmp_path, monkeypatch):
    root=tmp_path/"book";root.mkdir()
    manager=SimpleNamespace(_ws_manager=SimpleNamespace(resolve_workflow_workspace=lambda _workflow,override=None,create=True:Path(override)),
        get_workflow_execution_policy=lambda _workflow:"public",is_workflow_owner_enabled=lambda _workflow:True)
    app=FastAPI();app.include_router(novel_routes.router);app.state.workflow_manager=manager
    monkeypatch.setattr(novel_routes,"DATA_DIR",tmp_path)
    monkeypatch.setattr(novel_routes,"WORKFLOW_WORKSPACES_DIR",tmp_path)
    with TestClient(app) as client:
        payload={"workflow_id":"test","workspace":str(root),"chapter":"0002","action":"write"}
        result=client.post("/api/novel-console/chapters/context",json=payload)
        assert result.status_code==200 and not result.json()["has_body"]
        assert list(root.iterdir())==[]
        assert client.post("/api/novel-console/chapters/context",json={**payload,"chapter":"../2"}).status_code==422
        assert client.post("/api/novel-console/chapters/context",json={**payload,"action":"repair"}).status_code==409
