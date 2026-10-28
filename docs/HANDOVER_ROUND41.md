# DeterminFlow (xs2) 交接报告 — Round 41（维护轮：画像三面闭环——导出/可视化/周期化）

> 本轮定位：R40 §8 前 3 项候选全数落地，把 R40 建成的「供应商失败率画像」
> 从**只有 API/脚本出口**补成**界面出口 + 历史查询 + 周期化流程**的闭环：
> ①run-profile 端点支持 `?run_id=` 查任意历史 run（含路径穿越校验）；
> ②前端任务执行视图新增「运行画像」抽屉，逐阶段渲染尝试/失败/错误分类；
> ③挖矿脚本新增 `--summary` 紧凑口径并写进每轮收官固定动作。
> 基线：`b2a3d96`（R40 文档尾）→ 本轮 xs2 提交 2 个（见 §5），插件仓零提交。

## 1. run-profile 端点扩展（候选 3：`?run_id=` 历史查询）

`src/web/workflow_routes.py` 的 `get_task_run_profile`（R40 建）新增可选查询参数：

- **语义**：缺省仍取任务 JSON 记录的最新 run（R40 行为不变）；`?run_id=run-xxx`
  直接读 `runs/{run_id}.json`。任务/运行不存在仍是 404 三态（文案不变）。
- **入参校验**：新增模块级 `_RUN_ID_RE = ^[\w][\w\-]*$`（与既有 `_SCRIPT_NAME_RE`
  同款字符集，无点无斜杠），非法 run_id 拒 **400 `run_id 包含非法字符`**——
  查询串入参进路径拼接，不加校验就是路径穿越面。
- **只读纪律不变**：仍不建目录不写状态，B26/B28 静态钉测守卫自动覆盖该端点。

单测新增 2 条（`tests/test_run_profile.py` 12 → 14）：

| 用例 | 断言 |
|---|---|
| `test_run_profile_endpoint_explicit_run_id_queries_history` | 缺省取 `run-abc`（最新）、`?run_id=run-old` 取历史 run 的 status/totals/error_classes/stages 全部对上 |
| `test_run_profile_endpoint_run_id_validation` | 4 种穿越形态（`..%5C..%5Cevil` / `..%2F..%2Fdata` / `%2e%2e%2fescape` / `a/b`）全拒 400；`run-ghost` 拒 404 且文案为「运行记录不存在」 |

零建目录钉测同步扩到 `?run_id=` 变体（幻影 run 查询后文件树逐字节不变）。

## 2. 前端运行画像可视化（候选 1）

新增 `web/src/components/workflow/RunProfilePanel.tsx`（抽屉）+ `runProfileView.ts`
（纯展示映射），接入 `TaskExecuteToolbar` 的「运行画像」按钮：

- **入口**：任务执行视图工具栏右端（停止按钮左侧），`aria-haspopup="dialog"`；
  抽屉右滑 440px，遮罩点击/Escape 关闭。
- **头部**：run_id、运行状态徽章、开始/结束时间、总耗时；`?run_id=` 查询输入框
  + 查询按钮（前端调 `getTaskRunProfile(wf, task, runId)`）。
- **汇总卡**：阶段数、尝试数、成功/失败、总失败率、聚合错误分类徽章。
- **逐阶段卡**：阶段名 + 失败率（有失败标红）、尝试/成功/失败/自动重试/阶段耗时、
  错误分类徽章、`<details>` 折叠的逐尝试记录（序号 + trigger 文案 + 状态 + 耗时
  + 错误分类 + 原始错误文本）。
- **错误分类文案**：`http_5xx`/`timeout`/`stream_stall`/`connection`/`other` →
  「HTTP 5xx / 超时 / 流式停摆 / 连接错误 / 其他」；空值与未知分类诚实回退原文。
- **诚实 null 处理**：`wall_seconds` 为 null（B31 之前的旧 run）显示 `-`，
  不伪装成 0；`failure_rate` 为 null（空 run）同样 `-`。

### 活体暴露并修复的界面缺陷

真实 run（`xs2-novel-flywheel-character` / `run-cef95ebf`）里 `agent_deep` 与
`script_persist_deep` 各执行 **4 次**（节点定义内的循环重复执行），`node_id` 完全
重复。初版 `key={stage.node_id}` 会产生重复 key，且用户无法分辨同名阶段。修复：
key 改 `${node_id}-${index}`，重复 node_id 的卡片头追加 `#1`–`#4` 序号
（`data-node-id` 保留原名供定位）。回归锚
`test repeated node ids in one run get distinct cards and ordinal labels` 用该 run
的真实四段形态钉死。

### 前端测试（净增 10，`test:workflow` 17 → 27）

- `runProfileView.test.ts`（5）：错误分类六桶文案、尝试状态文案/色档、失败率
  格式化（null→`-`、0→`0%`）、时长格式化（0.071 秒 / 59 秒 / 10 分 0 秒 /
  2 时 1 分 / null→`-`）、`sortedAttempts` 数值容错。
- `RunProfilePanel.test.ts`（5，happy-dom）：关闭态不渲染；R38 重试形态全量渲染
  （run_id/状态/耗时/总失败率/聚合分类/2 张阶段卡/折叠明细展开后的 trigger、
  错误文本、分类徽章、耗时）；抓取失败走 `role=alert` 人因化文案；同名节点
  4 次执行各自成卡 + `#n` 序号 + null 耗时诚实显示；`?run_id=` 表单把显式
  run_id 透传给 fetcher。

## 3. 挖矿脚本周期化（候选 2）

`scripts/provider_failure_profile.py`：

- 新增 `--summary`：每 workflow 一行 + TOTAL 行（`runs= attempts= failed=
  failure_rate= failing_stages= error_classes=`），供交接文档逐轮贴表形成时间序列。
- 结构重构：`_iter_run_files_in(workflows_dir, ...)`（可注入目录）→
  `collect_profiles()` → `summarize()`，纯读取、便于测试；`_iter_run_files`
  保留为真实目录的薄封装。
- **顺带修一处采样缺陷**：`limit` 原先在解析前截断文件列表，一条坏 JSON 会占掉
  配额让「最近 N 次 run」静默缩小。现改为按**成功解析数**计数。

测试（新文件 `tests/test_provider_failure_profile.py`，5 条，此前脚本零覆盖）：

| 用例 | 断言 |
|---|---|
| `collect_and_summarize_aggregates_across_runs` | 跨 run 汇总 5 尝试/1 失败/0.2 失败率/失败阶段/错误分类；坏 JSON 与空 runs 目录被跳过，无 runs 的 workflow 不入选 |
| `limit_truncates_per_workflow` | limit=1 取到最新的有效 run（不被坏文件占位） |
| `workflow_filter_isolates` | 过滤命中/未命中两态 |
| `summary_is_empty_for_missing_dir` | 目录不存在时诚实空结果不抛异常 |
| `collect_is_strictly_read_only` | 扫描前后文件树 + mtime 逐一不变 |

### 周期化落地方式

脚本自身**严格只读**，不写任何文件（有上表末条钉死）；「每轮固定跑」的责任落在
交接文档——已在 `docs/PROJECT_INFO.md` 的维护入口下新增「每轮收官固定动作
（R41 起）」，要求跑 `--summary` 并把输出贴进当轮交接的同口径表格。本轮作为
第 1 个数据点记于 §4。

## 4. 供应商失败率时间序列（第 1 个数据点）

`python scripts/provider_failure_profile.py --summary`（每 workflow 最近 3 次 run）：

```
xs2-novel-flywheel-build:      runs=3 attempts=27 failed=1 failure_rate=3.7%  failing_stages=agent_corelaws                          error_classes={"http_5xx": 1}
xs2-novel-flywheel-character:  runs=3 attempts=75 failed=1 failure_rate=1.3%  failing_stages=agent_deep                              error_classes={"timeout": 1}
xs2-novel-flywheel-export:     runs=3 attempts=3  failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-mvp:        runs=2 attempts=56 failed=4 failure_rate=7.1%  failing_stages=script_check_originality,script_smart_context error_classes={"other": 4}
xs2-novel-flywheel-outline:    runs=2 attempts=16 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-polish:     runs=2 attempts=14 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-post-hoc:   runs=3 attempts=24 failed=1 failure_rate=4.2%  failing_stages=script_confirm_archive                  error_classes={"other": 1}
xs2-novel-flywheel-reader-sim: runs=3 attempts=12 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-story-plan: runs=2 attempts=16 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
TOTAL: runs=23 attempts=243 failed=7 failure_rate=2.9%
```

（下一轮同口径复跑即可与本表逐行比对。）

## 5. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | ①`feat(workflow)` | run-profile `?run_id=` 历史查询 + 非法入参 400 + 单测 14 |
| xs2 | ②`feat(web)` | 前端运行画像抽屉 + 同名节点序号 + 挖矿 `--summary`/只读钉测 |
| xs2 | 本文档提交 | 交接文档 + PROJECT_INFO R41 条目 |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性，
与前几轮一致）。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：画像（聚合+端点+B31） | **14 passed** |
| 定向：挖矿脚本（此前零覆盖） | **5 passed** |
| Low-IL 全量 | **1833 passed / 96 skipped / 0 failed**（100.54s） |
| High-IL 全量（权威） | **1918 passed / 11 skipped / 0 failed**（131.33s） |
| 插件套件（双 CWD） | **98 passed / 0 failed ×2** |
| 前端 8 组 | **457 passed / 0 fail**（R40 447 → +10） |
| 前端 lint / build | 0 problems / ✓ 5.53s |
| 存储名审计 | **[clean]** exit 0 |
| 索引污染复查 | **59 条，零 pytest 污染**，与 R40 完全一致 |
| 活体（8021，R41 代码） | 4/4 ready、degraded=false；e2e **17 passed / 0 skip** |

对账：Low 1826 + 2(端点新测) + 5(挖矿新测) = **1833** ✓；
High 1911 + 7 = **1918** ✓。总用例 R40 口径 1922 → **1929**
（High passed+skipped：1918+11）。

## 7. 活体端到端验证（真实服务 + 真实浏览器）

服务重启：旧 PID 23392 停止 → `powershell Start-Process -WindowStyle Hidden`
脱离会话启动（R40 §7.5 纪律）→ 新 PID 22200，4/4 执行器 ready、
degraded=false，日志 `data/system/test-probes/r41-8021-run{,-err}.log`。

**端点探针**（真实数据，非合成）：

- 最新 run：`task-0467488b` → `run-cef95ebf`，18 阶段 / 30 尝试 / 0 失败。
- 历史 run：`?run_id=run-99b3bd1b` → 200，`agent_deep` 第 3 次尝试
  **629.707s timeout**、分类 `{"timeout": 1}`——即 R38 §2.0 那条 600s
  `stream_chunk_timeout` 打穿实录，经新参数可从 UI/API 直达。
- 非法 run_id：`..%2F..%2Fx` / `a/b` / `%2e%2e%5Cevil` 全部 **400**。
- 幻影 run：`run-ghost` → **404「运行记录不存在」**。

**界面走查**（ZCode 内置浏览器，1280×720）：

1. 工作流 → 任务历史 → 角色创建管线_20261027_095302（`task-0467488b`）
   → 工具栏「运行画像」按钮出现。
2. 点开抽屉：18 张阶段卡；`agent_deep`/`script_persist_deep` 各 4 张、
   带 `#1`–`#4` 序号（重复 key 修复生效）；总数行「阶段 18 / 尝试 30 /
   成功 30 / 失败 0 / 总失败率 0%」与 API 返回逐项一致。
3. 输入 `run-99b3bd1b` 查询：抽屉整体切换为该历史 run——状态「失败」、
   阶段 11 / 尝试 15 / 成功 14 / 失败 1 / 总失败率 7%、聚合徽章「超时 ×1」；
   `agent_deep#3` 卡片失败率 33%、`text-destructive` 标红、错误徽章「超时 ×1」。
4. 展开该卡 `尝试记录 (3)`：三次尝试逐条可见（1 分 15 秒成功 / 5 分 51 秒
   成功 / 第 3 次超时失败）。
5. 几何校验：抽屉 440×720 靠右、内容区可滚动（scrollH 1601 / clientH 545）、
   `overflowX=false`（无横向溢出）、抽屉内 11 张卡全部可见渲染。
6. 截图存档：`data/system/test-probes/r41-run-profile-panel.png`（346KB）。

**观察项（非缺陷，记录备查）**：`run-99b3bd1b` 里 `agent_deep` 的第 2、3 次
尝试，后端 `attempt_history` 的 `trigger` 实际就是 `initial`、
`automatic_retry_count=0`——这是节点定义内的**循环重复执行**（同 node_id 跑
N 次），不是重试。前端因此如实显示「首次执行」。若后续要区分「循环轮次」
与「重试」，属后端语义扩展，不在本轮范围。

## 8. 遗留风险与需人工确认事项

1. **推送**：xs2 积压 **25 个**提交（R29 起 + R39 4 + R40 3 + 本轮 2 + 文档）、
   插件仓 4 个——需维护者授权推送触发 CI 全量核对（外向操作，未执行）。
2. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变；
   分别需容器环境、cargo 工具链、外部基础设施决策（T2 类）。
3. **画像 wall_seconds 对历史 run 为 null**：B31 只对新 run 生效；R38 及更早
   run 无 `completed_at`，本轮 UI 与脚本均诚实显示 `None`/`-`（只读纪律，
   历史不可追补）。压测画像以 B31 后的 run 为准。
4. **High-IL 跑法必须带完整 PYTHONPATH**：本轮首次漏了 `win32` 系列路径，
   4 个模块在收集期报 `ModuleNotFoundError: pywintypes`（环境问题，非代码
   缺陷）。正确命令见 PROJECT_INFO 平台注意事项 9，PYTHONPATH 需含
   `site-packages;win32;win32/lib;pythonwin;pywin32_system32`。
5. **服务进程托管**：仍须 `powershell Start-Process -WindowStyle Hidden`
   脱离会话启动（本轮实测有效）；后台 shell 直接启动会被连带回收。
6. **静态守卫的模块内局限**：见 R40 §2 末——跨模块助手闭包与方法内调用点
   覆盖边界已 docstring 化。

## 9. 下一轮候选

1. **失败率告警阈值化**（中等工作量）：`--summary` 已在，可加
   `--fail-if-above <pct>` 让收官动作在失败率超阈时非零退出，使「周期化」
   从人工比对升级为可挂 CI/脚本的硬闸门。
2. **画像跨 run 对比视图**（中等工作量）：抽屉内加「与上一次 run 对比」列，
   直接把 `run-a` vs `run-b` 的阶段失败率差值渲染出来。
3. **循环节点与重试语义区分**（低风险，需后端配合）：见 §7 观察项——若
   `attempt_history` 需要区分「循环第 N 轮」与「第 N 次重试」，属 Core 语义
   扩展，前端已有 `#n` 序号可复用。

其余：推送（待授权）、updater 死通道（待 cargo）、POSIX（待环境）、
大陆下载加速（待基础设施决策）。

## 10. 本轮未实际运行

无。本轮全部结论均有实际命令/测试/探针/界面走查输出支撑。
