"""O2 回归：Executor runtime 目录必须钉在 data/ 下，失败路径零残留。

修复前（HANDOVER_ROUND20 §7 O2）：``tempfile.mkdtemp(prefix=...)`` 不带
``dir=``，本机 %TEMP% 受 ACL 限制时 Python 按 ``TEMP → TMP → CWD`` 回落——
实测 ``tempfile.gettempdir()`` 返回进程工作目录，仓库根因此累积 52 个
``determinflow-executor-*`` 残留目录（进程硬杀时 start() 的 except 清理
与 stop() 都不会执行）。

修复后 runtime 目录固定在 ``data/system/executor-runtimes/`` 下：
- 位置可预测（残留集中一处，可审计可清理）；
- 不再依赖 %TEMP% 的可用性。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.workflow.executor_supervisor as supervisor_module
from src.workflow.executor_supervisor import WorkflowExecutorSupervisor, _runtime_dir_root


def test_runtime_dir_root_is_pinned_under_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(supervisor_module, "DATA_DIR", tmp_path)
    root = _runtime_dir_root()
    assert root == tmp_path / "system" / "executor-runtimes"
    assert root.is_dir()


def test_start_creates_runtime_dir_under_data_and_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """spawn 失败时：runtime 目录创建在 data/ 下，且 except 分支清干净、零残留。"""
    monkeypatch.setattr(supervisor_module, "DATA_DIR", tmp_path)
    residue_before = set(Path.cwd().glob("determinflow-executor-*"))

    async def _failing_spawn(*args, **kwargs):  # noqa: ANN001, ANN002 - 测试桩
        raise RuntimeError("spawn refused")

    supervisor = WorkflowExecutorSupervisor(executor_id="workflow-executor-test")
    with monkeypatch.context() as context:
        context.setattr(asyncio, "create_subprocess_exec", _failing_spawn)
        with pytest.raises(RuntimeError, match="spawn refused"):
            asyncio.run(supervisor.start())

    root = tmp_path / "system" / "executor-runtimes"
    assert root.is_dir()
    assert list(root.iterdir()) == []  # 失败清理生效：不留半成品
    assert supervisor.status == "stopped"
    # 无论 %TEMP% 是否可用，都不允许再向进程工作目录散落 runtime 目录
    assert set(Path.cwd().glob("determinflow-executor-*")) == residue_before


def test_start_failure_before_spawn_resets_status_to_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B14 回归：spawn 之前的准备步骤失败（mkdtemp / restrict_private_path）时，
    状态机必须落到 ``stopped``，不得悬挂在 ``starting``。

    修复前这两步位于 ``try`` 块之前，异常直接穿透 ``start()`` 而无人复位状态；
    调用方（pool）丢弃实例后，健康面板看到的该 executor 永远是 ``starting``。
    """
    monkeypatch.setattr(supervisor_module, "DATA_DIR", tmp_path)
    root = tmp_path / "system" / "executor-runtimes"

    # 场景一：mkdtemp 本身失败（如磁盘满 / 目录权限收紧）
    def _failing_mkdtemp(*args, **kwargs):  # noqa: ANN001, ANN002 - 测试桩
        raise OSError("mkdtemp refused")

    supervisor = WorkflowExecutorSupervisor(executor_id="workflow-executor-test")
    with monkeypatch.context() as context:
        context.setattr(supervisor_module.tempfile, "mkdtemp", _failing_mkdtemp)
        with pytest.raises(OSError, match="mkdtemp refused"):
            asyncio.run(supervisor.start())
    assert supervisor.status == "stopped"
    assert supervisor._runtime_dir is None

    # 场景二：目录已建好但收紧权限失败——except 分支须清掉半成品 runtime 目录
    def _failing_restrict(path, mode):  # noqa: ANN001 - 测试桩
        raise OSError("chmod refused")

    supervisor2 = WorkflowExecutorSupervisor(executor_id="workflow-executor-test")
    with monkeypatch.context() as context:
        context.setattr(supervisor_module, "restrict_private_path", _failing_restrict)
        with pytest.raises(OSError, match="chmod refused"):
            asyncio.run(supervisor2.start())
    assert supervisor2.status == "stopped"
    assert supervisor2._runtime_dir is None
    assert list(root.iterdir()) == []
