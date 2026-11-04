# DeterminFlow (xs2) 交接报告 — Round 114（注入矩阵 N=6/7 + 场景表不变量）

> 单 profile。用户要求按推荐方案连续推进 **R114–R118** 五轮；本轮是第 1 轮：
> 注入矩阵扩到 **N=6/7**，并用场景表不变量把「注入点可达」的代数关系钉住。
> 生产行为零改动（只动回放场景表与测试），`src/`、`web/` 零改动。

## 1. 一句话结论

- 本地场景 13 → **15**：新增 `rejected-hook-inject-at-3-budget-6`（预算 6/
  注入 3/attempts 6，中段注入后还有三次拒绝）与
  `rejected-hook-budget-6-at-6`（预算 6/注入 6/attempts 7，第 7 次成功）。
- 新增表不变量 `test_hook_scenarios_are_reachable_and_consistent`：
  每个钩子场景的注入点必须 ≤ 预算与 attempts；成功/失败的 reason 来源、
  净轮数、push/simulated 计数全部由表推导并逐项断言。
- 本机全量 **2690 passed / 28 skipped / 0 failed**（2718 条，363.69s），
  比 R113 净增 **+1**（一条不变量测试）。
- 定向 **17 passed**（161.34s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. 新增场景

| 场景 | 预算/注入/重试 | 观测 |
|---|---|---|
| `rejected-hook-inject-at-3-budget-6` | 6 / 3 / 6 | exit 1、`reason=push-rejected`（注入后还有第 4–6 次拒绝）、rounds 基线+1、末条 `replay-conflict`、push 6、`simulated rejection` 6 |
| `rejected-hook-budget-6-at-6` | 6 / 6 / 7 | exit 0、净 +2、第 6 次拒绝时注入、第 7 次成功 |

第一条把「注入发生在预算中段」与「注入在最后一次」区分开：两次都是失败，
但 `reason` 分别是 `push-rejected` 与 `rebase-conflict`。第二条把 N 推到 6、
attempts 推到 7，证明重试上限与注入点可以继续同步抬高。

## 3. 表不变量

`tests/test_replay_ci_scenarios.py::test_hook_scenarios_are_reachable_and_consistent`
对 `SCENARIOS` 里所有 `conflict_on_reject` 场景逐条断言：

- `1 <= conflict_on_reject <= reject_pushes`；
- `1 <= conflict_on_reject <= attempts`；
- `push_attempts == attempts`；
- 成功：`attempts == reject_pushes + 1`、`rounds_delta == 2`、
  `reason == written`、计数等于「预算次拒绝」；
- 失败：`injected_rounds == 1`、`rounds_delta == 0`、
  `reason == rebase-conflict iff 注入点 == attempts 否则 push-rejected`、
  末条 `replay-conflict`、计数等于 attempts。

**为什么需要它**：场景表是判据的唯一来源。未来加 N 时若写出「注入点 >
预算」或「注入点 > attempts」的组合，CLI 会退 2，而场景表仍看起来在测——
不变量把这种静默失效提前变成表本身的错误。首跑还抓到一个口径差异：
成功场景的 `injected_rounds` 一直是 0，净增量由 `rounds_delta=2` 表达；
不变量改成按成功/失败分别断言，而不是强行统一。

## 4. 判据台账

- #16「拒绝预算、注入时机与重试上限」扩到 N=6/7，并注明表不变量
  `test_hook_scenarios_are_reachable_and_consistent`。
- §6 复核表补该用例。
- §10.5 补 N=6/7 的行；核心结论不变：可达性由预算与重试次数共同决定。

## 5. 验证

- 定向：**17 passed**（`tests/test_replay_ci_scenarios.py`，161.34s）。
- 本机全量：**2690 passed / 28 skipped / 0 failed**（2718 条，363.69s）。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 成功场景 attempts 改成预算值 → 不变量红；
  - M2 中段注入的 reason 写成 rebase-conflict → 表钉 + 不变量 2 红；
  - M3 默认 attempts 退回 2 → 不变量红（多条注入点不可达）。
- 变异日志：`_r114_mutate.log`；备份 `_r114_backup/`（未提交）。

## 6. CI

- run **41487708892**（17:05:09→17:18:46 UTC，约 13m37s）：**10 个 job 全
  `success`**。
  - backend **2653/65**、windows-backend **2689/29**（均 **2718**）；
  - `replay-ci-writeback` 两平台各 **15/15 PASS**；
  - `replay-ci-fetch-chain` 两平台各 **18/18 PASS**（15 本地 + 3 全链）；
  - 前端 **490 / 0**。
- 写回历史 **43 → 44**（`ci-41487708892`、`source=ci`），bot 提交
  `0c97b74`（`[skip ci]`，未自触发）。

## 7. 边界与下一步

- 覆盖到 N=6 / attempts=7；N>6 与更大预算未建场景。
- 生产 `DEFAULT_ATTEMPTS=3` 未变；`--attempts` 仍只影响回放沙箱。
- 全链场景仍只有 3 条（N=4 late injection 已覆盖）；N=6 全链留到 R117。
- `config/skills_config.json` 保持未提交。

## 8. 提交与 CI

- 代码+文档提交 **e895a3a**（`test(R114): 注入矩阵扩到 N=6/7 + 场景表不变
  量`），显式路径 add，5 文件 +220/−16；`config/skills_config.json` 未纳入。
- CI run **41487708892**（见 §6）；写回 bot `0c97b74`。
- 本轮按五轮连推的节奏，R114 的 CI 回填与 R115 代码共用下一次推送；
  下一轮 CI 预计写回 **44 → 45**。
