"""Regression tests for the humanware (character voice) API surface.

Covers:
- workspace 路径穿越防护（含非法 id）
- 不存在的 workspace 返回 404（而非被吞成 500）
- voice-file 保存/读取往返
- humanware CLI 缺失时返回 501（业务未就绪），不是误导性 500
- CLI 可用时的正常生成路径
- 全应用 OpenAPI operationId 唯一（防 GET/HEAD 双方法重复 id 回归）
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.web import humanware_routes
from src.web import novel_routes


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(humanware_routes.router)
    app.include_router(novel_routes.router)
    return app


class HumanwareRoutesTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.books_root = Path(self._tmp.name) / "books"
        self.books_root.mkdir(parents=True)
        self.workspace = self.books_root / "alpha"
        self.workspace.mkdir()
        # 复用同一线程内资源；monkeypatch 用 try/finally 手动还原
        self._orig_books_root = humanware_routes._WORKSPACE_BOOKS_ROOT
        humanware_routes._WORKSPACE_BOOKS_ROOT = self.books_root

    def tearDown(self):
        humanware_routes._WORKSPACE_BOOKS_ROOT = self._orig_books_root
        self._tmp.cleanup()

    def _client(self):
        return TestClient(_app())

    def test_status_missing_workspace_returns_404_not_500(self):
        with self._client() as client:
            response = client.get("/api/humanware/status/ghost")
            self.assertEqual(response.status_code, 404)

    def test_voice_file_missing_workspace_returns_404_not_500(self):
        with self._client() as client:
            response = client.get("/api/humanware/voice-file/ghost")
            self.assertEqual(response.status_code, 404)

    def test_traversal_workspace_id_rejected(self):
        with self._client() as client:
            # URL 路径参数：斜杠/点段可能被路由归一化（404），也可能到达防护函数（400）。
            # 两种都安全，关键是绝不能按合法工作区执行（2xx）或落到 books 之外。
            for bad in ("..", "../..", "a/b", "..\\..", "data/workspaces/books/../../../config"):
                response = client.get(f"/api/humanware/status/{bad}")
                self.assertIn(response.status_code, (400, 404), bad)
            # body 层（不经 URL 归一化）直接到达防护函数：非法 id 必须 400
            for bad in ("..", "../..", "a/b", r"..\..", "../../../config", ".", "%41"):
                body_response = client.post(
                    "/api/humanware/generate-voice-file",
                    json={"workspace_id": bad, "from_profiles": True},
                )
                self.assertEqual(body_response.status_code, 400, bad)

    def test_save_then_read_voice_file_roundtrip(self):
        with self._client() as client:
            payload = {"workspace_id": "alpha", "content": "## 主角\n\n声音定义。\n"}
            saved = client.put("/api/humanware/voice-file/alpha", json=payload)
            self.assertEqual(saved.status_code, 200, saved.text)
            self.assertTrue(saved.json()["status"] == "success")
            self.assertTrue((self.workspace / "meta" / "character_voice.md").is_file())

            loaded = client.get("/api/humanware/voice-file/alpha")
            self.assertEqual(loaded.status_code, 200)
            self.assertEqual(loaded.json()["status"], "success")
            self.assertIn("主角", loaded.json()["content"])

            status = client.get("/api/humanware/status/alpha")
            self.assertEqual(status.status_code, 200)
            self.assertTrue(status.json()["voice_file_exists"])
            self.assertTrue(status.json()["humanware_enabled"])
            self.assertEqual(status.json()["character_count"], 1)

    def test_full_relative_path_workspace_also_accepted(self):
        with self._client() as client:
            full = "data/workspaces/books/alpha"
            response = client.get(f"/api/humanware/status/{full.split('/')[-1]}")
            self.assertEqual(response.status_code, 200)
            # 显式模拟 CLI 未部署：完整相对路径能通过校验并到达 CLI 调用点
            def _missing_cli():
                raise HTTPException(status_code=501, detail="Humanware CLI 未部署（测试模拟）")
            with patch.object(humanware_routes, "_get_humanware_cli_path", side_effect=_missing_cli):
                body = client.post(
                    "/api/humanware/generate-voice-file",
                    json={"workspace_id": full, "from_profiles": True},
                )
            # 路径解析通过后由 CLI 缺失返回 501（业务未就绪），而非 400/500
            self.assertEqual(body.status_code, 501, body.text)

    def test_generate_reports_501_when_cli_absent(self):
        with self._client() as client:
            def _missing_cli():
                raise HTTPException(status_code=501, detail="Humanware CLI 未部署（测试模拟）")
            with patch.object(humanware_routes, "_get_humanware_cli_path", side_effect=_missing_cli):
                response = client.post(
                    "/api/humanware/generate-voice-file",
                    json={"workspace_id": "alpha", "from_profiles": True},
                )
            self.assertEqual(response.status_code, 501, response.text)
            self.assertIn("humanware", response.json()["detail"].lower())


class HumanwareCliAvailableTests(unittest.TestCase):
    """CLI 脚本存在时的正常路径（用临时假 CLI 隔离）。"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.books_root = root / "books"
        self.books_root.mkdir()
        self.workspace = self.books_root / "alpha"
        self.workspace.mkdir()
        fake_cli = root / "humanware_cli.py"
        fake_cli.write_text(
            "import json, sys\n"
            "cmd = sys.argv[1]\n"
            "print(json.dumps({'status': 'success', 'message': 'ok',\n"
            "                   'character_count': 3 if cmd == 'generate-voice' else 0,\n"
            "                   'total_score': 88, 'grade': 'B',\n"
            "                   'summary': 'ok', 'detailed_scores': {},\n"
            "                   'issues': [], 'recommendation': ''}))\n",
            encoding="utf-8",
        )
        self._orig_books_root = humanware_routes._WORKSPACE_BOOKS_ROOT
        self._orig_cli = humanware_routes._get_humanware_cli_path
        humanware_routes._WORKSPACE_BOOKS_ROOT = self.books_root
        humanware_routes._get_humanware_cli_path = lambda: fake_cli

    def tearDown(self):
        humanware_routes._WORKSPACE_BOOKS_ROOT = self._orig_books_root
        humanware_routes._get_humanware_cli_path = self._orig_cli
        self._tmp.cleanup()

    def test_generate_voice_file_success(self):
        # 提供 character_profiles.md 让生成有来源
        profiles = self.workspace / "meta" / "character_profiles.md"
        profiles.parent.mkdir(parents=True)
        profiles.write_text("## 张三\n## 李四\n## 王五\n", encoding="utf-8")
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/generate-voice-file",
                json={"workspace_id": "alpha", "from_profiles": True},
            )
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["character_count"], 3)

    def test_score_content_propagates_business_result(self):
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/score-content",
                json={"workspace_id": "alpha", "character": "张三", "content": "你好。"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["total_score"], 88)


class OpenApiOperationIdUniquenessTests(unittest.TestCase):
    def test_no_duplicate_operation_ids_in_openapi(self):
        with TestClient(_app()) as client:
            schema = client.get("/openapi.json").json()
        ids = {}
        duplicates = []
        for path, methods in schema.get("paths", {}).items():
            for method, operation in methods.items():
                if method not in ("get", "post", "put", "delete", "patch", "head", "options", "trace"):
                    continue
                operation_id = operation.get("operationId")
                if operation_id in ids:
                    duplicates.append((operation_id, ids[operation_id], path, method))
                ids[operation_id] = (path, method)
        self.assertEqual(duplicates, [], f"重复 operationId: {duplicates}")
        # download 的 GET/HEAD 现在各自有独立 operationId
        download = schema["paths"]["/api/novel-console/export/download"]
        self.assertNotEqual(
            download["get"]["operationId"],
            download["head"]["operationId"],
        )


if __name__ == "__main__":
    unittest.main()