# DeterminFlow (xs2) 交接报告 — Round 130

> 单 profile。新五轮连推（R130–R134）第 1 轮：**e2e step summary 的坏数据
> 边界**。`e2e_retry_summary.py` 的说明承诺「metrics 缺失或损坏 → 可见说明 +
> 退出 0」，但 R74 只守住顶层三种异常；内层坏形状会以 traceback 把
> `if: always()` 的可观测性步骤判红。生产 e2e 判定与 metrics 生成零改动。

## 1. 一句话结论

- 实测 4 类内层坏形状会抛异常：`scenarios` 为对象/字符串（`AttributeError`）、
  条目为 `None`（`AttributeError`）、`attempts` 为 `"2"`（`ValueError`）、
  计数为 `"10"`（`ValueError`）；此外 `passed: true` 会被静默渲染成「通过 1」。
- 新增 `SummaryShapeError` + `_count` / `_scenarios`：渲染前只校验真正要读的
  字段；`main` 捕获后打印 `_e2e metrics 形状无效（path）：…_` 并退出 0。
- 新增 `tests/test_e2e_retry_summary.py`（9 个函数 / 17 条）：坏形状 10 格、
  表格转义 1 格、0 场景与缺字段 2 格、顶层异常 2 格、用法 1 格、
  `render` 直接抛异常 1 格。
- **+17 → 总用例 2755**；本机全量见 §5。

## 2. 为什么是这一轮

R74 的说明写得很清楚：「metrics 缺失或损坏时打印一条可见的说明并退出 0；
静默吞掉会让人把『没有数据』误读成『0 次重跑』」。但实现只在顶层做了三件事
——文件存在、JSON 可解析、顶层是对象。渲染真正要读的 `scenarios` /
`attempts` / 计数完全没有守卫。

CI 里这一步是 `if: always()`：e2e 判红后，summary 仍要执行。如果 metrics
恰好是内层坏形状，traceback 会成为日志里的第二层错误——真正的 e2e 结论被
它盖住，排查的人先看到的是「摘要脚本崩了」，而不是「e2e 哪条场景红了」。
展示层没有判决权，也不该有把 job 判红的能力。

## 3. 实现

### 3.1 校验点

- `_count(payload, field)`：缺省/`None` 按 0（保留 R74 兼容行为）；出现时
  必须是 >=0 的整数。`bool` 是 `int` 子类，显式排除——`passed: true` 不能
  冒充一次通过。
- `_scenarios(payload)`：缺省/`None` 按空列表；非列表、条目不是对象、
  `attempts` 是 `bool`/非整数/负数，全部抛 `SummaryShapeError`。
  `name` / `first_failure` 仍按字符串展示（`str(... or "")`）。
- `render` 在拼表前调用上面两个校验；坏形状不会产出「半张表」。
- `main` 只捕获 `SummaryShapeError`，打印一条可见说明并返回 0；参数个数
  错误仍返回 2（用法错误，不是数据损坏）。

### 3.2 刻意不做的

- **不判 metrics 的业务一致性**：`retried` 与「attempts>1 的场景数」不符、
  `total` 与 `len(scenarios)` 不符，都仍按原样展示。那是 `record` / `check`
  在写回侧的退出 4 判据，摘要只保证「不崩、不静默」。
- **不改 metrics 生成端**：`e2e_workflow_stub.py` 的 payload 形状不变。

## 4. 判据台账

- §6 复核表补一行（R130 的七条用例）；
- §10.10 新增「可观测性不得被坏数据判死」一段。

## 5. 验证

- 定向：`tests/test_e2e_retry_summary.py` + `tests/test_ci_e2e_stub.py`
  **88 passed**（4.13s；新文件 17 条 + 原 stub 71 条）。
- 本机全量（`core.symlinks=true`，同 R124/R129 口径）：
  **2727 passed / 28 skipped / 0 failed**（2755 条，484.40s）。
- 环境说明：首跑时系统 git 为 `core.symlinks=false`，
  `tests/test_plugin_store.py::test_symlink_cannot_escape_checked_out_package`
  单红（`DID NOT RAISE InvalidPluginPackageError`）。单独复跑仍红；用
  `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.symlinks GIT_CONFIG_VALUE_0=true`
  重跑即绿——与 R124/R129 记录的「便携 MinGit + core.symlinks=true」一致，
  不是本轮回归。
- 变异 **M1–M6 6/6**：

  | 变异 | 改动 | 红 |
  |---|---|---|
  | M1 | 非列表 `scenarios` 静默按空处理 | 2 |
  | M2 | 表格单元格不转义 | 1 |
  | M3 | 坏形状退出 1（把可观测性判红） | 10 |
  | M4 | `bool` 冒充计数 | 1 |
  | M5 | 负数 `attempts` 放行 | 1 |
  | M6 | 条目不查对象（原崩溃路径） | 1 |

  每次 `cp` 还原后 sha256 与备份逐字节相同
  （`7772efcd53aeff69df971f289d5aeb74871f8f53cd0b3ef25d1a65a54cc22bad`）。
  日志：`_r130_m1.log` … `_r130_m6.log`。

## 6. CI

- 待确认后提交/推送；推送后回填 run id、两平台 job 结果与写回历史。

## 7. 边界与遗留

- 摘要仍是「只展示」：不判趋势、不判 metrics 业务有效性；业务闸门仍在
  `record` / `check`（退出 4）与 e2e 步骤自身退出码。
- 本次只动 `scripts/e2e_retry_summary.py` 与测试；`src/`、`web/`、CI YAML
  零改动。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`scripts/e2e_retry_summary.py`、`tests/test_e2e_retry_summary.py`、
  R130 文档、PROJECT_INFO、JUDGEMENT_LEDGER。生产代码零改动。
