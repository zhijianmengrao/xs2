# DeterminFlow (xs2) 交接报告 — Round 49（CI e2e 桩 provider + 快照覆盖度）

> 本轮定位：R48 §9-1「CI e2e（桩 provider）」，用户在 R49 开工前拍定主攻方向，
> 并同时拍定两个不冲突的小项：快照覆盖度**单独成退出码 6**、macOS **不打 tag**
> 只确认手动触发口。
> 基线：`aaec0de`（R48 收尾，已有 Low 1905/96/0、High 1990/11/0、前端 471/0）。
> 快照保鲜容忍天数按用户选择**保持默认 7 天**，未改。

## 1. 为什么这一轮值得做

R45/R46/R47 连续三轮把「CI e2e」写进 §9 候选，每一轮都补一句「本轮未开工」。
它一直没做，卡的不是工作量，是**凭据**：真实 e2e 要一家供应商的 key，而 key
不能进 CI —— fork PR 拿不到 secrets，公网仓库也不该为了跑测试烧额度。这个约束
不动，缺口就会一直挂下去。

桩 provider 把这个卡点换成两件可控的事：

- **协议是真的**。一个真实监听 127.0.0.1 的 HTTP 服务，吐真实的
  `text/event-stream` 分块。被测代码走的是完整链路——ChatOpenAI SDK → 流式
  解析 → LangGraph 节点 → 工具调用 → 引擎回调 → Task 落盘。整条链上只有
  「谁生成的这些 token」是假的。
- **判定是真的**。桩按请求内容决定回什么，所以断言落在「节点是否真的流转到
  下一个」「失败是否真的被策略接住」「上游产出是否真的进了下游提示词」上，
  而不是「有没有返回 200」。

它**不**判模型质量、提示词优劣、供应商健康。那三件事分别属于人工验收、
`provider_failure_profile.py`、真实快照闸门（R47/R48）。把它当成「CI 里有个
假 LLM 所以模型行为也被测了」是误读——这一点写进脚本开头，免得下一轮误解。

## 2. 落地内容

### 2.1 `scripts/stub_llm_provider.py`：OpenAI 兼容桩（328 行）

纯标准库（`http.server` + `threading`），没有新依赖。四种响应语义，全部由请求
内容决定，纯函数 `decide(payload)` 可单测：

| 条件 | 响应 | 为什么 |
|---|---|---|
| 最后一条是 `role=tool` | 纯文本收尾 | 工具结果已回来，模型该总结而不是再调一次 |
| 提供了 `complete_task` / `complete_node_task` | 指向它的 tool_call | 这是「节点完成」的唯一信号，引擎靠它流转 |
| 首条 user 消息含 `[stub:fail]` | 同上但 `status="failure"` | 验失败策略 |
| 其他 | 固定文本 | — |

**第一行是最容易写错的一行**：若对 `role=tool` 仍返回 tool_call，agent 图会在
llm↔tools 之间空转到轮次上限，CI 上表现为**超时**而不是失败——超时不会被读成
「桩写错了」。§3 的变异 1 就是专门撞这一条。

流式响应包含 `finish_reason`、空 choices + usage 的收尾块、`data: [DONE]`，
三样都是 ChatOpenAI SDK 期望的形状（`create_llm` 在流式下总会请求
`stream_options.include_usage`）。`tests/test_ci_e2e_stub.py` 里有一条测试真起
端口验这些字节，因为 `decide` 全绿而协议层写错的情况是存在的。

### 2.2 `scripts/e2e_workflow_stub.py`：真跑编排（556 行）

装配顺序照 `src/web_server.py` 的 lifespan 抄（去掉 MCP / 扩展 / cron / 记忆等
与编排无关的部分），装的是**真组件**：`SessionManager`、`WorkflowManager`、
`WorkflowEngine`、`AgentNode`、`ToolRegistry`（真实 35 个工具）、`PromptBuilder`。

三个场景：

| 场景 | 断言 |
|---|---|
| `happy_path` | 2 agent + 1 script 全 completed；`{{writer_output}}` 已解析且上游文本真的出现在下游的模型请求里 |
| `failure_propagates` | 带 `[stub:fail]` 的节点 failed，下游未执行，任务未 completed |
| `turn_terminates` | 关 auto_flow 的单节点仍 completed，且模型请求数 ≤ 8（空转会暴涨） |

**为什么是独立脚本 + 独立进程，不是 pytest 用例**：`src/config.py` 在 import
期就把 `DATA_DIR` / `WORKFLOWS_DIR` 求值成模块常量。在 pytest 进程内改 env 已经
太晚，只能逐个 monkeypatch 十来个模块常量——那种写法每加一个模块就漏一处，且
跑完污染同进程后续用例。独立进程 + 临时 `DETERMINFLOW_DATA_DIR` 从根上避免这两个
问题，也让 CI 里这一步是**真的**跨进程端到端。

`CONFIG_DIR` 刻意**保持指向仓库真实 `config/`**：本 e2e 要验的是真实配置能否
驱动真实编排。配置被换成假的就是另一个测试了；只有模型供应商那一条由
`MODELS_CONFIG_FILE` 单独覆盖到桩。

### 2.3 接进 CI（`ci.yml` backend job 第八步）

`Workflow orchestration e2e (stub provider)`，`timeout-minutes: 10`（正常约 10s；
卡住通常是桩没回 SSE 收尾导致图空转，该红而不是把 job 拖到 6 小时上限）。

**不引 secrets**，这是整条路线的前提。有 `test_ci_e2e_step_takes_no_secrets`
反向钉死：加了 secrets 就退回「fork PR 跑不了」。

退出码 0 / 1（编排行为不符）/ 3（环境无法启动）**都让这一步红**，区分只体现在
提示文案（`::error::` 里写「先看装配栈，不是编排语义」）。这里有一个我改过一次
的取舍：初版写成「3 降级成 `::warning::` + `exit 0`」，随即发现那正是 R45/R46/R47
反复批评的**永远绿的防护**——环境起不来通常是 import 链断了，那本身就是回归。
改成全部透传，并加了 `test_ci_e2e_step_is_not_a_permanently_green_step` 反向钉住
「不得 `exit 0`、不得降级成 warning」。

### 2.4 `--check-coverage`：快照覆盖度，退出码 6（86 行）

R48 的 `--check-stale` 只判时间。它判不到的那一半是：**新增了 workflow 而快照
里没有它**——那时快照可能仍然「尚新」，却已不代表真实覆盖面（R48 §8-2 原话）。

判据：`data/workflows` 里「有 run 记录」的工作流名集合，减去快照里同样的集合。
只判「真实有、快照没有」；反方向（快照有、真实已删）不报——删掉的工作流留在
快照里只是冗余样本，不影响代表性。

**退出码 6 与 5 为什么必须分开**（用户拍定单独成码）：5 是「重导一次就好」，
6 是「快照的 workflow 集合已经不完整，重导后还要看新工作流是不是真进了样本」。
并进 5 会让人对着一个只差一条 workflow 的快照去查导出脚本。这与 R47 引入 4、
R48 引入 5 是同一条纪律的第三次延伸：**处置不同就不能共用退出码**。

同样**不进 CI**（同一条理由：CI 检出无 `data/workflows`），有
`test_coverage_check_is_not_wired_into_ci` 反向钉死。

### 2.5 macOS：R48 的一处误记被纠正

R48 §8-4 与 §9-3 把 `desktop-macos.yml` 记成 "tag-only"，据此把「R47 的
`--port 0` 在 macOS 上未复核」又挂了一轮。**实际读文件**：它是
`workflow_dispatch` + `workflow_call` + `pull_request(paths: desktop/**)`，
**没有** tag 触发条件。

也就是说这一面一直是可验证的，误记让它被当成不可验证而无限期挂着。本轮不改
workflow（本来就不需要改），加
`test_macos_workflow_is_manually_dispatchable_without_a_tag` 钉死三件事：可手动
触发、PR 路径过滤含 `desktop/**`、没有 `tags:` 过滤器。下次再有人说它 tag-only，
测试会问一句「你读的是哪个文件」。

## 3. 测试（20 条新增，四个变异全部咬合）

| 文件 | 新增 | 钉什么 |
|---|---|---|
| `tests/test_ci_e2e_stub.py`（新） | 12 | 桩四态语义、两处常量一致、真实端口 SSE 协议、CI 真接线、无 secrets、非恒绿、退出码常量、场景集合 |
| `tests/test_live_snapshot_gate.py` | 7 | 覆盖度缺口 → 6、6≠5 且 6≠1、「时间对但集合缺」staleness 为绿而 coverage 为红、快照独有项不报、真实数据缺 → 3、元数据缺 → 3、不进 CI |
| `tests/test_desktop_packaging.py` | 1 | macOS workflow 可手动触发、非 tag-only、PR 路径覆盖 `desktop/**` |

（`test_live_snapshot_gate.py` 总数 17 → 24；`test_ci_e2e_stub.py` 新文件 12 条。）

**四个变异，全部咬合**：

| 变异 | 预期 | 实测 |
|---|---|---|
| 桩忽略 `role=tool`，继续调工具 | 红 | ✓ `turn_terminates` 红（10 次请求 > 8） |
| 桩忽略 `[stub:fail]` | 红 | ✓ `failure_propagates` 红（3 条断言同时中） |
| 覆盖度集合方向反了 | 红 | ✓ 4 条红 |
| `EXIT_COVERAGE_GAP = 5`（混进过期码） | 红 | ✓ 1 条红（显式断言 `code != EXIT_STALE`） |

第一个变异能咬合是本轮最关键的验证：它是「桩写错但测试看着通过」的唯一出路。
没有 `turn_terminates` 的请求数上限，那个变异会让三个场景全绿而 CI 只是在空转。

## 4. 本机实跑（全部实际执行）

```
$ python scripts/e2e_workflow_stub.py
[e2e] PASS happy_path: 4 次模型请求，3 节点 completed，上游产出已传下游
[e2e] PASS failure_propagates: 任务 failed，broken=failed
[e2e] PASS turn_terminates: 任务 completed，2 次模型请求
[e2e] 3/3 场景通过                                                   → exit 0

$ python scripts/check_live_snapshot_gate.py --check-coverage
[live-gate] 快照覆盖完整：真实数据 9 个工作流全部在快照内（快照含 9 个） → exit 0

$ # 手工造一个真实数据里多出来的 workflow 后
[live-gate] 快照覆盖不全：真实数据有 10 个工作流，快照缺 1 个
            ['wf-coverage-probe']。重导：python scripts/export_run_samples.py …  → exit 6

$ python scripts/check_live_snapshot_gate.py --check-stale
[live-gate] 快照尚新：… 滞后 -0.5 天 ≤ 容忍 7.0 天                     → exit 0

$ python scripts/check_live_snapshot_gate.py
[live-gate] 失败率 3.74% 未超出阈值 13.7%（187 次尝试，余量 10.0 个百分点）→ exit 0

$ python scripts/provider_failure_profile.py --fail-if-above 5 --summary
TOTAL: runs=23 attempts=243 failed=7 failure_rate=2.9%                 → exit 0
```

覆盖度缺口路径是**手工造数据实跑**确认的（造一个 `wf-coverage-probe` 再删掉），
不只是单测里的 tmp_path。

## 5. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_ci_e2e_stub.py` | **12 passed** |
| 定向：`test_live_snapshot_gate.py` | **24 passed**（17 + 7 新增） |
| 定向：`test_desktop_packaging.py` | **35 passed / 1 skipped**（icon.icns 需 macOS） |
| 收齐后 `--collect-only` | **2021 tests collected** |
| Low-IL 全量 | **1925 passed / 96 skipped / 0 failed**（124.90s） |
| High-IL 全量（权威） | **2010 passed / 11 skipped / 0 failed**（142.19s） |
| 前端 `npm test` | **471 passed / 0 fail**（本轮未碰前端，与 R47/R48 一致） |
| 变异 1（桩忽略 tool 结果） | 1 failed → 咬合 ✓ |
| 变异 2（桩忽略失败标记） | 1 failed → 咬合 ✓ |
| 变异 3（覆盖度方向反） | 4 failed → 咬合 ✓ |
| 变异 4（`EXIT_COVERAGE_GAP=5`） | 1 failed → 咬合 ✓ |
| 真实数据四种模式 | 覆盖 **0** / 覆盖缺口 **6** / 保鲜 **0** / 失败率 **0** 全部实跑确认 |

**对账**：

- Low-IL：R48 1905 **+20** = **1925** ✓
- High-IL：R48 1990 **+20** = **2010** ✓
- 总用例 R48 口径 2001 → **2021**（High passed+skipped：2010 + 11）
- 新增 20 条构成：`test_ci_e2e_stub.py` 12 + 覆盖度 7 + macOS 触发 1。零删除。

## 6. 本轮改动一览（4 改 3 增，含 1 文档）

| 文件 | 变更 |
|---|---|
| `scripts/stub_llm_provider.py` | **新增** 328 行：OpenAI 兼容桩（`decide` 纯函数 + SSE + `StubProvider` 上下文管理器 + CLI） |
| `scripts/e2e_workflow_stub.py` | **新增** 556 行：真实组件装配 + 三场景 + 退出码语义 |
| `tests/test_ci_e2e_stub.py` | **新增** 219 行：12 条契约 |
| `scripts/check_live_snapshot_gate.py` | +86 行：`EXIT_COVERAGE_GAP=6`、`_workflow_names_with_runs`、`check_coverage`、`--check-coverage`、互斥校验 |
| `tests/test_live_snapshot_gate.py` | +111 行：7 条覆盖度契约 |
| `.github/workflows/ci.yml` | +30 行：e2e step（含 `timeout-minutes: 10`） |
| `tests/test_desktop_packaging.py` | +36 行：macOS 触发契约（+1 条） |
| `docs/PROJECT_INFO.md` | R49 覆盖度判据 + CI e2e 两节 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 7. 未做与未验证的事（如实记录）

1. **未在 CI 上实跑过这个新 step**。本机三场景全绿、`ci.yml` 已用 `yaml.safe_load`
   验过结构，但「GHA ubuntu-24.04 + Python 3.11 上真跑」这件事**本轮未知**。
   风险面具体是两条：①`tests/conftest.py` 未参与（独立脚本），ubuntu 上
   `DETERMINFLOW_DATA_DIR` 等 env 名与路径拼接是纯字符串，风险低；②桩用的
   `http.server` 在 Linux 上的 `ThreadingHTTPServer` 行为与 Windows 一致，风险低。
   **仍未验证的就是「低风险」本身**，与历轮「本机绿 ≠ CI 绿」的纪律一致，如实记。
2. **未重导快照**：本机快照滞后 -0.5 天（比真实数据还新）、9 个工作流全覆盖，
   两条判据都绿，无需重导。
3. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。
4. **未触发 macOS 实跑**：修的是「误记为 tag-only」这件事，不是「跑过了」。
   `--port 0` 在 macOS 的 `process_group(0)` 路径**仍未在 darwin 上真跑过**——
   只是现在明确了它是可手动触发的（`workflow_dispatch`），不再是「等 tag」。
   这个缺口从「不可验证」降级成「可验证但本轮没做」，性质不同。
5. **桩不模拟真实模型的任何失败模式**：不模拟 429/5xx/流式停摆/超长输出。
   错误分类与重试语义由 `provider_errors` 里的单测和 `tests/fixtures/run_samples`
   的真实失败样本覆盖，桩若也去模拟就是造第二套不可信的失败语义。
6. **`--check-coverage` 的判据是「集合差」，不是「样本量是否足够」**。一个
   workflow 只要在快照里有一条 run 就算覆盖到了，哪怕它真实跑了 50 次。这是
   刻意的：判「够不够」需要一条统计判据（而失败率闸门已经在判代表性），混在
   一起会让退出码 6 的语义变糊。
7. **`--check-stale` / `--check-coverage` 互斥**（同时给会 `parser.error`），因为
   一个退出码只能表达一种处置。

## 8. 下一轮候选

1. **验证本轮 CI e2e 在 GHA 上真跑**（§7-1 的唯一未验证项）：推送后看
   `backend` job 的新 step。若红，先看是 `::error::e2e 无法启动（退出码 3）`
   还是编排断言——两者排查方向完全不同，这也是保留退出码区分的原因。
2. **桩支持故障注入**：`[stub:5xx]` / `[stub:429]` / `[stub:stall]` 让 CI 能验
   重试与错误分类**在真实 chain 上**的行为（目前只在单测层验）。与本轮的取舍
   不冲突：§7-5 拒绝的是「伪造失败语义」，而按真实 provider 的响应格式注入
   已知错误码是另一件事，需要先设计「注入哪几种才够用」。
3. **画像对比的多 run 基线**（R47 §8-5 / R48 §9-4，两轮挂着）：当前只与「上一次
   run」比，看不出「连续三次都在退步」。需后端提供多点对比，工作量中等。
4. **循环节点与重试语义区分**（R41 §9-3）：需后端 Core 配合，用户已确认继续挂着。
5. **macOS `--port 0` 真跑**：现在有 `workflow_dispatch`，可在需要时手动触发一次
   `desktop-macos.yml`（会跑 `smoke_backend.py --port 0`）。不需要打 tag，不产生
   发布物。

其余：POSIX 真跑已由 CI 覆盖（R43 结论），大陆下载加速维持现状（R44 结论），
快照保鲜容忍天数 7 天维持（用户本轮确认）。

## 9. 本轮未实际运行

- **未在 CI 上跑新的 e2e step**（§7-1）。
- **未触发 macOS 实跑**（§7-4）。
- **未重导快照**（两条判据都绿，无必要）。
- **未跑 `docker build`**（本机无 docker）。
- **未重启 8021 服务**：改动面是脚本、测试、CI 与文档，不涉及运行时代码。
