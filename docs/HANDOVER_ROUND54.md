# DeterminFlow (xs2) 交接报告 — Round 54（workflow 级全失败聚合 + per-workflow 样本量）

> 本轮定位：R53 §12-2 与 §12-3 合并作主线（两者都是「从单任务信号升到 workflow
> 维度」），§11 四项挂账按用户拍定**本轮都不做**，收尾照旧走双基线+推送+CI。
> 基线：`64a5037`（R53 收尾，Low 2023/96/0、High 2108/11/0、前端 479/0、9 场景 e2e）。

## 1. 本轮最重要的一件事：**恒红**的门槛和恒绿的防护是同一个错误的两面

主线里有一项本该是本轮最容易写的：「给 `--check-sample-size` 加 per-workflow
判据」。写到一半去核对真实数据，发现它按直觉写出来会**永远红**：

| workflow | 尝试数 | 失败 | 所需余量（百分点） | margin=10 是否达标 |
|---|---|---|---|---|
| `flywheel-build` | 33 | 3 | 9.81 | 达标 |
| `flywheel-character` | 79 | 2 | 3.46 | 达标 |
| `flywheel-mvp` | 56 | 4 | 6.75 | 达标 |
| `flywheel-post-hoc` | 24 | 1 | 7.99 | 达标 |
| `flywheel-export` | **5** | **0** | **45.07** | 不达标 |
| `flywheel-outline` | 16 | 0 | 17.07 | 不达标 |
| `flywheel-polish` | 14 | 0 | 19.26 | 不达标 |
| `flywheel-reader-sim` | 12 | 0 | 22.09 | 不达标 |
| `flywheel-story-plan` | 16 | 0 | 17.07 | 不达标 |

`flywheel-export` 要把零失败的上界从 45 压到 10，需要约 **29 次尝试**；而那个
workflow 在真实数据里总共只有 **10 个 run**。也就是说这份快照里 5 个不达标的
workflow **物理上补不到**。把「任一 workflow 太薄就失败」做成 CI 门槛，得到的是
一个**每次跑都红**的步骤——与 R45–R53 反复批评的「永远绿的防护」是同一个错误的
两面：两者都让「这一步的颜色」不再携带关于被测对象的信息。

所以 per-workflow 判据最后只有两件事能红，而且第二件才是真正的增量：

1. **`per_workflow` 元数据必须与内容一致** → 不一致时退出码 4（与全局漂移同处置）。
2. 逐 workflow 报告精度，薄的那些列出来说明「这些 workflow 级的失败率不可信」，
   但**不**判失败。它恒退出 0 —— 它是诊断信息，不是判据。叫它判据就会变成假防护。

要真正按 workflow 判失败率，得先把闸门本身改成 per-workflow 基线。那是另一次
改动，R53 §12-3 原本也只把它列为候选。

## 2. workflow 级全失败聚合（R54-A）

### 2.1 任务级信号看不见的那一类

R52 加的 `failure_streak` 判的是「**这一条任务**引用的 run 序列」。它有两个
结构性盲区，都不是 bug 而是粒度问题：

- 只覆盖当前页的任务（`page_size` 默认 20），跨页任务不在其中；
- 已被删除的任务所引用的 run 完全不在考虑范围内。

具体失效形状是这一类：三个任务各跑过一次、各失败一次。任务级每条只看得到
**1 连败**（`required=3` 时不成立），而 workflow 整体已经**连续输 3 次**。

### 2.2 共用判据，不写第二份

新增 `workflow_health(runs, required)`（`src/workflow/run_profile.py`）内部
把 run 元数据映射成 `failure_streak` 要的 `{run_id, status}` 形状后直接调它。
不另写一份「连续失败计数」的理由与 R53 §2.3 抽出 `_rising_shape_violations`
完全相同：两条路径各自演进，迟早对「什么算失败」产生分歧（`stopped` 算不算、
`required=0` 是否永不成立）。

一处必须注意的细节：**内部按 `_order_key` 排序**，不信调用方给的顺序。文件名字典序
会把 `run-10` 排在 `run-9` 前面，不排序就会把最早那次当成最新，于是「最近是否
全挂」判的是错的那一端。这条有专门测试。

### 2.3 路由侧的开关

`GET /api/workflows` 加 `with_health`（默认关）与 `health_limit`（默认 0 = 全部）。

两个默认值的取法不同是有原因的：

- `with_health` 默认关，与 `list_tasks` 的 `with_trend` 同一取舍——默认路径
  （资源选择器、侧栏）只要定义概要，这个开关要逐 workflow 扫 `runs/`。
- `health_limit` 默认 **0（全部）** 而 `baseline_limit` 默认 5，因为问的问题不同：
  `baseline_limit` 是「够不够判趋势」（样本少了判不出方向），这里问「最近是不是
  一直在挂」（样本裁短会把全失败序列的头部截掉，反而更不安全）。

### 2.4 成本实测

21 个工作流全量扫 `runs/`：**0.028s**。所以前端模板列表直接开 `with_health`，
不做「按需展开」。这个数字是打开默认值的依据，不是估计。

## 3. per-workflow 样本量判据（R54-B）

### 3.1 补的是哪一层

`recompute_totals` 只比**全局** attempts/failed。一次「把 A 工作流的一次失败改成
B 工作流的」改动不改变全局合计，于是全局漂移校验通过，而 `snapshot-meta.json`
的 `per_workflow` 块已经在说谎。

实测对照（构造样本，两个 workflow 各 10 次尝试各 1 次失败，把失败从 a 挪到 b）：

```
per-workflow 判据 → 退出码 4，点名 wf-a 与 wf-b
全局判据         → 退出码 0（「失败率 3.92% 未超出阈值 13.9%」）
```

这就是分组复算的唯一价值：它补的是全局校验**结构上**看不见的那一层。

### 3.2 CI 接线与反向验证

ubuntu（bash）与 windows（pwsh）两个 job 各加一步。那一步能红的唯一路径是元数据
漂移，所以 CI 里**必须注入一处漂移并断言退出码 4**，否则判据失效时这一步照样绿。

一处实现细节：注入漂移的 Python 用**单行 `python -c`** 而不是 heredoc。heredoc
体必须顶格，会提前终止 YAML 块标量，整份 workflow 变成非法 YAML——这是写的时候
就踩到并改掉的（初版写完立刻用 `yaml.safe_load` 验过）。

## 4. 实测（三处）

| 环境 | 结果 |
|---|---|
| 本机，真实快照 | 退出码 0；4 达标 / 5 不达标，逐个点名 |
| 本机，注入漂移 | 退出码 4 |
| 本机，模拟 ubuntu CI 两步 | 真实 0 → 注入后 4 |

## 5. `with_health` 的端到端行为

| 场景 | 结论 |
|---|---|
| 3 个任务各失败 1 次（workflow 共 3 连败） | workflow 级 `all_failed=true`；任务级不成立 |
| 输入顺序打乱 | 结论不变（内部排序） |
| 最新一次是 `completed` | 连败 0（不是「2 次失败」） |
| 无 run 记录 | `run_count=0`、`all_failed=false`（没有证据 ≠ 全失败） |
| 中间夹一次 `stopped` | 不成立（人工停止不是失败证据） |
| `health_limit=2` | 裁**最新** 2 条，不是最早 2 条 |

## 6. 前端

`WorkflowPage` 的模板列表请求改为 `?with_health=true`，卡片状态行下加徽标
「连续 N 次全失败」（`AlertTriangle` + `destructive` 配色），只在 `all_failed` 时
渲染。文案里的人数用后端给的 `consecutive_failed`，门槛不写死——与 R52 任务级
徽标同一条纪律。

`listWorkflows()` 加了可选参数（`withHealth` / `healthLimit`），默认行为不变，
`NovelWorkbenchPage` 那个调用点不受影响。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_run_profile.py` | **63 passed**（54 → 63） |
| 定向：`test_live_snapshot_gate.py` | **56 passed**（44 → 56） |
| 收齐后 `--collect-only` | **2140 tests collected** |
| Low-IL 全量 | **2044 passed / 96 skipped / 0 failed**（119.75s） |
| High-IL 全量（权威） | **2129 passed / 11 skipped / 0 failed**（136.45s） |
| 前端 `npm test` | **484 passed / 0 fail**（479 → 484） |
| 前端 `npm run build` | **✓ built in 6.37s** |
| 本机 e2e | **9/9 场景通过** |

**对账**：

- Low-IL：R53 2023 **+21** = **2044** ✓
- High-IL：R53 2108 **+21** = **2129** ✓
- 总用例 R53 口径 2119 → **2140**（+21）✓
- 新增 21 条构成：`test_run_profile.py` 9 + `test_live_snapshot_gate.py` 12。零删除。
- 前端 479 → 484（+5，新文件 `WorkflowTemplatePanel.test.ts`）。

## 8. 变异验证（4 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| `workflow_health` 不排序（按输入顺序） | 红 | ✓ 1 红 |
| per-workflow 关闭漂移检测 | 红 | ✓ 3 红 |
| `health_limit` 裁最早那段 | 红 | ✓ 1 红 |
| per-workflow 把「薄」当硬失败 | 红 | ✓ 3 红 |

第 4 个最值得说：把「薄」当硬失败之后，连**入库快照自己**都过不了
（`test_per_workflow_passes_on_the_committed_snapshot` 红）。这就是 §1 那个结论的
实证——真实快照里 5 个 workflow 物理上补不到 margin=10，硬门槛一接就恒红。

## 9. 本轮改动一览（11 改 1 增）

| 文件 | 变更 |
|---|---|
| `src/workflow/run_profile.py` | +45 行：`workflow_health` 纯函数（复用 `failure_streak`，内部排序） |
| `src/web/workflow_routes.py` | +70 行：`_collect_workflow_health`、`_iter_run_metadata` 顺带取 `status`、`list_workflows` 的 `with_health`/`health_limit` |
| `scripts/check_live_snapshot_gate.py` | +143 行：`recompute_per_workflow`、`check_per_workflow`、`--check-per-workflow` 并入互斥表 |
| `.github/workflows/ci.yml` | +57 行：ubuntu 与 windows 各一步 + 反向验证注入漂移 |
| `tests/test_run_profile.py` | +173 行：9 条（纯函数 5 + 端点 4） |
| `tests/test_live_snapshot_gate.py` | +203 行：12 条（漂移四态 + 薄不判失败 + CI 接线 4 + 互斥 1 等） |
| `web/src/types/index.ts` | +17 行：`WorkflowHealth`、`WorkflowSummary.health?` |
| `web/src/lib/api.ts` | +19 行：`listWorkflows` 可选参数 |
| `web/src/pages/WorkflowPage.tsx` | 请求改带 `with_health=true` |
| `web/src/components/workflow/WorkflowPageParts.tsx` | +14 行：全失败徽标 |
| `web/src/components/workflow/WorkflowTemplatePanel.test.ts` | **新文件** 5 条 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 10. 未做与未验证的事（如实记录）

1. **未按 workflow 判失败率**：这是 §1 那个结论的另一面。当前闸门用全局合计当
   基线，per-workflow 只做诊断。要改得先把闸门改成 per-workflow 基线，涉及阈值
   来源与退出码语义的重新设计。
2. **§11 四项挂账本轮不做**（用户拍定）：三段以上退避形状、`min_ratio` 判别力
   边界重算、`p=1.0` 修复的真实数据验证、`FAILURE_STREAK_REQUIRED` 未改。
3. **`workflow_health` 未做「按 workflow 判趋势」**：`trend` 仍是任务级。workflow
   级 trend 与本次的 health 是同一类工作，可下一轮一起做。
4. **`with_health` 未做缓存**：每次列表请求重扫 `runs/`，实测 28ms 可接受；若将来
   workflow 数量或 run 数量大幅增长需要再看。
5. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。本轮改 `scripts/`
   与 `tests/`，`container-build` 在 GHA 上真构建。
6. **未重启 8021 服务**：改动涉及一个新端点开关与前端，但默认路径行为不变；
   服务仍在跑（PID 26252）。
7. **前端只验了 build 与单测，未做浏览器走查**：徽标只在全失败时出现，
   真实数据里当前没有全失败 workflow，走查也没有可看的样本。

## 11. 下一轮候选

1. **workflow 级趋势**（与 R51 §12-1「趋势上到 workflow 列表」是同一件事）：
   `trend` 目前是任务级，和本轮做完的 `health` 正好配成一对。判据可复用
   `compare_run_baseline`，缺的是 workflow 级的时间序列选择。
2. **闸门改 per-workflow 基线**：§10-1 那条。风险在于阈值来源变更会改变退出码
   语义，需要一次单独设计。
3. **`baseline_limit` 与 `FAILURE_STREAK_REQUIRED` 合并成常量表**（R53 §12-5）：
   仍未做，测试钉住的是耦合而不是根治。
4. **四段退避形状**（R53 §12-1）：判据已支持任意段数，缺标记与场景，价值仍低。
5. **`p=1.0` 修复的真实数据验证**（R53 §11-4）：需要真实出现全失败快照。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；CI 五 job 全绿。
