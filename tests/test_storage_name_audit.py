"""R21 B13 纵深：存储名只读审计扫描器的回归测试。

覆盖：
- 配置面（skills_config / plugins.lock 的 id 键）命中设备名 → 报告 + 建议；
- 目录面（checkouts / runtime-resources / skills 三个区域）目录项命中 → 报告；
- 合法名字（nul-2/com0/bishu-novel 等 R20 零误伤样本）不误报；
- 文件/目录缺失、JSON 损坏时安静跳过（只读诊断不因布局不全而失败）；
- 真实仓库树零命中（R20 零误伤结论的常驻锚——CI 克隆缺 data/ 时各面自然跳过）。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.storage_name_audit import scan_storage_names

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_clean_tree_reports_nothing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "config" / "skills_config.json",
        {"skill_configs": {"agent-definition-guide": {"enabled": True}}},
    )
    _write_json(
        tmp_path / "data" / "plugins" / "plugins.lock.json",
        {"plugins": {"bishu-novel": {"active_revision": {}}}},
    )
    for relative, names in (
        ("data/plugins/checkouts", ["bishu-novel"]),
        ("data/plugins/runtime-resources", ["bishu-novel"]),
        ("data/skills/marketplace", ["workflow-guide"]),
        ("data/skills/local", ["nul-2", "com0", "nullable"]),
    ):
        for name in names:
            (tmp_path / relative / name).mkdir(parents=True, exist_ok=True)
    assert scan_storage_names(tmp_path) == []


def test_device_named_config_keys_are_reported(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "config" / "skills_config.json",
        {"skill_configs": {"nul": {"enabled": True}, "ok-skill": {"enabled": True}}},
    )
    _write_json(
        tmp_path / "data" / "plugins" / "plugins.lock.json",
        {"plugins": {"com1": {}, "bishu-novel": {}}},
    )
    findings = scan_storage_names(tmp_path)
    reported = {(finding.surface, finding.name) for finding in findings}
    assert ("config/skills_config.json", "nul") in reported
    assert ("data/plugins/plugins.lock.json", "com1") in reported
    assert all("手工" in finding.detail for finding in findings)


def test_device_named_storage_entries_are_reported(tmp_path: Path) -> None:
    # con/aux 作为真实目录在 Windows 上可创建（PROJECT_INFO 注意事项 12），
    # POSIX 上是普通名字——两个平台都能构造出「目录项名字命中」的现场。
    for relative, name in (
        ("data/plugins/checkouts", "con"),
        ("data/plugins/runtime-resources", "aux"),
        ("data/skills/marketplace", "lpt9"),
    ):
        (tmp_path / relative / name).mkdir(parents=True)
    findings = scan_storage_names(tmp_path)
    reported = {(finding.surface, finding.name) for finding in findings}
    assert reported == {
        ("data/plugins/checkouts", "con"),
        ("data/plugins/runtime-resources", "aux"),
        ("data/skills/marketplace", "lpt9"),
    }
    assert all(finding.kind == "storage-entry" for finding in findings)


def test_missing_surfaces_and_broken_json_are_skipped(tmp_path: Path) -> None:
    assert scan_storage_names(tmp_path) == []  # 空根：全部面缺失，安静通过
    config = tmp_path / "config" / "skills_config.json"
    config.parent.mkdir(parents=True)
    config.write_text("{ not json", encoding="utf-8")
    assert scan_storage_names(tmp_path) == []  # 损坏 JSON 不使诊断崩溃


def test_real_repo_tree_is_clean() -> None:
    """R20 零误伤结论的常驻锚：真实数据里不得出现设备名遗留。

    CI 克隆不含 data/ 工作区（.gitkeep 布局）时各面自然跳过、恒过；
    本机真实数据树若被旧版本污染，此处会先行失败给出线索。
    """
    assert scan_storage_names(REPO_ROOT) == []


def test_script_survives_non_utf8_stdout() -> None:
    """B18 回归锚：stdout 为 cp1252（CI PowerShell 实况）时脚本不得崩溃。

    windows-latest 曾在打印中文 [clean] 结论处抛 UnicodeEncodeError（cp1252
    charmap 无法编码中文），把通过的审计误报成步骤失败——本机 cp936 可编码
    中文，故只有强制 cp1252 的子进程才能复现。"""
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "audit_storage_names.py")],
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"exit={proc.returncode} stderr={stderr}"
    assert "[clean]" in proc.stdout.decode("utf-8", errors="replace")
