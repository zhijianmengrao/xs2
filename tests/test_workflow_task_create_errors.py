"""Regression tests for workflow task-creation error mapping (B19).

冻结失败（典型：定义引用不存在的 Script Library 脚本）此前被引擎吞成 None，
HTTP 层误报 404「工作流不存在」；修复后引擎返回结构化 ``task_freeze_failed``，
路由层必须映射为 409 并透出真实原因。
"""
from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web import workflow_routes


class _StubManager:
    def get_workflow_execution_policy(self, workflow_id):
        return "public"

    def create_task(self, workflow_id, **kwargs):
        return {
            "success": False,
            "error": "task_freeze_failed",
            "message": "冻结任务运行身份失败: Script Library 脚本不存在: g/nope",
        }


class WorkflowTaskCreateErrorTests(unittest.TestCase):
    def test_freeze_failure_maps_to_409_with_real_reason(self) -> None:
        app = FastAPI()
        app.include_router(workflow_routes.router)
        app.state.workflow_manager = _StubManager()
        with TestClient(app) as client:
            resp = client.post(
                "/api/workflows/wf-x/tasks",
                json={"parameter_values": {}},
            )
        self.assertEqual(resp.status_code, 409)
        detail = resp.json()["detail"]
        self.assertEqual(detail["code"], "task_freeze_failed")
        self.assertIn("Script Library 脚本不存在", detail["message"])
        self.assertNotEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()


class _UnknownParameterManager:
    def get_workflow_execution_policy(self, workflow_id):
        return "public"

    def create_task(self, workflow_id, **kwargs):
        return {
            "success": False,
            "error": "unknown_parameters",
            "message": "任务参数包含工作流未定义的变量: 题材创意。可用变量: genre, premise",
        }


class WorkflowTaskUnknownParameterTests(unittest.TestCase):
    """B21：传变量显示名而非 key 时曾被报成 404「工作流不存在」。"""

    def test_unknown_parameter_maps_to_422_not_404(self) -> None:
        app = FastAPI()
        app.include_router(workflow_routes.router)
        app.state.workflow_manager = _UnknownParameterManager()
        with TestClient(app) as client:
            resp = client.post(
                "/api/workflows/xs2-novel-flywheel-build/tasks",
                json={"parameter_values": {"题材创意": "x"}},
            )
        self.assertEqual(resp.status_code, 422)
        self.assertNotEqual(resp.status_code, 404)
        detail = resp.json()["detail"]
        self.assertEqual(detail["code"], "unknown_parameters")
        self.assertIn("题材创意", detail["message"])

    def test_manager_reports_unknown_keys_instead_of_returning_none(self) -> None:
        from src.workflow.manager import WorkflowManager
        manager = WorkflowManager.__new__(WorkflowManager)
        manager.is_workflow_owner_enabled = lambda wid: True
        manager._new_task_admission_result = lambda: None
        manager.get_workflow = lambda wid: {
            "definition": {
                "workflow_id": wid, "name": "t", "version": 1, "nodes": [], "edges": [],
                "variables": [
                    {"key": "premise", "name": "题材创意", "type": "textarea",
                     "default": "", "required": True, "source_type": "input"},
                ],
            }
        }
        result = manager.create_task("wf-b21", parameter_values={"题材创意": "x"})
        self.assertIsNotNone(result, "未知参数不再静默返回 None")
        self.assertEqual(result["error"], "unknown_parameters")
        self.assertIn("题材创意", result["message"])
        self.assertIn("premise", result["message"])
