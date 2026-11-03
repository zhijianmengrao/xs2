# DeterminFlow (xs2) 交接报告 — Round 121

> 单 profile。五轮连推第 3 轮：把 R113 的 **全失败** 形状搬进生产
> fetch-chain——3 个场景全部失败也照常入库，失败数据也是数据；再叠一次
> 拒绝重试，证明 `failed=3` 与逐场景 `first_failure` 不被重算或清零。
> 生产行为零改动（只加夹具、场景与 CI 上传），`src/`、`web/` 零改动。

## 1. 一句话结论

- 全链场景 8 → **10**：新增 `fetched-all-failed` 与
  `fetched-all-failed-rejected`，使用 CI 单独上传的
  `e2e-metrics-all-failed` 夹具（3 场景全失败，`total=3 passed=0 failed=3`）。
- 全链总场景 **23 → 25**（15 本地 + 10 全链）。
- 本机全量 **2702 passed / 28 skipped / 0 failed**（2730 条，392.52s），
  比 R120 净增 **+2**。
- 定向 **6 passed**（38.55s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. 夹具与场景

`tests/fixtures/e2e_metrics_all_failed/e2e-metrics.json`：

```json
{"schema": 1, "total": 3, "passed": 0, "failed": 3, "retried": 0,
 "scenarios": [
   {"name": "fail_0", "passed": false, "attempts": 1,
    "first_failure": "全部失败：节点 0 未完成"},
   {"name": "fail_1", "passed": false, "attempts": 1,
    "first_failure": "全部失败：节点 1 未完成"},
   {"name": "fail_2", "passed": false, "attempts": 1,
    "first_failure": "全部失败：节点 2 未完成"}]}
```

| 场景 | 拒绝 | 观测 |
|---|---|---|
| `fetched-all-failed` | 无 | exit 0、`written`、rounds +1、push 1；`metrics 内容 total=3 passed=0 failed=3 retried=0 attempts=3`；语义 `fail_0=fail/1 fail_1=fail/1 fail_2=fail/1`；逐场景首次失败原样出现 |
| `fetched-all-failed-rejected` | `--reject-pushes 1` | 同上 + push 2、输出「第 2 次尝试」；`failed=3` 与首次失败文本不变 |

夹具 artifact 单独命名，`e2e-history-writeback` 仍只读 `e2e-metrics`，
不会把全失败夹具写进历史、污染趋势。

## 3. 代码与测试

- `replay_ci_scenarios.py`：新增 `ALL_FAILED_SHAPE_ARTIFACT`、两条
  `Scenario`，全链元组追加。
- `tests/test_replay_ci_scenarios.py`：
  `test_fetch_all_failed_shape_scenarios_pin_failed_counts` 校验夹具与场景；
  端到端用例扩到 10 个全链场景、4 个 artifact 路由、25 条记录。
- `tests/test_ci_replay_wiring.py`：
  `test_backend_uploads_the_all_failed_shape_fixture_for_full_chain`；
  写回 job 不消费夹具的断言加入 `e2e-metrics-all-failed`。
- 本机全量结果见 §5。

## 4. 判据台账

- #15 标题扩到 R121；补全失败全链：`failed=3`、逐场景语义/首次失败、
  拒绝重试后不变。
- §6 复核表补两条用例；§10.8 补全失败全链段落。

## 5. 验证

- 定向：**6 passed**（38.55s）。
- 本机全量：**2702 passed / 28 skipped / 0 failed**（2730 条，392.52s）。
  环境说明同 R119/R120。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 `_run_scenario` 忽略 `scenario.artifact` → 全失败场景读到 10 场景
    全过 artifact，端到端用例红；
  - M2 `run()` 的全链元组漏掉两条全失败场景 → 25 变 23，端到端用例红；
  - M3 删掉 backend 的全失败夹具上传步骤 → 接线用例红。
- 变异日志：`_r121_m1.log`、`_r121_m2.log`、`_r121_m3.log`；
  备份 `_r121_backup/`（未提交）。
- 还原后 sha256：
  `scripts/replay_ci_scenarios.py` `5908D3468E0F40C6096220493B7A90A471308013A1B00CF83F2DAD988A0332BE`、
  `ci.yml` `C606783D09E7720E40CD0A1651585F95B12FA6495D3ED82AF9E77165AAD7413D`
  与备份一致。

## 6. CI

- 本轮尚未提交/推送（GitHub 认证待补）；预计 `replay-ci-fetch-chain`
  两平台从 **23/23** 变 **25/25**，写回继续递增。

## 7. 边界与遗留

- 全失败数据照常入库；「本轮 e2e 全红」不等于「写回失败」。
- 生产 artifact 仍是真实全过形状；夹具只供回放。
- `config/skills_config.json` 保持未提交。

## 8. 提交

- 改动：`scripts/replay_ci_scenarios.py`、`tests/test_replay_ci_scenarios.py`、
  `tests/test_ci_replay_wiring.py`、`.github/workflows/ci.yml`、
  `tests/fixtures/e2e_metrics_all_failed/e2e-metrics.json`、R121 文档。
- 尚未提交；`config/skills_config.json` 不纳入。
