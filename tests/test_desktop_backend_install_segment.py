"""R219：backend 安装段同账（W 系续 W48）。

背景（实测，R216 §3 登记）：backend 可执行文件的安装位置有两份账——
``build_backend.py`` 用 pathlib 拼装（``runtime_root = desktop_root /
"runtime"``、``backend_dir = runtime_root / "backend"``、可执行名
``determinflow-backend.exe`` if win32 else ``determinflow-backend``），
``desktop-macos.yml`` 的两处 smoke 定位参数按字面路径消费（
``…/Contents/Resources/runtime/backend/determinflow-backend``，L67
构建产物、L78 挂载副本）。段名漂移无人判：打包资源布局挪动（tauri
resources 配置改）只改一边——build 出的 backend 落在新段而 smoke 按
旧段找，CI 到 run 时才炸，或 smoke 冒烟的根本不是打包进去的 backend。

W48 把这条边钉成两半（W32/W34/W38–W47 同型分工）：

- **W48a 语料守卫**：脚本的 runtime/backend 组合行各恰一处；yml 的
  ``runtime/backend/<name>`` 段恰 2 处（段形状值无关）。
- **W48b 段名同账**：脚本拼出的 ``runtime/backend`` 段 == yml 路径
  中的段；脚本的非 win32 可执行名 == yml 段的文件名（两处都等）。

边界：只判段名与可执行名的字面同账——不判 win32 侧的 ``.exe`` 名
（windows smoke 直接调 onedir 产物，另账）、不判 ``Contents/Resources``
前缀（tauri 打包布局，tauri 升级行为）、不判 smoke 的执行行为
（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MACOS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-macos.yml"
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "build_backend.py"

RUNTIME_RX = re.compile(r'runtime_root\s*=\s*desktop_root\s*/\s*"([^"]+)"')
BACKEND_DIR_RX = re.compile(r'backend_dir\s*=\s*runtime_root\s*/\s*"([^"]+)"')
EXE_NAME_RX = re.compile(r'else\s*"([^"]+)"\s*\n\s*\)')
# yml 侧段形状值无关（段名变体也进形状，值由 W48b 同账）；排除引号与空白。
YML_SEGMENT_RX = re.compile(r'runtime/backend[^"\s]*')

EXPECTED_YML_SITES = 2


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_segment_and_name() -> tuple[str, str]:
    text = _text(SCRIPT)
    runtime = RUNTIME_RX.findall(text)
    assert len(runtime) == 1, (
        f"build_backend.py 的 runtime_root 行应恰一处，实测 {len(runtime)} 处"
        "——W48a 语料守卫"
    )
    backend_dir = BACKEND_DIR_RX.findall(text)
    assert len(backend_dir) == 1, (
        f"build_backend.py 的 backend_dir 行应恰一处，实测 "
        f"{len(backend_dir)} 处——W48a 语料守卫"
    )
    exe = EXE_NAME_RX.findall(text)
    assert len(exe) == 1, (
        f"build_backend.py 的可执行名三元应恰一处，实测 {len(exe)} 处"
        "——W48a 语料守卫"
    )
    return f"{runtime[0]}/{backend_dir[0]}", exe[0]


def test_backend_segment_anchors() -> None:
    """W48a：脚本两行 + 可执行名三元各恰一处；yml 段恰 2 处。"""
    _script_segment_and_name()
    segments = YML_SEGMENT_RX.findall(_text(MACOS_WF))
    assert len(segments) == EXPECTED_YML_SITES, (
        f"desktop-macos.yml 的 runtime/backend 段应恰 {EXPECTED_YML_SITES} "
        f"处，实测 {len(segments)} 处——W48a 语料守卫"
    )


def test_backend_segments_agree() -> None:
    """W48b：yml 两处的 `runtime/backend/<名>` 段 == 脚本拼出的段与可执行名。"""
    segment, exe_name = _script_segment_and_name()
    expected = f"{segment}/{exe_name}"
    sites = YML_SEGMENT_RX.findall(_text(MACOS_WF))
    for i, site in enumerate(sites, 1):
        assert site == expected, (
            f"yml 第 {i} 处 smoke 定位段不同账：{site!r} vs 脚本 "
            f"{expected!r}——打包资源布局挪动两边同改"
        )
