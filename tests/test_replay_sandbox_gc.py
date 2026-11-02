"""R110：失败沙箱 GC 的行为用例（默认 dry-run、前缀/年龄/链接守卫）。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from scripts import replay_sandbox_gc as gc


def _sandbox(root: Path, name: str, age_days: float) -> Path:
    path = root / name
    path.mkdir()
    (path / "marker").write_text("x", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_dry_run_lists_only_old_matching_directories(
        tmp_path: Path, capsys) -> None:
    old = _sandbox(tmp_path, "replay-ci-writeback-old", 10)
    new = _sandbox(tmp_path, "replay-ci-writeback-new", 1)
    other = _sandbox(tmp_path, "other-old", 10)
    plain = tmp_path / "replay-ci-writeback-file"
    plain.write_text("not a dir", encoding="utf-8")
    stamp = time.time() - 10 * 86400
    os.utime(plain, (stamp, stamp))

    assert gc.main(["--root", str(tmp_path),
                    "--min-age-days", "7"]) == 0

    out = capsys.readouterr().out
    assert "[dry-run]" in out
    assert "replay-ci-writeback-old" in out
    assert "replay-ci-writeback-new" not in out
    assert "other-old" not in out
    assert "replay-ci-writeback-file" not in out
    # dry-run 一个都不删。
    for path in (old, new, other, plain):
        assert path.exists()


def test_apply_removes_only_the_candidates(
        tmp_path: Path, capsys) -> None:
    old = _sandbox(tmp_path, "replay-ci-writeback-old", 10)
    new = _sandbox(tmp_path, "replay-ci-writeback-new", 1)
    other = _sandbox(tmp_path, "other-old", 10)

    assert gc.main(["--root", str(tmp_path),
                    "--min-age-days", "7", "--apply"]) == 0

    out = capsys.readouterr().out
    assert not old.exists()
    assert new.exists()
    assert other.exists()
    assert "删除 1/1 个候选" in out


def test_min_age_zero_is_allowed(tmp_path: Path) -> None:
    fresh = _sandbox(tmp_path, "replay-ci-writeback-fresh", 0)

    assert gc.main(["--root", str(tmp_path),
                    "--min-age-days", "0", "--apply"]) == 0

    assert not fresh.exists()


def test_negative_age_is_a_usage_error(tmp_path: Path, capsys) -> None:
    assert gc.main(["--root", str(tmp_path),
                    "--min-age-days", "-1"]) == 2
    assert "不能为负" in capsys.readouterr().err


def test_missing_root_is_a_usage_error(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing"
    assert gc.main(["--root", str(missing)]) == 2
    assert "不存在" in capsys.readouterr().err


def test_symlink_with_matching_name_is_skipped(
        tmp_path: Path, capsys) -> None:
    target = _sandbox(tmp_path, "target", 10)
    link = tmp_path / "replay-ci-writeback-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"当前环境不能创建目录符号链接：{exc}")

    assert gc.main(["--root", str(tmp_path),
                    "--min-age-days", "7", "--apply"]) == 0

    assert target.exists(), "符号链接的目标不能被删除"
    assert link.exists(), "链接本身应被跳过"
    assert "删除 0/0 个候选" in capsys.readouterr().out
