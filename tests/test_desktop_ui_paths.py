"""R189：desktop README 架构表路径同账——adapter / test script / frontendDist / 注入点（W 系续 W25）。

背景（实测，R188 §3 登记、R189 开工复核）：``desktop/README.md`` 架构表
的「桌面适配」行写 ``ui/desktop-adapter.js``，声明它「仅由 Tauri 注入」。
这条声明背后是一条四源路径链——任何一环改了名或挪了目录，其余三环都会
静默失真：

- ``desktop/README.md`` 架构表「桌面适配」行：``ui/desktop-adapter.js``
  （按 README 的基座目录 ``desktop/`` 解析）；
- ``desktop/package.json`` 的 ``test`` script：
  ``node --test ui/desktop-adapter.test.mjs``（同一基座）；
- ``desktop/src-tauri/tauri.conf.json`` 的 ``build.frontendDist``：
  ``../ui``（按 ``desktop/src-tauri/`` 解析）——Tauri 把该目录整体打进
  安装包，指错目录会打出空壳包；
- ``desktop/src-tauri/src/main.rs`` 的注入点：
  ``include_str!("../../ui/desktop-adapter.js")``（按 ``desktop/src-tauri/
  src/`` 解析）——真正执行「仅由 Tauri 注入」的那一行。

登记时只数到前三锚；开工实测补上 ``main.rs`` 的 ``include_str!``——它是
四个引用点里唯一的生产代码，``include_str!`` 是编译期路径，adapter 文件
挪走时 Rust 构建会硬失败，但 README、package.json 与 frontendDist 都
不会红，这正是本判据要钉的边（候选制在实测阶段修正判据覆盖面，同
W18 五源、W13 八源先例）。

W25 把这条边钉成两半：

- **W25a 语料守卫与解析性**：四个引用点各恰一处；按各自基座目录解析后
  全部在磁盘；``frontendDist`` 解析出的目录里 ``index.html`` 在磁盘
  （``main.rs`` 的 ``WebviewUrl::App("index.html")`` 以它为入口，缺了
  就是空壳包）。
- **W25b 同目录同账**：四个字面值逐字钉死；adapter（README 与 main.rs
  两条路解析出的同一个文件）与 test script 引用文件的父目录都等于
  ``frontendDist`` 解析出的目录——四源互相同目录，谁挪走谁先红。

边界：只判架构表「桌面适配」行与上述三个工程引用点——不判 Windows /
macOS 表行（W26/W27 射程）、不判 ``frontendDist`` 的打包行为（CI 的
desktop 工作流负责）、不判 adapter 的运行时行为与测试的执行结果
（``npm test`` / ``cargo test`` 负责）、不判 Rust 侧其他 ``include_str``
（本仓只有这一处引用 ``ui/``）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DESKTOP = REPO_ROOT / "desktop"
SRC_TAURI = DESKTOP / "src-tauri"
README = DESKTOP / "README.md"
PACKAGE_JSON = DESKTOP / "package.json"
TAURI_CONF = SRC_TAURI / "tauri.conf.json"
MAIN_RS = SRC_TAURI / "src" / "main.rs"

ADAPTER_ROW_RX = re.compile(r"^\| 桌面适配 \| `([^`]+)` \|", re.M)
TEST_SCRIPT_RX = re.compile(r"ui/[\w./-]+\.test\.mjs")
INCLUDE_STR_RX = re.compile(r'include_str!\(\s*"([^"]+)"\s*\)')

EXPECTED_ADAPTER = "ui/desktop-adapter.js"
EXPECTED_TEST = "ui/desktop-adapter.test.mjs"
EXPECTED_FRONTEND_DIST = "../ui"
EXPECTED_INCLUDE = "../../ui/desktop-adapter.js"


def _adapter_row_token() -> str:
    matches = ADAPTER_ROW_RX.findall(README.read_text(encoding="utf-8"))
    assert len(matches) == 1, (
        f"desktop/README.md 的「桌面适配」行应恰一处，实测 {len(matches)} 处"
        "——W25 无锚"
    )
    return matches[0].strip()


def _test_script_reference() -> str:
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get(
        "scripts", {}
    )
    references = TEST_SCRIPT_RX.findall(str(scripts.get("test", "")))
    assert len(references) == 1, (
        f"desktop/package.json 的 test script 应恰一处 ui/*.test.mjs 引用，"
        f"实测 {references}——W25 无锚"
    )
    return references[0]


def _frontend_dist() -> str:
    build = json.loads(TAURI_CONF.read_text(encoding="utf-8")).get("build", {})
    assert isinstance(build.get("frontendDist"), str), (
        "tauri.conf.json 缺少 build.frontendDist 字符串值——W25 无锚"
    )
    return build["frontendDist"]


def _include_str_reference() -> str:
    references = [
        target
        for target in INCLUDE_STR_RX.findall(
            MAIN_RS.read_text(encoding="utf-8")
        )
        if "ui/" in target
    ]
    assert len(references) == 1, (
        f"main.rs 引用 ui/ 的 include_str! 应恰一处，实测 {references}"
        "——W25 无锚"
    )
    return references[0]


def _resolve(base: Path, relative: str) -> Path:
    return (base / relative).resolve()


def test_desktop_ui_references_resolve_on_disk() -> None:
    """W25a：四源各恰一处；按各自基座解析后在磁盘；入口 index.html 在。"""
    adapter = _adapter_row_token()
    test_ref = _test_script_reference()
    frontend_dist = _frontend_dist()
    include_ref = _include_str_reference()

    for base, relative, label in (
        (DESKTOP, adapter, "README 架构表"),
        (DESKTOP, test_ref, "package.json test script"),
        (SRC_TAURI / "src", include_ref, "main.rs include_str!"),
    ):
        resolved = _resolve(base, relative)
        assert resolved.is_file(), (
            f"{label}引用的 {relative} 按 {base} 解析后不在磁盘：{resolved}"
        )

    dist_dir = _resolve(SRC_TAURI, frontend_dist)
    assert dist_dir.is_dir(), (
        f"frontendDist 解析出的目录不在磁盘：{dist_dir}"
    )
    assert (dist_dir / "index.html").is_file(), (
        f"frontendDist 目录缺 index.html（main.rs 的 WebviewUrl::App 入口，"
        f"缺了就是空壳包）：{dist_dir / 'index.html'}"
    )


def test_desktop_ui_sources_agree_on_the_same_directory() -> None:
    """W25b：四源字面值逐字钉死；解析出的文件互相同 frontendDist 目录。"""
    adapter = _adapter_row_token()
    test_ref = _test_script_reference()
    frontend_dist = _frontend_dist()
    include_ref = _include_str_reference()

    literals = {
        "README 架构表": (adapter, EXPECTED_ADAPTER),
        "package.json test script": (test_ref, EXPECTED_TEST),
        "tauri frontendDist": (frontend_dist, EXPECTED_FRONTEND_DIST),
        "main.rs include_str!": (include_ref, EXPECTED_INCLUDE),
    }
    drifted = {
        label: (actual, expected)
        for label, (actual, expected) in literals.items()
        if actual != expected
    }
    assert not drifted, f"desktop ui 路径四源字面值漂移：{drifted}"

    dist_dir = _resolve(SRC_TAURI, frontend_dist)
    parents = {
        "README 架构表": _resolve(DESKTOP, adapter).parent,
        "package.json test script": _resolve(DESKTOP, test_ref).parent,
        "main.rs include_str!": _resolve(SRC_TAURI / "src", include_ref).parent,
    }
    mismatched = {
        label: str(parent)
        for label, parent in parents.items()
        if parent != dist_dir
    }
    assert not mismatched, (
        f"desktop ui 四源不同账：frontendDist 解析为 {dist_dir}，"
        f"其余引用落在 {mismatched}——adapter / test / frontendDist 挪目录"
        "必须四处同步"
    )
