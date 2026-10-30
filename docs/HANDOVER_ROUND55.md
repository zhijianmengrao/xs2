# DeterminFlow (xs2) 交接报告 — Round 55（workflow 级趋势 + 样本量精确界 + 四段退避形状）

> 本轮定位：R54 §11-1「workflow 级趋势」作主线（与 R54 做完的 `health` 正好
> 配成一对：一个判方向、一个判状态），并清理三项挂账：样本量判据的**方向错误
> 台阶**、`FAILURE_STREAK_REQUIRED` 的**数据依据**、四段退避形状。
> 基线：`75c4815`（R54 收尾，Low 2044/96/0、High 2129/11/0、前端 484/0、9 场景 e2e）。

## 1. 本轮最重要的一件事：一条判据在说反话

样本量判据 `sample_size_margin_needed` 原本是三段拼起来的：两端用
Clopper-Pearson 闭式 `1 - 0.05**(1/n)`，中段用正态近似 `1.96*sqrt(p(1-p)/n)`。
三段各自看都对，拼起来在 `p` 从 0 跳到 `1/n` 的地方留了一个台阶——

| n | k=0（零失败） | k=1（一次失败） |
|---|---|---|
| 10 | 25.89 | **18.59** |
| 16 | 17.07 | **11.86** |
| 24 | 11.73 | **7.99** |

**多了一次失败，样本反而显得更可信。** 这不是保守与否的问题，是判据在说反话：
「刚出现失败」的样本比「零失败」的样本更容易过闸门，正好把最该被看见的那一刻
放过去。

修法是**全线用同一个精确界**，而不是给中段打补丁：Clopper-Pearson 的单侧界可以
写成二项分布的精确分位数求解，两端恰好有闭式解——那个 `0.05**(1/n)` 不是另一个
估计，就是这个精确界在 `k=0` / `k=n` 时的解析值。合并之后只有一个式子，台阶消失。

三处实测：

```
修复后 n=10：k=0 → 25.89，k=1 → 29.42，k=2 → 30.69   （单调上升，不再说反话）
n ∈ [5, 300] 全区间：一次失败恒比零失败要求更厚；高端镜像同样成立
入库快照全局 10/255：2.38 → 2.64 个百分点，仍远小于 margin=10（闸门不受影响）
```

**代价如实记录**：精确界比正态近似宽，所以 per-workflow 诊断里
`flywheel-build`（9.81→12.76）与 `flywheel-post-hoc`（7.99→14.12）从「达标」变
「不达标」。但那一块**恒退出 0**（R54 §1 定性的诊断信息，不是判据），变的只是
报告文字。同一原因让导出脚本的半宽余量从 0.38 升到 0.64，越过 0.5 的告警带，
于是 `test_thin_headroom_still_passes_but_warns` 的断言从「越线」改成「仍有判定力」
——这是实测数字变了导致的文案变化，不是判据退化（2.64 > 2.0 仍成立，反向验证
那一步照样以退出码 7 触发）。

**一处必须记住的残余**：`n ≤ 4` 时低端仍有轻微反转（n=2 时 77.6 → 47.5）。它无害，
因为那几个 n 的**每一个** k 都远超任何合理 margin（最小值也在 45 个百分点以上），
判决结果不可能因此不同。这一点写成了独立测试钉住豁免范围，防止有人把「n≤4 无害」
扩成「小样本可以不管」。

## 2. workflow 级趋势（R55-A 主线）

### 2.1 为什么不能由任务级合并出来

本轮开工前先核对了 run JSON 的实际字段：

```
keys: ['completed_at', 'node_executions', 'run_id', 'started_at', 'status', 'workflow_id']
task_id = None
```

**run 记录里没有 `task_id`。** 所以 workflow 级趋势无法从任务级的 `trend` 块
合并——只能直接沿 `runs/` 目录的时间序列判。这与 R54 §2.1 记的 health 盲区是
同一层：任务级只沿「这一条任务」的 run 序列看，同一个 workflow 里多个任务交替
跑时，任何单条任务都判不出「整个 workflow 在变坏」。

### 2.2 共用判据，不写第二份

新增 `workflow_trend(profiles, limit)`（`src/workflow/run_profile.py`）：
内部按 `_order_key` 排序 → 取最近 `limit` 条 → 调 `compare_run_baseline`。

- **排序不信调用方**：与 `workflow_health` 同一纪律（R54 §2.2）。文件名字典序把
  `run-10` 排在 `run-9` 前面，不排序就会把「最新的 run」认成错的那条，判的是
  另一端的方向。有专门测试（打乱输入，结论不变）。
- **判据复用 `compare_run_baseline`**：趋势的定义（相邻差值连续 N 次同向、
  `insufficient` 不冒充 `stable`）已经在那一处定型。理由与 R53 §2.3 抽
  `_rising_shape_violations`、R54 §2.2 复用 `failure_streak` 完全相同。
- **无 run 时 `insufficient` 而非 `stable`**：没有序列不等于没问题。

### 2.3 路由与成本

`GET /api/workflows` 加 `with_trend`（默认关）与 `trend_limit`（默认 5，上限 20）。

两个开关同时打开时**共用一遍目录扫描**（`_collect_workflow_diagnostics`）：各自
扫一遍会把同一个 `runs/` 读两次、把同样那些 run JSON 解析两次。health 只要
`status`（元数据里就有），只有 trend 需要额外解析画像。

`trend_limit` 默认 5 而 `health_limit` 默认 0（全部），是两个不同的问题：
趋势窗口裁短只是丢掉过老的对比；health 问「最近是不是一直在挂」，裁短会把
全失败序列的头部截掉反而更不安全。

### 2.4 真实数据实测

14 个工作流，两个块都返回，响应 92ms：

```
世界观构建管线     trend=stable       pts=5 cmp=4 | health runs=12 streak=0
角色创建管线       trend=stable       pts=4 cmp=3 | health runs=4  streak=0
导出成品           trend=stable       pts=5 cmp=4 | health runs=10 streak=0
章节生产管线       trend=insufficient pts=2 cmp=1 | health runs=2  streak=0
… （7 个 points_considered=0/2 的判 insufficient，不冒充 stable）
```

当前真实数据里**没有** regressing / all_failed 的 workflow，所以模板列表上不该
出现任何徽标——这与实测一致（第 3 节记了怎么验证徽标本身能渲染）。

## 3. 前端与浏览器走查（本轮补上 R54 §10-7）

`WorkflowPage` 的模板列表请求改为 `?with_health=true&with_trend=true`（实测网络
面板确认请求真的带上了这两个参数）。卡片上新增两个徽标，与 R54 的全失败徽标
**并列而非互斥**：

| 徽标 | 触发 | 配色 |
|---|---|---|
| 连续 N 次全失败 | `health.all_failed` | destructive |
| 失败率连续上升 | `trend.trend === "regressing"` | warning |
| 失败率连续下降 | `trend.trend === "improving"` | success |

两者正交的 UI 表达：一个恒定 100% 失败的 workflow 只出全失败徽标（相邻差值恒 0
→ trend 是 stable）；一个从 0% 涨到 60% 的只出上升徽标。

**走查方法（如实记录）**：真实数据里没有可看的样本，所以用页内 fetch 拦截注入
了一份带 regressing / all_failed / improving 的响应，再切换子标签触发重新取数
（`window.location.reload` 会把注入冲掉，必须用组件内重取）。结果三个徽标同时
正确渲染：

```
statuses: ["失败率连续上升", "连续 4 次全失败", "失败率连续下降"]
```

随后 `reload()` 恢复真实数据，确认 14 张卡片、零徽标、注入痕迹已清除
（`patched: false`）。截图存在会话产物目录。

**一处走查踩的坑**：主导航的 `<Tab>` 用 Playwright role locator 点击会超时
（`count()=1` 且 `isVisible()=true` 却不可 actionable）。改用 URL 直接进
`/?tab=workflow`——该页面的 tab 由 `?tab=` 驱动，比点击更可靠。

## 4. `FAILURE_STREAK_REQUIRED` 的数据依据（R55 挂账清理）

R53 的结论是「3 合理、不改」，但那次**没有数据**。本轮把本机 8 个有 run 记录的
workflow、共 40 次 run 当作历史时刻逐点回放（每次新 run 落地时若门槛是 k 会不会报警）：

| 门槛 | 触发次数 | 事件 |
|---|---|---|
| 2 | **2** | build 的 6 连败 + **character 的 2 连败**（之后紧接一次 run 就成功） |
| 3 | 1 | 只有 build 的 6 连败 |
| 4 | 1 | 同一个事件，但晚一次 run 才报 |

所以 **3 是「能抓住真实事件、又不把 2 连败报成告警」的最小取值**。取 2 会多报一次
「重试一次就恢复」的假告警；取 4 只推迟发现时点，没有精度收益。

结论**保持 3 不变**，但依据从「推理」换成了「数据」，并把这两个边界写成测试
（character 形状在 required=2 时成立、required=3 时不成立；build 形状前三次结束时
required=3 已触发而 required=4 还没有）。

## 5. 常量表合并（R53 §12-5 挂账关闭）

R53 用测试钉住了「`FAILURE_STREAK_REQUIRED ≤ baseline_limit + 1`」这个耦合，但两个
数仍分处两个文件（`run_profile.py` 与 `workflow_routes.py` 的默认参数），改任一处
都不会碰到另一处。

本轮把 `DEFAULT_BASELINE_LIMIT = 5` 与 `MAX_BASELINE_LIMIT = 20` 收进
`run_profile.py`，端点三处默认值（`list_tasks`、`list_all_tasks`、
`list_workflows.trend_limit`）直接引用，裸 `20` 上限也一并替换。测试改为读同一个
常量，并新增一条「端点里不该再出现裸 20」的检查。

## 6. 四段退避形状（R53 §12-1 挂账清理）

判据 `_rising_shape_violations` 本就按 `len(configured)-1` 循环、支持任意段数，
缺的只是标记与场景。新增 `[stub:fail_four_times]`（配额 4）与场景
`retry_backoff_four_segment_shape_is_honoured`（`delays=[0.4,0.8,1.6,3.2]`）。

**一处刻意的取舍**：初版把量级降到 0.2 起（省 3 秒），随即发现 0.15s 的共模偏移
会把首对压到 1.57——离 `min_ratio=1.5` 只剩 0.07，CI 上很容易翻成假红。改回与
三段场景相同的 0.4 起：同一偏移下是 1.73，仍有安全余量。宁可多等 3 秒，也不要
一条会偶发变红的判据。

实测本机 `[0.413, 0.812, 1.610, 3.210]`（配置比值恒 2.0）。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| `--collect-only` | **2154 tests collected** |
| Low-IL 全量 | **2058 passed / 96 skipped / 0 failed**（127.85s） |
| High-IL 全量（权威） | **2143 passed / 11 skipped / 0 failed**（155.58s） |
| 前端 `npm test` | **490 passed / 0 fail**（484 → 490） |
| 前端 `npm run build` | **✓ built in 6.36s** |
| 本机 e2e | **10/10 场景通过**（新增四段形状） |

**对账**：

- Low-IL：R54 2044 **+14** = **2058** ✓
- High-IL：R54 2129 **+14** = **2143** ✓
- 总用例 R54 口径 2140 → **2154**（+14）✓
- 新增 14 条构成：`test_run_profile.py` 12 + `test_live_snapshot_gate.py` 2。零删除。
- 前端 484 → 490（+6，全部在 `WorkflowTemplatePanel.test.ts`）。

## 8. 变异验证（5 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| `workflow_trend` 不排序（按输入顺序） | 红 | ✓ 1 红 |
| 样本量中段回退正态近似 | 红 | ✓ 3 红 |
| `trend_limit` 裁**最早**那段 | 红 | ✓ 2 红 |
| `FAILURE_STREAK_REQUIRED` 3 → 2 | 红 | ✓ 1 红 |
| health 误用 trend 的窗口而非自己的 | 红 | ✓ 1 红 |

第 3 个值得说：第一次跑这个变异时**只**红了 health 那条测试，trend 那条没红——
因为 `_newest_metas` 是 health 与 trend 共用的，而当时的 trend 测试只覆盖纯函数、
不覆盖路由层。补了 `test_list_workflows_trend_limit_takes_the_newest_runs` 之后
两个都红。这是「共用 helper 的变异要由每个使用者的测试各自钉住」的实例。

## 9. 本轮改动一览（14 改）

| 文件 | 变更 |
|---|---|
| `src/workflow/run_profile.py` | +82 行：`workflow_trend` 纯函数、`DEFAULT_BASELINE_LIMIT`/`MAX_BASELINE_LIMIT`、门槛取值的数据依据注释 |
| `src/web/workflow_routes.py` | +105/−…：`list_workflows` 的 `with_trend`/`trend_limit`、`_collect_workflow_diagnostics`、`_newest_metas`（抽出共用排序）、常量替换 |
| `scripts/check_live_snapshot_gate.py` | +85 行：`_binomial_cdf_le`、`_cp_bounds`、中段改精确界 |
| `scripts/e2e_workflow_stub.py` | +57 行：四段形状场景 |
| `scripts/stub_llm_provider.py` | +11 行：`[stub:fail_four_times]` 标记与文档 |
| `tests/test_run_profile.py` | +287 行：12 条（趋势纯函数 5 + 端点 5 + 门槛数据依据 1 + 常量检查 1），门槛测试改为读共享常量 |
| `tests/test_live_snapshot_gate.py` | +77 行：2 条新测试替换 1 条（中段精确界、一次失败不得更可信、n≤4 豁免） |
| `tests/test_export_run_samples.py` | 告警带测试改用显式 margin，当前快照测试改断言「仍有判定力」 |
| `tests/test_ci_e2e_stub.py` | +2 行：场景清单加四段 |
| `web/src/types/index.ts` | +25 行：`WorkflowTrend`、`WorkflowSummary.trend?` |
| `web/src/lib/api.ts` | +10 行：`listWorkflows` 加 `withTrend`/`trendLimit` |
| `web/src/pages/WorkflowPage.tsx` | 请求改带 `with_trend=true` |
| `web/src/components/workflow/WorkflowPageParts.tsx` | +37 行：上升/下降徽标、`formatRate` |
| `web/src/components/workflow/WorkflowTemplatePanel.test.ts` | +67 行：6 条 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除（本轮又拦下一次：那个文件里多出
`apocalypse-writer` / `humanizer-zh` 等条目，与本轮无关）。

## 10. 未做与未验证的事（如实记录）

1. **未按 workflow 判失败率**：闸门仍用全局合计当基线，workflow 级只做趋势与
   健康度诊断。要改得先把闸门改成 per-workflow 基线（R54 §10-1），涉及阈值来源
   与退出码语义的重新设计。
2. **`p=1.0` 仍无真实数据验证**：本机真实快照是 255/10，没有「全部尝试都失败」
   的形状。精确界修复后这条判据的行为有单测钉住，但真实场景下的表现要等某次
   真出现全失败快照。
3. **`min_ratio=1.5` 的判别力边界未重算**：本轮不但没改，还因为四段场景把量级
   调回 0.4 而进一步避开了这个边界（见 §6）。彻底的判别力分析仍未做。
4. **`workflow_trend` 未判耗时趋势**：`trend` 只看失败率。R51 §10-7 已拒绝过把
   耗时混进同一个 trend（会让「退步」语义变糊），本轮沿用该结论。
5. **`with_trend` 未做缓存**：每次列表请求解析 run 画像，实测全量 92ms 可接受；
   workflow 或 run 数量大幅增长时需要再看。
6. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。本轮改
   `scripts/`、`src/`、`web/` 与 `tests/`，`container-build` 在 GHA 上真构建。
7. **已验证 8021 重启**：本轮重启了服务（旧 PID 26252 → 新 PID，代码含 R55），
   接口与前端走查都在新进程上做的。这与 R53/R54 的「未重启」不同。

## 11. 下一轮候选

1. **闸门改 per-workflow 基线**（R54 §10-1 / §11-2）：唯一还没做的「真正增量」，
   风险在阈值来源变更会改变退出码语义，需要一次单独设计。
2. **`min_ratio` 判别力边界的精确定量**（R53 §11-2）：当前只有一条测试钉住
   「配置 0.4→0.8 时 0.15s 偏移合格、0.1→0.2 时不合格」，没有给出「什么量级下
   这个门槛开始不可信」的公式。
3. **`workflow_trend` 与 `workflow_health` 合并成一次画像扫描**：当前 trend 要
   逐 run 解析 `node_executions`，health 只要 status。若将来两者都在多个端点用，
   可以按 run_id 缓存画像（`_collect_workflow_trends` 已有这个模式）。
4. **`p=1.0` 的真实数据验证**（R53 §11-4）：需要真实出现全失败快照。
5. **全失败徽标的真实样本**：与 4 同源——真出现全失败 workflow 时，可以顺带用
   真实数据复验 R54 的徽标与 R55 的趋势徽标是不是各司其职。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）。
