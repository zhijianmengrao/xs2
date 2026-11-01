# DeterminFlow (xs2) 交接报告 — Round 89（写回链路可执行化 + 历史窗口 20→40）

> 本轮定位：用户拍定 R88 §6 的两项收口——①写回粒度（窗口 20→40）、
> ②把只存在于 YAML 里的提交/推送重试搬进可执行代码并本地验证。
> 已拍定的另两项：**分支保护维持不加**、**保留 R78 那轮本机历史**（现 3 轮）。
> 形态：`ci.yml` 减 45 行（两个内联步骤 → 一次脚本调用）；新增
> `scripts/ci_writeback_history.py`；新增 8 条行为用例；`MAX_ROUNDS` 20→40；
> `record` 修一处「重跑必产生提交」的缺陷。

## 1. 一句话结论

1. **写回链路第一次真正被执行过**：8 条用例用真实 git 临时仓让 push **真的被拒**，
   覆盖快进、被拒→rebase→第 2 次成功、永久拒绝→3 次后 `::error::`、重跑不提交、
   无变化、无 metrics、冲突响亮失败、CLI 同语义。
2. **YAML 只剩委托**：`test_writeback_delegates_retry_to_the_script` 反向钉住
   YAML 里不得再出现 `git push` / `pull --rebase` / `for attempt`（R80：同一个
   事实写两处就会分裂）。
3. **修掉一个 R88 没发现的真缺陷**：`record` 每次重跑都写新的 `exported_at`，
   所以「内容不变就不提交」在重跑时**不成立**——会多一次非空提交。现在同一
   `run_id` 且观测一致时保留首次时间戳，文件逐字节不变。
4. **窗口 20→40**：一轮 = 一次 main push（R88），doc-only 提交也占一格；R88
   自身吃掉 3 轮，20 轮只剩 6~7 个工作轮。窗口只是保留期，趋势仍不判好坏。
5. 总用例 **2569 → 2579（+10）**；本机全量 **2551 passed / 28 skipped / 0 failed**。

## 2. 为什么把重试搬出 YAML

R88 的写回 job 本身是对的（写权限与执行面分离），但「提交 → push → 被拒 →
`pull --rebase` → 重试」只写在 YAML 里：

| R88 的测试能证明 | 证明不了 |
|---|---|
| YAML 文本里有 `for attempt in 1 2 3` | 循环真的会执行 3 次 |
| 文本里有 `git pull --rebase origin main` | push 被拒后真的会走 rebase |
| 文本里有 `[skip ci]` | 提交真的带上了它 |

这正是 R68 的教训：**重试路径必须在重试真的发生时被走过一次**。搬进
`scripts/ci_writeback_history.py` 后，测试可以建三个真实仓库（origin / work /
other），让 other 先推进 main，work 的 push 就**必然**被拒——拒绝是真实的，
不是模拟的退出码。

## 3. 行为用例（8 条，新增文件）

| 用例 | 让什么真的发生 |
|---|---|
| `test_push_succeeds_on_the_first_attempt` | 快进：第 1 次成功；提交信息以 `[skip ci]` 结尾 |
| `test_rejected_push_rebases_and_succeeds_on_the_second_attempt` | other 先推一个提交 → work 的 push 真被拒 → rebase → 第 2 次成功；远端无 merge 提交 |
| `test_permanent_rejection_stops_after_the_attempt_cap` | pre-receive 钩子永久拒绝：恰好 `DEFAULT_ATTEMPTS`（3）次后 `::error::` + 退出 1 |
| `test_same_run_rerun_does_not_create_a_second_commit` | 同一 run 重跑（第二次时间戳被推后）：历史逐字节不变、无第二次提交 |
| `test_commit_does_not_sweep_unrelated_changes` | 工作树里有**已暂存**的杂项，写回提交也只含 `history.json` |
| `test_missing_metrics_is_not_a_failure` | 没有 metrics：退出 0、历史不动 |
| `test_rebase_conflict_fails_loudly_instead_of_losing_the_round` | 远端也改了 `history.json`：rebase 冲突 → `::error::` + 退出 1 |
| `test_cli_has_the_same_semantics_as_the_function` | CLI 与函数同一语义（`--commit-message` 原样进提交） |

接线测试同步改一条：`test_writeback_retries_and_skips_self_trigger` →
`test_writeback_delegates_retry_to_the_script`（YAML 只许委托，不许内联 git 循环）。

## 4. 顺带修掉的缺陷：`record` 的 `exported_at`

R88 §3 写着「内容不变时 `git diff --quiet` 直接退出，不产生空提交」。实测：

- `record` 先用 `_iso_now()` 生成 `exported_at`，再按 `run_id` 覆盖；
- 同一 run 重跑时时间戳几乎必然不同 → 文件内容变了 → **会提交**；
- 轮数确实没变（覆盖而不是追加），但这句「不提交」是假的。

修法：`_same_observation()` 比较除 `run_id`/`exported_at` 外的全部字段
（`total/passed/failed/retried/attempts/scenarios`），完全一致时保留首次条目。
观测真的变了（例如重跑后 `retried` 不同）时照常更新，由反向用例
`test_record_updates_the_export_time_when_the_observation_changes` 钉住。

**变异 M7 的第一次实测很有价值**：端到端「重跑不提交」用例在同一秒内会**假绿**
（同秒的 `exported_at` 本来就相同），只有函数级 monkeypatch 用例咬住。把第二次
重跑的时间戳显式推后，两处才都咬合。

## 5. 窗口 20 → 40

- R88 把「一轮 = 一次显式导出」改成「一轮 = 一次 main push」；doc-only 提交也
  占一格。R88 自己吃掉 3 轮（2 次 CI + R78 本机导出）。
- 20 轮 ≈ 6~7 个工作轮；40 轮 ≈ 13 轮，回到 R88 前的日历跨度。
- 窗口是**保留期**，不是判决门槛：`check` 只校验历史有效、不判趋势（R78）。
- 守卫同时钉值与行为：`MAX_ROUNDS == 40` + 写第 41 轮时 `r0` 恰好掉出
  （R69：「数等于常量」不等于「数是判决的边界」）。

## 6. 变异验证（8/8 全咬合）

还原源是**当前文件快照**（`cp` 备份），不用 `git checkout`（R55 教训）。

| 变异 | 结果 |
|---|---|
| M1 `pull` 不带 `--rebase` | 1 红（rebase 用例） |
| M2 重试上限 3 → 1 | 2 红（重试用例 + 永久拒绝计数） |
| M3 没有 metrics 当失败 | 1 红 |
| M4 无变化仍然提交 | 1 红 |
| M5 默认提交信息丢 `[skip ci]` | 1 红 |
| M6 `commit` 不带 pathspec | 1 红 |
| M7 重跑总是改写 `exported_at` | **2 红**（函数级 + 端到端） |
| M8 窗口 40 → 20 | 1 红 |

## 7. 未做与未验证

1. **未加分支保护**：用户拍定维持不加。若将来加，bot 直推会三次失败后
   `::error::`——仍然响亮，不静默丢历史。
2. **未在本地复现 `actions/download-artifact` 与真实 token 的 push 权限**：
   覆盖的是脚本的输入契约与 git 行为，不是 Actions 的 artifact 传输。
3. **冲突处置未重算**：远端也改 `history.json` 时直接响亮失败（与 R88 相同）；
   `concurrency` 串行化下只有人工并发编辑才会触发。
4. **未改趋势判据**：仍只判历史有效（R78）。
5. **前端零改动**，未跑 `npm run build`。

## 8. 提交、推送与 CI 核对

- 提交 `390b8c3`（feat：写回脚本 + 8 条行为用例 + 窗口 40 + `record` 修复），
  推送 `27e7027..390b8c3`（`-c http.proxy=` 直连成功；`git fetch` 第一次仍走
  已失效的 socks5 代理、超时后改直连通过）。
- CI run **41299594952**（push，10:55:38Z → 11:00:33Z，约 4m55s）**六个 job**
  全部 `success`：

| 项 | 实证 |
|---|---|
| backend | `2514 passed, 65 skipped, 1 warning in 114.10s` = **2579** |
| windows-backend | `2550 passed, 29 skipped, 1 warning in 226.59s` = **2579** |
| 与 R88 相比 | ubuntu 2495→2504→**2514**/65、windows 2531→2540→**2550**/29（本轮各 +10，与新增用例数一致） |
| 写回 job | `e2e-history-writeback` success（10:58:27 → 10:58:33，**6 秒**）：**新脚本在生产路径第一次执行** |
| 写回结果 | main 头变成 bot 提交 `6bf2f44`，父提交 `390b8c3`；`history.json` 3 轮 → **4 轮**（新增 `ci-41299594952`，total=10 / passed=10 / retried=0） |
| 生产路径走到哪条分支 | 日志：`已记录 run_id=ci-41299594952：0/10 个场景重跑（总尝试 10 次），历史 4/40 轮`、`已写回 main（第 1 次尝试）`——**重试分支没有被走到**，这正是本地 harness 存在的理由 |
| 无自触发 | `runs?head_sha=6bf2f44fc846143ea781c0137f0be010d92a7532` → **total_count=0**（用完整 40 位 SHA 查；用错 SHA 时同样返回 0，见下方取证教训） |
| e2e / 前端 / 容器 | e2e 10/10；frontend / container-config / container-build 均 success |

**取证教训**：第一次查「有无自触发」时填的 `head_sha` 不是 bot 提交的真实 SHA，
接口照样返回 `total_count=0`——**0 只有在被查询的 SHA 确实是 bot 提交时才构成
证据**。用 `git rev-parse 6bf2f44` 取全 40 位后重查，结论不变（0）。

**本文档提交本身还会产生一轮**：doc-only push 同样触发 CI 与写回（§5 的现行
语义，已由 R88 的 docs 提交实测过一次），预计 history 4 → 5 轮。这不是缺陷，
是「一轮 = 一次 main push」的直接后果；窗口已按此调到 40。
