# DeterminFlow (xs2) 交接报告 — Round 70（判据边界的两种「不是常量」）

> 本轮定位：R69 §9 的 #3「留一法基线与翻转点串联」+ #4「贴边浮点」合并。
> 基线 `75c30ae`（R69 补记）。用户拍定：主线 = #3+#4；§3 那三个未被翻转点
> 覆盖的量**维持现状**（理由已在登记页 §7 具名）。
> 落地形态：**零生产代码改动**，只加深验证；收尾照常推送 + 五 job 逐字核对。

## 1. 一句话结论

R69 的翻转点钉的是「**阈值 = 登记的那个常量**」。但这句话有两种不成立的方式，
R69 一条都没挡住：**那个常量是怎么算出来的**（留一法基线）与**边界在什么
粒度上成立**（时间算术）。本轮各补一条用例，并把覆盖守卫从「一条判据一个用例
名」升级成「一条判据可以有多条，每一条都必须登记且写进 §7」。

## 2. 最重要的一件事：先跑全部相关用例，再决定这句话怎么说

R69 §2 的教训是「论证新用例的价值时，变异必须跑在**全部**相关用例上」。本轮
照做，结果否定了一个很顺手的说法：**四条变异里只有一条是新用例唯一咬住的**。

| # | 变异 | 期望 | 实测（`test_live_snapshot_gate` + `test_judgement_ledger` + `test_judgement_flip_points`，基线 180） |
|---|---|---|---|
| 1 | `per_workflow_rate_report` 里 `margin` → `margin * 2`（给留一法单独换一套阈值） | 新用例必须掉 | **2 failed**：`test_rate_check_passes_on_the_committed_snapshot`（既有）+ `test_leave_one_out_baseline_drives_the_flip_point`（新） |
| 2 | `per_workflow_baselines` 的 `rest_*` 改成全局合计（基线含自己） | 新用例必须掉 | **3 failed**：`test_leave_one_out_baseline_excludes_the_judged_workflow`、`test_leave_one_out_baseline_is_none_for_a_lone_workflow`（均既有 R56）+ 新用例 |
| 3 | `total_seconds() / 86400` → `(latest - exported).days` | 新用例必须掉 | **3 failed**：`test_freshness_flips_at_the_registered_days`、`test_freshness_default_is_the_registered_days`（均 R69）+ 新用例 |
| 4 | 同样的表达式外面套 `round(..., 1)`（天数四舍五入到 0.1） | 新用例必须掉 | **1 failed**：**只有** `test_freshness_flips_within_one_microsecond`（新） |

所以诚实的说法是：

- **留一法那条新用例不是唯一咬合者**。R56 的两条基线算术用例与 R69 的整点
  翻转点用例，在变异 1~3 上都会一并变红。它的增量是**把翻转点放进真实路径**：
  既有用例要么只钉基线算术（不判结论），要么只钉 `_rate_verdict` 这一层
  （基线是测试里写死的 `0.0`）。只有这条用例同时要求「基线由计数算出来」与
  「k=3 判不了 / k=4 判超出」。
- **微秒那条在变异 4 上是唯一咬合者**——而这正是它存在的原因：`.days` 这种
  粗粒度改法连 R69 的 7.1 天用例都能糊弄（`int(7.1) = 7`，不超 7），只有
  「7 天 + 1 微秒」能把它揪出来。

**教训（R69 §2 的同型，第二次）**：一个用例「有价值」与「只有它能发现」是两件
事；后者必须靠**全部相关用例上的变异实测**才说得出口。本轮初稿若按「只有新用例
能发现」写，表中第 1~3 行会当场打脸。

## 3. 设计

1. **#3 留一法串联**（`test_leave_one_out_baseline_drives_the_flip_point`）：
   从 `{workflow: (attempts, failed)}` 出发，`per_workflow_baselines` →
   `per_workflow_rate_report` 全程。rest 30 次零失败 ⇒ target 的留一法基线
   0/30 = 0.00%；target 10 次里 3 次判不了、4 次（40%）判超出。并显式断言
   **基线不随 target 自己的失败数变化**（k=3 与 k=4 时逐位相同）——那是 k=4
   还能翻得过去的原因，也是「留一法」三个字的意思。
2. **#4 贴边浮点**（`test_freshness_flips_within_one_microsecond`）：
   导出 `2026-01-01T00:00:00+00:00`，滞后 **7 天 − 1 微秒** 判通过、
   **7 天 + 1 微秒** 判过期。R69 的整点用例在整秒世界里「7.0 天」恰好可表示，
   覆盖不到时间算术的粒度；这条把「滞后按秒算、边界是精确的」钉死。
3. **覆盖守卫升级**：`_FLIP_POINT_TESTS` 的值从 `str` 改成 `tuple[str, ...]`，
   守卫对**每一个**用例名都查「函数存在 + 写进登记页 §7」。R69 时「一条判据
   对应一个用例名」的隐含约定不再成立，未登记的翻转点用例同样算不通过。
4. **登记页**：§7 的 #4/#6 两行补上新用例名；§6「这一页上的数由谁复核」补两行；
   新增 §7.1 把这两种缺口写成一张表（改法 / R69 看得见吗 / R70 的补丁）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/test_judgement_flip_points.py` | **+79 / −14** | 2 条新用例 + 守卫改多值映射 |
| `docs/JUDGEMENT_LEDGER.md` | **+25 / −3** | §6 两行、§7 两行、新增 §7.1 |
| `docs/HANDOVER_ROUND70.md` | 新增 | 本文 |
| `docs/PROJECT_INFO.md` | **+1 行** | 轮次条目（顶格新行） |

**零生产代码改动**：`scripts/check_live_snapshot_gate.py` 的 md5 仍是
`7a329d3a4e8d0cd38e2f2a3078889cb1`，与 R69 §6 记录的逐字节相同。本轮的产出是
**验证深度**，不是行为变更。

## 5. 变异验证（四次，`cp` 备份还原）

见 §2 的表。还原用 `cp _r70_gate_backup.py` 覆写，md5 与备份逐字节相同
（`7a329d3a…4cb1`）；不用 `git checkout --`（R55 教训）。还原后定向
**180 passed**。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 全量（本机，High 令牌） | **2189 passed / 113 skipped / 0 failed**（123.95s） |
| 全量（本机，**真降到 Low** 令牌 S-1-16-4096） | **2189 passed / 113 skipped / 0 failed**（124.94s） |
| 定向：`test_live_snapshot_gate` + `test_judgement_ledger` + `test_judgement_flip_points` | **180 passed**（5.31s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（本轮零生产代码改动） |

**对账**：总用例 **2300 → 2302**（+2）。2189 + 113 = 2302。

### 6.1 本机双基线只剩一种 profile（如实记录，与 R69 不一致）

R69 记的是 Low `2187/113`、High `2272/28`。本轮两次运行**都是 2189/113**
——包括用 `SetTokenInformation(TokenIntegrityLevel)` 真把令牌降到
`S-1-16-4096` 的那一次（进程内实测 SID 回读确认，不是推断）。

根因：本会话里**新起的 `sh.exe` 挂不上 msys 共享对象**
`\BaseNamedObjects\msys-2.0S…`（`NtCreateDirectoryObject … 0xC0000022`），
`tests/conftest.py::_git_transport_blocked_probe` 因此返回 `True`，六个
git-transport 模块整体 skip。实测范围：

| 启动器 | 令牌 | probe |
|---|---|---|
| Git Bash | High | `True` |
| cmd / PowerShell | High | `True` |
| 自降令牌（进程内回读 S-1-16-4096） | Low | `True` |
| 直接在 Git Bash 里 `git clone` | High | 成功（bash 自己早已挂接该对象） |

所以：**113 skipped 不是完整性级别的函数**，至少在「High 且对象不可挂接」这种
状态下也会发生。R65~R69 的 28-skip「High」基线在当前会话状态**复现不出来**；
本轮的 28-skip 数值只保留为算术对账（2274 + 28 = 2302），没有实测支撑。
这不是本轮改动引起的：生产代码 md5 未变，新增用例一条都不碰 git。

## 7. 未做与未验证的事（如实记录）

1. **没有复现 28-skip profile**，原因与边界见 §6.1；本轮不追查 msys 对象 ACL
   为什么会话间变化（需要跨会话对照实验，且可能要动正在被 shell 使用的命名对象）。
2. **翻转点仍不证明「阈值选得对」**：本轮只证明留一法基线是**算出来的**、
   新鲜度边界是**精确的**；3pp / 8pp / 10pp / 7 天这些数本身的校准属于 R61、
   R67。
3. **#4 只到「基线算出来」这一层**：`check_per_workflow_rate` 的元数据漂移、
   无样本两条失败路径没有与本用例串联（它们各有 R56 的用例）。
4. **未跑 e2e**：本轮没碰 `e2e_workflow_stub.py`（md5 `a5104e69…` 与 R69 记录
   一致），R68 的 10/10 与 R69 的 CI 10/10 仍适用。
5. **未跑 `docker build` / `npm run build` / 未重启 8021**：零生产代码与零前端改动。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
7. **重导仍被数据卡住**：`data/workflows/*/runs/run-*.json` 仍是 **40 个**，
   最新 `run-dfe789fd.json` 仍是 `2026-10-28 08:34`（今日实查，不是照抄）。
   R60~R63 的重导与 R69 §9-1 继续挂账。

## 8. 下一轮候选

1. **有新 run 后再重导**：唯一被外部数据卡住的候选，已连续多轮。
2. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
3. **重跑频率的可观测性**（R68 §7-4）：重跑真的频繁出现时，该改的是容差。
4. **会话级 msys 状态的判定**（本轮 §6.1 的新发现）：`conftest` 现在把 113 skips
   归因于「Low-integrity token」，但实测 High 下也会发生——提示文案与归因
   值得改准（「无法挂接 msys 共享对象」而不是「Low 令牌」），并留一个可复现
   的判据。**不改判据逻辑，只改归因措辞**也需要一次全量实跑。
5. **留一法基线的元数据漂移路径**（本轮 §7-3）：把 `check_per_workflow_rate`
   的 3/4 两条退出路径与翻转点串起来。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认，本轮把它的边界钉到微秒）；「轮」按导出轮推进
（R59 拍定，CI 不写回仓库）。

## 9. 推送与 CI 核对

（待推送后补记）
