# DeterminFlow (xs2) 交接报告 — Round 86（顶层 `source_root` 登记为只读展示字段）

> 本轮定位：用户拍定 R84 §9-1 的处置（**登记为只读展示字段**），与 R83 的
> `runs`、R84 的 `failure_rate` 同族。
> 形态：生产文件只改登记清单 + 测试 + 文档；无 CLI 开关、CI YAML 零改动、
> `data/workflows` 只读。

## 1. 一句话结论

1. `source_root`（顶层 meta，导出脚本写源目录名）是同一份元数据里最后一个
   「写了没人看」的字段：`export_run_samples.py:278` 写它，全仓库没有判据读它。
2. 登记进 `_DISPLAY_ONLY_FIELDS`（与 `failure_rate` 并列），由结构用例保证它与
   两张计数表无交集，并由六个读计数入口 × 六种坏值的守卫断言 `(退出码, 文案)`
   逐字不变。
3. 净增 **36** 条用例，总数 2514 → **2550**；本机全量 **2522 passed /
   28 skipped / 0 failed**（149.34s）。

## 2. 缺口与处置

**缺口**：`export_run_samples.py:278` 写入 `"source_root": workflows_dir.name`，
`grep source_root` 在 `scripts/` 只命中这一处写入，闸门的六个读计数入口都不读它。

**为什么登记，而不是并入计数表/做判据/删除**：

- **不并入计数表**：值是目录名（`workflows` 或任意 `--dest` 的父目录名），
  `_count_value_error` 只接受整数/整数字符串；混进计数表会让每一份快照在形状
  校验处被判「形状无效」（4）。
- **不做判据**：R84 §9-1 的另一选项是「合成快照不得进 CI 默认」。要判它必须先
  定义哪些 fixture 是 synthetic、哪条 CI 路径算「默认」；而 `source_root` 只是
  「导出时源目录的名字」，换一个目录导出就会变——拿它当判据会把合法重导误判成
  合成快照。
- **不删除**：它是读者要的信息（快照来源）；删掉只是把「没人读」变成「不存在」，
  与 R83 对 `runs`、R84 对 `failure_rate` 的处置理由相同。

## 3. 落地

- `scripts/check_live_snapshot_gate.py`：`_DISPLAY_ONLY_FIELDS` 由
  `("failure_rate",)` 扩成 `("failure_rate", "source_root")`；注释写清三条理由，
  并注明 `source_root` 只有顶层一个副本、与 `failure_rate` 的两个副本位置不同。
- `tests/test_live_snapshot_gate.py`：
  - `test_source_root_is_display_only`：六个读计数入口 × 六种值
    （`"abc"` / `true` / `3.7` / `0.99` / `null` / 整个删掉），先写一份正确的
    `source_root="workflows"`，每次变异后断言 `(code, message)` **逐字不变**。
    只比退出码抓不到「读了但只用在文案里」的入口。
  - `test_display_only_registry_is_structurally_excluded`：期望集合改为
    `{"failure_rate", "source_root"}`，并继续断言与 `_TOTALS_COUNT_FIELDS` /
    `_PER_WORKFLOW_COUNT_FIELDS` 无交集。
  - `test_committed_snapshot_carries_the_display_field`：增加
    `meta["source_root"] == "workflows"`——否则守卫只是在测「字段根本不存在」。

## 4. 变异验证（两次，`cp` 快照还原）

还原源是**改动后的当前文件快照**（`_r86_gate_snapshot.py`），不是旧备份
（R82 的坑）。每条都确认输出是 failed、不是 skipped（R71 的坑）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| M1 | 从 `_DISPLAY_ONLY_FIELDS` 删掉 `source_root` | **1 failed** | `test_display_only_registry_is_structurally_excluded` **唯一** |
| M2 | 让 `check_sample_size` 在 detail 里带上 `meta["source_root"]` | **6 failed** | `test_source_root_is_display_only` 的该入口 × 六种值（其余 30 条通过） |

`cp` 还原后 gate md5 逐字节相同（`5e0a070e…`）。

**如实记录**：M2 只打了一个入口。没有为六个入口各写一次变异——共享校验器
（`_load_snapshot_meta`）之外的入口各写一份读法，变异成本高于新增的信息量；
六个入口的覆盖由参数化用例本身保证（每个入口 × 六值都跑）。

## 5. 测试执行汇总

| 项 | 结果 |
|---|---|
| 定向：`tests/test_live_snapshot_gate.py` | **371 passed**（8.01s，含新增 36 条） |
| 全量（Medium，venv `S-1-16-8192`） | **2522 passed / 28 skipped / 0 failed**（149.34s） |
| 前端 / e2e / docker build | 未跑（零前端与服务路径改动） |

**总用例 2514 → 2550（+36）**：`2522 + 28 = 2550`。

## 6. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +8 / −2（2322 行，md5 `5e0a070e…`） | 生产：登记清单 + 注释，无行为变更 |
| `tests/test_live_snapshot_gate.py` | +49 / −2（3600 行，md5 `43203616…`） | 新增 36 条 + 结构/快照断言同步 |
| `docs/JUDGEMENT_LEDGER.md` | +15 / −0（731 行） | §6 一行 + §7.12 |
| `docs/PROJECT_INFO.md` | +1 / −0（748 行） | R86 轮次条目 |
| `docs/HANDOVER_ROUND86.md` | 新增 | 本文 |

## 7. 未做与未验证

1. **没有改导出脚本**：`source_root` 的写入口径不动（仍是目录名）。
2. **没有重导快照**：`tests/fixtures/live_snapshot` 仍 28/255；R84 的
   `live_snapshot_all_failed` 也不动。
3. **没有跑前端 / e2e / docker build**：零前端与服务路径改动。
4. **没有新增 CI 步骤**：pytest 在 CI 里就会跑这 36 条；两条既有 fixture 扫描
   自动覆盖。
5. **没有把 `source_root` 做成判据**：理由见 §2；这是用户拍定的处置。

## 8. 下一轮（用户已拍定）

1. **R87：制造 n≥29 全失败样本**（用户选择「主动制造」）。设计约束：在隔离的
   数据目录里跑，不污染 `data/workflows`；样本必须是真实执行记录。n=29 正是
   margin 10 的翻转点：`1 − 0.05^(1/29) = 9.82pp < 10`，n=28 是
   `10.15pp > 10`——两个方向都要有实测。
2. **R88：CI 回写历史**。先出设计与代价表（R81 §7 的结论是「不做」，本轮用户
   改判为「做」）：`contents: write`、并发/竞态、失败回滚、避免自我触发的提交
   循环，且不能影响现有只读 job。

## 9. 提交、推送与 CI 核对

（待补记）
