# DeterminFlow (xs2) 交接报告 — Round 80（元数据形状收尾：`totals` → 4、`history` 只报告且逐条）

> 本轮定位：R79 §7-1 / §7-2 与 §8-1 / §8-2 的两项挂账同族收尾（用户拍定
> **①+②**；④⑤⑥ 继续挂账）。落地形态：**一处生产代码重构（计数规则与容器
> 读取抽成共用件）+ 27 条用例 + 台账登记**。`src/` 与前端零改动。

## 1. 一句话结论

R79 把「读不开」收进唯一入口，剩下两块形状问题：`totals`（两条判据读它）与
`history`（四条判据读它）。实测 `totals` 的旧写法有**三种冒充 + 两种静默**：
`"junk"` → CLI 以 **1** 退出（冒充「判了且不合格」）、`"abc"` → **8**（冒充
「判据算术失败」）、`{"failed": true}` 与 `{"attempts": 20.5}` → **静默按
`int()` 转成 1 / 20，判决照常给出且日志里没有异常**。本轮把计数规则抽成
`_count_value_error`、容器形状抽成 `_count_block`，`totals` 与 `per_workflow`
（含此前漏掉的 `check_lead_time`）统一归 4；`history` 的畸形条目改为**逐条列出
「第 N 条：原因」**，四处文案共用一个格式器，**仍然只报告、不进退出码**（用户
拍定）。

## 2. 实测：旧脚本的退出码（不是推断）

本机探针（`_r80_probe.py`，同一份内容、只改 `totals`）：

| 形状 | 旧 `evaluate` | 旧 `--check-sample-size` | 修复后（两者） |
|---|---|---|---|
| `totals: "junk"` | 进程异常 → CLI **1** | 进程异常 → CLI **1** | **4** |
| `{"attempts": "abc"}` | 异常 → CLI **8** | 异常 → CLI **8** | **4** |
| `{"failed": true}`（内容恰有 1 次失败） | **0**（`int(True)`=1，静默） | 7（按 1/20 判薄，静默） | **4** |
| `{"attempts": 20.5}` | **0**（截断成 20，静默） | 7（按 2/20 判薄，静默） | **4** |
| `{"failed": -1}` | 4（内容复算不一致，碰巧对） | 4 | **4**（形状先拦） |
| 缺失 / `null` / `{}` / `[]` | 3 | 3 | **3**（不变） |

最危险的是 `true` 与 `20.5`：没有异常、没有 traceback，判决与「通过」一模一样。
`"junk"` 与 `"abc"` 至少还留下了异常痕迹，只是退出码把处置带偏。

`history` 侧旧行为只写「另有 N 条历史形状无效已跳过」——跳过本身仍发生，但
读日志的人无法判断该修哪一条。

## 3. 设计

### 3.1 计数规则只有一份（`_count_value_error`）

`per_workflow`、`totals`、`history` 三处原先各写一遍「能转成非负整数」，规则
并不一致：per_workflow 拒布尔（R75），history 的 `int(bucket.get(...) or 0)`
却把 `true` 算成 1、把 `1.5` 截断成 1。抽成一份之后规则统一：

| 输入 | 结论 |
|---|---|
| 非负整数 / 可转成整数的字符串（`"1"`） | 接受 |
| 布尔（`true` / `false`） | 拒绝——`int(True)` 是 1，但 `true` 不是计数 |
| 浮点（`1.5`） | 拒绝——`int(1.5)` 是截断，不是解释 |
| 负数 / `null` / 其它类型 | 拒绝 |

### 3.2 容器形状：缺失 3，非空非对象 4（`_count_block`）

| 情形 | 码 | 理由 |
|---|---|---|
| 缺失 / `null` / `{}` / `[]` | 3 | 没有可被冒充的计数；本机「还没导过快照」是预期状态 |
| 非空但不是对象（`"junk"` / `[1,2]`） | 4 | 读得开、形状不对；旧写法在 `per_workflow` 三处归 3（冒充「缺块」）、在 `totals` 两处抛 `AttributeError`（冒充 1） |

`check_lead_time` 此前没有形状校验（`"junk"` → 1、`"failed": "abc"` → 8），
本轮顺带收进同一套——它是第四条读 `per_workflow` 的判据，只是 R75 时还没加进来。

### 3.3 `history`：逐条原因，只报告

`snapshot_rounds` 的第二返回值从「计数」改成「逐条原因列表」（`第 N 条：…`），
计数由 `len()` 得到——两处各存一份迟早对不上。四处调用点
（`evaluate` 的回归层 / `check_per_workflow_rate` / `check_per_workflow_regression` /
`check_lead_time`）共用 `_invalid_history_note`：

```
另有 2 条历史形状无效已跳过（第 2 条：期望对象，实际是 str；第 3 条：per_workflow 为空）
```

`history` 本身不是数组（`"junk"`）同样只报告：旧写法静默当作「没有历史」，
而后面的判据会照常给出「只有当前这一轮」的结论，看不出历史块坏了。

**不改退出码**：被跳过的是过去轮次，当前判决不因此改变；这条由
`test_malformed_history_does_not_change_the_regression_verdict`（同一份快照，
加坏条目前后都是 1）与「四处同一句」用例共同钉住。

### 3.4 不做的事

- **不把 `history` 的畸形条目升级成 4**：用户拍定「只报告，不进退出码」。
- **不动任何判据算术与阈值**：本轮只碰形状校验与输出文案。
- **不改导出脚本**：它写的是合法形状；本轮修的是「读的人怎么对待坏形状」。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +212 / −57（2059 → 2214 行） | 新增 `_count_value_error` / `_totals_shape_error` / `_count_block` / `_history_entry_error` / `_invalid_history_note`；八处判据中的六处调用点收口 |
| `tests/test_live_snapshot_gate.py` | +227 / −6（**27 条**新用例；文件 195 → 222 条） | totals / 容器 / history 三组 + CLI + 共用守卫 |
| `docs/JUDGEMENT_LEDGER.md` | +53 / −0 | §6 五行、新增 §7.8 |
| `docs/PROJECT_INFO.md` | +1 行 | R80 轮次条目 |
| `docs/HANDOVER_ROUND80.md` | 新增 | 本文 |

**闸门脚本 md5 改变**：`03a4b09fafdd772a35834907dcfaff09` →
`8e13df177ce2e5606bf704354aa488ff`。

## 5. 变异验证（八次，`cp` 备份还原）

相关用例集 = 整份 `tests/test_live_snapshot_gate.py`（222 条）。每次还原后
`md5sum` 与备份逐字节相同（`8e13df17…`）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | 删 `evaluate` 的 totals 字段校验 | **6 failed** | totals 用例（字段形状 7 参数中的 5 个）+ 默认模式 CLI |
| 2 | 删 `check_sample_size` 的 totals 字段校验 | **6 failed** | 同上，CLI 换成 `--check-sample-size` |
| 3 | 计数校验器重新接受布尔 | **3 failed** | **三个族各一条**（per_workflow / totals / history）——共用校验器的直接后果 |
| 4 | 逐条原因丢掉位置（只留原因） | **9 failed** | 历史条目精确文案 + 四处共用句 + 计数规则 |
| 5 | 共用文案丢掉明细（退回「只数个数」） | **5 failed** | 四处共用句 + `history: "junk"` |
| 6 | 容器退回 `{}`（旧口径） | **6 failed** | `totals: "junk"` / `[1,2]` + 四条判据的非对象 `per_workflow` |
| 7 | `history` 非数组静默忽略 | **1 failed** | `test_non_list_history_block_is_reported_not_silently_ignored`（**唯一咬合**） |
| 8 | history 条目退回 `int()`（bool/浮点算 1） | **4 failed** | 计数规则 3 条 +「规则只写一份」守卫 |

**如实记录**：M1/M2 各自只咬字段形状，容器分支由 `_count_block` 单独挡——
所以「删掉一处校验」不会让 `"junk"` 用例红，这是两条独立防线，不是用例漏了。
M7 是唯一只红一条的变异，其余都在 3–9 条之间。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：新增 27 条（`-k` 选中 27 条、195 deselected） | **27 passed**（0.47s） |
| 相关集：`test_live_snapshot_gate` + `test_judgement_flip_points` + `test_judgement_ledger` + `test_ci_gate_wiring` | **258 passed**（6.89s） |
| 全量（本机，Low `S-1-16-4096`） | **2288 passed / 113 skipped / 0 failed**（141.67s） |
| 真机闸门（入库快照） | 默认 / `--check-sample-size` / `--check-per-workflow` / `--check-per-workflow-rate` / `--check-per-workflow-regression` / `--calibrate-lead-time` 全部 **0** |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| docker build / npm run build | 未跑（无生产与前端改动；CI 会跑 container-build） |

**对账**：总用例 **2374 → 2401**（+27）。Low `2288 + 113` = **2401**。
`tests/test_live_snapshot_gate.py` 由 **195 → 222**。

## 7. 未做与未验证的事（如实记录）

1. **`totals.runs` 不校验**：两条判据只读 attempts/failed，多校验一个没人用的
   字段等于给重导加一个不必要的失败点。
2. **`history` 的畸形条目仍不进退出码**（用户拍定），只报告。
3. **未重导快照**：`data/` 下 `run-*.json` 仍 **40 个**，最新
   `2026-10-28 08:34`；入库快照 `exported_at=2026-10-30T09:26:54`，保鲜判据
   比的是「快照滞后真实数据」，当前为负、未到期。
4. **本会话仍只有 Low profile**：113 skips，28-skip 未复现。
5. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。
6. **CI 没有新增步骤**：本轮改的是既有判据内部的形状分支，CI 已覆盖同一批
   `--check-*` 步骤。

## 8. 下一轮候选

1. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1，用户拍定继续挂账）：唯一能
   复现稳定 profile 的路径，风险最高（可能动 shell 正在用的命名对象）。
2. **趋势判红的前置研究**（R78 §2，挂账、不实现）：10 场景下不存在可判阈值。
3. **CI 回写历史**（R78 §8-6，挂账，明确不推荐）：需要 `contents: write`、
   会触发二次 CI。
4. **重导快照 / `p=1.0` 真实数据**：继续挂账，每轮查一次 run 数（本轮仍 40 个）。
5. **`totals` 与 `per_workflow` 的一致性交叉校验**：目前 totals 只与内容复算
   比、per_workflow 只与内容复算比，两者的**互相**一致性没有单独判据——把一次
   失败在两个 workflow 之间挪动时，两处各自都可能自洽。这是新发现的形状，
   尚未评估。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 提交、推送与 CI 核对

两次提交（`2d85b94` feat + 本文档提交，显式路径 add）后推送。CI run
**41268128901**（push，03:11:01 → 03:15:59，约 4m58s）五 job 全 `success`：

| 项 | 实证（下载日志解码后逐字比对） |
|---|---|
| 五个 job | backend（03:11:04–03:13:53）/ windows-backend（03:11:20–03:15:59）/ frontend（03:11:03–03:12:11）/ container-config（03:11:04–03:11:16）/ container-build（03:11:04–03:11:47）全部 `success` |
| ubuntu | `2336 passed, 65 skipped, 1 warning in 119.68s` = **2401** |
| windows | `2372 passed, 29 skipped, 1 warning in 211.26s` = **2401** |
| 新用例在 CI 真跑 | ubuntu 2309/65 → **2336/65**、windows 2345/29 → **2372/29**（各 **+27**） |
| 快照判据 | backend 第 7–14 步（自检 + 真实快照七步：闸门 / 回归 / 逐 workflow 回归 / 提前量 / 样本量 / per-workflow 报告 / 失败率门槛）全 `success`；windows 第 7–11 步同 |
| e2e / metrics | `[e2e] 10/10 场景通过`；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| e2e 趋势（R78 步骤） | backend 第 **17** 步 `e2e retry trend (history, read-only)` `success` |
| 前端 / 容器 | 前端 8 块 TAP `# pass` 求和 **490 / fail 0**；`容器镜像冒烟全部通过` |
| Desktop Windows / macOS | 未触发（该 SHA 下只有 CI 一个 run） |

`$GITHUB_STEP_SUMMARY` 正文 API 不提供，趋势表由本地同一个 `render_trend()` 逐字
验证（与 R74 §7-2 同一条限制）；CI 上能核到的是「这一步以 0 退出」。

补记提交 `307b3db`（纯文档）的 run **41268639618**（03:18:21 → 03:23:09，约
4m48s）同样五 job 全 `success`：ubuntu **2336/65**（102.86s）、windows
**2372/29**（221.16s）、前端 490/0、e2e 10/10 与上一个 run 逐项相同。文档提交
本身仍会触发 CI，回填链到此为止（与 R66/R77/R78/R79 同）。
