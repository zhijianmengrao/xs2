"""R169：npm 引用面——CI / Dockerfile 的脚本与锁文件必须可解析（V 系续 V5）。

背景（实测，R168 §3 登记）：CI 与容器构建里有 8 处 `npm run` / `npm test`
引用与 6 处 `npm ci`，但没有任何判据验证这些名字真的存在：

- `.github/workflows/ci.yml`：frontend 在 `web/` 跑 `npm ci`、`npm run
  lint`、`npm test`、`npm run build`；
- `desktop-macos.yml`：`web/` 跑 `npm ci && npm run build`；同一 step 里
  `cd desktop` 后跑 `npm ci` 与 `npm run build:macos`；
- `desktop-windows.yml`：`web/` 与 `desktop/` 各跑 `npm ci` / `npm run
  build`；
- `Dockerfile`：`WORKDIR /app/web` 下 `npm ci` 与 `npm run build`。

把 `build` 改名、删掉 `lint`、或换目录后忘了 lockfile，CI 会在最靠近
失败点的地方红——但如果引用写错的是非默认分支/矩阵，可能长期没人跑到。
V5 把引用面提前钉住：

- **V5a 脚本引用可解析**：workflow 每个 step 的 `npm run <script>` /
  `npm test` 必须命中该 step 工作目录下 `package.json` 的 scripts 键。
  工作目录 = `working-directory`，否则按 run 脚本里的 `cd <dir>` 顺序
  推进；Dockerfile 按 `WORKDIR` 推进并把 `/app/<x>` 映射回仓库 `<x>`。
  语料守卫要求至少 8 处脚本引用。
- **V5b 锁文件存在**：每个 `npm ci` 的工作目录必须有
  `package-lock.json`（`npm ci` 没有它会直接失败，且不读
  `package.json` 的 range）。语料守卫要求至少 6 处 `npm ci`。

边界：只判 npm 引用与 lockfile 存在——不判脚本内部命令是否正确（那是
脚本自己的事）、不判依赖版本与 lock（`npm ci` 自带的完整性闸门）、
不判 workflow 的矩阵/条件是否真的会跑到（CI 平台语义不在仓库内）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
DOCKERFILE = REPO_ROOT / "Dockerfile"

NPM_RUN_RX = re.compile(r"\bnpm\s+run\s+([A-Za-z0-9:_.-]+)")
NPM_TEST_RX = re.compile(r"\bnpm\s+test\b")
NPM_CI_RX = re.compile(r"\bnpm\s+ci\b")
CD_RX = re.compile(r"^cd\s+([^\s;&|]+)")


def _package_scripts(directory: Path) -> set[str]:
    manifest = directory / "package.json"
    assert manifest.is_file(), (
        f"{directory.relative_to(REPO_ROOT)} 没有 package.json——V5 无锚"
    )
    document = json.loads(manifest.read_text(encoding="utf-8"))
    scripts = document.get("scripts")
    assert isinstance(scripts, dict), (
        f"{manifest.relative_to(REPO_ROOT)} 没有 scripts 映射——V5 无锚"
    )
    return set(scripts)


def _referenced_scripts() -> list[tuple[str, str, Path, str]]:
    """返回 (来源, job/step, 工作目录, 脚本名) 列表。"""
    refs: list[tuple[str, str, Path, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job, spec in (document.get("jobs") or {}).items():
            for number, step in enumerate((spec or {}).get("steps") or [], 1):
                run = str(step.get("run") or "")
                if "npm " not in run:
                    continue
                explicit = step.get("working-directory")
                cwd = (
                    (REPO_ROOT / str(explicit)).resolve()
                    if explicit
                    else REPO_ROOT.resolve()
                )
                label = f"{path.name}:{job}#{number}"
                for token in re.split(r"[;\n]", run):
                    token = token.strip()
                    cd = CD_RX.match(token)
                    if cd:
                        cwd = (cwd / cd.group(1).strip("\"'")).resolve()
                        if REPO_ROOT.resolve() not in cwd.parents and cwd != REPO_ROOT.resolve():
                            raise AssertionError(
                                f"{label}: cd 到仓库外 {cwd}"
                            )
                    for match in NPM_RUN_RX.finditer(token):
                        refs.append((path.name, label, cwd, match.group(1)))
                    if NPM_TEST_RX.search(token):
                        refs.append((path.name, label, cwd, "test"))
    # Dockerfile：按 WORKDIR 推进，容器内 /app/<x> 映射回仓库 <x>。
    workdir = "/"
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        workdir_match = re.match(r"WORKDIR\s+(\S+)", stripped)
        if workdir_match:
            workdir = workdir_match.group(1)
            continue
        if "npm " not in stripped:
            continue
        relative = workdir.lstrip("/")
        if relative.startswith("app/"):
            relative = relative[len("app/"):]
        cwd = (REPO_ROOT / relative).resolve()
        label = f"Dockerfile:{workdir}"
        for match in NPM_RUN_RX.finditer(stripped):
            refs.append(("Dockerfile", label, cwd, match.group(1)))
        if NPM_TEST_RX.search(stripped):
            refs.append(("Dockerfile", label, cwd, "test"))
    return refs


def _ci_directories() -> list[tuple[str, Path]]:
    """返回 (来源标签, 工作目录) 列表，每个 `npm ci` 一条。"""
    out: list[tuple[str, Path]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job, spec in (document.get("jobs") or {}).items():
            for number, step in enumerate((spec or {}).get("steps") or [], 1):
                run = str(step.get("run") or "")
                if not NPM_CI_RX.search(run):
                    continue
                explicit = step.get("working-directory")
                cwd = (
                    (REPO_ROOT / str(explicit)).resolve()
                    if explicit
                    else REPO_ROOT.resolve()
                )
                label = f"{path.name}:{job}#{number}"
                for token in re.split(r"[;\n]", run):
                    token = token.strip()
                    cd = CD_RX.match(token)
                    if cd:
                        cwd = (cwd / cd.group(1).strip("\"'")).resolve()
                    if NPM_CI_RX.search(token):
                        out.append((label, cwd))
    workdir = "/"
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        workdir_match = re.match(r"WORKDIR\s+(\S+)", stripped)
        if workdir_match:
            workdir = workdir_match.group(1)
            continue
        if NPM_CI_RX.search(stripped):
            relative = workdir.lstrip("/")
            if relative.startswith("app/"):
                relative = relative[len("app/"):]
            out.append((f"Dockerfile:{workdir}", (REPO_ROOT / relative).resolve()))
    return out


def test_npm_script_references_resolve() -> None:
    """V5a：CI / Dockerfile 的 npm run / npm test 都命中 scripts 键。"""
    refs = _referenced_scripts()
    assert len(refs) >= 8, (
        f"npm 脚本引用只剩 {len(refs)} 处——V5a 的覆盖面缩水了"
    )
    violations = []
    for source, label, cwd, script in refs:
        scripts = _package_scripts(cwd)
        if script not in scripts:
            violations.append(
                f"{label}: npm 引用 {script!r}，"
                f"{cwd.relative_to(REPO_ROOT)}/package.json 只有 "
                f"{sorted(scripts)}"
            )
    assert not violations, (
        "npm 脚本引用无法解析：\n" + "\n".join(violations)
    )


def test_npm_ci_directories_have_lockfiles() -> None:
    """V5b：每个 npm ci 的工作目录都有 package-lock.json。"""
    directories = _ci_directories()
    assert len(directories) >= 6, (
        f"npm ci 只剩 {len(directories)} 处——V5b 的覆盖面缩水了"
    )
    violations = [
        f"{label}: {cwd.relative_to(REPO_ROOT)} 缺 package-lock.json"
        for label, cwd in directories
        if not (cwd / "package-lock.json").is_file()
    ]
    assert not violations, (
        "npm ci 的工作目录缺锁文件：\n" + "\n".join(violations)
    )
