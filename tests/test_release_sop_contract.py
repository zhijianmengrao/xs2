"""R138：RELEASE_SOP ↔ verify_release 退出码契约。

背景（实测，R137 §7 预告）：``scripts/verify_release.py`` 自 R132 起把
发版验收判决分成 0/1/2/4 四类互不冒充的退出码（``EXIT_PASS/FAIL/USAGE/
SHAPE``），但 ``docs/RELEASE_SOP.md`` §5 是发版人的操作手册，**此前一句
退出码都没教**——操作者看到非 0 退出时无法区分「判了不合格（停发）」
和「环境问题（修了重跑）」。R138 给 SOP 补退出码判决表，并把两侧钉成
同账：

- **T1 表与常量同账**：SOP 表的代码集合必须等于脚本的 ``EXIT_*`` 常量
  集合；每行的脚本输出标记（``[fail]``/``[error]``/``[shape]``/
  ``ALL CHECKS PASSED``）必须是脚本里真实存在的字面前缀——改任何一侧，
  另一侧判红。
- **T2 SOP 引用面**：SOP 里提到的每个 ``scripts/<name>.py`` 必须在库
  （导航层引用判据在 SOP 上的延伸——SOP 不在 R133 的三份活文档清单里，
  它的引用面由本文件守）。
- **T3 调用形状**：SOP §5 的验收命令必须带 ``--tag`` 与 ``--assets-dir``
  （R32 的参数化接口），参数被改名/删除时 SOP 先红。

边界：SOP 其余内容（下载 URL、密钥保管、R29 历史）不钉——本文件只守
「判决表 = 脚本行为」与「引用可解析」；验收判什么由 R132 的
``test_verify_release.py`` 担保。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOP = REPO_ROOT / "docs" / "RELEASE_SOP.md"
SCRIPT = REPO_ROOT / "scripts" / "verify_release.py"

MARKERS = {
    "0": "ALL CHECKS PASSED",
    "1": "[fail]",
    "2": "[error]",
    "4": "[shape]",
}


def _sop_text() -> str:
    return SOP.read_text(encoding="utf-8")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_sop_exit_table_matches_script_constants() -> None:
    """T1：SOP 退出码表 == 脚本 EXIT_* 常量（值与输出标记双向同账）。"""
    sop = _sop_text()
    script = _script_text()
    constants = dict(
        re.findall(r"^EXIT_(PASS|FAIL|USAGE|SHAPE) = (\d+)$", script, re.M)
    )
    assert set(constants.values()) == {"0", "1", "2", "4"}, (
        f"脚本退出码常量漂移（R132 分类是 0/1/2/4）：{constants}"
    )
    table_codes = set(re.findall(r"^\| (\d) \|", sop, re.M))
    assert table_codes == set(constants.values()), (
        f"SOP 退出码表与脚本常量不同账：表 {sorted(table_codes)} vs "
        f"脚本 {sorted(constants.values())}——改哪一侧都要同步另一侧"
    )
    for code, marker in MARKERS.items():
        row = next(
            (l for l in sop.splitlines() if l.startswith(f"| {code} |")), ""
        )
        assert marker in row, (
            f"SOP 表第 {code} 行缺脚本输出标记 {marker!r}：{row.strip()[:80]}"
        )
    for marker in ("[fail]", "[error]", "[shape]"):
        assert marker in script, (
            f"脚本输出前缀 {marker!r} 被改名——SOP 表与 T1 的锚点同步失效，"
            "请连同 docs/RELEASE_SOP.md 的判决表一起改"
        )


def test_sop_script_references_resolve() -> None:
    """T2：SOP 提到的 scripts/*.py 都在库（导航层判据在 SOP 上的延伸）。"""
    sop = _sop_text()
    refs = set(re.findall(r"`?scripts/([A-Za-z0-9_\-]+\.py)`?", sop))
    assert refs, "SOP 没有引用任何脚本——引用面判据失守"
    missing = sorted(r for r in refs if not (REPO_ROOT / "scripts" / r).exists())
    assert not missing, f"SOP 引用了不存在的脚本：{missing}"


def test_sop_release_acceptance_invocation_shape() -> None:
    """T3：SOP §5 的验收命令保留 --tag 与 --assets-dir（R32 参数化接口）。"""
    sop = _sop_text()
    section = sop.split("## 5.", 1)[1]
    fence = re.search(r"```bash\n(.*?)```", section, re.S)
    assert fence, "SOP §5 没有 bash 代码块"
    command = next(
        (l for l in fence.group(1).splitlines() if "verify_release.py" in l),
        "",
    )
    assert command, "SOP §5 没有验收命令行"
    for flag in ("--tag", "--assets-dir"):
        assert flag in command, (
            f"验收命令缺 {flag}（R32 参数化接口被改名/删除？）：{command.strip()}"
        )
