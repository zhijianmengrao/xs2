"""Windows 文件系统名称约束的回归测试（R17 B3/B4）。

两类名称会让存在性校验与写后读在 Windows 上失真：
- 保留设备名（``NUL`` 等）：``Path.exists()`` 恒真、写入内容被静默丢弃且不报错；
- 尾随点（``welcome.``）：Windows 解析时剥离，成为真实工作区的别名。

POSIX 上两者都是合法文件名，故守卫仅在 nt 平台生效。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.web import novel_routes
from src.web.path_guard import unsafe_windows_component, unsafe_windows_path

IS_NT = os.name == "nt"

# 必须被拒绝的名字（nt）。含设备名、带扩展名变体、大小写变体、尾随点变体。
# Windows 对保留名按「首个点之前」规范化，故 aux.txt.bak 也落到 AUX 设备上，
# 与项目既有的 skill_marketplace.bundle._RESERVED 规则一致。
REJECTED = ["NUL", "nul", "NUL.", "NUL.txt", "nul.md", "CON", "Con.", "PRN", "AUX.",
            "COM1", "COM1.log", "LPT9.", "CONIN$", "alpha.", "alpha..", "aux.txt.bak"]
# 必须放行的名字：设备名前缀但非完整段（core/console-NUL）、中间点、非保留编号。
ACCEPTED = ["core", "console-NUL", "alpha.beta", "a.b.c.md", "notes", "chapter-01",
            "NULLU", "COM0", "LPT0", "CLOCKWORK", "nul-x"]


def test_component_matrix_rejects_windows_unsafe_names():
    if not IS_NT:
        pytest.skip("Windows 名称约束仅在 nt 平台生效")
    for name in REJECTED:
        assert unsafe_windows_component(name) is not None, name
    for name in ACCEPTED:
        assert unsafe_windows_component(name) is None, name


def test_device_name_variants_are_caught_with_reason():
    if not IS_NT:
        pytest.skip("Windows 保留设备名仅在 nt 平台特判")
    assert "设备名" in unsafe_windows_component("NUL")
    assert "设备名" in unsafe_windows_component("nul.txt")
    assert "设备名" in unsafe_windows_component("COM1.log")
    assert "剥离" in unsafe_windows_component("alpha.")


def test_relative_path_checks_every_segment():
    if not IS_NT:
        pytest.skip("Windows 保留设备名仅在 nt 平台特判")
    assert unsafe_windows_path("references/NUL") is not None
    assert unsafe_windows_path(r"references\NUL") is not None
    assert unsafe_windows_path("references/foo.") is not None
    assert unsafe_windows_path("meta/console-NUL") is None
    assert unsafe_windows_path("references/outline.md") is None


def test_safe_target_rejects_device_name_and_trailing_dot(tmp_path):
    """B4：`references/NUL` 写入会静默丢失内容，必须在解析前拒绝。"""
    if not IS_NT:
        pytest.skip("Windows 设备名写入语义仅在 nt 平台存在")
    for rel in ("references/NUL", "references/foo.", "story/0001/NUL.md"):
        with pytest.raises(HTTPException) as exc:
            novel_routes.safe_target(tmp_path, rel)
        assert exc.value.status_code == 403, rel
        assert "不安全" in str(exc.value.detail), rel
    # 正常名字不受影响
    assert novel_routes.safe_target(tmp_path, "references/outline.md").is_relative_to(tmp_path)


def test_safe_target_data_loss_would_have_been_silent(tmp_path):
    """证明该拒绝是必要的：设备名写入「成功」但内容丢失（修复前的行为）。"""
    if not IS_NT:
        pytest.skip("Windows 设备名写入语义仅在 nt 平台存在")
    victim = tmp_path / "references" / "NUL"
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text("第一章正文", encoding="utf-8")  # 不抛异常
    assert victim.exists() and not victim.is_file()
    assert victim.read_text(encoding="utf-8") == ""
    assert list(victim.parent.iterdir()) == []


def test_library_path_rejects_reserved_device_name():
    """写法库条目 id 清洗后仍可能得到设备名（"NUL" → "nul"）。

    注：带扩展名的输入会被 ``safe_library_id`` 把 ``.`` 换成 ``-``（"NUL.txt" →
    "nul-txt"），清洗后已是安全名，无需拒绝。
    """
    if not IS_NT:
        pytest.skip("Windows 保留设备名仅在 nt 平台特判")
    for raw in ("NUL", "nul", "COM1", " aux "):
        with pytest.raises(HTTPException) as exc:
            novel_routes.library_path(raw)
        assert exc.value.status_code == 400, raw
    assert novel_routes.library_path("NUL.txt").name == "nul-txt"


@pytest.fixture
def novel_client(tmp_path, monkeypatch):
    library = tmp_path / "library"
    book = tmp_path / "book"
    library.mkdir()
    book.mkdir()
    manager = SimpleNamespace(
        # 与 test_novel_library_deletion 一致：override 非空时按 override 解析，
        # 这样测试才能把「幻影目录」作为工作区根传入。
        _ws_manager=SimpleNamespace(
            resolve_workflow_workspace=lambda _workflow, override=None:
            Path(override) if override else book),
        get_workflow_execution_policy=lambda _workflow: "public",
        is_workflow_owner_enabled=lambda _workflow: True,
    )
    app = FastAPI()
    app.include_router(novel_routes.router)
    app.state.workflow_manager = manager
    monkeypatch.setattr(novel_routes, "_library_root", library)
    with TestClient(app) as client:
        yield client, book


def test_put_text_refuses_device_name_and_keeps_normal_write(novel_client):
    client, book = novel_client
    body = {"workflow_id": "xs2-novel-flywheel", "workspace": str(book),
            "path": "references/NUL", "content": "参考资料正文"}
    if IS_NT:
        response = client.put("/api/novel-console/text", json=body)
        assert response.status_code == 403, response.text
        # 设备名写入不产生任何真实文件（修复前会「保存成功」但内容丢失）
        assert not any(p.name.lower() == "nul" for p in book.rglob("*"))
    body["path"] = "references/outline.md"
    assert client.put("/api/novel-console/text", json=body).status_code == 200
    assert (book / "references/outline.md").read_text(encoding="utf-8") == "参考资料正文"

    # 尾随点同样拒绝（否则写后按原名读回会落到另一个文件）
    if IS_NT:
        body["path"] = "references/outline."
        assert client.put("/api/novel-console/text", json=body).status_code == 403


def test_safe_target_rejects_unsafe_workspace_root(tmp_path):
    """B5：工作区**根**自身是设备名「幻影目录」时必须拒绝。

    Windows 上 `Path("<x>/NUL")` 的 mkdir 静默成功、exists() 恒真，但其下任何真实
    写入都会以 WinError 3 失败（实测未捕获 FileNotFoundError → HTTP 500）。
    """
    if not IS_NT:
        pytest.skip("Windows 设备名语义仅在 nt 平台存在")
    phantom = tmp_path / "NUL"
    phantom.mkdir(parents=True, exist_ok=True)  # 静默「成功」
    assert phantom.exists() and not phantom.is_dir()
    with pytest.raises(HTTPException) as exc:
        novel_routes.safe_target(phantom, "references/a.md")
    assert exc.value.status_code == 400, exc.value.detail

    # 注：根路径的尾随点不在此拦截——safe_target 先做 root.resolve()，Windows 已
    # 把它规范化掉（"book." → "book"），随后各端一致使用该规范名，不构成读写错位。
    # 若要按原始 workspace 字符串拒绝，须在各端点解析前处理（见交接 R18 建议）。

    # 正常根目录不受影响
    good = tmp_path / "real"
    good.mkdir()
    assert novel_routes.safe_target(good, "references/a.md").is_relative_to(good)


def test_put_text_with_phantom_workspace_root_does_not_500(novel_client, tmp_path):
    """端到端：PUT /text 的 workspace 以设备名结尾 → 400，绝不 500。"""
    if not IS_NT:
        pytest.skip("Windows 设备名语义仅在 nt 平台存在")
    client, _ = novel_client
    phantom = tmp_path / "books" / "NUL"
    phantom.mkdir(parents=True, exist_ok=True)
    response = client.put("/api/novel-console/text", json={
        "workflow_id": "xs2-novel-flywheel", "workspace": str(phantom),
        "path": "references/outline.md", "content": "正文"})
    assert response.status_code == 400, response.text


def test_delete_project_with_phantom_workspace_root_does_not_500(novel_client, tmp_path):
    """DELETE /projects 的 workspace 以设备名结尾 → 4xx，不得谎报删除成功。"""
    if not IS_NT:
        pytest.skip("Windows 设备名语义仅在 nt 平台存在")
    client, _ = novel_client
    phantom = tmp_path / "books" / "NUL"
    phantom.mkdir(parents=True, exist_ok=True)
    response = client.delete(
        "/api/novel-console/projects",
        params={"workflow_id": "xs2-novel-flywheel", "workspace": str(phantom)})
    assert response.status_code in (400, 403), response.text
