# DeterminFlow (xs2) 交接报告 — Round 51（样本量闸门进 CI + 退避可观察 + 趋势接入列表）

> 本轮定位：R50 §10 五个候选**全部**由用户拍定执行（"1. 2. 3. 4." + §10-5 macOS 核对），
> 收官走「双基线 + 推送 + CI 核对」。
> 基线：`b8bab16`（R50 收尾，Low 1945/96/0、High 2030/11/0、前端 475/0）。

## 1. 四项主线的共同线索：判「有没有」与判「够不够」

§10 的四条候选看起来互不相干，实际都在补同一类空缺——**已有的判据只回答了
「有没有」，没回答「够不够 / 准不准」**：

| 候选 | 已有判据回答的 | 缺的那一半 |
|---|---|---|
| §10-2 覆盖度样本量 | 「哪些 workflow 进了快照」 | 「进来的样本薄到看不出失败率」 |
| §10-4 退避验证 | 「重试把错误救回来了」 | 「退避时长真的是配置那个值」 |
| §10-1 趋势更多视图 | 「抽屉里能看到趋势」 | 「列表上能否一眼看到哪个在退步」 |
| §10-3 闸门 CI 接线 | 「CI 判失败率」 | 「哪条判据能在 CI 里真判」 |

四条里唯一需要外部环境才能定论的是 §10-3（CI 里有什么数据面），其余本机可验。

## 2. 样本量判据（R51-2）

### 2.1 为什么不能用「attempts ≥ 某个数」

写死「至少 100 次尝试」有两个毛病：数字没有依据（为什么不是 80 或 150），
以及它答错了问题——闸门拿快照的失败率当**基线**，真正该问的是「这个估计量的
精度够不够支撑那个用途」，与条数只是相关而非等同。

所以判据按估计量的形状分两支：

| 情形 | 判据 | 理由 |
|---|---|---|
| 有失败 | 正态近似 95% 半宽 `1.96·√(p(1-p)/n)` ≤ `--margin` | 取样误差不该把 margin 吃干净 |
| 零失败 | Clopper-Pearson 单侧 95% 上界 `1-0.05^(1/n)` ≤ `--margin` | 见下 |

**零失败分支是这一条最容易被写坏的地方**：`p=0` 时正态半宽恒为 0，任何 margin
都判合格。2 次尝试 0 失败也会通过，而它真实的单侧上界是 **77.6%**。这正是
R45/R46/R47 反复批评的「永远绿的防护」的又一个具体形状，所以单独用精确区间。

阈值完全由快照自身的 `attempts/failed` 与 margin 推导，重导后自动跟着变。

### 2.2 实测

```
$ python scripts/check_live_snapshot_gate.py --check-sample-size
[live-gate] 快照样本量足够支撑失败率判定：失败率 3.74% 的 95% 半宽 2.72 个百分点
            ≤ 余量 10.0（n=187, 失败 7）                                    → exit 0

$ python scripts/check_live_snapshot_gate.py --check-sample-size --margin 2
[live-gate] 快照样本太薄：失败率 3.74% 的 95% 半宽 2.72 个百分点 > 余量 2.0 …   → exit 7
```

分情形实测（临时目录造数据）：

| n | 失败 | margin | 结论 | 依据 |
|---|---|---|---|---|
| 2 | 0 | 10 | **7 太薄** | 上界 77.64% |
| 60 | 0 | 10 | 0 通过 | 上界 4.87% |
| 10 | 1 | 10 | **7 太薄** | 半宽 18.59% |
| 1000 | 1 | 10 | 0 通过 | 半宽 0.20% |
| 187 | 7 | 10 | 0 通过 | 半宽 2.72% |

## 3. 闸门进 CI（R51-3）

### 3.1 为什么只有这一条能进

`--check-stale` 与 `--check-coverage` 都要跟真实 `data/workflows` 比，而 CI 检出
里没有那个目录（gitignore）——接进去只会永远「无法判定」，是恒绿防护。R47 §2.3
与 R48/R49 都把这条写成了明确的「不进 CI」纪律，并有反向测试钉死。

`--check-sample-size` 只读快照自身，**这条限制对它不成立**。它不是对既有纪律的
例外，而是纪律指向的那个问题的另一面：纪律说的是「别接永远判不到的判据」，
这一条恰好判得到。

### 3.2 step 的双向验证

只跑「当前快照该通过」会得到一个恒绿步骤。所以 CI 里跑两次：

```yaml
- name: Snapshot sample-size gate
  run: |
    snapshot=tests/fixtures/live_snapshot
    # ① 默认余量必须通过
    python scripts/check_live_snapshot_gate.py --check-sample-size --data-dir "$snapshot"
    # ② 收紧到 2 个百分点必须触发退出码 7——只跑 ① 等于恒绿
    python ... --margin 2 ; 期望 exit 7，否则 ::error:: 判据失去判定力
```

本地等价实跑：`default exit=0` / `margin2 exit=7`。推送后 GHA 上同样两个分支都
成立，见 §11.1。

## 4. 退避策略验证（R51-4）— 本轮最有价值的发现

### 4.1 先量清楚 R50 §3.4 那个死结

R50 记录「关掉 Core `retry.max_retries` 后 transient 场景仍绿，因为 ChatOpenAI
自带 `max_retries=2`」。本轮先用桩直接量了四种组合的请求间隔：

| SDK `max_retries` | Core `delays` | 请求数 | 实测间隔 | 成功 |
|---|---|---|---|---|
| 2 | [3.0] | 2 | **0.48s** | ✓ |
| 0 | [3.0] | 2 | **3.01s** | ✓ |
| 2 | [0.0] | 2 | 0.41s | ✓ |
| 0 | [0.0] | 2 | 0.00s | ✓ |

**结论**：SDK 层开着时，Core 配的 3 秒退避一次都没被等到——SDK 用自身的指数
退避抢先救回了。所以当年那个「关掉 Core 重试仍绿」不仅是断言粒度问题，
更是**两层重试根本不可分**：只要 SDK 在，任何关于 Core 退避的断言都在量别人的数。

### 4.2 解法：把 SDK 层做成可单独关闭

`ModelManager.get_retry_config()` 新增 `sdk_max_retries`，`create_llm` 在它存在时
`kwargs.setdefault("max_retries", ...)`。

**一个关键取舍**：该项**默认不出现在返回值里**（不是 `None` 键）。因为
`build_effective_agent_definition` 把 `get_retry_config()` 的返回值纳入
`model_runtime_sha256`，而那是 **fail-closed 的运行身份守卫**——不匹配就拒绝
启动新 session。无条件多一个 `None` 键会让所有在途任务 resume 时被判「身份漂移」
而失败。有专门测试钉住「默认返回值与既往逐字段一致」。

### 4.3 e2e 场景：差分而不是绝对阈值

`retry_backoff_is_honoured` 同一场景跑两次（`delays=[0]` 与 `delays=[1.2]`），
比较桩记录的请求到达间隔。**差分法**绕开「固定开销有多少」这个不可知量：
绝对阈值只能取很松的数，于是「退避被删掉一半」也能绿；差分比的正是「多出来的
等待」。

实测输出：

```
[e2e] PASS retry_backoff_is_honoured: 退避生效：delays=0 → 0.01s，delays=1.2 → 1.21s（多 1.21s）
[e2e] 7/7 场景通过
```

桩新增 `received_at`（monotonic，收包时打）：在被测进程侧量到的是含调度抖动的
时间，服务端打点才是「请求真的到了」。

### 4.4 场景做了什么、没做什么

- **做了**：判「**Core 层**的 delays 被真的等过」。这是 `transient_error_is_retried`
  判不到的那一半（后者判「重试总效果」）。
- **没做**：不判真实 120s 级退避、不判指数退避的形状。`delays=[1.2]` 是
  单点验证。

## 5. 趋势接入任务列表（R51-1）

### 5.1 端点设计

```
GET /api/workflows/{wf}/tasks?with_trend=true&baseline_limit=N
GET /api/tasks?with_trend=true                          （全局）
```

附带的 `trend` 块**刻意比抽屉的 `baseline` 窄**：只给
`trend` / `run_id` / `consecutive_required` / `points_considered` /
`comparisons` / `delta_failure_rate`。一页 20 条各塞一份每阶段明细只是让响应膨胀。

**默认关**是刻意的：算趋势要扫 workflow 的 `runs/` 目录并解析 run JSON，是列表
端点里最重的一段 I/O；而列表的主要用途（找任务、点进去）不需要它。

### 5.2 效率：分组 + 缓存，不是逐任务

逐任务调 run-profile 等于把同一个目录读 N 次（N+1）。实现上：

1. 按 `workflow_id` 分组，每组的 `runs/` 只扫一次；
2. 画像按 `run_id` 缓存——多个任务常指向同一批 run。

有测试直接统计调用次数，实测 2 个任务 / 3 个 run：目录扫描 **1 次**、画像加载
**3 次**（每 run 一次，不重复）。

### 5.3 前端

任务历史加「标注连续退步」复选框。徽章只给 `regressing`（`data-trend` 属性供
测试断言）：`insufficient` 是「判不了」，挂徽章会把「没有足够历史」读成「有问题」。
趋势文案与配色从 `RunProfilePanel` 抽到 `runProfileView.ts` 共用，避免两处漂移。

## 6. macOS core candidate（R51-5）

R50 §9-1 挂账：`desktop-macos.yml` 的 `core candidate` job 被 GHA 并发策略
cancelled，只有 full candidate 有 success 记录。

本轮推送后手动触发 `desktop-macos.yml`（run **40796761709**，`workflow_dispatch`，
不打 tag、不产发布物）：**core candidate 与 full candidate 两个 job 都 success**，
run 级 `conclusion` 也是 success。挂账闭合，详见 §11.2。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_live_snapshot_gate.py` | **34 passed**（23 → 34） |
| 定向：`test_run_profile.py` | **45 passed**（39 → 45） |
| 定向：`test_llm_client_params.py` | **25 passed**（20 → 25） |
| 定向：`test_ci_e2e_stub.py` | **23 passed**（20 → 23） |
| 定向：`test_desktop_packaging.py` | 36 passed / 1 skipped（未变） |
| 收齐后 `--collect-only` | **2065 tests collected** |
| Low-IL 全量 | **1969 passed / 96 skipped / 0 failed**（119.81s） |
| High-IL 全量（权威） | **2054 passed / 11 skipped / 0 failed**（135.16s） |
| 前端 `npm test` | **478 passed / 0 fail**（475 + 3） |
| 前端 `npm run build` | **通过**（6.08s） |
| 本机 e2e | **7/7 场景通过** |

**对账**：

- Low-IL：R50 1945 **+24** = **1969** ✓
- High-IL：R50 2030 **+24** = **2054** ✓
- 总用例 R50 口径 2041 → **2065**
- 新增 24 条构成：`test_live_snapshot_gate.py` 11 + `test_run_profile.py` 6 +
  `test_llm_client_params.py` 5 + `test_ci_e2e_stub.py` 2。零删除。

### 7.1 High-IL 的跑法（本轮踩了一次坑，值得记）

`C:\Windows\py.exe` + `PYTHONPATH` 指向 venv site-packages 是文档里的方法，但
**只挂 site-packages 根目录不够**：`pywin32.pth` 里的 `import pywin32_bootstrap`
与 `win32` 路径条目是 `.pth` 机制，`PYTHONPATH` 不执行 `.pth`，于是四个模块
collection 直接 `ModuleNotFoundError: pywintypes`。正确命令需把 win32 子目录显式挂上：

```bash
SP=".venv/Lib/site-packages"
PYTHONPATH="$SP;$SP\win32;$SP\win32\lib;$SP\pythonwin" \
  "C:/Windows/py.exe" -3.14 -m pytest -q
```

顺带修正一处此前的误判：我先用 PowerShell `Start-Process` 起 `py.exe` 跑，
得到 1969/96 与 Low-IL 完全一样，疑心「IL 没提升」；实测根因是**父 PowerShell 的
IL 与 Python 子进程无关**——`Start-Process` 派生的是同一 token。真正决定的是
`py.exe` 这个 launcher 走的解释器，而不是从哪个 shell 起。

## 8. 变异验证（8 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| 零失败时上界恒 0（`upper = 0.0`） | 红 | ✓ 1 红（n=2 判合格） |
| 有失败时 margin 判据恒 True | 红 | ✓ 1 红（n=10/1 判合格） |
| `sdk_max_retries` 配置被忽略 | 红 | ✓ 1 红（`max_retries` 仍 None） |
| `ainvoke` 不退避（sleep 删掉） | 红 | ✓ 1 红（`slept == []`） |
| 取消画像缓存（每 run 重载） | 红 | ✓ 1 红（5 次加载 > 3） |
| 每任务多扫一次 `runs/` | 红 | ✓ 1 红（2 次扫描） |
| `insufficient` 也挂徽章 | 红 | ✓ 1 红（徽章数 2 ≠ 1） |
| 前端趋势开关默认开 | 红 | ✓ 3 红（opt-in 语义丢失） |

八个全部咬合——本轮没有出现「不咬合」的变异，与前几轮常见的 1–2 个不咬合不同。
值得记的一条：**变异只改一处、断言只钉一件事**。前几轮不咬合的变异多是
「变异本身无效」（如 R50 把 401 伪装成 5xx，分类以状态码为准，改了等于没改）。

## 9. 本轮改动一览（16 改 2 增，含文档）

| 文件 | 变更 |
|---|---|
| `scripts/check_live_snapshot_gate.py` | +~95 行：`EXIT_THIN_SAMPLE`、`_failure_rate_precision`、`check_sample_size`、三判据互斥 |
| `.github/workflows/ci.yml` | +30 行：`Snapshot sample-size gate`（双向验证） |
| `scripts/stub_llm_provider.py` | +2 行：`received_at` 时间戳 |
| `scripts/e2e_workflow_stub.py` | +~85 行：`_request_gaps`、`retry_backoff_is_honoured`、`sdk_max_retries` 参数 |
| `src/core/model_manager.py` | +12 行：`get_retry_config` 的 `sdk_max_retries`（默认不出现） |
| `src/core/llm_client.py` | +8 行：SDK 层单独关闭；`retry_config` 复用 |
| `src/web/workflow_routes.py` | +~95 行：`_collect_workflow_trends`、两个列表端点的 `with_trend` |
| `tests/test_live_snapshot_gate.py` | +11 条 |
| `tests/test_run_profile.py` | +6 条 |
| `tests/test_llm_client_params.py` | +5 条 |
| `tests/test_ci_e2e_stub.py` | +2 条（另调 1 条场景清单） |
| `web/src/types/index.ts` | +~15 行：`TaskTrendBlock`、`WorkflowTask.trend` |
| `web/src/lib/api.ts` | +6 行：两个列表函数的 `with_trend` |
| `web/src/components/workflow/runProfileView.ts` | +~25 行：趋势文案/配色/`shouldFlagTrend` |
| `web/src/components/workflow/RunProfilePanel.tsx` | −13 行（常量搬到共享模块） |
| `web/src/components/workflow/TaskHistoryPanel.tsx` | +~30 行：fetcher 注入、开关、徽章 |
| `web/src/components/workflow/TaskHistoryPanel.test.ts` | 新增 3 条 |
| `docs/PROJECT_INFO.md` | 四节更新（样本量判据 / 退避场景 / 列表趋势）+ R51 双基线 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 10. 未做与未验证的事（如实记录）

1. **`Snapshot sample-size gate` 的 GHA 实跑只覆盖了 Ubuntu runner**：CI 的
   `backend` job 在 ubuntu-24.04 上跑（Python 3.11.17），判据已验证跨版本一致；
   `windows-backend` job 没有这一步（它只跑 pytest 与存储名审计）。若要让 Windows
   runner 也判，需另行接线。
2. **未重导快照**：三条判据（失败率 / 样本量 / 覆盖度）与保鲜都绿，无需重导。
   快照仍停在 `exported_at 2026-10-28T12:30:35Z`，滞后约 0.5 天。
3. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。本轮改了
   `src/core/` 与 `src/web/`，`container-build` job 会真构建并跑容器冒烟。
4. **未重启 8021 服务**：改动是新增只读参数、新增配置项（默认不生效）与脚本，
   不涉运行时装配。列表趋势的真实数据验证用 TestClient + 临时目录完成。
5. **退避场景只验单点**：`delays=[1.2]` 判「配的延迟被等过」，不验指数退避的
   形状或多次退避的递减/递增。真实 120s 级退避属于压测画像地盘。
6. **`sdk_max_retries` 没有默认开启**：默认保留 SDK 自有策略。把它全局改成 0
   会让生产少一层重试（SDK 层用的是 openai 客户端的指数退避），这是行为变更，
   不该由一轮维护顺手做。它当前只服务于「让 Core 退避可观察」这一个用途。
7. **趋势块不含耗时趋势**：与 R50 §9-8 同一条理由——两个指标混进一个 `trend`
   字段会让「退步」语义变糊。
8. **`baseline_limit` 在列表端点默认 5**：与抽屉的「最近 5 次」一致，上限仍是
   20。没有理论最优值，属经验取值。

## 11. 推送与 CI 核对（本篇补记，2026-10-29）

推送 `bb0df1d` 后触发三个 workflow（本轮改了 `src/core/`、`src/web/`、`web/`，
`desktop-windows.yml` 的 paths 过滤这次**命中**，与 R50 只触发 CI 不同）。

### 11.1 CI run 40796688120 —— 五 job 全绿

| job | 结论 |
|---|---|
| `backend` | **success** |
| `windows-backend` | **success** |
| `frontend` | **success** |
| `container-build` | **success** |
| `container-config` | **success** |

**新增的第 9 步 `Snapshot sample-size gate` 在 GHA 上真跑并通过**，日志：

```
[live-gate] 快照样本量足够支撑失败率判定：失败率 3.74% 的 95% 半宽 2.72 个百分点
            ≤ 余量 10.0（n=187, 失败 7）
OK  样本量判据双向生效：默认余量通过，余量 2 触发 7
```

两点值得记：

1. **双向验证的第二半真的执行了**：如果只跑「默认该通过」，这行 `OK` 不会
   出现（那条路径需要 `--margin 2` 触发 7 才走到）。这是一条能红的步骤的证据。
2. **runner 是 Python **3.11.17**，不是本机的 3.14**。判据只用 `math` 与四则
   运算，跨版本结论一致——这本身也是对「判据没有隐含环境依赖」的一次检验。

**e2e 第 10 步在 GHA 上真跑了 7/7 场景**，含本轮新增的退避场景：

```
[e2e] PASS happy_path: 4 次模型请求，3 节点 completed，上游产出已传下游
[e2e] PASS failure_propagates: 任务 failed，broken=failed
[e2e] PASS turn_terminates: 任务 completed，2 次模型请求
[e2e] PASS transient_error_is_retried: 任务 completed，3 次请求（含 1 次注入 503），重试救回
[e2e] PASS permanent_error_is_not_retried: 任务 failed，1 次请求（401 未重试）
[e2e] PASS stream_stall_fails_fast: 任务 failed，1 次请求（部分流后未重试）
[e2e] PASS retry_backoff_is_honoured: 退避生效：delays=0 → 0.01s，delays=1.2 → 1.21s（多 1.20s）
[e2e] 7/7 场景通过
```

退避场景在 Linux runner 上量到 **1.20s**（本机 Windows 是 1.21s）——差分判据
（阈值 0.7s）跨平台成立，且这不是「恰好过」：配置值 1.2s 与两平台的实测差值
都在 0.01s 内吻合。

### 11.2 Desktop macOS run 40796761709 —— 两个 candidate 都 success

**R50 §9-1 的挂账在这里闭合**：R50 那次 `core candidate` 被 GHA 并发策略
cancelled，本轮**两个 job 都跑完并 success**：

| job | 结论 |
|---|---|
| `Build Apple Silicon core candidate` | **success** |
| `Build Apple Silicon full candidate` | **success** |

core candidate 的三步关键验证（第 10/12/13 步）都 success：
`Build and test frozen backend`（含 `smoke_backend.py` 的 `--port 0` 路径）、
`Verify app, DMG and bundled backend`、`Verify backend from installed DMG copy`。

R50 §9-1 记的那条「core flavor 没有 success 记录」**从此不再成立**。
run 级 `conclusion` 这次也是 **success**（不是 R50 那样的 failure+cancelled）。

（core candidate 第 8 步 `Verify latest official Plugin lock for Full candidate`
是 skipped——那是 Full 专属检查，在 core flavor 上跳过属预期。）

### 11.3 Desktop Windows run 40796688136 —— 双 NSIS success

| job | 结论 |
|---|---|
| `Build core NSIS installer` | **success** |
| `Build full NSIS installer` | **success** |
| `Publish GitHub Release` | skipped（不打 tag，预期） |

本轮改了 `src/core/`、`src/web/`、`web/`，所以 `desktop-windows.yml` 的 paths
过滤命中，NSIS 构建真实执行。这也顺带确认：改后端源码会触发桌面构建，
与 R50 的「只改 scripts/tests/docs 不触发」是同一套 paths 规则。

## 12. 下一轮候选

1. **趋势再往上一级**：当前是「每条任务」的趋势。若要在**工作流列表**上标
   「这个 workflow 在连续退步」，需要按 workflow 聚合（取最新 run 的 trend），
   语义与现状不同，是一次独立设计。
2. **`--check-sample-size` 加 per-workflow 判据**：当前只判全局样本厚度。
   单个 workflow 很薄而全局够厚时，全局判据看不出问题；需要新的退出码或
   `--strict` 形态，并想清楚「哪个 workflow 该有多少样本」的依据。
3. **退避策略的形状验证**：需要一个能断言「两次重试之间递增」的场景，
   这会引入真实等待（`delays=[0.4, 0.8]` 约 1.2s），仍在 CI 预算内。
4. **`sdk_max_retries` 的生产取值决策**：当前默认不改。若要统一关掉 SDK 层、
   让 Core 的 `delays` 成为唯一退避来源，需要单独一轮评估（涉及生产重试行为）。
5. **趋势徽章的运维视角**：现在只有「连续退步」一个信号。若要做「本 workflow
   最近 N 次全失败」这类更强信号，需要另立判据而不是塞进 trend。

其余：快照闸门的 CI 接线缺口已闭合（§3）；macOS `core candidate` 已闭合（§11.2）；
大陆下载加速维持现状（R44 结论）；快照保鲜容忍 7 天维持（R49 确认）。
