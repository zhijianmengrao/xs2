# DeterminFlow (xs2) 交接报告 — Round 50（桩故障注入 + 画像多 run 基线 + macOS 缺口收口）

> 本轮定位：R49 §8 五个候选中的前四项（用户拍定“1. 2. 3. 4.”全做），
> 外加推送后触发一次 `desktop-macos.yml`（用户确认）。
> 基线：`8727da3`（R49 收尾，Low 1925/96/0、High 2010/11/0、前端 471/0）。
> 先闭合 R49 遗留的唯一未验证项（CI e2e 在 GHA 上真跑），再做四项。

## 1. 本轮先做的事：把 R49 的未验证项验掉

R49 推送 `8727da3` 后，`CI` run **40723820649** 的 backend job 第 9 步
`Workflow orchestration e2e (stub provider)` **真跑并 success**。日志里三场景输出
与本机逐字一致：

```
[e2e] PASS happy_path: 4 次模型请求，3 节点 completed，上游产出已传下游
[e2e] PASS failure_propagates: 任务 failed，broken=failed
[e2e] PASS turn_terminates: 任务 completed，2 次模型请求
[e2e] 3/3 场景通过
```

顺带确认了一件事：`desktop-windows.yml` 的 `paths` 过滤**没有**被本轮改动带起
（本轮只碰 `.github/workflows/ci.yml`、scripts、tests、docs，不在它的 paths 里），
所以推送只触发了一个 CI run，没有误触发 NSIS 构建。

**这一段是本轮唯一靠外部环境才能得到答案的部分**，其余全部本机可验。

## 2. macOS `--port 0`：从“可验证但没做”变成“跑过了”

R49 §7-4 把这条从“不可验证”降级成“可验证但本轮没做”。本轮做了：

手动触发 `desktop-macos.yml`（run **40723984654**，`workflow_dispatch`，不打 tag、
不产发布物），`Build Apple Silicon full candidate` **success**，四步与 `--port 0`
直接相关的验证全绿：

| 步骤 | 结论 |
|---|---|
| Build and test frozen backend（含 `smoke_backend.py`） | success |
| Verify app, DMG and bundled backend | success |
| Verify backend from installed DMG copy | success |

`desktop/scripts/smoke_backend.py` 的事实（读码确认，不是推测）：它以
`Popen([exe, "--port", "0", "--user-data-dir", root])` 启动冻结后端，再从
`config/backend-port` 读回实际端口。**darwin 上的 `process_group(0)` / 临时端口
路径因此是真跑过的**，不再是挂账。

新增契约测试 `test_macos_smoke_really_runs_the_ephemeral_port_path`，钉**两层**：
workflow 里调了 `smoke_backend.py`，**且**脚本传的是 `--port` `0`。只钉第一层
不够——把端口改成固定值后同样“跑了 smoke”，覆盖却没了。

**必须区分 run 级与 job 级结论**：这个 run 的总体 `conclusion` 是 **failure**，
但原因是 `core candidate` job 被 GHA 并发策略 **cancelled**（同组只保留一个，
full candidate 跑完就取消了排队的另一个）。`Build Apple Silicon full candidate`
这个 job 本身是 **success**。两者跑同一份 `smoke_backend.py`，`--port 0` 的
结论由 full 的 success 支撑。**不要把 run 级的 failure 读成「macOS 验证失败」**
——那正是本轮要治的那类误读。

## 3. 桩故障注入（R50-1）

### 3.1 设计边界先说清楚

R49 §7-5 拒绝的是“桩也去模拟真实模型的失败语义”，理由是那会造出第二套不可信的
失败语义。本轮的注入**不是那件事**：

- 注入的是**真实 provider 会发出的 HTTP 状态码与错误体**（503 + `service_unavailable`、
  429 + `rate_limit_exceeded`、401 + `invalid_api_key`）；
- 经过的是**完整链路**：`openai` SDK 解析 → `provider_errors` 分类 →
  `_should_retry_provider_error` 判定 → `llm_client` 重试包装；
- 桩只决定“这一发返回什么状态码”，不发明新的失败类型。

### 3.2 标记与行为

| 标记 | 桩行为 | 期望被测行为 |
|---|---|---|
| `[stub:5xx]` | HTTP 503 + OpenAI 错误体 | 瞬时错误 → 重试 |
| `[stub:429]` | HTTP 429 + `rate_limit_exceeded` | 瞬时错误 → 重试 |
| `[stub:401]` | HTTP 401 + `invalid_api_key` | **永久**错误 → 不重试 |
| `[stub:stall]` | SSE 头 + 一个 chunk 后停住 | 触发 `stream_chunk_timeout` |
| `[stub:fail_once]` | 与上面的标记组合，只失败第一发 | 重试能救回来的唯一可观察证据 |

`injection()` 是纯函数（只看 `user` 消息；`role=tool` 的追问不触发——否则
“重试成功后的收尾请求”会被同一条标记打回，永远走不到成功路径）。`fail_once` 的
一次性语义放在 `StubProvider.claim()` 里，每场景 `reset_claims()`。

### 3.3 三个新场景

- `transient_error_is_retried`：503 一次后成功。断言“请求数 ≥ 2 且任务 completed”
  ——只看 completed 无法区分“重试救回来了”与“根本没失败”。
- `permanent_error_is_not_retried`：401 后立即失败、请求数必须为 1。与上一个场景
  互为正反面；只验“会重试”会让“把所有错误都重试”这种退步一路绿灯。
- `stream_stall_fails_fast`：停摆判失败、任务在预算内到终态、**部分流后不重试**
  （`retry_suppressed=partial_stream` 是刻意的：重发会在半截响应后再拼一段）。

`LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=2` 写进 `_isolate_environment`：默认 120s
会让 CI 上这一步慢两个数量级，而判据与超时具体值无关。

### 3.4 变异验证（三个咬合，一个不咬合并由此发现真问题）

| 变异 | 预期 | 实测 |
|---|---|---|
| `is_permanent_provider_error` 恒 False | 红 | ✓ 401 场景 3 次请求红 |
| 停摆不发 chunk（只发头就挂住） | 红 | ✓ 走到 httpx 读超时、无部分流、允许重试 → 3 次请求红 |
| 关掉 Core `retry.max_retries` | 红 | ✗ **仍绿** |
| 401 伪装成 5xx 类错误码 | 红 | ✗ 不咬合（分类以 HTTP 状态码为准，该变异本身无效） |

**第三个变异是本轮最有价值的发现**：关掉 Core 重试层后场景仍然绿，因为 LangChain
的 `ChatOpenAI` 自带 `max_retries=2`。只有**同时**关掉两层才红（1 次请求、任务
failed）。也就是说：

> `transient_error_is_retried` 判的是“重试总效果”，**不是**“Core 层重试”。
> 一条“Core 层重试失效”的回归，本场景抓不到。

这一点已写进场景 docstring 与 PROJECT_INFO，避免下一轮把它误当 Core 层守卫。
Core 层语义仍由 `tests/test_llm_client_params.py` 一类单测守。

## 4. 画像多 run 基线（R50-2）

### 4.1 为什么需要它

`compare_run_profiles`（R43）只与“上一次 run”比。它看不出“连续三次都在退步”——
每次单看都只是一次变化。R47 §8-5 / R48 §9-4 挂了两轮。

### 4.2 判据：连续相邻，不是与首个基线比

新增 `pick_recent_runs`（取当前 run 之前最近 N 个，升序）与
`compare_run_baseline`。`trend` 四态：

| trend | 条件 |
|---|---|
| `regressing` | 最近 `consecutive_required`(=2) 次相邻差值**全部 > 0** |
| `improving` | 同样连续、且全部 < 0 |
| `stable` | 其余（有涨有跌、持平、只有 1 次对比） |
| `insufficient` | 可比相邻对比不足 2 次——**不冒充 stable** |

为什么必须是“连续相邻”：序列 50% → 0% → 20% → 40%，与首个基线比是**改善**
（0.5 → 0.4），实际在退步。这条专门有一个测试
（`test_baseline_is_not_fooled_by_a_spike_then_regression`）。

### 4.3 端点与前端

`GET .../run-profile?baseline_limit=N`（N≤20，上限防一次请求扫遍上百条记录）。
与 `?compare=true` **相互独立**：comparison 判“比上一步退了没有”，baseline 判
“是否在连续变坏”。前端运行画像抽屉加“连续趋势（最近 5 次）”开关，趋势徽章带
`data-trend` 属性（测试据此断言），序列点带 `data-baseline-point` 与
`data-current`。

### 4.4 变异验证

| 变异 | 实测 |
|---|---|
| 改成“与首个基线比”而非连续相邻 | ✓ 2 红（含尖峰用例） |
| `insufficient` 改 `stable` | ✓ 3 红 |

### 4.5 真实数据实跑

`xs2-novel-flywheel-build`（本机最富的工作流，12 个 run）：取最近 6 个点，
5 次可比差，trend `stable`——真实数据 1.0/1.0/1.0/0.0/0.2/0.0 有涨有跌，判定正确。
端点用 TestClient + 真实数据验过：`baseline` 与 `comparison` 相互独立、
`baseline_limit=0` 不返回该块。

## 5. 循环轮次与重试语义区分（R50-4）

### 5.1 问题原样

R41 §7 的观察项：`run-99b3bd1b` 里 `agent_deep` 的第 2、3 次尝试，
`attempt_history.trigger` 都是 `initial`、`automatic_retry_count=0`。原因在
`execution_loop._reset_node_for_loop_iteration`：循环体每轮把
`next_attempt_trigger` 重置成 `initial`。于是“循环第 2 轮”与“第 2 次执行”在
history 里长得一样，前端只能如实显示“首次执行”。

### 5.2 修法：轮次单独记，不动 trigger 语义

- `NodeExecutionState.loop_iteration`（0 = 非循环节点），循环重置时写 `iteration`；
- `record_attempt` 把它带进 `attempt_history`；
- `run_profile._node_profile` 暴露到 `attempts_detail`（旧记录缺键回落 0，
  不伪造轮次）；
- 前端尝试明细在轮次 > 0 时加“循环第 N 轮”徽章（`data-loop-iteration`）。

**刻意没做的事**：没有新增 trigger 值（如 `loop_iteration`）。`trigger` 表达的是
“这次尝试为什么开始”，重试语义必须保持单一来源；循环轮次是另一个维度，混进去
会让所有消费 `trigger` 的地方都要重新判断。

### 5.3 变异验证

| 变异 | 实测 |
|---|---|
| 循环重置不写 `loop_iteration` | ✓ 1 红（补了走真实 `_reset_node_for_loop_iteration` 的测试后） |
| 前端不渲染轮次徽章 | ✓ 1 红 |

第一个变异**初次没有咬合**——原有 loop 测试只调 `_reset_rejection_state_for_iteration`，
没走 `_reset_node_for_loop_iteration`。补了
`test_loop_reset_stamps_the_iteration_for_attempt_history` 之后才咬合。这条值得记：
“有一个 loop 测试”不等于“loop 重置路径被测到”。

## 6. 本机实跑（全部实际执行）

```
$ python scripts/e2e_workflow_stub.py
[e2e] PASS happy_path: 4 次模型请求，3 节点 completed，上游产出已传下游
[e2e] PASS failure_propagates: 任务 failed，broken=failed
[e2e] PASS turn_terminates: 任务 completed，2 次模型请求
[e2e] PASS transient_error_is_retried: 任务 completed，3 次请求（含 1 次注入 503），重试救回
[e2e] PASS permanent_error_is_not_retried: 任务 failed，1 次请求（401 未重试）
[e2e] PASS stream_stall_fails_fast: 任务 failed，1 次请求（部分流后未重试）
[e2e] 6/6 场景通过                                                    → exit 0

$ python scripts/check_live_snapshot_gate.py --check-coverage
[live-gate] 快照覆盖完整：真实数据 9 个工作流全部在快照内（快照含 9 个）  → exit 0

$ python scripts/check_live_snapshot_gate.py --check-stale
[live-gate] 快照尚新：… 滞后 -0.5 天 ≤ 容忍 7.0 天                     → exit 0

$ python scripts/provider_failure_profile.py --fail-if-above 5 --summary
[gate] 总失败率 2.88% 未超出阈值 5.0%（243 次尝试）                     → exit 0
TOTAL: runs=23 attempts=243 failed=7 failure_rate=2.9%
```

故障注入的 HTTP 层也单独验过（真起端口）：

```
[stub:5xx]   HTTP 503  error.code=service_unavailable
[stub:429]   HTTP 429  error.code=rate_limit_exceeded
[stub:401]   HTTP 401  error.code=invalid_api_key
fail_once: first=503 second=200 (second has DONE=True)
```

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_ci_e2e_stub.py` | **20 passed**（12 → 20） |
| 定向：`test_run_profile.py` | **39 passed**（31 → 39） |
| 定向：`test_workflow_failure_policy.py` | **29 passed**（27 → 29） |
| 定向：`test_workflow_loop_rejections.py` | **6 passed**（5 → 6） |
| 定向：`test_desktop_packaging.py` | **36 passed / 1 skipped**（35 → 36） |
| 收齐后 `--collect-only` | **2041 tests collected** |
| Low-IL 全量 | **1945 passed / 96 skipped / 0 failed**（117.88s） |
| High-IL 全量（权威） | **2030 passed / 11 skipped / 0 failed**（134.21s） |
| 前端 `npm test` | **475 passed / 0 fail**（471 + 4） |
| 前端 `tsc --noEmit` | 通过 |
| GHA `CI` run 40723820649 backend 第 9 步 | **success**（3/3 场景） |
| GHA `Desktop macOS` run 40723984654 full candidate | **success**（4 步 smoke 全绿） |

**对账**：

- Low-IL：R49 1925 **+20** = **1945** ✓
- High-IL：R49 2010 **+20** = **2030** ✓
- 总用例 R49 口径 2021 → **2041**
- 新增 20 条构成：`test_ci_e2e_stub.py` 8 + `test_run_profile.py` 8 +
  `test_workflow_failure_policy.py` 2 + `test_workflow_loop_rejections.py` 1 +
  `test_desktop_packaging.py` 1。零删除。

**变异共 8 个，6 个咬合、2 个不咬合（均已查明原因并记录）**：

| 变异 | 结果 |
|---|---|
| `is_permanent_provider_error` 恒 False | ✓ 咬合 |
| 停摆不发 chunk | ✓ 咬合 |
| 关掉 Core `max_retries` | ✗ 不咬合 → **发现 SDK 自带重试**，已写入文档 |
| 401 错误码伪装成 5xx 类 | ✗ 不咬合 → 分类以状态码为准，该变异无效 |
| 基线改成“与首个基线比” | ✓ 咬合（2 红） |
| `insufficient` → `stable` | ✓ 咬合（3 红） |
| 循环重置不写 `loop_iteration` | ✓ 咬合（补测试后） |
| 前端不渲染轮次徽章 | ✓ 咬合 |

## 8. 本轮改动一览（9 改 2 增，含 1 文档）

| 文件 | 变更 |
|---|---|
| `scripts/stub_llm_provider.py` | +~110 行：`ERROR_MARKERS`、`injection()`、`_completion_decision()`、`_error()`、`_stall()`、`claim()`/`reset_claims()`、`error_requests()` |
| `scripts/e2e_workflow_stub.py` | +~170 行：三个故障场景、`max_retries=2` 与 `delays=[0,0]`、`LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=2` |
| `src/workflow/run_profile.py` | +~105 行：`pick_recent_runs`、`compare_run_baseline`、trend 常量；`_node_profile` 暴露 `loop_iteration` |
| `src/web/workflow_routes.py` | +~35 行：`baseline_limit` 参数、`baseline` 块、上限 20 |
| `src/workflow/runtime_models.py` | +~12 行：`loop_iteration` 字段（序列化/反序列化） |
| `src/workflow/failure_policy.py` | +3 行：`record_attempt` 写入 `loop_iteration` |
| `src/workflow/execution_loop.py` | +4 行：循环重置写轮次 |
| `tests/test_ci_e2e_stub.py` | +8 条 |
| `tests/test_run_profile.py` | +8 条 |
| `tests/test_workflow_failure_policy.py` | +2 条 |
| `tests/test_workflow_loop_rejections.py` | +1 条 |
| `tests/test_desktop_packaging.py` | +1 条（macOS `--port 0` 契约） |
| `web/src/types/index.ts` | +~40 行：`RunProfileBaseline*`、`RunProfileTrend`、`loop_iteration` |
| `web/src/lib/api.ts` | +4 行：`baselineLimit` 参数 |
| `web/src/components/workflow/RunProfilePanel.tsx` | +~90 行：`BaselineSummary`、趋势徽章、轮次徽章、开关 |
| `web/src/components/workflow/RunProfilePanel.test.ts` | +4 条 |
| `docs/PROJECT_INFO.md` | 三节更新（e2e 故障注入 / 多 run 基线 / 循环轮次）+ R50 双基线记录 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 9. 未做与未验证的事（如实记录）

1. **`desktop-macos.yml` 的 `core candidate` job 是 cancelled**（GHA 并发策略在
   full candidate 完成后取消同组排队任务）。full candidate 已 success 且跑同一份
   `smoke_backend.py`，`--port 0` 的结论不受影响，但 core flavor 这一条本轮没有
   success 记录。
2. **未重导快照**：覆盖完整（9/9）、滞后 -0.5 天，两条判据都绿，无需重导。
3. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。
4. **未重启 8021 服务**：改动面是脚本、只读端点新增参数、新增字段与前端，不涉及
   运行时装配（`loop_iteration` 只是多记一个字段）。画像端点的真实数据验证用
   TestClient + 真实 `data/workflows` 完成，不依赖 8021 进程的代码版本。
5. **`stream_stall` 场景把超时压到 2s**：这测的是“停摆会被判失败”与“部分流后不
   重试”，**不**测真实 120s 停摆的时长行为。后者属于压测画像（真实快照）的地盘。
6. **`[stub:429]` 的标记已实现但暂无场景使用**：它走的是与 5xx 完全相同的
   “瞬时错误”分类路径，再加一个场景只是重复断言。保留标记是因为人工排查时有用
   （`--only` 配合手写场景），且单测覆盖了它的 HTTP 形状。
7. **`baseline_limit` 上限 20 是经验值**：一次请求扫遍上百条记录没必要，但“多少
   才够看趋势”没有理论解。若将来出现需要更长窗口的分析，应做成独立导出而不是
   调高这个上限。
8. **多 run 基线只判失败率趋势，不判耗时趋势**。耗时序列已在 `points` 里（含
   `wall_seconds`），但趋势判定刻意只做失败率——两个指标混在一个 `trend` 字段里
   会让“退步”的语义变糊。

## 10. 下一轮候选

1. **画像趋势接入前端更多视图**：目前 baseline 只在抽屉里。若要在任务列表上直接
   标“连续退步”的 workflow，需要后端提供批量接口（当前是逐任务查询）。
2. **`--check-coverage` 补“样本量是否足够”判据**：R49 §7-6 明确说过当前只判集合差。
   判“够不够”需要统计判据，与失败率闸门有重叠，需先想清楚边界。
3. **快照闸门的 CI 接线**（R46 §未做）：真实数据的失败率判定要进 CI，需要 run
   记录进 artifact 聚合或入库数据面。这条从 R46 挂到现在。
4. **桩的 `[stub:429]` / 长尾错误形态**：若将来要验退避策略（`delays` 非零），
   需要能断言“两次请求之间确实等了 T 秒”。当前 `delays=[0,0]` 是刻意绕开这一点。
5. **macOS `core candidate` 核对**：下次触发时一并看两个 job，本轮 core flavor 被并发策略 cancelled。

其余：POSIX 真跑已由 CI 覆盖（R43 结论）；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍天数 7 天维持（R49 确认）。

## 11. 本轮未实际运行

- **未跑 `docker build`**（本机无 docker）。
- **未重导快照**（两条判据都绿）。
- **未重启 8021 服务**（改动不涉运行时装配）。
- **未拿到 macOS `core candidate` 的 success 记录**（被并发策略 cancelled；full 已 success）。
- **未在推送后核对本轮改动的 CI 结果**：本轮改动提交推送后需看 backend job 的
  e2e step（现在是 6 个场景）与 frontend job（新增 4 条前端测试）。
