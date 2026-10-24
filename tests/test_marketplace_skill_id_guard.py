"""Round 20 资源广场 Skill 标识（marketplace slug）设备名守卫回归测试。

B13（与 B11 同族，R19 审计未覆盖的第四个名字面）：`SKILL_ID_PATTERN`
（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）与插件 id 正则同型，放行小写 Windows 设备名；
slug / 包内 `name` 会拼成 `marketplace-skills/<id>` 的**目录名**。

实测取证（`data/_r20_probe4.py` 同款步骤，见 HANDOVER_ROUND20 §3）：

- 空目录下 `Path("marketplace-skills/nul").exists()` 为 **True**（幻影恒真），
  目录列表为空；
- `install_skill_atomically(target=nul, 合法包)` → `FileExistsError(WinError 183)`，
  且 `target/"SKILL.md"` 永不可读；
- `resolve_openable_skill("nul")` 走到 `exists()` 分支 → **409**
  「本地存在同名但来源不同的 Skill」，而实际什么都不存在（对用户谎报）；
- 对照组 `demo-skill` 安装成功、可读回，证明差异只来自设备名。

判定**不按平台门控**（同 B11 的理由）：Skill 标识写进 `skills_config.json`、
也是市场清单的键，跨平台共享；条件式校验会让同一份配置在 POSIX 有效、
在 Windows 永久损坏该名字。尾随点仍由平台门控负责（本正则不含点）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.win_names import is_reserved_device_name
from src.skill_marketplace.bundle import pack
from src.skill_marketplace.errors import LocalSkillError
from src.skill_marketplace.local_skills import (
    install_skill_atomically,
    require_skill_id,
    skill_identity,
    validate_skill_content,
)
from src.skill_marketplace.ownership import (
    SKILL_ID_PATTERN,
    installation_state,
    resolve_openable_skill,
    skill_id_is_safe,
)

DEVICE_IDS = ["nul", "con", "prn", "aux", "com1", "lpt9"]

SKILL_MD = """---
name: {name}
description: demo skill
version: 1.0.0
---

body text
"""


def _package(name: str) -> bytes:
    """单文件包：`pack` 对 {"SKILL.md": …} 直接返回原文（与线上下载一致）。"""
    return pack({"SKILL.md": SKILL_MD.format(name=name).encode("utf-8")})


# ------------------------------------------------------ 谓词与正则的关系（防误解）


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_device_names_pass_the_legacy_regex(device_id: str) -> None:
    """前提固化：这些名字本来能通过旧正则——正因如此才需要追加判定。"""
    assert SKILL_ID_PATTERN.fullmatch(device_id)
    assert is_reserved_device_name(device_id)
    assert not skill_id_is_safe(device_id)


@pytest.mark.parametrize(
    "legit", ["nul-2", "null", "nullable", "console", "com0", "lpt0", "bishu-novel"]
)
def test_legitimate_skill_ids_stay_safe(legit: str) -> None:
    assert skill_id_is_safe(legit)
    assert require_skill_id(legit) == legit


# ------------------------------------------------------ 各入口都必须拒绝


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_require_skill_id_rejects_device_names(device_id: str) -> None:
    with pytest.raises(LocalSkillError, match="Windows 保留设备名"):
        require_skill_id(device_id)


@pytest.mark.parametrize("device_id", DEVICE_IDS)
def test_validate_skill_content_rejects_device_named_package(device_id: str) -> None:
    """下载包正文里的 `name:` 是攻击者可控字段，且直接成为目录名。"""
    with pytest.raises(LocalSkillError, match="Windows 保留设备名"):
        validate_skill_content(_package(device_id))


def test_skill_identity_rejects_device_named_package() -> None:
    with pytest.raises(LocalSkillError, match="Windows 保留设备名"):
        skill_identity(_package("nul"))


def test_normalize_skill_id_rejects_device_names() -> None:
    from src.skill_marketplace.drafts import normalize_skill_id

    with pytest.raises(LocalSkillError, match="Windows 保留设备名"):
        normalize_skill_id("nul")


# ------------------------------------------------------ 拒绝必须先于 exists() 谎报


class _StubManager:
    """只实现被测函数用到的两个方法，避免拉起整个 SkillManager。"""

    def __init__(self, root: Path) -> None:
        self.marketplace_skills_dir = root

    def get_skill(self, skill_id: str):  # noqa: ANN201 - 桩
        return None


def test_resolve_openable_skill_returns_400_not_false_409(tmp_path: Path) -> None:
    """修复前：幻影 `exists()` 恒真 → 409「本地存在同名但来源不同的 Skill」。"""
    manager = _StubManager(tmp_path)
    with pytest.raises(LocalSkillError) as excinfo:
        resolve_openable_skill("nul", skill_manager=manager, marketplace_url=None)
    assert excinfo.value.code == "invalid_slug"
    assert excinfo.value.status_code == 400, "不得用 409 谎报存在性"


def test_installation_state_marks_device_id_conflict_without_touching_fs(
    tmp_path: Path,
) -> None:
    """列表页也不得据幻影 exists() 给出可安装/已存在的误导状态。"""
    detail = {"payload": {"name": "nul"}, "resource": {"slug": "nul"}, "versions": []}
    state = installation_state(
        detail, skill_manager=_StubManager(tmp_path), marketplace_url=None
    )
    assert state["status"] == "conflict"


def test_installation_state_still_reports_available_for_legit_id(tmp_path: Path) -> None:
    detail = {"payload": {"name": "demo-skill"}, "resource": {"slug": "demo-skill"}, "versions": []}
    state = installation_state(
        detail, skill_manager=_StubManager(tmp_path), marketplace_url=None
    )
    assert state["status"] == "available"


def test_install_skill_atomically_rejects_device_target(tmp_path: Path) -> None:
    """纵深防御：即使上游漏检，落盘函数自己也不接受设备名目录。"""
    target = tmp_path / "marketplace-skills" / "nul"
    with pytest.raises(LocalSkillError, match="Windows 保留设备名"):
        install_skill_atomically(target, _package("nul"))
    # 守卫在 mkdir 之前生效：连父目录都不该被创建（零残留）
    assert not (tmp_path / "marketplace-skills").exists()


# ------------------------------------------------------ 正常面不回归


def test_legitimate_skill_package_installs_and_reads_back(tmp_path: Path) -> None:
    target = tmp_path / "marketplace-skills" / "demo-skill"
    install_skill_atomically(target, _package("demo-skill"))
    assert target.is_dir()
    assert "name: demo-skill" in (target / "SKILL.md").read_text(encoding="utf-8")


def test_multi_file_bundle_package_still_works(tmp_path: Path) -> None:
    content = pack({
        "SKILL.md": SKILL_MD.format(name="demo-skill").encode("utf-8"),
        "refs/a.md": b"# a\n",
    })
    assert validate_skill_content(content) == "demo-skill"
    target = tmp_path / "marketplace-skills" / "demo-skill"
    install_skill_atomically(target, content)
    assert (target / "refs" / "a.md").is_file()
