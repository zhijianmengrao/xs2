# DeterminFlow (xs2) 交接报告 — Round 97（写回机读结果工件）

> 第 3 轮。形态：`ci_writeback_history.py --result-json`；写回 job 上传
> `writeback-result` artifact。关闭 R91 §未做 的「类别只进 summary，未进
> machine-readable 工件」。

## 1. 一句话结论

summary 之外新增一份机读 JSON，**每一个出口都写**（成功、无变化、缺 metrics、
record 坏、push 被拒、git 错误、dry-run）：

```json
{
  "schema": 1,
  "run_id": "ci-…",
  "source": "ci",
  "reason": "written",
  "detail": "第 1 次尝试，历史 11/40 轮",
  "exit_code": 0,
  "rounds": 11,
  "push_attempts": 1,
  "dry_run": false
}
```

- `reason` / `detail` 与 step summary 共用同一组常量与同一个字符串；
- `rounds` 读 **`origin/<branch>` 的已入库历史**，不是本地工作树文件；
- `push_attempts` 只数**真正发起的 push**（record 失败/无变化是 0）；
- 写失败只告警，不改变退出码（与 summary 同）。

## 2. 实现要点

1. `_writeback_steps` 多返回 `attempts_made`；计数点放在 `push` 之前、record /
   no-change 之后——否则 record 坏掉也会被记成「push 过一次」。
2. `_remote_rounds(repo, branch, history_path)`：`git show origin/<branch>:<rel>`
   → `validate_history` → `len`；git 不可用/路径不在仓库内 → `null`。
3. `_emit_result(result_path, payload)`：`tempfile` 旁写 + `os.replace`；任何
   `OSError` 只打印「结果工件写入失败」，不改变判决。
4. CI：写回步骤加 `--result-json "$RUNNER_TEMP/writeback-result.json"`；新增
   `Upload writeback result`（`if: always()`、`if-no-files-found: warn`、
   `retention-days: 1`）。

## 3. 用例（+12）

| 文件 | 新增 | 断言 |
|---|---|---|
| `tests/test_ci_writeback_history.py` | +10（含 1 条 CLI） | written / 被拒一次后 rebase（attempts=2）/ 缺 metrics / record 坏 / 持续被拒（attempts=3）/ no-change / dry-run / git-error / 写失败不改判决 / summary 与 result 的 reason+detail 逐字一致 / CLI `--result-json` 接线 |
| `tests/test_ci_history_writeback.py` | +2 | 写回步骤带 `--result-json`；上传步骤 `if: always()`、名称/路径/缺失行为 |

**本机全量**：**2610 passed / 28 skipped / 0 failed（2638 条）**，R96 的 2626 + 12。

## 4. 变异验证（6/6 全咬合）

| 变异 | 结果 |
|---|---|
| M44 失败路径不写结果工件 | 2 红 |
| M45 `exit_code` 恒为 0 | 2 红 |
| M46 `push_attempts` 恒为 1 | 2 红 |
| M47 工件写失败改判决 | 1 红 |
| M48 上传不是 `always()` | 1 红 |
| M49 `rounds` 读本地 HEAD 而非 origin | 1 红 |

## 5. 边界

- 结果工件只由写回 job 产出；`upload-artifact` 使用运行时 token，是否需要
  `actions: write` 由 CI 实证（本轮第一次上传）。
- `rounds` 是**远端已入库**轮数；dry-run 时它是磁盘当前值，不是「将写入」值
  （`detail` 里才有 +k）。
- `git-error` 的 `push_attempts` 固定 0：异常发生时无法可靠知道已发起的次数；
  不猜。

## 6. 提交与 CI

（待推送后回填）

## 7. 本轮教训

1. **「本地文件有这一轮」不等于「历史入库」**：push 被拒时 record 已经把
   `history.json` 写进工作树，用它算 rounds 会把「未入库」报成 1；必须读
   `origin/<branch>`。这是 R95「沙箱里看到的不是远端」的同一类错误。
2. **计数器要放在它计数的动作前面**：`attempts_made = attempt` 原在循环顶部，
   record 失败也会记成一次 push；移到 `push` 紧前面后，`record-invalid` 与
   `no-change` 都归 0。
3. **summary 与机读工件必须共用同一组字符串**：两处各拼一次就会分裂
   （R80）；用例直接断言 `payload["reason"]` 与 `payload["detail"]` 都出现在
   summary 文本里。
