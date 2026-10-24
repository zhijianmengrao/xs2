"""Round 20 插件命名面（plugin_system / extension_host）Windows 设备名守卫回归测试。

对应 R19 §8 R19-3（当时记为「豁免」）——本轮实测**推翻豁免结论**，改为缺陷 B11/B12：

- B11：`validate_plugin_id` 的 `^[a-z0-9]+(?:-[a-z0-9]+)*$` 放行小写设备名
  （`nul`/`con`/`aux`/`com1`/`lpt1`），而插件 id 会直接成为目录名：
  `data/plugins/checkouts/<id>`、`data/plugins/runtime-resources/<id>`、
  以及 `plugins.lock.json` 的键。`NUL` 目录是幻影（实测：mkdir 静默成功、
  `exists()` 恒真、`is_dir()` 假、`iterdir()` 看不到），于是
  `_atomic_replace_directory` 报 **OSError(WinError 87)**、`os.replace` 报
  **FileNotFoundError(WinError 3)**——`OSError` 不是 `PluginStoreError`/`ValueError`，
  逃出 `_raise_http_error` → **HTTP 500**（应为 400），且锁文件/目录状态不一致。
- B12：插件资源 `local_id` 经 `ResourceIdPlan.resolve` 成为 `effective_id`，
  而 `effective_id` 是 `copytree` 的目标目录名；`nul` 被放行且资源 JSON 键与目录名
  可以不同，构成「声明资源名 → 落盘目录名」的名字拼接点。

设备名判定是**平台无关**的（与 `skill_marketplace.bundle` 同一先例）：插件 id 同时是
锁文件键与市场清单键，若只在 nt 拒绝，同一注册表在 Linux/Windows 上会得到不同的
「清单是否有效」结论（`_parse_registry_plugin` 对任一非法 id 抛 `PluginRegistryError`
使整份清单失效），属不可接受的行为分裂。尾随点/空格仍按平台门控（现有 kebab-case
正则本就不含点，故此处无需重复）。
"""

from __future__ import annotations

import json
import os

import pytest

from src.core.win_names import is_reserved_device_name
from src.extension_host.resource_ids import (
    ResourceIdError,
    build_resource_id_plan,
    effective_resource_id,
)
from src.plugin_system.models import (
    ProcessSpec,
    validate_plugin_id,
    validate_plugin_subdirectory,
    validate_resource_prefix,
)

DEVICE_IDS = ["nul", "con", "prn", "aux", "com1", "com9", "lpt1", "lpt9"]


# ------------------------------------------------------------------ B11：插件 id


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_validate_plugin_id_rejects_lowercase_device_names(device_id: str) -> None:
    """小写设备名不能作插件 id（它们是大写保留名的合法 kebab-case 写法）。"""
    assert is_reserved_device_name(device_id), "前提：属于设备名规则源"
    with pytest.raises(ValueError, match="Windows 保留设备名"):
        validate_plugin_id(device_id)


@pytest.mark.parametrize("prefix", DEVICE_IDS)
def test_validate_resource_prefix_rejects_device_names(prefix: str) -> None:
    with pytest.raises(ValueError, match="Windows 保留设备名"):
        validate_resource_prefix(prefix)


def test_validate_plugin_id_device_rejection_is_platform_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 nt 平台也必须拒绝：同一插件 id 是锁/清单的跨平台共享键。"""
    from src.core import win_names

    monkeypatch.setattr(win_names, "_on_windows", lambda: False)
    assert win_names.unsafe_windows_component("nul") is None
    with pytest.raises(ValueError):
        validate_plugin_id("nul")


@pytest.mark.parametrize(
    "legit_id",
    [
        "xs2-novel-flywheel",
        "bishu-novel",
        "demo-plugin",
        "null",
        "nullable",
        "nul-2",
        "console",
        "com0",
        "com10",
        "lpt0",
        "clockwise",
        "prn-printer",
        "auxiliary",
    ],
)
def test_validate_plugin_id_keeps_legitimate_ids(legit_id: str) -> None:
    """零误伤：形近名与既有真实插件 id 必须继续通过。"""
    assert validate_plugin_id(legit_id) == legit_id


@pytest.mark.parametrize("legit_prefix", ["bishu-novel", "nul-2", "xs2-novel-flywheel"])
def test_validate_resource_prefix_keeps_legitimate_prefixes(legit_prefix: str) -> None:
    assert validate_resource_prefix(legit_prefix) == legit_prefix


def test_validate_plugin_id_still_rejects_illegal_shapes() -> None:
    """既有拒绝面不变（大写/点/下划线/空/超长）。"""
    for bad in ["", "Demo", "demo.plugin", "demo_plugin", "a" * 129, "nul/../../etc"]:
        with pytest.raises(ValueError):
            validate_plugin_id(bad)


def test_validate_plugin_subdirectory_rejects_traversal_but_allows_device_segment() -> None:
    """子目录的幻影段是**已核实豁免**（不修）：实测该段 `is_dir()` 为假，后续
    manifest 查找失败 → `InvalidPluginPackageError`（大声报错），不产生错误的成功
    响应，也不静默丢数据。此处只固化「不得因本轮改动而放宽穿越防护」。
    """
    with pytest.raises(ValueError, match="safe relative path"):
        validate_plugin_subdirectory("../etc/passwd")
    assert validate_plugin_subdirectory("package/src") == "package/src"


# ------------------------------------------------------------------ B12：资源 local_id


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_build_resource_id_plan_rejects_device_local_ids(device_id: str) -> None:
    """local_id 会成为 effective_id → copytree 目标目录名，必须拒绝。"""
    with pytest.raises(ResourceIdError, match="Windows 保留设备名"):
        build_resource_id_plan("demo-plugin", "", {"workflows": [device_id]})


def test_non_path_bearing_resource_kinds_are_not_rejected() -> None:
    """agent/prompt/preset_phrase 的 id 只是 JSON 文档内的键，不落盘为路径。

    拒绝它们会误伤插件正文（例如一个叫 ``nul`` 的 agent 键），故守卫必须
    **只**覆盖 effective_id 被用作目录名的资源类型。
    """
    plan = build_resource_id_plan(
        "demo-plugin", "", {"agent": ["nul"], "prompt": ["nul"], "preset_phrase": ["nul"]}
    )
    assert [m.effective_id for m in plan.mappings] == ["nul", "nul", "nul"]


@pytest.mark.parametrize("kind", ["workflows", "script_libraries", "skill_bundles", "rules"])
def test_path_bearing_resource_kinds_reject_device_effective_ids(kind: str) -> None:
    """落盘为目录名的四类资源必须拒绝设备名 effective_id。"""
    with pytest.raises(ResourceIdError, match="Windows 保留设备名"):
        build_resource_id_plan("demo-plugin", "", {kind: ["nul"]})


def test_prefixed_effective_ids_are_still_allowed() -> None:
    """加前缀后不再是设备名，属合法——不要顺手扩大拒绝面。"""
    assert effective_resource_id("xs2", "nul") == "xs2-nul"
    plan = build_resource_id_plan("demo-plugin", "demo", {"workflows": ["nul"]})
    assert [m.effective_id for m in plan.mappings] == ["demo-nul"]


def test_legitimate_resource_local_ids_still_accepted() -> None:
    plan = build_resource_id_plan(
        "demo-plugin", "", {"workflows": ["null-flow", "convey", "nul-2"]}
    )
    assert [m.effective_id for m in plan.mappings] == ["null-flow", "convey", "nul-2"]


# ------------------------------------------------------------------ process_id（同一规则源）


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_process_spec_rejects_device_process_id(device_id: str) -> None:
    """`process_id` 成为 `<id>.log`；`nul.log` 在部分 Windows 上是设备而非文件。"""
    with pytest.raises(ValueError, match="Windows 保留设备名"):
        ProcessSpec(process_id=device_id, argv=["python", "x.py"])


def test_process_spec_keeps_legitimate_ids() -> None:
    for legit in ["worker", "worker.main", "side-car", "null-checker"]:
        assert ProcessSpec(process_id=legit, argv=["x"]).process_id == legit


# ------------------------------------------------------------------ HTTP 语义（B11 的 500→400）


def _manager(base_dir, store):  # noqa: ANN001 - 与 test_plugin_routes 保持同型
    from src.extension_host.manager import ExtensionManager

    config_dir = base_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "extensions.json"
    config_file.write_text('{"enabled":[],"strict_startup":false}', encoding="utf-8")
    return ExtensionManager(
        base_dir,
        config_file=config_file,
        plugin_store=store,
        discover_entry_points=False,
    )


def test_install_endpoint_returns_400_for_device_plugin_id(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设备名插件 id 必须是 400（客户端输入错误），不是 500/200。

    id 校验发生在任何 git 传输之前，故本用例在 Low-IL（msys 不可引导）下同样可跑。
    """
    from fastapi.testclient import TestClient

    from src.plugin_system import PluginStore
    from src.web_server import create_app

    token = "t" + os.urandom(8).hex()
    monkeypatch.setenv("AI_COMPANY_PLUGIN_ADMIN_TOKEN", token)
    store = PluginStore(tmp_path / "plugins", official_sources=[str(tmp_path / "src")])
    client = TestClient(create_app(_manager(tmp_path / "core", store)))
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post(
        "/api/plugins/install",
        headers=headers,
        json={
            "plugin_id": "nul",
            "source": str(tmp_path / "src"),
            "ref": "HEAD",
            "subdirectory": "",
            "resource_prefix": None,
            "acknowledge_risk": True,
        },
    )

    assert response.status_code == 400, response.text
    assert "Windows 保留设备名" in response.json()["detail"]
    # 不得留下幻影目录、锁文件或任何 checkout 痕迹
    assert (store.checkouts_dir / "nul").is_dir() is False
    assert not store.lock_path.exists() or (
        json.loads(store.lock_path.read_text(encoding="utf-8"))["plugins"] == {}
    )
