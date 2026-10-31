# DeterminFlow (xs2) 交接报告 — Round 72（#4 的退出路径：门与翻转点用同一组计数）

> 本轮定位：R70 §7-3 的挂账「留一法基线的元数据漂移路径」。用户拍定主线 =
> 这一项。基线 `9bb1b5e`（R71 补记）。落地形态：**仅测试 + 文档**，
> 生产代码零改动。

## 1. 一句话结论

R56 的漂移/无样本用例与 #4 的翻转点**用的不是同一组计数**，所以两种改法在
既有用例上全绿：让真实失败（内容 k=4）被一句元数据改写成「判不了」，或让
内容为空的快照按元数据说出「超出」。本轮用 #4 的计数（rest 30/0、
target 4/10）加 3 条走真实入口的用例，把退出 4 / 退出 3 两道门接到翻转点上。
五次变异里 B/C 各在一条变异上是**唯一**咬合者，A 不是——它的增量是「翻转点
穿过真实入口」，不是「只有它能发现」。

## 2. 最重要的一件事：哪些变异是唯一咬合的

五次变异都跑**全部相关用例**（`test_judgement_flip_points` +
`test_live_snapshot_gate` + `test_judgement_ledger` + `test_msys_attribution`，
基线 188）：

| # | 变异 | 实测 | 唯一咬合者 |
|---|---|---|---|
| 1 | 漂移检查挪到报告之后，且 `if drifts and not exceeds` | **1 failed**：新用例 B | **B**（既有 R56 漂移用例无 exceeds，照绿） |
| 2 | `if not actual:` 从退出 3 改成退出 0 | **1 failed**：新用例 C | **C**（空内容分支此前无覆盖） |
| 3 | 漂移退出码 4 → 3 | **2 failed**：B + 既有 `test_rate_check_reuses_the_per_workflow_drift_check` | 否 |
| 4 | `_per_workflow_drift` 比较键丢掉 `failed` | **5 failed**：B + 4 条既有（共用同一漂移函数） | 否 |
| 5 | 调用点 `per_workflow_rate_report(actual, margin * 2)` | **2 failed**：A + 既有 `test_rate_check_passes_on_the_committed_snapshot` | 否 |

所以诚实的说法是：

- **B 的增量是「顺序」**：R56 的漂移用例断言的是「有漂移就退出 4」，但它用的
  计数无论如何都判不出 `exceeds`；把漂移检查放到判决之后、并只在判不出时执行，
  在它面前完全看不出来。B 用同一份 k=4 快照把「漂移必须说在判决之前」钉住。
- **C 的增量是「空内容分支」**：R56 只测了「缺 `per_workflow` 块」；缺元数据
  文件与「元数据说有、内容为空」两条分支此前没有 rate 判据的用例。
- **A 不唯一**：M5 同时被既有入库快照用例咬住。A 的价值是结构性的——证明
  磁盘上的计数能走到同一个翻转点，而不是纯函数层各自为政；这一点写在这里，
  不冒充「只有它能发现」（R69/R70 的教训第三次生效）。

## 3. 设计

1. **本地 helper** `_write_rate_snapshot(root, spec, declare_meta=True)`：落盘
   `workflows/<wf>/runs/run-x.json` + `snapshot-meta.json`，形状与
   `test_live_snapshot_gate.py::_write_per_workflow_snapshot` 相同。保留本地
   副本而不是跨测试模块 import：`tests/` 没有 `__init__.py`，prepend 模式下
   的跨模块 import 比复制这二十行更脆（与 R70 的 `_write_snapshot` 同一取舍）。
2. **三条用例**（都通过 `check_per_workflow_rate`，不是纯函数）：
   - `test_leave_one_out_flip_point_through_the_real_gate`：k=3 退出 0、
     「0 个超出」「1 个样本不足」；k=4 硬门槛退出 1、「1 个超出」；k=4
     报告模式退出 0「报告模式」。
   - `test_metadata_drift_preempts_the_leave_one_out_verdict`：同一份 k=4
     快照，元数据把一次失败从 target 挪给 rest（全局合计 40/4 不变，内容仍是
     target 4/10）→ 退出 4，消息含 `rest`/`target`/「重导」，且**不含**「超出」。
   - `test_no_sample_preempts_the_leave_one_out_verdict`：缺元数据文件 / 缺
     `per_workflow` 块 / 元数据说有但 `workflows/` 为空 → 各自退出 3，消息
     对应分支，且都不说「超出」。
3. **注册**：`_FLIP_POINT_TESTS["4"]` 追加三个名字；登记页 §7 的 #4 行追加
   用例名，并新增 §7.2 说明「数值翻转」与「翻转点的前提」的区别。覆盖守卫
   保证名字必须存在且出现在登记页。
4. **登记页**：§2 #4 的盲区补「3/4 两条退出路径先于判决」；§6 增一行；
   §7.2 三行表（前提 / 同一组计数下的期望 / 用例）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/test_judgement_flip_points.py` | **+138 / −1** | helper + 3 条用例 + 注册表 + docstring |
| `docs/JUDGEMENT_LEDGER.md` | **+27 / −2** | §2 盲区 / §6 一行 / §7 #4 用例格 / 新增 §7.2 |
| `docs/PROJECT_INFO.md` | **+1 行** | R72 轮次条目 |
| `docs/HANDOVER_ROUND72.md` | 新增 | 本文 |

**生产代码零改动**：`scripts/check_live_snapshot_gate.py`（`7a329d3a…`）与
`scripts/e2e_workflow_stub.py`（`a5104e69…`）与 R71 记录逐字节相同；
`tests/test_live_snapshot_gate.py` 未改（R56 用例保留，它们覆盖的是另一类
变异）。CI 配置、前端未动。

## 5. 变异验证（五次，`cp` 备份还原）

跑的是全部相关用例（基线 **188**）。每次还原后 `md5sum` 与备份逐字节相同
（`7a329d3a4e8d0cd38e2f2a3078889cb1`），还原后相关集 **188 passed**。

| # | 变异 | 实测（完整失败清单） |
|---|---|---|
| 1 | 漂移检查挪到报告之后 + `not exceeds` | `test_metadata_drift_preempts_the_leave_one_out_verdict`（1 红） |
| 2 | `if not actual:` 退出 3 → 退出 0 | `test_no_sample_preempts_the_leave_one_out_verdict`（1 红） |
| 3 | 漂移退出码 4 → 3 | 上条 B + `test_rate_check_reuses_the_per_workflow_drift_check`（2 红） |
| 4 | 漂移比较键丢掉 `failed` | B + `test_per_workflow_catches_drift_the_global_totals_miss` + `test_rate_check_reuses_the_per_workflow_drift_check` + `test_per_workflow_regression_rejects_metadata_content_drift` + `test_three_per_workflow_judges_share_one_drift_message`（5 红） |
| 5 | 调用点 `margin * 2` | `test_leave_one_out_flip_point_through_the_real_gate` + `test_rate_check_passes_on_the_committed_snapshot`（2 红） |

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`tests/test_judgement_flip_points.py` | **15 passed**（0.24s） |
| 相关集：msys + ledger + flip points + live snapshot gate | **188 passed**（5.38s） |
| 全量（本机，Low `S-1-16-4096`） | **2197 passed / 113 skipped / 0 failed**（123.57s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（零生产代码改动） |

**对账**：总用例 **2307 → 2310**（+3）。Low `2197+113` = **2310**。

### 6.1 本会话只有一个 profile（如实记录）

本轮 venv 进程本身即 Low（`_token_il_sid` 进程内回读 = `S-1-16-4096`）；
`_git_transport_blocked_probe()` 在 Git Bash 与 PowerShell 下均为 `True`
（cmd 的探测命令因引号问题未成功执行，未计为实测；R70 记录三处均 `True`）。
因此全量跑出 **2197/113**，**28-skip profile 本会话复现不出来**——与 R70 §6.1
同型（R71 曾相反）。这是会话状态，不是本轮改动引起的：生产代码 md5 未变，
新用例不碰 git/subprocess。**本报告不写未实测的 High 数**；High 侧由 CI 的
ubuntu / windows 日志给出。

## 7. 未做与未验证的事（如实记录）

1. **没测到 High profile**：本会话进程即 Low；未用 `runas`/命名对象等手段强改
   （B1 拍定不追 msys 对象 ACL）。
2. **只对齐了 rate 判据的 3/4 分支**：`check_per_workflow` 与
   `check_per_workflow_regression` 也共用 `_per_workflow_drift`，但它们的
   「缺元数据文件」「内容为空」等分支没有逐条用同一组计数对齐；M4 证明
   `failed` 字段的漂移它们都看得见，但顺序/分支覆盖不在本轮范围。
3. **A 不唯一**：见 §2，M5 同时咬住既有用例；它的增量是真实入口的连通性。
4. **skip 不等于通过**：113 条在 Low 下未执行，本轮没有改变这一点。
5. **未跑 e2e / docker build / npm run build / 未重启 8021**：零生产与零前端改动。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
7. **重导仍被数据卡住**：`data/workflows/*/runs/run-*.json` 仍是 **40 个**，
   最新 `run-dfe789fd.json` 仍是 `2026-10-28 08:34`（本轮实查）。

## 8. 下一轮候选

1. **有新 run 后再重导**：唯一被外部数据卡住的候选，已连续多轮。
2. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
3. **重跑频率的可观测性**（R68 §7-4）：重跑真的频繁出现时，该改的是容差。
4. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile
   的路径，但可能动正在被 shell 使用的命名对象。
5. **另外两条判据的 3/4 分支对齐**（本轮新增）：`check_per_workflow` /
   `check_per_workflow_regression` 的退出 3/4 分支用各自计数走一遍。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

推送 `ffa5bd9`（两次提交：`76989ea` test + `ffa5bd9` docs；一次 `git push`，
`9bb1b5e..ffa5bd9`，经 socks5 10808——本轮直连 `000`、socks5 `200`）。

| run | 触发 commit | 结果 |
|---|---|---|
| **41214865619** | `ffa5bd9` | 五 job 全部 `success`，**一次通过、无重跑**（15:26:32 → 15:31:13，约 4m41s） |
| — | `Desktop Windows` | **未触发**：`head_sha=ffa5bd9…` 下 `total_count=1` |

| 项 | 实证（下载日志解码后逐字比对，不是推断） |
|---|---|
| 五个 job | backend（15:28:49）/ windows-backend（15:31:13）/ frontend（15:28:28）/ container-config（15:26:39）/ container-build（15:27:12）全部 `success` |
| 用例数（ubuntu） | `2245 passed, 65 skipped, 1 warning in 93.56s` = **2310** |
| 用例数（windows） | `2281 passed, 29 skipped, 1 warning in 217.33s` = **2310** |
| 新用例在 CI 上真跑 | ubuntu 2242/65 → **2245/65**（+3）；windows 2278/29 → **2281/29**（+3） |
| 校准步骤照旧 | `OK  逐 workflow 提前量已复算（本步不作判定）` |
| e2e | `[e2e] 10/10 场景通过`（只 ubuntu 有；windows 日志里 `e2e_workflow_stub` 出现 **0** 次） |
| 前端 | `# pass` 合计 **490**、`# fail` 合计 **0**（8 个块） |
| 容器 | `container-config` success；`container-build` 真跑 `buildx build`（GHA cache）+ `容器镜像冒烟全部通过: determinflow-core:ci` |

**三面实测一致**：本机 Low `2197+113` = 2310、ubuntu `2245+65` = 2310、
windows `2281+29` = 2310。**本机 High 本会话不可得**（进程即 Low），因此不写
第四面；28-skip profile 的缺失在 §6.1 已如实记录，不用算术补数。

**取证方法**：沿用 R71 的两条坑——`actions/jobs/<id>/logs` 需认证；302 到
Azure blob 的 SAS URL 自带签名，**跳转后的请求必须去掉认证头**；先 `-r 0-0`
读 `Content-Range` 总长，再按 48KB 分块 Range 拼接。本轮五份日志实到字节数
与总长逐字节相等（backend 137966、windows 77098、frontend 222197、
container-config 9874、container-build 76911）。
