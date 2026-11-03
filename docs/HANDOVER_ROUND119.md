# DeterminFlow (xs2) 交接报告 — Round 119

> 单 profile。收口轮之后的下一轮：**A1** 回填 R118 的 CI 实测结果；
> **B1** 把 R116 的「失败形状 × 拒绝/注入」组合搬进生产 fetch-chain；
> **C1** `config/skills_config.json` 继续保持未提交。
> 生产行为零改动（只加测试夹具、场景与 CI 上传步骤），`src/`、`web/` 零改动。

## 1. 一句话结论

- R118 docs run **41498830796**：**10 个 job 全 `success`**（18:15:32→
  18:30:22 UTC，约 14m50s），`e2e-history-writeback` 成功，写回 **47→48**；
  R118 文档已回填实际结果。
- 全链场景 4 → **6**：新增 `fetched-failure-shape-rejected` 与
  `fetched-failure-shape-rejected-conflict`，使用 CI 单独上传的
  `e2e-metrics-failure-shape` 夹具（4 场景 / 1 失败 / 1 重跑）。
- 全链总场景 19 → **21**（15 本地 + 6 全链）。
- 本机全量 **2698 passed / 28 skipped / 0 failed**（2726 条，398.90s），
  比 R118 净增 **+3**。
- 定向 **11 passed**（32.54s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. A1：R118 CI 回填

- R118 docs 提交 `d88dff4` 触发 run **41498830796**：10 个 job 全
  `success`，含 `e2e-history-writeback`。
- 写回 **47→48**；`HANDOVER_ROUND118.md` 的 §2/§6/§8 与
  `PROJECT_INFO.md` 的 R118 条目已从「预计」改为实测值。
- 这一步不涉及代码；R118 仍是零代码改动的收口轮。

## 3. B1：全链失败形状 × 拒绝/注入

### 3.1 夹具 artifact

`tests/fixtures/e2e_metrics_failure_shape/e2e-metrics.json`：

| 字段 | 值 |
|---|---|
| 场景 | `ok_0`、`retry_1`、`fail_2`、`ok_3` |
| 计数 | `total=4 passed=3 failed=1 retried=1 attempts=5` |
| 语义 | `ok_0=ok/1 retry_1=retry/2 fail_2=fail/1 ok_3=ok/1` |
| 首次失败 | `retry_1=第一次判红：模拟超睡；fail_2=模拟失败：节点未完成` |

CI 的 `backend` job 在 main push 上把它上传为独立 artifact
`e2e-metrics-failure-shape`。它**不是**生产 e2e 输出：
`e2e-history-writeback` 仍只读 `e2e-metrics`，夹具不会写进历史、污染趋势。

### 3.2 新场景

| 场景 | 拒绝/注入 | 观测 |
|---|---|---|
| `fetched-failure-shape-rejected` | `--reject-pushes 1` | exit 0、`written`、rounds +1、push 2、输出「第 2 次尝试」 |
| `fetched-failure-shape-rejected-conflict` | `--reject-pushes 2 --conflict-on-reject 1` | exit 0、`written`、rounds +2、push 3、输出「第 1 次拒绝时注入冲突」「rebase 冲突（第 1 次）」「第 3 次尝试」 |

两条都断言 artifact 的计数、`metrics 语义` 与逐场景 `first_failure`
原样出现：重试只改变 push 次数与远端轮数，不能把内容重算掉。

### 3.3 场景表与驱动

- `Scenario` 新增 `artifact: str | None`；`None` 表示用驱动级
  `--artifact`（默认 `e2e-metrics`），失败形状场景固定指向夹具名。
- `run()` 的全链元组追加两条新场景；`_run_scenario` 按
  `scenario.artifact or artifact` 透传，避免场景悄悄回退到全过 artifact。
- `replay_ci_fetch_chain` 的调用方式不变：仍然只传 `--fetch-api-url` /
  `--fetch-run-id` / `--fetch-repo`；artifact 名由场景表决定。

## 4. 测试

- `tests/test_replay_ci_scenarios.py::test_fetch_failure_shape_scenarios_pin_content_and_retry`：
  校验夹具计数/场景名，以及两条场景的 `artifact`、rounds/push、输出 token。
- `test_driver_runs_the_fetch_chain_end_to_end` 扩到 6 个全链场景：
  两个 artifact 路由、21 条记录、失败形状的计数/语义/首次失败断言。
- `tests/test_ci_replay_wiring.py` 新增两条接线用例：
  `test_backend_uploads_the_failure_shape_fixture_for_full_chain` 与
  `test_writeback_job_does_not_consume_the_replay_fixture`。
- `tests/test_ci_history_writeback.py` 的两个 backend 上传筛选从「JSON 里
  含 e2e-metrics」收紧为「`with.name == "e2e-metrics"`」——否则新夹具会被
  误当成生产 artifact。

## 5. 验证

- 定向：**11 passed**（`test_ci_replay_wiring.py` + `test_replay_ci_scenarios.py`
  的失败形状/接线/表用例，32.54s）。
- 本机全量：**2698 passed / 28 skipped / 0 failed**（2726 条，398.90s）。
  - 本机 `.venv` 指向的 `C:\Program Files\Python314\python.exe` 已不存在，
    本次用官方 Python 3.14.8 embeddable 解释器 + `.venv\Lib\site-packages`
    运行；Git 全局 `core.symlinks=false` 会让
    `test_symlink_cannot_escape_checked_out_package` 把符号链接检出成普通
    文件（环境型失败），全量运行时用
    `GIT_CONFIG_KEY_0=core.symlinks=true` 覆盖后通过。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 `_run_scenario` 忽略 `scenario.artifact`（始终用驱动级 artifact）→
    两条失败形状场景读到 10 场景全过 artifact，端到端用例红；
  - M2 `run()` 的全链元组漏掉两条新场景 → 21 变 19，端到端用例红；
  - M3 删掉 backend 的夹具上传步骤 → 接线用例红。
- 变异日志：`_r119_m1.log`、`_r119_m2.log`、`_r119_m3.log`；
  备份 `_r119_backup/`（未提交）。
- 还原后 sha256：
  `scripts/replay_ci_scenarios.py` `D19B409A8C462F76055268C9CA79640D6E550435B8776B7198DCB3B2DEAC08C6`、
  `ci.yml` `7FAD1A7A6738AFAD1410EE5BD5DFE35B9D73BE66050E39AF8622894B1587948D`
  与备份一致。

## 6. CI

- 五轮提交一起推送；合并 run **41645884511**：**10 个 job 全 `success`**
  （13:36:48→13:51:18 UTC，约 14m30s）。
- `replay-ci-fetch-chain` 两平台 **25/25**（最终 tip 的场景表）；
  `e2e-history-writeback` success，写回 **48→49**。
- 夹具上传在 backend 的 main push 条件内；PR 不产生全链 job。

## 7. 边界与遗留

- 生产 artifact 仍是真实全过形状；失败形状只在回放夹具里，不进历史。
- N>6 / attempts>7 仍未建场景；全链失败形状只覆盖「最终成功」的重试路径。
- 趋势表仍不判趋势好坏；失败列只展示。
- 按天滚动、失败沙箱「保留最近 N 个」按 R112 拍板不做；GC 默认 dry-run/7 天。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交与 CI

- 本轮改动文件：
  `.github/workflows/ci.yml`、`scripts/replay_ci_scenarios.py`、
  `tests/test_replay_ci_scenarios.py`、`tests/test_ci_replay_wiring.py`、
  `tests/test_ci_history_writeback.py`、
  `tests/fixtures/e2e_metrics_failure_shape/e2e-metrics.json`、
  `docs/HANDOVER_ROUND118.md`、`docs/HANDOVER_ROUND119.md`、
  `docs/PROJECT_INFO.md`、`docs/JUDGEMENT_LEDGER.md`。
- 本地提交 **`445e6a1`**（`feat(R119): 全链失败形状 × 拒绝/注入 + R118
  CI 回填`），随五轮一起推送至 `7d999cc`；`config/skills_config.json` 不纳入。
