# DeterminFlow (xs2) 交接报告 — Round 84（failure_rate 登记 / p=1.0 真实数据 / F:→Low 根因）

> 本轮定位（用户拍定 R83 §9 的 1/2/3 项，第 4 项 CI 回写历史不做）：
> ① `totals.failure_rate` **登记为只读展示字段**（用户选的处置）；
> ② `p=1.0` **真实数据**验证（R54 起挂账）；
> ③ `F:` → Low 的**策略来源**（R81 §8-3 挂账，决定 C: 启动器处方是否可移植）。
> 落地形态：**一个生产文件（闸门脚本的登记清单）+ 测试 + 新入库 fixture + 文档**；
> 无 CLI 开关、CI YAML 零改动、`data/workflows` 只读。

## 1. 一句话结论

1. `failure_rate` 有两个副本（`totals` 与每个 `per_workflow` bucket），都只写不读。
   本轮登记进**一份可执行的清单** `_DISPLAY_ONLY_FIELDS`：守卫用例把六种坏值分别
   塞进两个副本，断言六个读计数入口的 `(退出码, 文案)` **逐字不变**。
2. 真实数据里确有 6 个 `failed == attempts` 的 run（build 5 + export 1，均 1 次尝试
   1 次失败）。导出的真实快照 6/6，`--check-sample-size` 退 **7**、`evaluate
   --fail-if-above 8` 退 **1**——R53 的 p=1.0 分支第一次由真实载荷走完全链。
3. `F:` → Low 的根因找到且可复现：**不是卷，也不是文件名/哈希，而是
   `F:\DeterminFlow x2` 整棵树带显式 Low 强制标签、子项继承**。同一份
   `python.exe` 放到无标签目录是 High；给该目录加 `icacls /setintegritylevel Low`
   后立刻变成 Low。R81 的「`F:` 上的可执行文件被强制降级」是误把目录树属性当成
   卷属性。

## 2. 主线 1：`failure_rate` 登记为只读展示字段

### 2.1 缺口（R83 §9-2 的原始记录）

`export_run_samples.py` 写两处 `failure_rate`（`:262-265` 每个 bucket、`:281-287`
totals），闸门脚本**零读取**——`grep failure_rate scripts/check_live_snapshot_gate.py`
只命中函数名 `_failure_rate_precision` 与文档字符串。R83 把 `runs` 收进计数表之后，
`failure_rate` 是同一份元数据里最后一个「写了没人看」的计数-派生字段。

### 2.2 为什么登记而不是删除或做判据

- **不并入计数表**：`_count_value_error` 只接受整数/整数字符串；`0.0392` 会让每一份
  入库快照在形状校验处被判「形状无效」（4）。
- **不做判据**：要比就得比「四舍五入后相等」——另一族脆弱算术（与台账 §7.3 的
  「门槛随共模偏移漂移」同类）。
- **不删除**：它是读者要的信息（28 run / 255 次尝试 / 3.92%），删掉只是把
  「没人读」变成「不存在」，与 R83 对 `runs` 的处置理由相同。

### 2.3 落地

- `_DISPLAY_ONLY_FIELDS = ("failure_rate",)`（`scripts/check_live_snapshot_gate.py`），
  注释写明上述三条理由，并声明它同时覆盖 `totals` 与 `per_workflow` 两个副本。
- `test_display_only_registry_is_structurally_excluded`：登记清单恰为
  `{"failure_rate"}`，且与 `_TOTALS_COUNT_FIELDS` / `_PER_WORKFLOW_COUNT_FIELDS`
  **无交集**——「只读」由结构保证，不是靠注释承诺。
- `test_failure_rate_is_display_only`：6 入口 × 2 副本 × 6 种值
  （`"abc"` / `true` / `3.7` / `0.99` / `null` / 整个删掉），基线先写一份正确的
  `0.0392`，每次变异后断言 `(code, message)` **逐字不变**。只比退出码抓不到
  「读了但只用在文案里」的入口。
- `test_committed_snapshot_carries_the_display_field`：真实快照必须带着它，
  否则守卫只是在测「字段不存在」。

## 3. 主线 2：p=1.0 的真实数据

### 3.1 真实数据的形状（本次查清）

`data/workflows` 40 个 run 中 **6 个是 `failed == attempts`**，全部是 1 次尝试
1 次失败（供应商流式超时）：

- build：`run-ff680fcd` / `run-c6105958` / `run-b4e622f8` / `run-6e0da8a3` / `run-58206be9`
- export：`run-7ec13269`

导出命令（只读源目录）：

```
python scripts/export_run_samples.py \
  --dest tests/fixtures/live_snapshot_all_failed --limit 10 \
  --run run-ff680fcd --run run-c6105958 --run run-b4e622f8 \
  --run run-6e0da8a3 --run run-58206be9 --run run-7ec13269
```

输出：`共导出 6 个 run …（6 次尝试 / 6 失败 / 100.00%）`，半宽告警 39.30 > 2
（默认只告警，退出 0；`--strict-half-width` 未加）。fixture 规模：run 文件合计
**10721 B**、meta **791 B**；`source_root=workflows`（真实导出，不是 synthetic）。

### 3.2 三个判决（真实载荷）

| 判据 | 结果 | 关键文案/数值 |
|---|---|---|
| `sample_size_margin_needed(6,6)` | **39.3038** | 全失败闭式 `1 - 0.05**(1/6)`；正态近似在这里算成 0 |
| `--check-sample-size`（margin 10） | **7** | 「全部失败时到 100% 的 95% 单侧距离 39.30 个百分点」「n=6」「约 29 次尝试」 |
| `evaluate --fail-if-above 8` | **1** | 「失败率 100.00%（n=6, 失败 6），95% 区间 [60.70%, 100.00%]…判超阈」 |

### 3.3 边界（如实记录）

- **n≥29 的自然全失败样本不存在**：本机全失败 run 只有这 6 个，全部 1 次尝试。
  要让这份快照在 margin 10 下合格需要 29 次全失败尝试——为一条判据故意跑坏 29 次
  真实工作流，代价与数据污染都不值得。所以这一项从「分支没有真实数据验证」改写为
  「分支已由真实数据验证；n≥29 的自然样本不存在，这是数据事实而不是缺口」。
- fixture 只含 2 个 workflow，`--check-coverage` 对它退 6 属设计内（它是分支钉子，
  不是覆盖率样本）。
- CI 不新增步骤：pytest 在 CI 里就会跑这条；两条既有 fixture 扫描
  （载荷扫描 / 裁剪恒等）自动覆盖新目录。

## 4. 主线 3：`F:` → Low 的根因（Windows-only 取证，探针不入库）

### 4.1 结论

`F:\DeterminFlow x2` 本身带一条**显式**的 `Mandatory Label\Low Mandatory
Level:(OI)(CI)(NW)`（`icacls` 里没有 `(I)`），整棵树（`xs2/`、`.venv/`、`src/`、
`tests/` 及其中 exe）全部继承；`F:\` 根、`F:\新建文件夹`、旧仓库 `F:\DeterminFlow`
都**没有**标签。Windows 创建进程时把令牌降到镜像的强制标签，于是一棵带 Low 标签
的树里，`python.exe` 一启动就是 `S-1-16-4096`。

### 4.2 判别实验（同一台机器、同一个 High 父进程）

| # | 实验 | 期望用来排除 | 结果 |
|---|---|---|---|
| E0 | `C:\Program Files\Python314\python.exe` | 对照 | **High** `S-1-16-12288` |
| E1 | `cmd.exe` 复制到 `F:\` 根 | 「F: 卷级降级」 | **High** —— 卷级假设死 |
| E2 | `cmd.exe` 改名成 `F:\python.exe` | 「按文件名降级」 | **High** —— 名字假设死 |
| E3 | `python.exe` 改名成 `F:\_r84_py_copy.exe` | 「按哈希/内容降级」 | **High** —— 字节假设死 |
| E4 | 同一份 `python.exe` 放进新建的 `F:\_r84_label_test\`（无标签） | 因果对照 | **High** |
| E5 | 对 `F:\_r84_label_test` 执行 `icacls ... /setintegritylevel (OI)(CI)Low` | 因果验证 | **Low** `S-1-16-4096` |
| E6 | `fltmc filters` / AV 枚举 | 「安全软件驱动改令牌」 | 全是 Windows 自带 minifilter；AV 仅 Defender —— 排除 |

文件标签用新写的只读探针 `_r84_filelabel.py` 读（`GetNamedSecurityInfoW` +
`LABEL_SECURITY_INFORMATION`，High 下启用 `SeSecurityPrivilege`）；进程 IL 用
R81 的 `_r81_probe_acl.py --pid` 读。两个探针都**不入库**（R81 拍定）。

### 4.3 处方与可移植性

- C: 解释器处方仍然有效，但它是**绕开**（C: 不在标签树下），不是「F: 盘不能跑」。
- 根修是清标签：`icacls "F:\DeterminFlow x2" /setintegritylevel (OI)(CI)Medium`。
  **本轮没有执行**——改用户目录的安全属性不是测试该做的事。
- **可移植性**：113-skip 的 Low profile 是**这棵树带标签的结果，不是机器的属性**。
  别的机器/无标签目录上，venv 解释器继承父进程的 IL，msys 不会因此失败。skip 判据
  本身（`_msys_skip_applies`）与 IL 无关（两个自变量：签名 / 模块+探针），所以
  别的机器上的测试语义不变。
- `tests/conftest.py::_msys_skip_reason` 同步：机制句改为「镜像可能继承了 Low 强制
  标签，查 `icacls`」，处置给出「清标签」与「C: 解释器」两条路；
  `tests/test_msys_attribution.py` 新增 `mandatory label` / `icacls` 两个断言，
  仍然**不写 SID、不写 "Low-integrity token"**。

## 5. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +10 / −0（2316 行） | 生产：只是登记，无行为变更 |
| `tests/test_live_snapshot_gate.py` | +129 / −2（3553 行） | 新增 78 条（展示字段 74 + p=1.0 4）；扫描断言补第三个 fixture 名 |
| `tests/conftest.py` | +18 / −7（329 行） | skip 文案：机制 + 两条处置 |
| `tests/test_msys_attribution.py` | +9 / −4（207 行） | 断言同步（`mandatory label` / `icacls`） |
| `tests/fixtures/live_snapshot_all_failed/` | 新增 7 文件（6 run + meta） | 真实导出（10721 B + 791 B） |
| `docs/JUDGEMENT_LEDGER.md` | +91 / −6（715 行） | §7.10 处置、§7.11 新章、§6 三行、§8 R84 根因 |
| `docs/PROJECT_INFO.md` | +30 / −5（745 行） | 平台注意 9 更正与 R84 取证、R83 过期括注、R84 轮次条目 |
| `docs/HANDOVER_ROUND84.md` | 新增 | 本文 |

md5（工作树）：闸门 `d0aaae2d…`、json 测试 `3b24bf25…`、conftest `d9e11fc0…`、
attribution `42bd0921…`、台账 `5f4f3353…`。

## 6. 变异验证（七次，`cp` 快照还原）

还原源一律是**改动后的当前文件快照**（`_r84_gate_snapshot.py` /
`_r84_conftest_snapshot.py`），不是改动前的备份（R82 的坑）。每条都确认输出是
failed、不是 skipped（R71 的坑）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| A1 | `failure_rate` 并进 `_TOTALS_COUNT_FIELDS` | **37 failed** | 登记清单无交集用例 + 大量展示字段格（baseline 本身变形状无效） |
| A2 | `_totals_shape_error` 校验 `failure_rate` | **36 failed** | 同上（结构用例仍绿——它只查表，不查校验器） |
| A3 | `_totals_block_error` 读 `totals.failure_rate` | **24 failed** | 4 条 per-workflow 判据 × 6 个值（`totals` 副本） |
| B1 | 删掉 `_failure_rate_precision` 的「全部失败」文案分支 | **1 failed** | `test_real_all_failed_snapshot_is_thin_and_says_why` **唯一** |
| B2 | 全失败退回正态近似（`sample_size_margin_needed` 返回 0） | **2 failed** | 闭式用例 + 退 7 用例 |
| B3 | `_cp_interval` 的全失败上界改成 99% | **1 failed** | `test_real_all_failed_snapshot_exceeds_the_policy_ceiling` **唯一** |
| C1 | 删掉 skip 文案的标签诊断（退回「this launcher is Low」） | **1 failed** | `test_skip_reason_names_the_mechanism_and_the_actionable_fix` **唯一** |

`cp` 还原后 md5 逐字节相同（闸门 `d0aaae2d…`、conftest `d9e11fc0…`）。

**如实记录一次没咬住的变异**：B3 最初把 `_cp_bounds` 的 `failed >= attempts`
分支改成 0.99，结果 **7 条全绿**——因为 `evaluate` 走的是 `_cp_interval`，那里有
自己的闭式端点（`:1198-1199`）。改成打 `_cp_interval` 才咬住。教训与 R69 的
「数等于常量 ≠ 数是判决的边界」同族：**变异必须打在实际执行路径上的那一份实现**。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：闸门 + 导出 + 翻转点 + 台账 + msys 归因 + CI 接线 | **393 passed**（12.41s） |
| 全量（Low，venv `S-1-16-4096`） | **2401 passed / 113 skipped / 0 failed**（152.02s） |
| 全量（High，`C:\Program Files\Python314\python.exe` + 绝对 `PYTHONPATH`） | **2486 passed / 28 skipped / 0 failed**（145.39s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm build | 未跑（生产代码只动闸门脚本；CI 会跑 e2e 与 container-build） |

**总用例 2434 → 2514（+80）**：Low `2401 + 113` = 2514；High `2486 + 28` = 2514。
80 = 展示字段守卫 74 + p=1.0 四条 + 新 fixture 进两条既有扫描各 1 条。

**如实记录一次环境坑**：第一次跑 High 时把 `PYTHONPATH` 传成了 Git Bash 的
`/f/...` 路径，得到 **137 个 collection error**——与 R82 的 `py.exe` 事故症状一模一样，
但原因不同。改用 `cygpath -w` 转成 Windows 路径后 2486/28 全绿；PROJECT_INFO
平台注意 9 已补记。

## 8. 未做与未验证的事（如实记录）

1. **没有清除 `F:\DeterminFlow x2` 的 Low 标签**：那是用户目录的安全属性，
   测试不该改；只给出命令与后果。
2. **没有重导主快照**：`tests/fixtures/live_snapshot` 仍是 28/255；本轮新增的是
   独立 fixture，不动既有数据。
3. **没有改 `data/workflows`**：只读导出。
4. **没有为 n≥29 全失败样本造数据**：理由见 §3.3。
5. **没有跑前端 / e2e / docker build**：零前端与服务路径改动。
6. **探针与变异脚本未入库**：`_r84_filelabel.py` / `_r84_mutate.py` /
   `_r84_gate_snapshot.py` / `_r84_conftest_snapshot.py` 按 R81 拍定留在工作区根。
7. **没有回查 Low 标签是何时/被谁设置**：SACL 没有时间戳；仓库内没有任何
   `setintegritylevel` 调用（全树 grep 为空），所以不把因果钉到某个具体轮次。
   R36 记录的「服务进程为 Low-IL」与此一致，仅作为相容证据。

## 9. 下一轮候选

1. **`source_root` 的去留**（本轮发现）：导出器写目录名，全仓库无读者——与
   `failure_rate` 同族的最后一个「写了没人看」字段。要么登记为只读展示字段，
   要么做成「合成快照不得进 CI 默认」的判据。
2. **清标签后的基线复核**（若用户决定清）：清掉 `F:\DeterminFlow x2` 的 Low 标签
   之后，本机 Low profile 会消失（venv 继承父进程 IL），本仓的「Low/High 双基线」
   记账方式需要重新定义；这是一次性环境变更，建议单独一轮。
3. **`p=1.0` 的 n≥29 样本**：只有当真实数据自然出现时才验证；不主动制造。
4. **CI 回写历史**：仍不推荐（R81 §7 的代价表未变）。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 10. 提交、推送与 CI 核对

（待回填：提交哈希、推送通道、CI run 与五个 job 的计数。）

## 11. 本轮的三条教训

1. **「登记」只有做成可执行的清单才不是又一句没人读的话**：`_DISPLAY_ONLY_FIELDS`
   被守卫用例参数化消费；若只写注释，下一轮会再发现一次「写了没人看」。
2. **同一个字段的多个副本要一起登记**：`totals.failure_rate` 与
   `per_workflow[*].failure_rate` 同源同义；只登记一处会留下「同一字段两块待遇
   不同」的裂缝（R80 的「同一事实两种说法」同族）。
3. **归因要落到「可被 icacls 看见的东西」**：R81 说「F: 上的可执行文件被降级」，
   听起来像卷策略，实际是一棵树的强制标签。判别实验的排序（卷 → 名字 → 哈希 →
   标签）把三个错误假设逐个排除，最后用「加标签 / 去标签」做了因果验证——
   **能加能去的那个变量才是原因**。
