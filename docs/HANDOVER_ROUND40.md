# DeterminFlow (xs2) 交接报告 — Round 40（维护轮：B26 家族机械化终局 + 供应商失败率画像）

> 本轮定位：R39 §6 三项候选全数落地——①契约 §6.1 常驻回归基线 R25 起首次
> 专项复跑（四层全绿、零未解释差异）；②「读端点建目录」静态防复发钉测
> （B26/B28 两轮同族缺陷的机械化终局，双变异咬合验证）；③供应商失败率画像
> （R38 §7.4 落地：聚合模块 + 只读端点 + 挖矿脚本 + 两次小规模实跑画像），
> 顺带发现并修复 **B31**（run 记录 completed_at 恒空 → 画像 wall_seconds
> 不可算）。
> 基线：`6d5c668`（R39 文档尾）→ 本轮 xs2 提交 3 个（见 §3），插件仓零提交。

## 1. 契约 §6.1 常驻回归基线复跑（候选 1）

| 层级 | 结果 | 与契约/基线差异 |
|---|---|---|
| L1 进程内 `test_humanware_routes.py` | **24 passed**（1.90s） | 无差异 |
| L2 活体 `test_humanware_e2e.py` | **17 passed / 0 skip**（R39 代码与 R40 重启后代码各跑一次，均 17/0） | 契约文本 15 条 = R24 B15 逻辑回归 +2 后的 17，无未解释差异；F5/F6/F7 版本探测全执行 |
| L3 名字面全域（workspace_manager / plugin_name_guard / marketplace_skill_id_guard / storage_name_audit） | **106 passed / 1 skipped** | skip=symlink（Low-IL 诚实 skip；High-IL 全量中真实执行） |
| L4 插件套件（CLI 本体行为） | **98 passed / 0 failed ×2**（插件子目录 + 仓库根双 CWD） | 无差异 |
| 存储名审计 | **[clean]** ×2（轮初 + 轮末） | 无差异 |

- 差异结论：**零未解释差异**。R25 起唯一结构性变化是 e2e 15→17（R24 B15
  逻辑回归，当时已文档化）。
- 活体服务探针（8021）：4/4 执行器 ready、degraded=false；B28 幻影探针
  404+零目录；真书 `r38-flow` 列文件 200/52 文件（与 R39 一致）；welcome
  工作区 `voice_file_exists=true`。
- **探针备忘**：真书探针必须带 `workspace=data/workspaces/books/r38-flow`
  ——相对 override 相对 **BASE_DIR**（仓库根）解析，不是相对 workspaces
  目录（本轮踩过后查 `resolve_workflow_workspace_path` 确认，非缺陷）。

## 2. 「读端点建目录」静态防复发检查（候选 2）

`tests/test_read_endpoints_static_guard.py`（3 条钉测，纯 stdlib AST，
不导入应用代码，双 IL 与 CI ubuntu/windows 均可运行）：

- **主断言**：扫描 `src/` 全部含 HTTP 路由装饰器的模块（实测 14 个、119 个
  GET 处理函数），任何 GET 处理链（含模块内顶层助手调用闭包）可达的
  `resolve_workflow_workspace` 调用点，create 实参必须解析为字面量 False。
  缺省（解析器缺省即 True）、字面量 True、非字面量（UNKNOWN 保守处理）
  一律判违规，违规信息带 `文件 GET 处理器 → 调用点:行号` 精确归因。
- **参数化助手传播**：`_console_root(..., create: bool = True)` 语义——
  助手体内 `create=create` 形参引用沿调用链传播求值，GET 链上必须显式
  字面量 False（novel_routes 406/957/1351 的写面缺省用法不在 GET 链，
  正确放行）。
- **防空转**：路由模块数 ≥13、GET 处理函数数 ≥60、resolver 调用点总数 ≥9
  （R40 基线实测 14/119/9）、B26/B28 三个关键助手存在性（`_console_root`
  缺省 True 语义、`_console_existing_root`、`_existing_workspace_root`）
  均钉死——重构改名让扫描静默变空会直接 fail。
- **跨模块锚点**：`task_queries.py` 两个 agent 工具底座调用点（B28）逐点
  钉字面量 False（恰好 2 处）。
- **变异咬合验证**（临时改坏 → 预期 fail → 还原，两例均抓到）：
  ①`workflow_routes.py:44` create=False→True → 3 个 GET 处理器归因失败；
  ②`get_library_usage` 的 `_console_root` 调用去掉 create=False → 经参数
  传播路径 1 处归因失败。还原后 3 passed——零误报 + 可咬合达成。
- **已知局限**（docstring 记录）：调用图只解析模块内顶层函数引用，跨模块
  导入的助手不在闭包内；类方法内调用点全树计点（计入审计与 task_queries
  钉测）但不入 GET 可达图（方法调用无法按名静态解析）。B26/B28 实际缺陷
  面均已钉死，超出现面时按 docstring 指引补钉。

## 3. 供应商失败率画像（候选 3）+ B31 修复

### B31：run 记录 completed_at 恒空（取证缺口，本轮发现本轮修）

- **现象**：实跑探针发现 run JSON `completed_at` 恒为 null——R38 实跑的
  run（`run-b8083dc1`）同样为 null，任务记录（task JSON）有时间戳，
  画像 `wall_seconds` 因此不可算。
- **根因**：`engine.py` 两条执行路径只给 `task.completed_at` 盖章，
  `run_record.completed_at` 从未赋值。
- **修复**：`_finalize_run_artifacts`（两条路径的收敛点）入口处终态盖章：
  `completed_at is None 且 status != "retry_waiting"` 时置 `_now_iso()`
  ——retry_waiting 是恢复中转而非终点，保持 None 诚实表达「未收尾」。
- **回归**：`test_engine_finalize_stamps_run_completed_at`（轻量引擎实例
  + monkeypatch `src.config.WORKFLOWS_DIR`，断言 completed/retry_waiting
  两态 + 落盘文件内容）；活体复跑证实新 run `wall_seconds=0.071`。

### 画像三件套

- **聚合模块** `src/workflow/run_profile.py`：纯函数
  `build_run_profile(node_executions, ...)`——每阶段（node）尝试数/成败/
  失败率/错误分类/逐尝试明细 + run 级 totals。错误分类为关键词启发式
  （http_5xx 含 530/524/502、timeout、stream_stall、connection、other），
  仅供压测参考。旧数据兼容：无 attempt_history 时以 attempt_count 计数、
  节点终态近似成败。
- **只读端点** `GET /api/workflows/{wf}/tasks/{task_id}/run-profile`：
  与 token-usage 同款纯文件读取模式（任务 JSON 取 run_id → runs/
  {run_id}.json → 纯函数聚合），不建目录不写状态（查询即建目录属
  B26/B28 同族，有 §2 静态钉测守卫 + 端点级「零新增路径」测试）。404
  三态：任务不存在 / 尚无运行记录 / 运行记录不存在。
- **挖矿脚本** `scripts/provider_failure_profile.py`：只读扫描
  `data/workflows/*/runs/run-*.json`，逐 run 画像 + 跨 run 按阶段汇总，
  支持 `--workflow/--limit/--json`。
- **单测** `tests/test_run_profile.py` 12 条：聚合五态（单尝试成功 /
  R38 重试形态 / 旧数据兼容 / 坏时间戳与坏条目 / 空 run）、分类六桶、
  B31 引擎盖章、端点 200/404 三态/零建目录。

### 实测画像数据（验收：小规模实跑 + 真实历史数据）

- **历史挖矿**（真实复现实测形态）：`xs2-novel-flywheel-character`
  `run-99b3bd1b` agent_deep 第 3 次尝试失败 **629.7s timeout**——即 R38
  §2.0 的 600s stream_chunk_timeout 打穿实录；分类 `{'timeout': 1}`；
  跨 run 汇总 agent_deep 26 尝试/1 失败（3.85%）。
- **小规模实跑**：r38-flow 上两次 export（R38 认定最便宜阶段，≤5min
  预算）：`task-4b75d8a1`/`run-738b7b19`（B31 前，30s 内 completed，
  1 尝试 0 失败，wall null）与 `task-377b5942`/`run-dfe789fd`（B31 后，
  wall **0.071s**）——两次均 30 秒内完成，端点与挖矿脚本均正确产出画像。
- 8021 服务本轮重启两次（R39 代码 → R40 代码 → B31 后代码），均为
  4/4 执行器 ready、degraded=false。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：静态守卫 | 3 passed（+ 变异咬合两例） |
| 定向：画像（聚合+端点+B31） | 12 passed |
| Low-IL 全量 | **1826 passed / 96 skipped / 0 failed**（98.41s） |
| High-IL 全量（权威） | **1911 passed / 11 skipped / 0 failed**（131.38s） |
| 插件套件（双 CWD） | **98 passed / 0 failed ×2** |
| 前端三连（零改动） | lint 0 problems；**447 passed / 0 fail**；build ✓ 5.59s |
| 存储名审计 ×2 | [clean] exit 0 |
| 索引污染复查 | 59 条，与 R39 完全一致（零新增） |
| 活体（8021，R40 最终代码） | 4/4 ready degraded=false；e2e 17/0；幻影 404+零目录；run-profile 200/404 语义 |

对账：Low 1811+3(守卫)+12(画像)=1826 ✓；High 1896+15=1911 ✓。
总用例 R39 口径 1907 → **1922**（High passed+skipped：1911+11）。

## 5. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | `c0cbf11` | §2 静态防复发钉测（B26/B28 终局） |
| xs2 | `db11c3b` | §3 画像三件套 + B31 run 记录终态盖章 |
| xs2 | 本文档提交 | 交接文档 + PROJECT_INFO R40 条目 |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性）；
新增任务/run 记录与 r38-flow 导出产物均为运行数据。

## 6. 运行数据记录

- 本轮**零清理**：索引 59 条零变化、无幻影目录产生（B26/B28 修复后首批
  实跑探针全程零残留，守卫体系首次完整伴随实跑验证）。
- 新增运行数据：export 任务×2（task-4b75d8a1 / task-377b5942）及其
  run 记录、r38-flow 工作区导出产物刷新——均合法写面。
- 8021 服务日志钉位 `data/system/test-probes/r40-8021-run*.log`。

## 7. 遗留风险与需人工确认事项

1. **推送**：xs2 积压 **23 个**提交（R29 起 + R39 4 个 + 本轮 3 个）、
   插件仓 4 个——需维护者授权推送触发 CI 全量核对（外向操作，未执行）。
2. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变；
   分别需容器环境、cargo 工具链、外部基础设施决策（T2 类）。
3. **`.env` 相对路径覆盖注释化已实际生效**：本轮两次服务重启均在无
   `DETERMINFLOW_DATA_DIR` 等覆盖下运行，默认 BASE_DIR/data 语义一切正常
   （R39 §5.3 的预期兑现）；维护者若要用非默认数据目录需改回绝对路径。
4. **画像 wall_seconds 对历史 run 为 null**：B31 只对新 run 生效，R38 及
   更早的 run 记录无 completed_at，挖矿脚本诚实显示 None——历史数据不可
   追补（只读纪律），压测画像以 B31 后的 run 为准。
5. **服务进程托管注意事项（运维）**：由 ZCode 后台 shell 直接启动的
   `run.py` 会在后台任务被回收时连带退出（本轮两次实测，无 traceback、
   静默消失）；须用 `powershell Start-Process -WindowStyle Hidden` 脱离
   会话启动。非仓库代码缺陷，记录于此供后续轮次参考。
6. **静态守卫的模块内局限**：见 §2 末——跨模块助手闭包与方法内调用点
   的覆盖边界已 docstring 化，出现新缺陷面时需按指引补钉。

## 8. 下一轮候选（优先前 3）

1. **前端画像可视化**（中等工作量）：任务详情页消费 run-profile 端点，
   渲染逐阶段尝试/失败/错误分类卡片——画像数据现在只有 API/脚本出口，
   没有界面出口；验收=真实任务页截图走查 + 组件测试。
2. **挖矿脚本周期化**（低风险，~30min）：把
   `provider_failure_profile.py` 的跨 run 汇总挂到文档化流程（如每轮
   收官固定跑 + 结果入交接），形成供应商失败率时间序列。
3. **run-profile 端点扩展**（低风险）：支持 `?run_id=` 查询任意历史
   run（当前仅任务最新 run），前端画像可视化（候选 1）会用到。

其余：推送（待授权）、updater 死通道（待 cargo）、POSIX（待环境）、
大陆下载加速（待基础设施决策）。

## 9. 本轮未实际运行

无。本轮全部结论均有实际命令/测试/探针/实跑输出支撑。
