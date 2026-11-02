# DeterminFlow (xs2) 交接报告 — Round 108（拒绝预算成为行为边界）

> 单 profile。把 R106 §8 的第三条候选做完：冲突注入从「writeback 开始前」
> 挪到「第一次 push 被拒的瞬间」，由 `pre-receive` 钩子自己把 origin 推进
> 一轮。第一次 push 因此真的走到钩子，`reject_pushes` 的 2 与 3 第一次成为
> **可区分的行为边界**。零 `web/` 改动；`MAX_ROUNDS`、失败沙箱策略、
> 写权限归属都不动。

## 1. 一句话结论

- 新增 `--conflict-on-reject`：拒绝钩子在**第一次拒绝**时用 git plumbing
  在 origin 上追加一轮 `history.json` 冲突历史，然后拒绝这次 push。
- 两个新场景：
  - `rejected-hook-conflict`（预算 3）：三次 push 全部被钩子拒绝，
    `simulated rejection` **3** 次、末条 `replay-conflict`、退出码 1；
  - `rejected-hook-budget-2`（预算 2）：第 1、2 次被拒（第 1 次注入冲突），
    第 3 次 push 成功，净 +2（注入轮 + 本轮）、末条是本轮。
- 同一夹具、同一注入时机，只改预算：**2 → 成功，3 → 失败**。R105/R106
  里「2 与 3 行为等价」的边界被真正拆开。
- 用例 **+2 → 2695**；本机 **2667 passed / 28 skipped / 0 failed**
  （242.86s）。R107 为 2665/28（2693）。
- **变异 M113–M119 7/7 咬合**；M119（注入不遵守窗口）只有满窗 40 的
  参数能咬住（§4）。
- CI run **41438478792**：**10 个 job run 全 `success`**；writeback 两平台
  各 **7/7 PASS**、fetch-chain 各 **9/9 PASS**；写回历史 **31 → 32**
  （`8ed84df`）。

## 2. 实现要点

### 2.1 钩子内注入冲突

`_install_rejection_hook(..., inject_conflict=True)` 额外生成
`origin/hooks/replay_conflict_inject.py`，`pre-receive` 在 `n == 0` 时先跑它：

```python
git("read-tree", ref, index=temp_index)
git("hash-object", "-w", "--stdin", input=new_history_bytes)
git("update-index", "--add", "--cacheinfo", "100644", blob_sha, HISTORY,
    index=temp_index)
tree = git("write-tree", index=temp_index)
commit = git("commit-tree", tree, "-p", old, "-m", "...")
git("update-ref", ref, commit, old)
```

不走工作树（Windows 没有 checkout 的路径问题），也不在钩子里再克隆。
`update-ref` 的旧值校验保证 origin 在此期间没被别人动过。

**关键陷阱：quarantine。** Git 在 `pre-receive` 里会把新对象写进隔离区，
钩子失败（exit 1）后隔离区被丢弃；如果注入脚本顺着这个环境写对象，
`update-ref` 会指向不存在的 commit，origin 直接坏掉。因此注入脚本显式
移除 `GIT_OBJECT_DIRECTORY` / `GIT_ALTERNATE_OBJECT_DIRECTORIES` /
`GIT_QUARANTINE_PATH`，让 blob/commit 落进真实对象库。

### 2.2 预算 2 vs 3 的时间线

预算 3：

```text
push#1 → 钩子拒绝（n=0，注入冲突轮，count=1）
      → pull --rebase 冲突 → 丢弃本地提交、reset 到 origin
push#2 → 钩子拒绝（n=1，count=2）→ pull 成功
push#3 → 钩子拒绝（n=2，count=3）→ 重试耗尽，exit 1
```

预算 2：

```text
push#1 → 钩子拒绝（n=0，注入冲突轮，count=1）→ pull 冲突 → reset
push#2 → 钩子拒绝（n=1，count=2）→ pull 成功
push#3 → n=2 不满足 n<2 → 接受 → 已写回，净 +2
```

第一次 push 从此真的到钩子，`simulated rejection` 的次数等于实际拒绝
次数（预算 3 → 3；预算 2 → 2），不再被非快进挡掉。

### 2.3 旧场景保留

`--conflict`（writeback 前注入）与 `--conflict-on-reject` 互斥，
`--conflict-on-reject` 要求 `--reject-pushes >= 1`（否则退 2）。
R105 的 `rejected-conflict` 仍保留：它覆盖「第一次是非快进、钩子只看得到
后两次」这条路径，并在场景注释里说明其预算行为阈值仍是 2。R108 不删除
那条证据，只是**新增**一条 2/3 可分的路径。

### 2.4 用例

- `tests/test_replay_ci_writeback.py`：
  - `test_replay_hook_injects_conflict_on_first_rejection`：预算 3，
    3 次钩子拒绝、1 次 rebase 冲突、`simulated rejection` 3、末条
    `replay-conflict`、失败沙箱；
  - `test_replay_rejection_budget_two_is_a_real_boundary`：预算 2，
    第 3 次成功、净 +2、末条本轮、成功沙箱删除。
- `tests/test_replay_ci_scenarios.py`：场景清单 5→7、actual 五项、
  失败沙箱清单、summary 行数、fetch 清单 7→9、窗口参数（38/39/40）
  增加两条新场景（budget-2 在 39/40 触发裁剪）。

## 3. 用例（+2）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_writeback.py` | +2 | 预算 3 全失败 / 预算 2 第三次成功 |
| `tests/test_replay_ci_scenarios.py` | 0（改既有） | 7 场景清单、新场景 actual、窗口参数、fetch 清单 9 |

**本机全量**：**2667 passed / 28 skipped / 0 failed**（2695 条，242.86s）。

## 4. 变异验证（7/7 咬合）

| 变异 | 结果 |
|---|---|
| M113 装钩子但不注入冲突 | **1 红**（预算 3 行为用例：没有 rebase 冲突/rounds=0） |
| M114 注入脚本不 `update-ref` | **1 红**（同上：origin 不前进） |
| M115 驱动不传 `--conflict-on-reject` | **1 红**（七场景行为用例） |
| M116 预算 2 场景实际用 3 | **1 红**（七场景行为用例：第三次不再成功） |
| M117 预算 2 期望净增量 2→1 | **1 红**（七场景行为用例：rounds） |
| M118 每次拒绝都注入冲突 | **1 红**（预算 3 行为用例：重复 run_id/轮数异常） |
| M119 注入不遵守 `MAX_ROUNDS` | **1 红**（仅满窗 40 参数：41 ≠ 40） |

M119 与 R105 的 M97/M99 同型：**窗口语义的缺陷只有满窗参数能看见**；
空历史的行为用例全绿。

全部用 `cp` 备份还原并核对 sha256（备份在 `_r108_backup/`）。

## 5. 边界

- 钩子注入只在**沙箱 origin** 上发生；源仓库只读检查仍然逐场景执行。
- `--conflict` 与 `--conflict-on-reject` 互斥；后者要求预算 ≥1，否则退 2。
- 注入的冲突轮 `run_id=replay-conflict`，与 R105 同一个身份；失败场景的
  末条断言因此可以共用。
- `MAX_ROUNDS` 保持 40；失败沙箱仍由驱动断言存在后清理；写权限仍只属于
  `e2e-history-writeback`；replay / fetch 两个 job 仍只读。
- 全链 job 现在跑 9 个场景（7 本地 + 2 下载）；多出的两条是本地 metrics
  场景，不额外依赖 artifact 形状。

## 6. 提交与 CI

- 提交 **d06fadc**（`feat(R108): 钩子首次拒绝注入冲突，拒绝预算成行为
  边界`；rebase 前；rebase 后 **0112001**），显式路径 add，4 文件
  +333/−32；`config/skills_config.json` 外来改动保持未提交。
- 本机全量：**2667 passed / 28 skipped / 0 failed**（2695 条，242.86s）。
- CI run **41438478792**：**10 个 job run** 全 `success`
  （11:39:00→11:46:33，约 7m33s）——backend **2630/65**、
  windows-backend **2666/29**（均 **2695**）；
  `replay-ci-writeback` ubuntu/windows 各 **7/7 PASS**
  （rounds 32/32/33/31/32/32/33；预算 3 末条 `replay-conflict`、
  push 3；预算 2 末条 `replay-ci-rejected-hook-budget-2-01120018`、
  净 +2、push 3）；
  `replay-ci-fetch-chain` 两平台各 **9/9 PASS**（同上 7 条 + `fetched` +
  `fetched-rejected-conflict`）。
- 写回历史 **31 → 32 轮**（`ci-41438478792`、`source=ci`、10/10/0），
  bot 提交 `8ed84df`（`[skip ci]`，未自触发）；本文档回填提交预计
  **32 → 33**。

## 7. 本轮教训

1. **要让一个数字成为行为边界，改状态/时机，不要改断言**：R106 的
   `reject_pushes=3` 只是字面口径，因为第一次 push 根本到不了钩子；R108
   把注入搬进钩子后，2 与 3 自然分开。判据的价值来自**路径**，不是来自
   写死一个数。
2. **钩子里写的对象会被 quarantine 吞掉**：`pre-receive` 失败后隔离区
   丢弃，`update-ref` 悬空。任何「钩子内改仓库」的实现都必须先清掉
   `GIT_OBJECT_DIRECTORY` / `GIT_ALTERNATE_OBJECT_DIRECTORIES` /
   `GIT_QUARANTINE_PATH`。
3. **「失败现场保留」对钩子同样适用**：注入脚本失败不会让 push 成功
   （仍 exit 1），但会让 rebase 冲突消失；行为断言必须同时看
   `simulated rejection` 次数、`rebase 冲突` 与末条身份，缺一项就可能把
   「注入没发生」误判成「拒绝发生了」。
4. **窗口缺陷只有满窗能看见**：M119 在空历史全绿，40 轮才红。新夹具的
   注入路径也必须进窗口参数化。

## 8. 下一步候选

- R109：保留期策略——`MAX_ROUNDS` 可配置（默认仍 40）。
- R110：失败沙箱自动 GC（默认 dry-run、只认约定前缀与过期年龄）。
- 钩子注入的第二个变体：在**第 N 次**拒绝注入（当前固定第一次），用于
  验证「预算 2 在中途耗尽」的更多时间线。
- 全链 artifact 内容语义：让下载的 metrics 用失败/重试形状。
