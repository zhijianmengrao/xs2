# DeterminFlow (xs2) 交接报告 — Round 105（永久拒绝 × 冲突组合场景）

> 单 profile。把 R104 §8 的第一条边界做完：三次永久拒绝与冲突注入放进
> 同一次回放，断言「冲突后仍失败」的退出码 / reason / rounds /
> push_attempts / 末条身份；顺带发现并修掉冲突夹具在满窗 40 轮时造出
> 41 轮的问题。零 `src/`、`web/` 改动；`MAX_ROUNDS`、失败沙箱策略、
> 写权限归属都不动。

## 1. 一句话结论

- **场景表新增 `rejected-conflict`**（`--reject-pushes 3 --conflict`）：
  第一次 push 被冲突注入造成的**非快进**拒绝挡下，钩子只拒绝第 2、3 次，
  rebase 冲突后按最新分支重算，三次尝试全部失败。
- **实测期望值**：`exit=1`、`reason=push-rejected`、`rounds=+1`（只有
  注入的冲突轮）、末条 `replay-conflict`、`push_attempts=3`；
  `simulated rejection` 只出现 **2** 次（第一次不是钩子拒绝）。
- **失败场景的期望模型扩展**：`injected_rounds` + `expected_last_run_id`；
  纯永久拒绝仍是「远端不变、末条停在基线」，组合场景则是「只多出注入轮」。
- **冲突夹具遵守窗口**：`_create_conflicting_round` 按 `[-MAX_ROUNDS:]`
  裁剪，满窗 40 时不再把 origin 留在 41 轮。
- 用例 **+1 → 2689**；本机 **2661 passed / 28 skipped / 0 failed**
  （343.44s）。R104 为 2660/28（2688）。
- **变异 M93–M99 7/7 全咬合**；M97/M99 只有满窗 40 轮参数咬住（§4）。
- CI run **41405610755**：**10 个 job run 全 `success`**，写回历史
  **25 → 26**（`f733a46`）。

## 2. 实现要点

### 2.1 组合场景

`SCENARIOS` 追加：

```python
Scenario(
    "rejected-conflict", 0, 3, reject_pushes=3, conflict=True,
    expected_exit=EXIT_MISMATCH,
    expected_reason="push-rejected",
    expect_sandbox=True,
    injected_rounds=1,
    expected_last_run_id="replay-conflict",
    must_contain=("rebase 冲突（第 1 次）",
                  "::error::连续 3 次写回均失败"),
    must_not_contain=("已写回",),
    output_counts=(("push 被拒（第", 3), ("simulated rejection", 2)),
)
```

第一次 push 之前，冲突注入已经让 origin 前进了一轮，所以 push 先被
Git 的**非快进**检查拒绝（此时钩子还没被调用）；第 2、3 次才由
`pre-receive` 钩子拒绝。若照抄纯永久拒绝的「3 次 simulated rejection」，
就会把「钩子其实没走到第一次」误报成通过——这条计数是实测出来的，
不是从「三次拒绝」的字面推出来的。

### 2.2 失败场景的两种「远端变化」

`Scenario` 新增两个字段：

- `injected_rounds`：夹具侧先推进 origin 的轮数（目前只有冲突注入 = 1）；
  只在失败场景参与期望轮数：`min(before + injected_rounds, MAX_ROUNDS)`。
- `expected_last_run_id`：失败场景的末条身份。纯永久拒绝不设（沿用基线
  末条），组合场景设为 `replay-conflict`。

失败场景的 `rounds_clipped` 仍固定为 `False`：失败场景不宣称「本轮写入了」，
所以「轮数被裁剪」不适用；末条身份才是远端变化的唯一证据。错配提示也按
`injected_rounds` 分流：无注入 → 「远端历史不应变化」，有注入 →
「远端只应多出注入的冲突轮」。

### 2.3 冲突夹具遵守 MAX_ROUNDS

`_create_conflicting_round` 原来直接 `entries + [新轮]`。历史满 40 轮时，
成功场景会在写回时被 `record` 裁剪回 40，**失败场景没有这次写回**，origin
就停在 41 轮——生产里 `record` 永远不会写出这种历史。改为：

```python
entries = (entries + [{...}])[-history.MAX_ROUNDS:]
```

满窗组合场景的期望轮数因此是 40（不是 41），`last_run_id` 仍能证明注入轮
真的落到了远端。

### 2.4 用例

- `tests/test_replay_ci_writeback.py`：新增
  `test_replay_combines_conflict_with_permanent_rejection`——真实
  `replay.main` 跑组合旗标，断言 stdout 的 3 次「push 被拒」、1 次
  「rebase 冲突」、stderr 的 **2** 次「simulated rejection」、失败沙箱
  保留与清理。
- `tests/test_replay_ci_scenarios.py`：
  - 五场景清单/汇总行数/脚本模式条数（`4 → 5`）；
  - `test_scenario_table_pins_the_replay_counts` 增加组合场景的四项
    数字与两个新字段；
  - 窗口边界参数化（38/39/40）增加组合项：`39/40/40`，最后一项同时
    钉住「注入也遵守窗口」；
  - fetch 端到端清单（`5 → 6`）。
- CI 接线用例无需改动（场景表是共享的，两个 job 自动都跑组合）。

## 3. 用例（+1）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_writeback.py` | 1 | 组合旗标：3 次 push 被拒、1 次 rebase 冲突、2 次 simulated rejection、exit/reason/rounds/last_run_id/push_attempts、失败沙箱 |
| `tests/test_replay_ci_scenarios.py` | 0（改既有） | 五场景清单、场景表数字、38/39/40 三个窗口参数、fetch 清单与脚本条数 |

**本机全量**：**2661 passed / 28 skipped / 0 failed**（2689 条，343.44s）。
R104 为 2660 passed / 28 skipped（2688）。

## 4. 变异验证（7/7 全咬合）

| 变异 | 结果 |
|---|---|
| M93 把组合场景从 `SCENARIOS` 摘掉 | **1 红**（五场景行为用例） |
| M94 `injected_rounds` 1→0 | **1 红**（同上：rounds 期望少 1） |
| M95 `expected_last_run_id` → None | **1 红**（同上：末条身份） |
| M96 simulated rejection 2→3 | **1 红**（同上：输出计数） |
| M97 去掉冲突注入的 `[-MAX_ROUNDS:]` | **1 红**（窗口边界 `[40-…]`：41 ≠ 40） |
| M98 组合场景 expected_exit 1→0 | **1 红**（五场景行为用例） |
| M99 失败期望去掉 `min(…, MAX_ROUNDS)` | **1 红**（窗口边界 `[40-…]`：41 ≠ 40） |

M97/M99 是同一行窗口语义的两个方向，只有满窗 40 轮参数能咬住；空历史
的行为用例看不见它们。全部用 `cp` 备份还原并核对 sha256（备份在
`_r105_backup/`），没有 `git checkout --`。

## 5. 边界

- 组合场景在 **两个 job** 里都跑（`replay-ci-writeback` 与
  `replay-ci-fetch-chain` 共用同一张 `SCENARIOS`）；fetch 链 job 本次
  6/6 PASS（含组合与 `fetched`）。
- 组合场景仍走**本地 metrics**；真实 artifact 下载与拒绝/冲突的**三重
  叠加**没有做——fetch 路径、拒绝重试、冲突重算已分别有判据，叠加没有
  独立断言时只会增加运行时长。若要做，给组合场景加 `fetch=True` 与
  独立期望即可（列为下一步候选）。
- `MAX_ROUNDS` 保持 40；失败沙箱仍由驱动断言存在后清理，没有自动 GC；
  保留期策略未动。
- 写权限仍只属于 `e2e-history-writeback`；replay / fetch 两个 job 仍
  只读、不跑 pytest/e2e/npm/docker。

## 6. 提交与 CI

- 提交 **ea51b78**（`feat(R105): 永久拒绝与冲突组合场景`；rebase 前
  `cfca8d8`），显式路径 add，5 文件 +175/−37；
  `config/skills_config.json` 的外来改动保持未提交。
- 本机全量：**2661 passed / 28 skipped / 0 failed**（2689 条，343.44s）。
- CI run **41405610755**：**10 个 job run**（8 个定义；replay 与 fetch-chain
  各两平台）全 `success`（07:19:58→07:27:31，约 7m33s）——
  backend **2624/65**、windows-backend **2660/29**（均 **2689**）；
  `replay-ci-writeback` ubuntu/windows 各 **5/5 PASS**
  （rounds 26/26/27/25/26；永久拒绝末条 `ci-41401029610`；
  组合 `exit=1`、末条 `replay-conflict`、push_attempts 3）；
  `replay-ci-fetch-chain` ubuntu/windows 各 **6/6 PASS**
  （组合同样通过；`fetched` rounds 26、
  `last_run_id=replay-ci-fetched-ea51b781`、push_attempts 1；
  Windows 路径 `D:\a\xs2\xs2`）。
- 写回历史 **25 → 26 轮**（`ci-41405610755`、`source=ci`、10/10/0），
  bot 提交 `f733a46`（`[skip ci]`，未自触发）；本文档回填提交预计
  **26 → 27**。

## 7. 本轮教训

1. **「三次拒绝」不等于「钩子拒绝三次」**：冲突注入先让 origin 前进，
   第一次 push 被非快进挡住，钩子只看到第 2、3 次。判据必须由实测给出；
   照抄纯永久拒绝的 3 次 `simulated rejection` 会让「钩子没走到」被误报
   成通过。
2. **失败场景不止一种「远端变化」**：纯永久拒绝是「完全不变」，组合是
   「只多出注入轮」。用 `expected_last_run_id` 把两种失败形式分开，比给
   `rounds` 加特例更直接，也让失败场景的「末条身份」成为一等证据。
3. **夹具也要遵守生产不变量**：`record` 会裁剪到 `MAX_ROUNDS`，冲突注入
   不会；满窗失败场景把 origin 留在 41 轮。窗口断言遇到「41 == 41」就会
   被自己骗过（与 R102 的恒等式同型）。修在夹具，不是放宽期望。
4. **同一行窗口语义的两个方向要各有一条用例**：M97（不裁剪）与 M99
   （期望不封顶）都只有满窗 40 轮参数能咬住；空历史的行为用例全绿。
   「用例看起来在测」和「只有它能发现」是两件事（R70 同一教训）。

## 8. 下一步候选

- fetch 与拒绝/冲突的三重叠加（真实 artifact 下载后再三次拒绝 + 冲突）。
- 保留期策略：`MAX_ROUNDS` 40→80，或改成按天滚动（趋势样本）。
- 失败沙箱的自动 GC（当前只清理期望失败场景的现场）。
