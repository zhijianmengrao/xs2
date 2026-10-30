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
| 3 | per-workflow 回归 | `check_per_workflow_regression` | 偏移型 | margin 10（CI 显式给 10） | `eligible` 由 `_failure_rate_precision` 决定 | 基线太薄的 workflow 判不了，且**不判失败** | 1 |
| 4 | per-workflow 失败率（留一法） | `check_per_workflow_rate` | 偏移型 | margin 10 | 与其余 workflow 的合并基线比 | 默认恒退出 0，只有 `--fail-on-exceeds` 才判 | 1 |
| 5 | 样本量厚度 | `check_sample_size`（`--check-sample-size`） | 精度型 | margin 10 个百分点 | 95% 半宽 ≤ margin | `p → 0/1` 用单侧界；`n ≤ 4` 有轻微反转（已豁免并钉住） | 7 |
| 6 | 快照新鲜度 | `check_stale`（`--check-stale`） | 时钟型 | 7 天（`--max-lag-days` 默认） | 滞后 ≤ 7.0 天 | 只读「最新 run 文件」，与内容质量无关 | 5 |
| 7 | 快照覆盖度 | `check_coverage`（`--check-coverage`） | 政策型 | 无 | 真实跑过的 workflow ⊆ 快照 | 只能判「漏了哪些」，判不了比例 | 6 |
| 8 | e2e 退避形状（两/三/四段） | `e2e_workflow_stub.py::_rising_shape_violations` | 偏移型（逐段、非对称） | 欠睡 0.05s / 超睡 0.30s | 容差 < 最小相邻配置差 0.4s（`judgeable`） | 容差 ≥ 相邻差时分不出「下标错一位」；容差内看不出来 | 1 |
| 9 | e2e 退避幅度（单点） | `scenario_retry_backoff_is_honoured` | 偏移型（差分） | 多出 ≥ 0.7s（配置 1.2s） | 两次运行相减，绕开固定开销 | 只判一个值，对形状失明 | 1 |
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

## 4. 退出码表

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

## 5. 这一页上的数由谁复核

| 数字 | 钉住它的地方 |
|---|---|
| 0/1/3/4/5/6/7/8 的**字面值** | `tests/test_judgement_ledger.py::test_ledger_pins_every_exit_code_value`（与脚本常量逐字对齐） |
| 1 与 8 不能共用 | `tests/test_live_snapshot_gate.py::test_numeric_failure_has_its_own_exit_code` |
| 3 个百分点（回归余量） | `tests/test_judgement_ledger.py::test_ledger_pins_the_regression_margin` + `REGRESSION_MARGIN` |
| 0.05 / 0.30 / 0.4（e2e 形状） | `tests/test_judgement_ledger.py::test_ledger_pins_the_e2e_shape_tolerances`、`tests/test_ci_e2e_stub.py::test_segment_budget_pins_the_two_tolerances` |
| 10 个百分点（margin 默认） | `--margin` 的默认值（脚本内 10.0），CI 六步显式或隐式使用 |
| 7 天（新鲜度） | `--max-lag-days` 的默认值 |
| 本页「不能直接迁移」的答案 | `tests/test_judgement_ledger.py::test_ledger_answers_the_r63_migration_question` |
