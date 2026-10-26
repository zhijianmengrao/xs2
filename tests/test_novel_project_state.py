"""Project snapshots must not overwrite newer workflow progress."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from src.web import novel_routes


class NovelProjectStateTests(unittest.TestCase):
    def test_stale_save_is_rejected_and_current_changes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / ".novel-project.json"
            manifest.write_text(json.dumps({"title": "末日", "completed": ["character"]}), encoding="utf-8")
            manager = SimpleNamespace(_ws_manager=SimpleNamespace(
                resolve_workflow_workspace=lambda *args, **kwargs: root,
            ))
            with patch.object(novel_routes, "_ensure_http_mutation_allowed"), \
                 patch.object(novel_routes, "_ensure_workflow_writable", return_value=manager), \
                 patch.object(novel_routes, "known_workspaces", return_value=[root]), \
                 patch.object(novel_routes, "_index", root / "index.json"), \
                 patch.object(novel_routes, "WORKFLOW_WORKSPACES_DIR", root):
                def save(state):
                    payload = novel_routes.ProjectSave(workflow_id="test", workspace=str(root), state=state)
                    return asyncio.run(novel_routes.save_project(payload, None))

                result = save({"title": "新名称", "completed": ["character", "story-plan"], "refs": {"character": {"task_id": "new"}}})
                self.assertEqual(result["revision"], 1)
                with self.assertRaises(HTTPException) as failure:
                    save({"title": "旧页面", "completed": [], "refs": {}})
                self.assertEqual(failure.exception.status_code, 409)
                current = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(current["title"], "新名称")
                self.assertEqual(current["completed"], ["character", "story-plan"])
                self.assertEqual(current["refs"]["character"]["task_id"], "new")
                # A deliberate change based on the current revision can still
                # clear task references when a different writing source is used.
                current["refs"] = {}
                self.assertEqual(save(current)["revision"], 2)
                self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["refs"], {})


if __name__ == "__main__":
    unittest.main()
