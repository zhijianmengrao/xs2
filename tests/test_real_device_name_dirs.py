"""R23（P1 复查收尾）：真实设备名目录（经 ``\\\\?\\`` 前缀创建）下的守卫与审计行为。

R21 §9 P1 要求对 ``_trusted_marketplace_skill_path`` 与 installs 的
``target.exists()`` 判定路径做「幻影目录免疫」复查，且要有 **monkeypatch
``_on_windows`` 之外的真实证据**。本文件把该真实证据钉成常驻回归：

在真实 NTFS 上用扩展路径前缀 ``\\\\?\\`` 绕过 Win32 设备名解析，创建一个
**真实存在**的 ``nul`` 目录，然后验证：

1. ``Path`` 对它仍呈幻影属性语义（``exists()=True`` 而 ``is_dir()=False``）——
   R23 实测，比 PROJECT_INFO 注意事项 12 的「幻影 NUL」更微妙：目录真实存在、
   ``iterdir`` 可列出、其下可正常读写，但属性查询被设备名解析劫持；
2. ``_trusted_marketplace_skill_path`` 在不打任何补丁的真实文件系统上依旧拒绝
   （409 conflict）——这是 R21 复查缺失的那块证据；
3. 规则源 ``unsafe_device_name`` / ``assert_safe_skill_id`` 判定不变；
4. 存储名审计扫描器能发现这种真实遗留；
5. （R24）``installation_state`` 在真实 nul 目录存在时仍报 conflict——
   R23 §9 P3 的「exists()→conflict 谎报路径复核」收口。

POSIX 上 ``\\\\?\\`` 无意义，直接 skip；Windows 上个别文件系统拒绝该前缀时
同样诚实 skip。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from src.core.storage_name_audit import scan_storage_names
from src.core.win_names import unsafe_device_name
from src.skill_marketplace.errors import LocalSkillError
from src.skill_marketplace.ownership import assert_safe_skill_id, installation_state
from src.skill_marketplace.updates import _trusted_marketplace_skill_path


class _StubManager:
    def __init__(self, marketplace_skills_dir: Path) -> None:
        self.marketplace_skills_dir = marketplace_skills_dir

    def get_skill(self, skill_id: str) -> None:
        """installation_state 对合法 id 会查本地注册表；桩固定返回未安装。"""
        return None


class _StubSkill:
    def __init__(self, skill_dir: str) -> None:
        self.metadata = {"skill_dir": skill_dir}


def _create_real_device_name_dir(parent: Path, name: str) -> Path | None:
    """经 ``\\\\?\\`` 前缀创建真实设备名目录；环境不支持时返回 None。"""
    target = parent / name
    try:
        os.mkdir("\\\\?\\" + str(target))
    except OSError:
        return None
    return target


def _remove_real_device_name_tree(path: Path) -> None:
    """设备名目录只能经 ``\\\\?\\`` 前缀删除（常规路径被设备名解析劫持）。"""
    shutil.rmtree("\\\\?\\" + str(path), ignore_errors=True)


def _requires_extended_path_support() -> None:
    if sys.platform != "win32":
        pytest.skip("\\\\?\\ 扩展路径前缀仅存在于 Windows")


def test_real_nul_dir_is_rejected_by_marketplace_path_guard(tmp_path: Path) -> None:
    _requires_extended_path_support()
    marketplace = tmp_path / "marketplace-skills"
    marketplace.mkdir()
    real_nul = _create_real_device_name_dir(marketplace, "nul")
    if real_nul is None:
        pytest.skip("本环境/文件系统拒绝经 \\\\?\\ 创建真实设备名目录")
    try:
        # 真实存在的目录，对常规 Path 仍呈幻影属性语义（R23 实测锚点）
        assert real_nul.exists() is True
        assert real_nul.is_dir() is False
        assert [entry.name for entry in marketplace.iterdir()] == ["nul"]

        # 规则源判定不受目录是否真实存在影响
        assert unsafe_device_name("nul") is not None
        with pytest.raises(LocalSkillError):
            assert_safe_skill_id("nul")

        # 防纵深：路径守卫在未打补丁的真实文件系统上拒绝（is_dir()=False → conflict）。
        # 入口面另有 _validate_slug / validate_skill_content 的 assert_safe_skill_id，
        # 本断言保证即便历史数据里已经躺着一个真实 nul 目录，update 链路也不会采用它。
        manager = _StubManager(marketplace)
        skill = _StubSkill(str(real_nul.resolve()))
        with pytest.raises(LocalSkillError) as excinfo:
            _trusted_marketplace_skill_path(manager, "nul", skill)
        assert excinfo.value.code == "conflict"
        assert excinfo.value.status_code == 409
    finally:
        _remove_real_device_name_tree(real_nul)
        assert list(marketplace.iterdir()) == []  # \\?\ 清理成功，零残留


def test_storage_name_audit_detects_real_nul_dir(tmp_path: Path) -> None:
    _requires_extended_path_support()
    storage = tmp_path / "data" / "skills" / "marketplace"
    storage.mkdir(parents=True)
    real_nul = _create_real_device_name_dir(storage, "nul")
    if real_nul is None:
        pytest.skip("本环境/文件系统拒绝经 \\\\?\\ 创建真实设备名目录")
    try:
        findings = scan_storage_names(tmp_path)
        assert [(finding.surface, finding.name) for finding in findings] == [
            ("data/skills/marketplace", "nul"),
        ]
    finally:
        _remove_real_device_name_tree(real_nul)
        assert list(storage.iterdir()) == []


def test_installation_state_conflict_with_real_nul_dir_on_disk(tmp_path: Path) -> None:
    """R24（R23 §9 P3 收口）：真实 nul 目录躺在 marketplace-skills 下时，
    installation_state 必须报 conflict（R20 修复面在真实文件系统上的证据）。

    两条路径在此叠加：名字守卫（skill_id_is_safe → conflict）先于 exists()，
    即便守卫被绕过，真实目录也让 exists() 恒真 → conflict——结论一致、
    无「可安装」谎报。对照组用真实存在的普通目录钉住 exists() 分支本身
    在真实文件系统上的行为（来源不同的同名 Skill → conflict）。
    """
    _requires_extended_path_support()
    marketplace = tmp_path / "marketplace-skills"
    marketplace.mkdir()
    real_nul = _create_real_device_name_dir(marketplace, "nul")
    if real_nul is None:
        pytest.skip("本环境/文件系统拒绝经 \\\\?\\ 创建真实设备名目录")
    try:
        (marketplace / "demo-skill").mkdir()  # 对照组：真实的普通同名目录
        manager = _StubManager(marketplace)
        device_detail = {"payload": {"name": "nul"}, "resource": {"slug": "nul"}, "versions": []}
        assert installation_state(
            device_detail, skill_manager=manager, marketplace_url=None
        )["status"] == "conflict"
        legit_detail = {
            "payload": {"name": "demo-skill"},
            "resource": {"slug": "demo-skill"},
            "versions": [],
        }
        assert installation_state(
            legit_detail, skill_manager=manager, marketplace_url=None
        )["status"] == "conflict"
        # 安装入口同判：真实 nul 目录存在时 install 仍被 already_exists 拒绝
        with pytest.raises(LocalSkillError):
            assert_safe_skill_id("nul")
    finally:
        _remove_real_device_name_tree(real_nul)
        assert [entry.name for entry in marketplace.iterdir()] == ["demo-skill"]
