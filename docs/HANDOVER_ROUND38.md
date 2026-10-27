# DeterminFlow (xs2) 交接报告 — Round 38（维护轮：R37 §8 候选落地）

> 本轮定位：R36 §6 遗留项 5 收口——**纯 API 全流程实跑**（建书 → 9 阶段任务驱动 →
> 0% 观察态 → sync-history 登记 → 100%），顺带完成 sync-history UI 按钮
> **真实浏览器逐字走查**；外加新缺陷 **B26**（读端点驱车建目录 + 谎报 0% 书，
> B24 家族残留面）修复与 `nope_missing` 残留清理（该残留即 B26 机制的产物）。
> 基线：`f9deef6`（R37 文档尾）→ 本轮 xs2 提交（见 §7）。

## 1. B26：console 读端点「查询即建目录」+ 谎报 0% 书

### 1.1 现象与活体复现（修复前，8021 实测）

```
GET /api/novel-console/progress?workflow_id=xs2-novel-flywheel
    &workspace=data/workspaces/books/r38-flow        ← 该书从未创建
→ HTTP 200（谎报一本 0% 的书）+ data/workspaces/books/r38-flow/ 空目录被静默创建
```

R37 §8.3 记录的 `data/workspaces/nope_missing` 无名残留（2026-10-24 时间戳）
正是同一机制的历史产物——本轮实跑前预检探针（对尚不存在的工作区 GET progress）
当场复现了一次目录创建，驱动器首跑因「书已存在」保护中止（run_log 08:34:53
ABORT 事件），随即转入缺陷处置。

### 1.2 根因

`WorkspaceManager.resolve_workflow_workspace` 的文档语义就是「自动创建目录」
（`src/core/workspace_manager.py`——为任务执行/建书面设计），console 面 27 个
解析点（R37 B24 收编）全部经由它；**读端点**复用该语义后，任何 GET 都会对
不存在的合法白名单工作区产生「查询即建目录」副作用并谎报 0%。B24 修的是
越界逃逸（400），白名单内的只读副作用面当时未触及。

### 1.3 修复（两层，接口向后兼容）

| 层 | 文件 | 内容 |
|---|---|---|
| 核心 | `src/core/workspace_manager.py` | `resolve_workflow_workspace` 新增 `create: bool = True` 形参：默认 True（任务执行/工作流 routes/engine 全部既有调用点零变化），`create=False` 只解析不创建 |
| console | `src/web/novel_routes.py` | `_console_root` 透传 `create`；新增 `_console_existing_root`（解析不创建 + 工作区不存在 → **404 诚实拒因**）。15 个调用点翻转：13 个 GET 读端点（progress/reader-report/archive-state/continuation/chapters/context/library-usage/adopted-writing/reference-candidates/assistant-history/library/{id}/mechanism-recommendations/chapters/removal-preview）+ sync-history + DELETE /projects 改 `create=False`；GET progress 用 existing-root 形态。**10 个写端点保持默认 create=True**（PUT /projects 建书、PUT /text、assistant、plot/apply、chapters/remove、repair/apply、library publish/attach、import-url、POST chapters/context）——PUT 建书实际依赖 `atomic_json` 的 `parent.mkdir`，与解析器解耦，语义不回归 |

### 1.4 验证（全部实际执行）

- 定向回归：12 个相关测试文件 **152 passed / 1 skipped**（新增 6 条 B26 回归，
  `tests/test_workspace_override_whitelist.py` 9→15 条；两个文件级 lambda 桩与
  5 处内联 lambda 桩补 `create` 形参——接口新增必选兼容实为可选关键字，桩同步）。
- 活体（修复后 8021，重启加载）：绝对/相对两形态幻影 GET progress → **404 + 拒因
  「作品工作区不存在」+ 零目录副作用**；sync-history 幻影 → 404（既有拒因
  「作品尚未保存」不变）；DELETE 幻影 → 200（既有成功契约不变）+ 零目录；
  真书 r33-flow 进度 200 / 100% 不受影响。
- 前端无需改动：NovelWorkbenchPage 进度读取已有 error 分支（「读取进度失败」），
  404 走既有降级路径。
- `nope_missing` 残留删除（R37 §8.3 项闭合）；同类 `wf-1/wf-drain/wf-resume/
  wf-wait` 为引擎默认工作区（历史任务数据），非 B26 家族，保留。

## 2. 纯 API 全流程实跑（R36 §6 遗留项 5 主体验证）

### 2.0 环境参数修正：stream_chunk_timeout 从「文档已暴露」变为「实跑必须」

首次发车 20 分钟后 build 阶段第 1 承担死在 `agent_society` 节点：

```
No streaming chunk received for 120.0s (model=Gemma-4-31B-IT, chunks_received=1442)
```

即 R37 §3 文档化的默认 120s 阈值在 AMD 免费档下**必然踩雷**——1400+ chunk 已产出后
中途静默超过 2 分钟。处置：`.env` 追加 `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600`
（R37 §3 记载的全局兜底途径）并重启服务。此后 build 第 3 次尝试成功。

**但 600s 也被打穿过一次**：character 第 1 次尝试在 `agent_deep` 节点报
`No streaming chunk received for 600.0s (chunks_received=602)`。结论（供后续性能轮参考）：
该供应商存在**分钟级流式停摆**，调整超时只能降低概率、无法根除；要靠重试消化。
这是供应商质量问题，非本仓代码缺陷。

### 2.0b character 各次失败原因（重试画像）

- attempt 1（22.3 min）：`agent_deep` 流式 600s 静默；
- attempt 2（8.3 min）：`script_extract` 节点 `JSON 解析失败: Expecting ','
  delimiter: line 43 column 49`——模型输出畸形 JSON，`safe_repair_then_retry` 未救回；
- attempt 3（26.7 min）：completed。

值得注意的是三个尝试之间存在**跨尝试增量推进**：`cache/character/` 里的
`skeleton.json`、`beliefs.json`、`江篱_deep.json`、`沈若冰_deep.json` 逐次累积，
人物由管线从世界观自动派生（未传 `character_names`），证明增量产物复用有效。

### 2.1 驱动方式

探针驱动器 `data/system/tmp_r38/run_flow.py`（用毕即删，运行日志
`run_log.jsonl` 存档于本文档）：严格 API 驱动，无 UI 参与——

1. `PUT /api/novel-console/projects` 建书 `data/workspaces/books/r38-flow`
   （state：refs={} / completed=[] / mode=short / _revision=0）；
2. 9 阶段（build→character→story-plan→outline→mvp→polish→reader-sim→post-hoc→
   export）逐个 `POST /api/workflows/xs2-novel-flywheel-<stage>/tasks` +
   `.../tasks/<task_id>/run`，20s 轮询至终态；失败重建任务重试（≤4 次/阶段）；
3. 参数面只发「用户可填变量」（variables API 的 `source_type=input && !hidden
   && !source_node_id`），premise/genre 为本书新值（都市悬疑短篇），
   `character_names` 不传（管线自动派生，不继承历史书人物）；`_json_output_file`
   等引擎透传变量一律不传（避免指向历史书绝对路径）。
   参数模板取自 r33-flow（R35 实跑）各阶段成功任务快照。
4. 模型面：本机当前唯一供应商 `amd`（Gemma-4-31B-IT，直连探针 HTTP 200 但
   平铃延迟 56s）——默认模型解析链 `main.model=null → 第一个可用模型` 实际生效。

### 2.2 观察项（对照 R35 观察项与 R36 三层处置）

**9 阶段全部完成（9/9），任务级耗时（含重试）合计 129.9 分钟：**

| 阶段 | 尝试 | 终态 | 各次耗时(min) | 产物 |
|---|---|---|---|---|
| build | 2 | completed | 13.0 / 15.0 | world_foundation.md 14,494 B + 六维世界 JSON |
| character | 3 | completed | 22.3 / 8.3 / 26.7 | character_profiles.md 16,834 B + character_voice.md |
| story-plan | 1 | completed | 6.0 | story_plan → 大纲前序 |
| outline | 1 | completed | 5.0 | near_term_outline.md 908 B |
| mvp | 1 | completed | 13.0 | story/0001/chapter.md + 15 个配套产物 |
| polish | 1 | completed | 9.3 | chapter.md 5,023 B |
| reader-sim | 1 | completed | 3.0 | reader_report.json 1,815 B |
| post-hoc | 1 | completed | 8.0 | diff_story_confirmed.md 1,343 B |
| export | 1 | completed | 0.3 | manuscript.md 5,041 B |

**终态进度观察（R35 观察项完整复现，R36 三层处置的实证）：**

```json
{"percent": 0, "completed_count": 0, "total_count": 9, "label": "建立世界观未完成",
 "chapter_count": 1, "can_download": true, "export_current": false,
 "reader_verdict": "pass"}
manifest: {"refs": {}, "completed": [], "_revision": 1}
```

即：**成品真实存在（1 章、可下载、读者结论 pass），但进度 0%**——因为经 API 直接驱动的
任务不写 manifest refs（`novel_progress` 只统计 refs 指向的任务，`test_c16` 钉死该语义，
R36 已定性为「归属语义正确、展示需诚实」）。前端据此渲染出诚实提示 + 登记按钮（§2.3）。

**sync-history 登记（UI 触发后实测）：**`POST /progress/sync-history` → 200，
`synced` 覆盖 9 个阶段，manifest `revision` 1→2，`refs` 9 条齐备（build/character/
story-plan/outline/mvp/polish/reader-sim/post-hoc/export），进度变 100%。

**幂等性（活体二次/三次调用）：**第二次、第三次均 `{"synced": [], "revision": 2}`——
已有 refs 一律不动（与 `test_novel_full_flow_round34.py` s2 单测语义一致）。

### 2.3 UI 按钮真实浏览器走查（R36 §6 遗留项 5，已完成）

流程（真实 IAB 浏览器，`http://127.0.0.1:8021`）：

1. 页签「小说控制台」→ 工作台「我的作品」；
2. 工作区输入框填 `data/workspaces/books/r38-flow` → 「切换工作区」→ 状态「已切换到工作区」；
3. 观察当前作品卡片：**0% + 「1 章」+ 「下载上次导出」三个事实同时成立**，
   状态行逐字为：
   > 建立世界观未完成 · 已完成 0/9 个生产步骤；检测到已有章节产物，但本作暂无流程记录
   > （经 API 直接启动的任务不计入进度，从创作流程页启动后开始统计）

   按钮「把已完成的历史任务登记进进度」可见——**出现条件（percent===0 &&
   chapter_count>0）与判定完全吻合**；
4. 点击按钮 → 等待 3.5s → 状态行变为「本篇已导出 · 已完成 9/9 个生产步骤」，
   **按钮消失**（0% 态专属，登记后不再展示）。

截图存档两张（0% 态含诚实提示与按钮 / 登记后 100% 态）。
浏览器操作细节：`getByRole("button").click()` 在本页 overline 布局下 actionability
探测失败（pointer probe 无点击点），改用 `locator.evaluate(el => el.click())` 成功——
属 IAB 点击探测限制，非产品缺陷。

## 3. B27：B26 新测试污染真实工作区索引（本轮引入、本轮修复）

### 3.1 现象

浏览器走查时「我的作品」列表里出现 3 个标题为「x」的作品，路径分别为
`C:\Users\wenbo\AppData\Local\Temp\pytest-of-wenbo\pytest-76\...`、
`F:\DeterminFlow x2\xs2\pytest-of-wenbo\pytest-6\...`、`pytest-7\...`。
真实运行索引 `data/novel-console/workspaces.json` 从 64 条膨胀到 73 条，其中 9 条为
pytest 临时路径。

### 3.2 根因

本轮新增的 B26 回归 `test_console_created_book_progress_still_200` 走 `PUT /projects`
建书，而 `save_project` 里有 `atomic_json(_index, sorted(roots))`——**写索引**。
我的 `_client` 夹具 patch 了 `DATA_DIR` 与 `WORKFLOW_WORKSPACES_DIR`，**没有 patch
`_index`**（它是模块级常量 `DATA_DIR / "novel-console" / "workspaces.json"`，在 import
时求值，所以 patch `DATA_DIR` 不会带动它）。于是测试把 tmp_path 写进了真实索引。

对比：R36/R37 的 sync-history、B24 测试都是**只读或 400 路径**，从不触达
`save_project` 的成功分支，所以此前没有暴露这条夹具缺口——是**我的新用例**引入的新面。

### 3.3 修复

`tests/test_workspace_override_whitelist.py` 的 `_client` 增加一行：

```python
monkeypatch.setattr(novel_routes, "_index",
                    tmp_path / "data" / "novel-console" / "workspaces.json")
```

并把本次已产生的 9 条污染从真实索引中剔除（保留其余 64 条，`r38-flow` 在册）。
验证：单独跑该文件 15 passed；跑完复查索引 `pytest pollution: 0`。

### 3.4 教训

**测试里凡是走到「写」分支的用例，必须审计它写到的每一个模块级路径常量。**
`DATA_DIR` 被 patch 不代表 `_index`、`_manifest`、`_library_root` 等派生常量跟着变——
它们在 import 期就固定了。本轮把该纪律写进交接，后续新增写路径用例须逐一核对。

## 4. 服务与工程事项

- 服务重启一次（加载 B26 后端代码）：原 8021 进程树（主服务 + 4 执行器）终止，
  `python run.py` 重启，4/4 执行器 ready、degraded=false；日志
  `xs2_r38_service.log`（已 gitignore）。
- 探针脚本（驱动器/变量探针/参数模板提取）集中于 `data/system/tmp_r38/`，
  与 conftest 探针钉位目录（`data/system/test-probes`）分离，用毕清理。

## 5. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：B26 涉及 12 文件 | **152 passed / 1 skipped**（含新增 6 条 B26 回归） |
| Low-IL 全量 | **1803 passed / 96 skipped / 0 failed**（98.64s；对账 1797 + 6 ✓） |
| High-IL 全量（权威） | **1888 passed / 11 skipped / 0 failed**（118.04s；对账 1882 + 6 ✓） |
| 插件套件 | **98 passed / 0 failed**（本轮零插件改动，与 R37 一致） |
| 前端三连 | lint 0 problems；**8 组 447 passed / 0 fail**（48+17+137+81+139+1+18+6，前端零改动与 R37 一致）；build ✓ 5.94s |
| 存储名审计 | `[clean]` exit 0 |
| B26 活体 | 幻影 GET 404+零目录 ×2 形态；sync-history/DELETE 契约保持；真书 100% 不受影响 |
| B27 复核 | 单文件 15 passed；跑完复查真实索引 `pytest pollution: 0` |
| 全流程实跑 | **9/9 阶段 completed**；129.9 任务分钟；终态 0%+1章+可下载 |
| UI 按钮走查 | 真实浏览器：0% 态诚实提示逐字吻合 → 点击 → 9/9 100% + 按钮消失；2 张截图 |

## 6. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | `182d4cf` | B26 主体：resolve_workflow_workspace `create` 参数 + console 读端点 `create=False`/404 化 + 6 条回归 + 7 处测试桩同步 |
| xs2 | 本文档提交 | B27 夹具修复 + 交接文档 + PROJECT_INFO R38 条目 |
| — | 未提交 | `nope_missing` 删除与索引污染清理均为运行数据，不入库 |

## 7. 遗留与下一轮候选

1. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变（本轮亦未动）。
2. **sync-history 幂等**已双向确认：单测 `test_novel_full_flow_round34.py` s1–s5
   钉死全分支（登记/幂等/跳过异章与未完成任务/相对形态/损坏 manifest 409）；
   本轮活体二次、三次调用均 `{"synced": [], "revision": 2}`（§2.2）。
3. **慢供应商耗时基线（本轮实测）**：AMD / Gemma-4-31B-IT，9 阶段干净跑通
   任务时间 129.9 分钟（含 2 次 build、3 次 character 重试）；单次最小完成时间
   约 78 分钟（无重试路径）。**轮询/超时面建议**：免费档下阶段超时预算应按
   layer 分级（build/character 需 ≥40min，export ≤5min），本轮驱动器已按此配置
   （`TIMEOUT` 字典）。
4. **供应商质量面**：`stream_chunk_timeout` 已被 600s 打穿过一次（§2.0），
   根因在供应商侧分钟级停摆。后续若要压测稳定性，建议记录「每阶段失败率」
   而非只看总耗时。
5. **测试卫生纪律（B27 教训，建议纳入 code review checklist）**：新增走「写」
   分支的路由测试，必须 patch 该路由模块用到的每一个模块级路径常量
   （`_index` / `_manifest` / `_library_root` 等），不能只 patch `DATA_DIR`。
6. 推送：xs2 积压提交 15 个（R29 起 + 本轮 2 个），插件仓库 3 个——建议维护者
   择机推送触发 CI 全量核对。
7. `data/workspaces/wf-1|wf-drain|wf-resume|wf-wait` 与
   `xs2-novel-flywheel-*` 为引擎默认工作区（含历史任务数据），非 B26 家族，保留。
