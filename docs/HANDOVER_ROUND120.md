# DeterminFlow (xs2) 交接报告 — Round 120

> 单 profile。五轮连推第 2 轮：把 R113 的 **0 场景** 形状搬进生产
> fetch-chain——0 场景是合法数据，写回照常入库，语义行必须显式打印
> `（无场景）`；再叠一次拒绝重试，证明 0 场景不会被重试循环吃掉。
> 生产行为零改动（只加夹具、场景与 CI 上传），`src/`、`web/` 零改动。

## 1. 一句话结论

- 全链场景 6 → **8**：新增 `fetched-empty` 与 `fetched-empty-rejected`，
  使用 CI 单独上传的 `e2e-metrics-empty` 夹具（`total=0`、`scenarios=[]`）。
- 全链总场景 **21 → 23**（15 本地 + 8 全链）。
- 本机全量 **2700 passed / 28 skipped / 0 failed**（2728 条，430.09s），
  比 R119 净增 **+2**。
- 定向 **5 passed**（34.75s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. 夹具与场景

`tests/fixtures/e2e_metrics_empty/e2e-metrics.json`：

```json
{"schema": 1, "total": 0, "passed": 0, "failed": 0, "retried": 0,
 "scenarios": []}
```

| 场景 | 拒绝 | 观测 |
|---|---|---|
| `fetched-empty` | 无 | exit 0、`written`、rounds +1、push 1；`metrics 内容 total=0 passed=0 failed=0 retried=0 attempts=0`；`metrics 语义 （无场景）`；不得出现 `metrics 首次失败` |
| `fetched-empty-rejected` | `--reject-pushes 1` | 同上 + push 2、输出「第 2 次尝试」；0 场景内容不变 |

夹具 artifact 单独命名，`e2e-history-writeback` 仍只读 `e2e-metrics`，
不会把 0 场景夹具写进历史、污染趋势。

## 3. 代码与测试

- `replay_ci_scenarios.py`：新增 `EMPTY_SHAPE_ARTIFACT`、两条 `Scenario`，
  全链元组追加；`must_not_contain=("metrics 首次失败",)` 把「0 场景没有逐
  场景失败文本」钉住。
- `tests/test_replay_ci_scenarios.py`：
  `test_fetch_empty_shape_scenarios_pin_zero_counts` 校验夹具与场景；
  端到端用例扩到 8 个全链场景、3 个 artifact 路由、23 条记录。
- `tests/test_ci_replay_wiring.py`：
  `test_backend_uploads_the_empty_shape_fixture_for_full_chain`；
  写回 job 不消费夹具的断言加入 `e2e-metrics-empty`。
- 本机全量结果见 §5。

## 4. 判据台账

- #15 标题扩到 R119/R120；补 0 场景全链：计数全 0、语义 `（无场景）`、
  拒绝重试后内容不变。
- §6 复核表补两条用例；§10.8 补 0 场景全链段落。

## 5. 验证

- 定向：**5 passed**（34.75s）。
- 本机全量：**2700 passed / 28 skipped / 0 failed**（2728 条，430.09s）。
  环境说明同 R119：venv 的 3.14 解释器缺失，用官方 3.14.8 embeddable；
  `GIT_CONFIG_KEY_0=core.symlinks=true` 让 symlink 用例走真实路径。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 `_run_scenario` 忽略 `scenario.artifact` → `fetched-empty` 读到
    10 场景全过 artifact，端到端用例红；
  - M2 `run()` 的全链元组漏掉两条 0 场景 → 23 变 21，端到端用例红；
  - M3 删掉 backend 的 0 场景夹具上传步骤 → 接线用例红。
- 变异日志：`_r120_m1.log`、`_r120_m2.log`、`_r120_m3.log`；
  备份 `_r120_backup/`（未提交）。
- 还原后 sha256：
  `scripts/replay_ci_scenarios.py` `7346728477A7233047DBD70495837127CEE4A8A0E2EC677F2EB05BE877AA7124`、
  `ci.yml` `703E3405B60EDF26C288C6C31C25DEF7F741DA772BF6A65B6E9058BBF4543C87`
  与备份一致。

## 6. CI

- 本轮已本地提交 **`78afe48`**，尚未推送（GitHub 认证待补）；预计
  `replay-ci-fetch-chain` 两平台从 **21/21** 变 **23/23**，写回继续递增。

## 7. 边界与遗留

- 0 场景是合法数据，不是「历史为空」；趋势表对 0 场景显示 n/a（R115）。
- 生产 artifact 仍是真实全过形状；夹具只供回放。
- `config/skills_config.json` 保持未提交。

## 8. 提交

- 改动：`scripts/replay_ci_scenarios.py`、`tests/test_replay_ci_scenarios.py`、
  `tests/test_ci_replay_wiring.py`、`.github/workflows/ci.yml`、
  `tests/fixtures/e2e_metrics_empty/e2e-metrics.json`、R120 文档。
- 本地提交 **`78afe48`**；尚未推送；`config/skills_config.json` 不纳入。
