r"""Windows MAX_PATH 回归:插件 checkout 深层树的哈希与遍历。

v1.0.1 事故:checkouts/<id>/<commit>-<digest16>/ 前缀 151 字符 + 深层
vendor 相对路径 105 字符 = 叶子目录 254 字符,iterdir/scandir 追加通配符
后越界抛 WinError 3。所有针对 checkout 树的遍历/复制/哈希必须走
extended_path()(\\?\ 前缀)。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from src.plugin_system import extended_path
from src.plugin_system.integrity import plugin_content_sha256

_DEEP_REL = Path(
    "resources/script-library/xs2/reference_distill/vendor/"
    "writing-dna-skill/templates/author-corpus/zh/_meta"
)


def _materialize_deep_tree(base: Path, leaf_target_chars: int) -> tuple[Path, Path]:
    """先在短路径建树,再改名为指定长度,绕过 Windows 对创建长路径的限制。"""
    short_root = base / "staging-short"
    leaf = short_root / _DEEP_REL
    leaf.mkdir(parents=True)
    (leaf / "example.schema.json").write_text("{}", encoding="utf-8")
    (short_root / "extension.toml").write_text("[extension]\n", encoding="utf-8")
    pad_chars = max(leaf_target_chars - len(str(base)) - 1 - len(str(_DEEP_REL)), 1)
    long_root = base / ("p" * pad_chars)
    os.rename(short_root, long_root)
    return long_root, long_root / _DEEP_REL


def test_extended_path_matches_platform(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"
    extended = extended_path(target)
    if sys.platform == "win32":
        text = str(extended)
        assert text.startswith("\\\\?\\")
        assert "\\" not in text[4:] or "/\\/" not in text
        assert not text[4:].startswith("\\\\")
        assert extended.name == "b"
    else:
        assert extended == target


def test_extended_path_is_idempotent(tmp_path: Path) -> None:
    once = extended_path(tmp_path)
    assert extended_path(once) == once


def test_deep_checkout_sha256_survives_max_path(tmp_path: Path) -> None:
    root, leaf = _materialize_deep_tree(tmp_path, 254)
    digest_a = plugin_content_sha256(root)
    digest_b = plugin_content_sha256(root)
    assert len(digest_a) == 64
    assert digest_a == digest_b


def test_deep_dir_listing_uses_extended_path(tmp_path: Path) -> None:
    root, leaf = _materialize_deep_tree(tmp_path, 300)
    names = [path.name for path in extended_path(leaf).iterdir()]
    assert names == ["example.schema.json"]
    assert plugin_content_sha256(root)


def _max_path_enforced(base: Path) -> bool:
    """探测当前环境是否仍强制 MAX_PATH(CI runner 常已启用长路径)。"""
    probe = base / ("l" * 250)
    try:
        probe.mkdir()
    except OSError:
        return True
    probe.rmdir()
    return False


@pytest.mark.skipif(sys.platform != "win32", reason="MAX_PATH 仅 Windows")
def test_plain_iterdir_fails_beyond_max_path(tmp_path: Path) -> None:
    if not _max_path_enforced(tmp_path):
        pytest.skip("此环境已启用 Windows 长路径(LongPathsEnabled),MAX_PATH 不生效")
    _root, leaf = _materialize_deep_tree(tmp_path, 300)
    with pytest.raises(OSError):
        list(leaf.iterdir())
