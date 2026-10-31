# DeterminFlow (xs2) 交接报告 — Round 67（提前量命令化：R62 的「同一把尺」是错的，两层阈值差 7 个百分点是必需的）

> 本轮定位：R66 §9-3「R62 提前量固化成可复核命令」（挂账 4 轮：R62 §10-6 起的
> 直接后续），顺带关闭 R65 §9-5 的一半（登记页的数字要有可复算口径）。
> 基线 `1f7420e`（R66 收尾：Low 2157/113/0、High 2242/28/0（权威）、
> 总用例 2270、前端 490/0）。落地形态：**主线 = 提前量命令化**；
> **范围 = 主线 + 登记页 + ci.yml 一行校准步骤**；**收尾 = 照常推送 + 五 job 逐字核对**。

## 1. 一句话结论

`--calibrate-lead-time` 把 R62 §2 那张手算的「提前 2 次 / 5 次」变成了判据自己的
算术，复算结果与 R62 逐字相同（2 / 5）。**但它顺带证明 R62 那句「与合并层同一把尺」
是错的**：逐 workflow 层用 `--margin`（10）、合并层用 `--regression-margin`（3），
差 7 个百分点。这 7 个百分点不是疏忽，而是「计数不变 ⇒ normal」的充要条件——
把它压到 3，两个可判的 workflow 会从「没有回归」整批变成「判不了」。

## 2. 最重要的发现：共享一个参数是「不变量」的充要条件

`_baseline_verdict(attempts, failed, baseline_attempts, baseline_failed, margin_pct)`
用**一个** `margin_pct` 同时回答两个问题：

1. 「基线够不够准」（精度门槛，经 `_failure_rate_precision`）；
2. 「变化够不够大」（阈值 = 基线失败率 + `margin_pct`）。

R62 的注释把这写成「同一把尺，只是把总体换成单个 workflow」。**后半句漏了关键
的一半**：合并层的 `margin_pct` 是 `REGRESSION_MARGIN = 3`，逐 workflow 层的是
`--margin = 10`。所以「提前 2 次」是**跨阈值**量出来的。

为什么不能统一成 3：可判条件保证基线的 95% 上界 ≤ 基线 + 余量；两轮计数相同时
当前区间与基线区间**逐位相同**，于是

```
upper(基线) ≤ 基线 + 余量  ⟺  阈值 ≥ 基线自身的 95% 上界
                           ⟺  计数不变时能判 normal
```

入库快照上：

| workflow | 基线 | 95% 上界 | 阈值（+3） | 阈值（+10） | 计数不变时（+3 / +10） |
|---|---|---|---|---|---|
| character | 2/79（2.53%） | **7.75%** | 5.53% | 12.53% | **undetermined** / normal |
| mvp | 4/56（7.14%） | **14.2%** | 10.14% | 17.14% | **undetermined** / normal |

**所以两个量必须相同**：共享参数不是省一个参数，而是这条不变量的充要条件。

## 3. 取舍的量化（同一份快照、同一个函数）

| 配置 | character 首次开口 | mvp 首次开口 | 提前量 | 计数不变时的判决 |
|---|---|---|---|---|
| 增量 10（默认） | 16/79（20.25%） | 15/56（26.79%） | **2 / 5 次** | **normal** |
| 增量 3（反事实） | 9/79（11.39%） | 11/56（19.64%） | 9 / 9 次 | undetermined |

压到 3 换来 4.5 倍 / 1.8 倍的提前，代价是**这一层在真实数据上永远说不出 normal**
（不是「更严」，是少了一个判决）。默认不压，但这个反事实现在是命令输出的一部分，
不是文档里的一句推断。

## 4. 设计

1. **新纯函数 `lead_time_report(previous, current, precision_margin, per_workflow_delta, merged_delta)`**：
   只调 `_rate_verdict` / `_failure_rate_precision`（即 `_cp_interval` +
   `_verdict_of_interval` + `sample_size_margin_needed`），不写第二份公式。口径固定
   「同样长的样本」：attempts 不变，只扫失败次数 k，找两条判据各自第一次判
   `exceeds` 的 k。覆盖变化（只在一边出现）、`attempts=0`、整段都够不着阈值
   （`None`）都单独标记，不给哨兵值。
2. **新模式 `--calibrate-lead-time`**：只读，**不作判定**（没有任何输入让它退出 1），
   无样本给 3、元数据漂移给 4、算术失败给 8——沿闸门自己的退出码词汇。正文第一行
   就写「退出 0 只表示算出来了」。
3. **`check_per_workflow_regression` 的汇总行**：把两层阈值都写出来（原来只有
   `margin=` 一个数），并注明「提前量用 `--calibrate-lead-time` 复算」。只写一个数
   会让读日志的人以为两层同样严格。
4. **CLI 拒绝 `--check-per-workflow-regression --regression-margin`**：逐 workflow
   层的阈值必须等于 `--margin`，放开这个开关就是允许一个说不出 normal 的判据上线。
   报错文案直接指向 `_baseline_verdict` 的不变量。
5. **ci.yml 加一步 ubuntu-only 的校准**（`Snapshot per-workflow lead-time calibration`）：
   参数与两个真判据同参（`--margin 10` / `--regression-margin 3`），由用例钉住同参关系。
   只在 ubuntu 跑的理由：它不作判定、算术与平台无关，两个 runner 的共同覆盖由
   pytest 的不变量用例承担。

## 5. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | **+331 / −10** | `lead_time_report` / `check_lead_time` / CLI / 三处 docstring 更正 |
| `tests/test_live_snapshot_gate.py` | **+168 / −0** | 163 条（原 154）：9 条新用例 + `_live_gate_step` 排除校准步 |
| `.github/workflows/ci.yml` | **+19 / −0** | 新增校准步骤（ubuntu） |
| `docs/JUDGEMENT_LEDGER.md` | **+42 / −3** | 新增 §4「提前量：两层不是同一把尺」，§5/§6 顺延；#3 行的容忍量改成可复算口径 |
| `config/skills_config.json` | 未入库的运行时写入（B23/R36 定性），照例排除 | 排除 |

## 6. 变异验证（三次全部咬合，`cp` 备份还原）

| 变异 | 期望 | 实测 |
|---|---|---|
| `_baseline_verdict` 的阈值换成 `margin_pct / 3` | 「计数不变 ⇒ normal」不变量必须掉 | **3 failed**（`only_judges_baselines_with_enough_precision`、`fires_on_a_thick_workflow_jump`、`unchanged_counts_are_normal...`） |
| `lead_time_report` 的逐 workflow 首红改用 `merged_delta_pct` | 提前量表与命令正文必须掉 | **2 failed**（`reproduces_the_r62_table`、`mode_says_it_is_not_a_judgement`） |
| 无历史时返回 `EXIT_OK` 而不是 3 | 「算不了 ≠ 算出来」用例必须掉 | **1 failed**（`without_history_exits_three`） |
| 还原后 | 全绿 | **163 passed**；`md5 39d890d8…` 与备份逐字节相同 |

还原用 `cp` 备份覆写，不用 `git checkout --`（R55 教训）。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2166 passed / 113 skipped / 0 failed**（129.84s） |
| High-IL 全量（权威） | **2251 passed / 28 skipped / 0 failed**（148.61s） |
| 定向：`test_live_snapshot_gate.py` | **163 passed** |
| 定向：`test_ci_gate_wiring.py` + `test_judgement_ledger.py` + `test_ci_e2e_stub.py` | **67 passed** |
| e2e 全量 | 未跑（零 e2e 改动；R65 的 10/10 仍适用） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |

**对账**：总用例 **2270 → 2279**（+9，全部是 R67 新增）。四面：Low `2166+113` = 2279、
High `2251+28` = 2279。

## 8. 未做与未验证的事（如实记录）

1. **R60~R63 的重导仍被数据卡住**：`data/workflows/**/runs/run-*.json` 仍是 **40 个**，
   最新 `run-dfe789fd.json` 仍是 `2026-10-28 08:34`（本轮复查：比它新的 **0 个**）。
   提前量表因此仍是「自比自」的那一轮——它复算的是**判据的算术**，不是「有新增样本
   时的提前量」。
2. **`p=1.0` 真实数据验证**未做。补充观察：`tests/fixtures/live_snapshot_exceeds` 里
   `wf-bad` 已经是 **40/40 → 40/40**（p=1.0）并通过 CI 的 `-ne 1` 反向验证，
   所以「p=1.0 的**算术路径**」有合成覆盖；缺的是真实全失败快照，仍然没有。
3. **未跑 `docker build`**：本机仍无 docker/wsl；`container-build` 在 GHA 真构建。
4. **未跑 `npm run build` / `npm test`**：零前端改动。
5. **未重启 8021 服务**：改动是离线脚本 + CI 文案 + 文档，不涉运行时装配。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`、
   `.github/`（R66 只因为改了 `src/**` 才触发）。
7. **`--calibrate-lead-time` 只在 ubuntu 跑**：这是有意的非对称（见 §4-5），
   windows 那份的共同覆盖靠 pytest 的不变量用例，不是靠日志。

## 9. 下一轮候选

1. **形状场景失败时重跑一次**（R65 §8-9 / R66 §9-4）：仍未做，需要先定义
   「两次里几次算通过」。本轮 §3 的取舍表提供了一个模板——把「代价」写成
   同参反事实，而不是拍一个更松的容差。
2. **判据容忍量的「翻转点」验证**（R65 §9-5 的另一半）：登记页上的每个容忍量
   都应该能用「输入在边界两侧各挪一点，判决翻转」来钉住，而不只是「与代码常量
   相等」。形状判据的 0.05/0.30 可以直接这样做；百分点类的可以按 k 翻。
3. **有新 run 后再重导一次**（R60 §7-1 起的直接后续）：仍被数据卡住，本机已
   5 天没有新 run。
4. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
5. **收尾尾巴的可观测性**（R66 §9-6）：本轮顺带读了一遍 `SessionManager.shutdown()`
   （只读代码，未跑 shutdown 场景）——它会遍历 `self.sessions` 逐个 `async_save(force=True)`，而收尾中的 Session
   在 `detach_saved_runtime_session` 之前仍在册，所以 R66 §8-2 的取舍**没有**造成
   「进程退出丢会话」的窗口（与 R66 当时的表述相比，这一点可以收窄）。剩下的是
   「谁在等这段收尾」，优先级可降。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定，CI 不写回仓库）。

## 10. 推送与 CI 核对

（待推送后补记）
