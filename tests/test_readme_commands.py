"""R176：README 命令引用面——文档命令里的脚本/编排文件必须可解析（V 系续 V6）。

背景（实测，R172 §3 登记）：两份 README 的「从源码运行 / Docker / 开发
与验证」代码块里有 8 处对仓库文件的引用——每份各 4 处：

- ``python run.py``（macOS / Linux 启动命令）；
- ``.\\.venv\\Scripts\\python.exe run.py``（Windows PowerShell 启动命令，
  同一个 ``run.py`` 的 exe 变体）；
- ``docker compose up --build``（不带 ``-f``，要求默认编排文件存在）；
- ``docker compose -f docker-compose.yml config -q``（显式编排文件）。

登记时按「每份 3 条」计（PowerShell 的 ``python.exe`` 变体未计入）；开工
实测为每份 4 条，共 8 条，当前全部可解析——候选制又一次在实测阶段修正
判据自身的覆盖面。

V3 已钉安装文档的 ``pip install -r <file>`` 与 Dockerfile 的 ``COPY``；
V5 钉 CI / Dockerfile 的 npm 引用。README 的 ``python <file>.py`` 与
``docker compose [-f <file>]`` 此前无人判：``run.py`` 改名、编排文件
改名后，README 的快速开始与开发验证命令会直接失效，而 CI 不执行 README
命令，没有任何现有闸门会咬住它。

V6 把这条边钉住：

- **V6a 语料守卫**：两份 README 的 fenced 代码块里，每份至少解析出 3 处
  文件引用（实测 4 处），合计至少 6 处（实测 8 处）；引用面被整体删光时
  判据不能静默空转。
- **V6b 引用可解析**：``python <file>.py`` / ``python.exe <file>.py`` 的
  脚本文件必须存在；``docker compose -f <file>`` 的编排文件必须存在；
  不带 ``-f`` 的 compose 工程子命令（up / config / …）要求默认编排文件
  （``compose.yaml`` / ``compose.yml`` / ``docker-compose.yaml`` /
  ``docker-compose.yml``）至少一个存在。

边界：只扫**两份 README 的 fenced 代码块**——正文散文与行内代码不是
「可复制执行的命令」，不在射程；不判命令参数语义（端口、``--build`` 等
由各自判据 / 运行时负责）；不判 ``python -m <module>``（模块不是文件
引用）；不判 ``cp`` / ``Copy-Item`` 的源文件引用（``.env.example`` 由
W15 直接读取，配置示例文件的读取点另有测试）；compose 子命令只认需要
工程的集合，``docker compose version`` 之类不判。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_DOCS = (REPO_ROOT / "README.md", REPO_ROOT / "README.en.md")

# python / python3 / python3.11 / py，可带 .exe 后缀（PowerShell 的
# ``.\\.venv\\Scripts\\python.exe run.py``）；``-m`` 之类旗标因不含 ``.py``
# 不会命中。脚本名限定 ASCII 路径字符，避免把中文标点带进引用值。
PY_SCRIPT_RX = re.compile(
    r"(?<![\w.-])(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?\s+"
    r"([A-Za-z0-9_./\\-]+\.py)\b"
)
COMPOSE_RX = re.compile(r"(?<![\w-])docker[ -]compose\b(.*)$")
COMPOSE_FILE_RX = re.compile(r"(?:^|\s)(?:-f|--file)[\s=]+(\S+)")

# 需要「有工程文件」才能执行的子命令；version / help 之类不在此列。
COMPOSE_PROJECT_SUBCOMMANDS = frozenset({
    "up", "down", "config", "build", "start", "stop", "restart",
    "ps", "logs", "run", "exec", "create", "pull", "push",
})
# docker compose 的默认文件查找顺序（compose.yaml 优先于 docker-compose.yaml）。
DEFAULT_COMPOSE_NAMES = (
    "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
)

# 语料守卫下限（登记口径每份 3 条；实测 4 条）。新增 README 文档的
# 下限默认 1，防止「只解析到 0 条」的静默空转。
MIN_REFS = {"README.md": 3, "README.en.md": 3}
MIN_TOTAL_REFS = 6


def _command_lines(path: Path):
    """逐个产出 fenced 代码块内的 (行号, 行文本)；围栏行本身跳过。"""
    inside = False
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), 1
    ):
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            yield lineno, line


def _references(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(行号, 种类, 引用值)]。

    种类：``python`` = ``python <file>.py`` 的脚本文件；``compose-file`` =
    ``docker compose -f <file>`` 的编排文件；``compose-default`` = 不带
    ``-f`` 的 compose 工程子命令（引用值为子命令名）。
    """
    refs: list[tuple[int, str, str]] = []
    for lineno, line in _command_lines(path):
        command = line.strip()
        if not command or command.startswith("#"):
            continue
        for match in PY_SCRIPT_RX.finditer(command):
            refs.append((lineno, "python", match.group(1)))
        compose = COMPOSE_RX.search(command)
        if not compose:
            continue
        rest = compose.group(1)
        explicit = COMPOSE_FILE_RX.search(rest)
        if explicit:
            refs.append((lineno, "compose-file", explicit.group(1)))
            continue
        subcommand = next(
            (token for token in rest.split() if not token.startswith("-")), ""
        )
        if subcommand in COMPOSE_PROJECT_SUBCOMMANDS:
            refs.append((lineno, "compose-default", subcommand))
    return refs


def _default_compose_files() -> list[Path]:
    return [
        REPO_ROOT / name
        for name in DEFAULT_COMPOSE_NAMES
        if (REPO_ROOT / name).is_file()
    ]


def test_readme_command_refs_are_parseable() -> None:
    """V6a：两份 README 的 fenced 命令至少各解析出 3 处文件引用。"""
    counts = {path.name: len(_references(path)) for path in README_DOCS}
    short = [
        f"{name}: {count} 处（下限 {MIN_REFS.get(name, 1)} 处）"
        for name, count in counts.items()
        if count < MIN_REFS.get(name, 1)
    ]
    assert not short, (
        "README 命令引用面缩水——判据会静默空转：\n" + "\n".join(short)
    )
    total = sum(counts.values())
    assert total >= MIN_TOTAL_REFS, (
        f"两份 README 合计只解析到 {total} 处文件引用"
        f"（下限 {MIN_TOTAL_REFS} 处）——命令块被删光了？"
    )


def test_readme_command_ref_files_resolve() -> None:
    """V6b：README 命令引用的脚本与编排文件必须存在。"""
    missing: list[str] = []
    defaults = _default_compose_files()
    for path in README_DOCS:
        for lineno, kind, value in _references(path):
            if kind == "compose-default":
                if not defaults:
                    missing.append(
                        f"{path.name}:{lineno}: docker compose {value} 需要"
                        f"默认编排文件，候选 {list(DEFAULT_COMPOSE_NAMES)} "
                        "一个都不存在"
                    )
                continue
            target = REPO_ROOT / value.replace("\\", "/")
            if target.is_file():
                continue
            label = "python" if kind == "python" else "docker compose -f"
            missing.append(f"{path.name}:{lineno}: {label} {value}")
    assert not missing, (
        "README 命令引用的仓库文件不存在（改名脚本/编排文件前必须同步"
        "更新命令）：\n" + "\n".join(missing)
    )
