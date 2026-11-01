"""msys 传输不可用时 skip 的归因与判据边界（R71 建立，R81 更正归因）。

R70 §6.1 的四行矩阵曾让仓库得出「113 skips 不是 IL 的函数」的结论：那次实测
High 令牌与真降到 ``S-1-16-4096`` 的令牌同为 2189/113。R81 把对象的安全描述符
读出来了，并做了创建者 × 打开者的交叉对照：

* 对象 ``\\BaseNamedObjects\\msys-2.0S5-…`` 的 DACL 只有一条
  ``Everyone -> 0x2000F``（READ_CONTROL + DIRECTORY_QUERY/TRAVERSE/CREATE_*），
  **没有 SACL**；可 Low 打开者仍然被拒 ``CREATE_OBJECT``，High 打开者通过。
* 同一 DACL 的合成对象：High 创建 → Low 被拒；Low 创建 → Low 通过。也就是说
  对象隐式带着创建者的完整性级别，DACL 里写着允许并不够。
* IL 由**启动器所在位置**决定：``F:\\...\\.venv\\python.exe`` 是 Low（即使父
  shell 是 High），同一份 python.exe 复制到 C: 就是 High。

所以 R70 的「High 也失败」在本机不成立：High 解释器起来 ``sh.exe`` rc=0，
全量 2373 passed / 28 skipped；Low 下 2288 passed / 113 skipped。

本文件钉**归因与判据边界**，不改「何时转 skip」的行为：

1. 文案写机制 + 可执行处方，但**不把责任钉成「本令牌是 Low」**（对象侧可能
   比任何我们能拿到的令牌都高）；
2. 判据的真值表只有两个自变量（签名、探针结果），令牌 IL 不是第三个；
3. 同一条 clone 失败，仅 stderr 不同就必须翻转成「不转 skip」——这是
   「真实缺陷不会被伪装成环境问题」的可复现判据；
4. 允许「无签名也转 skip」的模块集合逐字等于那 6 个（盲区不能悄悄变大）；
5. 本文件自身的**失败**绝不能被钩子转成 skip——R71 变异验证实测过这个坑：
   文案用例判红时断言消息里带着 `NtCreateDirectoryObject`，钩子按签名把它吞成
   skip，于是「判据发现错误」在输出里长成「环境不可用」。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# 判归因本身的用例不参与「msys 签名 → skip」的转换（见第 5 条与注释里的实测）。
pytestmark = pytest.mark.no_msys_skip

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "tests" / "conftest.py"

# 与 conftest 的 allowlist 逐字相同；改动必须同时改这里与登记页 §2/#11。
EXPECTED_TRANSPORT_MODULES = frozenset({
    "test_plugin_store",
    "test_plugin_routes",
    "test_plugin_host_integration",
    "test_plugin_registry",
    "test_plugin_source_catalog",
    "test_plugin_resource_namespace",
})


def _conftest():
    """取 pytest 已导入的 ``tests/conftest.py`` 模块本身（不重复执行探针）。"""
    module = sys.modules.get("conftest")
    assert module is not None and Path(module.__file__).resolve() == CONFTEST, (
        "pytest 没有把 tests/conftest.py 以模块名 conftest 导入；"
        "本文件的判据需要的是实际生效的那一份")
    return module


def test_skip_reason_names_the_mechanism_and_the_actionable_fix() -> None:
    """两种归因都描述机制，并给出照做就能过的处方（R81 / R84）。

    R71 曾以「High 也会被挡」为据把处方删掉。R81 实测推翻了那条：同一份
    ``python.exe`` 在 C: 是 High（``sh.exe`` rc=0、2373 passed / 28 skipped），
    在 F: 的 venv 里是 Low（``0xC0000022``、2288 passed / 113 skipped）。R84 找到了
    机制：工作区整棵树带显式 Low 强制标签，带标签的镜像被创建时令牌降到 Low；
    同一份二进制放到无标签目录就是 High。所以判据钉住：处方必须同时给出
    「清标签」与「C: 解释器」两条路，并**不写具体 SID**、**不写
    "Low-integrity token"**——对象侧可能比任何我们能拿到的令牌都高。
    """
    cf = _conftest()
    for signature_hit in (True, False):
        reason = cf._msys_skip_reason(signature_hit)
        lowered = reason.lower()
        assert "msys" in lowered
        assert "attach" in lowered, reason
        assert "shared" in lowered, reason
        # 处方必须可执行：复制过去的命令能照做。R82 实测 ``py.exe`` 缺依赖
        # （137 个 collection error），处方改用 C: 上的 CPython 本体。
        assert "python.exe" in lowered, reason
        assert "py.exe" not in lowered, reason
        assert "pythonpath" in lowered, reason
        # R84：真正的机制是「镜像继承了 Low 强制标签」，两条处置都要写出来。
        assert "mandatory label" in lowered, reason
        assert "icacls" in lowered, reason
        # 但不许把责任钉成「本令牌是 Low」，也不许写 SID 字面量。
        assert "low-integrity token" not in lowered, reason
        assert "s-1-16-" not in lowered, reason
    hit = cf._msys_skip_reason(True)
    miss = cf._msys_skip_reason(False)
    assert cf._MSYS_BOOT_FAILURE in hit, hit
    assert "unattributable" in miss.lower(), miss


def test_skip_truth_table_has_exactly_two_independent_variables() -> None:
    """签名 / 模块 / 探针三者的四种可达组合逐格钉住，与令牌状态无关。"""
    cf = _conftest()
    transport_module = sorted(EXPECTED_TRANSPORT_MODULES)[0]
    # 失败调用自己带签名：任何模块都转 skip（识别环境，而不是识别模块）。
    assert cf._msys_skip_applies(True, "test_unrelated", False) is True
    assert cf._msys_skip_applies(True, transport_module, False) is True
    # 无签名：只有「传输模块内 + 探针复现同一签名」才转 skip。
    assert cf._msys_skip_applies(False, transport_module, True) is True
    assert cf._msys_skip_applies(False, transport_module, False) is False
    # 非传输模块即使探针判环境坏，也照常失败（真实缺陷不被吞）。
    assert cf._msys_skip_applies(False, "test_unrelated", True) is False


@pytest.mark.skipif(
    os.name != "nt",
    reason="probe 在 POSIX 直接返回 False，没有可测的 msys 判据")
def test_probe_flips_on_the_msys_signature_only(monkeypatch) -> None:
    """同一条 clone 失败，仅 stderr 不同：无签名 → False，有签名 → True。

    这是「真实 git 缺陷（仓库不存在/权限）永远不会被归类成环境限制」的边界
    测试。探针走真实代码路径，只把 git 子进程换成一个按参数返回固定结果的桩。
    """
    cf = _conftest()
    clone_stderr = [""]

    def fake_run(args, **_kwargs):
        if "clone" in args:
            return subprocess.CompletedProcess(
                args=args, returncode=1, stderr=clone_stderr[0])
        return subprocess.CompletedProcess(args=args, returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(cf, "_git_transport_blocked", None)

    clone_stderr[0] = "fatal: repository 'source' does not exist\n"
    assert cf._git_transport_blocked_probe() is False

    monkeypatch.setattr(cf, "_git_transport_blocked", None)
    clone_stderr[0] = (
        "*** fatal error - NtCreateDirectoryObject("
        "\\BaseNamedObjects\\msys-2.0S5-1a2b3c4d): 0xC0000022\n")
    assert cf._git_transport_blocked_probe() is True


def test_skip_surface_is_exactly_the_six_transport_modules() -> None:
    """盲区（无签名也转 skip 的模块）只有这 6 个，且每个都真实存在。"""
    cf = _conftest()
    assert cf._GIT_TRANSPORT_MODULES == EXPECTED_TRANSPORT_MODULES, (
        "允许转 skip 的模块集合变了；盲区变大必须同时更新登记页 §2/#11 与本用例")
    for module_name in EXPECTED_TRANSPORT_MODULES:
        assert (REPO_ROOT / "tests" / f"{module_name}.py").is_file(), module_name


class _RecordedReport:
    def __init__(self) -> None:
        self.failed = True
        self.outcome = "failed"
        self.longrepr = None


class _RecordedExcinfo:
    def __init__(self, message: str) -> None:
        self.value = AssertionError(message)


class _RecordedCall:
    def __init__(self, message: str) -> None:
        self.excinfo = _RecordedExcinfo(message)


class _RecordedItem:
    fspath = str(REPO_ROOT / "tests" / "test_msys_attribution.py")
    path = fspath
    location = ("test_msys_attribution.py", 1, "test_example")

    def __init__(self, marked: bool) -> None:
        self._marked = marked

    def get_closest_marker(self, name: str):
        return object() if self._marked and name == "no_msys_skip" else None


def _drive_makereport(cf, item: _RecordedItem, message: str) -> _RecordedReport:
    """直接驱动 wrapper 钩子：yield 一次后送进一条已判红的 report。"""
    generator = cf.pytest_runtest_makereport(item, _RecordedCall(message))
    next(generator)
    try:
        return generator.send(_RecordedReport())
    except StopIteration as stop:
        return stop.value


def test_attribution_failures_are_never_converted_into_skips() -> None:
    """没有 ``no_msys_skip`` 标记时钩子会吞掉本文件的失败——标记必须挡住。

    这条同时钉住机制与豁免：未标记的红色 report 被转成 skipped（钩子的
    设计目的），标记之后必须原样保持 failed。R71 的第一次变异验证就是被
    前者骗成「全绿」的。
    """
    cf = _conftest()
    message = "assert 'integrity' not in '... NtCreateDirectoryObject ...'"
    unmarked = _drive_makereport(cf, _RecordedItem(marked=False), message)
    assert unmarked.outcome == "skipped"
    marked = _drive_makereport(cf, _RecordedItem(marked=True), message)
    assert marked.outcome == "failed"
    assert marked.longrepr is None
