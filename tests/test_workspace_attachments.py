import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.web.attachment_routes import _safe_attachment_name, router


def _client(workspace: Path, *, session_id: str = "session-1") -> TestClient:
    workspace.mkdir(parents=True, exist_ok=True)
    session = SimpleNamespace(workspace_path=str(workspace))
    session_manager = SimpleNamespace(
        get_session=lambda requested: session if requested == session_id else None,
    )
    app = FastAPI()
    app.state.session_manager = session_manager
    app.include_router(router)
    return TestClient(app)


def test_attachment_name_discards_client_directories():
    assert _safe_attachment_name("../private/report.txt") == "report.txt"
    assert _safe_attachment_name(r"C:\\Users\\me\\notes.md") == "notes.md"


def test_upload_stores_file_in_session_workspace_and_returns_absolute_path(tmp_path):
    workspace = tmp_path / "workspace"
    response = _client(workspace).post(
        "/api/workspace/session-1/attachments",
        params={"filename": "report.txt"},
        content=b"attachment body",
    )

    assert response.status_code == 200
    payload = response.json()
    stored = Path(payload["absolute_path"])
    assert stored == (workspace / "attachments" / "report.txt").resolve()
    assert payload["relative_path"] == "attachments/report.txt"
    assert payload["size"] == len(b"attachment body")
    assert stored.read_bytes() == b"attachment body"


def test_upload_never_overwrites_an_existing_attachment(tmp_path):
    workspace = tmp_path / "workspace"
    client = _client(workspace)

    first = client.post(
        "/api/workspace/session-1/attachments",
        params={"filename": "report.txt"},
        content=b"first",
    ).json()
    second = client.post(
        "/api/workspace/session-1/attachments",
        params={"filename": "report.txt"},
        content=b"second",
    ).json()

    assert first["name"] == "report.txt"
    assert second["name"] == "report (1).txt"
    assert Path(first["absolute_path"]).read_bytes() == b"first"
    assert Path(second["absolute_path"]).read_bytes() == b"second"


def test_upload_rejects_unknown_session(tmp_path):
    response = _client(tmp_path / "workspace").post(
        "/api/workspace/missing/attachments",
        params={"filename": "report.txt"},
        content=b"body",
    )

    assert response.status_code == 404


@pytest.mark.skipif(os.name != "nt", reason="Windows 设备名/尾随点语义仅在 nt 平台特判")
def test_attachment_name_rejects_windows_device_names_and_trailing_dots():
    """B10：设备名/尾随点附件名在 Windows 上不可用，必须在命名层拒绝。

    实测（R19）：``NUL`` 经 os.open 打开的是设备本身——上传返回 200 但内容被静默
    丢弃；``notes.`` 落盘名被剥离成 ``notes``（上报名与实际名不一致）。
    """
    for bad in ("NUL", "nul", "NUL.txt", "con.md", "COM1", "notes.", "report. "):
        with pytest.raises(ValueError):
            _safe_attachment_name(bad)


@pytest.mark.skipif(os.name != "nt", reason="Windows 设备名/尾随点语义仅在 nt 平台特判")
def test_upload_device_name_returns_400_and_writes_nothing(tmp_path):
    workspace = tmp_path / "workspace"
    response = _client(workspace).post(
        "/api/workspace/session-1/attachments",
        params={"filename": "NUL"},
        content=b"attachment body",
    )

    assert response.status_code == 400
    assert "文件名" in response.json()["detail"]
    # 不得留下幻影条目：attachments 目录要么不存在，要么为空
    attachments = workspace / "attachments"
    assert not attachments.exists() or not any(attachments.iterdir())
