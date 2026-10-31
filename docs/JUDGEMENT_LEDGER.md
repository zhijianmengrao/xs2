# 判据全景登记（Judgement Ledger）

> 本文回答 R63 §9-2 挂账的问题：**「R63 的预算式能不能迁移到别的阈值」**。
> 结论先说：**不能直接迁移**——它只对「两个实测量的比值 ≥ r」且偏移同时加在
> 分子分母上这一种形态成立。下面把十条判据逐条登记，并写明每条自己的容忍量、
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

## 2. 逐条登记

| # | 判据 | 位置 | 类别 | 容忍量 | 可复算边界 | 盲区 | 码 |
|---|---|---|---|---|---|---|---|
| 1 | 真实失败率 vs 政策上限 | `check_live_snapshot_gate.py::evaluate`（`--fail-if-above 8`） | 政策型 | 8 个百分点 | 区间下界 > 8 才红 | 阈值是政策，不随数据变；下界宽度由样本量决定 | 1 |
| 2 | 历史基线回归 | 同上（`--fail-on-regression`） | 偏移型 | 3 个百分点（`REGRESSION_MARGIN`） | 当前 ≥ 基线 + 3 且下界 > 该值 | 一个 workflow 变坏会被其余摊薄（由 #3 补） | 1 |
| 3 | per-workflow 回归 | `check_per_workflow_regression` | 偏移型 | 10 个百分点（`--margin`，**必须同时是基线精度余量**） | 可判 + 计数不变 ⇒ `normal`；阈值 = 基线 + 10 | 阈值小于基线精度时说不出 `normal`（反事实见 §4）；基线太薄判不了 | 1 |
| 4 | per-workflow 失败率（留一法） | `check_per_workflow_rate` | 偏移型 | margin 10 | 与其余 workflow 的合并基线比 | 默认恒退出 0，只有 `--fail-on-exceeds` 才判 | 1 |
| 5 | 样本量厚度 | `check_sample_size`（`--check-sample-size`） | 精度型 | margin 10 个百分点 | 95% 半宽 ≤ margin | `p → 0/1` 用单侧界；`n ≤ 4` 有轻微反转（已豁免并钉住） | 7 |
| 6 | 快照新鲜度 | `check_stale`（`--check-stale`） | 时钟型 | 7 天（`--max-lag-days` 默认） | 滞后 ≤ 7.0 天 | 只读「最新 run 文件」，与内容质量无关 | 5 |
| 7 | 快照覆盖度 | `check_coverage`（`--check-coverage`） | 政策型 | 无 | 真实跑过的 workflow ⊆ 快照 | 只能判「漏了哪些」，判不了比例 | 6 |
| 8 | e2e 退避形状（两/三/四段） | `e2e_workflow_stub.py::_rising_shape_violations` | 偏移型（逐段、非对称） | 欠睡 0.05s / 超睡 0.30s（**每次尝试**）；判红重跑 1 次，任一次通过即通过（R68） | 容差 < 最小相邻配置差 0.4s（`judgeable`） | 容差 ≥ 相邻差时分不出「下标错一位」；容差内看不出来；**两次都判红才算红** | 1 |
| 9 | e2e 退避幅度（单点） | `scenario_retry_backoff_is_honoured` | 偏移型（差分） | 多出 ≥ 0.7s（配置 1.2s）；同样在重跑集合里（R68） | 两次运行相减，绕开固定开销 | 只判一个值，对形状失明 | 1 |
| 10 | 判据算术失败 | `_run_judgement`（六个派发分支） | 不是判据 | — | 捕获 `ArithmeticError` / `ValueError` | 只把「算不下去」与「判了不合格」分开 | 8 |

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
| 3 | 无样本 | 重导快照 | 全部读快照的模式 |
| 4 | 元数据漂移 | 重导快照（内容变了没重导） | 全部读快照的模式 |
| 5 | 快照过期 | 重导快照 | 仅 `--check-stale` |
| 6 | 覆盖度缺口 | 重导快照 | 仅 `--check-coverage` |
| 7 | 样本太薄 | 攒更多 run 再导 | 仅 `--check-sample-size` |
| 8 | 判据算术失败，**未作判定** | 修判据 | 全部（`_run_judgement` 统一套用） |

**1 与 8 必须分开**：1 是「有结论」，8 是「没有结论」。共用退出码时，读日志的
人会把一次崩溃读成「失败率突破政策」，两种处置（查数据 / 修判据）互相冒充。

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
| 7 天（新鲜度） | `--max-lag-days` 的默认值 |
| 本页「不能直接迁移」的答案 | `tests/test_judgement_ledger.py::test_ledger_answers_the_r63_migration_question` |

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
| 3 | 逐 workflow +10 | character 15/79 | 16/79 | `test_per_workflow_regression_margin_flips_at_the_registered_k` |
| 4 | 留一法 +10 | 基线 0/30, k=3/10 | 4/10 | `test_leave_one_out_margin_flips_at_four_failures` |
| 5 | 样本量 margin 10 | 零失败 29 次尝试 | 28 次 | `test_sample_size_margin_flips_between_28_and_29_attempts` |
| 6 | 新鲜度 7 天 | 滞后 7.0 天 | 7.1 天 | `test_freshness_flips_at_the_registered_days`、`test_freshness_default_is_the_registered_days` |
| 8 | 形状 −0.05 / +0.30 | −0.050 / +0.300 | −0.051 / +0.301 | `test_shape_tolerances_flip_on_both_sides` |
| 9 | 幅度 0.7s | extra 0.700s | 0.699s | `test_backoff_amplitude_flips_at_the_registered_minimum` |

#7（覆盖度）与 #10（判据算术失败）没有数字容忍量：#7 判的是集合关系，#10 不是
判据而是「算不下去」的分流。覆盖守卫
`test_every_numeric_tolerance_has_a_registered_flip_point` 保证「登记页出现数字」
与「登记了翻转点」互为充要。

三个**没有**被翻转点覆盖的量，如实写在这里：

- **2.64 个百分点**（入库快照的 95% 半宽）是**测量结果**，不是容忍量；
- **0.4s**（形状的相邻配置差）由场景配置决定，`RisingShapeSegmentBudget.judgeable`
  已把它写成不等式；
- **3 次**（连续 `undetermined` 的提示阈值）不改变任何退出码，不是判据。
