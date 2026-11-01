"""Test-process fallback for the community Executor Pool defaults.

Community runtime defaults are process mode with four members. Tests keep the
supported environment-variable rollback to inline/1 unless a case overrides it.
"""

from __future__ import annotations

import os

os.environ.setdefault("DETERMINFLOW_WORKFLOW_EXECUTOR_MODE", "inline")
os.environ.setdefault("DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT", "1")

import pathlib
import re
import stat
import sys
import tempfile

import pytest


def _probe_dir_root() -> pathlib.Path:
    """测试探针目录的固定落点（data/system 下，R37 治理）。

    ``tempfile.mkdtemp()`` 不带 ``dir=`` 时按 ``TEMP → TMP → CWD`` 回落；本机
    %TEMP% 受 ACL 限制时落点即进程工作目录（PROJECT_INFO 注意事项 8），仓库根
    曾积累 41 个 ``git-transport-probe-*`` 残留。显式 ``dir=`` 钉住位置，与
    executor-runtimes（R21）同款治理。
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "data" / "system" / "test-probes"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _rmtree_force(path: pathlib.Path) -> None:
    """删除探针目录；git clone 产物的 pack 文件是只读的，必须先解只读。

    此前 ``rmtree(ignore_errors=True)`` 遇只读文件静默跳过，正是 41 个探针
    目录残留的直接原因。兼容 3.11（onerror）与 3.12+（onexc）。
    """
    import shutil

    def _chmod_and_retry(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    try:
        shutil.rmtree(path, onexc=_chmod_and_retry)
    except TypeError:  # Python 3.11 无 onexc
        shutil.rmtree(path, onerror=_chmod_and_retry)


def _can_create_symlink() -> bool:
    """Probe the actual OS capability without changing production behavior."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="symlink-probe-", dir=_probe_dir_root()))
    link = root / "link"
    target = root / "target"
    target.mkdir()
    try:
        os.symlink(target, link)
        link.unlink(missing_ok=True)
        return True
    except OSError:
        return False
    finally:
        link.unlink(missing_ok=True)
        target.rmdir()
        root.rmdir()


_CAN_CREATE_SYMLINK = _can_create_symlink()

# --- Git-for-Windows msys transport (Windows) -----------------------------
# git's clone/fetch/push/ls-remote transports exec `Git\usr\bin\sh.exe`. msys2
# first opens the shared `\BaseNamedObjects\msys-2.0*` object left by an earlier
# msys process; when this session cannot attach that object, the child dies at
# boot with `NtCreateDirectoryObject(...): 0xC0000022`.
#
# **Why a session cannot attach** (R81, measured on this machine): the object
# carries the integrity level of the process that created it, implicitly — its
# DACL grants Everyone `0x2000F` (read + DIRECTORY_CREATE_*), and yet a Low-IL
# opener is denied every write right with 0xC0000022 while a High-IL opener gets
# them. A synthetic object with the same DACL reproduced the same matrix: created
# by High -> Low denied, created by Low -> Low allowed. Integrity level is
# inherited from the parent token, but executables on F: are forced down to Low:
# `F:\...\.venv\python.exe` runs Low even under a High shell, and the same
# python.exe copied to C: inherits the shell's High. A Low process spawning
# `C:\Windows\py.exe` stays Low, so the fix is to start pytest from a High shell
# (Git Bash / PowerShell here) with a C: launcher. The skip reason names the
# mechanism, the fact that the object was created above this launcher, and that
# prescription — never a "this token is Low" causal claim: the object side may be
# higher than any token we can get. `tests/test_msys_attribution.py` pins both
# halves (R81 restored the prescription that R71 had dropped on R70's evidence).
# Converting exactly those failures into skips keeps `pytest -q` meaningful — a
# genuine git defect carries no msys signature and still fails loudly. Native git
# verbs (init/add/commit/rev-parse) are unaffected and keep running.
_MSYS_BOOT_FAILURE = "NtCreateDirectoryObject"

# 这些模块的用例依赖 git 远程传输（clone/fetch）。传输不可用时，模块内的失败
# 无法归因（生产代码会把 git 错误吞成空结果/断言失败），因此一并转成 skip。
# 传输可用时（探测通过）本钩子完全不介入，真实缺陷照常失败。
_GIT_TRANSPORT_MODULES = frozenset({
    "test_plugin_store",
    "test_plugin_routes",
    "test_plugin_host_integration",
    "test_plugin_registry",
    "test_plugin_source_catalog",
    "test_plugin_resource_namespace",
})

_git_transport_blocked: "bool | None" = None


def _git_transport_blocked_probe() -> bool:
    """True when a local `git clone` fails *specifically* due to msys boot.

    Keyed on the exact msys signature so a genuine git defect (missing repo, bad
    URL, permissions) is never classified as an environment limitation. Cached
    per process; any non-msys outcome means "do not skip anything".
    """
    global _git_transport_blocked
    if _git_transport_blocked is not None:
        return _git_transport_blocked
    if os.name != "nt":
        _git_transport_blocked = False
        return False

    import shutil
    import subprocess

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="git-transport-probe-", dir=_probe_dir_root()))
    blocked = False
    try:
        def run(*args: str) -> "subprocess.CompletedProcess[str]":
            return subprocess.run(["git", *args], cwd=str(workdir), capture_output=True,
                                  text=True, errors="replace", check=False)

        # git 缺失或仓库初始化失败：让测试照常失败，不伪装成 msys 问题。
        if run("--version").returncode != 0:
            pass
        else:
            source = workdir / "source"
            source.mkdir()
            if run("init", "-q", "-b", "main", "source").returncode == 0:
                (source / "payload.txt").write_text("probe", encoding="utf-8")
                subprocess.run(["git", "-C", str(source), "add", "."],
                               capture_output=True, check=False)
                subprocess.run(["git", "-C", str(source), "-c", "user.name=probe",
                                "-c", "user.email=probe@invalid", "commit",
                                "-q", "-m", "probe"], capture_output=True, check=False)
                clone = run("clone", "--quiet", "--no-hardlinks", "source", "clone")
                blocked = clone.returncode != 0 and _MSYS_BOOT_FAILURE in (clone.stderr or "")
    except OSError:
        blocked = False
    finally:
        _rmtree_force(workdir)
    _git_transport_blocked = blocked
    return blocked


def _msys_boot_failure(call) -> bool:
    """True when this failed call is git's msys child dying at boot."""
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return False
    parts = [str(excinfo.value)]
    inner = getattr(excinfo.value, "stderr", None)
    if inner:
        parts.append(str(inner))
    return _MSYS_BOOT_FAILURE in "\n".join(parts)


def _msys_skip_applies(signature_hit: bool, module: str, transport_blocked: bool) -> bool:
    """转 skip 的判据：msys 签名，或「传输模块内 + 探针复现同一签名」。

    只看签名与本会话的探测结果，**不看令牌完整性级别**。R81 把「为什么挂不上」
    查清了（对象隐式带创建者 IL，启动器路径决定自己的 IL），但判据不变：
    skip 只看「这次失败是不是环境造成的」，不按 IL 分支；
    ``tests/test_msys_attribution.py`` 用真值表把四种组合逐格钉住。
    """
    return signature_hit or (module in _GIT_TRANSPORT_MODULES and transport_blocked)


def _msys_skip_reason(signature_hit: bool) -> str:
    """Skip 归因文案：机制 + 可执行的处置（R81 恢复处方，R71 曾删除）。

    R71 删掉「改用 High-IL 解释器」是因为 R70 §6.1 记录 High 也被挡。R81 实测
    推翻那条：同一份 python.exe 在 C: 是 High（``sh.exe`` rc=0，2373 passed /
    28 skipped），在 F: 的 venv 里是 Low（``0xC0000022``，2288 passed / 113
    skipped）；对象隐式带创建者 IL，Low 打开者连 DACL 里写着允许的
    ``DIRECTORY_CREATE_*`` 都会被拒。因此文案写回处方，但仍然**不把责任钉在
    「本令牌是 Low」**（对象侧可能比任何我们能拿到的令牌都高），也不写具体 SID。

    R82 更正启动器：``C:\\Windows\\py.exe`` 是 Windows launcher，本机今天没有
    项目依赖（137 个 collection error）；实测有效的是 C: 上的 CPython 本体
    ``C:\\Program Files\\Python314\\python.exe``，并把 venv 的 site-packages
    与 ``win32`` / ``pythonwin`` / ``pywin32_system32`` 一起放进 ``PYTHONPATH``
    （``.pth`` 不生效，必须显式列出）。

    R84 更正机制（不是「F: 上的可执行文件被降级」）：本工作区
    ``F:\\DeterminFlow x2`` 整棵树带**显式 Low 强制标签**（``icacls`` 显示
    ``Mandatory Label\\Low Mandatory Level:(OI)(CI)(NW)``），子项全部继承；带
    Low 标签的镜像被创建时，进程令牌降到 Low。把同一份 python.exe 复制到
    ``F:\\`` 根或别的无标签目录就是 High。因此文案给出两条并列处置：清标签，
    或用 C: 解释器。文案对**别的机器**只说「镜像可能继承了 Low 标签，查
    ``icacls``」，不声称这台机器的标签是唯一可能的原因。
    """
    return (
        "msys git transport cannot attach this session's shared msys-2.0 object "
        + ("(matched NtCreateDirectoryObject boot signature)" if signature_hit
           else "(unattributable inside a git-transport module)")
        + "; the interpreter image runs below the integrity level that created "
          "the object (an image that inherits a Low mandatory label is launched "
          "at Low; check `icacls <tree>`), so either clear that label "
          "(icacls <tree> /setintegritylevel Medium) or re-run from a High-IL "
          "shell with a C: interpreter, e.g. "
          "C:\\Program Files\\Python314\\python.exe -m pytest with the venv "
          "site-packages on PYTHONPATH "
          "(see PROJECT_INFO.md platform note 9)"
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Turn the environment-only msys boot failure into a skip, never other errors."""
    report = yield
    if not report.failed:
        return report
    if item.get_closest_marker("no_msys_skip"):
        # 判归因本身的用例：把它的失败转成 skip 等于让判据自证。R71 实测过这个
        # 坑——文案用例一旦判红，断言消息里带着 `NtCreateDirectoryObject`，
        # 本钩子会把「判据发现了错误」吞成「环境不可用」。
        return report
    signature_hit = _msys_boot_failure(call)
    module = pathlib.Path(str(item.fspath)).stem
    transport_blocked = module in _GIT_TRANSPORT_MODULES and _git_transport_blocked_probe()
    if not _msys_skip_applies(signature_hit, module, transport_blocked):
        return report
    report.outcome = "skipped"
    reason = _msys_skip_reason(signature_hit)
    # pytest 的折叠 skip 报告要求 (path, lineno, reason) 三元组。
    report.longrepr = (str(item.path), item.location[1], reason)
    return report


def pytest_collection_modifyitems(config, items):
    # Skip the macOS-only signing tests when Mach-O tooling is absent.
    if sys.platform != "darwin":
        for item in items:
            if "macos_signing" in pathlib.Path(str(item.fspath)).name.lower():
                item.add_marker(
                    pytest.mark.skip(
                        reason="macOS signing tooling is unavailable on this platform"
                    )
                )
    # Symlink-dependent cases opt in explicitly via @pytest.mark.requires_symlink;
    # no fragile source-text scanning. Skip them only when the OS cannot create
    # symlinks (e.g. Windows without the SeCreateSymbolicLinkPrivilege token).
    if _CAN_CREATE_SYMLINK:
        return
    for item in items:
        if item.get_closest_marker("requires_symlink"):
            item.add_marker(
                pytest.mark.skip(
                    reason="OS-level symlink creation is unavailable in this environment"
                )
            )


# ---------------------------------------------------------------------------
# R39：真实运行索引防污染守卫（R38 B27 教训的机械化）
#
# B27：走「写」分支的路由用例若漏 patch 模块级路径常量（_index 在 import 期
# 求值，patch DATA_DIR 不联动），tmp_path 会写进真实
# data/novel-console/workspaces.json。本守卫在每个用例前后对真实索引做
# 「pytest 临时路径条目」集合差比对，新增即在该用例上报错，精确归因到污染者。
# 仅抓 pytest 临时路径签名，不约束对真实索引的任何其他合法变更。
# ---------------------------------------------------------------------------

_REAL_CONSOLE_INDEX = (
    pathlib.Path(__file__).resolve().parents[1] / "data" / "novel-console" / "workspaces.json"
)


def _polluted_index_entries() -> set[str]:
    """真实索引中指向 pytest 临时目录的条目；索引缺失/损坏时返回空集。"""
    import json

    try:
        entries = json.loads(_REAL_CONSOLE_INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(entries, list):
        return set()
    flagged: set[str] = set()
    temp_root = pathlib.Path(tempfile.gettempdir()).resolve()
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    # 注意事项 8：本机 %TEMP% 可能回落为进程 CWD（即仓库根），此时 tempdir
    # 前缀规则会误伤全部合法条目，只保留 pytest-of- 签名规则。
    temp_rule_usable = not temp_root.is_relative_to(repo_root)
    for item in entries:
        text = str(item)
        if "pytest-of-" in text:
            flagged.add(text)
            continue
        if temp_rule_usable:
            candidate = pathlib.Path(text)
            if candidate.is_absolute():
                try:
                    candidate.resolve().relative_to(temp_root)
                except (ValueError, OSError):
                    continue
                flagged.add(text)
    return flagged


@pytest.fixture(autouse=True)
def _no_real_console_index_pollution():
    before = _polluted_index_entries()
    yield
    added = _polluted_index_entries() - before
    if added:
        pytest.fail(
            "本用例把 pytest 临时路径写进了真实运行索引 "
            f"({_REAL_CONSOLE_INDEX}，R38 B27 家族）：{sorted(added)}"
        )