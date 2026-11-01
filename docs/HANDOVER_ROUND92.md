# DeterminFlow (xs2) 交接报告 — Round 92（PR 预检 `record --check-only`）

> 第 3 轮。形态：`e2e_retry_history.record` 增加 `--check-only` 与写入前自校验；
> `ci.yml` 的 backend 增加一个**只读、只在 PR 上跑**的预检步骤。

## 1. 一句话结论

坏 metrics / 与历史不兼容的计数，原先要等**合入 main 之后**的写回 job 才炸。
R92 把它左移到 PR：

- `record --check-only`：读 metrics、读历史、算出条目、校验结果，**不写文件**；
- 退出码与正常 `record` 完全一致（3 = 无样本、4 = 数据坏、2 = 用法）；
- backend 的预检步骤只在 `pull_request` 上跑，且只调 `--check-only`——
  写权限仍然只在 `e2e-history-writeback`。

## 2. 实现要点

1. **写入前自校验**（不只 check-only 有）：算出来的 `trimmed` 历史必须能通过
   `validate_history`，否则返回 4 且**文件逐字节不动**。这条覆盖 record 自己的
   覆盖/去重/裁剪算术。
2. `--check-only` 打印「将写入 run_id…历史 N/40 轮（未写入）」后返回 0。
3. CI 预检步骤先判 metrics 是否存在：e2e 环境未启动时跳过（那一步已经红过），
   与写回 job 的处置一致。

## 3. 用例（5 条）

| 用例 | 断言 |
|---|---|
| `test_record_check_only_does_not_write` | 不创建历史文件；打印的轮次与实际写入后一致 |
| `test_record_check_only_uses_the_same_exit_codes` | 坏 metrics 4 / 缺 metrics 3，不发明新码 |
| `test_record_validates_the_result_before_writing` | 注入「结果无效」→ 返回 4 且历史逐字节不变 |
| `test_cli_wires_check_only` | CLI 的 `--check-only` 真的不落盘 |
| `test_backend_prechecks_metrics_on_pull_requests`（接线） | 唯一一处 `--check-only`、条件是 `pull_request`、无 `git commit`/`push`/`upload-artifact` |

既有用例 `test_ci_checks_the_committed_history_file` 的定位条件从
「`e2e_retry_history.py`」收紧成「`e2e_retry_history.py check`」——否则新预检
会被算成第二处趋势校验。

## 4. 变异验证（5/5 全咬合）

| 变异 | 结果 |
|---|---|
| M18 check-only 照样写盘 | 1 红 |
| M19 写入前不做自校验 | 1 红 |
| M20 check-only 换一个退出码 | 1 红（成功码用例 + 失败码用例都跑） |
| M21 接线丢掉 `--check-only`（预检变成真写） | 1 红 |
| M22 预检改到 push 上也跑 | 1 红 |

**教训（R70 复现）**：M20 第一次只配了「失败码」用例，结果 MISSED——成功码那条
用例本来就能咬住它。**变异必须跑全部相关用例**，不能只跑看起来最相关的那条。

## 5. 边界

- 预检只证明「metrics 能被当前历史接受」，不证明「这一轮写回会成功」（网络、
  权限、并发都不在预检范围）。
- PR 上的 run_id 用 `pr-<number>`，只用于 check-only；不写入任何文件。

## 6. 提交与 CI

- 与 R91 同一个提交 `b71f6b9`；CI run **41302777624**（ubuntu **2527/65**、
  windows **2563/29**，均 **2592**；六 job 全 success）。
- 本机全量 **2564 passed / 28 skipped / 0 failed**。
