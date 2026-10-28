# DeterminFlow (xs2) 交接报告 — Round 47（四项技术债并行收口）

> 本轮定位：按用户选定的四项（R46 §8 候选 1/2/3 中的三项 + 画像对比演进）做维护轮。
> 基线：`b74eff4`（R46 收尾）。
> 用户同时确认：CI e2e **继续暂缓**（模型凭据设计未决，与 R46 一致）；
> 端口竞态采用「后端自选端口并上报」方案。

## 1. 为什么这一轮值得做

四项各自对着一处「已知会疼、但一直没治」的位置：

1. **错误分类顺序**（R46 §5-2 自曝）：`_ERROR_CLASS_PATTERNS` 把宽匹配的
   `stream|chunk` 排在 `connection` 前面，导致真实文本
   `peer closed connection without sending complete message body (incomplete
   chunked read)` 被判成 **流式停摆** 而不是 **连接错误**。这不是文档问题——
   失败率时间序列的分类桶本身是错的，而分类正是「哪个供应商在哪一类故障上涨」
   的唯一读数。
2. **端口 TOCTOU**（R46 §10.3 定位）：`backend.rs:244` 的 `reserve_local_port()`
   是「bind 拿号 → listener drop 释放 → 后端按号码重新 bind」的两步设计。两步
   之间任何进程占走该端口，后端就在**初始化全部完成后** bind 失败并自关，
   表现为 Full NSIS 冒烟在 180 秒里一直读不到 200。R46 判为 flake 是对的，
   但「重跑即绿」不是修复。
3. **闸门判不到真实数据**（R46 §2.1 判据边界）：R46 把闸门接进了 CI，但判的是
   **固定** fixture，它自己写明了「保护的命题是闸门与脚本不退化，不是供应商今天
   健康」。于是「失败率升高」这件事在 CI 上依然无人发现。
4. **画像对比只有差值，没有结论**（R45 §8-5）：R43 的对比列把每个阶段的
   `-17%` 摆出来，用户还得自己数哪个阶段退步了、退了几次。

## 2. 落地内容

### 2.1 错误分类改为「强信号优先、宽匹配兜底」（`src/workflow/run_profile.py`）

**改法**：把 4 条扁平模式改成 6 条两层结构。

| 层 | 桶 | 匹配 |
|---|---|---|
| 1 | `http_5xx` | 数字状态码（500/502/503/504/524/529/530）——最无歧义 |
| 2 | `connection`（强） | `peer closed` / `connection reset\|refused\|aborted\|closed` / `incomplete chunked read` / `连接被重置\|拒绝\|中断\|断开` |
| 3 | `stream_stall`（强） | `no streaming chunk` / `stream_chunk_timeout` / `流式停摆` / `停摆` |
| 4 | `timeout` | 显式超时措辞 |
| 5 | `stream_stall`（宽） | 仅 `stream\|chunk\|流式` |
| 6 | `connection`（宽） | 仅 `connection\|refused\|reset\|unreachable\|连接` |

**为什么必须两层而不是简单调序**：LangChain 的停摆原文里带一句
`The connection may be alive at the TCP layer`。若只把 `connection` 整桶提前，
**所有**流式停摆都会被误判成连接错误——把 §5-2 的 bug 换成反向的同款 bug。
两层结构让「真连接故障」和「真流式停摆」各归其位。

**用真实文本做的前后对比**（本机 `data/workflows` 与 fixture 的全部 12 条去重
错误文本，逐条新旧各判一次）：

| 错误文本 | 旧桶 | 新桶 |
|---|---|---|
| `peer closed connection ... incomplete chunked read` | stream_stall | **connection** ← 本轮要修的 |
| `No streaming chunk received for 120.0s (…stream_chunk_timeout…)` ×3 | timeout | **stream_stall** |
| `No streaming chunk received for 600.0s` | timeout | **stream_stall** |
| `Error code: 530 - Cloudflare Tunnel error` ×2 | http_5xx | http_5xx（不变） |
| `JSON 解析失败` / `退出码 1` / `导出终止…` / 长度上限 / Traceback | other | other（不变） |

后两条变化值得说明：旧桶把它们判成 `timeout` 纯属巧合——原文里并没有超时措辞，
命中的是 `stream_chunk_timeout` 这个**参数名**里的 `timeout`。语义上它们确实是
流式停摆（模型停止产出 chunk），新桶更准。

**3 条钉测**（`test_run_profile.py` 143 → 4 条分类用例）：
`test_classify_error_prefers_specific_signal_over_broad_one`（peer closed → connection）、
`test_classify_error_stream_stall_is_not_swallowed_by_connection_wording`（带 TCP
措辞的停摆仍归 stream_stall）、`test_classify_error_keeps_plain_timeout_distinguishable`
（显式超时不被附近的 chunk/stream 字样抢走）。

### 2.2 端口 TOCTOU 根治：后端自选端口并上报（`backend.rs` + `entrypoint.py` + 两个 smoke 脚本）

**旧协议**（TOCTOU 来源）：

```
Rust: TcpListener::bind(("127.0.0.1", 0)) → 拿端口号 → listener 随函数返回 drop（端口释放）
Rust: 把号码通过 --port 传给后端
Python: 后端按号码重新 bind  ← 窗口就在这里：号码可能已被别人占走
```

**新协议**：

```
Rust: --port 0 → 等后端把实际端口写进 <user_root>/config/backend-port
Python: socket.bind(("127.0.0.1", 0)) → getsockname() 拿实际端口 → 写端口文件
Python: uvicorn Server.run(sockets=[sock])  ← 同一个 socket 直接交给 uvicorn
Rust: 读到 LISTEN_PORT=<n> → url = http://127.0.0.1:<n>
```

关键在最后一步：**socket 从 bind 到进 accept 循环全程不释放**，因此「先释放再
复用」这个窗口在结构上不存在了，不是被变窄，是被删除。

| 文件 | 改动 |
|---|---|
| `desktop/src-tauri/src/backend.rs` | 删 `reserve_local_port()`（含 `TcpListener` 导入）；新增 `read_port_file()`；启动参数改 `--port 0`；读端口失败时**先结束子进程**再报错 |
| `desktop/python/entrypoint.py` | `--port` 变可选；`--port 0` 走 `_serve_self_select()`；其余路径把端口写 stdout `LISTEN_PORT=<n>` |
| `desktop/scripts/smoke_backend.py` | 删 `_free_port()`；新增 `_read_listen_port()`；`--port 0` 起进程 |
| `desktop/scripts/smoke_installer.ps1` | 删 `Get-FreeTcpPort`；新增 `Get-BackendPortFromFile`；`Start-TestBackend` 改 `--port 0` |

**`read_port_file` 的一个诊断改进**（顺带）：同时轮询 `child.try_wait()`，子进程
提前退出时**立刻**返回「后端在报告端口前退出（exit status: N）」，而不是把 90 秒
超时白等完。「后端崩了」与「后端慢」在诊断上是两回事，混在一起会让人以为是慢。

**端到端实测**（源码态真实起服务，不是推理）：

```
reported port: 53855
status HTTP 200
```

即：后端自选端口 → 写端口文件 → 上层读到 → `/api/system/status` 返回 200。

**1 条契约钉测**（`test_desktop_packaging.py::test_desktop_backend_self_selects_its_port`）
钉五件事：`reserve_local_port` 必须不存在、Rust 传 `--port 0`、两端都用
`LISTEN_PORT=` 协议、后端用 `sockets=[sock]` 交接、两个 smoke 脚本不得再自行预留端口。
**变异验证**：把 `.arg("0")` 改回 `.arg("8020")` → 该测试红（已实测并还原）。

**Rust 编译面如实记录**：本机 `cargo check` 卡在 `ring` 的 C 编译（MSVC `cl.exe`
报错，与本次改动无关；历轮都未在本机构建 Rust 前端）。已做的是 `rustc --edition 2021
--crate-type lib --emit=metadata` 单文件解析（唯一报错是预期的 `use tauri` 未链接），
加上逐行人工复核。**权威验证只能来自 CI 的 `Desktop Windows` job。**

### 2.3 闸门判真实数据：入库真实快照 + 独立闸门脚本（新）

**路线选择**：R45 §2.4 给了 artifact 聚合与「提交真实形状数据 + `DETERMINFLOW_DATA_DIR`」
两条路。本轮走后者，但**不是**复用 R46 的固定 fixture——那条已经判过一次且判据
边界写清了。新做的是**真实快照**：

- `tests/fixtures/live_snapshot/`：从本机真实 run 记录裁剪，18 个 run / 188KB
- `snapshot-meta.json`：导出时算出的判定数字（per-workflow 与 totals）
- `scripts/export_run_samples.py`：**可复现的导出器**（R46 §7-1 说「重新生成的做法
  见 §2.1 的裁剪表」——那只是文档，本轮变成脚本）
- `scripts/check_live_snapshot_gate.py`：对快照判失败率的独立闸门

**导出器的正确性判据不是「看起来对」**：对每个 run 计算裁剪前后的
`build_run_profile`，任一字段不等就拒绝写入并以退出码 1 结束。这条判据是 R46 §2.1
「画像逐字段完全相同」那句的**可执行版本**——下次 `build_run_profile` 加了影响
成败判定的字段，导出时会当场炸，而不是等下一轮有人发现 fixture 过时。

**闸门的三条设计取舍，每条都是为了不当「又一个永远绿的防护」**：

| 取舍 | 为什么 |
|---|---|
| 阈值由快照自身实测失败率 + 余量算出（默认 +10 个百分点） | 写死阈值会在快照重导后静默失准 |
| 先校验「元数据与内容复算一致」，漂移即退出码 4 | 否则闸门拿旧阈值判新内容，看着在工作，判的是别的数字 |
| 退出码 0/1/3/4 各自可分 | 沿用 R45/R46 语义：「超阈」与「没判到」必须能分开 |

**新增退出码 4（元数据漂移）的理由**：R45 引入 3 是为了区分「闸门没生效」与
「闸门判了且不合格」。本轮引入 4 是同一个思路的延伸——「闸门判了，但判的是
过期数字」是第三种失效，不能挤进 0（假绿）也不能挤进 1（假红）。

**CI 接线**（`ci.yml` backend job 现在有 7 个 step，两个闸门并存）：

| step | 判什么 | 数据 |
|---|---|---|
| `Provider failure-rate gate self-test (fixture)`（R46） | 闸门与脚本行为不退化 | 固定 fixture，三态 0/1/3 |
| `Provider failure-rate gate against real snapshot`（**R47 新**） | 这批真实 run 的失败率 | 入库真实快照，阈值动态算 |

**shell 语义踩到并修掉的一处**：第一版写 `python … ; code=$?`，在 GHA 默认的
`bash -e` 下非零退出会直接中断脚本，后面的 `cat` 与 `exit $code` 都不执行——
行为上没错，但**解释退出码的那段提示永远不会打印**。改成
`code=0; python … || code=$?` 后本地实测：正常时 `captured=0`、漂移时
`captured=3` 且 final exit=3。这条记在这里，因为「CI 脚本里 `$?` 被 `set -e`
抢走」是很容易静默失效的一类写法。

**11 条契约测试**（新 `tests/test_live_snapshot_gate.py`）分五组：CI 真的调用、
指向快照而非 fixture、与 fixture 自检并存、快照与元数据一致、阈值非写死、
漂移可检出、快照不含载荷、体积可控。

**四个变异全部咬合（其中一个最初逃逸，已修）**：

| 变异 | 预期 | 实测 |
|---|---|---|
| CI 的 `DETERMINFLOW_DATA_DIR` 改指 fixture | 红 | ✓ |
| 删掉元数据漂移检测 | 红 | ✓ |
| 快照里注入 `summary` 载荷字段 | 红 | ✓ |
| 阈值替换成写死的 `15.0` | 红 | ✓（**第二版才咬住**，见下） |

阈值那条最初**没咬住**：第一版断言「余量 0 与余量 50 得到的判定说明不同」，而
说明文本里本来就含余量文字，写死阈值的变异照样能骗过去。改成从说明里**正则取出
阈值数字**再比数值才真正咬住。这条与 R46 §2.3 记录的「断言粒度太粗导致变异逃逸」
是同一类失效，说明它对静态断言是常态而非偶发。

### 2.4 画像跨 run 对比视图演进（前端）

**R43 的问题**：对比列把每个阶段的 `-17%` 摆出来，但「到底哪个阶段退步了、
退了几次」要用户自己数。

**本轮加的是结论层**，两处：

1. **顶部阶段变化摘要**：`退步 2 · 改善 1 · 持平 1 · 不可比 1（共 5 个阶段）`，
   下面跟一排带符号的节点 chip（退步红、改善绿，按退步优先排序）。
2. **「只看有变化的阶段」开关**：过滤掉持平与不可比，只剩需要行动的阶段。

**刻意保持的一条诚实语义**：`incomparable`（任一侧无尝试）**单列一档，不混进
`flat`**。`flat` 的意思是「比过了、没变」，而「无数据」不等于「没变」——这是
R43 就在守的纪律（`comparable=False` 不伪装 0%），本轮在分档层继续守。

**纯函数**（`runProfileView.ts`）：`stageChangeOf()` / `summarizeStageChanges()` /
`describeStageChanges()`——三者都无副作用，因此摘要与列表过滤**口径必然一致**
（不会出现摘要说 2 个退步、列表只剩 1 个）。

**踩到并修掉的一个自身缺陷**：加「只看变化」后，阶段卡片的 `#n` 序号仍按**过滤后**
的数组下标算，同一 node 重复执行时序号会漂（`agent_deep #1/#3` 变成 `#1/#2`）。
改成在**原始 `stages`** 上用 `indexOf` 定位。这条写在这里是因为它只在
「同 node 多次执行 + 开启过滤」的组合下出现，单看代码不容易发现。

**8 条新测试**（view 4 + panel 4），`incomparable` 变异（改成返回 `flat`）实测咬合。

## 3. 对历轮记录的两处认知修正

1. **R46 §5-2 说「分类是关键词启发式，顺序敏感」——但它把原因归到「越具体的
   越先匹配」，实际更微妙**：单纯按「具体程度」排会把 `connection` 整桶提到
   `stream_stall` 前面，而 LangChain 停摆原文含 `The connection may be alive…`，
   结果是把本已正确的流式停摆判错。正确解法是**每个桶分强弱两层**，不是简单的
   单维排序。
2. **R46 §10.3 把端口竞态写成「彻底修法是让 Rust 端用 SO_REUSEADDR + 重试，或
   把端口分配改为后端自己选」——本轮确认后者才是根治**：`SO_REUSEADDR` 只是让
   释放后的端口更容易被抢回来，仍是两步协议，窗口仍在；「后端自己选 + 同一个
   socket 交接」才是把两步变一步。本轮选的是后者（用户也选的这项）。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_live_snapshot_gate.py`（**新**） | **11 passed** |
| 定向：`test_run_profile.py` | **31 passed**（含 3 条新分类测试） |
| 定向：`test_desktop_packaging.py` | **34 passed / 1 skipped**（含 1 条新端口契约） |
| 定向五文件合计 | **100 passed / 1 skipped** |
| Low-IL 全量 | **1899 passed / 96 skipped / 0 failed**（121.41s） |
| High-IL 全量（权威） | **1984 passed / 11 skipped / 0 failed**（139.12s） |
| 前端 8 组 | **471 passed / 0 fail**（R46 为 463，+8） |
| 前端 lint / build | 0 problems / ✓ 6.17s |
| 插件相关（Low-IL `-k plugin`） | 236 passed / 72 skipped |
| 存储名审计 | **[clean]** exit 0 |
| 真实快照闸门实跑 | 3.74%（7/187）未超阈值 13.7% → **exit 0** |
| 失败率时间序列（收官） | 23 runs / 243 尝试 / 7 失败 / **2.9%** |

**对账**：

- Low-IL：R46 1884 **+ 15** = **1899** ✓
- High-IL：R46 1969 **+ 15** = **1984** ✓
- 总用例 R46 口径 1980 → **1995**（High passed+skipped：1984 + 11）
- 前端：R46 463 **+ 8**（view 4 + panel 4）= **471** ✓

新增 15 条 Python 用例的构成：分类 3 + 端口契约 1 + 真实快照闸门 11。零净减，
本轮无删除。

## 5. 未做与未验证的事（如实记录）

1. **Rust 端未真正编译过**：本机 `cargo check` 失败于 `ring` 的 C 编译
   （MSVC `cl.exe`，与改动无关），历轮同样未在本机构建 Rust。已做单文件
   `rustc --emit=metadata` 解析 + 人工复核。**`backend.rs` 的权威验证只能来自 CI
   的 `Desktop Windows` job**（`Build core/full NSIS installer` + `smoke_installer.ps1`）。
   若新协议有问题，最可能的红点是冒烟脚本读不到 `config/backend-port`。
2. **CI 的新 step 本机没在 GitHub Actions 上跑过**：本机无 GHA。已在 Git Bash 用
   `bash -eo pipefail` 实测退出码传递（0 与 3 两种），但 `${{ github.workspace }}`
   展开与 runner 上的 yml 解析仍需真实 CI 验证。
3. **快照有保鲜期**：`live_snapshot` 是 2026-10-28 本机数据的切片。它不会自动更新
   ——更新方式是重跑导出器。`check_live_snapshot_gate` 会在「内容变了但元数据没重导」
   时报退出码 4，但**它无法察觉「整体数据都旧了」**（旧数据自身仍自洽）。闸门判的是
   「这批样本的失败率没有恶化」，不是「供应商今天健康」。
4. **`--port 0` 之后端口不再是外部可控的**：若将来有场景需要固定端口（例如反代），
   得走 `--port <n>` 的旧路径——该路径仍然保留并测过（`--port 8021` 解析正常），
   只是桌面客户端不再使用。
5. **`config/skills_config.json` 仍是未入库的运行时写入**（B23/R36 定性，与历轮一致）。
6. **本轮未重启 8021 服务**：改动面不含后端运行时代码（`entrypoint.py` 只影响桌面
   打包出的可执行文件，源码态 `run.py` 路径未变）。
7. **`_free_port` 在 `tests/test_plugin_processes.py` 里仍存在**：那是测试自己的
   辅助函数，与被根治的启动路径无关，未动。

## 6. 本轮改动一览（12 改 5 增）

| 文件 | 变更 |
|---|---|
| `src/workflow/run_profile.py` | 错误分类 4 条扁平 → 6 条两层（强信号优先） |
| `desktop/src-tauri/src/backend.rs` | 删 `reserve_local_port`；新增 `read_port_file`（含子进程退出检测）；`--port 0` |
| `desktop/python/entrypoint.py` | `--port` 变可选；`_serve_self_select()` 用同一 socket 交接 uvicorn |
| `desktop/scripts/smoke_backend.py` | 删 `_free_port`；新增 `_read_listen_port` |
| `desktop/scripts/smoke_installer.ps1` | 删 `Get-FreeTcpPort`；新增 `Get-BackendPortFromFile` |
| `.github/workflows/ci.yml` | backend job 新增真实快照闸门 step（第 7 步） |
| `web/src/components/workflow/runProfileView.ts` | 新增 `stageChangeOf` / `summarizeStageChanges` / `describeStageChanges` |
| `web/src/components/workflow/RunProfilePanel.tsx` | 变化摘要块 + 「只看有变化的阶段」开关 + 序号定位修正 |
| `tests/test_run_profile.py` | +3 条分类测试 |
| `tests/test_desktop_packaging.py` | +1 条端口契约测试 |
| `web/src/components/workflow/runProfileView.test.ts` | +4 条 |
| `web/src/components/workflow/RunProfilePanel.test.ts` | +4 条 |
| `scripts/export_run_samples.py` | **新增**（可复现裁剪导出器，含画像等价校验） |
| `scripts/check_live_snapshot_gate.py` | **新增**（真实快照闸门，退出码 0/1/3/4） |
| `tests/test_live_snapshot_gate.py` | **新增**（11 条契约） |
| `tests/fixtures/live_snapshot/` | **新增**（18 run / 188KB + `snapshot-meta.json`） |
| `docs/HANDOVER_ROUND47.md` | **新增**（本文） |

## 7. 遗留风险与需人工确认事项

1. **`backend.rs` 未经真实编译**（见 §5-1）。这是本轮**唯一**有编译期风险的改动。
   建议推送后第一时间看 `Desktop Windows` 的 `Build core NSIS installer` 与
   `smoke_installer.ps1` 结果。
2. **快照需要周期性重导**：建议与「轮次收官跑 `--summary`」同批做，即每轮把
   `export_run_samples.py --dest tests/fixtures/live_snapshot --limit 2` 跑一次并提交。
   不重导不会报错（旧快照自洽），只是判据逐渐失真。
3. **`live_snapshot` 的 .gitignore 边界**：实测 `git check-ignore` 未命中（`data/**`
   只管 `data/` 目录），但若将来有人放宽忽略规则需复核。
4. **阈值余量 10 个百分点是判断值**，不是统计结论。快照失败率低（3.74%）时
   13.7% 的阈值很宽松；若快照失败率升到 20%，阈值会变成 30%，保护力下降。
   收紧方式：`check_live_snapshot_gate.py --margin 5`。
5. **High-IL 跑法必须用 Windows 反斜杠路径 + `py.exe` + PYTHONPATH**
   （PROJECT_INFO 平台注意事项 9），本轮照做得到 1984/11/0。
6. **`F:\DeterminFlow x2` 路径含空格**：本轮仍未碰 Rust 构建产物，无影响。
7. **插件仓推进必须刷新本仓锁**（R42 纪律）：本轮插件仓零提交，
   `official-plugins.lock.json` 无需刷新。

## 8. 下一轮候选

1. **CI e2e**（R45 §8-3 / R43 §2.3 选项 B）：仍是最有价值的缺口，前置条件仍是
   「CI 无模型凭据」的设计决策（桩 provider vs 仅手工触发）。用户已连续两轮暂缓。
2. **快照保鲜自动化**：把「重导 live_snapshot」接进轮次收官动作清单，或做一个
   `--check-stale`（比对快照时间与 `data/workflows` 最新 run 时间）。
3. **循环节点与重试语义区分**（R41 §9-3）：需后端 Core 配合，用户已确认继续挂着。
4. **`--port 0` 协议的 macOS 面验证**：`desktop-macos.yml` 用的是同一份
   `entrypoint.py`，但 macOS 的 `process_group(0)` 路径未在本轮复核。
5. **画像对比的多 run 基线**：当前只与「上一次 run」比。若要判趋势（连续 3 次
   都在退步），需要后端提供多点对比——工作量中等，价值取决于是否真有人看趋势。

其余：POSIX 真跑已由 CI 覆盖（R43 结论），大陆下载加速维持现状（R44 结论）。

## 9. 本轮未实际运行

- **未在 CI 上验证两个新东西**：真实快照闸门 step（本机用 `bash -eo pipefail`
  实测了退出码传递）、`--port 0` 启动协议（本机源码态实测了端到端，但**冻结可执行
  文件**只在 CI 上构建）。
- **未真正编译 Rust**：见 §5-1。
- **未重启 8021 服务**：改动面不含后端运行时代码。
- **未跑 `docker build`**：本机仍无 docker/wsl（R43/R44/R45/R46 复核仍不可用）。
