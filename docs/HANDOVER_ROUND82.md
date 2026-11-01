# DeterminFlow (xs2) 交接报告 — Round 82（两块元数据：任何读计数的入口都校验整份工件）

> 本轮定位（用户拍定）：主线 = R80 §8-5「`totals` × `per_workflow` 交叉一致性」；
> 另一项按拍定执行——**本轮重导快照**（R81 §8-5 挂账项）。
> 落地形态：**一个生产文件（闸门脚本）+ 测试 + 入库快照 + 文档**；CLI 无新增开关，
> CI YAML 零改动。

## 1. 一句话结论

R80 挂的账「两块各自与内容比、互相之间没有判据」在实现上是更尖锐的一件事：
**默认判定（`evaluate` / `--fail-if-above`，CI 第 8 步）根本不读 `per_workflow`
元数据。** 把一次失败从 A 工作流挪到 B，全局合计分毫不动，旧代码退出 **0**，
只有 `--check-per-workflow` 退 4；反方向（四条 per-workflow 判据不读 totals）
同样存在。本轮不给新开关，而是把「另一块」的校验补进**六个读计数的入口**，
统一退出 **4**；并把 `recompute_totals` 改成 `recompute_per_workflow` 的求和，
让两块钉在**同一次**内容复算上——「互相一致」成为构造保证，而不是一条求和对账。

## 2. 缺口实测（旧脚本 / 新脚本，同一份快照）

探针 `_r82_probe.py`（未入库）用两份临时快照分别喂旧、新脚本。旧脚本 =
本轮改动前的逐字节副本（`_r82_gate_orig.py`，md5 `8e13df17…`）。

| 场景 | 入口 | 旧 | 新 |
|---|---|---|---|
| 两块都真（基线，20 次尝试 / 2 失败） | `evaluate(ceiling=8)` | 0 | 0 |
| 同上 | `check_sample_size(10)` | 7（太薄） | 7 |
| per_workflow 挪一次失败（totals 不变） | `evaluate` | **0** | **4** |
| 同上 | `check_sample_size` | **7** | **4**（漂移先于精度） |
| totals 说谎（per_workflow 与内容都真） | `check_per_workflow` | **0** | **4** |
| 同上 | `check_per_workflow_rate` | **0** | **4** |
| 同上 | `check_per_workflow_regression` | **0** | **4** |
| 同上 | `check_lead_time` | **3**（无上一轮） | **4** |

新脚本的说明会点名是哪一块：「per-workflow 元数据与内容不一致（全局合计可能仍然
相等，所以全局校验看不出来）：wf-a: 元数据 (1, 10, 2)，内容复算 (1, 10, 1)…」
与「totals 元数据与内容不一致：元数据 40/101，内容复算 40/100」。

## 3. 设计（两个取舍）

1. **不加 `--check-meta-consistency` 开关。** 加开关 = 再造一个可以被跳过、忘记
   跑的步骤，而默认闸门依旧失明——历轮批评的「恒绿防护」的另一种外衣。校验补进
   既有入口后，每个入口都独立成立，不依赖「另一步也配了」。
2. **不写「totals 与 per_workflow 求和对账」。** 两块都钉到同一次内容复算后，
   求和对账永远不会唯一决定任何事：能构造出的差异都会被更强的内容漂移先抓到。
   写成判据就是一条走不到的死判据。替代它的是构造保证 + 一条不变量用例：
   `recompute_totals` = `_totals_of(recompute_per_workflow(...))`，由
   `test_content_counting_has_one_rule` 钉住（含「坏 run 文件被两边同样跳过」）。

其余规则：

- 另一块**缺失**不是矛盾：跳过、退出码不变。但 `evaluate` / `check_sample_size`
  的说明必须写明「本次未做分组交叉校验」——否则读者会以为两块都校验了。
- `totals.runs` 仍不校验：没有判据消费它；`live_snapshot_exceeds` 的 `runs`
  3 vs 120 是合成的，抬它只会给重导加一个没人读的失败点。
- 退出码仍由各判据自己的「无样本 3」措辞决定，共用校验器只报形状（4）与漂移（4）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +148 / −80（2283 行） | 生产：`_totals_of`、两个块校验器、六处接线 |
| `tests/test_live_snapshot_gate.py` | +183 / −11（3334 行） | 新增 14 条（8 个函数，含 3 组参数化） |
| `tests/fixtures/live_snapshot/snapshot-meta.json` | +43 / −1 | 重导产物（history 第 3 轮） |
| `docs/JUDGEMENT_LEDGER.md` | +56 / −1 | §7.9、§5 码 4、§6 三行 |
| `docs/PROJECT_INFO.md` | +1 行 | R82 轮次条目 |
| `docs/HANDOVER_ROUND82.md` | 新增 | 本文 |

md5（工作树）：闸门 `1d3d1834…`、测试 `5aaf7e66…`、快照元数据 `b36631c4…`；
闸门改动前的逐字节副本 `_r82_gate_orig.py` = `8e13df17…`（§2 的「旧」列由它产出）。

## 5. 变异验证（十次，`cp` 快照还原）

相关用例集 = `tests/test_live_snapshot_gate.py` 的 R82 新用例。**每条都确认输出是
failed，不是 skipped**（R71 的教训）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | `evaluate` 不再校验 per_workflow | **1 failed / 2** | `moved_failure…[evaluate]`（参数化内唯一） |
| 2 | `check_sample_size` 不再校验 per_workflow | **1 failed / 2** | `moved_failure…[check_sample_size]` |
| 3 | `check_per_workflow` 不再校验 totals | **1 failed / 4** | `lying_totals…[check_per_workflow]` |
| 4 | `check_per_workflow_rate` 不再校验 totals | **1 failed / 4** | 同上 `[rate]` |
| 5 | `check_per_workflow_regression` 不再校验 totals | **1 failed / 4** | 同上 `[regression]` |
| 6 | `check_lead_time` 不再校验 totals | **1 failed / 4** | 同上 `[lead_time]` |
| 7 | 缺失的 per_workflow 块被抬成 4 | **2 failed** | 两条反方向用例同时咬住（向错方向的假红） |
| 8 | `recompute_totals` 退回第二份计数 | **3 failed** | 不变量用例**不唯一**（与两条元数据一致性用例一起红） |
| 9 | totals 只校验形状、不校验内容 | **4 failed** | 一个放松、四条判据同时失守（共享校验器） |
| 10 | totals 漂移文案不点名块 | **4 failed** | 四条用例都断言消息含 `totals` |

`cp` 快照还原后 md5 逐字节相同（`1d3d1834…`）。**如实记录**：M8 的不变量用例
不可能唯一咬合——`recompute_totals` 已经是 `_totals_of(recompute_per_workflow)`
的一行 wrapper，它的价值在防止未来重新引入第二份计数实现。

**本轮踩到的坑（写下来给下一轮）**：第一版变异脚本把「改动前的备份」当还原源，
跑完第一轮 `finally` 就把工作树里的 R82 改动整体写回旧版（`8e13df17…`）。
修法 = **启动时先快照当前文件**（`_r82_gate_snapshot.py`），还原只认这份快照。
这再次验证 R55 的纪律：还原源必须是「改动后的当前文件」，不是「改动前的备份」。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：闸门 + 翻转点 + 登记页 + CI 接线 | **272 passed**（7.86s） |
| 全量（Low，venv `S-1-16-4096`） | **2302 passed / 113 skipped / 0 failed**（143.41s） |
| 全量（High，`C:\Program Files\Python314\python.exe` + venv site-packages 绝对 `PYTHONPATH`） | **2387 passed / 28 skipped / 0 failed**（160.02s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm build | 未跑（生产代码只动闸门脚本；CI 会跑 e2e 与 container-build） |

**总用例 2401 → 2415（+14）**：Low `2302 + 113` = 2415；High `2387 + 28` = 2415。
High 的跑法与 R81 不同：`C:\Windows\py.exe`（3.14.8）**没有**项目依赖，会 137 个
collection error；改用同一份 C: 解释器 `C:\Program Files\Python314\python.exe`，
把 venv 的 `site-packages`（以及 `win32` / `win32/lib` / `Pythonwin` 与
`pywin32_system32` 的 PATH）放进 `PYTHONPATH`，28 skips 与 2387 passed 全绿。

## 7. 重导快照（用户拍定本轮执行）

命令 `python scripts/export_run_samples.py --dest tests/fixtures/live_snapshot
--limit 5`。结果：**28 个 run / 255 次尝试 / 10 失败 / 3.92%**，与 R60 逐字相同；
28 个 run 文件**逐字节不变**，只有 `snapshot-meta.json` 变化（+43/−1）：
`exported_at` `2026-10-30T09:26:54+00:00` → **`2026-11-01T06:23:56+00:00`**，
`history` 2 → **3 轮**（新轮计数逐字相同）。

重导后本地全链 12 条（venv CLI）：

| 步骤 | 退出码 | 关键数字 |
|---|---|---|
| `--fail-if-above 8` | 0 | 3.92%（n=255, 失败 10），区间 [2.14%, 6.56%] |
| `--fail-if-above 1` | 1 | 区间整个在 1% 之上 |
| `--fail-on-regression --regression-margin 3` | 0 | 基线 + 3 = 6.92%（历史上一轮） |
| `--check-per-workflow-regression --margin 10` | 0 | 9 个里 2 个可判，0 回归 |
| `--calibrate-lead-time --margin 10 --regression-margin 3` | 0 | character 提前 2 次 / mvp 5 次 |
| `--check-sample-size` | 0 | 半宽 2.64 ≤ 10 |
| `--check-sample-size --margin 2` | **7** | 2.64 > 2（CI 反向验证仍有判定力） |
| `--check-per-workflow` | 0 | 2 个精度达标 / 7 个不达标（诊断） |
| `--check-per-workflow-rate` | 0 | 0 超出 / 1 正常 / 8 样本不足 |
| 同上 `--fail-on-exceeds` | 0 | 无超出 |
| `--check-stale` | 0 | 滞后 **−4.2 天** ≤ 7 |
| `--check-coverage` | 0 | 9/9 |

`live_snapshot_exceeds` 反向验证：政策 8% → 1、合并回归 → 1、逐 wf 回归 → 1、
失败率硬门槛 → 1；逐 wf 报告与提前量 → 0。新增的 per_workflow 交叉校验没有改变
任何一条（该 fixture 的 two blocks 自洽）。

**预期可见变化（不判失败，需如实记录）**：同一批 run 导了三次，R58 的「连续轮」
提示现在生效——`--check-per-workflow-rate` 的输出会出现「连续 3 轮以上样本不足」
（build / export / mvp / outline / polish / post-hoc / reader-sim / story-plan
共 8 个，各「连续 3 轮」）。退出码仍是 0；它不是质量结论，是「这批数据支撑不了
逐 workflow 判决」的时间维度提示。`tests/test_live_snapshot_gate.py` 的
`_committed_two_rounds` 由 `len(rounds) == 2` 改为 `>= 2`（提前量表仍取最后两轮，
2 / 5 不变），并写明原因。

## 8. 未做与未验证的事（如实记录）

1. **没有把 `totals.runs` 纳入校验**：没有判据消费它；`live_snapshot_exceeds`
   的 3 vs 120 是合成的，本轮不动。
2. **没有做「求和对账」判据**：理由见 §3-2；如果将来有人重新引入第二份计数实现，
   应由不变量用例而不是一条新判据来挡。
3. **没有改 `data/workflows`**：仍 40 个 run，最新 `2026-10-28 08:34`；本次重导
   只是把同一批 run 再导一次。
4. **没有跑前端 / e2e / docker build**：生产与前端零改动（闸门脚本不是服务路径）。
5. **没有追「`F:` 上的可执行文件为什么被降到 Low」**（R81 §8-3 挂账）：本轮
   High 跑法改用 C: 解释器绕开该问题，没有推进根因。
6. **High 跑法与本轮之前不同**：`C:\Windows\py.exe` 缺依赖（137 个 collection
   error），改用 `C:\Program Files\Python314\python.exe` + venv site-packages。
   R81 记的 `py.exe` 处方在**本机今天**不成立，需要在下一轮复核（§9-3）。
7. **探针 / 变异脚本未入库**（`_r82_probe.py` / `_r82_mutate.py` /
   `_r82_gate_orig.py` / `_r82_gate_snapshot.py`）：按 R81 拍定，Windows-only
   的取证脚本不入库。

## 9. 下一轮候选

1. **`F:` → Low 的策略来源**（R81 §9-1，仍挂账）：决定 R81 处方在别的机器上是否
   成立；本轮的 High 跑法绕过了它，但没有回答它。
2. **`totals.runs` 与 run 数的口径**（新发现）：导出脚本写 `totals.runs`，但没有
   任何判据消费它，`live_snapshot_exceeds` 的 3 vs 120 说明它可以长期与内容不符。
   要么删掉这个字段，要么给它一个判据——但不能维持「写了没人看」。
3. **High 启动器处方的复核**：R81 写的是 `C:\Windows\py.exe` + 绝对 `PYTHONPATH`，
   本机今天实测缺依赖（137 个 collection error），有效的是
   `C:\Program Files\Python314\python.exe` + venv site-packages。把处方改成实测
   有效的那一个（并写清 `win32` / `pywin32_system32` 的附加路径）。
4. **CI 回写历史**：仍不推荐（R81 §7 的代价表未变）。
5. **`p=1.0` 真实数据**：继续挂账；本轮重导后快照仍是 10/255。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 10. 提交、推送与 CI 核对

两次提交（`422972a` fix + `e48970b` docs，显式路径 add）后推送
`4475fc2..e48970b`。推送通道：全局 socks5 10808 已失效
（`schannel: failed to receive handshake`）；`git -c http.proxy= -c https.proxy=`
第一次 `Connection was reset`、第二次成功（与 R58/R61 同一条纪律：先探路，别照抄
上一轮的通道）。

CI run **41281752270**（push，06:40:12 → 06:45:04，约 4m52s）五 job 全 `success`：

| 项 | 实证（下载日志解码后逐字比对） |
|---|---|
| 五个 job | backend（06:40:15–06:42:49）/ windows-backend（06:40:15–06:45:04）/ frontend（06:40:15–06:41:26）/ container-config（06:40:15–06:40:21）/ container-build（06:40:15–06:40:51）全部 `success` |
| ubuntu | `2350 passed, 65 skipped, 1 warning in 112.92s` = **2415** |
| windows | `2386 passed, 29 skipped, 1 warning in 224.56s` = **2415** |
| 计数与 R81 相比 | ubuntu 2336/65 → **2350/65**、windows 2372/29 → **2386/29**（各 **+14**，与本轮新增用例数一致） |
| 快照判据 | backend 第 7 步 fixture 自检 + 第 8–14 步七个真实快照判据全 `success`（政策 8%→0 / 1%→1、回归→0、逐 wf 回归→0、提前量→0、样本量→0、逐 wf 报告→0、失败率硬门槛→0；exceeds fixture 的三条反向验证在输出里各退 1）；windows 第 7–11 步同 |
| 新行为在 CI 真跑 | 第 14 步输出含「快照历史 3 轮（含当前）。连续 3 轮以上样本不足：…」共 8 个 workflow，退出 0——重导的预期可见变化在 CI 上逐字复现 |
| e2e / metrics | `[e2e] 10/10 场景通过`；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| e2e 趋势（R78 步骤） | backend 第 **17** 步 `e2e retry trend (history, read-only)` `success` |
| 前端 / 容器 | 前端 8 块 TAP `# pass` 求和 **490 / fail 0**；`容器镜像冒烟全部通过: determinflow-core:ci`；`docker compose config -q` 成功 |
| Desktop Windows / macOS | 未触发（该 SHA 下只有 CI 一个 run） |

`$GITHUB_STEP_SUMMARY` 正文 API 不提供（与 R74 §7-2 / R80 §9 同一条限制）；CI 上能
核到的是「这一批步骤都以 0 退出」。


补记提交 `6168d05`（纯文档）的 run **41282279612**（06:48:17 → 约 06:53）
同样五 job 全 `success`：ubuntu **2350/65**（114.29s）、windows **2386/29**
（253.69s）、前端 TAP 求和 490 / 0，与上一个 run 逐项相同。文档提交本身仍会
触发 CI，回填链到此为止（与 R66/R77/R78/R79/R80/R81 同）。