# DeterminFlow (xs2) 交接报告 — Round 106（fetch × 永久拒绝 × 冲突三重叠加）

> 单 profile。把 R105 §8 的第一条候选做完：在全链 job 的真实 artifact
> 下载之后，再叠加三次拒绝与冲突注入，端到端证明 fetch 路径没有绕开写回
> 的拒绝/重算语义。零 `src/`、`web/` 改动；`MAX_ROUNDS`、失败沙箱策略、
> 写权限归属都不动。

## 1. 一句话结论

- **全链场景表新增 `fetched-rejected-conflict`**（`--fetch-api-url` 时
  追加）：真实 artifact 下载成功 → 冲突注入 → 第一次 push 非快进拒绝 →
  钩子拒绝第 2、3 次 → 三次尝试全失败。
- **期望与本地 `rejected-conflict` 完全一致**：`exit=1`、
  `reason=push-rejected`、`rounds=基线+1`、末条 `replay-conflict`、
  `push_attempts=3`、`simulated rejection` **2** 次；只多出
  「已下载 1 个文件」这条 fetch 证据。
- **两个全链场景都必须真的走 artifact API**：测试断言 API 请求路径里出现
  两次 GitHub run id、且不含历史 run id——否则回退到本地 metrics 也能
  把写回部分跑绿（M101 的教训）。
- 用例 **+1 → 2690**；本机 **2662 passed / 28 skipped / 0 failed**
  （228.38s）。R105 为 2661/28（2689）。
- **变异 M100–M108 9/9 咬合**；其中 **M102 只有表钉用例能发现**——
  `reject_pushes` 2 与 3 在本组合里行为完全等价（§4/§7）。
- CI run **41429330605**：**10 个 job run 全 `success`**，
  `replay-ci-fetch-chain` 两平台 **7/7 PASS**；写回历史
  **27 → 28**（`44fa941`）。

## 2. 实现要点

### 2.1 全链三重叠加场景

`scripts/replay_ci_scenarios.py` 新增：

```python
FETCH_REJECTED_CONFLICT_SCENARIO = Scenario(
    "fetched-rejected-conflict", 0, 3, reject_pushes=3, conflict=True,
    fetch=True,
    expected_exit=EXIT_MISMATCH,
    expected_reason="push-rejected",
    expect_sandbox=True,
    injected_rounds=1,
    expected_last_run_id="replay-conflict",
    must_contain=("已下载 1 个文件",
                  "rebase 冲突（第 1 次）",
                  "::error::连续 3 次写回均失败"),
    must_not_contain=("已写回",),
    output_counts=(("push 被拒（第", 3), ("simulated rejection", 2)),
)
```

它只在 `--fetch-api-url` 时追加，顺序在 `fetched` 之后：

```python
scenarios = SCENARIOS + (
    (FETCH_SCENARIO, FETCH_REJECTED_CONFLICT_SCENARIO)
    if fetch_api_url else ())
```

`replay_ci_writeback.py` **零改动**：CLI 早就允许 `--fetch-api-url` 与
`--reject-pushes`/`--conflict` 同时给（R99/R103 的能力），缺的是生产驱动
层的组合场景与独立期望。这也是本轮最容易被误判的地方——「功能已存在」
不等于「生产链路被证明过」。

### 2.2 fetch 只换 metrics 来源，不改变写回语义

replay 的顺序是：克隆 origin/work → 冲突注入 → 装拒绝钩子 →（fetch 时）
下载 artifact → `writeback()`。因此三重叠加的观测必须与本地组合场景逐项
相同；唯一的额外证据是 `must_contain=("已下载 1 个文件")`。把本地场景的
期望复制成全链场景而不是新写一套数字，避免两个来源各说一套。

### 2.3 用例

- `tests/test_replay_ci_writeback.py`：新增
  `test_replay_fetch_conflict_and_rejection_work_together`——真实
  `replay.main` 启动本地假 artifact API，断言下载成功、3 次 push 被拒、
  1 次 rebase 冲突、stderr 的 **2** 次 `simulated rejection`、exit/reason/
  rounds/last_run_id/push_attempts、失败沙箱保留后清理。
- `tests/test_replay_ci_scenarios.py`：
  - 全链端到端清单 `6 → 7`，新增三重场景的 actual 五项与失败沙箱清理；
  - 断言 artifact API 路径出现 **≥2** 次 GitHub run id、且不含
    `replay-ci-` 历史 run id；
  - `test_scenario_table_pins_the_replay_counts` 增加全链场景的字段钉。

### 2.4 CI 接线无需改动

`replay-ci-fetch-chain` 调用的就是同一张场景表；`--fetch-api-url` 一给，
新场景自动进入。`replay-ci-writeback`（不传 fetch 参数）仍是本地 5 场景。

## 3. 用例（+1）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_writeback.py` | +1 | 全链三重叠加：下载成功 + 3 次拒绝 + 1 次冲突 + 2 次钩子拒绝 + exit/reason/rounds/last_run_id/push_attempts + 失败沙箱 |
| `tests/test_replay_ci_scenarios.py` | 0（改既有） | 全链清单 7 项、三重场景 actual、API 路径证据、场景表字段钉 |

**本机全量**：**2662 passed / 28 skipped / 0 failed**（2690 条，228.38s）。
R105 为 2661 passed / 28 skipped（2689）。

## 4. 变异验证（9/9 咬合，M102 仅表钉）

| 变异 | 结果 |
|---|---|
| M100 从 fetch 模式摘掉三重场景 | **1 红**（全链行为用例：清单少一项） |
| M101 三重场景 `fetch=True→False` | **2 红**（表钉 + 全链行为：缺「已下载」且没走 API） |
| M102 `reject_pushes 3→2` | **仅表钉 1 红**；行为用例全绿（见下） |
| M103 `expected_last_run_id→None` | **2 红**（表钉 + 全链行为：末条身份） |
| M104 `simulated rejection 2→3` | **2 红**（表钉 + 全链行为：输出计数） |
| M105 `injected_rounds 1→0` | **2 红**（表钉 + 全链行为：rounds 少 1） |
| M106 `must_contain` 改成「已下载 99 个文件」 | **2 红**（表钉 + 全链行为：输出缺 token） |
| M107 三重场景 `conflict=True→False` | **2 红**（表钉 + 全链行为：末条/轮数/拒绝计数全变） |
| M108 `expected_reason push-rejected→written` | **2 红**（表钉 + 全链行为：reason 不符） |

**M102 是真实边界，不是漏网**：冲突注入先把 origin 推前一轮，第一次 push
必然被 Git 的非快进检查挡下，**根本到不了 `pre-receive` 钩子**；钩子只要
拒绝后两次（`reject_pushes=2`）就能让三次尝试全失败。实测 2 与 3 的退出码、
rounds、末条、`simulated rejection` 次数、push_attempts 完全相同，所以只有
「表里的数字」能区分。场景定义处已写明：`3` 是与纯永久拒绝同口径的拒绝
预算，**行为阈值是 2**。

全部用 `cp` 备份还原并核对 sha256（备份在 `_r106_backup/`），没有
`git checkout --`。

## 5. 边界

- 三重场景只在 **`replay-ci-fetch-chain`** 跑；该 job 的 gate 是
  `push main && backend success`，PR 不跑全链。`replay-ci-writeback`
  仍是本地 5 场景。
- artifact 内容仍是同一份 10 场景形状的 metrics；本场景证明「fetch 路径
  不绕开拒绝/冲突语义」，**不证明**「不同 artifact 内容会改变写回结果」
  （内容依赖由 backend 的 e2e 与 R96 文件名契约覆盖）。
- `MAX_ROUNDS` 保持 40；失败沙箱仍由驱动断言存在后清理，没有自动 GC；
  保留期策略未动。
- 写权限仍只属于 `e2e-history-writeback`；replay / fetch 两个 job 仍只读、
  不跑 pytest/e2e/npm/docker。

## 6. 提交与 CI

- 提交 **c2a0478**（`feat(R106): fetch×拒绝×冲突三重叠加`），显式路径
  add，3 文件 +114/−7；`config/skills_config.json` 的外来改动保持未提交。
- 本机全量：**2662 passed / 28 skipped / 0 failed**（2690 条，228.38s）。
- CI run **41429330605**：**10 个 job run**（8 个定义；replay 与
  fetch-chain 各两平台）全 `success`（10:30:21→10:38:13，约 7m52s）——
  backend **2625/65**、windows-backend **2661/29**（均 **2690**）；
  `replay-ci-writeback` ubuntu/windows 各 **5/5 PASS**
  （rounds 28/28/29/27/28；永久拒绝末条 `ci-41406945790`；
  组合末条 `replay-conflict`、push_attempts 3）；
  `replay-ci-fetch-chain` ubuntu/windows 各 **7/7 PASS**：
  两个全链场景都通过，`fetched` rounds 28、
  `last_run_id=replay-ci-fetched-c2a0478c`；新增
  `fetched-rejected-conflict` **exit=1、rounds=28（基线 27+注入 1）、
  末条 `replay-conflict`、push_attempts 3**（Windows 路径
  `D:\a\xs2\xs2`）。
- 写回历史 **27 → 28 轮**（`ci-41429330605`、`source=ci`、10/10/0），
  bot 提交 `44fa941`（`[skip ci]`，未自触发）；本文档回填提交预计
  **28 → 29**。

## 7. 本轮教训

1. **配置里的数字不一定是行为边界**：`reject_pushes=3` 看起来像「三次
   拒绝」，但第一次 push 到不了钩子，行为阈值是 2。表钉用例能守住字面，
   行为用例守不住——两者都要有，且要写明哪个数字只是口径。
2. **「功能已存在」不等于「生产被证明过」**：CLI 早就支持 fetch + 拒绝 +
   冲突同时给，R106 的产出不是新开关，而是把这条组合放进生产 job 并给它
   独立期望。写交接时不要把「复用了既有能力」说成「新增能力」。
3. **全链场景必须证明 artifact 真的被用上**：`fetch=False` 时写回部分照样
   能跑绿（M101），只有「已下载 1 个文件」+ API 路径两条证据能区分。任何
   「先下载再 X」的链路，判据里都要有一条只可能来自下载的观测。
4. **同一语义的本地/全链版本要共用字段**：三重场景直接复制本地组合的
   期望值，避免两套数字漂移；全链只多一条下载证据。

## 8. 下一步候选

- 保留期策略：`MAX_ROUNDS` 40→80，或改成按天滚动（趋势样本）。
- 失败沙箱的自动 GC（当前只清理期望失败场景的现场）。
- 若要让「拒绝预算」成为行为边界：把冲突注入挪到第一次 push **之后**
  （新夹具），否则 `reject_pushes=2` 与 `3` 永远等价；或在场景表里直接
  写 2 并把「拒绝所有钩子可见尝试」写进名字/注释。
- artifact 内容维度：让全链场景用一份**不同于本地**的 metrics（如
  失败/重试形状），证明写回结果确实取自下载内容。
