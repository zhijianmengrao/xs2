# DeterminFlow (xs2) 交接报告 — Round 117（全链注入 N=6 · fetch-chain）

> 单 profile。五轮连续推进的第 4 轮：把本地矩阵的 **N=6 / attempts=7**
> 搬进全链——真实 artifact 下载后再走六次拒绝、末次注入、第 7 次成功。
> 生产行为零改动（只加全链场景与测试），`src/`、`web/` 零改动。

## 1. 一句话结论

- 全链场景 3 → **4**：新增 `fetched-rejected-hook-at-6`（预算 6/注入 6/
  attempts 7，成功净 +2）；`replay-ci-fetch-chain` 从 18/18 变 **19/19**。
- 新增 `test_fetch_hook_scenarios_match_the_local_formula`：全链 N=4/6
  必须与本地成功场景同用一组代数关系（注入点=预算、attempts=预算+1、
  净 +2、拒绝/模拟计数=预算、断 `metrics 内容 total=10` 与 `metrics 语义`）。
- 本机全量 **2695 passed / 28 skipped / 0 failed**（2723 条，368.93s），
  比 R116 净增 **+1**。
- 定向 **3 passed**（29.91s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. 新场景

`FETCH_REJECTED_HOOK_AT_6_SCENARIO`：

| 字段 | 值 |
|---|---|
| 名称 | `fetched-rejected-hook-at-6` |
| fetch | True（走真实 `fetch_ci_artifact.fetch()`） |
| 预算 / 注入 / attempts | 6 / 6 / 7 |
| 期望 | exit 0、`reason=written`、rounds +2、末条本轮 run_id、push 7 |
| 输出 | `已下载 1 个文件`、`metrics 内容 total=10`、`metrics 语义`、`第 6 次拒绝时注入冲突`、`rebase 冲突（第 6 次）`、`第 7 次尝试`、`已写回` |

`replay_ci_scenarios.run()` 的 fetch 场景元组从 3 条扩到 4 条；本地场景仍
15 条，所以全链 job 的总场景数是 **19**。

## 3. 公式测试

`tests/test_replay_ci_scenarios.py::test_fetch_hook_scenarios_match_the_local_formula`
对 `FETCH_REJECTED_HOOK_AT_4_SCENARIO` / `..._AT_6_SCENARIO` 逐条断言：

- `conflict_on_reject == reject_pushes`；
- `attempts == reject_pushes + 1`、`push_attempts == attempts`；
- `rounds_delta == 2`、`expected_exit == 0`、`expected_reason == written`；
- `output_counts` 等于「预算次拒绝/模拟」；
- `metrics 内容 total=10` 与 `metrics 语义` 仍在 `must_contain`。

**全链只换 metrics 来源，不换写回语义**；N=4/6 在两处说两套话时，
这条公式测试先红。

## 4. 判据台账

- #16 补全链 N=6（`fetched-rejected-hook-at-6`）。
- §6 复核表补公式测试。
- §10.5 补一句：全链与本地共用同一组代数关系。

## 5. 验证

- 定向：**3 passed**（`-k "fetch_hook_scenarios or fetch_chain_end_to_end
  or hook_scenarios_are_reachable"`，29.91s）。
- 本机全量：**2695 passed / 28 skipped / 0 failed**（2723 条，368.93s）。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 全链 N=6 的 attempts 改成预算值 → 公式测试红；
  - M2 fetch 场景元组漏掉 N=6 → 全链端到端用例红（18/18，缺场景）；
  - M3 全链 N=6 的净轮数写成 1 → 公式测试红。
- 变异日志：`_r117_mutate.log`；备份 `_r117_backup/`（未提交）。

## 6. CI

- run **41496585289**（18:05:14→18:11:40 UTC，约 6m26s）：**10 个 job 全
  `success`**。
  - backend **2658/65**、windows-backend **2694/29**（均 **2723**）；
  - `replay-ci-writeback` 两平台各 **15/15 PASS**；
  - `replay-ci-fetch-chain` 两平台各 **19/19 PASS**（15 本地 + 4 全链）；
    `fetched-rejected-hook-at-6` 实测 `exit=0 rounds=48 push_attempts=7`；
  - 前端 **490 / 0**。
- 写回历史 **46 → 47**（`ci-41496585289`、`source=ci`），bot 提交
  `756a6c5`（`[skip ci]`，未自触发）。

## 7. 边界与下一步

- 全链 N=6 仍使用生产真实 artifact（10/10 全过）；失败形状的组合留在
  R116 的本地用例。
- N>6 / attempts>7 未建场景。
- `config/skills_config.json` 保持未提交。

## 8. 提交与 CI

- 代码+文档提交 **c38193d**（`test(R117): 全链注入场景扩到 N=6（含 R116
  CI 回填）`），显式路径 add；`config/skills_config.json` 未纳入。
- CI run **41496585289**（见 §6）；写回 bot `756a6c5`。
- 下一轮（R118 收口 docs）预计写回 **47 → 48**。
