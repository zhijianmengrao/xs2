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


class HumanwareContractHardeningTests(unittest.TestCase):
    """Round 15：业务错误码透传与超长内容（argv 限制）回归。"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.books_root = root / "books"
        self.books_root.mkdir()
        self.workspace = self.books_root / "alpha"
        self.workspace.mkdir()
        # 假 CLI：模拟真实 CLI 的关键行为——
        # - check-dialogue 未知角色 → error JSON + code 409（exit 0）
        # - score-text/check-dialogue 内容参数为 "-" 时从 stdin 读 UTF-8
        # - 成功时回显 content_len 供断言 stdin 往返完整性
        fake_cli = root / "humanware_cli.py"
        fake_cli.write_text(
            "import json, sys\n"
            "cmd = sys.argv[1]\n"
            "def read_arg(value):\n"
            "    if value == '-':\n"
            "        return sys.stdin.buffer.read().decode('utf-8')\n"
            "    return value\n"
            "if cmd == 'check-dialogue':\n"
            "    character = sys.argv[3]\n"
            "    if character == 'missing':\n"
            "        print(json.dumps({'status': 'error', 'message': '角色未定义', 'code': 409}))\n"
            "    else:\n"
            "        dialogue = read_arg(sys.argv[4])\n"
            "        print(json.dumps({'status': 'success', 'matches': True, 'character': character,\n"
            "                           'violations': [], 'suggestion': '', 'dialogue_len': len(dialogue)}))\n"
            "elif cmd == 'score-text':\n"
            "    content = read_arg(sys.argv[4])\n"
            "    print(json.dumps({'status': 'success', 'total_score': 88, 'grade': 'B', 'summary': 'ok',\n"
            "                       'detailed_scores': {}, 'issues': [], 'recommendation': '',\n"
            "                       'content_len': len(content)}))\n"
            "else:\n"
            "    print(json.dumps({'status': 'success', 'message': 'ok', 'character_count': 2}))\n",
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

    def test_check_dialogue_business_error_propagates_code(self):
        # CLI 契约：未知角色 → error JSON code=409；路由应透传 409 而非 500
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/check-dialogue",
                json={"workspace_id": "alpha", "character": "missing", "dialogue": "你好。"},
            )
            self.assertEqual(response.status_code, 409, response.text)

    def test_score_content_large_content_via_stdin(self):
        # Windows CreateProcess 命令行上限约 32,767 UTF-16 单元；42,000 字符必须改走 stdin
        content = "结论已经给出，方案可以执行。" * 3000  # 42,000 字符 > 上限
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/score-content",
                json={"workspace_id": "alpha", "character": "张三", "content": content},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["content_len"], len(content))

    def test_check_dialogue_long_dialogue_via_stdin(self):
        dialogue = "此事罢了，不必再提。" * 5000  # 50,000 字符 > 上限
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/check-dialogue",
                json={"workspace_id": "alpha", "character": "张三", "dialogue": dialogue},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["dialogue_len"], len(dialogue))

    def test_score_content_small_content_still_argv(self):
        # 短内容保持 argv 路径（不回归既有行为）
        with TestClient(_app()) as client:
            response = client.post(
                "/api/humanware/score-content",
                json={"workspace_id": "alpha", "character": "张三", "content": "你好。"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["content_len"], 3)

    def test_voice_file_save_url_id_wins_over_body(self):
        # URL 路径参数优先；body workspace_id 不一致时以 URL 为准（beta 不存在也不得 404）
        with TestClient(_app()) as client:
            response = client.put(
                "/api/humanware/voice-file/alpha",
                json={"workspace_id": "beta", "content": "## 主角\n"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue((self.workspace / "meta" / "character_voice.md").is_file())

    def test_cli_timeout_maps_to_500_error_payload(self):
        import subprocess as sp

        def _boom(*args, **kwargs):
            raise sp.TimeoutExpired(cmd="humanware", timeout=120)

        with patch.object(humanware_routes.subprocess, "run", side_effect=_boom), \
                patch.object(humanware_routes, "_get_humanware_cli_path", return_value=Path("fake.py")):
            result = humanware_routes._run_humanware_command_blocking("generate-voice", "ws")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["code"], 500)


class HumanwareInputFuzzTests(unittest.TestCase):
    """Round 16：路径/输入安全扩展 fuzz + stdin 阈值可配置回归。

    覆盖 R16 两缺陷的红灯：
    - B1 character/dialogue/chapter_file 含 NUL → 应 400（修复前 500 embedded null character）
    - B2 workspace_id 为 Windows 保留设备名（NUL/CON/COM1…）→ 应 400（修复前 NUL 可 200）
    """

    def setUp(self):
        import os
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.books_root = root / "books"
        self.books_root.mkdir()
        (self.books_root / "alpha").mkdir()
        # 假 CLI 回显内容长度与「是否经 stdin（argv=='-'）」，供阈值断言
        fake_cli = root / "humanware_cli.py"
        fake_cli.write_text(
            "import json, sys\n"
            "def read_arg(v):\n"
            "    if v == '-':\n"
            "        return sys.stdin.buffer.read().decode('utf-8')\n"
            "    return v\n"
            "cmd = sys.argv[1]\n"
            "if cmd == 'score-text':\n"
            "    print(json.dumps({'status': 'success', 'total_score': 88, 'grade': 'B', 'summary': 'ok',\n"
            "        'detailed_scores': {}, 'issues': [], 'recommendation': '',\n"
            "        'argv_is_dash': sys.argv[4] == '-', 'content_len': len(read_arg(sys.argv[4]))}))\n"
            "elif cmd == 'check-dialogue':\n"
            "    print(json.dumps({'status': 'success', 'matches': True, 'character': sys.argv[3],\n"
            "        'violations': [], 'suggestion': '', 'argv_is_dash': sys.argv[4] == '-',\n"
            "        'dialogue_len': len(read_arg(sys.argv[4]))}))\n"
            "elif cmd == 'score-chapter':\n"
            "    print(json.dumps({'status': 'success', 'total_score': 88, 'grade': 'B', 'summary': 'ok',\n"
            "        'detailed_scores': {}, 'issues': [], 'recommendation': '', 'dialogues_scored': 0,\n"
            "        'chapter_file': sys.argv[3]}))\n"
            "else:\n"
            "    print(json.dumps({'status': 'success', 'message': 'ok', 'character_count': 2}))\n",
            encoding="utf-8",
        )
        self._orig_books_root = humanware_routes._WORKSPACE_BOOKS_ROOT
        self._orig_cli = humanware_routes._get_humanware_cli_path
        humanware_routes._WORKSPACE_BOOKS_ROOT = self.books_root
        humanware_routes._get_humanware_cli_path = lambda: fake_cli
        # 阈值环境变量用例自管理；setUp 保证基线干净
        self._env_key = "DETERMINFLOW_HUMANWARE_STDIN_ARG_THRESHOLD"
        self._saved_env = os.environ.pop(self._env_key, None)

    def tearDown(self):
        import os

        humanware_routes._WORKSPACE_BOOKS_ROOT = self._orig_books_root
        humanware_routes._get_humanware_cli_path = self._orig_cli
        if self._saved_env is not None:
            os.environ[self._env_key] = self._saved_env
        self._tmp.cleanup()

    def test_body_workspace_id_fuzz_all_rejected_400(self):
        # URL 编码字面量、全角点、NUL、混合反斜杠段、非法首字符——body 层必须 400，不得 2xx/500
        import os

        bad_ids = [
            "%2e%2e", "．．/", "..\\..\\..", "data/workspaces/books/..%2f..",
            "x" + chr(0) + "y", "-leading", ".dot", "space id",
        ]
        for bad in bad_ids:
            with self._client() as client:
                response = client.post(
                    "/api/humanware/generate-voice-file",
                    json={"workspace_id": bad, "from_profiles": True},
                )
            self.assertEqual(response.status_code, 400, bad)
        # 合法模式但不存在：404 是正确语义，关键是不得 2xx 命中其他工作区。
        # 注意 "tail." 一类尾随点输入已改判 400（见 test_workspace_id_trailing_dot…），
        # 因为 Windows 会剥离尾随点、让它成为真实工作区的别名。
        for missing in ("ghost",):
            with self._client() as client:
                response = client.post(
                    "/api/humanware/generate-voice-file",
                    json={"workspace_id": missing, "from_profiles": True},
                )
            self.assertEqual(response.status_code, 404, missing)

    def test_workspace_id_trailing_dot_alias_rejected_400(self):
        # B3（R17）：Windows 解析路径时剥离尾随点，使 "alpha." 成为真实工作区
        # "alpha" 的别名并返回 200（修复前实测）；POSIX 上是两个不同名字。
        # 尾随点名字无法稳定按名读回，必须 400 而不是别名命中。
        import os

        if os.name != "nt":
            self.skipTest("尾随点别名仅在 Windows 文件系统语义下成立")
        for alias in ("alpha.", "alpha..", "alpha..."):
            with self._client() as client:
                response = client.get(f"/api/humanware/status/{alias}")
            self.assertEqual(response.status_code, 400, alias)
        # 真实名字仍正常 200（未被新规则误伤）；名字中间的点是合法的
        with self._client() as client:
            self.assertEqual(client.get("/api/humanware/status/alpha").status_code, 200)
            self.assertEqual(client.get("/api/humanware/status/alpha.md").status_code, 404)

    def test_reserved_device_alias_variants_rejected_400(self):
        # B2 变体补齐（R17）：设备名 + 尾随点等组合此前依赖 split(".")[0] 判断，
        # 统一交 path_guard 后按「首段是否保留名」判定，覆盖 CONIN$/带扩展名变体。
        import os

        if os.name != "nt":
            self.skipTest("Windows 保留设备名仅在 nt 平台特判")
        for bad in ("NUL.", "nul.", "COM1.", "CON.txt", "LPT9.", "aux.txt.bak"):
            with self._client() as client:
                response = client.get(f"/api/humanware/status/{bad}")
            self.assertEqual(response.status_code, 400, bad)

    def test_windows_reserved_workspace_id_rejected_400(self):
        # B2：保留设备名（含大小写/带扩展名变体）必须 400；修复前 NUL 因 exists() 恒真而 200
        import os

        if os.name != "nt":
            self.skipTest("Windows 保留设备名仅在 nt 平台特判")
        for bad in ("NUL", "nul", "Con", "NUL.txt", "COM1", "LPT9", "aux"):
            with self._client() as client:
                status_resp = client.get(f"/api/humanware/status/{bad}")
                voice_resp = client.get(f"/api/humanware/voice-file/{bad}")
            self.assertEqual(status_resp.status_code, 400, bad)
            self.assertEqual(voice_resp.status_code, 400, bad)

    def test_character_with_nul_rejected_400(self):
        # B1：character 含 NUL → subprocess 抛 ValueError → 应 400（修复前 500）
        with self._client() as client:
            score = client.post(
                "/api/humanware/score-content",
                json={"workspace_id": "alpha", "character": "张三" + chr(0), "content": "你好。"},
            )
            check = client.post(
                "/api/humanware/check-dialogue",
                json={"workspace_id": "alpha", "character": "张三" + chr(0), "dialogue": "你好。"},
            )
        self.assertEqual(score.status_code, 400, score.text)
        self.assertEqual(check.status_code, 400, check.text)

    def test_dialogue_and_chapter_file_with_nul_rejected_400(self):
        with self._client() as client:
            dialogue = client.post(
                "/api/humanware/check-dialogue",
                json={"workspace_id": "alpha", "character": "张三", "dialogue": "你好。" + chr(0)},
            )
            chapter = client.post(
                "/api/humanware/score-chapter",
                json={"workspace_id": "alpha", "chapter_file": "story/0001" + chr(0) + "/chapter.md"},
            )
        self.assertEqual(dialogue.status_code, 400, dialogue.text)
        self.assertEqual(chapter.status_code, 400, chapter.text)

    def test_stdin_threshold_env_override(self):
        # P2：阈值可经环境变量下调；介于默认 8192 与新阈值之间的内容改走 stdin
        import os

        os.environ[self._env_key] = "10"
        try:
            with self._client() as client:
                response = client.post(
                    "/api/humanware/score-content",
                    json={"workspace_id": "alpha", "character": "张三", "content": "字" * 12},
                )
        finally:
            os.environ.pop(self._env_key, None)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["argv_is_dash"], "阈值=10 时 12 字符内容应经 stdin（argv 为 '-'）")
        self.assertEqual(body["content_len"], 12)

    def test_stdin_threshold_default_when_unset(self):
        # 未设置环境变量：默认 8192，12 字符短内容仍走 argv（既有行为不回归）
        import os

        os.environ.pop(self._env_key, None)
        with self._client() as client:
            response = client.post(
                "/api/humanware/score-content",
                json={"workspace_id": "alpha", "character": "张三", "content": "字" * 12},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["argv_is_dash"])

    def test_stdin_threshold_invalid_value_falls_back(self):
        # 非整数/非正值：回退默认 8192 并记录警告（不得让请求 500）
        import os

        for raw in ("abc", "-5", "0"):
            os.environ[self._env_key] = raw
            try:
                with self._client() as client:
                    response = client.post(
                        "/api/humanware/score-content",
                        json={"workspace_id": "alpha", "character": "张三", "content": "字" * 12},
                    )
            finally:
                os.environ.pop(self._env_key, None)
            self.assertEqual(response.status_code, 200, raw)
            self.assertFalse(response.json()["argv_is_dash"], raw)

    def _client(self):
        return TestClient(_app())


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