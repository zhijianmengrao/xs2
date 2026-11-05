"""R140：scripts/ 引用面钉测——每个脚本三面之一可引用，或在豁免清单。

背景（实测，R139 §7）：23 个 ``scripts/*.py`` 里 **5 个全无引用**——
``_hw_analyze_smoke.py``、``_hw_bench_r16.py``、``_hw_frontend_sim.py``、
``_hw_score_matrix.py``、``_hw_setup_welcome.py``，全部是 R16 时代
（2026-10-23/24）对着本地开发服务器跑的一次性活体探针，已被 R49 的桩
provider + R50 的故障注入取代。R140 将 5 个全部删除（git 历史可取回），
并把「孤儿脚本不再回潮」钉成本文件：

- **V1 引用面**：每个 ``scripts/*.py`` 的文件名必须出现在
  ``tests/*.py``、``.github/workflows/*.yml``、``docs/*.md`` 三面之一的
  文本里，或在 ``ALLOWED_ORPHANS`` 豁免清单中（须带理由）。R45 清过一次
  孤儿，此后没有守门人——本文件就是守门人。
- **V2a CI 引用可解析**：ci.yml（常开闸门）引用的每个
  ``scripts/<file>`` 必须在库。
- **V2b 桌面管线缺失引用冻结**：desktop-macos / desktop-windows /
  replace-desktop-assets（上游继承、tag-only）引用的 8 个本 fork 没有的
  脚本冻结成清单——新增缺失引用或补齐脚本都要显式改清单。

边界：只管 ``.py``（``docker-entrypoint.sh``、``humanware_banner.ps1``
由引用它们的 Dockerfile/文档自然约束）；不判脚本内容对错（各有自己的
测试）；「被 handover 提及」也算引用——历史文档是脚本的合法出处记录。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

# 豁免清单：登记「有意无引用」的脚本与理由。R140 起为空——
# 新增孤儿必须在这里登记理由，或者让它被三面之一引用。
ALLOWED_ORPHANS: dict[str, str] = {}


def _script_names() -> list[str]:
    names = sorted(p.name for p in SCRIPTS.glob("*.py"))
    assert names, "scripts/ 下没有 .py——仓库形态不对？"
    return names


def _referencing_corpus() -> str:
    chunks = []
    for pattern in ("tests/*.py", ".github/workflows/*.yml", "docs/*.md"):
        chunks.extend(
            p.read_text(encoding="utf-8", errors="replace")
            for p in REPO_ROOT.glob(pattern)
        )
    return "\n".join(chunks)


def test_every_script_is_referenced_or_allowlisted() -> None:
    """V1：孤儿脚本必须三面之一可引用，或在豁免清单里登记理由。"""
    corpus = _referencing_corpus()
    orphans = [n for n in _script_names() if n not in corpus]
    unregistered = [n for n in orphans if n not in ALLOWED_ORPHANS]
    stale = [n for n in ALLOWED_ORPHANS if n not in orphans]
    assert not unregistered, (
        f"scripts/ 出现无引用孤儿（tests/CI/docs 三面都没有提及）："
        f"{unregistered}。处置：删除（handover 记账），或在 "
        "ALLOWED_ORPHANS 登记理由。"
    )
    assert not stale, f"豁免清单里的脚本已不存在或已有引用：{stale}"


def test_ci_referenced_scripts_resolve() -> None:
    """V2a：ci.yml（常开闸门）引用的脚本必须全部在库。"""
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8", errors="replace")
    refs = set(re.findall(r"scripts/([A-Za-z0-9_\-]+\.(?:py|sh))", ci))
    assert refs, "ci.yml 没有引用任何 scripts/ 文件——判据失守"
    missing = sorted(r for r in refs if not (SCRIPTS / r).exists())
    assert not missing, f"ci.yml 引用的脚本不存在（闸门会当场碎）：{missing}"


def test_desktop_pipeline_missing_refs_frozen() -> None:
    """V2b：桌面管线（上游继承）缺失脚本引用集合冻结——新增缺失即红。

    desktop-macos/desktop-windows/replace-desktop-assets 是 alikon-art 上游
    继承的发版管线（R31 起按 tag-only 规则运行），引用了 8 个本 fork 没有
    的脚本。这份「已知缺失」被冻结成清单：管线新增对缺失脚本的引用、或
    某脚本补齐/删除导致清单失真，都必须显式改本清单。
    """
    frozen = {
        "desktop-macos.yml": {
            "build_backend.py", "generate_macos_icon.py",
            "install_macos_build_dependencies.py",
            "refresh_official_plugin_lock.py", "smoke_backend.py",
            "verify_bundle.py",
        },
        "desktop-windows.yml": {
            "build_backend.py", "create_update_manifest.py",
            "publish_r2_release.py", "refresh_official_plugin_lock.py",
            "smoke_backend.py", "verify_bundle.py",
        },
        "replace-desktop-assets.yml": {"publish_r2_release.py"},
    }
    for wf_name, expected_missing in frozen.items():
        text = (REPO_ROOT / ".github" / "workflows" / wf_name).read_text(
            encoding="utf-8", errors="replace"
        )
        refs = set(re.findall(r"scripts/([A-Za-z0-9_\-]+\.(?:py|sh))", text))
        missing = {r for r in refs if not (SCRIPTS / r).exists()}
        assert missing == expected_missing, (
            f"{wf_name} 的缺失脚本引用漂移：实缺 {sorted(missing)}，冻结清单 "
            f"{sorted(expected_missing)}。新增引用缺失脚本/补齐脚本都要显式改清单。"
        )


# ------------------------------------------------- R158: 安装文档引用面
# R158（R156 §7 登记）：R140 的 V1/V2 只管 scripts/*.py 与 ci.yml 的引用；
# README×2 / CONTRIBUTING.md 的 `pip install -r <file>` 与 Dockerfile 的
# `COPY <file>` 引用的仓库文件此前无人判——锁文件一改名，所有安装命令
# 同时失效（404 / 构建失败）。V3 把这些引用钉成「必须存在」。
INSTALL_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.en.md",
    REPO_ROOT / "CONTRIBUTING.md",
)
INSTALL_REF_RX = re.compile(r"-r\s+([A-Za-z0-9_.\-/]+)")
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERFILE_COPY_RX = re.compile(r"^COPY\s+(\S+)", re.M)
# 语料守卫下限：引用面被整体删光时判据不能静默空转（V3 的锚是「至少还有」）。
MIN_INSTALL_REFS = {name: n for name, n in (
    ("README.md", 2), ("README.en.md", 2), ("CONTRIBUTING.md", 1),
)}


def _dockerfile_file_copies() -> list[str]:
    """Dockerfile 里「单文件 COPY」的源路径（跳过旗标/目录/通配）。"""
    out = []
    for ref in DOCKERFILE_COPY_RX.findall(DOCKERFILE.read_text(encoding="utf-8")):
        if ref.startswith("--"):
            continue  # COPY --from=… 的首 token 是旗标，第二源在构建器阶段里
        if ref.endswith("/") or ref in (".", "./"):
            continue  # 目录 COPY：目录存在性由构建结果（container-build）判
        if "*" in ref:
            continue  # 通配 COPY：空匹配是合法形态，不在文件判据射程
        out.append(ref)
    return out


def test_install_doc_references_resolve() -> None:
    """V3：安装文档与 Dockerfile 引用的仓库文件必须存在（R158）。"""
    missing: list[str] = []
    for path in INSTALL_DOCS:
        refs = INSTALL_REF_RX.findall(path.read_text(encoding="utf-8-sig"))
        floor = MIN_INSTALL_REFS.get(path.name, 1)
        assert len(refs) >= floor, (
            f"{path.name} 只解析到 {len(refs)} 处 `-r` 安装引用"
            f"（下限 {floor}）——引用面被删光，V3 空转"
        )
        for ref in refs:
            if not (REPO_ROOT / ref).is_file():
                missing.append(f"{path.name}: -r {ref}")
    copy_refs = _dockerfile_file_copies()
    assert copy_refs, "Dockerfile 没有任何单文件 COPY——V3 的镜像面无锚"
    for ref in copy_refs:
        if not (REPO_ROOT / ref).is_file():
            missing.append(f"Dockerfile: COPY {ref}")
    assert not missing, (
        "安装文档 / Dockerfile 引用的仓库文件不存在（改名锁文件前必须"
        "同步改引用）：\n" + "\n".join(missing)
    )
