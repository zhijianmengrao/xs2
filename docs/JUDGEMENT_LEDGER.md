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
| 4 | 元数据漂移 | 重导快照 / 重录历史（内容变了没重导 / 形状无效 / 路径读不开 / 顶层不是对象；路径被占时先清理再重导） | 全部读快照的模式、e2e 重跑历史（读不懂 / 形状无效 / 计数矛盾） |
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
| e2e 重跑历史的窗口 **20 轮**（R78） | `scripts/e2e_retry_history.py::MAX_ROUNDS` + `tests/test_e2e_retry_history.py::test_record_trims_to_the_window` |
| 同一 `run_id` 覆盖而非追加（R78） | `tests/test_e2e_retry_history.py::test_record_replaces_the_same_run_id_instead_of_appending` |
| 「1 次重跑 = 10 个百分点」是**算出来的**（R78） | `test_check_computes_the_resolution_from_the_latest_total`（20 个场景时必须是 5 个百分点） |
| 「本步不判趋势」必须写进输出（R78） | `test_check_says_it_has_no_judgement_power` |
| 坏历史 → 4（不是 3/1/8，R78） | `test_check_exits_four_on_unparseable_history_not_eight`、`test_check_exits_four_on_contradictory_counts`、`test_check_exits_four_on_duplicate_run_ids` |
| 跳过坏条目继续渲染会被咬住（R78） | `test_check_rejects_bad_json_even_when_one_entry_would_render` |
| CI 只读校验**入库的**历史（R78） | `tests/test_e2e_retry_history.py::test_ci_checks_the_committed_history_file` |
| 本页「不能直接迁移」的答案 | `tests/test_judgement_ledger.py::test_ledger_answers_the_r63_migration_question` |
| msys 归因不写完整性级别（R71） | `tests/test_msys_attribution.py::test_skip_reason_names_the_mechanism_and_never_an_integrity_level` |
| 「签名 / 模块 / 探针」真值表（R71） | `tests/test_msys_attribution.py::test_skip_truth_table_has_exactly_two_independent_variables` |
| 「无签名 ≠ 环境问题」（R71） | `tests/test_msys_attribution.py::test_probe_flips_on_the_msys_signature_only` |
| 允许转 skip 的 6 个模块（R71） | `tests/test_msys_attribution.py::test_skip_surface_is_exactly_the_six_transport_modules` |
| 归因用例的失败不被吞（R71） | `tests/test_msys_attribution.py::test_attribution_failures_are_never_converted_into_skips` |
| 113 skips 的四行实测矩阵（R70 §6.1） | 本页 §8：High 2189/113 与**真降** Low 2189/113 逐字相同 |

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
**2279 passed / 28 skipped**、真降 Low **2194 passed / 113 skipped**——28-skip
profile 在 High 下又出现了。两次观测合起来才是完整的结论：**能不能挂接那个共享
对象会自己变**（谁先创建/挂接、DACL 如何），既不跟令牌 IL 绑定，也不在一台机器
上保持恒定。所以：

- **113 skips 不是令牌完整性级别的函数。** 就「转 skip」这条判据而言，判别变量
  是探针是否复现 `NtCreateDirectoryObject` 签名——也就是本会话能否挂接那个共享对象。
- R17 的结论（Low 被拒）在**那次会话**是实测事实，但它不是通用归因；R70 起文案
  只写机制（「cannot attach this session's shared msys-2.0 object」），不写 IL。

判据本身（`_msys_skip_applies`）只有两个自变量：

| 失败调用带签名 | 模块 ∈ 6 个传输模块 | 探针复现签名 | 结果 |
|---|---|---|---|
| 是 | 任意 | 不查 | **转 skip**（识别环境，不识别模块） |
| 否 | 是 | 是 | **转 skip**（模块内失败无法归因） |
| 否 | 是 | 否 | 照常失败 |
| 否 | 否 | 任意 | 照常失败 |

**登记这个判据的同时必须登记它的代价**：skip 不等于通过。113 条用例在本会话
**没有执行**；上表只说明「那批失败带 msys 签名或落在传输模块内」，不说明这些
用例的断言成立。复现 28-skip profile 需要能挂接共享对象的会话状态——R70 §7-1
的根因未追查，R71 按用户拍定只改归因措辞、不追根因（B1）。

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
