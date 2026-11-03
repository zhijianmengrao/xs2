# DeterminFlow (xs2) 交接报告 — Round 125

> 单 profile。五轮连推（R125–R129）第 1 轮：**满窗实战**——用真实默认窗口
> （80）预演「历史顶满时 CI replay 怎么活」。R102 的边界几何用显式窗口 40
> 钉住；但生产 history 终将走到 80（本轮已 52/80），届时成功场景的 rounds
> 断言退化为恒等式，唯一写入证据是 `last_run_id`。这一幕必须在到 80 之前
> 先演过一次。生产行为零改动（只加测试）。

## 1. 一句话结论

- 新增参数化用例 `test_driver_keeps_witnesses_at_the_default_window`
  两格：满窗（80/80）与满窗前 1 轮（79/80），**不设** `XS2_MAX_ROUNDS`。
- 两格都跑完整 17 场景真实回放；期望值从场景表现算（成功按
  `rounds_delta`、失败按 `injected_rounds`），表加场景自动跟着覆盖。
- 满窗几何钉死：成功场景 8 个全部 `rounds_clipped=True`、失败注入裁到
  80 不越窗、摘要逐条「窗口已满」；79 时只有 6 个 +2 场景被裁。
- **+2 → 总用例 2735**，定向见 §5；全量见 §5。

## 2. 为什么是这一轮

R102 证明满窗时「rounds 恒等、last_run_id 是唯一证据」，但那条判据只在
显式 40 窗口下演过（R112 又补了 8）。生产默认 80 从未满过——第一次满窗
会发生在 CI 的 replay job 里，而且没有预演。R125 把默认窗口下 79/80 两格
在测试里跑真：等 history 真到 80 时，CI 已经见过这个形状。

## 3. 测试

`tests/test_replay_ci_scenarios.py::test_driver_keeps_witnesses_at_the_default_window`
（`pytest.mark.parametrize` offset 0/1）：

| offset | 种子 | 断言 |
|---|---|---|
| 0 | 80/80 | `window_full=True`；8 个成功场景 rounds=80 且 `rounds_clipped=True`；失败注入裁到 80；末条=本轮/`replay-conflict`/基线末条；摘要「窗口已满」×8 |
| 1 | 79/80 | 只有 +2 场景被裁（6 个）；+1 场景 rounds=80 不裁；摘要 ×6 |

断言 `window == MAX_ROUNDS`（80）：默认值被改或被环境覆盖时这组用例先红。

## 4. 判据台账

- §6 复核表补该用例；§10.9（R129 收口）汇总。

## 5. 验证

- 定向：2 passed（57.33s）。
- 本机全量（R128 最终代码统一跑）：**2710 passed / 28 skipped / 0 failed**
  （2738 条）。环境：便携 MinGit + `core.symlinks=true`，同 R124。
- 变异 **M1–M3 3/3**（`cp` 还原后 sha256 逐字节相同）：
  - M1 `_run_scenario` 成功场景期望去掉 `min(…, window)` → 满窗格红；
  - M2 成功场景 `rounds_clipped` 恒 False → 满窗格摘要计数红；
  - M3 失败场景期望去掉 `min` → 满窗格失败场景红。
- 变异日志：`_r125_m1.log`、`_r125_m2.log`、`_r125_m3.log`。

## 6. CI

随五轮一起推送 tip **`c9710a0`**，合并 run **41686188378**：10 个 job 全
`success`（17:38:24→17:53:44 UTC，约 15m20s）。两平台
`replay-ci-writeback` **17/17 PASS**、`replay-ci-fetch-chain` **29/29
PASS**；backend **2673/65**、windows-backend **2709/29**（均 2738）。
写回历史 **52→53**（`ci-41686188378`）；本文档回填提交预计 **53→54**。

## 7. 边界与遗留

- 趋势表仍只展示、不判趋势好坏（R78/R115）；按天滚动不做（R112）。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_replay_ci_scenarios.py`、R125 文档、PROJECT_INFO、
  JUDGEMENT_LEDGER。生产代码零改动。
