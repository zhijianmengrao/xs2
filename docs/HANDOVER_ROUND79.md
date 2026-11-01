# DeterminFlow (xs2) 交接报告 — Round 79（元数据路径读不开：退出 4 不是 3）

> 本轮定位：R78 §8-1 / R77 §7-1 的挂账。落地形态：**一处生产代码重构
> （八处判据收进同一个元数据读入口）+ 24 条用例 + 台账登记**。
> `src/` 与前端零改动。

## 1. 一句话结论

R77 说「`snapshot-meta.json` 是目录」是同一个 `except` 的另一种注入方式——**实测
不成立**。旧写法先 `meta_path.is_file()`，目录在那一步就是 `False`，八处判据
**一起以 3（无样本）退出**；而 3 的处置是「先导出一份快照」，对着一个已经被
目录占住的路径重导只会再失败一次。本轮把读取收进 `_load_snapshot_meta()`，
按**异常类型**分流：缺失 3、读不开 4、读不懂 4；顶层是合法 JSON 但不是对象
（`[]` / `"x"` / `null` / `42`）同样归 4——旧行为是 `AttributeError` → CLI 以
**1** 退出，与「判了且不合格」同码。

## 2. 实测：R77 的前提为什么不成立

本机探针（八处判据 × 三种元数据状态，`meta` 正常 / 目录 / 缺失）实测：

| 状态 | 修复前 | 修复后 |
|---|---|---|
| 正常 | 0 / 0 / 0 / 7 / 0 / 0 / 0 / 3（各自判决） | 逐字相同 |
| **目录** | 八处**全部 3**（`快照元数据缺失：…`） | 八处**全部 4**（`快照元数据无法读取（PermissionError…）`） |
| 缺失 | 八处全部 3 | 八处全部 3（不变） |

两个平台细节决定了修法：

- **Windows 上打开目录抛 `PermissionError`，不是 `IsADirectoryError`**（POSIX 才
  是后者）。所以「用 `is_dir()` 预检」等于把同一条判据写成两份平台相关代码；
- `is_file()` 在**父目录 ACL 被拒**时同样返回 `False`——它连「权限拒绝」也一起
  吞成 3，而那正是 `except OSError` 本来要接住的一格。

`open()` 抛出的异常类型就是「为什么读不了」的答案，也是唯一能区分「没有」与
「坏了」的信息。因此最终形态是**直接读、按异常类型分流**，不设任何 `stat` 预检。

## 3. 设计

### 3.1 唯一入口

`_load_snapshot_meta(data_dir, purpose="") -> (meta, error)`：

| 情形 | 码 | 处置 |
|---|---|---|
| `FileNotFoundError` | 3 | 没有快照 → 导出一份 |
| 其它 `OSError`（目录 / 权限拒绝 / 路径不可用） | 4 | 先清理该路径，再重导 |
| `ValueError`（`UnicodeDecodeError` / `JSONDecodeError`） | 4 | 重导 / 修文件 |
| 顶层不是 JSON 对象 | 4 | 重导 |
| 正常 | — | 返回 `meta` |

八处判据全部改走它：`evaluate`、`check_stale`、`check_coverage`、
`check_sample_size`、`check_per_workflow`、`check_per_workflow_rate`、
`check_per_workflow_regression`、`check_lead_time`。

`purpose` 只改「缺失」那一句的措辞（`无法判新鲜度` / `无法判样本量` / …），
**不改变判决**：八处原有的缺失文案逐字保留。

### 3.2 两处顺带的统一（如实记录）

1. `check_coverage` 原先只把 `is_file()` 当「快照存在」的信号，不解析内容。
   现在它也走同一个门：坏 JSON / 读不开 → 4。理由是「快照坏了」与「快照缺了」
   的处置不同，而覆盖度判的正是快照本身是否可用。
2. 顶层非对象（`[]` / `"x"` / `null` / `42`）在旧代码里会让每个调用方的
   `meta.get(...)` 抛 `AttributeError`，进程以 1 退出。它不是 `OSError`，但同属
   「读得开、形状不对」，与 R75 的 `"junk"` / `"abc"` 同族，因此一并归 4。

### 3.3 不做的事

- **不把 `totals` 块纳入形状校验**：`{"attempts": "abc"}` 仍会在 `int()` 处抛
  `ValueError` → `_run_judgement` 归成 8。它是 R75 同族但属于另一块元数据，
  本轮范围只有「路径读不开」，如实留在 §7。
- **不改任何判据算术与阈值**：本轮的 24 条用例只碰退出路径，不改判决。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +83 / −52（2028 → 2059 行） | 新增 `_load_snapshot_meta` + 八处调用点收口 |
| `tests/test_live_snapshot_gate.py` | +117 / −0（**24 条**） | 退出路径 + 统一入口守卫 |
| `docs/JUDGEMENT_LEDGER.md` | +45 / −1 | §5 退出码 4 的处置、§6 四行、新增 §7.7 |
| `docs/PROJECT_INFO.md` | +1 行 | R79 轮次条目 |
| `docs/HANDOVER_ROUND79.md` | 新增 | 本文 |

**闸门脚本 md5 改变**：`1d0e0ac027f3732fad7586cf81ac05fa` → `03a4b09fafdd772a35834907dcfaff09`。
本轮**不是**零生产代码改动——`src/` 与前端零改动，但 `scripts/` 的闸门脚本改了。

## 5. 变异验证（六次，`cp` 备份还原）

相关用例集 = 新增的 24 条（`-k` 选择）。每次还原后 `md5sum` 与备份逐字节相同
（`03a4b09f…`）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | `OSError` 一律当无样本（3） | **8 failed** | 八处判据的「目录」参数 |
| 2 | `FileNotFoundError` 也当坏数据（4） | **8 failed** | 八处判据的「缺失」参数 |
| 3 | 退回 `is_file()` 预检（旧写法） | **8 failed** | 八处判据的「目录」参数 |
| 4 | 去掉顶层对象校验 | **4 failed** | 4 条「顶层非对象」参数 |
| 5 | 只让 `check_lead_time` 绕过统一入口 | **2 failed** | `[check_lead_time]` 目录参数 + 统一入口守卫 |
| 6 | 读不开的文案退回「缺失」口径 | **8 failed** | 八处判据的「目录」参数（文案断言） |

**如实记录**：M1/M2/M3/M6 各自同时咬红 8 条参数化用例，**没有唯一咬合者**——它们
破坏的是同一个前提（「按异常类型分流」），所以八处一起响。M5 的 2 条里，
`test_every_judge_reads_the_metadata_through_one_door` 是**唯一能守住「将来新增
判据」**的用例：只改一处时那条判据的参数会红，但新增一处绕过时只有它红。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：新增 24 条 | **24 passed**（0.33s） |
| 相关集：`test_live_snapshot_gate` + `test_judgement_flip_points` + `test_judgement_ledger` + `test_ci_gate_wiring` | **231 passed**（6.03s） |
| 全量（本机，Low `S-1-16-4096`） | **2261 passed / 113 skipped / 0 failed**（151.84s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| docker build / npm run build | 未跑（无生产与前端改动；CI 会跑 container-build） |

**对账**：总用例 **2350 → 2374**（+24）。Low `2261 + 113` = **2374**。
`tests/test_live_snapshot_gate.py` 由 **171 → 195**。

## 7. 未做与未验证的事（如实记录）

1. **`totals` 块形状仍会冒充 8**：`{"attempts": "abc"}` → `int()` 抛
   `ValueError` → `_run_judgement` 归成「判据算术失败」。与 R75 的
   `per_workflow.failed = "abc"` 同族，但属于另一块元数据，本轮未动。
2. **`history` 畸形条目仍由 `_history_entry_counts` 跳过并计数**（R58 起），
   不进判决。处置已拍定为「只报告，不进退出码」（本轮用户选择），**尚未实现**。
3. **未重导快照**：`data/` 下 `run-*.json` 仍 **40 个**，最新
   `2026-10-28 08:34`（本轮实查）；入库快照 `exported_at=2026-10-30T09:26:54`，
   保鲜判据比的是「快照滞后真实数据」，当前为负、未到期，无需重导。
4. **本会话仍只有 Low profile**：113 skips，28-skip 未复现。
5. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。
6. **CI 没有新增步骤**：本轮改的是既有判据内部的退出路径，CI 已覆盖同一批
   `--check-*` 步骤；坏元数据在 CI 上出现的概率极低，用例是主要防线。

## 8. 下一轮候选

1. **`history` 畸形条目按「只报告」落地**（处置已拍定）：现在只有
   `invalid_history` 计数出现在两处判据的输出里，需要逐条列出并确认八处
   判据的文案一致。
2. **`totals` 块形状 → 4**（本轮 §7-1）：`"attempts": "abc"` / `"failed": true`
   等，与 `_per_workflow_shape_error` 同一件工具，可能要提取一个共用校验器。
3. **重导快照 / `p=1.0` 真实数据**：继续挂账，每轮查一次 run 数（本轮仍 40 个）。
4. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile 的
   路径，风险最高（可能动 shell 正在用的命名对象）。
5. **趋势判红的前置研究**（不实现）：R78 §2 已论证 10 场景下不存在可判阈值。
6. **CI 回写历史**：明确不推荐（需要 `contents: write`、会触发二次 CI）。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 提交、推送与 CI 核对

两次提交（`5a86694` feat + `1d6ef42` docs，显式路径 add）后推送
`bf5fd77..1d6ef42`（一次成功；本轮 socks5 与直连同时可用，用的是全局 socks5）。
CI run **41265908796**（push，02:36:31 → 02:40:51，约 4m20s）五 job 全 `success`：

| 项 | 实证（下载日志解码后逐字比对） |
|---|---|
| 五个 job | backend（02:36:34–02:39:06）/ windows-backend（02:36:34–02:40:51）/ frontend（02:36:34–02:38:20）/ container-config（02:36:34–02:36:40）/ container-build（02:36:34–02:37:13）全部 `success` |
| ubuntu | `2309 passed, 65 skipped, 1 warning in 110.02s` = **2374** |
| windows | `2345 passed, 29 skipped, 1 warning in 195.72s` = **2374** |
| 新用例在 CI 真跑 | ubuntu 2285/65 → **2309/65**、windows 2321/29 → **2345/29**（各 **+24**） |
| 快照判据 | backend 第 8–14 步（真实快照闸门 / 回归 / 逐 workflow 回归 / 提前量 / 样本量 / per-workflow 报告 / 失败率门槛）全 `success`；windows 第 7–11 步同 |
| e2e / metrics | `[e2e] 10/10 场景通过`；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| e2e 趋势（R78 步骤） | backend 第 **17** 步 `e2e retry trend (history, read-only)` `success` |
| 前端 / 容器 | 前端 8 块 TAP `# pass` 求和 **490 / fail 0**；`容器镜像冒烟全部通过`；`docker compose config -q` 成功 |
| Desktop Windows / macOS | 未触发（该 SHA 下只有 CI 一个 run） |

`$GITHUB_STEP_SUMMARY` 正文 API 不提供，趋势表由本地同一个 `render_trend()` 逐字
验证（与 R74 §7-2 同一条限制）；CI 上能核到的是「这一步以 0 退出」。

补记提交 `465c518`（纯文档）的 run **41266296978**（02:42:37 → 02:47:24，约 4m47s）同样五 job 全 `success`：ubuntu **2309/65**（106.81s）、windows **2345/29**（220.54s）、前端 490/0、e2e 10/10 与上一个 run 逐项相同。文档提交本身仍会触发 CI，回填链到此为止（与 R66/R77/R78 同）。

