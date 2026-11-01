# DeterminFlow (xs2) 交接报告 — Round 83（`totals.runs` 收口：写了没人看的字段并入内容复算）

> 本轮定位（用户拍定）：主线 = R82 §9-2「`totals.runs` 与 run 数的口径」，处置 =
> **并入内容复算校验**（不是删字段）；副线 = R82 §9-3 的 High 启动器处方复核
> （同轮顺手做）。
> 落地形态：**一个生产文件（闸门脚本）+ 测试 + 文档**；CLI 无新增开关，
> CI YAML 零改动，fixture 零改动（两份入库快照本来自洽）。

## 1. 一句话结论

R82 挂的账「导出脚本写 `totals.runs`，但没有任何判据消费它」在实现上是一句
**没人读的话**：把 `runs` 改成任何数字，六个读计数的入口（`evaluate` /
`check_sample_size` / 四条 per-workflow 判据）没有一条会说话。本轮不写新判据，
而是把这个字段并入**同一个块、同一把尺**：`_TOTALS_COUNT_FIELDS` 增加 `runs`，
`_totals_of` 按该字段表求和并返回 `{runs, attempts, failed}`，新增 `_totals_key`
让元数据与内容复算做整张 key 比较，六处入口统一退 **4**；漂移文案写全三个计数。
旧格式 totals 缺 `runs` 按 0 计 → 同样退 4（处置是重导，导出脚本会补上）。

## 2. 缺口实测（HEAD 旧脚本 / 新脚本，同一份临时快照）

探针 `_r83_probe.py`（未入库）用 `git show HEAD:scripts/check_live_snapshot_gate.py`
取出改动前文件（`_r83_gate_orig.py`，md5 `62738c67…`），与新脚本同时 import，
喂同一份「两 workflow 各 10 次尝试 / 1 次失败」的临时快照。

| 场景 | `evaluate` | `check_sample_size` | `check_per_workflow` | `…_rate` | `…_regression` | `check_lead_time` |
|---|---|---|---|---|---|---|
| 两块都真（基线） | 0 / **0** | 7 / **7** | 0 / **0** | 0 / **0** | 0 / **0** | 3 / **3** |
| `totals.runs` +1（其余全真） | 0 / **4** | 7 / **4** | 0 / **4** | 0 / **4** | 0 / **4** | 3 / **4** |
| `totals.runs` 字段删除（旧格式） | 0 / **4** | 7 / **4** | 0 / **4** | 0 / **4** | 0 / **4** | 3 / **4** |

（每格「旧 / 新」。基线两列逐项相同——本轮不改变任何正常快照的判决。）

新脚本的说明点名块与三个计数：「totals 元数据与内容不一致：元数据
runs/attempts/failed=3/20/2，内容复算 2/20/2。改过快照就要重导…」。只写
failed/attempts 时，仅 `runs` 说谎会打印出两个一模一样的「2/20」——这也是
M5 变异唯一咬合的那条用例。

## 3. 设计（三个取舍）

1. **不新增 `--check-runs` 开关。** `runs` 与 attempts/failed 是同一个块的三个
   计数；单独一条判据会出现「这条判据信这个字段、那条信那个字段」的分裂。
2. **不删字段。** 用户拍定「并入校验」而不是删掉：`runs` 是导出器已经写进
   入库工件的事实，删掉只是把「没人读」变成「不存在」，而 run 数本身对读者
   有信息量（28 run / 255 次尝试）。
3. **缺失按 0 计，不跳过。** 与 `per_workflow` 块内缺失字段的既有口径一致
   （`int(rec.get("runs") or 0)`）：字段可以缺失，但缺失不能等于「没人看」。
   内容里有多少 run，导出脚本就会写多少；缺了说明这份元数据不是当前导出器
   写的，重导一次即修复——所以与漂移同归 4。

其余规则：

- `_TOTALS_COUNT_FIELDS` 仍是求和、形状校验、漂移比较**共用的唯一字段表**；
  `_totals_key` 不重复分流 `bool`（形状校验先拒），避免「这边拒了、那边放过」。
- `totals.failure_rate` **仍未消费**：它是导出时写给人看的派生值，做成判据会
  引入「浮点四舍五入相等」的另一族脆弱算术。如实记录，见台账 §7.10。
- 两份入库 fixture 自洽（`live_snapshot` 28/28、`live_snapshot_exceeds` 3/3），
  本轮**没有重导快照**；`live_snapshot_exceeds` 的 `runs` 3 是「3 run / 120 次
  尝试」的合成形状，不是 3 vs 120 的矛盾。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | +59 / −35（2306 行） | 生产：字段表加 `runs`、`_totals_of` 改返回字典、新增 `_totals_key`、六处接线、文案写全三计数 |
| `tests/test_live_snapshot_gate.py` | +108 / −15（3426 行） | 新增 19 条（6×2 参数化 + 文案 + CLI 2 + `runs` 畸形 4 格），helper 补 `runs` |
| `tests/test_judgement_flip_points.py` | +2 / −1 | 本地快照 helper 的 totals 补 `runs` |
| `tests/conftest.py` | +9 / −2 | 副线：msys skip 处方改用 C: CPython 本体 |
| `tests/test_msys_attribution.py` | +4 / −2 | 副线：断言同步（`python.exe` 在、`py.exe` 不在） |
| `docs/JUDGEMENT_LEDGER.md` | +70 / −4 | §7.10、§5 码 4、§6 四行、§7.9 更正、§8 启动器更正 |
| `docs/PROJECT_INFO.md` | +11 / −4 | R83 轮次条目、R82 条目的过期括注、平台注意事项 9 |
| `docs/HANDOVER_ROUND83.md` | 新增 | 本文 |

md5（工作树）：闸门 `19507a3d…`、json 测试 `3de7bfeb…`、翻转点 `86cff8fe…`、
conftest `76628685…`、attribution `987637b6…`、台账 `1454ed92…`；
改动前闸门副本 `_r83_gate_orig.py` = `62738c67…`（§2 的「旧」列由它产出）。

## 5. 变异验证（六次，`cp` 快照还原）

相关用例集 = `tests/test_live_snapshot_gate.py`。**每条都确认输出是 failed，
不是 skipped**（R71 的教训）。还原源是**改动后的当前文件快照**
（`_r83_gate_snapshot.py`），不是改动前的备份——R82 踩过「把 finally 当还原源
反而写回旧版」的坑。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | `evaluate` 只比 attempts/failed | **4 failed** | `[evaluate]` 两条参数化用例唯一咬住本入口（另两条是文案与 CLI） |
| 2 | `check_sample_size` 只比两项 | **3 failed** | `[check_sample_size]` 两条唯一（另一条是 CLI） |
| 3 | 共享 `_totals_block_error` 只比两项 | **8 failed** | 四条 per-workflow 判据各两条同时失守（共享校验器的直接后果） |
| 4 | `_TOTALS_COUNT_FIELDS` 退回两项 | **21 failed** | 核心变异：六个入口 + 文案 + CLI + 形状 + 入库快照断言一起红 |
| 5 | 漂移文案不写 `runs` | **1 failed** | `test_totals_drift_message_names_all_three_counts` **唯一咬合** |
| 6 | 形状校验漏掉 `runs` | **4 failed** | 恰好是新增的四个 `runs` 畸形格（`totals7`–`totals10`） |

`cp` 快照还原后 md5 逐字节相同（`19507a3d…`）。**如实记录**：M1/M2 的入口
专属用例是唯一的，但文案与 CLI 用例会因为同一个入口失守而一起红——它们不是
「唯一咬合者」，价值在于把退出码与可读性各钉一层。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：闸门 + 翻转点 + 台账 + CI 接线 + msys 归因 | **296 passed**（6.58s） |
| 全量（Low，venv `S-1-16-4096`） | **2321 passed / 113 skipped / 0 failed**（135.72s） |
| 全量（High，`C:\Program Files\Python314\python.exe` + venv site-packages 绝对 `PYTHONPATH`） | **2406 passed / 28 skipped / 0 failed**（140.03s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm build | 未跑（生产代码只动闸门脚本；CI 会跑 e2e 与 container-build） |

**总用例 2415 → 2434（+19）**：Low `2321 + 113` = 2434；High `2406 + 28` = 2434。
High 的跑法用副线复核后的命令（见 §7），与 R82 一致；本轮没有再出现
`C:\Windows\py.exe` 的 137 个 collection error。

## 7. 副线：High 启动器处方复核（R82 §9-3）

R81 写的处方是 `C:\Windows\py.exe` + 绝对 `PYTHONPATH`；R82 §6 实测该 launcher
**没有项目依赖**（137 个 collection error）。本轮把处方改成实测有效的那一个：

```powershell
cd "F:\DeterminFlow x2\xs2"
$sp = "$PWD\.venv\Lib\site-packages"
$env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
& "C:\Program Files\Python314\python.exe" -m pytest -q
```

- `tests/conftest.py::_msys_skip_reason`：处方句由 `C:\Windows\py.exe` 改为
  `C:\Program Files\Python314\python.exe`，并写清 venv site-packages 与
  `win32` / `pythonwin` / `pywin32_system32` 的附加路径（`.pth` 在 PYTHONPATH
  下不执行，必须显式列出）。
- `tests/test_msys_attribution.py`：断言从「文案里有 `py.exe`」改为
  「有 `python.exe`、且**不出现** `py.exe`」——把这次更正钉住，防止下一轮
  照抄旧处方。
- `docs/PROJECT_INFO.md` 平台注意事项 9：PowerShell 命令同步更新，并加
  **R82 更正**括注（137 个 collection error + R82 High 2387/28 的实测）。
- **本轮验证**：§6 的 High 全量 **2406/28** 就是用上面这条命令跑出来的；
  处方在本机今天成立。

## 8. 未做与未验证的事（如实记录）

1. **没有重导快照**：两份入库 fixture 的 `totals.runs` 与内容本来就一致
   （28/28、3/3），本轮只改了校验，不改数据。
2. **没有把 `totals.failure_rate` 纳入校验**：理由见 §3；它是导出时写给人看的
   派生值，做成判据会引入浮点四舍五入相等的问题。
3. **没有改 `data/workflows`**：仍 40 个 run，最新 `2026-10-28 08:34`。
4. **没有跑前端 / e2e / docker build**：生产与前端零改动（闸门脚本不是服务路径）。
5. **没有追「`F:` 上的可执行文件为什么被降到 Low」**（R81 §8-3 挂账）：本轮
   副线只复核「用哪一个 C: 启动器能跑」，没有推进磁盘策略根因。
6. **探针 / 变异脚本未入库**（`_r83_probe.py` / `_r83_mutate.py` /
   `_r83_gate_orig.py` / `_r83_gate_snapshot.py`）：按 R81 拍定，Windows-only
   的取证脚本不入库。

## 9. 下一轮候选

1. **`F:` → Low 的策略来源**（R81 §9-1，仍挂账）：决定「C: 启动器」处方是否
   在别的机器上成立；本轮与 R82 都只是绕开它。
2. **`totals.failure_rate` 的去留**（新发现）：与 R83 的 `runs` 同族——写在
   入库工件里、没有判据读。要么删除（导出时仍可打印到控制台），要么明确
   登记为「只读展示字段」，不能维持「写了没人看」。
3. **CI 回写历史**：仍不推荐（R81 §7 的代价表未变）。
4. **`p=1.0` 真实数据**：继续挂账；快照仍是 10/255。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 10. 提交、推送与 CI 核对

两次提交（`f2c971b` fix + `2adac7b` docs，显式路径 add）后推送
`27cfda7..2adac7b`。推送通道：本轮直接用
`git -c http.proxy= -c https.proxy= push`，一次成功（与 R58/R61/R62/R82 同一条
纪律：每轮先探路，不照抄上一轮的通道；socks5 10808 本轮未使用）。

CI run **41286127641**（push，07:46:39 → 07:52:01，约 5m22s）五 job 全 `success`：

| 项 | 实证（下载日志解码后逐字比对） |
|---|---|
| 五个 job | backend（07:46:42–07:49:22）/ windows-backend（07:46:41–07:51:11）/ frontend（07:46:42–07:48:19）/ container-config（07:46:41–07:46:46）/ container-build（07:46:41–07:47:17）全部 `success` |
| ubuntu | `2369 passed, 65 skipped, 1 warning in 112.91s` = **2434** |
| windows | `2405 passed, 29 skipped, 1 warning in 211.36s` = **2434** |
| 计数与 R82 相比 | ubuntu 2350/65 → **2369/65**、windows 2386/29 → **2405/29**（各 **+19**，与本轮新增用例数一致） |
| 快照判据 | backend 第 7 步 fixture 自检 + 第 8–14 步七个真实快照判据全 `success`；R83 的 `_totals_key(recorded) != _totals_key(actual)` 就在这些入口里执行——两份入库 fixture 自洽（28/28、3/3），所以退出码与 R82 逐项相同（政策 8%→0 / 1%→1、回归→0、逐 wf 回归→0、提前量→0、样本量→0、逐 wf 报告→0、失败率硬门槛→0） |
| 新行为在 CI 真跑 | 第 14 步输出仍含「快照历史 3 轮（含当前）。连续 3 轮以上样本不足：…」共 8 个 workflow，退出 0 |
| e2e / metrics | `[e2e] 10/10 场景通过`；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| e2e 趋势（R78 步骤） | backend 第 **17** 步 `e2e retry trend (history, read-only)` `success` |
| 前端 / 容器 | 前端 8 块 TAP `# pass` 求和 **490 / fail 0**；`容器镜像冒烟全部通过: determinflow-core:ci` |
| Desktop Windows / macOS | 未触发（该 SHA 下只有 CI 一个 run） |

`$GITHUB_STEP_SUMMARY` 正文 API 不提供（与 R74 §7-2 / R80 §9 同一条限制）；CI 上能
核到的是「这一批步骤都以 0 退出」。

补记提交 `50d2e09`（纯文档）的 run **41286776250**（07:56:40 启动）五个 job 全部
`completed / success`：ubuntu **2369/65**（75.72s）、windows **2405/29**
（218.81s）、前端 TAP 求和 490 / 0，与上一个 run 逐项相同。**如实记录一个平台
异常**：run 级 `status` 在 API 上一直停在 `in_progress`（`updated_at` 冻结在
07:56:51，windows job 09:01:31 完成后仍未翻转），但五个 job 的 `conclusion`
全部是 `success`——本报告以 job 结论为准；这是 GitHub 的聚合状态滞后，不是本轮
代码问题。
