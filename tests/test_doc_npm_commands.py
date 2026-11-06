"""R178：文档 npm 命令引用面——文档里的脚本名与锁文件必须可解析（V 系续 V7）。

背景（实测，R177 §5 登记、R178 开工复核）：V5 只钉 CI / Dockerfile 的
``npm run`` / ``npm test`` / ``npm ci``；V6 只钉两份 README 的
``python <file>.py`` 与 ``docker compose`` 命令。文档里的 npm 命令仍是
无人判的一面：

- ``README.md`` / ``README.en.md`` 的开发验证块各 3 处
  （``lint`` / ``test:extensions`` / ``build``，``cd web`` 后执行）；
- ``CONTRIBUTING.md`` 的本地验证块 4 处（含 ``test:workflow``）与
  1 处 ``npm ci``。

``web/package.json`` 改名或删掉这些 script 后，读者照文档执行才会失败；
CI 从不执行文档命令，没有任何现有闸门会咬住它。

V7 把这条边钉住：

- **V7a 语料守卫**：三份文档的 fenced 代码块里，每份至少解析出 3/3/4 处
  script 引用（实测 10 处），合计至少 9 处；``npm ci`` 至少 1 处。
- **V7b 引用可解析**：按块内 ``cd <dir>``（含 ``(cd web && …)`` 子壳）
  推进工作目录，``npm run <script>`` / ``npm test`` 必须命中该目录
  ``package.json`` 的 ``scripts`` 键；``npm ci`` 的工作目录必须有
  ``package-lock.json``。

边界：只扫三份文档的 fenced 代码块；正文散文与行内代码不是可复制执行的
命令；不判命令参数语义（``--cache`` 等）与 script 内部命令（那是 script
自己的事）；不判 ``cd DeterminFlow`` 这类克隆后的目录名（本地不存在，
后面没有 npm 命令时自然不进射程）；不判 ``desktop/README.md`` 与其它
docs（留作后续轮次）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.en.md",
    REPO_ROOT / "CONTRIBUTING.md",
)

NPM_RUN_RX = re.compile(r"\bnpm\s+run\s+([A-Za-z0-9:_.-]+)")
NPM_TEST_RX = re.compile(r"\bnpm\s+test\b")
NPM_CI_RX = re.compile(r"\bnpm\s+ci\b")
CD_RX = re.compile(r"^\s*\(?cd\s+([^\s&)]+)")

# 登记口径每份 3/3/4 处（README×2 + CONTRIBUTING），实测合计 10 处；
# 新增文档的下限默认 1，防止「解析到 0 条」的静默空转。
MIN_SCRIPT_REFS = {"README.md": 3, "README.en.md": 3, "CONTRIBUTING.md": 4}
MIN_TOTAL_SCRIPT_REFS = 9
MIN_NPM_CI_REFS = 1


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
    assert not inside, f"{path.name} 的 fenced 代码块未闭合——V7 会漏扫"


def _references(path: Path) -> list[tuple[int, Path, str, str]]:
    """返回 [(行号, 工作目录, 种类, 值)]。

    种类：``script`` = ``npm run <name>`` / ``npm test``；``ci`` =
    ``npm ci``。工作目录按块内 ``cd`` 顺序推进，每个 fenced 块重置。
    """
    refs: list[tuple[int, Path, str, str]] = []
    for block in _fenced_blocks(path):
        cwd = REPO_ROOT
        for lineno, line in block:
            command = line.strip()
            if not command or command.startswith("#"):
                continue
            for token in re.split(r"\s*(?:&&|;)\s*", command):
                token = token.strip().strip("()")
                if not token:
                    continue
                cd = CD_RX.match(token)
                if cd:
                    cwd = (cwd / cd.group(1).strip("\"'")).resolve()
                    continue
                for match in NPM_RUN_RX.finditer(token):
                    refs.append((lineno, cwd, "script", match.group(1)))
                if NPM_TEST_RX.search(token):
                    refs.append((lineno, cwd, "script", "test"))
                if NPM_CI_RX.search(token):
                    refs.append((lineno, cwd, "ci", ""))
    return refs


def _package_scripts(directory: Path) -> set[str]:
    manifest = directory / "package.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    scripts = document.get("scripts")
    assert isinstance(scripts, dict), (
        f"{manifest.relative_to(REPO_ROOT)} 没有 scripts 映射——V7 无锚"
    )
    return set(scripts)


def test_documented_npm_script_refs_are_parseable() -> None:
    """V7a：三份文档的 fenced npm 命令至少解析出 10 处引用。"""
    counts: dict[str, int] = {}
    ci_total = 0
    for path in DOCS:
        refs = _references(path)
        counts[path.name] = sum(1 for _, _, kind, _ in refs if kind == "script")
        ci_total += sum(1 for _, _, kind, _ in refs if kind == "ci")
    short = [
        f"{name}: {count} 处（下限 {MIN_SCRIPT_REFS.get(name, 1)} 处）"
        for name, count in counts.items()
        if count < MIN_SCRIPT_REFS.get(name, 1)
    ]
    assert not short, (
        "文档 npm 命令引用面缩水——判据会静默空转：\n" + "\n".join(short)
    )
    total = sum(counts.values())
    assert total >= MIN_TOTAL_SCRIPT_REFS, (
        f"三份文档合计只解析到 {total} 处 script 引用"
        f"（下限 {MIN_TOTAL_SCRIPT_REFS} 处）——命令块被删光了？"
    )
    assert ci_total >= MIN_NPM_CI_REFS, (
        f"三份文档只解析到 {ci_total} 处 npm ci（下限 {MIN_NPM_CI_REFS} 处）"
        "——本地验证块的锁文件检查面消失"
    )


def test_documented_npm_scripts_and_lockfiles_resolve() -> None:
    """V7b：文档引用的 script 名必须存在，npm ci 必须有锁文件。"""
    missing: list[str] = []
    for path in DOCS:
        for lineno, cwd, kind, value in _references(path):
            label = f"{path.name}:{lineno}"
            manifest = cwd / "package.json"
            if not manifest.is_file():
                missing.append(
                    f"{label}: npm 命令的工作目录 {cwd} 没有 package.json"
                )
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
        "文档 npm 命令引用的 scripts / 锁文件不存在（改名 script 或移动"
        "锁文件前必须同步更新文档）：\n" + "\n".join(missing)
    )
