# DeterminFlow (xs2) 交接报告 — Round 102（MAX_ROUNDS 耗尽防护）

> 单 profile：历史窗口 40 轮满后 `rounds` 断言会退化成恒等式。本轮把
> 「这一轮真的写进去了」的判断改到 `last_run_id` 身份上，并补 38/39/40
> 三个翻转点。零产品代码改动（`src/`、`web/` 未动）。

## 1. 一句话结论

- 现状：history **19/40**。窗口是自然滚动（`e2e_retry_history.py:321`
  `history[-40:]`），满窗后新轮挤掉最早一轮，不会拒写。
- 问题：驱动 `expected_rounds = min(before + delta, MAX_ROUNDS)`
  （`replay_ci_scenarios.py:212`）。**38 轮**三个场景都不裁剪；**39 轮**
  conflict 的 `+2` 先被压成 `+1`；**40 轮**三场景全部 `40 → 40`——`rounds`
  不再能区分「写了 1 轮」「写了 2 轮」「没写」。`reason` / `push_attempts` /
  输出令牌仍有判定力，丢的是 `rounds_delta` 这一项（尤其 conflict 与 happy
  在满窗时计数同形）。
- 修法：writeback 的 result JSON 增 **`last_run_id`**（远端 `origin/<branch>`
  末条 run_id）与 **`window_full`**；驱动逐场景断言
  `result.last_run_id == 本轮 run_id`。窗口状态再怎么变，末条必须是这一轮。
  `rounds` 仍按 `min(...)` 断言，另用 **`rounds_clipped`** 明说计数是否已被
  裁剪；满窗时 step summary 追加「计数已裁剪，本次写入由 last_run_id=… 证明」。
- dry-run 满窗不再报「+0，未写入」：改为「历史窗口已满 40/40 轮（写入挤掉
  最早 1 轮，净 +0，未写入）」——净 0 与「没有变化」不再同形。
- 本机全量 **2645 passed / 28 skipped / 0 failed（2673 条，245.42s）**；
  R101 为 2639/28（2667），**+6** 全部是本轮新增。
- 变异 **M71–M78 8/8 全咬合**；M71 / M75 / M78 各自唯一咬合。

## 2. 实现要点

1. **远端历史一次读全**：`ci_writeback_history.py` 的 `_remote_rounds` 改为
   `_remote_history`，返回 `origin/<branch>` 的条目列表；轮数与末条 run_id
   来自同一次读取。历史坏掉/路径不在仓库内仍给 `null`，不猜。
2. **result JSON 扩字段**：除 `exit_code/reason/detail/rounds/push_attempts/
   dry_run` 外，新增：
   - `last_run_id`：远端已入库历史的末条 run_id。dry-run 不推送，所以它
     仍指向上一次已入库的轮次，不是本轮；
   - `window_full`：`rounds >= MAX_ROUNDS`（远端口径）。
3. **驱动的身份断言**：`_run_scenario` 的 `expected` / `actual` 都带
   `last_run_id`，等于本轮的 `replay-ci-{scenario}-{head8}`。失败消息写明
   「窗口满时这是『本轮已入库』的唯一证据」。
4. **裁剪可见**：`rounds_clipped = before + delta > MAX_ROUNDS`，逐场景写进
   record；顶层 result 增 `max_rounds` / `window_full`。满窗时启动日志先打
   一行「rounds 计数会被裁剪；写入判定以 result.last_run_id 为准」。
5. **dry-run 满窗文案**：`_rehearse` 用 `added / dropped / net` 三个量说话
   （按上一份历史的 run_id 集合判断是新增还是覆盖）。`dropped > 0` 时走
   「窗口已满」分支；普通写入仍报 `+N`。
6. **CI job 注释**：`ci.yml` 的 `replay-ci-writeback` 注释补 R102 说明；job
   的调用参数、权限与隔离不变。

翻转点（实测）：

| before | happy | rejected | conflict | 被裁剪 |
|---|---|---|---|---|
| 38 | 39 | 39 | 40 | 无 |
| 39 | 40 | 40 | 40 | **conflict**（+2 → +1） |
| 40 | 40 | 40 | 40 | **三个场景全部** |

## 3. 用例（+6）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_scenarios.py` | 4 | 38/39/40 参数化：expected/actual rounds、`rounds_clipped`、`last_run_id`、`window_full`、summary 里「窗口已满」的出现次数（0/1/3）；满窗时其余四项全对、只有末条不是本轮 → 必须由 `last_run_id` 判 1，且失败消息不含 exit/reason/rounds/push_attempts 的异议 |
| `tests/test_ci_writeback_history.py` | 2 | 满窗写入：rounds 恒 40、`last_run_id=ci-new`、`window_full=true`、最早一轮被挤掉；满窗 dry-run：输出含「窗口已满」「挤掉最早 1 轮」，`last_run_id` 是远端旧末条，文件一个字节不变 |

既有用例同步补断言：written / no-change / push-rejected / missing-metrics /
dry-run 的 `last_run_id`、`window_full`；回放层 rejected/conflict 透传
`last_run_id`，永久拒绝为 `null`。

**本机全量**：**2645 passed / 28 skipped / 0 failed**（2673 条，245.42s）。
R101 为 2639/28（2667）。

## 4. 变异验证（8/8 全咬合）

| 变异 | 结果 |
|---|---|
| M71 删驱动的 `last_run_id` 断言 | **仅** `test_window_full_identity_is_the_only_remaining_witness` 红（1 failed / 9 passed） |
| M72 result 去掉 `last_run_id` 字段 | 11 红（写回 result 6 条 + 驱动 4 条 + 集成 1 条） |
| M73 `last_run_id` 取 `remote[0]`（首条） | 6 红（满窗两条 + 驱动 4 条） |
| M74 `rounds_clipped` 恒 False | 2 红（39/40 参数化；38 正确保持绿） |
| M75 满窗 dry-run 分支不可达 | **仅** `test_dry_run_at_the_window_reports_the_dropped_round` 红 |
| M76 `expected_rounds` 去掉 `min` 裁剪 | 3 红（39/40 + identity） |
| M77 `window_full` 恒 False | 2 红（40 + identity） |
| M78 `dropped` 恒 0 | **仅** `test_dry_run_at_the_window_reports_the_dropped_round` 红 |

还原全部用 `cp` 备份并核对 sha256（**没有** `git checkout --`）。

## 5. 边界

- **没有改 `MAX_ROUNDS`**（保持 40）。本轮只修「满窗时还能不能判」；保留期
  策略（40→80 / 按天滚动）是另一个决策，未做。
- `last_run_id` 由 writeback 自己从 `origin/<branch>` 读出后写进 result；
  驱动不直接读沙箱 origin（成功即删）。这仍是同一段代码的读与写，不是独立
  第二证据源；但它把「计数」换成了「身份」，不再依赖窗口状态。
- 源历史若被手工改成 >40 条（`validate_history` 不限制长度），baseline 会
  >`MAX_ROUNDS`；驱动按 `min` 期望 40、`window_full=true`，判定不受影响。
- 永久拒绝（三次全拒）、replay job 上 Windows、`--fetch-api-url` 全链、
  驱动子进程化仍未做（R101 §5 的其余边界）。
- **CI 未跑、代码未提交未推送**——等待拍定后提交。

## 6. 提交与 CI

- 当前工作树改动：`scripts/ci_writeback_history.py`、
  `scripts/replay_ci_scenarios.py`、`tests/test_ci_writeback_history.py`、
  `tests/test_replay_ci_scenarios.py`、`tests/test_replay_ci_writeback.py`、
  `.github/workflows/ci.yml`、本文件与 PROJECT_INFO/JUDGEMENT_LEDGER。
- `config/skills_config.json` 的外来改动保持未提交。
- 推送后预计写回 **19 → 20**（代码提交）**→ 21**（文档回填）；七个 job 需
  全绿，`replay-ci-writeback` 三场景应仍为 3/3，且日志里带
  `last_run_id=replay-ci-...`。

## 7. 本轮教训

1. **「计数正确」不等于「计数有判定力」**：`min(before+delta, 40)` 在满窗时
   把一次真写入与零写入压成同一个数。同形的两个状态要换证据（身份），不是
   把阈值加大。
2. **裁剪点不是单一值**：conflict 的 +2 在 **39** 轮就先被裁剪，早于
   happy/rejected 的 40。flip-point 必须按 `(before, delta)` 两个维度看。
3. **dry-run 的净增量 0 有两种含义**（没有变化 vs 满窗挤压）；只报 `+0`
   会把两者同形。同时报 `added / dropped / net` 才说清。
4. **同一个短语两种说法**（print 写「历史已满」、detail 写「窗口已满」）被
   本轮用例当场抓到；同一事实只留一处文案来源。
5. **变异唯一咬合要说得出「哪条用例」**：M71/M75/M78 的单独红证明新用例
   不是冗余装饰；M72/M73/M76/M77 的宽红则说明字段/常量被多处共用。

## 8. 下一步候选

- 保留期策略：`MAX_ROUNDS` 40→80，或改成按天滚动（趋势样本）。
- 永久拒绝进生产 CI + 失败沙箱的断言后清理。
- replay job 上 Windows（矩阵或独立 job）。
- 驱动改 subprocess（真实 CLI 进程边界）。
- `--fetch-api-url` 全链（下载 → 写回）进 replay job。
