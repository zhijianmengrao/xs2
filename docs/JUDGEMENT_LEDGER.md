# 判据全景登记（Judgement Ledger）

> 本文回答 R63 §9-2 挂账的问题：**「R63 的预算式能不能迁移到别的阈值」**。
> 结论先说：**不能直接迁移**——它只对「两个实测量的比值 ≥ r」且偏移同时加在
> 分子分母上这一种形态成立。下面把十八条判据逐条登记，并写明每条自己的容忍量、
> 可复算边界与盲区。
>
> 数字由 `tests/test_judgement_ledger.py` 与代码常量对齐；分类文字无法自动校验。

## 1. 分类依据：容忍量加在哪里

| 类别 | 判据形态 | 容忍量的量纲 | 典型盲区 | 预算怎么算 |
|---|---|---|---|---|
| **偏移型** | `实测 ≥ 配置 − tol` / `实测 ≤ 配置 + tol` | 与实测量同单位（秒、百分点） | 单段离群 vs 共模偏移；容差 ≥ 相邻差时分不出相邻项 | 就是 `tol` 本身，或由不等式解出 |
| **精度型** | `区间半宽 ≤ margin` | 百分点 | 样本太薄 → 判不了（不是不合格）；`p → 0/1` 两端退化 | 二项分布精确界（Clopper-Pearson） |
| **政策型** | `区间下界 > 上限` | 无（阈值即政策） | 看不出原因；与其它判据共用退出码 1 | 无预算，只有阈值 |
| **时钟型** | `滞后 ≤ N 天` | 天 | 依赖墙钟与「最新 run」的取法 | `N` 天 |
| **环境型** | `签名匹配 或 (模块 ∈ 已知集合 且 探针复现签名)` | 无（不是容忍量） | 真实缺陷带同一签名时会被吞；探针每进程只跑一次 | 无预算；只有「签名 + 集合」两个自变量 |

## 2. 逐条登记

| # | 判据 | 位置 | 类别 | 容忍量 | 可复算边界 | 盲区 | 码 |
|---|---|---|---|---|---|---|---|
| 1 | 真实失败率 vs 政策上限 | `check_live_snapshot_gate.py::evaluate`（`--fail-if-above 8`） | 政策型 | 8 个百分点 | 区间下界 > 8 才红 | 阈值是政策，不随数据变；下界宽度由样本量决定 | 1 |
| 2 | 历史基线回归 | 同上（`--fail-on-regression`） | 偏移型 | 3 个百分点（`REGRESSION_MARGIN`） | 当前 ≥ 基线 + 3 且下界 > 该值 | 一个 workflow 变坏会被其余摊薄（由 #3 补） | 1 |
| 3 | per-workflow 回归 | `check_per_workflow_regression` | 偏移型 | 10 个百分点（`--margin`，**必须同时是基线精度余量**） | 可判 + 计数不变 ⇒ `normal`；阈值 = 基线 + 10 | 阈值小于基线精度时说不出 `normal`（反事实见 §4）；基线太薄判不了；3/4 两条退出路径先于判决（§7.3，R73） | 1 |
| 4 | per-workflow 失败率（留一法） | `check_per_workflow_rate` | 偏移型 | margin 10 | 与其余 workflow 的合并基线比 | 默认恒退出 0，只有 `--fail-on-exceeds` 才判；3/4 两条退出路径先于判决（§7.2，R72） | 1 |
| 5 | 样本量厚度 | `check_sample_size`（`--check-sample-size`） | 精度型 | margin 10 个百分点 | 95% 半宽 ≤ margin | `p → 0/1` 用单侧界；`n ≤ 4` 有轻微反转（已豁免并钉住） | 7 |
| 6 | 快照新鲜度 | `check_stale`（`--check-stale`） | 时钟型 | 7 天（`--max-lag-days` 默认） | 滞后 ≤ 7.0 天 | 只读「最新 run 文件」，与内容质量无关 | 5 |
| 7 | 快照覆盖度 | `check_coverage`（`--check-coverage`） | 政策型 | 无 | 真实跑过的 workflow ⊆ 快照 | 只能判「漏了哪些」，判不了比例 | 6 |
| 8 | e2e 退避形状（两/三/四段） | `e2e_workflow_stub.py::_rising_shape_violations` | 偏移型（逐段、非对称） | 欠睡 0.05s / 超睡 0.30s（**每次尝试**）；判红重跑 1 次，任一次通过即通过（R68） | 容差 < 最小相邻配置差 0.4s（`judgeable`） | 容差 ≥ 相邻差时分不出「下标错一位」；容差内看不出来；**两次都判红才算红** | 1 |
| 9 | e2e 退避幅度（单点） | `scenario_retry_backoff_is_honoured` | 偏移型（差分） | 多出 ≥ 0.7s（配置 1.2s）；同样在重跑集合里（R68） | 两次运行相减，绕开固定开销 | 只判一个值，对形状失明 | 1 |
| 10 | 判据算术失败 | `_run_judgement`（六个派发分支） | 不是判据 | — | 捕获 `ArithmeticError` / `ValueError` | 只把「算不下去」与「判了不合格」分开 | 8 |
| 11 | msys 传输不可用 → skip | `tests/conftest.py::_msys_skip_applies`（`_git_transport_blocked_probe` + `pytest_runtest_makereport`） | 环境型 | 无 | 失败调用含 `NtCreateDirectoryObject` 签名，**或** 模块 ∈ 6 个传输模块且探针 clone 复现同一签名 | 真实缺陷若文本里带同签名会被误归因；探针每进程只跑一次；6 个模块内无签名的失败一律转 skip（见 §8） | — |
| 12 | 满窗时的写入身份 | `replay_ci_scenarios.py::_run_scenario`（`last_run_id`） | 环境型（身份，不是容忍量） | 无（精确相等） | `result.last_run_id == 本轮 run_id`；`rounds` 仍按 `min(before+delta, MAX_ROUNDS)` 断言并用 `rounds_clipped` 标注 | 窗口满后 `rounds` 恒定在窗口值（R112 起默认 80），`rounds_delta` 的 +1/+2 不可辨（窗口−1 轮的 +2 先被裁剪）；该断言不依赖窗口状态，但 `last_run_id` 由 writeback 自报（读同一 `origin/<branch>`），不是独立第二证据源 | 1 |
| 13 | 期望失败场景（永久拒绝） | `replay_ci_scenarios.py::Scenario` / `_run_scenario` | 环境型（身份 + 计数） | 无（精确相等） | exit=1、reason=`push-rejected`、rounds=基线、`last_run_id`=基线末条、`push_attempts=3`；输出必须出现 3 次 `simulated rejection` 与 3 次 `push 被拒（第`；失败沙箱必须「存在过 → 清理 → 不存在」 | 传输故障也能让 push 三次非零，不数钩子签名就会为错误的原因变绿；清理只覆盖期望失败场景，意外失败仍保留现场 | 1 |
| 14 | 全链 artifact 身份分离 | `replay_ci_scenarios.py`（fetch 场景）+ `replay_ci_writeback.py::--fetch-run-id` | 环境型（身份） | 无（精确相等） | artifact API 用 GitHub run id，历史写入用 `replay-ci-fetched-<sha>`；`result.last_run_id` 必须等于后者；输出含 `已下载 1 个文件` | 真实下载依赖 backend 同 run 上传 artifact（job 用 needs+success 门控）；缺 artifact 时 fetch 退 0、writeback 退 0（metrics-missing），必须由驱动的期望 `written` 判红 | 1 |
| 15 | 全链 metrics 内容指纹与语义（R107/R112/R113/R116/R119/R120/R121/R122/R126） | `replay_ci_writeback.py::_metrics_content` / `_metrics_semantics` + `replay_ci_scenarios.py` 的 fetch 场景 | 环境型（身份） | 无（精确相等） | 写回前打印计数行 `metrics 内容 total=… passed=… failed=… retried=… attempts=…`、逐场景语义行 `name=ok/retry/fail/尝试次数` 与 `metrics 首次失败`；全链场景断 `metrics 内容 total=10` 且 `metrics 语义` 出现；失败/重试形状用例断具体场景状态与 `first_failure`，并读沙箱历史确认逐项落库；R113 再覆盖全失败 / 0 场景 / 重试多次仍失败三种形状，0 场景打印 `（无场景）`；R116 把失败形状与拒绝/注入组合（被拒一次后成功、注入冲突后第三次成功），断言重试后计数与逐场景 `first_failure` 不被重算；R119 把同一组合搬进生产全链：CI 单独上传 `e2e-metrics-failure-shape` 夹具（4 场景 / 1 失败 / 1 重跑），`fetched-failure-shape-rejected` 与 `fetched-failure-shape-rejected-conflict` 断言计数仍为 `(4,3,1,1,5)`、`metrics 语义` 与 `first_failure` 原样出现；R120 补全链 0 场景：`fetched-empty` 与 `fetched-empty-rejected` 断言计数全 0、语义 `（无场景）`、不得出现 `metrics 首次失败`，拒绝重试后内容不变；R121 补全链全失败：`fetched-all-failed` 与 `fetched-all-failed-rejected` 断言 `(3,0,3,0,3)`、语义全 `fail` 与逐场景首次失败原样出现；R122 用同一组夹具走真实 replay 写回，再从沙箱 history 渲染趋势表，按列断言 `(4,1,1,25.0%,5)`、`(0,0,0,n/a,0)`、`(3,3,0,0.0%,3)`；R126 把失败形状夹具放进大预算链（`fetched-failure-shape-hook-at-8`，预算/注入 8、attempts=9），证明 9 次 push 的长链里 failed/retried/attempts 与逐场景 `first_failure` 不被重算 | 生产 artifact 的形状取值不钉死（e2e 可能真的重跑）；失败/重试形状由全链测试夹具提供——不伪造生产 artifact，避免把强制重跑写进历史污染趋势；夹具 artifact 单独命名，`e2e-history-writeback` 仍只读 `e2e-metrics`；计数行只证明「形状对」，语义行才证明「内容被读到」；生产形状的断言仍不证明来源对（M110）；0 场景是合法数据，空语义行与「指纹没打」不可区分（R113），全链也必须显式打印 `（无场景）`；全失败数据也是数据，`failed=3` 让「失败数被清零」显形；R122 只证明展示层消费正确，趋势表仍不判好坏 | 1 |
| 16 | 拒绝预算、注入时机与重试上限（R108/R112/R113/R114/R117/R124） | `replay_ci_writeback.py::_install_rejection_hook`（`--conflict-on-reject N` / `--attempts`）+ `rejected-hook-*` 场景 | 环境型（身份 + 计数） | 无（精确相等） | 钩子第 N 次拒绝时注入冲突轮：N=1 预算 3 全失败 / 预算 2 第三次成功；N=2 预算 3 仍耗尽 / 预算 2 成功；N=3 末次注入、无重试可消化（`reason=rebase-conflict`）；R113 补 N=4/5（attempts=4/5）：N=4 预算 4 全失败、N=4 预算 4 attempts=5 第五次成功、N=5 预算 5 全失败；R114 补预算 6 / N=6：中段注入（注入 3、后面还有 3 次拒绝，reason=`push-rejected`）与末次注入后第 7 次成功；`push 被拒（第` 与 `simulated rejection` 次数逐场景钉住；N 超预算、N<1 或 N 超 attempts 退 2；表不变量 `test_hook_scenarios_are_reachable_and_consistent` 逐场景校验注入点 ≤ 预算/attempts、成功失败的 reason 来源与计数；R117 全链补 `fetched-rejected-hook-at-6`（预算/注入 6、attempts 7），并由 `test_fetch_hook_scenarios_match_the_local_formula` 断言全链与本地同用一组代数关系；R124 补 N=7（预算/注入 7、attempts=7，七次全拒、末次注入）与 N=8/attempts=9（预算/注入 8，第 9 次成功），全链补 `fetched-rejected-hook-at-8`（同 N=8/attempts=9）——证明 N>6 与 attempts>7 没有隐含上限 | R105 的 `rejected-conflict`（writeback 前注入）第一次是非快进、到不了钩子，其预算阈值仍是 2；`--conflict` 与 `--conflict-on-reject` 互斥；**可达性是两个变量**：拒绝预算 ≥ N 只保证钩子会走到第 N 次，重试循环最多 push `attempts` 次；N 超 attempts 时注入同样永远不会发生（R113）；场景表不变量是「未来加 N 时不会写出不可达组合」的唯一守卫（R114） | 1 |
| 17 | 保留期可配置（R109；R112 默认 40→80） | `e2e_retry_history.py::max_rounds`（`XS2_MAX_ROUNDS`） | 环境型（配置） | 默认 80；范围 [3, 1000]；非法值告警退回 | record 裁剪/文案、writeback `window_full`/文案、驱动期望、冲突夹具、钩子注入都从同一读取点取窗口 | R112 用户拍板 40→80：39 条历史只覆盖约 1.5 天，40 格 ≈ 13 个工作轮；旧历史条目保留原值、不改写。非法值是「出声的默认」（`::warning::`），不是静默；按天滚动未实现 | — |
| 18 | 沙箱 GC 守卫（R110） | `replay_sandbox_gc.py::candidates` + `main` | 政策型（删除） | 默认 7 天；4 道守卫 | 直接子目录 + `replay-ci-writeback-` 前缀 + 非符号链接/junction + mtime 超龄；默认 dry-run，`--apply` 才删，删后 `exists()` 复核 | 只清本机/长期环境；runner 临时目录无需 GC；7 天是默认值，保留策略数值未拍板 | 0/1/2 |

## 3. R63 的预算式能迁移到哪

R63 的结论是解一个不等式得到的：

```
(b + c) / (a + c) ≥ r   ⟺   rho ≥ r + (r − 1) · (c / a)
```

它成立的前提有三条，缺一条就失效：

1. 判据形态是**两个实测量的比值 ≥ r**；
2. 偏移 `c` **同时**加在分子与分母上（共模），而不是只加在一侧；
3. 两个量同量纲、同量级（否则 `c/a` 与 `c/b` 不是同一个数）。

逐条对照：

| 判据 | 能否迁移 | 原因 |
|---|---|---|
| #9 幅度（差分型） | **不能** | 判的是差值 `extra ≥ 0.7`，没有比值可解 |
| #2 / #3 / #4（百分点） | **不能** | 容忍量就是 margin 本身（加性），不经过比值 |
| #5（精度型） | **不能** | 容忍量来自二项分布，不是加性偏移 |
| #8（R65 之后） | **不需要** | 判据已换成绝对容差，比值降为诊断行 |

**只有「比值型」判据能用这个式子**；形态不是比值时套上去，会得到一个与判据
无关的数。R64 已经付过一次学费：把共模预算 0.40s 当成单段预算写进文档，而单段
的真实预算是 `b/r − a = 0.133s`——紧三倍，CI 上真的因此红过一次。

R65 把这个教训反过来用：既然判据的最后形态是绝对容差，就把容差**显式写出来**
（0.05 / 0.30），而不是让它藏在「比值 ≥ 1.5」里被反推。前者能一眼核对，后者
要解不等式才知道自己有多少余量。

## 4. 提前量：两层不是同一把尺（R67）

R62 §2 报过「逐 workflow 层比合并层早 2 次 / 5 次失败开口」，并把两层写成
「同一把尺、只是总体不同」。**后半句是错的**（R67 更正）：两层判的是同一个
问题（变化够不够大），但阈值增量不同——

| 层 | 阈值 | 增量来源 | 入库快照上的具体值 |
|---|---|---|---|
| 逐 workflow | 基线 + 10 | `--margin`（同时是基线精度余量） | character 12.53% / mvp 17.14% |
| 合并层 | 基线 + 3 | `--regression-margin`（`REGRESSION_MARGIN`） | 6.92% |

差 7 个百分点不是随手取的，它是**「计数不变 ⇒ normal」的充要条件**：可判
（95% 半宽 ≤ 10）保证基线的 95% 上界 ≤ 基线 + 10；两轮计数相同时当前区间
与基线区间逐位相同，上界自然 ≤ 阈值。把增量压到 3 的结果不是「更严」，而是
**在没有变化时也说不出 normal**：character 的 95% 上界 7.75% 高于 5.53%、
mvp 的 14.2% 高于 10.14%，两个可判的 workflow 会整批从「没有回归」变成
「判不了」。

取舍的量化（同一份快照、同一个函数）：

| 配置 | character 首次开口 | mvp 首次开口 | 提前量 | 计数不变时的判决 |
|---|---|---|---|---|
| 增量 10（默认） | 16/79（20.25%） | 15/56（26.79%） | 2 / 5 次 | **normal** |
| 增量 3（反事实） | 9/79（11.39%） | 11/56（19.64%） | 9 / 9 次 | undetermined |

复算命令（CI 每次都会跑这一条，见 `ci.yml` 的 `Snapshot per-workflow
lead-time calibration`）：

```bash
python scripts/check_live_snapshot_gate.py --calibrate-lead-time \
  --margin 10 --regression-margin 3 --data-dir tests/fixtures/live_snapshot
```

它是**校准**不是判据：没有输入会让它退出 1，退出 0 只表示「算出来了」。

## 5. 退出码表

| 码 | 含义 | 处置 | 出现在哪些模式 |
|---|---|---|---|
| 0 | 通过 | — | 全部 |
| 1 | 判了，且不合格 | 查数据 / 查供应商 | 默认判定（政策上限、回归）、per-workflow 回归/失败率、e2e 编排行为 |
| 3 | 无样本 | 重导快照 / 重录历史 | 全部读快照的模式、e2e 重跑历史（缺失或为空） |
| 4 | 元数据漂移 | 重导快照 / 重录历史（内容变了没重导 / 形状无效 / 路径读不开 / 顶层不是对象 / **任一计数块与内容不一致**，含 `totals.runs`，R83；路径被占时先清理再重导） | 全部读快照的模式、e2e 重跑历史（读不懂 / 形状无效 / 计数矛盾） |
| 5 | 快照过期 | 重导快照 | 仅 `--check-stale` |
| 6 | 覆盖度缺口 | 重导快照 | 仅 `--check-coverage` |
| 7 | 样本太薄 | 攒更多 run 再导 | 仅 `--check-sample-size` |
| 8 | 判据算术失败，**未作判定** | 修判据 | 全部判据模式（`_run_judgement` 统一套用）；e2e 重跑历史**不适用**（所有失败都是数据问题） |

**1 与 8 必须分开**：1 是「有结论」，8 是「没有结论」。共用退出码时，读日志的
人会把一次崩溃读成「失败率突破政策」，两种处置（查数据 / 修判据）互相冒充。

**e2e 重跑历史（R78）刻意没有 8**：它只校验数据有效性，没有可失败的判据算术。
坏历史是 4（重录/修文件）、没有历史是 3（先跑一轮）、计数矛盾是 4——留一个
走不到的 8，只会让读日志的人去查一个没坏的判据。

## 6. 这一页上的数由谁复核

| 数字 | 钉住它的地方 |
|---|---|
| 0/1/3/4/5/6/7/8 的**字面值** | `tests/test_judgement_ledger.py::test_ledger_pins_every_exit_code_value`（与脚本常量逐字对齐） |
| 1 与 8 不能共用 | `tests/test_live_snapshot_gate.py::test_numeric_failure_has_its_own_exit_code` |
| 3 个百分点（回归余量） | `tests/test_judgement_ledger.py::test_ledger_pins_the_regression_margin` + `REGRESSION_MARGIN` |
| 0.05 / 0.30 / 0.4（e2e 形状） | `tests/test_judgement_ledger.py::test_ledger_pins_the_e2e_shape_tolerances`、`tests/test_ci_e2e_stub.py::test_segment_budget_pins_the_two_tolerances` |
| 10 个百分点（margin 默认） | `--margin` 的默认值（脚本内 10.0），CI 六步显式或隐式使用 |
| 12.53 / 17.14 / 6.92（§4 的两层阈值） | `tests/test_live_snapshot_gate.py::test_lead_time_prints_the_two_thresholds_not_one` |
| §4 的 16 / 15 / 18 / 20 / 提前 2 / 5 | `tests/test_live_snapshot_gate.py::test_lead_time_reproduces_the_r62_table` |
| §4 反事实的 9 / 11 / 提前 9 | `tests/test_live_snapshot_gate.py::test_lowering_the_workflow_delta_kills_the_normal_voice` |
| 「可判 + 计数不变 ⇒ normal」 | `tests/test_live_snapshot_gate.py::test_unchanged_counts_are_normal_for_every_eligible_workflow` |
| e2e 重跑口径（最多 2 次 / 任一次通过即通过 / 只对计时型，R68） | `tests/test_ci_e2e_stub.py::test_retry_policy_covers_exactly_the_timing_scenarios`、`test_run_with_retries_stops_at_the_attempt_cap`、`test_run_with_retries_never_retries_a_semantic_scenario` |
| 7 天（新鲜度） | `--max-lag-days` 的默认值 + `tests/test_judgement_flip_points.py::test_freshness_flips_within_one_microsecond`（7 天 ±1 微秒） |
| 留一法基线（#4） | `tests/test_judgement_flip_points.py::test_leave_one_out_baseline_drives_the_flip_point`（从计数出发算基线，再判翻转） |
| #4 的 3/4 两条退出路径先于判决（R72） | `tests/test_judgement_flip_points.py::test_leave_one_out_flip_point_through_the_real_gate`、`test_metadata_drift_preempts_the_leave_one_out_verdict`、`test_no_sample_preempts_the_leave_one_out_verdict` |
| #3 的 3/4 两条退出路径先于判决（R73） | `tests/test_judgement_flip_points.py::test_per_workflow_regression_flip_point_through_the_real_gate`、`test_metadata_drift_preempts_the_per_workflow_regression_verdict`、`test_no_sample_preempts_the_per_workflow_regression_verdict` |
| 样本量诊断的 3/4 两条退出路径先于报告（R76） | `tests/test_judgement_flip_points.py::test_metadata_drift_preempts_the_per_workflow_sample_report`、`test_no_sample_preempts_the_per_workflow_sample_report` |
| 畸形 `per_workflow` → 4（不是 1/8，R75） | `tests/test_live_snapshot_gate.py::test_malformed_per_workflow_metadata_is_drift_not_a_verdict`、`test_malformed_metadata_exits_four_from_the_cli` |
| 坏 JSON 的处置：4（不是 1/3/8，R77） | `tests/test_judgement_flip_points.py::test_unparseable_metadata_is_not_a_verdict_for_the_leave_one_out_rate`、`test_unparseable_metadata_is_not_a_verdict_for_the_per_workflow_regression`、`tests/test_live_snapshot_gate.py::test_unparseable_metadata_exits_four_from_the_cli` |
| 元数据路径读不开（目录 / 权限）→ 4（不是 3，R79） | `tests/test_live_snapshot_gate.py::test_meta_path_that_is_a_directory_is_drift_not_no_sample`、`test_unreadable_meta_file_is_drift_not_missing`、`test_directory_meta_exits_four_from_the_cli` |
| 元数据缺失仍是 3（反方向，R79） | `tests/test_live_snapshot_gate.py::test_missing_meta_is_still_no_sample_for_every_judge` |
| 元数据顶层不是对象 → 4（不是 1，R79） | `tests/test_live_snapshot_gate.py::test_meta_that_is_not_a_json_object_is_drift` |
| 八处判据只走一道元数据门（R79） | `tests/test_live_snapshot_gate.py::test_every_judge_reads_the_metadata_through_one_door` |
| 畸形 `totals` → 4（不是 1/8/0，R80） | `tests/test_live_snapshot_gate.py::test_malformed_totals_is_drift_not_a_verdict`、`test_malformed_totals_exits_four_from_the_cli` |
| 空 `totals` 仍是 3（反方向，R80） | `tests/test_live_snapshot_gate.py::test_empty_totals_is_still_no_sample_not_drift` |
| 非对象 `per_workflow` 块 → 4（不是 3/1，R80） | `tests/test_live_snapshot_gate.py::test_non_object_per_workflow_block_is_drift_not_no_sample` |
| 历史畸形逐条列出且**不进退出码**（R80） | `tests/test_live_snapshot_gate.py::test_four_history_readers_report_the_same_note`、`test_malformed_history_does_not_change_the_regression_verdict` |
| 计数形状规则只写一份（R80） | `tests/test_live_snapshot_gate.py::test_count_shape_rules_are_written_once` |
| 另一块元数据与内容不一致 → 4（R82） | `tests/test_live_snapshot_gate.py::test_moved_failure_is_drift_for_every_totals_reader`、`test_lying_totals_is_drift_for_every_per_workflow_reader`、`test_contradicting_blocks_exit_four_from_the_cli` |
| 另一块**缺失**不是矛盾、但必须写明（R82） | `tests/test_live_snapshot_gate.py::test_absent_per_workflow_block_is_reported_not_judged`、`test_sample_size_without_per_workflow_block_says_no_cross_check`、`test_absent_totals_block_is_not_a_contradiction` |
| 两份内容复算同口径（R82） | `tests/test_live_snapshot_gate.py::test_content_counting_has_one_rule` |
| `totals.runs` 单独说谎 → 4（六个入口，R83） | `tests/test_live_snapshot_gate.py::test_total_runs_drift_is_drift_for_every_reader`、`test_total_runs_drift_exits_four_from_the_cli` |
| 旧格式缺 `totals.runs` → 4（不是静默，R83） | `tests/test_live_snapshot_gate.py::test_totals_without_runs_is_incomplete_not_silent` |
| 漂移文案写全三计数（R83） | `tests/test_live_snapshot_gate.py::test_totals_drift_message_names_all_three_counts` |
| `totals.runs` 的形状规则（R83） | `tests/test_live_snapshot_gate.py::test_malformed_totals_is_drift_not_a_verdict`（runs 的 `true`/浮点/字符串/负数四格） |
| 展示字段不参与判决（两处 `failure_rate`，R84） | `tests/test_live_snapshot_gate.py::test_failure_rate_is_display_only`、`test_display_only_registry_is_structurally_excluded` |
| 展示字段不参与判决（顶层 `source_root`，R86） | `tests/test_live_snapshot_gate.py::test_source_root_is_display_only`、`test_display_only_registry_is_structurally_excluded` |
| n≥29 全失败样本（R87） | `tests/test_live_snapshot_gate.py::test_n29_all_failed_sample_passes_the_margin`、`test_n28_all_failed_sample_is_the_flip_point`、`test_manufactured_all_failed_fixture_is_a_real_export`、`test_manufactured_fixtures_differ_by_exactly_one_run` |
| CI 回写历史的写权限/执行面分离（R88） | `tests/test_ci_history_writeback.py::test_write_permission_belongs_only_to_the_writeback_job`、`test_writeback_job_runs_no_repository_tests`、`test_writeback_uses_run_id_not_run_attempt` |
| 写回重试语义由**行为**驱动、YAML 只委托（R89） | `tests/test_ci_history_writeback.py::test_writeback_delegates_retry_to_the_script` + `tests/test_ci_writeback_history.py::test_rejected_push_rebases_and_succeeds_on_the_second_attempt`、`test_permanent_rejection_stops_after_the_attempt_cap` |
| 同一 run 重跑且观测一致 → **不产生提交**（R89） | `tests/test_e2e_retry_history.py::test_record_keeps_the_first_export_time_when_the_observation_is_identical`、`tests/test_ci_writeback_history.py::test_same_run_rerun_does_not_create_a_second_commit` |
| 写回冲突 → 重算（R90） | `tests/test_ci_writeback_history.py::test_rebase_conflict_recomputes_instead_of_losing_the_round`、`test_conflict_stops_after_the_attempt_cap` |
| 写回结果类别 + summary（R91） | `tests/test_ci_writeback_history.py::test_summary_records_missing_metrics_and_record_invalid_separately`、`test_result_categories_are_distinct_literals` |
| PR 预检只读（R92） | `tests/test_e2e_retry_history.py::test_record_check_only_does_not_write`、`tests/test_ci_history_writeback.py::test_backend_prechecks_metrics_on_pull_requests` |
| 条目来源 `source`（R93） | `tests/test_e2e_retry_history.py::test_record_writes_the_source`、`test_validate_history_rejects_unknown_source`、`test_check_reports_the_source_mix` |
| 本地回放不碰源仓库（R94） | `tests/test_ci_writeback_history.py::test_dry_run_does_not_touch_the_repo`、`tests/test_replay_ci_writeback.py::test_replay_leaves_the_source_repo_untouched` |
| p=1.0 真实数据（R84） | `tests/test_live_snapshot_gate.py::test_all_failed_fixture_is_a_real_export`、`test_all_failed_fixture_uses_the_all_failed_closed_form`、`test_real_all_failed_snapshot_is_thin_and_says_why`、`test_real_all_failed_snapshot_exceeds_the_policy_ceiling` |
| e2e 重跑历史的窗口 **80 轮**（R78；R89 20→40；R112 40→80） | `scripts/e2e_retry_history.py::MAX_ROUNDS` + `tests/test_e2e_retry_history.py::test_record_trims_to_the_window`（值 + 边界行为两条一起钉） |
| 同一 `run_id` 覆盖而非追加（R78） | `tests/test_e2e_retry_history.py::test_record_replaces_the_same_run_id_instead_of_appending` |
| 「1 次重跑 = 10 个百分点」是**算出来的**（R78） | `test_check_computes_the_resolution_from_the_latest_total`（20 个场景时必须是 5 个百分点） |
| 「本步不判趋势」必须写进输出（R78） | `test_check_says_it_has_no_judgement_power` |
| 失败数必须显示在趋势表（R115） | `tests/test_e2e_retry_history.py::test_check_shows_failed_scenarios_in_the_trend_table` |
| 0 场景 ≠ 空历史（R115） | `tests/test_e2e_retry_history.py::test_check_distinguishes_zero_scenarios_from_an_empty_history` |
| 坏历史 → 4（不是 3/1/8，R78） | `test_check_exits_four_on_unparseable_history_not_eight`、`test_check_exits_four_on_contradictory_counts`、`test_check_exits_four_on_duplicate_run_ids` |
| 跳过坏条目继续渲染会被咬住（R78） | `test_check_rejects_bad_json_even_when_one_entry_would_render` |
| CI 只读校验**入库的**历史（R78） | `tests/test_e2e_retry_history.py::test_ci_checks_the_committed_history_file` |
| 本页「不能直接迁移」的答案 | `tests/test_judgement_ledger.py::test_ledger_answers_the_r63_migration_question` |
| msys 归因「机制 + 处方」两半、但不钉「本令牌是 Low」（R71/R81） | `tests/test_msys_attribution.py::test_skip_reason_names_the_mechanism_and_the_actionable_fix` |
| 「签名 / 模块 / 探针」真值表（R71） | `tests/test_msys_attribution.py::test_skip_truth_table_has_exactly_two_independent_variables` |
| 「无签名 ≠ 环境问题」（R71） | `tests/test_msys_attribution.py::test_probe_flips_on_the_msys_signature_only` |
| 允许转 skip 的 6 个模块（R71） | `tests/test_msys_attribution.py::test_skip_surface_is_exactly_the_six_transport_modules` |
| 归因用例的失败不被吞（R71） | `tests/test_msys_attribution.py::test_attribution_failures_are_never_converted_into_skips` |
| 113 skips 的四行实测矩阵（R70 §6.1） | 本页 §8：High 2189/113 与**真降** Low 2189/113 逐字相同 |

| 全链 metrics 内容指纹与语义（R107/R112/R113/R116/R119/R120/R121/R122） | `tests/test_replay_ci_writeback.py::test_replay_reports_the_metrics_content`、`test_replay_reports_the_fetched_metrics_content`、`test_replay_reports_the_metrics_semantics`、`test_replay_fetch_chain_carries_failure_and_retry_semantics`、`test_replay_fetch_chain_carries_failure_shapes`、`test_failure_shape_survives_retries`、`test_trend_table_consumes_the_replayed_shapes`、`tests/test_replay_ci_scenarios.py::test_local_metrics_shape_is_deliberately_different`、`test_fetch_failure_shape_scenarios_pin_content_and_retry`、`test_fetch_empty_shape_scenarios_pin_zero_counts`、`test_fetch_all_failed_shape_scenarios_pin_failed_counts`、`test_driver_runs_the_fetch_chain_end_to_end`、`tests/test_ci_replay_wiring.py::test_backend_uploads_the_failure_shape_fixture_for_full_chain`、`test_backend_uploads_the_empty_shape_fixture_for_full_chain`、`test_backend_uploads_the_all_failed_shape_fixture_for_full_chain`、`test_writeback_job_does_not_consume_the_replay_fixture` |
| 预算、注入时机与重试上限（R108/R112/R113/R114） | `tests/test_replay_ci_writeback.py::test_replay_hook_injects_conflict_on_first_rejection`、`test_replay_rejection_budget_two_is_a_real_boundary`、`test_replay_hook_injects_conflict_on_the_second_rejection`、`test_replay_rejects_an_unreachable_injection_point`、`test_replay_rejects_an_injection_point_beyond_the_attempt_budget`、`test_replay_hook_injects_conflict_on_the_fourth_rejection`、`test_replay_succeeds_on_the_fifth_attempt_after_late_injection`、`tests/test_replay_ci_scenarios.py::test_scenario_table_pins_the_replay_counts`、`test_hook_scenarios_are_reachable_and_consistent`、`test_fetch_hook_scenarios_match_the_local_formula` |
| `XS2_MAX_ROUNDS` 默认/范围/告警（R109） | `tests/test_e2e_retry_history.py::test_max_rounds_env_override_and_invalid`、`test_record_uses_the_configured_window`、`tests/test_ci_writeback_history.py::test_writeback_window_follows_env`、`tests/test_replay_ci_scenarios.py::test_driver_uses_the_configured_window` |
| 满窗实战：默认窗口 80 的 rounds/last_run_id 双证据（R125） | `tests/test_replay_ci_scenarios.py::test_driver_keeps_witnesses_at_the_default_window` |
| 写回幂等在回放链路成立（R127） | `tests/test_replay_ci_writeback.py::test_replay_same_run_id_rerun_is_a_no_change`、`test_replay_missing_metrics_file_reports_metrics_missing` |
| 语义指纹截断只影响展示（R128） | `tests/test_replay_ci_writeback.py::test_semantics_line_truncates_display_but_not_the_record` |
| e2e step summary 的坏形状只可见、不判死（R130） | `tests/test_e2e_retry_summary.py::test_malformed_scenarios_are_visible_and_not_fatal`、`test_malformed_counts_are_visible_and_not_fatal`、`test_render_raises_the_shape_error_instead_of_a_partial_table`、`test_render_escapes_pipes_and_newlines_in_table_cells`、`test_unparseable_payload_is_visible_and_not_fatal`、`test_non_object_payload_is_visible_and_not_fatal`、`test_usage_requires_exactly_one_path` |
| CI 报告层：summary 单行、写失败只告警（R131） | `tests/test_ci_reporting.py::test_summary_appends_one_exact_bullet`、`test_summary_flattens_newlines_in_every_field`、`test_result_keeps_the_raw_multiline_detail`、`test_summary_write_failure_only_warns`、`test_summary_encoding_failure_only_warns`、`test_result_writes_exact_bytes_and_replaces_atomically`、`test_result_write_failure_only_warns_and_leaves_no_tmp`、`test_result_encoding_failure_only_warns_and_leaves_no_tmp`、`test_result_serialization_failure_only_warns`、`test_default_summary_path_reads_the_ci_environment`、`test_none_paths_are_no_ops` |
| 发版验收：判决不依赖 assert、四类退出码（R132） | `tests/test_verify_release.py::test_optimized_mode_still_rejects_a_bad_sha256`、`test_sha256_mismatch_fails`、`test_keynum_mismatch_fails`、`test_invalid_signature_fails`、`test_empty_sha256_asset_is_shape`、`test_bad_outer_base64_is_shape`、`test_sig_blob_length_is_shape`、`test_comment_line_is_required`、`test_manifest_missing_platform_is_shape`、`test_missing_asset_is_environment`、`test_network_failure_is_environment` |
| 沙箱 GC 四道守卫与默认 dry-run（R110） | `tests/test_replay_sandbox_gc.py::test_dry_run_lists_only_old_matching_directories`、`test_apply_removes_only_the_candidates`、`test_symlink_with_matching_name_is_skipped`、`test_negative_age_is_a_usage_error`、`test_missing_root_is_a_usage_error` |

## 7. 翻转点（R69）

「数字等于常量」不等于「数字是判决的边界」：把阈值写成 `基线 + margin * 2` 的
实现，常量仍然相同，边界却挪了一倍，而日志、文档、CI 文案全都对得上——只有
判决是错的。下面每个**带数字**的容忍量都有一条用例，在**边界内**与**边界外**
各构造一次输入，断言判决翻转；阈值一律取自代码常量（`REGRESSION_MARGIN`、
`DEFAULT_MARGIN`、`DEFAULT_MAX_LAG_DAYS`、`UNDER_SLEEP_TOLERANCE`、
`OVER_SLEEP_TOLERANCE`、`BACKOFF_EXTRA_MIN_SECONDS`），不写第二份字面量。

| # | 判据 | 边界内（通过 / 不判失败） | 边界外（判失败） | 用例 |
|---|---|---|---|---|
| 1 | 政策上限 8 个百分点 | n=255, k=28 | k=29 | `test_policy_ceiling_flips_between_28_and_29_failures` |
| 2 | 合并层回归 +3 | 基线 10/255, k=25 | k=26 | `test_merged_regression_margin_flips_at_26_failures` |
| 3 | 逐 workflow +10 | character 15/79 | 16/79 | `test_per_workflow_regression_margin_flips_at_the_registered_k`、`test_per_workflow_regression_flip_point_through_the_real_gate`、`test_metadata_drift_preempts_the_per_workflow_regression_verdict`、`test_no_sample_preempts_the_per_workflow_regression_verdict`（后三条是退出路径的前提，见 §7.3） |
| 4 | 留一法 +10 | 基线 0/30, k=3/10 | 4/10 | `test_leave_one_out_margin_flips_at_four_failures`、`test_leave_one_out_baseline_drives_the_flip_point`、`test_leave_one_out_flip_point_through_the_real_gate`、`test_metadata_drift_preempts_the_leave_one_out_verdict`、`test_no_sample_preempts_the_leave_one_out_verdict`（后三条是退出路径的前提，见 §7.2） |
| 5 | 样本量 margin 10 | 零失败 29 次尝试 | 28 次 | `test_sample_size_margin_flips_between_28_and_29_attempts` |
| 6 | 新鲜度 7 天 | 滞后 7.0 天 | 7.1 天 | `test_freshness_flips_at_the_registered_days`、`test_freshness_default_is_the_registered_days`、`test_freshness_flips_within_one_microsecond` |
| 8 | 形状 −0.05 / +0.30 | −0.050 / +0.300 | −0.051 / +0.301 | `test_shape_tolerances_flip_on_both_sides` |
| 9 | 幅度 0.7s | extra 0.700s | 0.699s | `test_backoff_amplitude_flips_at_the_registered_minimum` |
| 17 | 窗口 8 轮 | 写满 8 轮仍在窗口（首条 r0） | 第 9 轮挤掉最早一轮（首条 r1） | `test_configured_window_flips_between_the_last_kept_and_first_dropped_round` |
| 18 | GC 年龄 7 天 | mtime 恰好 7 天（含等号）是候选 | 年轻 1ms 不是候选 | `test_sandbox_gc_age_flips_at_the_registered_days` |

#7（覆盖度）、#10（判据算术失败）与 #11（环境归因）没有数字容忍量：#7 判的是
集合关系，#10 不是判据而是「算不下去」的分流，#11 判的是**系统签名字符串是否
出现**——边界不是数，是三格真值表（§8）。覆盖守卫
`test_every_numeric_tolerance_has_a_registered_flip_point` 保证「登记页出现数字」
与「登记了翻转点」互为充要。

三个**没有**被翻转点覆盖的量，如实写在这里：

- **2.64 个百分点**（入库快照的 95% 半宽）是**测量结果**，不是容忍量；
- **0.4s**（形状的相邻配置差）由场景配置决定，`RisingShapeSegmentBudget.judgeable`
  已把它写成不等式；
- **3 次**（连续 `undetermined` 的提示阈值）不改变任何退出码，不是判据。

### 7.1 边界的两种「不是常量」（R70）

§7 的每一行钉的都是「阈值 = 登记的这个数」。但那句话有两种不成立的方式，而
R69 的用例只挡住了第一种的一半：

| 缺口 | 改法 | R69 的用例看得见吗 | R70 的补丁 |
|---|---|---|---|
| **基线不是常量** | 留一法基线换成「含自己的全局合计」（R56 修掉的自指错误），或给留一法单独乘 2 | 看不见：`_rate_verdict` 收到的 `baseline_pct` 是测试里写死的 `0.0` | `test_leave_one_out_baseline_drives_the_flip_point` 从 `{workflow: (attempts, failed)}` 出发，走 `per_workflow_baselines` → `per_workflow_rate_report` 全程 |
| **时间算术的粒度** | `total_seconds() / 86400` 改成 `.days` 或四舍五入到 0.1 天 | 看不见：整点时间戳下「7.0 天」恰好可表示 | `test_freshness_flips_within_one_microsecond` 用 7 天 ±1 微秒 |

两条的共同点：**常量一个都没动、比较符也是对的**，错的是「那个数是怎么来的」。
翻转点只能证明「比较里用的是这个阈值」；阈值本身若是另一个量的函数，还得把那个
量一起钉进来——否则「防止有人换一套阈值」这句话没有依据（R69 §2 的同型教训）。

留一法那条尤其要连起来看：基线**不随 target 自己的失败数变化**（`0/30` 在 k=3 与
k=4 时逐位相同），才是 k=4 还能翻得过去的原因；换回全局合计，基线自己从 7.5%
涨到 10%，阈值跟着涨到 20%，40% 的观测就再也说不出口了。

§7 的用例登记从 R70 起是**多条**：覆盖守卫要求 `_FLIP_POINT_TESTS` 里每一个
用例名都必须真实存在且出现在本页，未登记的翻转点用例同样算不通过。

### 7.2 翻转点的前提：3/4 两条退出路径（R72）

§7.1 钉的是「阈值怎么算出来」；这一节钉的是**那个数能不能被走到**。
`check_per_workflow_rate` 在判决之前有两道门：元数据漂移（退出 4）与无样本
（退出 3）。R56 的用例各测过这两道门，但它们与 #4 的翻转点**用的不是同一组
计数**，于是两种改法能在既有用例上全绿：

- 「只有判不出 `exceeds` 时才查漂移」——真实失败（内容 k=4）被一句元数据
  改写成「判不了」，退出码从 4 变成 1；
- 「元数据里有数就拿来判」——内容为空的快照按元数据说出「超出」。

R72 用 #4 的同一组计数（rest 30/0、target 4/10——正是 §7 第 4 行的边界外）
把门与翻转点绑在一起，且走真实入口（落盘快照 → `snapshot-meta.json` → 漂移
校验 → 报告 → 退出码）：

| 前提 | 同一组计数下的期望 | 用例 |
|---|---|---|
| 内容与元数据一致 | rest 30/0 + target 10/3 → 不判失败；10/4 → 硬门槛退出 1、报告模式退出 0 | `test_leave_one_out_flip_point_through_the_real_gate` |
| 元数据漂移先于判决 | 内容 target 4/10，元数据把一次失败挪给 rest（全局合计 40/4 不变）→ 退出 4，消息不含「超出」 | `test_metadata_drift_preempts_the_leave_one_out_verdict` |
| 无样本先于判决 | 缺元数据文件 / 缺 `per_workflow` 块 / 元数据说有但内容为空 → 退出 3，消息不含「超出」 | `test_no_sample_preempts_the_leave_one_out_verdict` |

「缺 `per_workflow` 块」这一分支与 R56 的用例重复，不声称唯一覆盖；新增量是
另外两条分支与「判决词不得先出现」这条顺序断言。

### 7.3 回归判据的前提：3/4 退出路径（R73）

与 §7.2 同一形状，换到 #3：`check_per_workflow_regression` 在判决之前也先过
元数据漂移（退出 4）与无样本（退出 3）两道门。R62 的用例各测过这两道门，
但它们的计数在 #3 的阈值下判不出 `exceeds`，于是「只有判不出回归时才查漂移」
能让一个内容为 16/79（会判回归）的快照被元数据改写成 15/79 后静默通过。

| 前提 | 同一组计数下的期望 | 用例 |
|---|---|---|
| 内容与元数据一致 | character 上一轮 2/79，当前 15/79 → 不判回归；16/79 → 退出 1（来源写明 character） | `test_per_workflow_regression_flip_point_through_the_real_gate` |
| 元数据漂移先于判决 | 内容 16/79，元数据写 15/79 → 退出 4，消息不含「判回归」/「退出码 1」 | `test_metadata_drift_preempts_the_per_workflow_regression_verdict` |
| 无样本先于判决 | 缺元数据文件 / 缺 `per_workflow` 块 / 元数据说有但内容为空 → 退出 3，消息不含判决词 | `test_no_sample_preempts_the_per_workflow_regression_verdict` |

「缺 `per_workflow` 块」这一分支与 R62 的用例重复，不声称唯一覆盖；新增量是
「缺元数据文件」「内容为空」两条分支与顺序断言。

### 7.4 样本量诊断的前提：3/4 退出路径（R76）

与 §7.2/§7.3 同一形状，换到 `check_per_workflow`。它**不是判据，是诊断**
（§2 没有它的行）：R54 定下它只有两件事能红——元数据漂移（退出 4）与无样本
（退出 3），薄只进报告、恒退出 0。所以这里没有「判决词」，要钉的是报告词
**「达标 / 不达标」**不得出现在退出 4/3 的消息里。

R54 的用例为什么挡不住：它测漂移用的是 10/1 + 10/1（两条都需约 29.4 个百分点
> margin，报告说不出「达标」），于是「只有发现薄样本时才查漂移」在它面前全绿
——一份**全厚**快照（日常最常见的形状）配上说谎的元数据会静默通过；它也没有
任何一条检查消息里有没有报告词。

| 前提 | 同一组计数下的期望 | 用例 |
|---|---|---|
| 内容与元数据一致 | wf-thin 5/0（需 45.07）+ wf-thick 30/0（需 9.50）→ 退出 0，报告同时说「达标」与「不达标」 | `test_metadata_drift_preempts_the_per_workflow_sample_report` |
| 元数据漂移先于报告 | 同一份内容，元数据把 wf-thick 写成失败 1 次 → 退出 4，消息不含「达标」；**全厚**快照（30/0 ×2）同样退出 4 | 同上 |
| 元数据不是合法 JSON | 同一份内容 + `{not json` → 退出 4（不是 3，也不是带着报告出来的 0） | 同上 |
| 无样本先于报告 | 缺元数据文件 / 缺 `per_workflow` 块 / 元数据说有但内容为空 → 退出 3，消息不含「达标」 | `test_no_sample_preempts_the_per_workflow_sample_report` |

新增量是「缺元数据文件」「坏 JSON」「全厚快照的漂移」三格与顺序断言；「缺块」
「内容为空」两条分支与 R54 重复，不声称唯一覆盖。

### 7.5 元数据不是 JSON：同一道门的另一格（R77）

§7.2/§7.3/§7.4 把「退出 4 / 退出 3」这两道门接到了判决与报告上，但它们造的
元数据**全是合法 JSON**——坏也只坏形状（R75 §9 的 `"junk"` / `"abc"` / `true`
/ `-2`）。于是 `json.loads` 抛异常这条分支在三条判据上都没有用例（R76 §7-3
挂的账），而两种改法在既有 2328 条上全绿：

- **读不懂就按内容重算**：`except ValueError` 里换成
  `meta = {"per_workflow": recompute_per_workflow(...)}`，一份真实快照照样判出
  「超出 / 判回归」——元数据问题（处置是重导）被翻译成「判了且不合格」；
- **读不懂当空元数据继续**：退出码从 4 变成 3（「没有数据可判」），回归那条
  还会把「上一轮基线丢了」说成「只有当前这一轮」（退出 0）。

坏 JSON 属于退出 4 这道门（处置与漂移相同），不是第三个退出码。要钉的是
**同一组边界外计数**：先证明元数据可读时它确实说话，再把元数据换成
`{not json` 看它闭嘴。

| 前提 | 同一组计数下的期望 | 用例 |
|---|---|---|
| #4 坏 JSON 先于判决 | rest 30/0 + target 4/10（硬门槛下退出 1）→ 换成 `{not json` 后退出 4，消息含「无法解析」、不含「超出」「报告模式」；**报告模式同样退出 4** | `test_unparseable_metadata_is_not_a_verdict_for_the_leave_one_out_rate` |
| #3 坏 JSON 先于判决 | 上一轮 2/79、当前 16/79（会判回归）→ 换成 `{not json` 后退出 4，消息不含「判回归」「退出码 1」 | `test_unparseable_metadata_is_not_a_verdict_for_the_per_workflow_regression` |
| CLI 外部退出码 | 两条判据的 `--check-per-workflow-rate` / `--check-per-workflow-regression` 都以 **4** 退出，不是 8 | `test_unparseable_metadata_exits_four_from_the_cli` |

**8 是这一格最容易冒充的码**：`_run_judgement` 把 `ValueError` 归成「判据算术
失败」，而 `json.JSONDecodeError` 正是 `ValueError` 的子类——判据里那条
`except` 一旦被删，进程就从 4 变成 8，人按 8 去查判据算术，处置全歪。

**如实记录覆盖关系**：函数级用例与 CLI 用例在 M1–M5 上**同时判红**，CLI 不是
唯一咬合者；两条函数级用例各自的唯一咬合只有「退出码不变、消息里先写出判决词」
那两次变异（M6/M7）。CLI 用例的价值是把**外部退出码**也钉住，而不是多发现
一种改法。

### 7.6 趋势判据不判趋势：先钉「数据有效」（R78）

R74 让单次 run 的重跑频率可机读，跨 run 那一层缺存储与判据。R78 的形态是：
**本机显式 `record`、随被判数据入库（快照式）、CI 只读 `check`**（不改
`permissions: contents: read`）。这里有一个必须写清楚的选择：**趋势不判红**。

原因是判据自己的算术，不是保守：

- e2e 只有 **10 个场景**，`retried/total` 的取值只能是 0、10、20…100 个百分点。
  阈值因此只能落在「第 k 次重跑」上：任何小于 10pp 的余量都会被**一次**重跑
  越过（0 → 10pp），而「小幅变差」在 10 个场景的格点上根本不存在——这就是
  R63 §3「小量级被判据自己的量级压成单点窗口」的同一条算术。
- 于是 `check` 的 **0 退出只表示「历史可读」**，输出必须逐字写出「不判趋势
  好坏」与当前分辨率（`100 / 最近一轮 total`，是算出来的量，不是写死的 10）。
  退出码里**没有 1 和 8**：所有失败都是数据问题。

| 情形 | 退出码 | 处置 | 用例 |
|---|---|---|---|
| 历史可读 | 0（**不是**「趋势合格」） | 继续攒轮次 | `test_check_says_it_has_no_judgement_power` |
| 没有历史 / 历史为空 | 3 | 先跑一轮 e2e 并 record | `test_check_exits_three_without_a_history_file`、`test_check_exits_three_for_an_empty_history` |
| 读不懂 / 形状无效 / 计数矛盾 / `run_id` 重复 | 4 | 重录或修文件 | `test_check_exits_four_on_unparseable_history_not_eight` 等 |
| 判据算术失败 | **不适用** | — | 没有可失败的算术，不设 8 |

**最隐蔽的一种改法是「跳过坏条目继续渲染」**：剩下的好条目会让趋势表看起来
完整，「0 次重跑」与真实数据一模一样（R74 对 summary 的同一条批评）。因此
`validate_history` 对整份文件校验，不做逐条过滤；
`test_check_rejects_bad_json_even_when_one_entry_would_render` 专门咬这一口。

**轮次去重**：条目带 `run_id`（默认取入库时间戳），同一 id 重复 `record` 是
**覆盖**而不是追加——否则修一次数据就会在趋势里凭空多出一轮。窗口 20 轮，
第 21 轮写入时最早一轮掉出（`test_record_trims_to_the_window`）。

**如实记录这一层的覆盖范围**：CI 每次 push 都跑 e2e，但**不入库**——入库是
本机显式动作。所以趋势的轮次密度取决于「本机跑 e2e 并提交」的频率，不是
push 频率；CI 的职责只有「入库的那份历史仍然可读」。

### 7.7 元数据路径读不开：4 不是 3（R79）

§7.2–§7.5 造的元数据**全都读得开**（合法 JSON，坏也只坏形状）；§7.5 钉的是
「读得开但读不懂」。剩下的一格是**打不开**。R77 §7-1 把「把 `snapshot-meta.json`
写成目录」当成同一条 `except (OSError, ValueError)` 的另一种注入方式，**实测
不成立**：旧写法先 `meta_path.is_file()`，目录在那一步就是 `False`，八处判据
一起以 **3**（无样本）退出。

| 状况 | 修复前 | 冒充的东西 | 修复后 |
|---|---|---|---|
| `snapshot-meta.json` 是目录 | 八处判据全部 **3**（`is_file()` 返回 False） | 「快照还没导出」→ 对着一个**已被占用的路径**反复重导，而重导只会再失败一次 | **4**（先清理该路径再重导） |
| 文件在、`read_text` 抛 `OSError`（权限拒绝） | 旧代码在 `except` 里会归 4，但 `is_file()` 在父目录 ACL 被拒时也返回 False → 3 | 同上 | **4** |
| 顶层是合法 JSON 但不是对象（`[]` / `"x"` / `null` / `42`） | 调用方 `meta.get(...)` 抛 `AttributeError` → CLI 退出 **1** | 「判了且不合格」→ 查供应商 | **4**（重导） |

修法是把八处判据的读取收进 `_load_snapshot_meta()`，**按异常类型分流**：
`FileNotFoundError` → 3（没有快照）；其它 `OSError` → 4（读不开）；`ValueError`
（`UnicodeDecodeError` 与 `json.JSONDecodeError` 都是它的子类）→ 4（读不懂）。

**为什么不 `is_dir()` 预检**：目录在 POSIX 上是 `IsADirectoryError`、在 Windows
上是 `PermissionError`（本机实测），预检等于把同一条判据写成两份平台相关代码，
而且它仍然看不见权限拒绝。`open()` 抛出的异常类型本来就是「为什么读不了」的
答案，也是唯一能区分「没有」与「坏了」的信息。

| 前提 | 期望 | 用例 |
|---|---|---|
| meta 路径是目录 | 八处判据全部 4；消息含「无法读取」「不是「没有样本」」「先清理该路径」，不含「缺失」 | `test_meta_path_that_is_a_directory_is_drift_not_no_sample` |
| meta 文件不存在 | 八处判据全部 3；消息含「缺失」、不含「无法读取」 | `test_missing_meta_is_still_no_sample_for_every_judge` |
| 文件在但 `read_text` 抛 `PermissionError` | 4（注入而非 `chmod`：Windows 的 `os.chmod` 只切只读位，读操作照样成功） | `test_unreadable_meta_file_is_drift_not_missing` |
| 顶层不是对象 | 4（不是 1/8） | `test_meta_that_is_not_a_json_object_is_drift` |
| 外部退出码 | 默认判定模式与 `--check-per-workflow-rate` 都以 4 退出 | `test_directory_meta_exits_four_from_the_cli` |
| 以后新增的判据 | 文件名只允许出现在 `_load_snapshot_meta`，不许自己拼路径再 `is_file()` | `test_every_judge_reads_the_metadata_through_one_door` |

**如实记录覆盖关系**：M1（`OSError`→3）、M2（缺失→4）、M8（退回 `is_file()`
预检）、M6（文案退回「缺失」口径）各自同时咬红 **8** 条参数化用例（八处判据
一起响），**没有唯一咬合者**；M4（去掉顶层对象校验）咬红 4 条；M5（只让
`check_lead_time` 绕过统一入口）咬红 2 条——该判据的目录参数 + 统一入口守卫，
**后者是唯一能守住「将来新增判据」的那条用例**。



### 7.8 畸形 totals 与逐条历史：4 与「只报告」（R80）

§7.5 收的是 `per_workflow` 块内的形状，§7.7 收的是读取路径。剩下的两块是
`totals`（`evaluate` / `check_sample_size` 读它）与 `history`（四处判据读它）。
**处置不同是有意的**：`totals` 是**当前**这一轮的计数，坏了就没有可判的数字；
`history` 描述的是**过去**的轮次，跳过它只会削弱连续性，不会把当前判决变成假话。

**`totals` → 4。** 旧写法 `int(recorded.get("attempts") or 0)` 实测有三种冒充
（本机 CLI，`_r80_probe.py` 原始输出）：

| 形状 | 修复前退出码 | 冒充的东西 | 修复后 |
|---|---|---|---|
| `totals: "junk"` | **1**（`AttributeError` 未捕获） | 「判了且不合格」→ 查供应商 | 4 |
| `{"attempts": "abc"}` | **8**（`_run_judgement` 归为算术失败） | 「判据崩了」→ 修判据 | 4 |
| `{"failed": true}`（内容 1 次失败） | **0**：`int(True)` 是 1，静默当成一次真实失败 | 「通过」——没有异常、没有 traceback | 4 |
| `{"attempts": 20.5}` | **0**：`int(20.5)` 截断成 20 | 「通过」 | 4 |

空值（缺失 / `null` / `{}` / `[]`）仍是 **3**：没有可被冒充的计数，本机「还没
导出过快照」是预期状态。容器与字段共用一个 `_count_block`，`per_workflow` 的
非空非对象（`"junk"`）也一并从 3 改成 4；`check_lead_time` 原本没走形状校验
（`"junk"` → 1、`"failed": "abc"` → 8），R80 顺带收进同一套。

**`history` 的畸形条目 → 只报告，不进退出码**（用户拍定）。旧输出只有
「另有 N 条历史形状无效已跳过」，读日志的人不知道该修哪一条；R80 起逐条给出
`第 N 条：原因`，四处（`evaluate` 的回归层 / `check_per_workflow_rate` /
`check_per_workflow_regression` / `check_lead_time`）共用 `_invalid_history_note`，
文案一致由构造保证。`history` 本身不是数组同样只报告（旧写法静默当作「没有历史」）。

| 前提 | 期望 | 用例 |
|---|---|---|
| `totals` 是 truthy 非对象 / 字段是 `"abc"` / `true` / 负数 / 浮点 / `null` | 两条判据都 4；消息含「totals 元数据形状无效」 | `test_malformed_totals_is_drift_not_a_verdict` |
| `totals` 是缺失 / `null` / `{}` / `[]` | 仍是 3（不是 4） | `test_empty_totals_is_still_no_sample_not_drift` |
| 外部退出码 | 默认判定与 `--check-sample-size` 都以 4 退出（不是 1/8） | `test_malformed_totals_exits_four_from_the_cli` |
| `per_workflow: "junk"` | 四条判据（含校准）都 4，不再是 3/1 | `test_non_object_per_workflow_block_is_drift_not_no_sample` |
| 历史条目的 `true` / `1.5` | 与 per_workflow/totals 同一规则：跳过并逐条报原因 | `test_history_entry_counts_use_the_same_shape_rules` |
| 四处读 history 的判据 | 同一句「另有 N 条…（第 N 条：…）」，退出码不受影响 | `test_four_history_readers_report_the_same_note` |
| 加坏历史前后 | 回归判决不变（仍 1） | `test_malformed_history_does_not_change_the_regression_verdict` |
| `history: "junk"` | 只报告「history 期望数组」 | `test_non_list_history_block_is_reported_not_silently_ignored` |
| 将来新增的计数校验 | 必须走 `_count_value_error`，不许手抄 | `test_count_shape_rules_are_written_once` |

**八次变异如实记录**：M1（删 `evaluate` 的 totals 校验）6 红、M2（删
`check_sample_size` 的）6 红——两者都只咬字段形状，容器由 `_count_block` 单独挡；
M3（布尔重新算 1）**3 红，三个族各一条**（共享校验器的直接后果：一处放松、
三处同时失守）；M4（逐条原因丢位置）9 红；M5（共用文案丢掉明细）5 红；
M6（容器退回 `{}`）6 红；M7（`history` 非数组静默忽略）**1 红，唯一咬合**；
M8（history 退回 `int()`）4 红，其中 `test_count_shape_rules_are_written_once`
是唯一守住「将来新增第四处」的那条。`cp` 还原后 md5 逐字节相同（`8e13df17…`）。

### 7.9 两块元数据：任何读计数的入口都校验整份工件（R82）

R80 §8-5 挂的账是「totals 只与内容复算比、per_workflow 只与内容复算比，两者的
**互相**一致性没有判据」。实测的缺口比这句话更具体：**默认判定
（`evaluate` / `--fail-if-above`，CI 第 8 步）根本不读 `per_workflow` 元数据。**
两个 workflow 各 10 次尝试、各 1 次失败，把 a 的一次失败改成 b 的：全局合计
`(20, 2)` 分毫不动，`evaluate` 退出 **0**，只有 `--check-per-workflow` 退 4。
反方向同样存在：四条 per-workflow 判据不读 totals，totals 说谎时它们照常判决。

**处理方式：不给新开关，六处各补「另一块」。** 加 `--check-meta-consistency`
等于再造一个可以被跳过、忘记跑的步骤，而默认闸门依旧失明——这正是历轮批评的
「恒绿防护」的另一种外衣。落地点是六个读计数的入口：

| 入口 | 本来读 | R82 起也校验 |
|---|---|---|
| `evaluate`（默认判定） | totals | per_workflow（形状 + 与内容漂移） |
| `check_sample_size` | totals | per_workflow（同上） |
| `check_per_workflow` | per_workflow | totals（形状 + 与内容漂移） |
| `check_per_workflow_rate` | per_workflow | totals（同上） |
| `check_per_workflow_regression` | per_workflow | totals（同上） |
| `check_lead_time` | per_workflow | totals（同上） |

**不写「totals 与 per_workflow 求和对账」。** 两块都被钉到**同一次**内容复算后，
求和对账永远不会唯一决定任何事：能构造出的差异都会被更强的内容漂移先抓到，它
会是一条走不到的死判据。替代它的是构造保证——`recompute_totals` 改成
`recompute_per_workflow` 的求和（`_totals_of`），全仓只有一份内容计数口径，并由
`test_content_counting_has_one_rule` 钉住「全局合计 = 分组求和」。

**缺失不是矛盾。** 另一块缺失（旧快照、手写 fixture）时跳过、退出码不变，但
`evaluate` / `check_sample_size` 的说明必须写明「本次未做分组交叉校验」——
否则读者会以为默认判定校验了两块。**R83 更正**：本段原先写的「`totals.runs`
仍不校验」已不成立——`runs` 现在与 attempts/failed 共用同一份 `_totals_key`，
见 §7.10。

| 前提 | 期望 | 用例 |
|---|---|---|
| per_workflow 挪一次失败（totals 不变） | `evaluate` / `check_sample_size` 都 4（原先是 0/7） | `test_moved_failure_is_drift_for_every_totals_reader` |
| totals 说谎（per_workflow 与内容都真） | 四条 per_workflow 判据都 4，消息含 `totals` | `test_lying_totals_is_drift_for_every_per_workflow_reader` |
| 外部退出码 | 默认 / `--check-sample-size` / `--check-per-workflow-rate` 都以 4 退出 | `test_contradicting_blocks_exit_four_from_the_cli` |
| 另一块缺失 | 退出码不变，说明含「未做分组交叉校验」 | `test_absent_per_workflow_block_is_reported_not_judged`、`test_sample_size_without_per_workflow_block_says_no_cross_check` |
| 缺失的 totals | 不是「说谎的 totals」，不判 4 | `test_absent_totals_block_is_not_a_contradiction` |
| 两份复算同口径 | 全局合计 = 分组求和（含坏 run 文件被同样跳过） | `test_content_counting_has_one_rule` |
| 入库快照 | 六个入口全绿 | `test_every_count_reader_passes_the_committed_snapshot` |

**十次变异如实记录**：M1（删 `evaluate` 的 per_workflow 检查）1 红 / 2 中唯一；
M2（删 `check_sample_size` 的）1 红 / 2 中唯一；M3–M6（依次删四条 per_workflow
判据的 totals 检查）各 **1 红 / 4 中唯一**；M7（缺失块抬成 4）2 红（向错方向的
假红被两条反方向用例同时咬住）；M8（`recompute_totals` 退回第二份计数）3 红——
不变量用例**不唯一**，它与两条元数据一致性用例一起红；M9（totals 只校验形状）
**4 红，一个放松、四条判据同时失守**（共享校验器的直接后果）；M10（漂移文案不
点名块）同样 4 红。`cp` 备份还原后 md5 逐字节相同（`1d3d1834…`）。

### 7.10 `totals.runs`：写了没人看的字段，钉进同一次内容复算（R83）

R82 §8-5 留下的账是口径问题：导出脚本（`export_run_samples.py`）一直写
`totals.runs = len(exported)`，但六个读计数的入口只信 attempts/failed——把
`runs` 改成任何数字，六个入口没有一条会说话。这不是「少一个校验」，而是
**入库工件里有一句没人读的话**：它可以长期与内容不符，直到某天有人拿它做判决。

两份入库 fixture 本身是自洽的（`live_snapshot` 28 run、`live_snapshot_exceeds`
3 run），所以这条缺口在既有用例上全绿——它只能由「只改 runs」的用例咬住。

**落点：不是新判据，而是把字段并入已有口径。**

- `_TOTALS_COUNT_FIELDS` 由 `("attempts", "failed")` 改为
  `("runs", "attempts", "failed")`；`_totals_of` 按这份字段表求和并返回
  `{runs, attempts, failed}`（原先是 2 元组），`recompute_totals` 同步改为返回
  该字典。
- 新增 `_totals_key(块) -> tuple[int, ...]`：元数据与内容复算用**同一把尺**
  比较。`evaluate`、`check_sample_size`、`_totals_block_error`（四条 per-workflow
  判据共用）三处都改成 `_totals_key(recorded) != _totals_key(actual)`。
- 漂移文案改为写全三个计数：`元数据 runs/attempts/failed=3/20/2，内容复算
  2/20/2`。只写 failed/attempts 时，仅 `runs` 说谎会打印出两个一模一样的
  「2/20」，读者看不出差在哪。
- **缺失按 0 计**：旧格式 totals 没有 `runs` → 与内容（通常 >0）不等 → 4。
  处置与漂移相同（重导），导出脚本会补上。这与 `per_workflow` 块内缺失字段
  的既有口径一致（`int(rec.get("runs") or 0)`）。

`totals.runs` 不单独写一条判据：它和 attempts/failed 是同一个块的三个计数，
分开写就会出现「这条判据信这个字段、那条信那个字段」的分裂（与 R82 拒绝
「求和对账」同一条理由）。

| 前提 | 期望 | 用例 |
|---|---|---|
| 只改 `totals.runs`（两块内容与 attempts/failed 全真） | 六个入口都 4 | `test_total_runs_drift_is_drift_for_every_reader` |
| 外部退出码 | 默认 / `--check-sample-size` 都以 4 退出 | `test_total_runs_drift_exits_four_from_the_cli` |
| 旧格式 totals 缺 `runs` | 4（按 0 比内容），不是静默通过 | `test_totals_without_runs_is_incomplete_not_silent` |
| 只差 `runs` 时的文案 | 写明 `runs/attempts/failed=` 与内容复算 | `test_totals_drift_message_names_all_three_counts` |
| `runs` 是 `true` / `20.5` / `"abc"` / `-1` | 4；消息含「totals 元数据形状无效」 | `test_malformed_totals_is_drift_not_a_verdict` |
| 两份内容复算同口径 | `recompute_totals == _totals_of(...)`，含 `runs` | `test_content_counting_has_one_rule` |
| 入库快照 | 三计数都与内容一致 | `test_snapshot_metadata_matches_its_content` |

**六次变异如实记录**：M1（`evaluate` 只比 attempts/failed）4 红，其中
`[evaluate]` 两条参数化用例唯一咬住本入口；M2（`check_sample_size` 同）3 红，
`[check_sample_size]` 唯一；M3（共享 `_totals_block_error` 只比两项）**8 红，
四条 per-workflow 判据各两条同时失守**（共享校验器的直接后果）；M4
（`_TOTALS_COUNT_FIELDS` 退回两项）21 红，是整轮的核心变异；M5（漂移文案不写
runs）**1 红，唯一咬合**；M6（形状校验漏掉 runs）4 红，恰好是新增的四个
`runs` 畸形格。全部输出都是 failed、没有 skipped（R71 的教训）。`cp` 快照还原
后 md5 逐字节相同（`19507a3d…`）。

**R84 处置（2026-11-01）：登记为只读展示字段，不删除、不做判据。**

`totals.failure_rate` 与 `per_workflow[*].failure_rate` 是导出脚本按 4 位小数
写给人看的派生值（`export_run_samples.py:262-265`、`:281-287`）。R84 把两处一起
登记进 `_DISPLAY_ONLY_FIELDS`（`scripts/check_live_snapshot_gate.py`），登记的
含义是**任何判决都不读它**：

- **不并入计数表**：`_count_value_error` 只接受整数/整数字符串，`0.0392` 会让
  每一份入库快照在形状校验处被判「形状无效」（4）；而要做成判据就得比「四舍五入
  后相等」——反正都是另一族脆弱算术（与 §7.3 记的「门槛随共模偏移漂移」同类）。
- **不删除**：它是读者要的信息（28 run / 255 次尝试 / 3.92%），删掉只是把
  「没人读」变成「不存在」，与 R83 对 `runs` 的处置理由相同。
- 守卫用例 `test_failure_rate_is_display_only` 参数化六个读计数入口 × 两个副本 ×
  六种值（`"abc"` / `true` / 浮点 / 合理的错值 0.99 / `null` / 整个删掉），断言
  `(退出码, 文案)` **逐字不变**——只比退出码抓不到「读了但只用在文案里」的入口。
- `test_display_only_registry_is_structurally_excluded` 钉住登记清单与两张计数表
  无交集：结构上碰不到，而不是靠注释承诺。

### 7.11 p=1.0 的真实数据：分支第一次由真实载荷走完（R84）

R53 修了「全部失败时 `p(1-p)=0` 让样本量判据恒绿」，但自 R54 起每一轮都挂着
「没有真实数据验证，只有构造样本」（`HANDOVER_ROUND53.md:375` 起）。

R84 查清了真实数据的形状：`data/workflows` 40 个 run 里有 **6 个
`failed == attempts`**（build 5 个 + export 1 个，全部是 1 次尝试 1 次失败，都是
供应商流式超时）。把它们导出成 `tests/fixtures/live_snapshot_all_failed/` 之后，
`p=1.0` 这条分支第一次由**真实载荷**走完 导出 → 元数据 → 闸门 全链：

| 量 | 真实值 | 说明 |
|---|---|---|
| 快照 | 6 run / 6 尝试 / 6 失败 / 100.00% | `source_root` = `workflows`（真实导出，不是 synthetic） |
| `sample_size_margin_needed(6, 6)` | **39.3038 个百分点** | 全失败闭式 `1 - 0.05**(1/n)`；正态近似在这里算成 0，会把「全挂」判成「样本足够」 |
| `--check-sample-size`（margin 10） | **7** | 文案含「全部失败时到 100% 的 95% 单侧距离 39.30 个百分点」「n=6」「约 29 次尝试」 |
| `evaluate --fail-if-above 8` | **1** | 95% 区间 `[60.70%, 100.00%]` 整个在 8% 之上，判超阈 |

| 前提 | 期望 | 用例 |
|---|---|---|
| 来源是真实导出、内容自洽 | 6/6，`source_root=workflows`，6 个 run 全 `status=failed` | `test_all_failed_fixture_is_a_real_export` |
| `p=1.0` 走全失败闭式 | 39.3038（与 `1-0.05**(1/6)` 一致） | `test_all_failed_fixture_uses_the_all_failed_closed_form` |
| 真实全失败快照的样本量判决 | 7，文案写全失败与 29 次 | `test_real_all_failed_snapshot_is_thin_and_says_why` |
| 真实全失败快照的政策判决 | 1，区间 `[60.70%, 100.00%]` | `test_real_all_failed_snapshot_exceeds_the_policy_ceiling` |

**仍未验证（如实记录）**：自然状态不会出现 n≥29 的全失败样本——本机有史以来
全失败 run 只有这 6 个，全部 1 次尝试。要让这份快照在 margin 10 下合格需要
**29 次全失败尝试**；为一条判据故意跑坏 29 次真实工作流，代价与污染都不值得。
所以这项挂账从「分支没有真实数据验证」改写成「分支已由真实数据验证；n≥29 的
自然样本不存在，这是数据事实而不是缺口」。

其余边界：fixture 只含 2 个 workflow，`--check-coverage` 对它退 6 属设计内
（它是分支钉子，不是覆盖率样本）；CI 不新增步骤，pytest 在 CI 里就会跑这条。

### 7.12 顶层 `source_root`：最后一个「写了没人看」字段（R86）

R84 §9-1 发现：导出脚本在顶层 meta 写 `source_root = workflows_dir.name`（`export_run_samples.py:278`），全仓库没有任何判据读它——与 `totals.runs`（R83）、`failure_rate`（R84）同族。

**处置：登记为只读展示字段**。`_DISPLAY_ONLY_FIELDS` 从 `("failure_rate",)` 扩成 `("failure_rate", "source_root")`。

- **不并入计数表**：它的值是目录名（`workflows` / 任意 `--dest` 的父目录名），`_count_value_error` 只接受整数/整数字符串。
- **不做成判据**：原 R84 §9-1 的另一选项是「合成快照不得进 CI 默认」。要判它必须先定义哪些 fixture 是 synthetic、哪条 CI 路径算「默认」；而 `source_root` 恰好只是「导出时源目录的名字」，换一个目录导出就会变，拿它当判据会把合法重导误判成合成快照。
- **不删除**：它是读者要的信息（快照来源），删掉只是把「没人读」变成「不存在」，与 R83/R84 的处置理由相同。

**守卫按位置分开写**：它只有一个副本、在顶层 meta，不是 `totals` / `per_workflow` 的副本。`test_source_root_is_display_only` 参数化六个读计数入口 × 六种值（`"abc"` / `true` / `3.7` / `0.99` / `null` / 整个删掉），断言 `(退出码, 文案)` 逐字不变——只比退出码抓不到「读了但只用在文案里」的入口。`test_display_only_registry_is_structurally_excluded` 的期望集合同步为两项，并继续钉住登记清单与两张计数表无交集。

**变异验证（两次）**：M1 从登记清单删掉 `source_root` → 结构用例 **1 red**；M2 让 `check_sample_size` 在 detail 里带上 `meta["source_root"]` → 六入口守卫 **6 red**（该入口 × 六种值），其余 30 条通过。`cp` 还原后 gate md5 逐字节相同（`5e0a070e…`）。

### 7.13 n≥29 全失败样本：主动制造（R87）

R84 §3.3 的结论是「n≥29 的自然全失败样本不存在」，并把它记为数据事实。用户在 R85 拍定改判为「主动制造」。本条记录制造方式、边界与两份 fixture。

**制造方式（真实执行，不是手写 JSON）**：复用 `scripts/e2e_workflow_stub.py` 的桩 provider + `Runtime` 装配，把 `DETERMINFLOW_DATA_DIR` 指到隔离目录（`F:\DeterminFlow x2\_r87_sample_data`，仓库 `data/` 只读），建一个首节点带 `[stub:fail]` 的工作流，真跑 **29 次**。每次 run 都由真实编排落一份 `run-*.json`：`status=failed`、节点 `error=stub induced failure`、`attempt_count=1`、无自动重试。桩 provider 是 e2e 已在用的那个（协议真实、不依赖供应商凭据）。

**为什么 n=29 是关键**：全失败时 Clopper-Pearson 单侧界到 100% 的距离是闭式 `1 - 0.05**(1/n)`。n=29 → **9.81pp < 10**（margin 10 下合格）；n=28 → **10.15pp > 10**（太薄）。所以 29 是这条判据在这个 margin 下的**最小合格样本量**，28 与 29 之间就是翻转点。

**两份 fixture**（同一批真实 run，只差一个）：

| fixture | 计数 | `--check-sample-size`（margin 10） | `evaluate --fail-if-above 8` | `--check-coverage` |
|---|---|---|---|---|
| `live_snapshot_all_failed_29` | 29 / 29 / 100% | **0**（9.81pp ≤ 10） | **1**（区间 [90.19%, 100.00%]） | 6（单 workflow，设计内） |
| `live_snapshot_all_failed_28` | 28 / 28 / 100% | **7**（10.15pp > 10，「约 29 次尝试」） | **1**（区间 [89.85%, 100.00%]） | 6（同上） |

**守卫**：`test_manufactured_all_failed_fixture_is_a_real_export` 两份都查「每个 run `status=failed`、计数与 meta 自洽」；`test_n29_all_failed_sample_passes_the_margin` 与 `test_n28_all_failed_sample_is_the_flip_point` 钉住翻转；`test_manufactured_fixtures_differ_by_exactly_one_run` 钉住「差异只能是一个 run」——否则翻转就不是样本量造成的；`test_n29_all_failed_snapshot_still_exceeds_the_policy_ceiling` 钉住「样本量合格 ≠ 政策合格」。两条既有 fixture 扫描（载荷 / 裁剪恒等）按目录自动发现，各多 2 个参数，无需改扫描逻辑。

**变异验证（两次）**：M1 把全失败闭式改成返回常量 `9.0` → 两条边界用例 **2 red**；M2 从 29 fixture 移走一个 run 文件（不改 meta）→ 真实性用例与 n29 样本量用例 **2 red**，还原后计数 29。

**边界（如实）**：fixture 只有 1 个 workflow，`--check-coverage` 退 6 是设计内；样本是按桩协议诱导的真实失败，不代表真实供应商的失败分布——它验证的是**样本量判据的边界算术**，不是供应商质量。

### 7.14 CI 回写 e2e 重跑历史：写权限与执行面分离（R88）

R78 的存储决策是「历史随被判数据入库（快照式），本机显式 `record` 后提交」；
R81 §7 评估了 CI 回写的代价表后结论是「不做」。R85 的用户拍定改为「做」。
R88 的落点是**独立 job**，不是给 backend 加一步，理由：写权限
（`contents: write`）与仓库测试的执行面不能重叠。

- **backend**：e2e 后上传 `e2e-metrics` artifact（`if: always() && push/main`，
  `if-no-files-found: warn`）。
- **`e2e-history-writeback`**：`needs: backend`、
  `if: always() && push/main && result != cancelled`、
  `permissions: contents: write`、`concurrency: e2e-history-writeback`
  （`cancel-in-progress: false`）。
- **步骤**：checkout（fetch-depth 0）→ download-artifact（`continue-on-error`）→
  `record --run-id ci-<github.run_id>`（metrics 缺失打印「本轮不入库」退出 0）→
  有 diff 才 commit（`[skip ci]`）→ push，每次被拒先 `pull --rebase`，最多 3 次。
- **幂等**：`run_id` 用 `github.run_id` 而非重试次数，重跑覆盖同一轮
  （R78 的「同 id 覆盖」契约）。
- **失败轮次也记录**：backend 断言失败时 metrics 仍存在（脚本在返回 1 前写出），
  写回 job 仍执行；环境起不来（退出码 3）没有 metrics，跳过。
- **语义变更**：R81 §7 说的「轮按导出轮推进」在这里变成「一次 main push 算一轮」；
  20 轮窗口在密集提交下会更快滚完。趋势仍不判好坏（R78），所以这个变化只影响
  「历史覆盖多长时间」，不影响判决。

守卫：`tests/test_ci_history_writeback.py` 的 9 条接线用例（写权限只在写回 job、
只 main push、写 job 不跑 pytest/e2e/npm/docker、artifact 同名、run_id 非
重试次数、串行化/`[skip ci]`、入库历史仍能通过 `validate_history`）。**R89 起
重试语义改由 `tests/test_ci_writeback_history.py` 用真实 git 仓驱动**（见 §7.15）。

边界：main 当前无分支保护；若将来加保护，bot 直推会失败——三次重试后以
`::error::` 显式报错，而不是静默丢历史。

### 7.15 写回链路搬进可执行代码：重试必须在重试发生时被走过（R89）

R88 的重试循环只写在 `ci.yml` 里：本地跑不了，测试只能对 YAML 做子串断言
（`for attempt in 1 2 3`、`git pull --rebase origin main`）。子串断言证明不了
「push 被拒之后真的会 rebase 再推」——R68 的教训是重试路径必须在重试真的发生
时被走过一次。

- **提取**：提交/推送/重试搬进 `scripts/ci_writeback_history.py`；YAML 只剩一次
  调用（`--metrics` / `--history` / `--run-id` / `--commit-message`）。重试语义
  只有一份：`test_writeback_delegates_retry_to_the_script` 反向钉住 YAML 里不得
  再出现 `git push` / `pull --rebase` / `for attempt`（R80：同一个事实写两处会分裂）。
- **行为用例**（`tests/test_ci_writeback_history.py`，真实 git 临时仓）：

| 用例 | 让什么真的发生 |
|---|---|
| `test_push_succeeds_on_the_first_attempt` | 快进：第 1 次成功；提交信息带 `[skip ci]` |
| `test_rejected_push_rebases_and_succeeds_on_the_second_attempt` | other 仓先推一个提交 → work 的 push **真的被拒** → rebase → 第 2 次成功；远端无 merge 提交 |
| `test_permanent_rejection_stops_after_the_attempt_cap` | pre-receive 钩子永久拒绝：恰好 `DEFAULT_ATTEMPTS`（3）次后 `::error::` + 退出 1 |
| `test_same_run_rerun_does_not_create_a_second_commit` | 同一 run 重跑（第二次时间戳被推后）：历史逐字节不变、没有第二次提交 |
| `test_commit_does_not_sweep_unrelated_changes` | 工作树里有**已暂存**的杂项，写回提交也只含 history.json |
| `test_missing_metrics_is_not_a_failure` | 没有 metrics：退出 0、历史不动 |
| `test_rebase_conflict_fails_loudly_instead_of_losing_the_round` | 远端也改了 history.json：rebase 冲突 → `::error::` + 退出 1（不静默丢轮次） |
| `test_cli_has_the_same_semantics_as_the_function` | CLI 与函数同一语义 |

- **顺带修掉的一个真缺陷**：`record` 原先每次重跑都写新的 `exported_at`，所以
  R88 文案里的「内容不变就不提交」在重跑时并不成立——会多一次**非空**提交。
  现在同一 `run_id` 且观测（`total/passed/failed/retried/attempts/scenarios`）
  完全一致时保留首次时间戳；观测变了照常更新（反向边界
  `test_record_updates_the_export_time_when_the_observation_changes`）。
- **身份**：bot 身份走 `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 环境变量，而不是只给
  `git commit` 加 `-c`——被拒后的 `pull --rebase` 也会重写提交、也需要身份
  （R89 实测：只给 commit 加 `-c` 时 rebase 会因缺身份而失败）。
- **窗口 20 → 40**：R88 把「一轮 = 一次显式导出」改成「一轮 = 一次 main push」，
  doc-only 提交也占一格；R88 自己就吃掉 3 轮，20 轮只剩 6~7 个工作轮的量。
  窗口是**保留期**，不是判决门槛（趋势仍不判好坏）。
- **窗口 40 → 80（R112，用户拍板）**：R111 时已用到 39/40，而 39 条只覆盖
  2026-11-01 01:51 ～ 2026-11-02 13:32（约 1.5 天）——每个工作轮约 3 次 push，
  40 格 ≈ 13 个工作轮。默认值只改 `MAX_ROUNDS`；环境变量与 [3, 1000] 校验不变；
  `test_record_trims_to_the_window` 钉值 80 与「第 81 轮掉最老」，驱动的窗口
  边界用例改为**显式配置 40**，不再跟默认政策走。
- **变异验证（8/8 全咬合，还原源是当前文件快照，不用 `git checkout`）**：
  M1 `pull` 不带 `--rebase` → 1 红；M2 重试上限 3→1 → 2 红；M3 没有 metrics
  当失败 → 1 红；M4 无变化仍然提交 → 1 红；M5 默认信息丢 `[skip ci]` → 1 红；
  M6 commit 不带 pathspec → 1 红；M7 重跑总是改写 `exported_at` → **2 红**；
  M8 窗口 40→20 → 1 红。**M7 第一次实测只有函数级用例咬住**：端到端重跑用例
  在同一秒内会假绿（同秒的 `exported_at` 本来就相同），把第二次重跑的时间戳
  显式推后才变成两处咬合。
- **边界（如实）**：本地仍不能复现 `actions/download-artifact` 与真实 token 的
  push 权限；覆盖的是脚本的输入契约与 git 行为。远端冲突时的处置仍是「响亮失败、
  本轮不入库」（与 R88 相同），没有自动重算。

### 7.16 写回冲突：重算而不是丢轮次（R90）

R89 的处置是「rebase 冲突 → `::error::` + 退出 1」。冲突意味着本地提交是在**旧
历史**上算的；`record` 是幂等的，所以在最新历史上重算即可同时保住人工轮与 CI 轮。

- **结构**：`record` 移进重试循环；`prepared` 标志区分「需要重新准备」与「只需重推」。
- **两个可被变异咬住的细节**：①自身 rebase 成功后**不得**再 record——提交已在分支
  上，再 record 会得到「没有变化」并提前返回 0，把这一轮丢掉；②冲突回退后**必须**
  `prepared = False`——否则下一轮推一个空提交、报成功却什么都没写。
- **守卫**：`tests/test_ci_writeback_history.py::test_rebase_conflict_recomputes_instead_of_losing_the_round`（两轮都在、无 merge 提交、第 2 次成功）、
  `test_conflict_stops_after_the_attempt_cap`（冲突消耗一次尝试）。
- **变异**：M9–M12 **4/4 全咬合**。
- **边界**：重算丢弃本地写回提交（仅在本 job 的 checkout 里安全）；冲突消耗一次尝试。

### 7.17 写回结果：固定类别 + step summary（R91）

同一个退出码可能来自不同原因（R64 教训）。R91 把每轮结果升级成
`(退出码, 类别, 说明)` 三元组，类别是固定字面值：

`written` / `no-change` / `metrics-missing` / `record-invalid` /
`push-rejected` / `rebase-conflict` / `git-error` / `usage`（R94 增 `dry-run`）。

- 追加进 `GITHUB_STEP_SUMMARY`；**写不进去只告警**，不改判决（历史已在 git 里）。
- 守卫：`test_summary_records_missing_metrics_and_record_invalid_separately`
  （缺 metrics 与坏 metrics 不共用一句话）、`test_result_categories_are_distinct_literals`
  （字面值固定且互异）、`test_summary_write_failure_does_not_change_the_verdict`。
- 变异：M13–M17 **5/5 全咬合**。

### 7.18 PR 预检：`record --check-only`（R92）

坏 metrics 原先要等合入 main 后的写回 job 才炸。R92 把它左移到 PR：

- `--check-only`：读 metrics/历史、算条目、校验结果，**不写文件**；退出码与正常
  record 完全一致（3/4/2）。
- **写入前自校验**（所有路径）：算出的 `trimmed` 历史必须通过 `validate_history`，
  否则 4 且文件逐字节不动——覆盖 record 自己的覆盖/去重/裁剪算术。
- CI：backend 增加只在 `pull_request` 上跑的只读预检步骤（无 `git commit`/
  `git push`/`upload-artifact`），写权限仍只在 `e2e-history-writeback`。
- 守卫：`test_record_check_only_does_not_write`、`test_record_validates_the_result_before_writing`、
  `test_backend_prechecks_metrics_on_pull_requests`。
- 变异：M18–M22 **5/5 全咬合**。**M20 第一次 MISSED 是用例配错**（只跑失败码用例，
  没跑成功码用例）——R70「必须跑全部相关用例」。

### 7.19 历史条目来源：`source`（R93）

R88 之后历史同时含本机导出与 CI 写回，此前只能靠 `run_id` 形状猜。R93 让条目
自己说 `source`：

- `SOURCES = ("ci", "local")`；本机默认 `local`，写回脚本显式传 `ci`。
- 旧条目**缺失合法** → 计「未标注」，**不根据 run_id 反推**（不把命名习惯变成事实）。
- 出现但不在 `SOURCES` 里 → `HistoryError`（退出 4）——未知值不是「未标注」，是数据坏了。
- `check` 多打印 `来源：CI n / 本机 m / 未标注 k`，**只读展示**、不改退出码。
- 生产证据：run 41303273571 写回的条目 `source=ci`（前 8 轮保持未标注，不回填）。
- 变异：M23–M27 **5/5 全咬合**。

### 7.20 本地回放：`--dry-run` 与沙箱回放（R94）

R89 §7-2 的「未在本地复现整个 writeback job」缩到只剩 artifact 传输本身：

- `--dry-run`：`TemporaryDirectory` 里的历史副本上真算一遍，报告 `历史 N/<保留期> 轮（+k）`，
  不写文件、不提交、不推送。
- `scripts/replay_ci_writeback.py`：裸克隆源仓库当 origin → 克隆工作区 → 跑真实
  `writeback()`（提交/推送/重试都是真的，只是推到沙箱）；复核源仓库 HEAD 未变。
- 守卫：`test_dry_run_does_not_touch_the_repo`、`test_replay_leaves_the_source_repo_untouched`、
  `test_replay_dry_run_does_not_commit`。
- 变异：M28–M30 **3/3 全咬合**。
- **边界**：`actions/download-artifact` 的传输仍不能本地复现；replay 只回放已提交状态。

### 7.21 artifact 传输与回放未提交态：把「传输」也变成代码（R95）

- 下载侧从 `actions/download-artifact` 换成 `scripts/fetch_ci_artifact.py`：
  列表（`name` 精确匹配）→ 下载 zip → 安全解压；认证头用
  `add_unredirected_header`，302 到 blob 主机时不带 token（R71 实测 401）；
  zip 的绝对路径与 `..` 被拒。
- **旧接线的 `continue-on-error: true` 会把 401/403/5xx 吞成「没有 metrics」**：
  写回 job 以 0 退出、静默丢掉一轮。R95 改为缺 artifact/过期 → 0，真实传输
  错误 → `::error::` + 1——与 R64「同一退出码不同来源」同源。
- replay `--from-worktree`：`git diff HEAD --binary`（暂存 + 未暂存）apply 到
  沙箱；未跟踪文件不进入（只打印数量）。
- 失败自动保留沙箱：成功删除、失败/`--keep` 保留。`_remove_sandbox()` 先清
  只读位——`shutil.rmtree(ignore_errors=True)` 在 Windows 上删不掉 git 的只读
  pack/object，**R94 的「默认删除」在 Windows 上一直没删掉**（R95 用例发现；
  本机 temp 实测积了 12 个旧沙箱）。
- 守卫：`tests/test_fetch_ci_artifact.py` 9 条、`tests/test_replay_ci_writeback.py`
  +4、`tests/test_ci_history_writeback.py` +2（替换 1 条）。
- 变异：M31–M39 **9/9 全咬合**。
- **生产首跑 415**：artifact 下载端点拒绝 `application/octet-stream`，必须
  `application/vnd.github+json`；假服务器不校验 Accept，9 条用例全绿也漏了它。
  修复后本机真实 API 探针成功，run **41324392700** 六 job 全绿（写回 10→11）。
- **边界**：假服务器只证明脚本的 API 契约；真实 token 权限、artifact zip 布局
  与上传侧 `upload-artifact` 仍由下一次 CI 生产运行验证。

### 7.22 下载 → 写回：整链本地回放（R96）

- `replay --fetch-api-url`：先走真实的 `fetch_ci_artifact.fetch()`（列表 →
  下载 zip → 解压），再把解出来的 `e2e-metrics.json` 交给真实 `writeback()`；
  fetch 非 0 → 不进入写回、沙箱按失败保留；缺 artifact → fetch 0、写回按
  「没有 metrics」0。
- 假 artifact API 抽成 `tests/artifact_api_fixture.py`，fetch 与 replay 共用。
- **三处文件名的同一条契约**：backend 上传路径的 basename、fetch 的
  `--artifact`、写回读取的 metrics 路径；任何一处改名都只会表现为「本轮不入库」
  （退出 0），所以必须由一条接线用例串起来（R80 的「同一事实两处会分裂」在
  这里是三处）。
- 守卫：`tests/test_replay_ci_writeback.py` +4、
  `tests/test_ci_history_writeback.py` +1。
- 变异：M40–M43 **4/4 全咬合**。
- **边界**：上传侧 `actions/upload-artifact` 仍无法本地执行；R96 只钉文件名
  契约，zip 的实际布局由 CI 生产运行验证。

### 7.23 机读结果工件：rounds 读远端、attempts 数 push（R97）

- `--result-json` 每个出口都写：`reason` / `detail` / `exit_code` / `rounds` /
  `push_attempts` / `dry_run`，与 step summary 共用同一组 `reason` / `detail`。
  写失败只告警，不改变退出码。
- **`rounds` 必须读 `origin/<branch>` 的已入库历史**：push 被拒时 record 已经
  把 `history.json` 写进工作树，读本地会把「未入库」报成 1（M49 咬住）。
- **`push_attempts` 的计数点放在 push 紧前面**：原在循环顶部，record 失败也会
  记成一次 push；移到 record / no-change 之后，两类都归 0（M46 咬住）。
- CI 新增 `Upload writeback result`（`if: always()`、缺失 warn）。
- 守卫：`tests/test_ci_writeback_history.py` +10（含 CLI）、
  `tests/test_ci_history_writeback.py` +2。
- 变异：M44–M49 **6/6 全咬合**。
- **边界**：`upload-artifact` 使用运行时 token，是否需要 `actions: write` 由
  CI 首次上传实证；`git-error` 的 `push_attempts` 固定 0（异常时无法可靠知道
  已发起的次数）。

### 7.24 fetch 重试与分类：白名单 + 异常携带计数（R98）

- **只重试瞬时错误**：`RETRY_STATUS = {429,500,502,503,504}` + 网络/超时；
  401/403 不重试（重试只会把「凭证坏了」拖成三次）。最多
  `DEFAULT_ATTEMPTS = 3`，退避 0.5s / 1s，可注入 `sleep`。
- **失败路径的 attempts 必须由异常携带**：`_read_with_retries` 成功才 return，
  `attempts_used += used` 在 return 之后，失败时永远加不上；改为
  `FetchError(msg, used)`，外层 `attempts_used += exc.attempts`。
- 类别：`artifact-fetched` / `missing` / `expired` / `fetch-failed` /
  `invalid` / `usage`；`ArtifactInvalid` 覆盖坏 zip、路径穿越、缺 archive_url。
- summary/result 写入抽到 `scripts/ci_reporting.py`，写回与 fetch 共用；
  写失败只告警。
- 守卫：`tests/test_fetch_ci_artifact.py` +7、
  `tests/test_ci_history_writeback.py` +1。
- 变异：M50–M56 **7/7 全咬合**。
- **边界**：真实 GitHub 网络层的重试从未发生（生产两次 fetch 均首次成功）；
  `attempts` 是列表 + 下载的**总请求数**，不是「重试轮数」。

### 7.25 回放内制造拒绝/冲突：失败路径的本地演练（R99）

- `replay --reject-pushes N`：沙箱 origin 装 `pre-receive`，计数器在
  `$GIT_DIR/replay-reject-count`，前 N 次 push 真实被拒 → 重试/rebase 分支在
  fetch → writeback 全链里被走过。
- `replay --conflict`：先在 origin 推一条**通过 `validate_history`** 的
  `history.json` 轮次；写回 push 被拒 → `pull --rebase` 冲突 → R90 的
  reset/recompute 路径真实触发，最终历史同时保留冲突轮和本轮。
- 顺序：worktree patch → conflict → reject hook → writeback；钩子若先装会把
  冲突那一推也拒掉。
- `--result-json` 透传给 writeback，端到端可断言 `push_attempts`
  （被拒一次 = 2）。
- 守卫：`tests/test_replay_ci_writeback.py` +5。
- 变异：M57–M62 **6/6 全咬合**。
- **边界**：钩子是 `#!/bin/sh`（Git for Windows 自带 sh）；模拟的是沙箱
  origin 行为，不是 GitHub 服务端/网络层。
- **测试精度**：`out.count("push 被拒")` 会把钩子安装提示也算进去；断言词
  必须带边界（`push 被拒（第`）。

### 7.26 replay 拒绝/冲突进生产 CI：三条路径的逐场景断言（R101）

- `replay-ci-writeback`（`ubuntu-24.04`、只读、PR 与 push 都跑）调用
  `scripts/replay_ci_scenarios.py`；生产 job **不跑 pytest**，pytest 覆盖只是
  并存的第二道锚，不再是唯一执行者。
- 期望计数是**精确值**，不是容忍量（因此不进 §2 的数字容忍量表）：

  | 场景 | rounds 增量 | push_attempts |
  |---|---|---|
  | `happy` | +1 | 1 |
  | `rejected`（`--reject-pushes 1`） | +1 | 2 |
  | `conflict`（`--conflict`） | +2（冲突轮 + 本轮） | 2 |

- 每个场景前后比较源仓库 HEAD 与 history 字节；任一变化 → 1，并**停止**
  后续场景（基线已污染，继续跑只会扩散）。
- 退出码：0 全符 / 1 场景不符 / 2 用法 / **3 基线不可用**（repo 不是 git 仓、
  history 缺失/读不懂）。3 不是 1——环境坏不冒充回放语义坏。
- 守卫：`tests/test_replay_ci_scenarios.py` +6、
  `tests/test_ci_replay_wiring.py` +9。
- 变异：M63–M70 **8/8 全咬合**（M64/M66/M70 各自唯一咬合）。
- **边界**：只在 ubuntu 跑（Windows 的 replay 行为由 `windows-backend` 的
  pytest 覆盖）；永久拒绝（三次全拒）仍只由 pytest 覆盖；不跑
  `--fetch-api-url`（下载→写回整链已由生产 fetch 与 R96/R99 覆盖）。

## 8. 环境归因：skip 判据的自变量（R71）

R70 §6.1 的发现推翻了 `tests/conftest.py` 旧 skip 文案的因果句。把四行实测矩阵
原样登记在这里，作为「113 skips 是什么的函数」的唯一依据：

| 启动器 | 令牌 | probe（`_git_transport_blocked_probe`） | 说明 |
|---|---|---|---|
| Git Bash | High | `True` | 新起的 `sh.exe` 挂不上 `\BaseNamedObjects\msys-2.0S…`（`NtCreateDirectoryObject: 0xC0000022`） |
| cmd / PowerShell | High | `True` | 同上；不是 Git Bash 特有 |
| 自降令牌（进程内回读 `S-1-16-4096`） | Low | `True` | 与 High 同 profile |
| 直接在 Git Bash 里 `git clone` | High | 成功 | bash 自己早已挂接该对象 |

全量套件两次运行同为 **2189 passed / 113 skipped / 0 failed**（High 123.95s、
Low 124.94s）。**R71 复测（同机同码，约 20 小时后）方向反过来了**：High
**2279 passed / 28 skipped**、真降 Low **2194 passed / 113 skipped**。

**R81 把根因查清了（2026-11-01，本机只读取证 + 合成对象交叉对照）**：

- 对象 `\BaseNamedObjects\msys-2.0S5-1888ae32e00d56aa` 的 DACL 只有一条
  `Everyone → 0x2000F`（含 `DIRECTORY_CREATE_OBJECT`），**没有 SACL**；Low
  打开者的写权限仍然全拒（`0xC0000022`），High 打开者全通。
- 同一 DACL 的合成临时对象：**High 创建 → Low 被拒；Low 创建 → Low 通过**。
  所以对象**隐式带着创建者的完整性级别**，DACL 里写着允许并不够。
- IL 由父令牌继承。R81 当时写成「`F:` 上的可执行文件被强制降到 Low」——**R84
  更正：降级的是带 Low 强制标签的那棵目录树，不是卷**（见下条）。

于是「113 vs 28」的判别变量是**启动器的 IL**，而不是「会话状态」这种不可操作的
说法。R70 的「High 也失败」在本机不复现（Git Bash / PowerShell / py.exe 三种 C:
启动器下 `sh.exe` 全 rc=0，High 全量 2373/28）；那次所谓「High」最可能是 Low
解释器派生的 shell——本机实测这种派生不会升 IL。**skip 文案自 R81 起恢复处方**
（High shell + C: 启动器 + `PYTHONPATH`），但仍不把责任钉成「本令牌是 Low」：
对象侧的 IL 可能高于任何我们能拿到的令牌。

**R82/R83 更正启动器（2026-11-01）**：`C:\Windows\py.exe` 是 Windows launcher，
本机今天用它跑 pytest 有 **137 个 collection error**（没有项目依赖），照抄会得到
一个看似环境故障的假象。实测有效的是 C: 上的 CPython 本体
`C:\Program Files\Python314\python.exe`，并把 venv 的 `site-packages` 连同
`win32` / `win32\lib` / `pythonwin` / `pywin32_system32` 显式放进 `PYTHONPATH`
（`.pth` 在 PYTHONPATH 下不执行）。R82 全量 High 2387/28、R83 复跑 2406/28
都用这条命令；`tests/conftest.py::_msys_skip_reason` 与 PROJECT_INFO 平台注意
事项 9 已同步。

**R84 找到机制（2026-11-01，只读取证）**：`F:\DeterminFlow x2` 本身带一条
**显式**的 `Mandatory Label\Low Mandatory Level:(OI)(CI)(NW)`（`icacls` 里没有
`(I)`），整棵树继承；`F:\` 根、`F:\新建文件夹`、`F:\DeterminFlow`（旧仓库）都
**没有**标签。Windows 创建进程时把令牌降到镜像的强制标签：于是 venv 里的
`python.exe` 一启动就是 `S-1-16-4096`，而同一份二进制放到 `F:\` 根或别的无标签
目录就是 `S-1-16-12288`。判别实验（同一台机器、同一个 High 父进程）：

| 实验 | 镜像位置 | 结果 |
|---|---|---|
| 对照 | `C:\Program Files\Python314\python.exe` | High |
| 卷级假设 | `cmd.exe` 复制到 `F:\` 根 | **High**（推翻「F: 上的可执行文件」） |
| 名字假设 | `cmd.exe` 改名成 `F:\python.exe` | **High**（推翻「按文件名」） |
| 字节假设 | `python.exe` 复制到 `F:\_r84_py_copy.exe` | **High**（推翻「按哈希」） |
| 因果对照 | 同一份 `python.exe` 放进新建的无标签 `F:\_r84_label_test\` | High |
| 因果验证 | 对同目录执行 `icacls ... /setintegritylevel (OI)(CI)Low` | **Low** |

第三、四、五行是关键：降级**只在镜像继承了 Low 标签时发生**。R81 的「F: 上的
可执行文件被强制降到 Low」把目录树属性误读成了卷属性——它当时的样本全部落在
`F:\DeterminFlow x2` 树下。本机 minifilter 只有 Windows 自带组件（`fltmc filters`
列出的是 bindflt / UCPD / storqosflt / wcifs / CldFlt / bfs / FileCrypt / UnionFS /
npsvctrig / Wof / FileInfo），AV 只有 Windows Defender，因此排除「安全软件驱动
在 `CreateProcess` 时改令牌」这一类。

后果：**113-skip 的 Low profile 是这棵树带标签的结果，不是机器的属性**。别的
机器、别的目录（无标签）上，venv 解释器继承父进程的 IL，msys 不会因此失败。
C: 解释器处方仍然有效（C: 不在标签树下），但它是**绕开**；真正的根修是清掉那棵
树的标签：

```
icacls "F:\DeterminFlow x2" /setintegritylevel (OI)(CI)Medium
```

本条在 R84 时**没有执行**这一步：改用户目录的安全属性不是测试该做的事；R85 经用户拍定后已执行，见下条。`conftest.py` 的
skip 文案因此同时给出「清标签」与「C: 解释器」两条路（R84 已同步，用例钉住）。
R36 记录的「服务进程为 Low-IL」与此一致，但本轮没有回查当时的标签状态，不把
因果钉到某个具体轮次。
**R85 执行（2026-11-01，用户拍定 R84 §9-2）**：清标签落地并重定基线。前置审计（只读）覆盖 **17290 个目录 + 169 个 `.exe`/`.dll`**，显式标签只有根目录一条（`Low:(OI)(CI)(NW)`，无 `(I)`），其余全部继承——所以 `icacls "F:\DeterminFlow x2" /setintegritylevel (OI)(CI)Medium` 一步即可覆盖全树；改后复核：根 `Medium:(OI)(CI)(NW)`、`.venv\Scripts\python.exe` `Medium:(I)(NW)`、显式 Low 残留 **0**。**一个必须写下来的事实**：清成 Medium 后 venv 解释器的令牌是 `S-1-16-8192`（Medium），**不是 High**——Windows 用镜像的强制标签给令牌封顶，镜像带 Medium 标签时不会继承 High 父进程；R84 §8-2 的「清标签后 venv 继承父进程 IL」只对**完全没有标签**的镜像成立。要真正 High 仍走 C: 解释器 + `PYTHONPATH`。**基线**：venv 全量 **2486 passed / 28 skipped / 0 failed**（180.64s），与 R84 的 High 基线逐项相同（2401+85=2486、113−85=28，85 条正是被 msys 签名转 skip 的那批）。**记账变更**：本机不再维护「Low/High 双基线」，改为**单一本地基线 2486/28**；用例总数不变（2514），CI 的 ubuntu/windows 计数不变。**未做**：没有删除 SACL 里的标签 ACE（只改成显式 Medium）；没有跑前端 / e2e / docker build（零代码改动）。

判据本身（`_msys_skip_applies`）只有两个自变量：

| 失败调用带签名 | 模块 ∈ 6 个传输模块 | 探针复现签名 | 结果 |
|---|---|---|---|
| 是 | 任意 | 不查 | **转 skip**（识别环境，不识别模块） |
| 否 | 是 | 是 | **转 skip**（模块内失败无法归因） |
| 否 | 是 | 否 | 照常失败 |
| 否 | 否 | 任意 | 照常失败 |

**登记这个判据的同时必须登记它的代价**：skip 不等于通过。113 条用例在 Low 会话
**没有执行**；上表只说明「那批失败带 msys 签名或落在传输模块内」，不说明这些
用例的断言成立。要真正执行它们，按上面的处方从 High shell 用 C: 启动器跑——
本机实测 28 skips 全是平台类（macOS 签名 / fcntl / Unix 进程树），没有 msys 归因。

**判据还必须对自己的失败免疫**：R71 第一次变异验证时，文案用例判红，断言消息里
带着 `NtCreateDirectoryObject`，钩子按签名把它转成 skip——输出变成「全绿」，判据
发现了错误却被伪装成「环境不可用」。修法是 `no_msys_skip` 标记（`pyproject.toml`
登记）：带标记的用例失败时钩子原样返回。这样「判据判红」与「环境真坏」在输出里
永远可区分。

钉住它的五条用例见 §6（`tests/test_msys_attribution.py`）。

## 9. 元数据形状无效：4 不是 1/8（R75）

`per_workflow` 是手可改的入库文件。R75 实测两种畸形：

| 畸形 | 修复前 | 冒充的东西 | 修复后 |
|---|---|---|---|
| `"wf-a": "junk"` | `AttributeError`，CLI 退出 **1** | 「判了且不合格」→ 查供应商 | 退出 **4**（重导） |
| `"failed": "abc"` | `ValueError` → `_run_judgement` 归成 **8** | 「判据算术失败」→ 修判据 | 退出 **4**（重导） |

`_per_workflow_shape_error()` 在漂移检查之前校验三条 per-workflow 判据共用的
`per_workflow` 块：bucket 必须是对象；`runs`/`attempts`/`failed` 必须是非负
整数（数值字符串接受、布尔与非整数拒绝）。返回第一条问题，统一走
`_metadata_shape_message()` → 退出码 4。**4 与 8 的分界**：8 是「判据自己算不
下去」（修判据），4 是「被判的数据坏了」（重导）；把数据错误归到 8 会让两种
处置互相冒充，与 R64 给 `OverflowError` 单独开 8 是同一条纪律的反面。

## 10. R107–R113：输入来源、预算边界、窗口配置、删除守卫与可达性（2026-11-02/03）

### 10.1 指纹不是来源证明（R107）

全链写回前打印实际 metrics 的计数指纹（`replay：metrics 内容 total=…`），
并让驱动自己的本地夹具故意与生产 artifact 不同形（3 场景/1 重跑 vs 10
场景）。只断言生产形状（`total=10`）能发现「没打印/没下载」，发现不了
「打印的是另一份文件」——M110 把指纹写死成 10，全链行为用例照样绿，
只有变体形状（2/4 场景）的单测能咬住。**判据要证明来源，必须让错误来源
的形状与正确来源不同。**

R112 把指纹从「计数」扩到「内容」：写回前逐场景打印
`name=ok|retry|fail/尝试次数` 与 `first_failure`，全链场景断语义行出现；
另用**失败/重试形状**（一失败、一重跑）的 artifact 走真实 fetch → writeback，
并读沙箱历史确认 failed/retried/attempts 与逐场景 `first_failure` 原样落库。
**总数相同、语义不同的两份数据，只有语义断言能把它们分开。**

### 10.2 预算：改时机，不改断言（R108/R112）

R106 的 `reject_pushes=3` 只是字面口径：冲突在 writeback 前注入，第一次
push 被非快进挡下、根本到不了钩子，预算 2 与 3 行为等价。R108 把注入搬进
`pre-receive`（第一次拒绝时用 plumbing 追加一轮冲突历史），第一次 push
真的到钩子；预算 3 → 三次全拒，预算 2 → 第三次成功。**一个数字要成为
行为边界，改变的是状态/时机，不是断言里的常量。**

R112 再把时机参数化到「第 N 次拒绝」：N=2 覆盖预算中途耗尽与第三次成功；
N=3 覆盖「注入发生在最后一次拒绝」——冲突轮进了 origin，但已没有下一次
重试去消化，最后一次失败因此是 `rebase-conflict` 而不是 `push-rejected`。
N 落在预算之外时 CLI 退 2：**注入永远不会发生却静默退化成普通拒绝，等于
让「第 N 次注入」从未被执行过。**

钩子内写对象还有一个硬约束：`pre-receive` 失败会丢弃 quarantine，注入脚本
必须清掉 `GIT_OBJECT_DIRECTORY` / `GIT_ALTERNATE_OBJECT_DIRECTORIES` /
`GIT_QUARANTINE_PATH`，否则 `update-ref` 指向不存在的对象。

### 10.3 配置：一个读取点（R109）

`XS2_MAX_ROUNDS`（R112 起默认 80，范围 [3, 1000]）由 `max_rounds()` 单点读取；
record、写回文案、`window_full`、驱动期望、冲突夹具、钩子注入全部走它。
非法值不静默：`::warning::` 后退回默认值。**一个配置项若有两处读取，就会
出现「裁剪按 A、期望按 B」的分裂**；驱动用「窗口 8、基线 8」把这种分裂
判红。只改文案的缺陷（M123）需要文案断言，`rounds` 全对时它完全隐形。

### 10.4 删除：默认不删（R110）

`replay_sandbox_gc.py` 四道守卫各自独立：直接子目录、`replay-ci-writeback-`
前缀、非符号链接/junction、mtime 超龄；默认 dry-run，`--apply` 才删，删后
复核。删除复用 `_remove_sandbox`（Windows 只读 pack 的历史修复）。**删除
类工具默认必须是 dry-run**；守卫要各自有变异咬住，否则测的只是「删了一个」。
GC 不进 CI：runner 临时目录随 job 消失，没有历史现场可清。

### 10.5 可达性是两个变量：预算够 ≠ 注入点到得了（R113）

R112 的「N 落在预算之外退 2」只回答了半个问题。注入发生在
`pre-receive` 的第 N 次拒绝，而拒绝要由写回循环发起 push 才会发生；循环
最多 push `attempts` 次（默认 3）。`--reject-pushes 4 --conflict-on-reject 4`
因此能通过「预算 ≥ N」校验，却永远走不到第 4 次 push——和第 N 次注入从未
发生完全一样，只是失败得更安静。R113 把重试上限提成 `--attempts` 并补上
`N <= attempts` 的校验（与预算校验并列，两个都退 2）。

新增 N=4/5 三条时间线：N=4/预算 4/attempts=4（全失败，末次注入）、N=4/
预算 4/attempts=5（第五次成功）、N=5/预算 5/attempts=5（全失败）。
**一条「配置生效」的判据，必须同时覆盖配置里每一个决定可达性的变量**；
只改其中一个，另一个会让整条路径静默消失。

R114 把矩阵抬到预算 6 / N=6，并新增表不变量
`test_hook_scenarios_are_reachable_and_consistent`：对每个钩子场景校验
`注入点 <= 预算`、`注入点 <= attempts`、成功场景 `attempts == 预算 + 1`、
失败场景 `reason` 由「注入点是否等于 attempts」决定。**场景表是判据的
唯一来源**——未来加 N 时，不可达组合会在表上直接判红，而不是等 CLI 退 2
才发现「这条场景其实从未执行过」。

R117 把 N=6 / attempts=7 搬进全链（`fetched-rejected-hook-at-6`），并用
`test_fetch_hook_scenarios_match_the_local_formula` 断言全链 N=4/6 与本地
成功场景共用同一组代数关系：全链只换 metrics 来源，不换写回语义。

R124 把矩阵抬过 6/7 的上限：本地 N=7/attempts=7（七次全拒、末次注入，
`reason=rebase-conflict`）与 N=8/attempts=9（第 9 次成功、净 +2），全链
`fetched-rejected-hook-at-8`（同 N=8/attempts=9）。三条都不改代数关系，
只证明钩子计数与重试循环没有隐含的 6/7 上限；场景表不变量仍是加 N 时的
唯一守卫。

### 10.6 失败形状：写回记录的是数据，不是结论（R113）

R112 的失败/重试形状只有一个失败、一个重跑。R113 补三种边界，全部走真实
`fetch_ci_artifact.fetch()` → `writeback()`，再读沙箱历史核对：

- **全失败**（3 场景全 `passed=False`）：写回照常成功入库。失败数据也是
  数据；把「本轮 e2e 全红」当成「写回失败」会让趋势永远看不到质量事故。
- **0 场景**（`total=0`）：合法形状，语义行打印 `（无场景）`。空行与
  「指纹没打」在日志里不可区分——**缺少内容也要显式说出来**。
- **重试多次仍失败**（`attempts=3` 且 `passed=False`，另一个场景重跑后
  通过）：`retried`/`attempts` 只描述试了几次，最终结论仍看 `passed`；
  两者不能互相冒充。

三种形状的逐场景 `first_failure` 都原样落库。生产 artifact 仍是真实全过
形状（不造假），失败形状只由测试夹具提供——与 §5 的「不污染趋势」同一条
边界。

**下游消费（R115）**：历史条目从 R112 起就带 `failed`，但 `render_trend`
的趋势表一直只显示「场景/重跑/重跑率/总尝试」——全失败轮与全通过轮在表
里长得一样。R115 补 `失败` 列，并把「0 场景」从「历史为空」的文案里拆出
来：前者可读、只是重跑率 n/a，后者才是没有可读轮次。**一个字段入库不等于
它被消费；下游不显示，等于上游白记。**

**与重试组合（R116）**：失败形状 artifact 再叠一次拒绝/注入，重试循环的
`record → rebase/reset → 再 push` 不得重算内容。两格用例断 `(4,3,1,1,5)`
与逐场景 `first_failure` 原样保留。全过形状的 `failed=0` 会让「失败数被
清零」完全隐形——组合用例的价值正在于让被重算的计数显形。

### 10.7 五轮收口（R114–R118）

- **R114**：场景表不变量把「注入点 ≤ 预算」与「注入点 ≤ attempts」的
  代数关系钉住；N=6/7 两条时间线（中段注入后仍耗尽、末次注入后第 7 次
  成功）。
- **R115**：趋势表补 `失败` 列；0 场景与空历史分开说话。下游消费才算
  真的记录。
- **R116**：失败形状 × 拒绝/注入组合；重试不得重算计数或场景明细。
- **R117**：全链 N=6；全链与本地共用同一组代数关系（公式测试）。
- **R118**：四账收口；用例 2717 → **2723**，本机 **2695/28/0**。

五轮均为测试/展示层：生产 `DEFAULT_ATTEMPTS=3`、`MAX_ROUNDS=80`、GC
dry-run/7 天、按天滚动未实现等政策边界不变；`check` 的退出码语义不变。

### 10.8 全链复验：失败形状 × 拒绝/注入（R119）

R116 的「失败形状 × 拒绝/注入」此前只在本地用例里；R119 把它搬进生产
fetch-chain。CI 的 backend 额外上传一个夹具 artifact
`e2e-metrics-failure-shape`（固定 4 场景、1 失败、1 重跑；**不是**生产 e2e
输出，`e2e-history-writeback` 仍只读 `e2e-metrics`，不会把夹具写进历史）。
新增两条全链时间线：

- `fetched-failure-shape-rejected`：被拒一次后第 2 次成功，净 +1；
- `fetched-failure-shape-rejected-conflict`：第 1 次拒绝时注入冲突，第 3 次
  成功，净 +2。

两条都断言 `(total, passed, failed, retried, attempts) == (4,3,1,1,5)`、
`metrics 语义 ok_0=ok/1 retry_1=retry/2 fail_2=fail/1 ok_3=ok/1` 与逐场景
`first_failure` 原样出现。场景表按 `Scenario.artifact` 选 artifact 名，避免
全链场景悄悄回退到 `e2e-metrics`——全过形状的 `failed=0` 会让「失败数被
清零」完全隐形。`tests/test_ci_replay_wiring.py` 另钉住「夹具只在 main
push 上传」与「写回 job 不消费夹具」两条接线边界。

**0 场景（R120）**：`e2e-metrics-empty`（`total=0`、`scenarios=[]`）同样
走真实 artifact 下载。`fetched-empty` 断言计数全 0、语义行
`metrics 语义 （无场景）`、且不出现 `metrics 首次失败`；`fetched-empty-
rejected` 再叠一次拒绝，证明 0 场景经重试循环仍是同一份数据。0 场景是
合法轮次，不是「历史为空」；语义行缺失与「指纹没打」不可区分，所以必须
显式打印。

**全失败（R121）**：`e2e-metrics-all-failed`（3 场景全 `passed=False`）同样
走真实 artifact 下载。`fetched-all-failed` 断言 `(3,0,3,0,3)`、语义全
`fail/1` 与逐场景 `first_failure`；`fetched-all-failed-rejected` 再叠一次
拒绝，证明重试不会把 `failed` 清零或重算。失败数据也是数据——把「本轮
e2e 全红」当成「写回失败」会让趋势永远看不到质量事故。

**下游消费 × 真实写回（R122）**：R115 只证明趋势表有 `失败` 列；R122 用
同一组夹具走真实 `replay.main()` 写回，再从沙箱 history 调
`render_trend()`，按列断言三格：失败/重试 `(4,1,1,25.0%,5)`、0 场景
`(0,0,0,n/a,0)`、全失败 `(3,3,0,0.0%,3)`。0 场景还断「最近一轮 0 个
场景」——`n/a` 是「可读但没有重跑率」，不是「历史里没有可读轮次」。

### 10.9 满窗实战、长链形状、幂等与截断（R125–R128）

- **满窗实战（R125）**：R102 的边界几何只在显式 40 窗口下演过；生产
  默认 80 从未满过，第一次满窗将发生在 CI replay job 里。R125 用默认
  窗口跑真 79/80 两格：满窗时 8 个成功场景 `rounds_clipped=True`、失败
  注入裁到 80 不越窗、摘要逐条「窗口已满」、末条身份分三类（本轮/
  `replay-conflict`/基线末条）。期望值从场景表现算，表加场景自动覆盖；
  `window == MAX_ROUNDS` 防默认值漂移。
- **失败形状 × 大预算（R126）**：`fetched-failure-shape-hook-at-8` 把
  失败形状夹具放进 9 次尝试链。大预算（R124）与失败形状（R119）此前
  各自成立，全过形状的 `failed=0` 会让「长链里计数被重算」完全隐形
  （R116 教训）；这条交叉把 `total=4/failed=1` 的内容指纹与逐场景
  `first_failure` 钉在 `attempts=9` 的路径上。
- **写回幂等在回放链路成立（R127）**：no-change 与 metrics-missing 此前
  只有 writeback() 层用例；replay 每次从源仓克隆全新沙箱，去重路径没被
  端到端走过。R127 在真实 CLI 上钉住：已入库 run_id 重放 → 退 0、
  `push_attempts=0`、历史不多出第二轮；metrics 缺失 → 退 0、零写入。
  实现细节：种子条目必须由 `history.record` 写出（序列化格式不同会让
  「字节不变」永远不成立），`_same_observation` 忽略 `exported_at`。
- **语义指纹截断（R128）**：`SEMANTICS_TEXT_LIMIT=160` 自 R112 零覆盖。
  两半各钉一边：展示行截到 160+`…` 且全文不进日志；history 里的
  `first_failure` 保留全文。期望钉死字面 160——变异 M3 实测：自引用
  常量会让「LIMIT 改小」静默通过，展示参数漂移必须先改用例。

### 10.10 可观测性不得被坏数据判死（R130）

`e2e_retry_summary.py` 的契约是「metrics 缺失或损坏 → 可见说明 + 退出 0」，
但 R74 只守住了缺文件 / JSON 坏 / 顶层非对象三种异常。内层字段坏会抛
`AttributeError`/`ValueError`：`scenarios` 是对象会迭代出字符串键、条目是
`None` 会调用 `.get`、`attempts` 是 `"2"` 会让 `int()` 抛错；`passed: true`
还会被静默渲染成「通过 1」。CI 里该步骤是 `if: always()`——e2e 判红后
summary 再以 traceback 失败，真正的 e2e 结论会被第二层错误淹没。

R130 把同一契约补到内层：`render` 先过 `_count` / `_scenarios`，坏形状抛
`SummaryShapeError`，`main` 转成一条 `_e2e metrics 形状无效（path）：…_`
并退出 0。`bool` 与负数都被拒绝（`True` 不能冒充一次通过/重跑），缺省字段
仍按 0 渲染（保留 R74 的兼容行为）。`_cell` 的竖线/换行转义同时补上首个
用例。这里**不判 metrics 的业务有效性**——计数矛盾仍由 `record`/`check`
在写回侧以退出 4 处置；摘要只保证「不崩、不静默」。

### 10.11 报告层：单行与写失败不得判死（R131）

`ci_reporting.py` 是 R98 集中出来的唯一实现：三个 CI 脚本共用「一行
summary + 一份机读 JSON，且写失败只告警、不改判决」。它此前零直接用例，
现有覆盖都从 `writeback()` / `fetch()` / `replay` 间接经过，只走单行
detail 的 happy path。

两处会把展示层变成判决层。第一，`_git_checked` 把 git stderr 整段塞进
`WritebackError`，`fetch_ci_artifact` 把 HTTP body 截 300 字符塞进
`detail`——二者都可能是多行；直接拼进 summary 会伪造出新的列表项/段落，
读者分不清哪条是脚本写的结论。第二，payload 一旦混入 `Path` 等不可
序列化对象，`json.dumps` 的 `TypeError` 会逃出 `emit_result`，让已经
成功的主判决以 traceback 收场。孤立代理字符还会让 `write_text` 抛
`UnicodeEncodeError`，两条写路径此前都未接住。

R131 的处置：`_one_line` 把 summary 三个字段的 CR/LF 压成空格（机读 JSON
的 `detail` 保持原文）；`emit_result` 先序列化再开临时文件，`TypeError` /
`ValueError` 转成 `结果工件序列化失败（path）：…` 后返回；`emit_summary`
与 `emit_result` 的写块都补 `UnicodeError` 降级。空 `GITHUB_STEP_SUMMARY`
仍按「没有 summary」处理，不是当前目录。这里不转义 Markdown 元字符——
`run_id` / `reason` 是固定类别与数字 run id；本轮只保证结构不被换行破坏。

### 10.12 发版验收：判决不得是 assert（R132）

`verify_release.py` 是发版前的判决脚本：产物 sha256、minisign key id、
ed25519 验签（blake2b-512 预哈希）、`tauri.conf` 版本与 updater 公钥、
`latest.json` 的 version/url/signature 三项。它此前**十处判断全是裸
`assert`**——`python -O` 会把整段删掉，脚本仍打印 `ALL CHECKS PASSED`
并退 0。这不是风格问题：`assert` 是调试断言，解释器有权在优化模式下移除，
而发版验收的结论必须无条件执行。R132 起判断一律走 `_require`（显式抛
`VerificationFailure`），`-O` 下同一份坏产物仍退 1。

坏输入按「有没有作判定」分类，互不冒充：

- **4 形状无效**（能读到，但结构不对，没能比较）：空 `.sha256`、首列不是
  64 位十六进制、外层/内层不是合法 base64、minisign 首行不是注释、
  sig blob 不是 74B、pubkey blob 不是 42B、`tauri.conf` 不是 JSON、
  `latest.json` 顶层/`platforms`/`windows-x86_64` 结构不对；
- **2 环境或用法**（没作判定）：缺资产文件、公钥读不开、`--tag` 为空、
  `latest.json` 网络不可达/读不出；
- **1 判了不合格**：sha256 不符、key id 不符、验签失败、`tauri.conf`
  版本或公钥不符、`latest.json` 三项任一不符。

**没有 8**：这里没有判据算术，算不下去的形态都归 4；**也没有 3**：
发版验收不存在「样本不足」。与 #10 的分界是：`_require` 只表达「判决为
假」，不捕获 `ArithmeticError`；没预料到的异常仍以 traceback 退出，
不会被误分类成 2/4。

### 10.13 导航层引用判据：可解析，或带归档标记（R133）

`tests/test_docs_navigation.py` 把三份活文档（`PROJECT_INFO.md` /
`HANDOVER_INDEX.md` / `humanware-helper-contract.md`）对已归档 HANDOVER
文档的具体引用钉成判据：

- **可解析**：`HANDOVER_ROUND<n>.md`（n 为纯数字）与 `docs/HANDOVER.md`
  必须能在 `docs/` 下解析到。纯数字约束天然豁免区间写法
  （`HANDOVER_ROUND15..22.md`）与占位符（`HANDOVER_ROUNDn.md`）——
  那两类是记法，不是引用；
- **归档标记**：引用所在行出现「归档」「已删」或 `git show <sha>`
  即视为有意指向史料（取回指引），不算失效；
- **登记表豁免**：`HANDOVER_INDEX.md` §6.3 本身就是失效引用的登记表，
  扫描跳过该小节；小节标题改名会让定位失效并判红（钉测里有显式断言）。

配套两条不变量：索引 `[md]` 链接集合 == 磁盘交接文档集合（新交接文档漏
登记索引即红，§6.4.3 式的「主题未登记」从此靠钉测防复发）；每份交接文档
H1 必须是 `— Round <n>（<主题副标题>）` 且 n 与文件名一致（§6.4.4 的
19 份缺副标题已在本轮补齐）。

边界：本判据是**导航层**的（引用指得到、登记齐、标题可读），不判文档
内容正确性；历史交接文档里对删除事件的记载是有意史料，永不扫描。

### 10.14 五轮收口（R130–R134）

R130–R132 在代码三面证明同一条纪律：展示层坏数据可见不判红（R130）、
报告层降级不判死（R131）、判决不得被 `-O` 静默删除（R132）；R133 把纪律
推到第四面——交接文档导航层（引用可解析或带归档标记、索引覆盖齐、标题
带副题，判据见 §10.13）。五轮零生产代码改动，生产 `DEFAULT_ATTEMPTS=3`、
`MAX_ROUNDS=80`、GC dry-run/7 天不变。写回 54→63（9 个 run 全部与
history.json 对齐；第 59 条 `ci-41826379385` 为 R132 前过路 run，无轮次
文档，账型见索引 §6.2）。

R135 把 §10.13 的导航层判据扩到 CI 闸门本身：ci.yml 顶层 job 键集合
**恰等**八个在册 job（矩阵展开 10 个 run，与索引 §1「CI 10 job」同一把
尺），欠引用 job（frontend 零测试引用、windows-backend 引用最少）的
runs-on 与关键步骤在场。新增 job 必须显式改清单并在 handover 记账——
名单判据的「改清单要走明路」是特性，不是负担。

R136 把导航层判据扩到账本之间：history.json 与 git bot 提交双向恰等
（按 run_id 形状取集合，R93 前无 source 标注的 legacy 条目也在账），
逐条形状（计数 int、passed+failed==total）与账序（唯一、exported_at 单调）
一并钉住；时间戳形状 run_id 恰好 1 条（第 1 条 legacy 种子）。浅检出下
判据显式红而非 skip——CI 两 backend 已 fetch-depth: 0。

R137 的 S 系判据把索引 §1 三行快照钉到磁盘实况：交接文档份数与轮次区间、
写回 K 与末条 id（与 R136 的 H3 双账恰等互补）、用例数用 `pytest
--collect-only` 确定性导出（前提：无模块级 importorskip，实测为零）。
backend job 在自己的提交树上跑测试，bot 写回提交不改已检出树——严格
恰等成立，无需竞态余量。

R138 补一行（§10.12 同账延伸）：RELEASE_SOP §5 的退出码判决表与
`verify_release.py` 的 `EXIT_*` 常量由 `test_release_sop_contract.py`
钉成同账，锚点是脚本输出字面前缀（`[fail]`/`[error]`/`[shape]`/
`ALL CHECKS PASSED`）——改任何一侧，另一侧判红。

### 10.15 五轮收口（R135–R139）：流程资产自描述

五轮把五处「靠人记」变成机判：CI job 清单恰等（R135）、history.json 与
git bot 提交双账恰等（R136）、索引 §1 三行快照 = 磁盘实况与收集数
（R137）、SOP 判决表与 `EXIT_*` 常量同账（R138）、外加 CI 两 backend 全
历史检出（R136）。判据家族统一形态：**锚点选在「改了就必须连动文档」
的字面上**（job 键名、run_id 形状、输出前缀、`[md]` 链接、H1 副标题），
漏连动即红。生产默认值不变；写回 64→68+。

R140 把引用面判据扩到 scripts/：孤儿（V1：三面语料零提及且无豁免登记）、
ci.yml 引用可解析（V2a）、桌面管线缺失引用冻结（V2b）。锚点是文件名
字面——脚本改名/删除/新增都必须连动三面之一或显式改清单。

R141 把 skip 自述钉成判据：tests/ 的每个 `pytest.mark.skip[if]` 标记
必须带非空 reason、每个 `pytest.skip()/fail()` 调用必须带非空消息
（平衡括号提取，无参调用不逃逸）。扫描器语料排除自身文件——扫描器的
docstring 里有 skip 字样，自扫自咬是 R141 首跑实测。

R142 的 B 系判据把 PROJECT_INFO 叙事账钉住：每轮专述 bullet（B1，豁免
{33,34,35}）与分节账本段单调（B2，floor 23/41/112）。章节结构（叙事
三层 + 历史锚）由实测得出并写进判据 docstring——改章节结构必须连动。

R143 的 W 系判据把依赖双源钉住：requirements.txt 每包（extras 剥离）
必须在 requirements-dev.lock（W1），`==` 钉版逐字同账（W2）。闭包超集
与范围规格不在射程；一边升版另一边没跟会当场红。
