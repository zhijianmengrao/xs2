"""R110：清理 replay 失败现场（默认 dry-run）。

``replay_ci_writeback`` 在退出码非 0 时按设计保留沙箱
（``replay-ci-writeback-*``），便于复盘；CI runner 是临时的，本机则会
累积。本工具只处理**直接子目录**、**名字前缀匹配**、**非符号链接/非
junction**、**mtime 超过阈值**的目录；默认只打印候选，``--apply`` 才删除。

用法::

    python scripts/replay_sandbox_gc.py
    python scripts/replay_sandbox_gc.py --min-age-days 3
    python scripts/replay_sandbox_gc.py --apply
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import replay_ci_writeback as replay

# 与 ``replay_ci_writeback.replay`` 里 ``mkdtemp(prefix=...)`` 完全一致。
SANDBOX_PREFIX = "replay-ci-writeback-"
DEFAULT_MIN_AGE_DAYS = 7.0


def _is_symlink_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    # Python 3.12+；旧版本没有 is_junction，按「不是 junction」处理。
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def candidates(root: Path, min_age_days: float,
               now: float | None = None) -> list[tuple[Path, float]]:
    """返回 ``(路径, 年龄秒数)``；只认直接子目录 + 前缀 + 非链接 + 超龄。"""
    now = time.time() if now is None else now
    cutoff = now - min_age_days * 86400
    found: list[tuple[Path, float]] = []
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith(SANDBOX_PREFIX):
            continue
        if _is_symlink_or_junction(entry) or not entry.is_dir():
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime <= cutoff:
            found.append((entry, max(now - mtime, 0.0)))
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        default=Path(tempfile.gettempdir()),
                        help="扫描根目录（默认系统临时目录；只看直接子目录）")
    parser.add_argument("--min-age-days", type=float,
                        default=DEFAULT_MIN_AGE_DAYS,
                        help=f"只清理 mtime 早于 N 天的目录"
                             f"（默认 {DEFAULT_MIN_AGE_DAYS:g}）")
    parser.add_argument("--apply", action="store_true",
                        help="真的删除；不加只打印候选（默认 dry-run）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.min_age_days < 0:
        print("--min-age-days 不能为负", file=sys.stderr)
        return 2
    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(f"扫描根目录不存在或不是目录：{root}", file=sys.stderr)
        return 2

    found = candidates(root, args.min_age_days)
    if not args.apply:
        for path, age in found:
            print(f"[dry-run] 将删除 {path}（{age / 86400:.1f} 天）")
        print(f"dry-run：候选 {len(found)} 个（加 --apply 才会删除）")
        return 0

    failed = 0
    for path, age in found:
        replay._remove_sandbox(path)
        if path.exists():
            failed += 1
            print(f"删除失败：{path}", file=sys.stderr)
        else:
            print(f"已删除 {path}（{age / 86400:.1f} 天）")
    print(f"完成：删除 {len(found) - failed}/{len(found)} 个候选")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
