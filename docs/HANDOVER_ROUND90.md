# DeterminFlow (xs2) 交接报告 — Round 90（写回冲突可恢复）

> 本轮是用户「按推荐连续 5 轮」的第 1 轮（R90–R94 同一主线：CI 写回子系统
> 从「能跑」到「可恢复、可观测、可预检、可追溯、可回放」）。
> 形态：只改 `scripts/ci_writeback_history.py` 的重试循环 + 2 条用例。

## 1. 一句话结论

R89 的处置是「rebase 冲突 → `::error::` + 退出 1」：轮次没丢在磁盘上，但**这一轮
写回失败了**，要靠人重跑。R90 改成**重算**——`record` 是幂等的，在 rebase 后的
历史上再跑一遍，人工轮与 CI 轮都能保住。

## 2. 结构变更

原来的结构是「record + commit 一次，然后循环 push」：

```
record → commit → for attempt: push / pull --rebase（失败即 raise）
```

冲突时无法重算，因为 record 已经跑过了。新结构把 `record` 放进循环，用
`prepared` 标志区分「需要重新准备」与「只需重推」：

```
for attempt in 1..attempts:
    if not prepared: record → add → commit
    push == 0 → 成功
    pull --rebase == 0 → continue（提交已被 rebase，只需重推）
    冲突 → rebase --abort → fetch → reset --hard origin/<branch> → prepared=False
```

**两个必须保留的细节**（各自有变异咬住，见 §4）：

1. rebase 成功后**不能**再 record：此时提交已在分支上，再 record 会得到
   「没有变化」并提前返回 0，把这一轮丢掉（M11）；
2. 冲突后**必须** `prepared = False`：否则下一轮会推一个空提交（M12）。

## 3. 用例

| 用例 | 断言 |
|---|---|
| `test_rebase_conflict_recomputes_instead_of_losing_the_round` | 真实仓冲突 → 退出 0、`manual-1` 与 `ci-1` 都在、无 merge 提交、写回提交在顶端、日志出现「重算」「第 2 次尝试」 |
| `test_conflict_stops_after_the_attempt_cap` | `attempts=1` 时冲突消耗唯一一次尝试 → `::error::` + 退出 1、只尝试 1 次 |

原 `test_rebase_conflict_fails_loudly...`（R89）被替换。

## 4. 变异验证（4/4 全咬合）

| 变异 | 结果 |
|---|---|
| M9 冲突仍直接失败（R89 旧行为） | 1 红 |
| M10 冲突后不回退到最新分支 | 1 红 |
| M11 rebase 成功后仍重新 record（提前返回 0，丢一轮） | 1 红 |
| M12 冲突后忘记标记重算（推空提交） | 1 红 |

## 5. 未做与边界

1. **重算会丢弃本地写回提交**：安全前提是这个 checkout 里只有我们刚做的那一个
   提交（CI job 成立）。回放工具（R94）在沙箱里跑，同样成立。
2. **冲突消耗一次尝试**：`attempts=3` 时最多 3 轮完整「准备+推送」，不是无限重算。
3. **非冲突类 git 错误**（fetch 失败等）仍然响亮失败，不重试。

## 6. 提交与 CI

- 提交 `4c7e481`，推送后 main 出现 bot 提交 `3908c80`（run 41301567697 的写回）。
- CI run **41301567697** 六 job 全 `success`：
  - backend **2515 passed / 65 skipped**（109.01s）= **2580**；
  - windows-backend **2551 / 29**（235.95s）= **2580**；
  - 写回 job：`已记录 run_id=ci-41301567697 … 历史 6/40 轮`、`已写回 main（第 1 次尝试）`。
- 本机全量 **2552 passed / 28 skipped / 0 failed**（R89 2551/28，+1）。
