"""R101：在 CI 里回放写回的生产路径（happy / 被拒一次 / 冲突 / 永久拒绝 /
永久拒绝+冲突）。

R99 已经把「在沙箱 origin 上真实制造 push 拒绝与 rebase 冲突」做成可执行
能力，但那些场景此前只由 ``tests/test_replay_ci_writeback.py`` 在 backend
job 里以 pytest 驱动。pytest 能证明函数行为，**证明不了**「生产 CI 的
checkout、git、shell 钩子、历史文件上，这套回放真的能跑完」。本脚本就是那
个生产 job 的驱动：它把 ``scripts/replay_ci_writeback.py`` 当**真实 CLI
子进程**逐个跑场景，断言退出码、``reason``、``rounds``、``push_attempts``
与关键输出，再把机读结果交给 step summary / artifact。

## 判什么、不判什么

判：回放的**可执行性与链路语义**——写回成功、被拒一次后重试成功、冲突后
丢弃本地提交并按最新分支重算、三次全拒后正确失败并保留现场。每个场景都从
``--repo`` 的 HEAD 克隆出独立沙箱，源仓库一个字节都不该动。

判定写入是否发生不能只看轮数：历史窗口 ``MAX_ROUNDS`` 满了以后
``history[-MAX_ROUNDS:]`` 会把最早一轮挤掉，happy/rejected 的净增量变成 0，conflict
的 +2 也会被压平——``rounds`` 会退化成恒等式（R102）。因此成功场景额外断言
``result.last_run_id`` 等于本轮的 ``run_id``；失败场景（永久拒绝）断言远端
末条**仍是基线那一条**，远端轮数完全没变。

永久拒绝是**期望失败**：退出码 1、``reason=push-rejected``、推送恰好 3 次。
它必须同时看到 3 次 ``simulated rejection``——否则 msys/传输故障也能让 push
三次非零，场景会为错误的原因变绿。replay 按设计保留失败沙箱；驱动断言现场
存在、随后清理，既证明「失败现场真的留下过」，也不让 CI runner 的临时目录
累积（R103）。

R105 的组合场景（``rejected-conflict``）把冲突注入与永久拒绝放进同一次
回放：第一次 push 先被冲突注入造成的**非快进**拒绝挡下，钩子再拒绝第 2、3
次，rebase 冲突后按最新分支重算，三次尝试全部失败。它的观测与纯永久拒绝
不同——远端会多出一轮注入的冲突历史（``replay-conflict``），所以失败场景
不能用「远端完全没变」来判，必须用 ``expected_last_run_id`` 钉住末条身份；
``simulated rejection`` 也只应出现 **2** 次（第一次不是钩子拒绝）。

``--fetch-api-url`` 启用时追加 ``fetched`` 场景：不喂本地 metrics，而是让
replay 先走 ``fetch_ci_artifact`` 从真实 API 下载 artifact，再走同一条写回
链路。artifact API 的 run id 与历史 run id 是两件事（前者是 GitHub run，
后者是 ``replay-ci-fetched-<sha>``），由 ``--fetch-run-id`` 分开。

R106 在同一份全链配置上追加 ``fetched-rejected-conflict``：真实 artifact
下载成功后再叠加三次拒绝与冲突注入，端到端证明「下载 → 非快进拒绝 →
钩子拒绝 → 重算 → 全失败」这条链没有被 fetch 路径绕开。

R112 把钩子的注入时机参数化（``--conflict-on-reject N``），并补三条时间线：
N=2 且预算耗尽、N=2 且第三次成功、N=3（末次拒绝注入、没有下一次重试）。
同轮把写回前的指纹扩成**语义**：除计数外逐场景打印
``name=ok|retry|fail/尝试次数`` 与 ``first_failure``，全链场景据此断言
artifact 的内容而不只是总数。

R113 把注入矩阵扩到 N=4/5：写回重试上限变成可配置的 ``--attempts``，并补上
「注入点 <= 重试次数」这条可达性校验（只查拒绝预算会漏掉重试先耗尽的那
一半）。本地新增三条时间线，全链新增 ``fetched-rejected-hook-at-4``，证明
late injection 在下载 artifact 之后同样可达。

## 退出码

- 0：所有场景符合预期
- 1：至少一个场景的观测与预期不符（真回归；输出里有逐项 expected/actual）
- 2：用法错误（argparse，或 fetch 参数不成对）
- 3：基线不可用——``--repo`` 不是 git 仓库、history 缺失/读不懂。**不是**
  回放语义失败，排查方向是 checkout/git/数据，别把它当 1。

## 为什么不是 pytest

R100 §5 的边界原话是「replay 仍不进 CI；拒绝/冲突场景由 pytest 在 backend
job 里驱动，不是生产 job」。把同样的断言塞回 pytest 只是换了个执行者，
``.github/workflows/ci.yml`` 里的 ``replay-ci-writeback`` job 仍然没有生产
调用者。这里把断言放在独立脚本里，CI 只负责调用与透传退出码（R89 的同一
原则：能本地跑的逻辑不写在 YAML 里）。

用法::

    python scripts/replay_ci_scenarios.py --repo . --branch main
    python scripts/replay_ci_scenarios.py --repo . \\
        --result-json "$RUNNER_TEMP/replay-ci-result.json" \\
        --summary "$GITHUB_STEP_SUMMARY"
    # 全链：下载 GitHub artifact 后再写回
    python scripts/replay_ci_scenarios.py --repo . --fetch-api-url \\
        https://api.github.com --fetch-run-id "$GITHUB_RUN_ID" \\
        --fetch-repo "$GITHUB_REPOSITORY"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ci_reporting
from scripts import ci_writeback_history as writeback
from scripts import e2e_retry_history as history
from scripts import replay_ci_writeback as replay

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_USAGE = 2
EXIT_ENV = 3

RESULT_SCHEMA = 1
DEFAULT_HISTORY = "tests/fixtures/e2e_retry_history/history.json"

# 每个场景的捕获输出写进 result JSON 时截断：失败现场足够诊断，又不至于让
# artifact 里塞进整份 git 输出。
OUTPUT_LIMIT = 8000


@dataclass(frozen=True)
class Scenario:
    """一个回放场景的预期观测。

    ``rounds_delta`` / ``push_attempts`` 来自 R99 的真实行为，不是拍脑袋：
    - happy：一次 push 成功，rounds +1，push_attempts=1；
    - rejected：第 1 次被拒、第 2 次成功，rounds +1，push_attempts=2；
    - conflict：origin 上预置一轮冲突历史 + 本轮，rounds +2；写回同样经历
      被拒→rebase 冲突→按最新分支重算→第 2 次 push，push_attempts=2；
    - permanently-rejected（R103）：三次全被拒，退出码 1、远端轮数不变、
      push_attempts=3，失败沙箱保留后由驱动清理；
    - rejected-conflict（R105）：冲突注入 + 永久拒绝组合。第一次 push 被
      非快进拒绝，钩子拒绝第 2、3 次；远端只多出注入的冲突轮，退出码 1。
    - rejected-hook-conflict（R108）：钩子在**第一次拒绝**时注入冲突，
      第一次 push 真的走到钩子；预算 3 时三次全失败。
    - rejected-hook-budget-2（R108）：同一夹具、预算 2，第三次 push 成功；
      ``reject_pushes`` 的 2 与 3 因此成为可区分的行为边界。
    - rejected-hook-conflict-at-2（R112）：注入点移到**第 2 次拒绝**，预算 3
      仍在中途耗尽；冲突发生在第 2 次尝试，第 3 次重算后仍被拒。
    - rejected-hook-budget-2-at-2（R112）：注入点在第 2 次、预算 2 的变体——
      第 2 次拒绝时注入，第三次 push 成功；最终观测与 N=1 相同，但「rebase
      冲突（第 2 次）」把注入时机钉住。
    - rejected-hook-inject-at-3（R112）：预算与注入点都在第 3 次——注入之后
      已经没有下一次重试，冲突轮留在 origin，本轮不入库。
    - rejected-hook-conflict-at-4（R113）：N=4、预算 4、attempts=4；四次全被
      拒，注入在最后一次，失败类别是 rebase-conflict。
    - rejected-hook-budget-4-at-4（R113）：同注入点、attempts=5；第 5 次
      push 成功，净 +2。证明 late injection 不是必然失败。
    - rejected-hook-inject-at-5（R113）：N=5、预算 5、attempts=5；五次全被
      拒，注入在最后一次。

    ``attempts`` 是写回重试上限（默认 3）。N=4/5 的场景必须显式抬到 4/5，
    否则注入点永远到不了——``replay_ci_writeback`` 会以退出码 2 拒绝这种
    不可达配置（R113 补的闸门）。

    ``injected_rounds`` 是**夹具侧**先推进 origin 的轮数（冲突注入），
    只在失败场景里参与期望轮数计算：``rounds_delta`` 描述成功场景的净变化，
    失败场景不能写回，远端的变化只可能来自注入。``expected_last_run_id``
    用于失败场景的末条身份断言——纯永久拒绝断言「仍是基线那一条」，组合
    场景则断言「正好是注入的 ``replay-conflict``」。
    """

    name: str
    rounds_delta: int
    push_attempts: int
    reject_pushes: int = 0
    conflict: bool = False
    conflict_on_reject: int = 0
    attempts: int = writeback.DEFAULT_ATTEMPTS
    expected_exit: int = EXIT_OK
    expected_reason: str = "written"
    expect_sandbox: bool = False
    fetch: bool = False
    injected_rounds: int = 0
    expected_last_run_id: str | None = None
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()
    output_counts: tuple[tuple[str, int], ...] = ()

    @property
    def succeeds(self) -> bool:
        return self.expected_exit == EXIT_OK


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "happy", 1, 1,
        must_contain=("已写回",),
        # 证明这一场景真的没有拒绝；否则「被拒一次」与它无法区分。
        must_not_contain=("push 被拒（第", "simulated rejection"),
    ),
    Scenario(
        "rejected", 1, 2, reject_pushes=1,
        must_contain=("push 被拒（第 1 次）", "第 2 次尝试"),
        # 必须看到钩子自己的拒绝，而不是任何一次传输故障。
        output_counts=(("simulated rejection", 1),),
    ),
    Scenario(
        "conflict", 2, 2, conflict=True, injected_rounds=1,
        must_contain=("rebase 冲突（第 1 次）", "第 2 次尝试"),
        must_not_contain=("simulated rejection",),
    ),
    Scenario(
        "permanently-rejected", 0, 3, reject_pushes=3,
        expected_exit=EXIT_MISMATCH,
        expected_reason="push-rejected",
        expect_sandbox=True,
        must_contain=("::error::连续 3 次写回均失败",),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 3), ("simulated rejection", 3)),
    ),
    # R105：冲突注入 + 三次尝试全被拒。远端会多出注入的冲突轮（+1），
    # 但本轮写回没有入库——末条必须正好是 replay-conflict。
    # reject_pushes 的行为边界是 2（第一次 push 到不了钩子，见 R106）；这里的
    # 3 只是与纯永久拒绝同口径，改数字只有表钉用例能发现。
    Scenario(
        "rejected-conflict", 0, 3, reject_pushes=3, conflict=True,
        expected_exit=EXIT_MISMATCH,
        expected_reason="push-rejected",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("rebase 冲突（第 1 次）",
                      "::error::连续 3 次写回均失败"),
        must_not_contain=("已写回",),
        # 第 1 次是非快进拒绝（冲突注入），钩子只拒绝第 2、3 次（R105 实测）。
        output_counts=(("push 被拒（第", 3), ("simulated rejection", 2)),
    ),
    # R108：第一次拒绝时由钩子注入冲突。第一次 push 真的走到了钩子（不是
    # 非快进），因此预算 3 = 三次全失败；预算 2 = 第三次成功。同一夹具下
    # reject_pushes 的 2/3 第一次成为可区分的**行为**边界。
    Scenario(
        "rejected-hook-conflict", 0, 3, reject_pushes=3,
        conflict_on_reject=1,
        expected_exit=EXIT_MISMATCH,
        expected_reason="push-rejected",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("rebase 冲突（第 1 次）",
                      "::error::连续 3 次写回均失败"),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 3), ("simulated rejection", 3)),
    ),
    # 预算 2：钩子拒绝第 1、2 次（第 1 次注入冲突），第三次 push 成功；
    # 远端 = 注入轮 + 本轮，净 +2。
    Scenario(
        "rejected-hook-budget-2", 2, 3, reject_pushes=2,
        conflict_on_reject=1,
        must_contain=("rebase 冲突（第 1 次）", "第 3 次尝试", "已写回"),
        output_counts=(("push 被拒（第", 2), ("simulated rejection", 2)),
    ),
    # R112：注入点可指定到第 N 次拒绝，覆盖「预算中途耗尽 / 注入后无重试」
    # 的时间线。N=1 的两种结局已在 R108 覆盖，这里补 N=2 与 N=3。
    #
    # N=2、预算 3：第 1 次普通拒绝 → 第 2 次拒绝时注入 → 重算 → 第 3 次仍被拒。
    # 冲突轮留在远端但本轮未入库；判据必须说出冲突发生在第 2 次尝试，否则
    # 「钩子忽略 N、仍固定第一次注入」无法与它区分。
    Scenario(
        "rejected-hook-conflict-at-2", 0, 3, reject_pushes=3,
        conflict_on_reject=2,
        expected_exit=EXIT_MISMATCH,
        expected_reason="push-rejected",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("第 2 次拒绝时注入冲突",
                      "rebase 冲突（第 2 次）",
                      "::error::连续 3 次写回均失败"),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 3), ("simulated rejection", 3)),
    ),
    # N=2、预算 2：第 2 次拒绝时注入，第三次 push 成功；净 +2。最终观测与
    # N=1/预算 2 相同，唯一区别是冲突发生在第 2 次尝试。
    Scenario(
        "rejected-hook-budget-2-at-2", 2, 3, reject_pushes=2,
        conflict_on_reject=2,
        must_contain=("第 2 次拒绝时注入冲突",
                      "rebase 冲突（第 2 次）",
                      "第 3 次尝试", "已写回"),
        output_counts=(("push 被拒（第", 2), ("simulated rejection", 2)),
    ),
    # N=3、预算 3：注入发生在最后一次拒绝——冲突轮进了 origin，但已经没有
    # 第 4 次尝试去重算。最后一次失败是 rebase 冲突（不是 push 被拒），
    # 这条时间线证明注入不依赖「还有下一次重试」，也钉住 reason 的来源。
    Scenario(
        "rejected-hook-inject-at-3", 0, 3, reject_pushes=3,
        conflict_on_reject=3,
        expected_exit=EXIT_MISMATCH,
        expected_reason="rebase-conflict",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("第 3 次拒绝时注入冲突",
                      "rebase 冲突（第 3 次）",
                      "::error::连续 3 次写回均失败"),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 3), ("simulated rejection", 3)),
    ),
    # R113：N=4/5 需要重试上限跟着抬到 4/5。R112 只校验了「预算 >= 注入
    # 点」，但重试循环默认只 push 3 次——预算够、次数不够时注入同样永远
    # 到不了。--attempts 与可达性校验是本组场景存在的前提。
    #
    # N=4、预算 4、attempts=4：四次全被拒，注入落在最后一次，没有第 5 次
    # 重试去消化冲突；失败类别是 rebase 冲突。
    Scenario(
        "rejected-hook-conflict-at-4", 0, 4, reject_pushes=4,
        conflict_on_reject=4, attempts=4,
        expected_exit=EXIT_MISMATCH,
        expected_reason="rebase-conflict",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("第 4 次拒绝时注入冲突",
                      "rebase 冲突（第 4 次）",
                      "::error::连续 4 次写回均失败"),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 4), ("simulated rejection", 4)),
    ),
    # N=4、预算 4、attempts=5：第 4 次拒绝时注入，第 5 次 push 成功；
    # 注入轮 + 本轮 = 净 +2。证明 late injection 不是必然失败。
    Scenario(
        "rejected-hook-budget-4-at-4", 2, 5, reject_pushes=4,
        conflict_on_reject=4, attempts=5,
        must_contain=("第 4 次拒绝时注入冲突",
                      "rebase 冲突（第 4 次）",
                      "第 5 次尝试", "已写回"),
        output_counts=(("push 被拒（第", 4), ("simulated rejection", 4)),
    ),
    # N=5、预算 5、attempts=5：五次全被拒，注入在最后一次；失败类别与
    # N=3/3 同型（rebase-conflict），但尝试次数与钩子计数都到了 5。
    Scenario(
        "rejected-hook-inject-at-5", 0, 5, reject_pushes=5,
        conflict_on_reject=5, attempts=5,
        expected_exit=EXIT_MISMATCH,
        expected_reason="rebase-conflict",
        expect_sandbox=True,
        injected_rounds=1,
        expected_last_run_id="replay-conflict",
        must_contain=("第 5 次拒绝时注入冲突",
                      "rebase 冲突（第 5 次）",
                      "::error::连续 5 次写回均失败"),
        must_not_contain=("已写回",),
        output_counts=(("push 被拒（第", 5), ("simulated rejection", 5)),
    ),
)

# R103：全链场景不喂本地 metrics，而是让 replay 先下载真实 artifact。
FETCH_SCENARIO = Scenario(
    "fetched", 1, 1, fetch=True,
    # total=10 只可能来自生产 artifact（本地夹具故意是 3 场景），
    # retried/attempts 不钉死：e2e 偶发重跑不应让全链 job 变红（R107）。
    # R112：语义行必须出现——它逐场景列出 name=状态/尝试次数，证明写回读的是
    # 内容而不是只数了总数；具体取值仍不钉死（生产可能真的重跑）。
    must_contain=("已下载 1 个文件", "metrics 内容 total=10",
                  "metrics 语义", "已写回"),
)

# R106：全链 × 永久拒绝 × 冲突的三重叠加。期望与本地 metrics 的
# rejected-conflict 完全一致——fetch 只换 metrics 来源，不能改变写回语义；
# 「已下载 1 个文件」把「artifact 真的被用上」钉在同一个场景里。
#
# 注意 reject_pushes=3 的行为边界其实是 2：第一次 push 被非快进挡下、根本
# 到不了 pre-receive 钩子，所以钩子只要拒绝后两次就能让三次尝试全失败
# （R106 变异实测 2 与 3 的输出/轮数/末条完全一致）。写 3 是与纯永久拒绝
# 保持同一个「拒绝预算」口径，不是行为阈值；改这个数字只有表钉用例能发现。
FETCH_REJECTED_CONFLICT_SCENARIO = Scenario(
    "fetched-rejected-conflict", 0, 3, reject_pushes=3, conflict=True,
    fetch=True,
    expected_exit=EXIT_MISMATCH,
    expected_reason="push-rejected",
    expect_sandbox=True,
    injected_rounds=1,
    expected_last_run_id="replay-conflict",
    must_contain=("已下载 1 个文件",
                  "metrics 内容 total=10",
                  "metrics 语义",
                  "rebase 冲突（第 1 次）",
                  "::error::连续 3 次写回均失败"),
    must_not_contain=("已写回",),
    output_counts=(("push 被拒（第", 3), ("simulated rejection", 2)),
)

# R113：全链 × 第 4 次拒绝注入 × 5 次重试。fetch 只换 metrics 来源，
# 「第 4 次拒绝时注入」与「第 5 次成功」必须和本地场景同型；这条同时证明
# --attempts 在全链子进程里真的透传到了写回重试循环。
FETCH_REJECTED_HOOK_AT_4_SCENARIO = Scenario(
    "fetched-rejected-hook-at-4", 2, 5, reject_pushes=4,
    conflict_on_reject=4, attempts=5, fetch=True,
    must_contain=("已下载 1 个文件",
                  "metrics 内容 total=10",
                  "metrics 语义",
                  "第 4 次拒绝时注入冲突",
                  "rebase 冲突（第 4 次）",
                  "第 5 次尝试",
                  "已写回"),
    output_counts=(("push 被拒（第", 4), ("simulated rejection", 4)),
)

# 单个场景是 1–2 次本地 git 操作；超时保护只防止沙箱 git/钩子卡死。
SCENARIO_TIMEOUT = 180.0

SANDBOX_PREFIX = "replay：沙箱保留在 "


class BaselineError(RuntimeError):
    """无法建立回放基线（repo/git/history）；对应退出码 3。"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True)


def _git_text(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode(
            "utf-8", "replace").strip()
        raise BaselineError(f"git {' '.join(args)} 失败：{detail}")
    return (result.stdout or b"").decode("utf-8", "replace").strip()


def _metrics(path: Path) -> Path:
    """本地夹具：3 场景、其中 1 个重跑一次（总尝试 4）。

    生产 artifact 是 10 场景形状（当前 10/0/10）。**故意与生产不同**：全链
    场景断言 ``replay：metrics 内容 total=10``，如果 fetch 成功却回退到这份
    本地夹具，计数指纹会变成 ``total=3 attempts=4``，断言立刻露馅（R107）。
    """
    scenarios = [
        {"name": "local_0", "passed": True, "attempts": 2,
         "first_failure": "local retry"},
        {"name": "local_1", "passed": True, "attempts": 1, "first_failure": ""},
        {"name": "local_2", "passed": True, "attempts": 1, "first_failure": ""},
    ]
    path.write_text(json.dumps({
        "schema": 1, "total": 3, "passed": 3, "failed": 0, "retried": 1,
        "scenarios": scenarios}), encoding="utf-8")
    return path


def _baseline(repo: Path, history_rel: str) -> dict:
    """读源仓库的 HEAD、历史轮数与历史字节（用于前后对比）。"""
    if not repo.is_dir():
        raise BaselineError(f"仓库目录不存在：{repo}")
    _git_text(repo, "rev-parse", "--show-toplevel")
    head = _git_text(repo, "rev-parse", "HEAD")
    history_path = repo / history_rel
    try:
        entries = history.load_history(history_path)
    except history.HistoryError as exc:
        raise BaselineError(str(exc)) from exc
    return {
        "head": head,
        "history_path": history_path,
        "history_bytes": history_path.read_bytes(),
        "rounds": len(entries),
        # 失败场景（永久拒绝）要证明远端末条**没有变**：它仍是基线这一条。
        "last_run_id": entries[-1]["run_id"] if entries else None,
    }


def _invoke_replay(argv: list[str]) -> tuple[int, str]:
    """把 replay 当真实 CLI 子进程跑（R103）。

    此前是进程内 ``replay.main(argv)`` + 重定向 stdout/stderr。那条路径看不见
    ``sys.path`` 引导、argparse 的进程退出码、未捕获异常的 traceback——R98 的
    ``ModuleNotFoundError`` 正是只在脚本模式下出现。子进程还让驱动与回放共享
    全局状态的窗口消失（``redirect_stdout`` 是进程级的）。
    """
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8",
             str(REPO_ROOT / "scripts" / "replay_ci_writeback.py"), *argv],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=env, timeout=SCENARIO_TIMEOUT)
    except subprocess.TimeoutExpired:
        return (EXIT_MISMATCH,
                f"replay 子进程超时（{SCENARIO_TIMEOUT:.0f}s）")
    except OSError as exc:
        return EXIT_MISMATCH, f"replay 子进程无法启动：{exc}"
    return completed.returncode, completed.stdout + completed.stderr


def _kept_sandbox(output: str) -> Path | None:
    """从 replay 的收尾行里取出失败沙箱路径。"""
    for line in reversed(output.splitlines()):
        if line.startswith(SANDBOX_PREFIX):
            text = line[len(SANDBOX_PREFIX):].strip()
            text = text.removesuffix("（失败现场）").strip()
            return Path(text) if text else None
    return None


def _cleanup_sandbox(path: Path) -> bool:
    """清理失败沙箱并确认真的删掉了；Windows 的只读 pack 需要重试。"""
    for _ in range(3):
        replay._remove_sandbox(path)
        if not path.exists():
            return True
        time.sleep(0.2)
    return not path.exists()


def _read_result(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_scenario(scenario: Scenario, repo: Path, branch: str,
                  history_rel: str, before: int,
                  baseline_last_run_id: str | None, workdir: Path,
                  fetch_api_url: str | None = None,
                  fetch_run_id: str | None = None,
                  fetch_repo: str = "",
                  artifact: str | None = None) -> dict:
    """跑一个场景并返回逐项观测；不抛异常，失败写进返回值。"""
    window = history.max_rounds()
    head = _git_text(repo, "rev-parse", "HEAD")
    source_history = repo / history_rel
    history_before = source_history.read_bytes()

    result_path = workdir / f"{scenario.name}-result.json"
    # 子进程崩溃时不能读到上一轮的旧文件（R103 起每个场景一个子进程）。
    result_path.unlink(missing_ok=True)
    # run_id 带 HEAD 短 SHA：同一 commit 重跑时稳定，换 commit 自动换键；
    # replay 的 record 对同键是覆盖，不会把一次回放记成两轮。
    run_id = f"replay-ci-{scenario.name}-{head[:8]}"
    argv = [
        "--repo", str(repo),
        "--run-id", run_id,
        "--history", history_rel,
        "--branch", branch,
        "--attempts", str(scenario.attempts),
        "--result-json", str(result_path),
    ]
    if scenario.fetch:
        # 全链：artifact API 的 run id 与历史 run id 是两件事，必须分开传。
        argv += [
            "--fetch-api-url", str(fetch_api_url),
            "--fetch-run-id", str(fetch_run_id),
        ]
        if fetch_repo:
            argv += ["--fetch-repo", fetch_repo]
        if artifact:
            argv += ["--artifact", artifact]
    else:
        metrics = _metrics(workdir / f"{scenario.name}-metrics.json")
        argv += ["--metrics", str(metrics)]
    if scenario.reject_pushes:
        argv += ["--reject-pushes", str(scenario.reject_pushes)]
    if scenario.conflict:
        argv.append("--conflict")
    if scenario.conflict_on_reject:
        argv += ["--conflict-on-reject", str(scenario.conflict_on_reject)]

    code, output = _invoke_replay(argv)
    result = _read_result(result_path)
    if scenario.succeeds:
        expected_rounds = min(before + scenario.rounds_delta, window)
        expected_last_run_id = run_id
        # 窗口满时轮数会恒定在 MAX_ROUNDS：这一项只能证明「窗口没坏」，不能
        # 再证明「本轮写进去了」。rounds_clipped 把这件事写进产物，免得看
        # 日志的人把满窗恒等式（window == window）当成强证据。
        rounds_clipped = before + scenario.rounds_delta > window
    else:
        # 写回失败时本轮不入库，远端只会因夹具注入而变化（目前只有冲突轮）。
        # 注入也遵守 MAX_ROUNDS：满窗时挤掉最早一轮，不会造出窗口 +1 轮。
        expected_rounds = min(before + scenario.injected_rounds, window)
        expected_last_run_id = (
            scenario.expected_last_run_id or baseline_last_run_id)
        # 失败场景不宣称「本轮写入了」，所以「轮数被裁剪」不适用；末条身份
        # 才是远端变化的唯一证据。
        rounds_clipped = False
    expected = {
        "exit_code": scenario.expected_exit,
        "reason": scenario.expected_reason,
        "rounds": expected_rounds,
        "rounds_clipped": rounds_clipped,
        "last_run_id": expected_last_run_id,
        "push_attempts": scenario.push_attempts,
    }
    actual = {
        "exit_code": code,
        "reason": result.get("reason") if result else None,
        "rounds": result.get("rounds") if result else None,
        "last_run_id": result.get("last_run_id") if result else None,
        "push_attempts": result.get("push_attempts") if result else None,
    }

    problems: list[str] = []
    if code != scenario.expected_exit:
        problems.append(
            f"退出码 {code}，期望 {scenario.expected_exit}")
    if result is None:
        problems.append("没有写出 --result-json")
    else:
        if result.get("exit_code") != code:
            problems.append(
                f"result.exit_code={result.get('exit_code')!r} 与进程退出码 "
                f"{code} 不一致")
        if result.get("reason") != scenario.expected_reason:
            problems.append(
                f"reason={result.get('reason')!r}，"
                f"期望 {scenario.expected_reason!r}")
        if result.get("rounds") != expected_rounds:
            problems.append(
                f"rounds={result.get('rounds')!r}，期望 {expected_rounds}")
        if result.get("last_run_id") != expected_last_run_id:
            if scenario.succeeds:
                hint = "（窗口满时这是「本轮已入库」的唯一证据）"
            elif scenario.injected_rounds:
                hint = "（失败场景：远端只应多出注入的冲突轮）"
            else:
                hint = "（失败场景：远端历史不应变化）"
            problems.append(
                f"last_run_id={result.get('last_run_id')!r}，"
                f"期望 {expected_last_run_id!r}{hint}")
        if result.get("push_attempts") != scenario.push_attempts:
            problems.append(
                f"push_attempts={result.get('push_attempts')!r}，"
                f"期望 {scenario.push_attempts}")
    for token in scenario.must_contain:
        if token not in output:
            problems.append(f"输出缺少 {token!r}")
    for token in scenario.must_not_contain:
        if token in output:
            problems.append(f"输出不应包含 {token!r}")
    for token, count in scenario.output_counts:
        actual_count = output.count(token)
        if actual_count != count:
            problems.append(
                f"输出中 {token!r} 出现 {actual_count} 次，期望 {count} 次")

    # 失败沙箱：期望失败场景必须留下现场，随后由驱动清理；成功场景不应留下
    # 任何沙箱。断言「真的留下过」再删，而不是让 runner 的临时目录累积。
    sandbox_cleaned: bool | None = None
    kept = _kept_sandbox(output)
    if scenario.expect_sandbox:
        if kept is None:
            problems.append("期望保留失败沙箱，但输出里没有「沙箱保留在」")
            sandbox_cleaned = False
        elif not kept.is_dir():
            problems.append(f"失败沙箱不存在：{kept}")
            sandbox_cleaned = False
        else:
            sandbox_cleaned = _cleanup_sandbox(kept)
            if not sandbox_cleaned:
                problems.append(f"失败沙箱未能清理：{kept}")
    elif kept is not None:
        problems.append(f"成功场景却保留了沙箱：{kept}")

    # 源仓库只读：HEAD 与 history 字节都必须与调用前一致。放在场景内部检查，
    # 失败时能指出是哪个场景越界，而不是只在最后报一句“变了”。
    source_head_after = _git_text(repo, "rev-parse", "HEAD")
    source_mutated = (
        source_head_after != head
        or source_history.read_bytes() != history_before
    )
    if source_mutated:
        problems.insert(0, "源仓库被改动（HEAD 或 history 字节变化）")

    return {
        "name": scenario.name,
        "ok": not problems,
        "exit_code": code,
        "run_id": run_id,
        "rounds_clipped": rounds_clipped,
        "sandbox_cleaned": sandbox_cleaned,
        "sandbox": str(kept) if kept is not None else None,
        "expected": expected,
        "actual": actual,
        "failure": "；".join(problems),
        "source_mutated": source_mutated,
        "output": output[-OUTPUT_LIMIT:],
    }


def run(repo: Path, branch: str, history_rel: str,
        result_path: Path | None = None,
        summary_path: Path | None = None,
        fetch_api_url: str | None = None,
        fetch_run_id: str | None = None,
        fetch_repo: str = "",
        artifact: str | None = None) -> int:
    repo = Path(repo).resolve()
    window = history.max_rounds()
    scenarios = SCENARIOS + (
        (FETCH_SCENARIO, FETCH_REJECTED_CONFLICT_SCENARIO,
         FETCH_REJECTED_HOOK_AT_4_SCENARIO)
        if fetch_api_url else ())
    try:
        baseline = _baseline(repo, history_rel)
    except BaselineError as exc:
        print(f"replay-ci 基线不可用：{exc}", file=sys.stderr)
        ci_reporting.emit_result(result_path, {
            "schema": RESULT_SCHEMA,
            "repo": str(repo),
            "branch": branch,
            "history": history_rel,
            "ok": False,
            "reason": "baseline-unavailable",
            "detail": str(exc),
            "scenarios": [],
        })
        return EXIT_ENV

    print(
        f"replay-ci：源仓库 {repo} HEAD {baseline['head'][:8]}，"
        f"历史 {baseline['rounds']}/{window} 轮，"
        f"末条 {baseline['last_run_id']}",
        flush=True)
    window_full = baseline["rounds"] >= window
    if window_full:
        print(
            f"replay-ci：注意：历史窗口已满 "
            f"{baseline['rounds']}/{window}，rounds 计数会被"
            f"裁剪；写入判定以 result.last_run_id 为准",
            flush=True)

    records: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="replay-ci-scenarios-") as tmp:
        workdir = Path(tmp)
        for scenario in scenarios:
            record = _run_scenario(
                scenario, repo, branch, history_rel, baseline["rounds"],
                baseline["last_run_id"], workdir,
                fetch_api_url=fetch_api_url,
                fetch_run_id=fetch_run_id,
                fetch_repo=fetch_repo,
                artifact=artifact)
            records.append(record)
            mark = "PASS" if record["ok"] else "FAIL"
            print(
                f"[replay-ci] {mark} {scenario.name}: "
                f"exit={record['exit_code']} "
                f"rounds={record['actual'].get('rounds')} "
                f"last_run_id={record['actual'].get('last_run_id')} "
                f"push_attempts={record['actual'].get('push_attempts')}",
                flush=True)
            if record["failure"]:
                print(f"[replay-ci]   {record['failure']}", flush=True)
                print(record["output"], flush=True)
            if record["source_mutated"]:
                # 源仓库已不可信，继续跑后面的场景只会把基线污染扩散。
                print("[replay-ci] 源仓库被改动，停止后续场景", file=sys.stderr)
                break

    # 场景没跑完（中途因源仓库被改动而停止）同样算失败：不能因为剩下的
    # 没跑就报通过。
    ok = len(records) == len(scenarios) and all(
        record["ok"] for record in records)
    ci_reporting.emit_result(result_path, {
        "schema": RESULT_SCHEMA,
        "repo": str(repo),
        "branch": branch,
        "history": history_rel,
        "before": baseline["rounds"],
        "max_rounds": window,
        "window_full": window_full,
        "source_head": baseline["head"],
        "ok": ok,
        "scenarios": records,
    })
    for record in records:
        reason = "ok" if record["ok"] else "mismatch"
        detail = record["failure"] or (
            f"rounds={record['actual'].get('rounds')} "
            f"push_attempts={record['actual'].get('push_attempts')}")
        if record["ok"] and record["rounds_clipped"]:
            detail += (
                f"（窗口已满：rounds 计数已裁剪，"
                f"本次写入由 last_run_id="
                f"{record['actual'].get('last_run_id')} 证明）")
        ci_reporting.emit_summary(
            summary_path, f"replay-ci-{record['name']}", reason, detail)

    passed = sum(1 for record in records if record["ok"])
    print(f"replay-ci：{passed}/{len(scenarios)} 场景通过", flush=True)
    return EXIT_OK if ok else EXIT_MISMATCH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."),
                        help="源仓库（只读；replay 会克隆到临时沙箱）")
    parser.add_argument("--branch", default="main",
                        help="回放的分支（CI 会先 checkout -B main）")
    parser.add_argument("--history", default=DEFAULT_HISTORY,
                        help="仓库内的历史文件相对路径")
    parser.add_argument("--summary", type=Path, default=None,
                        help="step summary 文件（可选）")
    parser.add_argument("--result-json", type=Path, default=None,
                        help="机读结果工件（可选）")
    parser.add_argument("--fetch-api-url", default=None,
                        help="启用 fetched 场景：先下载 artifact 再写回")
    parser.add_argument("--fetch-run-id", default=None,
                        help="artifact API 的 run id（启用全链时必填）")
    parser.add_argument("--fetch-repo", default="",
                        help="artifact API 的 owner/name（默认取子进程环境）")
    parser.add_argument("--artifact", default=None,
                        help="artifact 名称（默认用 replay 的 e2e-metrics）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if bool(args.fetch_api_url) != bool(args.fetch_run_id):
        print("--fetch-api-url 与 --fetch-run-id 必须同时给出",
              file=sys.stderr)
        return EXIT_USAGE
    return run(args.repo, args.branch, args.history,
               args.result_json, args.summary,
               fetch_api_url=args.fetch_api_url,
               fetch_run_id=args.fetch_run_id,
               fetch_repo=args.fetch_repo,
               artifact=args.artifact)


if __name__ == "__main__":
    raise SystemExit(main())
