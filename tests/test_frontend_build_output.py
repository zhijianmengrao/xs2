"""R183：前端构建输出目录同账——Vite 产物目录 ↔ 两处后端路径（W 系续 W21）。

背景（实测，R180 §3 登记、R183 开工复核）：服务版启动链有两处读前端产物：

- ``run.py`` 的 ``dist_dir = web_dir / "dist"``——启动时判断产物是否已
  构建，缺失则自动 ``npm run build``；
- ``src/web_server.py`` 的 ``web_dist = BASE_DIR / "web" / "dist"``——
  FastAPI 把该目录挂到 ``/``。

Vite 侧没有显式 ``build.outDir``，默认值就是 ``dist``。三处当前同账，
但没有任何判据盯着：给 ``web/vite.config.ts`` 加
``build.outDir: "public"`` 后，产物落到 ``web/public``，而 ``run.py``
仍看 ``web/dist``——每次启动都会重新构建、``web_server`` 挂载不到产物；
frontend CI job 只跑 ``npm run build``，不会走 ``run.py``，所以这条边
不会被 CI 咬住。

W21 把这条边钉成两半：

- **W21a 语料守卫**：Vite 配置最多一处 ``outDir``（缺省按 Vite 默认
  ``dist`` 取有效值）；``run.py`` 恰一处 ``dist_dir = web_dir / "<dir>"``；
  ``web_server.py`` 恰一处 ``web_dist = BASE_DIR / "web" / "<dir>"``。
- **W21b 三处同账**：有效 ``outDir`` == ``run.py`` 的子目录 ==
  ``web_server.py`` 的子目录（逐字相等）。

边界：只判**产物目录名**——不判 Vite 的其它构建选项、不判
``web/public`` 静态资源目录（它是 Vite 的输入，不是输出）、不判
``desktop/README.md`` 里 ``web/dist`` 的叙述（V8 只判命令引用）；
不判构建是否真的执行（CI 的 frontend job 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VITE_CONFIG = REPO_ROOT / "web" / "vite.config.ts"
RUN_PY = REPO_ROOT / "run.py"
WEB_SERVER = REPO_ROOT / "src" / "web_server.py"

# Vite 的 build.outDir；缺省值是 "dist"（Vite 官方默认）。
VITE_OUTDIR_RX = re.compile(r"\boutDir\s*:\s*[\"']([^\"']+)[\"']")
RUN_DIST_RX = re.compile(
    r"^\s*dist_dir\s*=\s*web_dir\s*/\s*[\"']([^\"']+)[\"']\s*$", re.M
)
SERVER_DIST_RX = re.compile(
    r"^\s*web_dist\s*=\s*BASE_DIR\s*/\s*[\"']web[\"']\s*/\s*[\"']([^\"']+)[\"']\s*$",
    re.M,
)
DEFAULT_VITE_OUTDIR = "dist"


def _vite_outdir() -> str:
    matches = VITE_OUTDIR_RX.findall(VITE_CONFIG.read_text(encoding="utf-8"))
    assert len(matches) <= 1, (
        f"web/vite.config.ts 解析到 {len(matches)} 处 build.outDir：{matches}"
        "——W21 只认一个有效输出目录"
    )
    return matches[0] if matches else DEFAULT_VITE_OUTDIR


def _backend_dirs() -> tuple[str, str]:
    run_matches = RUN_DIST_RX.findall(RUN_PY.read_text(encoding="utf-8"))
    server_matches = SERVER_DIST_RX.findall(
        WEB_SERVER.read_text(encoding="utf-8")
    )
    assert len(run_matches) == 1, (
        f"run.py 的 dist_dir 赋值应恰一处，实测 {run_matches}——W21 无锚"
    )
    assert len(server_matches) == 1, (
        "src/web_server.py 的 web_dist 挂载路径应恰一处，实测 "
        f"{server_matches}——W21 无锚"
    )
    return run_matches[0], server_matches[0]


def test_frontend_output_sources_are_parseable() -> None:
    """W21a：Vite 有效 outDir 与两处后端目录各解析出唯一值。"""
    vite = _vite_outdir()
    run_dir, server_dir = _backend_dirs()
    for name, value in (
        ("web/vite.config.ts", vite),
        ("run.py", run_dir),
        ("src/web_server.py", server_dir),
    ):
        assert value and "/" not in value and "\\" not in value, (
            f"{name} 的前端输出目录必须是单段目录名：{value!r}"
        )


def test_frontend_output_directories_agree() -> None:
    """W21b：Vite 有效 outDir == run.py == web_server 的产物目录。"""
    vite = _vite_outdir()
    run_dir, server_dir = _backend_dirs()
    if len({vite, run_dir, server_dir}) != 1:
        raise AssertionError(
            "前端构建输出目录不同账："
            f"web/vite.config.ts 有效 outDir={vite!r}，"
            f"run.py dist_dir={run_dir!r}，"
            f"src/web_server.py web_dist={server_dir!r}"
            "——改 outDir 必须同时改两处后端路径（或反过来）"
        )
