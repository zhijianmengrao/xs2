# DeterminFlow (xs2) 交接报告 — Round 101（replay 拒绝/冲突进生产 CI）

> 单 profile：把 R99 的 reject/conflict 回放从 pytest 驱动升级为独立生产
> job；另按用户拍定把 93 项 `_r*` 临时件归档。零产品代码改动（`src/`、
> `web/` 未动）。

## 1. 一句话结论

- R100 §5 的第一条边界已消掉：新增独立只读 job **`replay-ci-writeback`**，
  在真实 checkout / 真实历史文件上跑 **happy / rejected / conflict** 三个
  场景，逐场景断言退出码、`reason`、`rounds`、`push_attempts` 与关键输出。
- 驱动 `scripts/replay_ci_scenarios.py` 在每个场景前后比较源仓库 HEAD 与
  history 字节；一旦变化立即判 1 并停止后续场景。写回只发生在 replay 的临时
  沙箱，真实 origin 不会被推。
- 写权限仍在 `e2e-history-writeback`；新 job 不声明 permissions、不跑
  pytest / e2e / npm / docker、不引 secrets，**PR 与 push 都跑**。
- 本机全量 **2639 passed / 28 skipped / 0 failed（2667 条，244.00s）**；
  R100 为 2624/28（2652），+15 条全部是本轮新增。
- CI run **41373779709** 七 job 全 `success`；新 job 日志三场景 **3/3 PASS**。

## 2. 实现要点

1. **生产驱动**：`scripts/replay_ci_scenarios.py` 按
   `e2e_workflow_stub.py` 的多场景模板，调用真实的
   `replay_ci_writeback.main(argv)`（不复制逻辑），用
   `redirect_stdout/stderr` 捕获输出做文案断言。
2. **三个场景**（精确计数，不是容忍量）：

   | 场景 | 参数 | rounds 增量 | push_attempts | 关键输出 |
   |---|---|---|---|---|
   | happy | 无 | +1 | 1 | `已写回`，且不含 `push 被拒（第` |
   | rejected | `--reject-pushes 1` | +1 | 2 | `push 被拒（第 1 次）`、`第 2 次尝试` |
   | conflict | `--conflict` | +2 | 2 | `rebase 冲突（第 1 次）`、`第 2 次尝试` |

   期望 rounds 用 `min(before + delta, e2e_retry_history.MAX_ROUNDS)`，当前
   17/40，不把 17 写死。
3. **退出码**：0 全符 / 1 场景不符 / 2 用法 / 3 基线不可用（repo 不是 git
   仓、history 缺失或读不懂）。3 与 1 分开——「环境坏」不冒充「回放坏」。
4. **机读结果**：`ci_reporting.emit_result` 原子写
   `schema/repo/branch/history/before/source_head/ok/scenarios[]`，每个场景带
   `expected/actual/failure/output`（输出截断 8KB）；每个场景一行
   `emit_summary`。CI 上传 `replay-ci-result`（`if: always()`）。
5. **CI job**：`ubuntu-24.04`、`timeout-minutes: 10`；PR 的 checkout 是
   detached HEAD，先用 `git checkout -B main` 物化本地分支（只改 runner 临时
   工作区）。`e2e-history-writeback` 里不出现 replay 驱动——写权限与仓库代码
   执行面仍分离。
6. **归档**：93 项 `_r*`（约 11MB）移到 `_archive/r100/`，`/.gitignore` 增加
   `/_archive/`，仍不入库；`config/skills_config.json` 外来改动保持未提交。

## 3. 用例（+15）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_scenarios.py` | 6 | 三场景真实跑通（0，rounds/push_attempts 逐项）；`push_attempts` 错误必须 1；源仓库被改动必须 1 且停后续场景；非 git 仓/坏 history → 3；场景表计数与 R99 语义一致 |
| `tests/test_ci_replay_wiring.py` | 9 | job 存在/超时；只读且写权限仍唯一；驱动恰好一处且参数齐全；不跑 pytest/e2e/npm/docker、无 secrets/continue-on-error；PR 也跑；上传 `always()`；`checkout -B main`；非恒绿；写回 job 不含 replay |

**本机全量**：**2639 passed / 28 skipped / 0 failed**（2667 条，244.00s）。
CI：ubuntu **2602 / 65**、windows **2638 / 29**，均 **2667**；前端与容器
job 无改动但照常全绿。

## 4. 变异验证（8/8 全咬合）

| 变异 | 结果 |
|---|---|
| M63 删 rejected 场景 | 3 红（含场景表） |
| M64 不校验 push_attempts | **仅** `test_driver_does_not_trust_the_replay_exit_code` 红 |
| M65 conflict 增量 2→1 | 2 红（集成 + 场景表） |
| M66 删源仓只读检查 | **仅** `test_driver_stops_when_the_source_repo_is_mutated` 红 |
| M67 删整个 CI job | 8 个接线测试全红，既有写回测试 17 条仍绿 |
| M68 job 加 `contents: write` | 新接线 + 既有 `test_write_permission_belongs_only_to_the_writeback_job` 各 1 红 |
| M69 用 pytest 替换驱动调用 | 3 红（驱动调用/不跑 pytest/透传退出码） |
| M70 上传去掉 `if: always()` | **仅** `test_replay_job_uploads_its_result_even_on_failure` 红 |

还原全部用 `cp` 备份并核对 sha256（**没有** `git checkout --`）。

## 5. 边界

- 新 job 只在 ubuntu 跑；Windows 的 replay 行为仍由 `windows-backend` 的
  pytest 覆盖（reject/conflict 用例已在两个平台执行，本轮 windows
  **2638 / 29**）。
- **永久拒绝**（三次全拒）仍只由 pytest 覆盖：它按设计保留失败沙箱，生产
  job 不制造需要人工清理的现场。
- 不跑 `--fetch-api-url`：下载→写回的整链已由 `e2e-history-writeback` 的
  生产 fetch 与 R96/R99 用例覆盖。
- 驱动在进程内调用 `replay.main()`（不是 subprocess）：CLI 解析仍被走到，
  且能捕获输出；CI job 本身就是生产调用者。
- 历史达到 `MAX_ROUNDS=40` 后，rejected/happy 的增量会被裁剪压成 0；驱动用
  `min(before + delta, 40)` 计算期望，不会误报。
- `_archive/r100/` 只在本地保留，不随仓库分发。

## 6. 提交与 CI

- 代码+测试提交 **`d44dfd2`**；CI run **41373779709** 七 job 全 `success`：
  - `replay-ci-writeback`：`[replay-ci] PASS happy: exit=0 rounds=18
    push_attempts=1`；`PASS rejected: ... rounds=18 push_attempts=2`；
    `PASS conflict: ... rounds=19 push_attempts=2`；`3/3 场景通过`；artifact
    `replay-ci-result` 1315 字节。
  - backend **2602 / 65**、windows **2638 / 29**，均 **2667**（与本地
    2639/28 的差是平台专属 skip，总数一致）。
  - 写回 job：历史 **17 → 18 轮**（`ci-41373779709`、`source=ci`、
    10/10/0），main 头 bot 提交 **`48a32ed`** 带 `[skip ci]`，未自触发。
- 本文档回填提交本身会再触发一轮，预计 **18 → 19**；这是「一次 main push =
  一轮」的既有语义，不是缺陷。

## 7. 本轮教训

1. **生产 job 不能寄生在写权限 job 里**：既有契约把
   `writers == ["e2e-history-writeback"]` 与「写回 job 不跑仓库测试」都钉死
   了；新增的 replay 只能落在独立的只读 job，否则两条测试会同时红。
2. **PR 的 checkout 是 detached HEAD**：本机在 `main` 上直接跑驱动永远暴露
   不了 `git clone -b main` 找不到本地分支；job 里的 `git checkout -B main`
   是必要步骤，不是仪式。
3. **驱动不能盲信子调用的退出码**：M64 只有「读 result 字段做断言」能发现
   「子调用退 0 但 push_attempts 错」；只看退出码的回放 job 会是一个恒绿的
   新防护。
4. **3 与 1 必须分开**：基线不可用（repo/history）不是回放语义失败；混成
   一个码会把排查方向带向沙箱 git，而真正的问题是 checkout 或数据。
5. **归档不是删除**：`_archive/r100/` + 忽略规则让 11MB 历史现场仍可回查，
   工作树根只留当前轮——比直接删除多一条可回退路径。
