# DeterminFlow (xs2) 交接报告 — Round 127

> 单 profile。五轮连推第 3 轮：**写回幂等在回放链路成立**。no-change 与
> metrics-missing 此前只有 writeback() 层用例（`test_ci_writeback_history.py`）；
> replay CLI 从源仓克隆全新沙箱，去重路径完全没被端到端走过。生产行为
> 零改动（只加测试）。

## 1. 一句话结论

- 新增 `test_replay_same_run_id_rerun_is_a_no_change`：源仓历史预置
  `replay-dup`（由 `history.record` 亲手写出，格式/观测与回放一致），
  同 run-id 同 metrics 重放 → 退 0、`reason=no-change`、`push_attempts=0`、
  `rounds=1`、输出含「history 没有变化」。
- 新增 `test_replay_missing_metrics_file_reports_metrics_missing`：
  `--metrics` 指向不存在的文件 → 退 0、`reason=metrics-missing`、
  `push_attempts=0`、`rounds=0`、`last_run_id=None`、输出含
  「e2e 环境未启动」。
- **+2 → 总用例 2737**。

## 2. 为什么是这一轮

驱动 R103 依赖「record 对同键是覆盖，不会把一次回放记成两轮」；CI 写回
依赖「同 run 重跑不提交」。两句话此前都只在 writeback() 层验证，回放链路
（沙箱克隆 → work → record → commit/push）单独退化成重复入库或误报失败
时没有用例会红。R127 把两条路径在真实 CLI 上钉住。

## 3. 实现细节

- 种子条目必须由 `history.record` 写出：`record` 的序列化是
  `json.dumps(..., ensure_ascii=False, indent=2)`，手写 `json.dumps`
  默认格式会因字节差异触发 `git diff --cached` 变化，no-change 永远到不了
  （首跑实测踩中，改为 `history.record` 造种子后通过）。
- `_same_observation` 忽略 `exported_at`：重放的 record 保留首次时间戳，
  历史逐字节不变 → 「history 没有变化（同一 run 重跑），不提交」。

## 4. 判据台账

- §6 复核表补两条用例；§10.9 汇总。

## 5. 验证

- 定向：2 passed（0.76s）。
- 本机全量（R128 最终代码统一跑）：**2710 passed / 28 skipped / 0 failed**
  （2738 条）。
- 变异 **M1–M2 2/2**：
  - M1 `_writeback_steps` 的 no-change 路径改退 `EXIT_FAILED` → 重放
    用例红（退 1 而非 0）；
  - M2 metrics-missing 路径改退 `EXIT_FAILED` → 缺 metrics 用例红。
- 变异日志：`_r127_m1.log`、`_r127_m2.log`。

## 6. CI

随五轮合并推送（run 待回填）。

## 7. 边界与遗留

- CI 的 e2e-history-writeback job 自身的去重语义维持原状（R89/R97）。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_replay_ci_writeback.py`、R127 文档、PROJECT_INFO、
  JUDGEMENT_LEDGER。生产代码零改动。
