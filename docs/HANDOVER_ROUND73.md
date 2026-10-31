# DeterminFlow (xs2) 交接报告 — Round 73（#3 的退出路径：回归判据的门也要用边界计数）

> 本轮定位：R72 §8-5「另外两条判据的 3/4 分支对齐」的第一条——把
> `check_per_workflow_regression` 的退出 4（元数据漂移）与退出 3（无样本）
> 与 #3 的翻转点用同一组计数（character 上一轮 2/79、当前 15/79 与 16/79）
> 绑在一起。落地形态：**仅测试 + 文档**，生产代码零改动。

## 1. 一句话结论

R62 的漂移/无样本用例都落在「判不出回归」的计数上（40/0），所以「只有判不出
回归时才查漂移」这类改法在它们面前全绿——而它会让一个内容为 16/79（会判回归）
的快照被元数据改写成 15/79 后静默通过。本轮用 #3 的边界计数加 3 条走真实入口
（落盘快照 + `history` → `snapshot_rounds` → 报告 → 退出码）的用例，把门接到
翻转点上。

## 2. 最重要的一件事：两次唯一咬合、两次不是

四次变异都跑全部相关用例（`test_judgement_flip_points` +
`test_live_snapshot_gate` + `test_judgement_ledger` + `test_msys_attribution`，
基线 191）：

| # | 变异 | 实测 | 唯一咬合者 |
|---|---|---|---|
| 1 | 漂移检查保留在历史守卫之前，但「判出回归时跳过漂移」 | **1 failed**：`test_metadata_drift_preempts_the_per_workflow_regression_verdict` | **B**（R62 漂移用例无 exceeds；共用漂移消息用例走无历史分支仍返回 4） |
| 2 | `if not actual:` 从退出 3 改成退出 0 | **1 failed**：`test_no_sample_preempts_the_per_workflow_regression_verdict` | **C**（空内容分支此前无回归判据覆盖） |
| 3 | 漂移退出码 4 → 3 | **2 failed**：B + 既有 `test_per_workflow_regression_rejects_metadata_content_drift` | 否 |
| 4 | `per_workflow_regression_report(rounds[-2], …)` → `(rounds[-1], …)`（拿当前轮当上一轮） | **4 failed**：A + 既有 exceeds fixture / malformed history / CLI 三处 | 否 |

所以诚实的说法是：**B/C 各在一条变异上是唯一咬合者；A 不是**——A 的增量是把
#3 的翻转点放进真实入口（纯函数层看不见 `history` 的取法），不是「只有它能
发现」。R69/R70/R72 的教训继续生效。

## 3. 设计

1. **本地 helper** `_write_regression_snapshot(root, previous, current)`：先用
   `_write_rate_snapshot` 落盘当前轮，再补一条 `history`（只写
   `attempts`/`failed`，`snapshot_rounds` 也只用这两个数）。
2. **三条用例**（都通过 `check_per_workflow_regression`，不是纯函数）：
   - `test_per_workflow_regression_flip_point_through_the_real_gate`：上一轮
     2/79，当前 15/79 → 退出 0（「1 个可判 / 0 个判回归 / 区间横跨阈值」；
     16/79 → 退出 1，来源行写明 character。
   - `test_metadata_drift_preempts_the_per_workflow_regression_verdict`：内容
     16/79，元数据写 15/79 → 退出 4，消息不含「判回归」/「退出码 1」。
   - `test_no_sample_preempts_the_per_workflow_regression_verdict`：缺元数据
     文件 / 缺 `per_workflow` 块 / 内容为空 → 退出 3，消息不含判决词。
3. **注册**：`_FLIP_POINT_TESTS["3"]` 追加三个名字；登记页 §7 的 #3 行追加
   用例名，新增 §7.3（前提 / 同一组计数下的期望 / 用例）。
4. **登记页**：§2 #3 的盲区补「3/4 两条退出路径先于判决」；§6 增一行。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/test_judgement_flip_points.py` | **+106 / −2** | helper + 3 条用例 + 注册表 + docstring |
| `docs/JUDGEMENT_LEDGER.md` | **+19 / −2** | §2 盲区 / §6 一行 / §7 #3 用例格 / 新增 §7.3 |
| `docs/PROJECT_INFO.md` | **+1 行** | R73 轮次条目 |
| `docs/HANDOVER_ROUND73.md` | 新增 | 本文 |

**生产代码零改动**：`scripts/check_live_snapshot_gate.py`（`7a329d3a…`）与
`scripts/e2e_workflow_stub.py`（`a5104e69…`）与 R72 记录逐字节相同。

## 5. 变异验证（四次，`cp` 备份还原）

跑的是全部相关用例（基线 **191**）。每次还原后 `md5sum` 与备份逐字节相同
（`7a329d3a4e8d0cd38e2f2a3078889cb1`），还原后相关集 **191 passed**。

| # | 变异 | 实测（完整失败清单） |
|---|---|---|
| 1 | 判出回归时跳过漂移检查 | `test_metadata_drift_preempts_the_per_workflow_regression_verdict`（1 红） |
| 2 | `if not actual:` 退出 3 → 退出 0 | `test_no_sample_preempts_the_per_workflow_regression_verdict`（1 红） |
| 3 | 漂移退出码 4 → 3 | B + `test_per_workflow_regression_rejects_metadata_content_drift`（2 红） |
| 4 | 拿当前轮当上一轮 | A + `test_the_exceeds_fixture_fires_the_per_workflow_regression_gate` + `test_per_workflow_regression_skips_malformed_history_but_reports_it` + `test_cli_per_workflow_regression_mode_is_wired`（4 红） |

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`tests/test_judgement_flip_points.py` | **18 passed**（0.27s） |
| 相关集：msys + ledger + flip points + live snapshot gate | **191 passed**（5.75s） |
| 全量（本机，Low `S-1-16-4096`） | **2200 passed / 113 skipped / 0 failed**（132.43s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（零生产代码改动） |

**对账**：总用例 **2310 → 2313**（+3）。Low `2200+113` = **2313**。

## 7. 未做与未验证的事（如实记录）

1. **只做了 #3**：`check_per_workflow`（样本量诊断判据）的 3/4 分支仍未用
   同一组计数对齐；它没有数值翻转点，属于纯分支覆盖（见 §8-5）。
2. **A 不唯一**：见 §2，M4 同时咬住三条既有用例；A 的增量是真实入口的
   连通性。
3. **skip 不等于通过**：113 条在 Low 下未执行。
4. **未跑 e2e / docker build / npm run build / 未重启 8021**：零生产与零前端改动。
5. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
6. **重导仍被数据卡住**：`run-*.json` 仍是 **40 个**，最新仍是
   `2026-10-28 08:34`（本轮实查）。

## 8. 下一轮候选

1. **重跑频率的可观测性**（R68 §7-4）：本轮计划中的 R74。
2. **畸形 `per_workflow` 元数据不得冒充「判了不合格」**（R64 退出码冒充家族）：
   本轮计划中的 R75。
3. **`check_per_workflow` 的 3/4 分支对齐**（R73 新增）：它没有数字翻转点，
   只做三条 exit-3 分支与顺序断言。
4. **有新 run 后再重导**：唯一被外部数据卡住的候选，已连续多轮。
5. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
6. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile
   的路径，但可能动正在被 shell 使用的命名对象。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

（推送后补记）
