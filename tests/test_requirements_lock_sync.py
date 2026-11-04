"""R143：requirements 双源一致性——requirements.txt ⊆ requirements-dev.lock。

背景（实测，R142 §7）：CI 从 ``requirements-dev.lock`` 安装（84 个包的
传递闭包），本地开发从 ``requirements.txt`` 安装（19 个顶层依赖）。两个
来源之间此前没有判据：某人在一边升版本、另一边忘了跟，本地与 CI 就会
跑在不同版本上——那种漂移最难排查（与 R57 注释里「两个 runner 给出互相
矛盾的结论」同族）。实测 2026-11-05：按名覆盖成立（``uvicorn[standard]``
→ lock 裸名 ``uvicorn``，extras 归一）、19 个 ``==`` 钉版全部与 lock
一致。

本文件把两件事钉住（**W 系判据**）：

- **W1 名字覆盖**：requirements.txt 的每个包（extras 归一）必须出现在
  lock 里；
- **W2 版本同账**：requirements.txt 用 ``==V`` 钉版的包，lock 必须对
  同一包钉 ``==V``（逐字相等）。

边界：不反向要求 lock ⊆ req（lock 是闭包，超集是常态）；不解析
环境标记（``; sys_platform …`` 行按整行接受）；不钉 lock 内部的传递
依赖版本（那是锁文件的职责）。注释、``-r``/``-e`` 行跳过。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQ = REPO_ROOT / "requirements.txt"
LOCK = REPO_ROOT / "requirements-dev.lock"

LINE_RX = re.compile(r"^([A-Za-z0-9_\-.]+)(\[[^\]]*\])?\s*(.*)$")
EXACT_RX = re.compile(r"==\s*([^;\s]+)")


def _parse(path: Path) -> dict[str, str | None]:
    """返回 包名（小写，extras 剥离）-> 钉版（``==`` 才有，否则 None）。"""
    out: dict[str, str | None] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = LINE_RX.match(line)
        assert m, f"{path.name} 有解析不了的行：{line!r}"
        spec = m.group(3).strip()
        exact = EXACT_RX.fullmatch(spec) if spec else None
        out[m.group(1).lower()] = exact.group(1).strip() if exact else None
    return out


def test_requirements_names_covered_by_lock() -> None:
    """W1：requirements.txt 的每个包（extras 归一）都在 lock 里。"""
    req, lock = _parse(REQ), _parse(LOCK)
    assert req, "requirements.txt 没有解析到包——判据空转"
    missing = sorted(set(req) - set(lock))
    assert not missing, (
        f"requirements.txt 有而 requirements-dev.lock 没有（本地与 CI 将"
        f"跑在不同依赖上）：{missing}"
    )


def test_pinned_versions_agree() -> None:
    """W2：requirements.txt 的每个 ``==V`` 与 lock 的同包 ``==V`` 逐字相等。"""
    req, lock = _parse(REQ), _parse(LOCK)
    drift = {
        name: (pinned, lock[name])
        for name, pinned in req.items()
        if pinned is not None and lock.get(name) != pinned
    }
    assert not drift, (
        "双源版本漂移（一边升版另一边没跟，本地与 CI 版本分叉）："
        + "; ".join(f"{k}: req=={v[0]} vs lock=={v[1]}" for k, v in drift.items())
    )
