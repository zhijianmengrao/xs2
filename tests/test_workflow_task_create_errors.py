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
