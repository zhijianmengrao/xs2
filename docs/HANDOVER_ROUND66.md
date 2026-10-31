# DeterminFlow (xs2) 交接报告 — Round 66（executor pool 的 `node_control_conflict`：闸门在「终态落盘」与「收尾」之间误报）

> 本轮定位：R65 §9-6 的第二族 flake（`test_real_pool_routes_retry_and_skip_to_original_executor`
> 偶发 `node_control_conflict`）。基线 `9c895ad`（R65 收尾：Low 2156/113/0、
> High 2241/28/0（权威）、总用例 2269、前端 490/0）。
> 落地形态由用户拍定四项：**主线 = executor pool 竞态根治**；**范围 = 主线 + 同源排查**；
> **收尾 = 照常推送 + 五 job 逐字核对**；**修法 = 生产端根治 + 钉窗口用例**。

## 1. 一句话结论

`_running_tasks` 里的运行标记原本要等 `_release_terminal_task_sessions()` 这个 **await**
结束才摘除，而终态 `failed` 在这之前就已经落盘。节点控制闸门（`retry_node` / `skip_node`）
先验的正是磁盘终态，于是它在这段 await 里读到的组合是「磁盘说 failed、运行标记说还在跑」，
返回一句自相矛盾的 `node_control_conflict`（「任务正在执行，不能同时修改节点状态」）。
修法只有一件事：**摘标记与终态落盘放进同一个同步段**，中间不许有 await。

## 2. 根因：窗口的精确形状

`src/workflow/manager.py::_persist_execution_result`（R66 前）：

```python
self._save_task(task)                                # ① 终态落盘（failed）
self._push_task_update(workflow_id, task)            # ② 同步推送
await self._release_terminal_task_sessions(task)     # ③ ← 唯一的 await
# 返回后，调用方 _run_task_coroutine 的 finally 才执行：
#     self._running_tasks.pop(task_id, None)         # ④ 运行标记在这里才摘
```

③ 的实现在 `src/agent/session_lifecycle.py::release_workflow_task_sessions`：逐个
`await session.cancel_active_invocation(timeout=5.0)` → `await session.stop_consumer()`
→ `await session.async_save(force=True, strict=True)`。这是一段**有真实等待**的收尾，
CI 上足以覆盖控制请求的往返时间。

闸门 `src/workflow/task_recovery.py::_validate_node_control` 的顺序是：

```python
if task.status not in _CONTROLLABLE_TASK_STATUSES:   # 240 行：只放行 failed / retry_waiting
    return node_control_conflict("任务状态为 X；仅 failed 或 retry_waiting ...")
...
running = self._running_tasks.get(task_id)            # 260 行
if running is not None and not running.done():
    return node_control_conflict("任务正在执行，不能同时修改节点状态")   # 264 行
```

**走到 260 行时，磁盘状态必然已经是 failed 或 retry_waiting**——否则 240 行就返回了。
所以 260 行那句「任务正在执行」在语义上只可能对应「执行已经结束、收尾还没做完」。
它不是防护，是一个只会误报的检查。

变异取证（把 helper 改成 `pass` 后跑新用例）：

```
AssertionError: assert <Task pending name='Task-3' coro=<WorkflowManager._run_task_coroutine()
running at .../src/workflow/manager.py:1022> wait_for=<Future pending ...>> is None
```

`manager.py:1022` 正是 ③ 那一行——运行标记活到了 Session 释放里面。

## 3. 修法：摘标记与终态落盘同处一个同步段

新增 helper（`manager.py:1028`）：

```python
def _drop_running_marker_before_cleanup(self, task: WorkflowTask) -> None:
    """终态落盘后立即摘除运行标记，再允许调用方 await 收尾。 ..."""
    self._running_tasks.pop(task.task_id, None)
```

在**全部 5 个终态路径**上调用，位置都在 `_save_task(...)` 之后、`await
_release_terminal_task_sessions(...)` **之前**（中间只有同步的 `_push_task_update`）：

| 位置 | 路径 | 终态 |
|---|---|---|
| `manager.py:1010` | `_run_task_coroutine` → `except CancelledError` | stopped |
| `manager.py:1019` | `_run_task_coroutine` → `except Exception` | failed |
| `manager.py:1075` | `_persist_execution_result`（正常执行返回） | completed / failed / retry_waiting |
| `manager.py:1349` | `_run_task_with_session` → `except CancelledError` | stopped |
| `manager.py:1356` | `_run_task_with_session` → `except Exception` | failed |

`finally` 里原来的 `pop` 保留（幂等，`pop(..., None)`），这样异常退出路径仍然有兜底。

### 3.1 为什么不怕与「新一轮」并发

摘标记之后，控制动作可能立刻启动新一轮，而旧 runner 还在做 Session 释放。这不会把旧收尾
误伤到新一轮，理由是**候选集在第一个 await 之前就同步快照好了**：

`release_workflow_task_sessions` 的第一件事是列表推导
`candidates = [ ... for session_id, session in list(self.sessions.items()) ... ]`，
`await` 只出现在其后的 for 循环里。而 `_drop_running_marker_before_cleanup` → `await
_release_terminal_task_sessions(...)` 之间没有任何挂起点，所以候选集是在「新一轮还没来得及
注册任何 Session」的时刻定格的。旧收尾只会释放旧 Session，不会碰新一轮的 Session。

`_prune_terminal_workflow_history()` 同样安全：它把 `self.sessions`（在册 Session）作为
`protected_session_ids` 传下去，新一轮刚注册的 Session 在册。

旧 runner 在终态落盘之后也不再写 task/node 状态（`_release_terminal_task_sessions` 只碰
Session），所以「控制动作改节点状态」与「旧 runner」不存在写冲突。

### 3.2 没选的三个方案

| 方案 | 为什么不选 |
|---|---|
| 只改测试等待条件（等到 `running.done()`） | 生产上用户点「重试节点」仍会撞到同一句误导性提示；flake 只是从 CI 消失，缺陷留在产品里 |
| 闸门里对有界等待（`asyncio.wait_for(shield(running), timeout)`） | 能消红，但把「一次误报」换成「每个正常控制请求可能多等 N 秒」；真正的根因（发布与释放的次序）没动 |
| 把 Session 释放挪到终态落盘**之前** | 窗口确实会消失（落盘后无 await），但终态会推迟到释放结束才可见——单 Session 最长 5s，卡住时 UI 会长时间停留在 running，代价比现在的取舍大 |

## 4. 同源排查：controller 里「发布 vs 释放」门清单

标准：**某个同步可查的标记被另一个代码路径当作闸门，而它的释放晚于一次 await**。

| # | 门 | 谁检查 | 谁释放 | 定性 |
|---|---|---|---|---|
| 1 | `_running_tasks` | `task_recovery.py:260`（控制闸门）、`manager.py:713/1304`（重复启动）、`executor_observability.count_active_tasks` | 本轮修复前：`finally`（在 release 之后）；修复后：终态落盘同一同步段 | **本轮的缺陷，已修** |
| 2 | `_task_control_locks` | `retry_node` / `skip_node` / `_activate_due_retries` / `_recover_task` | `async with` 退出 | 安全：锁本来就是为跨 await 持有而设计的，释放晚于 await 是它的语义 |
| 3 | `_retry_timers` + `_retry_timer_generations` | `_activate_due_retries:181`（代次比对） | `_cancel_retry_timer`（**纯同步**）；worker 的 `finally` 也在无 await 段 | 安全：无 await 介入 |
| 4 | `_active_task_index` | `_reassign_executor_tasks` / `reconcile_executor_pool` | `_save_task` 内 `track_after_save`（**同步**，紧跟 `write_task_state_file`） | 安全：无 await 介入 |
| 5 | `manager.py:713 / 1304` 的「任务已在运行中」 | `run_task` / `_start_pre_running_task` | `_running_tasks[task_id] = coro`，在 `_save_task("running")` → `create_task` → 赋值之间**没有 await** | 安全：磁盘 running 与标记赋值是同一步 |
| 6 | `_activate_due_retries:190` 的 `_running_tasks` 检查 | 自动重试激活 | 同 #1 | 安全：该分支要求状态是 `retry_waiting`（195 行），而 `_release_terminal_task_sessions` 对 `retry_waiting` 直接 return（`manager.py:1079` 状态集合不含它）→ 不存在「收尾尾巴」 |
| 7 | Executor 身份/世代（`executor_id` + `executor_epoch`） | `_delegate_identity_error` | `reassign_*` / `reconcile_executor_pool`（各自同步落盘） | 另一套机制：产出的是明确的 `executor_epoch_stale` 交接语义，不是「同一状态两种说法」，本轮不改 |

**顺带的用户可见行为变化**（如实记录，未写测试钉住）：任务已 failed 且正处在收尾尾巴时，
`stop_task` 以前会走进「取消 coro → 任务已停止」，现在走「任务未在运行」——因为标记已经摘了。
对一个已经失败的任务，后者更准确。

## 5. 钉窗口用例（确定性构造，不靠 sleep）

`tests/test_workflow_task_recovery.py::test_terminal_status_is_controllable_while_session_release_is_pending`

- `_GatedReleaseSessionManager`：把**第一次** `release_workflow_task_sessions` 卡在
  `asyncio.Event` 上——这就把真实世界里那段 5s 级 await 变成一个可控的停顿点；
- 失败的探针节点让任务走到 `failed`；
- 用例在「release 已进入、gate 未放行」的精确时刻做两条断言：
  1. 磁盘状态是 `failed`（收尾之前就已落盘）；
  2. `manager._running_tasks.get(task_id) is None`（标记必须先摘）；
- 然后**在这同一个窗口里**调 `retry_node`，断言 `success is True` 且 `error is None`。

没有 `sleep`、没有轮询重试：窗口是由 Event 精确保持的，每次执行都会命中。

## 6. 变异验证（`cp` 备份还原，不用 `git checkout --`）

| 变异 | 期望 | 实测 |
|---|---|---|
| helper 体改成 `pass  # R66 mutation`（等价于修复前） | 新用例必须掉 | **1 failed**，报错点正是 `manager.py:1022` 的 `await _release_terminal_task_sessions` |
| 还原后 | 全绿 | 文件级 **23 passed**；md5 与备份逐字节相同（`68f8a3b8…`） |

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2157 passed / 113 skipped / 0 failed**（128.58s） |
| High-IL 全量（权威） | **2242 passed / 28 skipped / 0 failed**（145.65s） |
| 定向：task_recovery | **23 passed** |
| 定向：control / residency / protocol / recovery_regressions | **70 passed**（19.73s） |
| executor pool 场景文件 ×5 | **4 passed ×5**（20.80–22.02s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |

**对账**：总用例 **2269 → 2270**（+1，新增钉窗口用例）。四面一致：
Low `2157+113` = 2270、High `2242+28` = 2270。

## 8. 未做与未验证的事（如实记录）

1. **没有在 CI 上再观测到那次 flake**：它是偶发的（CI 一次红、本机 12 次执行未见）。
   本轮能做的是把窗口**确定性地钉住**（§5）并重复跑场景文件 5 轮，而不是等它再红一次。
   「修好了」的证据是结构性的（窗口不存在了），不是统计性的。
2. **收尾尾巴不再被 `shutdown_running_tasks` 跟踪**：摘标记之后，若进程恰在 Session 释放
   期间关闭，这段收尾不会被 `shutdown_running_tasks` cancel。它本身有界（每 Session 5s 超时、
   失败只 log 并保留驻留 Session），且 `extension_manager.stop()` 之后还会收口 Session，
   但这确实是本修法换来的取舍。
3. **R60~R63 的重导仍被数据卡住**：`data/workflows/**/runs/run-*.json` 仍是 **40 个**，
   最新 `run-dfe789fd.json` 仍是 `2026-10-28 08:34`（本轮复查：比它新的 **0 个**）。
4. **`p=1.0` 真实数据验证**未做（需要真实全失败快照）。
5. **R62 提前量命令化**未做。
6. **未跑 `docker build`**：本机仍无 docker/wsl；`container-build` 在 GHA 真构建。
7. **未跑 `npm run build` / `npm test`**：零前端改动。
8. **未重启 8021 服务**：改动是后端执行收尾的次序，但本轮没有需要活体验证的新端点行为。
9. **Desktop Windows 本轮会触发**：`desktop-windows.yml` 的 paths 过滤**包含 `src/**`**
   （`src-tauri/` 不在列表里，但 `src/**` 在），本轮改了 `src/workflow/manager.py`，
   所以推送后除 `CI` 之外还会起一次 NSIS 构建（90min 超时）。结果按 §11 一并记录。

## 9. 下一轮候选

1. **有新 run 后再重导一次**（R60 §7-1 起的直接后续）：仍被数据卡住，本机已 4 天没有新 run。
2. **`p=1.0` 的真实数据验证**（R53 §11-4）。
3. **R62 提前量固化成可复核命令**（R62 §10-6）。
4. **形状场景失败时重跑一次**（R65 §8-9）：仍未做，需要先定义「两次里几次算通过」。
5. **判据全景登记的迁移验证**（R65 §9-5）。
6. **收尾尾巴的可观测性**（本轮 §8-2 的直接后续）：给「终态已落盘、Session 收尾未结束」
   一个可读的观测口径（日志/状态字段），并决定 `shutdown_running_tasks` 是否要显式等它。

## 10. 供应商失败率时间序列（R41 起的固定动作）

`python scripts/provider_failure_profile.py --summary`（严格只读）本轮输出，与 R43–R65 逐行一致
（无新 run，故无新数据点）：

| workflow | runs | attempts | failed | failure_rate | failing_stages | error_classes |
|---|---|---|---|---|---|---|
| xs2-novel-flywheel-build | 3 | 27 | 1 | 3.7% | agent_corelaws | http_5xx ×1 |
| xs2-novel-flywheel-character | 3 | 75 | 1 | 1.3% | agent_deep | stream_stall ×1 |
| xs2-novel-flywheel-export | 3 | 3 | 0 | 0.0% | - | {} |
| xs2-novel-flywheel-mvp | 2 | 56 | 4 | 7.1% | script_check_originality, script_smart_context | other ×4 |
| xs2-novel-flywheel-outline | 2 | 16 | 0 | 0.0% | - | {} |
| xs2-novel-flywheel-polish | 2 | 14 | 0 | 0.0% | - | {} |
| xs2-novel-flywheel-post-hoc | 3 | 24 | 1 | 4.2% | script_confirm_archive | other ×1 |
| xs2-novel-flywheel-reader-sim | 3 | 12 | 0 | 0.0% | - | {} |
| xs2-novel-flywheel-story-plan | 2 | 16 | 0 | 0.0% | - | {} |
| **TOTAL** | **23** | **243** | **7** | **2.9%** | | |

## 11. 推送与 CI 核对

推送 `ca52111`（`2e50759` 修复+用例、`ca52111` 交接文档+PROJECT_INFO 两个提交为**一次**
`git push`，`head_sha` 只产生一个 run）。

| run | workflow | 触发 commit | 结果 |
|---|---|---|---|
| **41158950366** | `CI` | `ca52111` | 五 job 全部 `success`，**一次通过、无重跑** |
| **41158950390** | `Desktop Windows` | `ca52111` | **success**（该 workflow 的 paths 含 `src/**`，本轮改了 `manager.py` 所以真触发；NSIS 构建通过） |

| 项 | 实证（下载日志解码后逐字比对，不是推断） |
|---|---|
| 五个 job | backend / windows-backend / frontend / container-config / container-build 全部 `conclusion=success` |
| 用例数（ubuntu） | `2206 passed, 64 skipped, 1 warning in 74.24s` = **2270** |
| 用例数（windows） | `2241 passed, 29 skipped, 1 warning in 222.83s` = **2270** |
| 四面一致 | 本机 Low `2157+113` = 2270、本机 High `2242+28` = 2270、ubuntu `2206+64` = 2270、windows `2241+29` = 2270 |
| **被修的 flake 在 CI 上真跑了** | 两个 runner 都跑全量套件，`tests/test_workflow_executor_pool_scenarios.py` 在内且全部通过（ubuntu 74.24s、windows 222.83s 全绿） |
| e2e（只 ubuntu 有） | `[e2e] 10/10 场景通过`；形状判据逐字：两段实测 `[0.404, 0.805]` 最大超睡 **0.005s**（余量 60.0 倍）、三段 `[0.403, 0.803, 1.605]` **0.005s**（60.0 倍）、四段 `[0.404, 0.804, 1.604, 3.206]` **0.006s**（50.0 倍），诊断行 `参考：相邻比值 [...]（诊断用，不参与判定）` 照旧 |
| 失败率闸门 | 两 runner 都打印 `快照样本量足够支撑失败率判定：失败率 3.92% 的 95% 半宽 2.64 个百分点≤ 余量 10.0（n=255, 失败 10）`；逐 workflow 回归 `9 个 workflow 里 2 个可判（0 个判回归 / 2 个没有回归 / 0 个区间横跨阈值），7 个基线太薄判不了`——与 R65 判决逐字相同 |
| windows 的边界 | 日志里 `e2e_workflow_stub` 出现 **0** 次——**没有** e2e 步骤，不写成「两 runner 都验证了 e2e」 |
| 前端 | 日志里 8 个 `# pass` 块合计 **490**（8 个 `# fail` 块合计 **0**） |
| 容器 | `container-config`：`docker compose config -q` 通过；`container-build`：`docker buildx build` 真构建后 `smoke_container.py --image determinflow-core:ci --skip-build` 逐行输出 `status 契约成立: mode=process ready=4/4 degraded=False` / `内置前端产物可用: /assets/index-DJbfnKbu.js` / `镜像 HEALTHCHECK=healthy` / `entrypoint 先裁剪再 exec 已验证` / `镜像布局契约成立（不含 tests 与预先烘焙的凭据）` / `容器镜像冒烟全部通过` |

**取证方法的一个坑（本轮实测）**：`actions/jobs/<id>/logs` 会 302 到
`productionresultssa*.blob.core.windows.net`，该 blob 主机在本机**直连约 100KB/s 且整段 GET
会在 120s 超时**（Range 请求正常）。最终用「先 `-r 0-0` 读 `Content-Range` 得总长，再按 48KB
分块 Range 下载并拼接」的方式取全 5 份日志。过程中还观察到一次 **Content-Range 报的总长与
实到字节不符**（container-build 报 87240、实收 174480，整份日志被写成两份），已按「第二份
与第一份逐行相同」判定为重复并截掉。**下载日志不能只看 curl 是否 exit 0**。
