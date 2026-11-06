"""R182：desktop 管线命令引用面——发布文档里的脚本 / npm 命令必须可解析（V 系续 V8）。

背景（实测，R180 §3 登记、R182 开工复核）：``desktop/README.md`` 是桌面
full 包唯一的人读构建说明——CI 只跑脚本本身，从不执行文档里的命令；
V7 只扫 ``README.md`` / ``README.en.md`` / ``CONTRIBUTING.md``，明确把
桌面 README 留在射程外。文档里的引用面因此是第二份账：

- ``python desktop/scripts/*.py``：stage_defaults / build_backend（本地
  与 macOS 各一次）/ smoke_backend ×2 / verify_bundle ×2 /
  install_macos_build_dependencies / generate_macos_icon；
- ``npm run`` / ``npm test``：``build``（web）、``test``（desktop）、
  ``build:macos``（desktop）；
- ``npm ci``：web 与 desktop 各一次。

R180 §3 按逐行口径登记 8 处脚本引用——macOS 的 ``build_backend`` 脚本名
在 ``\\`` 续行上，单独一行没有 ``python`` 前缀。V8 把 ``\\`` 续行合并为
同一条命令后实测 **9 处**；V8a 仍用登记下限 8，避免把口径修正本身变成
判据的失败面。

V8 把这条边钉住：

- **V8a 语料守卫**：fenced 代码块里至少 8 处 ``python desktop/scripts/
  *.py``、至少 3 处 ``npm run`` / ``npm test``、至少 2 处 ``npm ci``。
  命令块被整体删光时判据不能静默空转。
- **V8b 引用可解析**：脚本文件必须存在；npm script 必须命中该工作目录
  ``package.json`` 的 ``scripts``；``npm ci`` 的工作目录必须有
  ``package-lock.json``。工作目录按块内 ``cd``（含 ``(cd … && …)``
  子壳）推进。

边界：只扫 ``desktop/README.md`` 的 fenced 代码块；正文散文与行内代码
不是可复制执行的命令；不判 ``python -m <module>``（模块不是文件引用）、
不判 ``cargo test`` 与命令参数语义；不判其它 docs / README（V6/V7 已
覆盖各自的面）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "desktop" / "README.md"

# python / python3 / python3.11，可带 .exe 后缀；脚本限定在 desktop/scripts/
# 下（V8 的管线面），避免把未来的其它脚本静默纳入或漏出。
PY_SCRIPT_RX = re.compile(
    r"(?<![\w.-])(?:python(?:3(?:\.\d+)?)?)(?:\.exe)?\s+"
    r"(desktop/scripts/[A-Za-z0-9_.-]+\.py)\b"
)
NPM_RUN_RX = re.compile(r"\bnpm\s+run\s+([A-Za-z0-9:_.-]+)")
NPM_TEST_RX = re.compile(r"\bnpm\s+test\b")
NPM_CI_RX = re.compile(r"\bnpm\s+ci\b")
CD_RX = re.compile(r"^\s*\(?cd\s+([^\s&)]+)")

# 登记下限（R180 §3）：8 处脚本引用 / 3 处 npm run|test / 2 处 npm ci。
# 续行合并后实测脚本引用为 9 处（macOS build_backend 的脚本名在续行上）。
MIN_SCRIPT_REFS = 8
MIN_NPM_SCRIPT_REFS = 3
MIN_NPM_CI_REFS = 2


def _fenced_blocks(path: Path):
    """逐个产出 fenced 代码块内的 [(行号, 行文本)]；围栏行本身跳过。"""
    inside = False
    block: list[tuple[int, str]] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if line.startswith("```"):
            if inside:
                yield block
            block = []
            inside = not inside
            continue
        if inside:
            block.append((lineno, line))
    assert not inside, f"{path.name} 的 fenced 代码块未闭合——V8 会漏扫"


def _logical_lines(block: list[tuple[int, str]]):
    """把块内的 ``\\`` 续行合并为一条逻辑命令行，产出 (起始行号, 命令)。"""
    buffer = ""
    start: int | None = None
    for lineno, line in block:
        text = line.strip()
        if start is None:
            start = lineno
            buffer = text
        else:
            buffer = f"{buffer} {text}"
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip()
            continue
        yield start, buffer
        buffer = ""
        start = None
    if start is not None:
        yield start, buffer


def _references(path: Path) -> list[tuple[int, Path, str, str]]:
    """返回 [(行号, 工作目录, 种类, 值)]。

    种类：``script-file`` = ``python desktop/scripts/<name>.py``；``script``
    = ``npm run <name>`` / ``npm test``；``ci`` = ``npm ci``。块内独立的
    ``cd`` 推进基准目录；``(cd … && …)`` 的 ``cd`` 只在本行子壳内生效，
    不改变后续行的基准（README 同一块里既有 ``(cd web …)`` 又有
    ``(cd desktop …)``）。
    """
    refs: list[tuple[int, Path, str, str]] = []
    for block in _fenced_blocks(path):
        cwd = REPO_ROOT
        for lineno, command in _logical_lines(block):
            command = command.strip()
            if not command or command.startswith("#"):
                continue
            subshell = command.startswith("(") and command.endswith(")")
            inner = command[1:-1] if subshell else command
            local_cwd = cwd
            for token in re.split(r"\s*(?:&&|;)\s*", inner):
                token = token.strip().strip("()")
                if not token:
                    continue
                cd = CD_RX.match(token)
                if cd:
                    target = (local_cwd / cd.group(1).strip("\"'")).resolve()
                    if subshell:
                        local_cwd = target
                    else:
                        cwd = target
                    continue
                base = local_cwd if subshell else cwd
                for match in PY_SCRIPT_RX.finditer(token):
                    refs.append((lineno, base, "script-file", match.group(1)))
                for match in NPM_RUN_RX.finditer(token):
                    refs.append((lineno, base, "script", match.group(1)))
                if NPM_TEST_RX.search(token):
                    refs.append((lineno, base, "script", "test"))
                if NPM_CI_RX.search(token):
                    refs.append((lineno, base, "ci", ""))
    return refs


def _package_scripts(directory: Path) -> set[str]:
    manifest = directory / "package.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    scripts = document.get("scripts")
    assert isinstance(scripts, dict), (
        f"{manifest.relative_to(REPO_ROOT)} 没有 scripts 映射——V8 无锚"
    )
    return set(scripts)


def test_desktop_pipeline_commands_are_parseable() -> None:
    """V8a：desktop/README 的命令块至少 8 / 3 / 2 处引用。"""
    refs = _references(README)
    script_files = [value for _, _, kind, value in refs if kind == "script-file"]
    npm_scripts = [value for _, _, kind, value in refs if kind == "script"]
    npm_ci = [value for _, _, kind, value in refs if kind == "ci"]

    assert len(script_files) >= MIN_SCRIPT_REFS, (
        f"desktop/README.md 只解析到 {len(script_files)} 处 "
        f"python desktop/scripts/*.py 引用（下限 {MIN_SCRIPT_REFS} 处）"
        "——命令块被删光了？"
    )
    assert len(npm_scripts) >= MIN_NPM_SCRIPT_REFS, (
        f"desktop/README.md 只解析到 {len(npm_scripts)} 处 npm run/test "
        f"引用（下限 {MIN_NPM_SCRIPT_REFS} 处）"
    )
    assert len(npm_ci) >= MIN_NPM_CI_REFS, (
        f"desktop/README.md 只解析到 {len(npm_ci)} 处 npm ci "
        f"（下限 {MIN_NPM_CI_REFS} 处）——本地验证块的锁文件检查面消失"
    )


def test_desktop_pipeline_command_targets_resolve() -> None:
    """V8b：脚本文件、npm scripts 与锁文件全部可解析。"""
    missing: list[str] = []
    for lineno, cwd, kind, value in _references(README):
        label = f"desktop/README.md:{lineno}"
        if kind == "script-file":
            target = (REPO_ROOT / value).resolve()
            if not target.is_file():
                missing.append(f"{label}: 脚本不存在 {value}")
            continue
        manifest = cwd / "package.json"
        if not manifest.is_file():
            missing.append(f"{label}: npm 命令的工作目录 {cwd} 没有 package.json")
            continue
        if kind == "script":
            try:
                scripts = _package_scripts(cwd)
            except (OSError, ValueError) as exc:
                missing.append(f"{label}: 读 {manifest} 失败: {exc}")
                continue
            if value not in scripts:
                missing.append(
                    f"{label}: npm run {value} 不在 "
                    f"{manifest.relative_to(REPO_ROOT)} 的 scripts 里"
                )
        elif not (cwd / "package-lock.json").is_file():
            missing.append(
                f"{label}: npm ci 的工作目录 {cwd} 没有 package-lock.json"
            )
    assert not missing, (
        "desktop/README.md 引用的脚本 / npm script / 锁文件不存在"
        "（改名或移动前必须同步更新发布文档）：\n" + "\n".join(missing)
    )
