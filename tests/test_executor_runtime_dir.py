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
