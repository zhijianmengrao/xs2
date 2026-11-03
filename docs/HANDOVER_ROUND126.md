# DeterminFlow (xs2) 交接报告 — Round 126

> 单 profile。五轮连推第 2 轮：**失败形状 × 大预算**——把 R119 的失败形状
> 夹具放进 R124 的 9 次尝试链。R124 证明大预算在生产 artifact（全过形状）
> 上可达；R126 证明同一条长链换成失败形状时，failed/retried/attempts 与
> 逐场景 `first_failure` 原样落库，不因路径变长被重算。生产行为零改动。

## 1. 一句话结论

- 全链场景 **11→12**：`fetched-failure-shape-hook-at-8`（夹具 artifact
  `e2e-metrics-failure-shape` + 预算/注入 8 + attempts=9，第 9 次成功、
  净 +2）；`replay-ci-fetch-chain` 记录 **28→29**。
- 场景断 `metrics 内容 total=4 passed=3 failed=1 retried=1 attempts=5`、
  `metrics 语义 ok_0=ok/1 retry_1=retry/2 fail_2=fail/1 ok_3=ok/1`、
  `metrics 首次失败` 两行、`rebase 冲突（第 8 次）`、`第 9 次尝试`。
- **用例总数 2735 → 2738**（R127/R128 另加）；端到端列表与 API 调用数
  12 同步。

## 2. 为什么是这一轮

大预算链（R124）与失败形状（R119）各自成立，但「9 次 push 的长链里夹具
内容是否被重算」没有交叉证据：全过形状的 `failed=0` 会让计数清零完全隐形
（R116 的教训）。R126 用同一夹具把这条交叉钉住。

## 3. 测试

- `test_fetch_failure_shape_scenarios_pin_content_and_retry`：补第三格
  ——`conflict_on_reject == reject_pushes == 8`、`attempts == 9`、
  `rounds_delta == 2`、内容三行全在 `must_contain`；
- `test_driver_runs_the_fetch_chain_end_to_end`：12 场景列表 + 新场景
  actual（push_attempts=9）+ 输出指纹 + API 调用 ≥12。

## 4. 判据台账

- #15 标题扩到 R126；描述补大预算 × 失败形状组合。
- §6 复核表该行补端到端用例（已含）。

## 5. 验证

- 定向：2 passed（46.74s；场景文件全量 64 passed，315.34s）。
- 本机全量（R128 最终代码统一跑）：**2710 passed / 28 skipped / 0 failed**
  （2738 条）。
- 变异 **M1–M3 3/3**：
  - M1 全链元组漏掉新场景 → 端到端列表红；
  - M2 新场景 `attempts` 改 8 → 表不变量（`attempts == 预算+1`）红；
  - M3 新场景 `artifact` 置 None → 回退全过 artifact，`total=4` 指纹红。
- 变异日志：`_r126_m1.log`、`_r126_m2.log`、`_r126_m3.log`。

## 6. CI

随五轮合并推送（run 待回填）。

## 7. 边界与遗留

- 夹具只供回放，不进历史、不污染趋势；`e2e-history-writeback` 仍只读
  `e2e-metrics`。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`scripts/replay_ci_scenarios.py`、`tests/test_replay_ci_scenarios.py`、
  R126 文档、PROJECT_INFO、JUDGEMENT_LEDGER。
