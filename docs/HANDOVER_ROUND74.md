# DeterminFlow (xs2) 交接报告 — Round 74（重跑频率：从 grep 日志到机读指标 + step summary）

> 本轮定位：R68 §7-4 挂账的「重跑频率的可观测性」。用户拍定三轮迭代
> （R73/R74/R75），本轮为第二轮。落地形态：**e2e 测试脚本 + CI + 测试 + 文档**，
> `src/` 生产代码零改动。

## 1. 一句话结论

`attempts` / `first_failure` 此前只写进日志正文，「重跑有多频繁」只能靠 grep。
本轮把它们整理成稳定 schema：e2e 脚本新增 `metrics_payload()` 与
`--metrics-json PATH`，汇总行打印 `[e2e-metrics] ...`；新脚本
`scripts/e2e_retry_summary.py` 把 JSON 渲染成 CI step summary 的 markdown 表，
`if: always()` 保证 e2e 失败时也看得到重跑次数。本地实跑 10/10、metrics 为
`retried=0`（本轮无场景级重跑），summary 渲染正确。

## 2. 最重要的一件事：summary 不判失败，但也不许沉默

这个脚本的职责只有一个：把 metrics 变成可读的表格。它的三种异常——
**文件不存在 / JSON 解析失败 / 顶层不是对象**——都必须打印一条可见说明并退出
0：静默吞掉会让人把「没有数据」误读成「0 次重跑」，而这正是本轮要消灭的
「只能 grep」状态。e2e 的判决仍由那一步自己的退出码承担，summary 步骤不改变
任何结论。

对应的测试钉住「缺失时打印『未生成』且退出 0」，而 CI 侧用 `if: always()`
覆盖「e2e 判红后没有后续步骤」的窗口。

## 3. 设计

1. **`metrics_payload(results)`**（纯函数）：
   ```json
   {"schema": 1, "total": 10, "passed": 10, "failed": 0, "retried": 0,
    "scenarios": [{"name": ..., "passed": true, "attempts": 1,
                   "first_failure": ""}]}
   ```
   `retried` 只数 `attempts > 1` 的场景；`first_failure` 原样保留（不截断，
   截断在渲染层做）。
2. **`write_metrics(path, payload)`**：父目录不存在就建（CI 用
   `$RUNNER_TEMP/e2e-metrics.json`）。
3. **e2e 汇总行**：无论是否给 `--metrics-json` 都打印
   `[e2e-metrics] total=… passed=… failed=… retried=…`，便于 grep 与日志对账。
4. **`scripts/e2e_retry_summary.py`**：读 JSON，输出
   `**e2e 重跑：N / M 个场景重跑**（总尝试 K 次，通过 P）`；只有
   `attempts > 1` 的场景进表（场景 / 尝试次数 / 第一次判红），表格单元格转义
   `|` 与换行。
5. **CI**：e2e 步骤加 `--metrics-json "$RUNNER_TEMP/e2e-metrics.json"`；新增
   `e2e retry summary (observability)` 步骤（`if: always()`）把渲染结果追加到
   `$GITHUB_STEP_SUMMARY`。
6. **测试**（`tests/test_ci_e2e_stub.py` +7，64 → 71）：payload 字段与计数 /
   0 重跑是明确 0 / 写文件建父目录 / `--metrics-json` 真的传到 `_run` /
   summary 渲染与缺失文件 / CI 接线（metric 参数 + always + 无 secrets）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/e2e_workflow_stub.py` | **+53 / −0** | metrics_payload / write_metrics / 汇总行 / CLI |
| `scripts/e2e_retry_summary.py` | 新增（70 行） | metrics → markdown |
| `.github/workflows/ci.yml` | **+9 / −1** | e2e 写 metrics + summary 步骤 |
| `tests/test_ci_e2e_stub.py` | **+106 / −0** | 7 条契约测试 |
| `docs/PROJECT_INFO.md` | **+1 行** | R74 轮次条目 |
| `docs/HANDOVER_ROUND74.md` | 新增 | 本文 |

**`src/` 生产代码零改动**：`scripts/check_live_snapshot_gate.py` md5 仍
`7a329d3a…`；`scripts/e2e_workflow_stub.py` 是测试装配脚本（R68 起同性质），
本轮其 md5 由 `a5104e69…` 变为新值。

## 5. 变异验证（四次，`cp` 备份还原）

跑的是 `tests/test_ci_e2e_stub.py`（基线 **71**）：

| # | 变异 | 实测 |
|---|---|---|
| 1 | `metrics_payload` 的 `attempts` 恒为 1 | **1 failed**：`test_metrics_payload_records_attempts_and_first_failure` |
| 2 | `retried` 改成 `attempts >= 1`（全算重跑） | **2 failed**：records + `test_metrics_payload_counts_zero_retries_for_a_clean_run` |
| 3 | CI e2e 步骤去掉 `--metrics-json` | **1 failed**：`test_ci_e2e_writes_metrics_and_renders_a_summary` |
| 4 | summary 步骤去掉 `if: always()` | **1 failed**：同一条接线测试 |

每次还原后 `md5sum` 与备份逐字节相同；还原后 71 passed。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`tests/test_ci_e2e_stub.py` | **71 passed**（3.40s） |
| 本机 e2e（带 `--metrics-json`） | **10/10 场景通过**；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| summary 本机渲染 | `**e2e 重跑：0 / 10 个场景重跑**（总尝试 10 次，通过 10）` |
| 全量（本机，Low `S-1-16-4096`） | **2207 passed / 113 skipped / 0 failed**（130.97s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| docker build | 未本地跑（CI 的 container-build 会跑） |

**对账**：总用例 **2313 → 2320**（+7）。Low `2207+113` = **2320**。

## 7. 未做与未验证的事（如实记录）

1. **只让单次 run 可观测**：没有历史/趋势（多次 run 的重跑率），那需要跨 run
   存储，属于下一层；本轮解决的是「一次 run 里重跑了几次、第一次为什么红」。
2. **summary 的内容只能在 CI 页面上看**：API 能给出步骤结论，但不提供
   `$GITHUB_STEP_SUMMARY` 正文；本机用同一 `render()` 做了逐字验证。
3. **Windows runner 不跑 e2e**（既有事实），因此 summary 步骤只在 ubuntu。
4. **本会话仍只有 Low profile**：28-skip 未复现。
5. **未重导**：`run-*.json` 仍 **40 个**，最新 `2026-10-28 08:34`。
6. **未跑 docker build / npm run build / 未重启 8021**：无生产与前端改动。

## 8. 下一轮候选

1. **畸形 `per_workflow` 元数据不得冒充「判了不合格」**：本轮计划中的 R75。
2. **`check_per_workflow` 的 3/4 分支对齐**（R73 §8-3）：它没有数字翻转点，
   只做分支与顺序断言。
3. **重跑率的跨 run 趋势**（R74 新增）：需要把 metrics 存进可累积的位置，
   先得决定「存哪」（CI artifact / 快照式入库），不是纯测试改动。
4. **有新 run 后再重导**：唯一被外部数据卡住的候选。
5. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
6. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：可能动命名对象，风险最高。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

（推送后补记）
