"""R21 P2：市场 Skill 安装端到端（真实包）——路由 → 服务 → 真实 portal 客户端。

既有安装测试面（test_marketplace_installation.py）以 FakeMarketplace 直接调服务；
此处补齐的是 HANDOVER_ROUND20 §9 P2 指出的缺口——**真实包**经完整链路：

- 真实 ``ResourceMarketplaceClient`` + ``httpx.MockTransport``（走真实请求
  序列化/响应解析路径，仅不出网卡）；
- 真实多文件包（``bundle.pack``：SKILL.md + refs/reference.md）；
- FastAPI 路由层（TestClient）+ 真实 SkillManager（磁盘 skills 根、provenance、
  启用配置）。

锚定：安装成功落盘可读回、provenance/启用状态持久化、重复安装 409、
设备名 slug 在 HTTP 面 400 且**零市场请求**（R20 守卫在路由链最上游生效）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from marketplace_fixtures import _empty_manager
from src.skill_marketplace.bundle import pack
from src.skill_marketplace.portal import ResourceMarketplaceClient
from src.skill_marketplace.routes import router
from src.skill_marketplace.service import SkillMarketplaceService

SLUG = "demo-skill"
SKILL_MD = (
    "---\n"
    "name: demo-skill\n"
    "description: e2e real-package install target\n"
    "version: 1.4.2\n"
    "---\n"
    "\n"
    "# Demo\n"
    "\n"
    "Do the real thing.\n"
).encode("utf-8")
BUNDLE = pack({"SKILL.md": SKILL_MD, "refs/reference.md": b"# reference\n"})
BUNDLE_SHA = hashlib.sha256(BUNDLE).hexdigest()
BASE_URL = "https://marketplace.example"

DETAIL = {
    "resource_id": "44444444-4444-4444-8444-444444444444",
    "version_id": "55555555-5555-4555-8555-555555555555",
    "publisher_id": "pub_0123456789abcdef01234567",
    "resource_type": "skill",
    "functional_category": "general",
    "slug": SLUG,
    "skill_name": SLUG,
    "version": "1.4.2",
    "license": "MIT",
    "sha256": BUNDLE_SHA,
}
PIN = {"expected_version_id": DETAIL["version_id"], "expected_sha256": BUNDLE_SHA}


def _marketplace_transport(requests: list[str]):
    """按线上 API 形状应答，并记录每次出站请求（方法+路径）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.url.path == f"/api/resource-marketplace/skills/{SLUG}":
            return httpx.Response(200, json=DETAIL)
        if request.url.path == f"/api/resource-marketplace/skills/{SLUG}/download":
            return httpx.Response(
                200, content=BUNDLE, headers={"x-skill-sha256": BUNDLE_SHA}
            )
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def _e2e_service(
    tmp_path: Path, requests: list[str]
) -> SkillMarketplaceService:
    return SkillMarketplaceService(
        data_dir=tmp_path / "data",
        skill_manager=_empty_manager(tmp_path),
        marketplace=ResourceMarketplaceClient(
            BASE_URL, app_version="test-e2e", transport=_marketplace_transport(requests)
        ),
    )


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    requests: list[str] = []
    monkeypatch.setenv("DETERMINFLOW_DESKTOP", "1")
    application = FastAPI()
    application.state.resource_marketplace_service = _e2e_service(tmp_path, requests)
    application.include_router(router)
    yield application, requests


def test_install_real_package_through_http_route(tmp_path: Path, app) -> None:
    application, requests = app
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        response = client.post(f"/api/resource-marketplace/skills/{SLUG}/install", json=PIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["installed"] is True
    assert body["skill_id"] == SLUG
    assert body["sha256"] == BUNDLE_SHA
    assert body["version"] == "1.4.2"
    assert body["installation"] == {
        "status": "installed",
        "version": "1.4.2",
        "enabled": True,
        "update_available": False,
    }

    # 链路取证：详情 + 下载各一次，均为真实 portal 客户端发起
    assert requests == [
        f"GET /api/resource-marketplace/skills/{SLUG}",
        f"GET /api/resource-marketplace/skills/{SLUG}/download",
    ]

    # 落盘真相：多文件包完整解包、字节一致
    target = tmp_path / "skills" / "marketplace" / SLUG
    assert (target / "SKILL.md").read_bytes() == SKILL_MD
    assert (target / "refs" / "reference.md").read_bytes() == b"# reference\n"

    # provenance / 启用状态持久化
    source = body["provenance"]["source"]
    assert source["kind"] == "marketplace"
    assert source["registry"] == BASE_URL
    assert source["resource_id"] == DETAIL["resource_id"]
    assert body["provenance"]["package"]["sha256"] == BUNDLE_SHA
    manager = application.state.resource_marketplace_service.skill_manager
    installed = manager.get_skill(SLUG)
    assert installed is not None and installed.enabled is True


def test_second_install_of_same_package_conflicts(tmp_path: Path, app) -> None:
    application, requests = app
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        first = client.post(f"/api/resource-marketplace/skills/{SLUG}/install", json=PIN)
        second = client.post(f"/api/resource-marketplace/skills/{SLUG}/install", json=PIN)
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "already_exists"
    # 第二次只重新取了详情（判定安装态），未再次下载
    assert requests.count(f"GET /api/resource-marketplace/skills/{SLUG}/download") == 1


def test_device_name_slug_is_400_without_any_marketplace_request(app) -> None:
    """R20 B13 在 HTTP 安装面的最上游锚：`nul` → 400 invalid_slug，零出站请求。"""
    application, requests = app
    with TestClient(application, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/resource-marketplace/skills/nul/install", json=PIN)
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "invalid_slug"
    assert requests == []
