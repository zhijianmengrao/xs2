# DeterminFlow (xs2) 交接报告 — Round 122（失败形状的下游趋势消费）

> 单 profile。五轮连推第 4 轮：把「失败形状入库」与「趋势表展示」接起来——
> 用 R119–R121 的同一组夹具走真实 replay 写回，再从沙箱 history 渲染趋势
> 表，断言 `场景/失败/重跑/重跑率/总尝试` 五列与 0 场景文案。只断言「写回
> 成功」或只断言「表里有失败列」都发现不了「入库的形状在展示层被读错」。
> 生产行为零改动（只加测试）。

## 1. 一句话结论

- 新增参数化用例 `test_trend_table_consumes_the_replayed_shapes` 三格：
  失败/重试形状、0 场景、全失败。
- 三格都先用夹具走真实 `replay.main()` 写回，再从沙箱 history 调
  `history.render_trend()`，按列断言：`(4,1,1,25.0%,5)`、
  `(0,0,0,n/a,0)`、`(3,3,0,0.0%,3)`；0 场景还断「最近一轮 0 个场景」。
- 本机全量 **2705 passed / 28 skipped / 0 failed**（2733 条，390.43s），
  比 R121 净增 **+3**。
- 定向 **3 passed**（3.00s）；变异 **M1–M3 全咬合**、sha256 还原一致。

## 2. 为什么是这一轮

R113 证明失败形状能入库；R115 证明趋势表有 `失败` 列；R119–R121 证明同一
形状能走全链。但三段各自为政：把 `render_trend` 的失败列读成 `retried`、
把 0 场景的 `n/a` 改成 `0.0%`，前面的用例都不会红。R122 用**同一组夹具 +
真实写回后的 history** 渲染趋势表，把「入库」与「展示」钉在同一条链上。

## 3. 测试

`tests/test_replay_ci_writeback.py::test_trend_table_consumes_the_replayed_shapes`
（`pytest.mark.parametrize` 三格）：

| 夹具 | 期望五列（场景/失败/重跑/重跑率/总尝试） | 额外断言 |
|---|---|---|
| `e2e_metrics_failure_shape` | `4 / 1 / 1 / 25.0% / 5` | 表头含 `失败` |
| `e2e_metrics_empty` | `0 / 0 / 0 / n/a / 0` | 输出含「最近一轮 0 个场景」 |
| `e2e_metrics_all_failed` | `3 / 3 / 0 / 0.0% / 3` | 表头含 `失败` |

三格都先 `replay.main([... --metrics <fixture> --run-id shape --keep])`，
从 `--keep` 收尾行取沙箱，读 `work/tests/fixtures/e2e_retry_history/history.json`，
断言末条 `run_id=shape`，再渲染趋势表并按 `|` 分列。清理沙箱在 `finally`。

## 4. 判据台账

- #15 补「下游消费」：R115 只证明表有失败列，R122 证明**真实 replay 写回的
  形状**在表里取到正确值；0 场景的 n/a 与「没有可读轮次」分开。
- §6 复核表补该用例；§10.6 补「下游消费 × 真实写回」段落。

## 5. 验证

- 定向：**3 passed**（3.00s）。
- 本机全量：**2705 passed / 28 skipped / 0 failed**（2733 条，390.43s）。
  环境说明同 R119–R121。
- 变异 **M1–M3 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 `render_trend` 的失败列读成 `retried` → 全失败行 `(3,3,...)` 变
    `(3,0,...)`，参数化用例红；
  - M2 `_rate` 的 0 场景返回 `0.0%` 而非 `n/a` → 0 场景行红；
  - M3 0 场景文案改成「历史里没有可读的轮次」→ 0 场景 note 断言红。
- 变异日志：`_r122_m1.log`、`_r122_m2.log`、`_r122_m3.log`；
  备份 `_r122_backup/`（未提交）。
- 还原后 sha256：
  `scripts/e2e_retry_history.py` `BB45F2E7B855D119895622CF598C867C778581DBCD2205C6BABB45BECE327F35`
  与备份一致。

## 6. CI

- 随五轮一起推送；合并 run **41645884511**：10 个 job 全 `success`，
  测试在 backend job 的 pytest 全量里执行，`replay-ci-fetch-chain`
  两平台 **25/25**，写回 **48→49**。

## 7. 边界与遗留

- 趋势表仍只展示、不判好坏（R78/R115 政策不变）。
- 0 场景的 `n/a` 只表示重跑率不可算，不代表通过。
- `config/skills_config.json` 保持未提交。

## 8. 提交

- 改动：`tests/test_replay_ci_writeback.py`、R122 文档、PROJECT_INFO、
  JUDGEMENT_LEDGER。生产代码零改动。
- 本地提交 **`f8a83ec`**，随五轮推送至 `7d999cc`；`config/skills_config.json` 不纳入。
