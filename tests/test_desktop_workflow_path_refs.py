"""R241：workflow 路径字面多源同账（W 系续 W64）。

背景（实测，R240 §3 登记）：三份 desktop workflow 里对
``.github/workflows/*.yml`` 的字面引用恰 **5 处**——desktop-windows.yml
的 ``paths`` 自引用（L12）、可复用调用 ``uses:``（L150）、
desktop-macos.yml 的 ``paths`` 自引用（L9）、replace-desktop-assets.yml
provenance 元组的两个 ``run['path']`` 期望值（L43/L45）。W32 只钉
``desktop/scripts/*`` 引用面（17 处），workflow 路径这一族没有锚：
文件改名 / 引用改名而对面没跟 → ``run['path']`` 校验在应急通道当场
失败（``build must be successful and match exact source/workflow``）、
可复用 workflow 起不来。

W64 把这条边钉成两半：

- **W64a 语料守卫**：三份文件的引用总数恰 5；路径条目（``paths`` 列表项）
  恰 2、本地 ``uses:`` 恰 1、replace 元组路径恰 2。
- **W64b 多源同账**：自引用 == 该文件自身文件名（两个 producer 各 1 处）；
  全部引用逐处可解析到磁盘文件；replace 元组的两条路径 ↔ 平台（
  ``desktop-<platform>.yml``）↔ 该 producer 恰 1 个非诊断 artifact
  模板（模板小写含平台名）——模板与清单的展开恰等由 W63 负责，这里
  只钉「哪个文件是哪个平台的 producer」。

边界：只判路径字面本身——不判 workflow 触发条件、不判 ``uses`` 的
``secrets``/``with`` 传参（W57/W58 系）、不判 artifact 名展开（W63）、
不判 GitHub 解析行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DESKTOP_WINDOWS = "desktop-windows.yml"
DESKTOP_MACOS = "desktop-macos.yml"
REPLACE = "replace-desktop-assets.yml"
PRODUCERS = (DESKTOP_WINDOWS, DESKTOP_MACOS)

# paths 列表项：`- ".github/workflows/x.yml"` / `- .github/workflows/x.yml`
PATH_ITEM_RX = re.compile(
    r'^\s*-\s*"?\.github/workflows/([A-Za-z0-9_.-]+\.yml)"?\s*$', re.M
)
# 本地可复用调用：`uses: ./.github/workflows/x.yml`
USES_RX = re.compile(
    r'^\s*uses:\s*"?\./\.github/workflows/([A-Za-z0-9_.-]+\.yml)"?\s*$', re.M
)
# 任意位置的字面引用（用于总数与逐处可解析）
ALL_REF_RX = re.compile(r"\.github/workflows/([A-Za-z0-9_.-]+\.yml)")
# provenance heredoc 内的元组路径
TUPLE_PATH_RX = re.compile(r"'\.github/workflows/([A-Za-z0-9_.-]+\.yml)'")
HEREDOC_RX = re.compile(r"python - <<'PY'\n(.*?)\n {10}PY\n", re.S)
TUPLE_RX = re.compile(
    r"\('(\w+)',\s*'([A-Z_]+)',\s*'([^']+\.yml)',\s*\[(.*?)\]\)", re.S
)

EXPECTED_TOTAL_REFS = 5
EXPECTED_PATH_ITEMS = 2
EXPECTED_USES = 1
EXPECTED_TUPLES = 2
EXPECTED_PLATFORMS = {"windows", "macos"}


def _text(name: str) -> str:
    path = WORKFLOWS / name
    assert path.is_file(), f"workflow 不在：{path}"
    return path.read_text(encoding="utf-8")


def _replace_heredocs() -> list[str]:
    heredocs = HEREDOC_RX.findall(_text(REPLACE))
    assert len(heredocs) == 2, (
        f"replace workflow 的 <<'PY' heredoc 应恰 2 个，实测 {len(heredocs)} 个"
        "——W64/W66 的语料形态变了"
    )
    return heredocs


def _producer_artifact_templates(name: str) -> list[str]:
    """producer 的非诊断 artifact 名模板（排除 *-diagnostics-*）。"""
    document = yaml.safe_load(_text(name))
    jobs = document.get("jobs") if isinstance(document, dict) else None
    assert isinstance(jobs, dict) and jobs, f"{name} 没有 jobs——W64 无锚"
    templates: list[str] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            if not str(step.get("uses") or "").startswith(
                "actions/upload-artifact"
            ):
                continue
            template = str((step.get("with") or {}).get("name") or "")
            if template and not template.startswith("installer-diagnostics"):
                templates.append(template)
    return templates


def test_workflow_path_references_shape() -> None:
    """W64a：引用总数恰 5；路径条目 2 / uses 1 / 元组 2。"""
    total = sum(len(ALL_REF_RX.findall(_text(n))) for n in PRODUCERS + (REPLACE,))
    assert total == EXPECTED_TOTAL_REFS, (
        f"三份 workflow 对 .github/workflows/*.yml 的字面引用应恰 "
        f"{EXPECTED_TOTAL_REFS} 处，实测 {total} 处——W64a 语料守卫"
    )
    path_items = [
        ref for n in PRODUCERS for ref in PATH_ITEM_RX.findall(_text(n))
    ]
    assert len(path_items) == EXPECTED_PATH_ITEMS, (
        f"producer 的 paths 自引用应恰 {EXPECTED_PATH_ITEMS} 处，实测 "
        f"{len(path_items)} 处（{path_items}）——W64a 语料守卫"
    )
    uses = [ref for n in PRODUCERS for ref in USES_RX.findall(_text(n))]
    assert len(uses) == EXPECTED_USES, (
        f"producer 的本地 uses: 应恰 {EXPECTED_USES} 处，实测 {len(uses)} 处"
        f"（{uses}）——W64a 语料守卫"
    )
    tuples = TUPLE_RX.findall(_replace_heredocs()[0])
    assert len(tuples) == EXPECTED_TUPLES, (
        f"replace provenance 元组应恰 {EXPECTED_TUPLES} 个，实测 "
        f"{len(tuples)} 个——W64a 语料守卫"
    )
    tuple_paths = TUPLE_PATH_RX.findall(_replace_heredocs()[0])
    assert len(tuple_paths) == EXPECTED_TUPLES, (
        f"replace 元组内的 workflow 路径应恰 {EXPECTED_TUPLES} 条，实测 "
        f"{len(tuple_paths)} 条（{tuple_paths}）——W64a 语料守卫"
    )


def test_workflow_path_references_agree() -> None:
    """W64b：自引用 == 自身文件名；逐处可解析；元组路径 ↔ 平台 ↔ producer。"""
    violations: list[str] = []

    for name in PRODUCERS:
        items = PATH_ITEM_RX.findall(_text(name))
        expected = [name] * len(items)
        if items != expected:
            violations.append(
                f"{name}: paths 自引用 {items} != 自身文件名 {expected}"
                "——改名后触发面跟着丢"
            )

    referenced = {
        ref
        for name in PRODUCERS + (REPLACE,)
        for ref in ALL_REF_RX.findall(_text(name))
    }
    missing = sorted(ref for ref in referenced if not (WORKFLOWS / ref).is_file())
    if missing:
        violations.append(f"引用指向不存在的 workflow：{missing}")
    if referenced != set(PRODUCERS):
        violations.append(
            f"被引用的 workflow 集合 {sorted(referenced)} != "
            f"{sorted(PRODUCERS)}——多引/漏引"
        )

    tuples = TUPLE_RX.findall(_replace_heredocs()[0])
    platforms = {platform for platform, _, _, _ in tuples}
    if platforms != EXPECTED_PLATFORMS:
        violations.append(
            f"replace 元组的平台集合 {sorted(platforms)} != "
            f"{sorted(EXPECTED_PLATFORMS)}"
        )
    for platform, _env, workflow, _artifacts in tuples:
        expected_name = f"desktop-{platform}.yml"
        if Path(workflow).name != expected_name:
            violations.append(
                f"{platform}: 元组路径 {workflow} 不是 {expected_name}"
                "——平台与 producer 错位"
            )
            continue
        templates = _producer_artifact_templates(expected_name)
        if len(templates) != 1:
            violations.append(
                f"{expected_name}: 非诊断 artifact 模板应恰 1 个，实测 "
                f"{len(templates)} 个（{templates}）"
            )
        elif platform.lower() not in templates[0].lower():
            violations.append(
                f"{expected_name}: artifact 模板 {templates[0]!r} 不含平台名 "
                f"{platform!r}——元组把两个平台指到同一个 producer"
            )

    assert not violations, (
        "workflow 路径字面不同账：\n" + "\n".join(violations)
    )
