# DeterminFlow (xs2) 交接报告 — Round 75（畸形 per_workflow：退出码 4 不是 1，也不是 8）

> 本轮定位：R64「退出码不许互相冒充」家族的第三个形状——**被判的数据坏了**
> 曾被归成「判了且不合格」（1）或「判据算术失败」（8）。用户拍定三轮迭代
> （R73/R74/R75），本轮为第三轮。落地形态：**闸门脚本 + 测试 + 文档**；
> `src/` 生产代码未动，但 `scripts/check_live_snapshot_gate.py` 有真实修改。

## 1. 一句话结论

`per_workflow` 是手可改的入库文件。R75 复现两个畸形：

| 畸形 | 修复前 | 冒充的东西 |
|---|---|---|
| `"wf-a": "junk"` | `AttributeError`，CLI 退出 **1** | 「判了且不合格」→ 查供应商 |
| `"failed": "abc"` | `ValueError` → `_run_judgement` 归成 **8** | 「判据算术失败」→ 修判据 |

两者真正该做的都是**重导快照**。新增 `_per_workflow_shape_error()`，在漂移
检查之前校验三条 per-workflow 判据共用的 `per_workflow` 块，统一返回退出码
**4**；CLI 实测从 1/8 变为 4。

## 2. 最重要的一件事：按「原因」分流，不是按「异常类型」分流

R64 引入 8 的理由是：`OverflowError` 让进程以 1 退出，与「政策突破」同码，
两种处置互相冒充。所以 8 = 「判据自己算不下去」（修判据），1 = 「判了且不
合格」（查数据/供应商）。

本轮的两个畸形都不属于这两类：

- `"junk"` 抛 `AttributeError`，`_run_judgement` **不捕获**它——进程以 1
  退出，读日志的人会去查供应商；
- `"abc"` 抛 `ValueError`，被 `_run_judgement` 捕获成 8——读日志的人会去
  修判据，而判据没坏。

`ValueError` 在 R64 的捕获清单里是对的（算术失败确实可能是 `ValueError`），
但「异常类型」不能替代「异常原因」。形状校验把数据错误在进入算术之前拦下来，
才让 8 继续只表示「判据算不下去」。这条与 R64 的教训是同一枚硬币的两面。

## 3. 设计

1. **`_per_workflow_shape_error(recorded) -> str | None`**：
   - bucket 必须是对象（`"junk"` → 报 `期望对象，实际是 str`）；
   - `runs` / `attempts` / `failed` 必须是非负整数：**数值字符串接受**
     （`"1"` 是手改快照里可解释的写法，且旧代码就接受）、**布尔拒绝**
     （`true` 不是计数）、**负值拒绝**；
   - 返回第一条问题，合法时 `None`。
2. **`_metadata_shape_message(error)`**：统一文案——「这不是判据算术失败，
   也不是不合格——重导一次即可修复」，与漂移的处置（重导）一致。
3. **三条判据接入**：`check_per_workflow` / `check_per_workflow_rate` /
   `check_per_workflow_regression` 在 `recorded` 非空校验之后、内容复算与漂移
   之前调用；`_per_workflow_drift` 因此继续只面对已校验的输入。
4. **测试**（`tests/test_live_snapshot_gate.py` +6）：
   - 参数化 4 种畸形（字符串 bucket / `failed:"abc"` / `failed:true` /
     `failed:-2`）× 三条判据 → 全部退出 4 且消息含「形状无效」与 workflow 名；
   - CLI `main()` 对字符串 bucket 返回 **4**（钉住不再以 1 崩、也不以 8 退出）；
   - 数值字符串 `"1"` 仍走到判决（退出 0），钉住没有过度拒绝。
5. **登记页**：§5 退出码 4 的处置补「形状无效」；§6 增一行；新增 §9
   （两种冒充的前后对照 + `_per_workflow_shape_error` 的规则）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | **+55 / −0** | 形状校验 + 三条判据接入 |
| `tests/test_live_snapshot_gate.py` | **+54 / −0** | 6 条用例（4 参数 + CLI + 数值字符串） |
| `docs/JUDGEMENT_LEDGER.md` | **+18 / −1** | §5 / §6 / 新增 §9 |
| `docs/PROJECT_INFO.md` | **+1 行** | R75 轮次条目 |
| `docs/HANDOVER_ROUND75.md` | 新增 | 本文 |

**闸门脚本 md5 改变**：`7a329d3a…` → `1d0e0ac0…`。本轮**不是**零生产代码
改动轮（只有 `scripts/` 下的闸门，`src/` 未动）；因此 CI 仍然照常跑全量五
job，`container-build` 也会重新构建。

## 5. 变异验证（五次，`cp` 备份还原）

跑的是全部相关用例（基线 **197**）：

| # | 变异 | 实测 |
|---|---|---|
| 1 | 失败率判据不做形状校验（`shape_error = None`） | **5 failed**：4 个参数化用例 + CLI |
| 2 | 形状错误归成 `EXIT_NUMERIC_FAILURE`（8） | **5 failed**：同上 |
| 3 | 布尔被当作整数接受 | **1 failed**：`[bucket2]`（`failed:true`） |
| 4 | 数值字符串被拒绝（只接受 JSON 整数） | **1 failed**：`test_numeric_string_counts_are_still_accepted` |
| 5 | 只让失败率判据校验（样本量/回归跳过） | **4 failed**：4 个参数化用例 |

每次还原后 `md5sum` 与备份逐字节相同（`1d0e0ac027f3732fad7586cf81ac05fa`），
还原后相关集 **197 passed**。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`tests/test_live_snapshot_gate.py -k "malformed or numeric_string"` | **10 passed**（含既有 malformed 用例） |
| 相关集：msys + ledger + flip points + live snapshot gate | **197 passed**（5.82s） |
| 全量（本机，Low `S-1-16-4096`） | **2213 passed / 113 skipped / 0 failed**（131.20s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未本地跑（闸门不在 e2e 链路上；CI 会跑 container-build） |

**对账**：总用例 **2320 → 2326**（+6）。Low `2213+113` = **2326**。

## 7. 未做与未验证的事（如实记录）

1. **只校验了 `per_workflow`**：`history` 的畸形条目由
   `_history_entry_counts` 跳过并计数（R58 起），不走本校验；它不参与判决，
   不会冒充结论。
2. **浮点计数由同一分支拒绝，但未单独入参**：`1.5` 会命中
   `not isinstance(value, (int, str))`；参数化里没有这一格（布尔、负值、
   非数值字符串已各占一格）。
3. **`_per_workflow_drift` 仍假定输入已校验**：三条生产调用方都先调用形状
   校验；直接以畸形 dict 调用它的测试/脚本仍会抛异常（这是内部契约）。
4. **本会话仍只有 Low profile**：28-skip 未复现。
5. **未重导**：`run-*.json` 仍 **40 个**，最新 `2026-10-28 08:34`。
6. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。

## 8. 下一轮候选

1. **`check_per_workflow` 的 3/4 分支对齐**（R73 §8-3）：它没有数字翻转点，
   只做三条 exit-3 分支与顺序断言；本轮的形状校验已覆盖它的一部分。
2. **重跑率的跨 run 趋势**（R74 §8-3）：需要先决定 metrics 存哪
   （CI artifact / 入库），不是纯测试改动。
3. **有新 run 后再重导**：唯一被外部数据卡住的候选，已连续多轮。
4. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
5. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：可能动命名对象，风险最高。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

（推送后补记）
