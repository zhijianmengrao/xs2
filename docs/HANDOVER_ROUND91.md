# DeterminFlow (xs2) 交接报告 — Round 91（写回失败分类 + step summary）

> 第 2 轮。形态：`ci_writeback_history.py` 把「退出码」升级成「退出码 + 固定
> 类别」，并把每轮结果追加进 `GITHUB_STEP_SUMMARY`。

## 1. 一句话结论

R90 之前，写回 job 的失败只有两种可读信号：退出码（0/1/2/4）与中文文案。同一个
退出码可能来自不同原因（R64 教训），日志里要靠人读那句话才知道该修什么。R91
给每轮结果一个**固定的机器类别**，并写进 step summary：

| 类别 | 含义 | 处置 |
|---|---|---|
| `written` | 已写回（第 N 次尝试） | 无 |
| `no-change` | 历史已含这一轮 | 无（幂等） |
| `metrics-missing` | e2e 环境未启动 | 查装配栈，不是写回的问题 |
| `record-invalid` | metrics/历史形状坏 | 修数据（退出码 2/4） |
| `push-rejected` | 连续 N 次 push 被拒 | 查并发/分支保护 |
| `rebase-conflict` | 冲突且最后一次尝试用尽 | 查并发编辑 |
| `git-error` | add/commit/fetch 等失败 | 查仓库/权限 |
| `usage` | 参数错误 | 调用方 |

## 2. 实现要点

- `_writeback_steps()` 返回 `(退出码, 类别, 说明)`，`writeback()` 负责统一
  **追加** summary 并返回退出码。
- **summary 写不进去只告警**，不改判决：历史已经进 git 了，摘要只是可读性。
- 类别是常量（`REASON_*`），测试同时钉字面值与互异性。

## 3. 用例（7 条）

| 用例 | 断言 |
|---|---|
| `test_summary_records_a_successful_writeback` | 追加而非覆盖（保留既有行）、含 `written` 与 `1/40` |
| `test_summary_records_the_rejection_category` | 永久拒绝 → `push-rejected`、N 次 |
| `test_summary_records_missing_metrics_and_record_invalid_separately` | 缺 metrics（0）与坏 metrics（4）类别不同，且都不冒充 `push-rejected` |
| `test_summary_records_no_change_on_a_rerun` | 重跑 → `no-change` |
| `test_git_errors_are_classified_as_git_errors` | 非 git 仓库 → `git-error`（不是 `push-rejected`） |
| `test_summary_write_failure_does_not_change_the_verdict` | 摘要写失败仍退出 0 |
| `test_result_categories_are_distinct_literals` | 类别字面值固定且互异 |

接线：`test_writeback_delegates_retry_to_the_script` 增加
`--summary "$GITHUB_STEP_SUMMARY"` 断言。

## 4. 变异验证（5/5 全咬合）

| 变异 | 结果 |
|---|---|
| M13 只在成功时写 summary | 2 红 |
| M14 所有结果都标成 push-rejected | 1 红 |
| M15 summary 覆盖而不是追加 | 1 红 |
| M16 summary 写失败直接抛出（翻掉判决） | 1 红 |
| M17 record 坏掉却当成成功 | 1 红 |

## 5. 边界

- 类别集合是契约：新增类别必须同时更新字面值用例。
- summary 在 job 失败时也会写（只要脚本跑到那里）；checkout 之前失败不覆盖。

## 6. 提交与 CI

- 与 R92 同一个提交 `b71f6b9`（`feat(R91+R92): …`），推送后 main 出现 bot 提交
  `f55c922`（run 41302777624 的写回）。
- CI run **41302777624** 六 job 全 `success`：
  - backend **2527 / 65**（113.23s）= **2592**；
  - windows-backend **2563 / 29**（255.61s）= **2592**；
  - 写回 job：`已记录 run_id=ci-41302777624 … 历史 7/40 轮`（本轮脚本带
    `--summary`，但该 run 的 checkout 是 b71f6b9——summary 已接线）。
- 本机全量（R91+R92 合并）**2564 passed / 28 skipped / 0 failed**。
