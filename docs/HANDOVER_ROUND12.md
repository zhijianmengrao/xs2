# DeterminFlow (xs2) 交接报告 — Round 12

> 生成时间：2026-10-23
> 项目路径：F:/DeterminFlow x2/xs2
> 分支：main（基线提交 4854d47「添加角色声音功能前端组件和后端路由」）
> 文档编码：UTF-8
> 重要说明：与 R11 相同，本轮代码改动仍在未提交的工作区中；R11 的 52 个已跟踪修改 + 8 个未跟踪文件依旧未提交，接收者需自行比对后决定提交粒度。

---

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| 基线复现 | 全量 pytest：1514 passed / 0 failed / 36 skipped（120.95s），与 PROJECT_INFO.md 一致 |
| 修复后全量回归 | **1523 passed / 0 failed / 36 skipped**（119.77s），新增 9 个 humanware 用例全部通过 |
| 前端 | lint 0 errors（25 个预存 warning）/ test 全过 / build 成功 |
| OpenAPI 重复 operationId | 修复前 1 处重复（GET/HEAD 双方法共享 id）+ UserWarning；修复后 277 个 operationId 0 重复、警告消失 |
| humanware 角色声音功能 | 发现整个功能后端不可用（CLI 脚本不存在）；本轮将其从「误导性 500」修复为「明确业务 501」，并修复 404 吞 500、事件循环阻塞、路径穿越、前端保存指向不存在路由 4 类问题；**端到端启用依赖插件补发 humanware_helper 脚本库（下一轮）** |
| 服务状态 | 8021 已重启并在监听；/api/system/status、/api/plugins、/docs 均 200；4 执行器 ready；双插件 running |

## 2. 测试数据对照

| 指标 | R11 基线 | 本轮首轮（未改动） | 本轮终轮（修复后） |
|---|---|---|---|
| pytest 日志 | .pytest-r11.log | .pytest-r12.log | .pytest-r12b.log |
| passed | 1514 | 1514 | **1523** |
| failed | 0 | 0 | 0 |
| skipped | 36 | 36 | 36 |
| warnings | — | 1（Duplicate Operation ID） | **0** |
| 耗时 | 116.37s | 120.95s | 119.77s |
| 前端 | — | lint 0err/test 过/build 过 | lint 0err/build 过（同） |

换算验证：1514 + 36 = 1550；1523 + 36 = 1559（= 1550 + 9 新增用例）。新增用例全部来自 tests/test_humanware_routes.py（9 条）。

## 3. 本轮发现与修复的 Bug

### B12-1（中）重复 OpenAPI operationId（GET/HEAD 双方法）

- **现象**：`app.openapi()` 时 FastAPI 警告 `Duplicate Operation ID download_novel_manuscript_api_novel_console_export_download_get for function download_novel_manuscript`；`/openapi.json` 中 `/api/novel-console/export/download` 的 get/head 两个 operation 共用同一个 operationId。
- **复现**：`app.openapi()`；或在 pytest 中任何构建全量 OpenAPI 的用例（test_extension_host.py::test_core_app_has_no_product_extension_routes 触发）。
- **根因**：`@router.api_route("/export/download", methods=["GET","HEAD"])` 注册的**单个 APIRoute** 在构造时按 `generate_unique_id` 用 `list(methods)[0]`（GET）算出一个 `unique_id`；OpenAPI 生成时对 route.methods 的每个方法各产出一个 operation，二者共享同一 operationId → 第二个（HEAD）触发重复警告。
- **影响**：OpenAPI 文档/生成的客户端以 operationId 为键时会冲突；/docs 启动告警噪音。功能性无直接影响（FastAPI 仍按路径+方法路由）。
- **修复**：拆分 `@router.get` + `@router.head` 为两个独立函数（`download_novel_manuscript` / `head_novel_manuscript`），共用 `_manuscript_target` / `_manuscript_response` 辅助函数。HEAD 返回 `None`（无 body），行为兼容（HEAD 本就无 body）。
- **修改**：`src/web/novel_routes.py`（610-621 行附近重构为 3 个函数）。
- **验证**：OpenAPI 277 个 operationId 0 重复；GET/HEAD operationId 各自唯一；`test_humanware_routes.py::OpenApiOperationIdUniquenessTests` 固化。
- **风险**：低。路由路径、参数、返回类型不变；HEAD 不传 body（符合 HTTP 语义）。

### B12-2（低 → 判定非缺陷，降级为部署建议）main agent model 为 null 启动回退告警（R11-6 延续）

- **现象**：服务日志 `WARNING: 未找到 agents_config.json main agent 的 model 配置，回退到: agnes:agnes-2.5-flash`。
- **根因分析**：`config/agents_config.json` 中 main 及其他 agent 的 `"model": null` 是**仓库默认模板**语义 = “继承 models_config.json 全局默认（第一个可用模型）”。`tests/test_model_manager_secrets.py::test_default_agent_definitions_inherit_the_main_model` 明确断言 `agents["main"]["model"] is None`——这是项目既定契约。
- **尝试与还原**：曾将 main.model 改为 `"agnes:agnes-2.5-flash"`，随即导致上述测试失败；已还原 `config/agents_config.json`（git diff 为空）。**结论：不改版本库默认配置；若部署环境要显式指定，应在设置页选择模型（写入 agents_config.json 为本地部署决策）或接受回退行为。**
- **修改**：无。
- **风险**：无（未改任何文件）。

### B12-3（高）humanware 角色声音功能全部端点 500，且存在 4 类缺陷

- **现象**：`/api/humanware/*` 全部返回 500；前端「角色声音」页面所有操作失败。
- **复现**：`GET /api/humanware/status/welcome`（或浏览器打开角色声音页）。
- **根因分析**（逐条验证）：
  1. **CLI 脚本不存在**：`_get_humanware_cli_path()` 硬编码 `data/plugins/runtime-resources/xs2-novel-flywheel/script-libraries/0/xs2-novel-flywheel-xs2/humanware_helper/humanware_cli.py`；已确认该路径不存在，且递归搜索**插件源仓库**（`F:\DeterminFlow x2\DeterminFlow-Plugins`，HEAD 4eed8cb）、插件 checkout、runtime-resources 均无 `humanware_helper`。→ 任何调用 CLI 的端点（generate/score/check）必然 500「Humanware CLI 脚本不存在」。
  2. **async 端点内阻塞调用**：所有 handler 是 `async def` 却在事件循环里执行 `subprocess.run(...)`（无 timeout）与文件 IO → 一个评分请求会**阻塞整个 uvicorn 事件循环**（聊天、执行器事件桥、所有 API 全部冻结直至 CLI 返回）。
  3. **404 被吞成 500**：`get_voice_file` / `get_humanware_status` 的 `except Exception` 会捕获 `_get_workspace_root` 抛出的 `HTTPException(404)` 并转成 500 → HTTP 语义错误。
  4. **workspace_id 路径穿越**：`_get_workspace_root` 直接 `books / workspace_id` 无任何校验，`../..` 等可越出 `data/workspaces/books`。
- **影响**：功能不可用；错误状态码误导排障；事件循环阻塞影响全站；路径穿越为本地 API 的安全缺口。
- **修复**（`src/web/humanware_routes.py` 全面重写，保持 API 路径与请求/响应契约不变）：
  1. `_get_humanware_cli_path` 不存在时抛 **HTTPException(501)**——语义为「功能未部署」，区别于 500 内部错误；detail 明确说明当前插件版本未包含 humanware_helper。
  2. 所有 CLI/文件 IO 下沉：`_run_humanware_command_blocking`（含 `subprocess.run(timeout=120)` + `asyncio.to_thread` 包装）在线程池执行；`_CLI_SEMAPHORE = asyncio.Semaphore(4)` 限制并发拉起解释器；voice-file 写文件用 `asyncio.Lock` 串行化。
  3. GET 端点改为先捕获 `HTTPException` 单独 `raise`，其余异常才转 500 → 不存在的 workspace 返回 **404**。
  4. `_get_workspace_root` 增加白名单校验（`^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$`）+ `resolve()` 后必须仍位于 books 根下；同时兼容前端传入的完整相对路径 `data/workspaces/books/<id>`（提取 id 段）。
  5. 请求模型补充长度上限（workspace_id ≤200、dialogue ≤200k、content ≤10M）——防御超大 body。
- **验证**：9 个新测试用例（tests/test_humanware_routes.py）+ 运行时调用（见第 5 节）。
- **风险**：低。API 路径与请求/响应字段未变；501 是新引入但更正确的状态码；线程池语义与原先「直接在事件循环跑」相比仅影响并发表现（只改善）。**注意：端到端启用需插件补发 humanware_helper 脚本库（下一轮，跨仓库）。**

### B12-4（高）前端「角色声音」保存指向不存在的路由 + workspaceId 传参格式不匹配

- **现象**：点击「保存」永远失败（toast 提示保存失败）；「从角色档案生成」按钮在无 profiles 时禁用逻辑正常但生成必失败。
- **复现**：打开角色声音页 → 编辑 → 保存。
- **根因分析**：
  1. `CharacterVoiceEditor.tsx` 保存调用 `POST /api/novel/${workspaceId}/file`——**全应用不存在该路由**（novel-console 前缀为 `/api/novel-console`，且无 `/file` 端点；`write_text` 只允许 `references/` 与 `meta/console-` 前缀）。
  2. 页面传入的 `workspaceId` 实为完整相对路径 `data/workspaces/books/welcome`，而 humanware API 期望纯 id（`books/{id}`）；直接放入 URL 路径参数会被拆段 → 404。
- **修复**：
  - 后端新增 `PUT /api/humanware/voice-file/{workspace_id}`（保存 `meta/character_voice.md`，UTF-8，带写锁与校验）。
  - 前端保存改为调用该端点；并在组件内将 workspaceId 归一化为最后一段（`split('/').filter(Boolean).pop()`），status/voice-file/generate/save 全部改用归一化 id。
- **修改**：`web/src/components/CharacterVoiceEditor.tsx`、`src/web/humanware_routes.py`。
- **验证**：运行时装验证（PUT→200、GET 读回、status 更新）；前端 build 通过；测试用例 `test_save_then_read_voice_file_roundtrip`、`test_full_relative_path_workspace_also_accepted`。
- **风险**：低。后端新增端点不影响既有契约；前端改动仅限保存 URL 与 id 归一化。

## 4. 变更清单（本轮新增/修改）

| 文件 | 变更 | 对应 Bug |
|---|---|---|
| `src/web/novel_routes.py` | GET/HEAD 拆分 + 共享辅助函数 | B12-1 |
| `src/web/humanware_routes.py` | 重写：501/超时/线程池/信号量/404/穿越防护/id 归一化/保存端点 | B12-3、B12-4 |
| `web/src/components/CharacterVoiceEditor.tsx` | 保存改调 humanware 端点 + workspaceId 归一化 | B12-4 |
| `tests/test_humanware_routes.py`（新） | 9 个回归用例 | B12-1/3/4 |

未改动：`config/agents_config.json`（B12-2 尝试后还原，git diff 为空）。

## 5. 测试用例与执行结果

### 5.1 全量回归（修复后）

```
.\.venv\Scripts\python.exe -m pytest -q --tb=short
=> 1523 passed, 36 skipped in 119.77s (PYTEST_EXIT=0)
36 skipped 全部为环境限制（Windows symlink 特权 23 / macOS 签名 7 / POSIX fcntl 2 / Unix 进程组与进程树 2 / 同源重复 2），同 R11。
```

### 5.2 新增回归测试 tests/test_humanware_routes.py（9 条，全部通过）

| 编号 | 用例 | 验证点 |
|---|---|---|
| T1 | test_status_missing_workspace_returns_404_not_500 | 不存在的 workspace → 404（防 404 吞 500） |
| T2 | test_voice_file_missing_workspace_returns_404_not_500 | 同上（GET voice-file） |
| T3 | test_traversal_workspace_id_rejected | URL 层 400/404 均安全；body 层 `..`、`../..`、`a/b`、`..\..`、`../../../config`、`.`、`%41` → **400** |
| T4 | test_save_then_read_voice_file_roundtrip | PUT 保存 → GET 读回 → status 显示 voice_file_exists/humanware_enabled/character_count=1 |
| T5 | test_full_relative_path_workspace_also_accepted | 完整相对路径作为 body workspace_id 可用；CLI 缺失 → 501 |
| T6 | test_generate_reports_501_when_cli_absent | CLI 不存在 → **501**（业务未就绪）而非 500 |
| T7 | test_generate_voice_file_success | 假 CLI 注入后 generate-voice 正常 → 200 + character_count=3 |
| T8 | test_score_content_propagates_business_result | score-text 业务结果透传（total_score=88） |
| T9 | test_no_duplicate_operation_ids_in_openapi | 全应用 OpenAPI operationId 唯一；download GET/HEAD id 不同（B12-1 固化） |

### 5.3 运行时验证（服务重启后，8021）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 1 | GET /api/humanware/status/echo-test（临时空工作区） | 200 `{voice_file_exists:false, humanware_enabled:false, character_count:0}` |
| 2 | GET /api/humanware/voice-file/echo-test | 200 `{status:"not_found", content:null}` |
| 3 | PUT /api/humanware/voice-file/echo-test（保存内容） | 200 `{status:"success"}`，文件落盘 UTF-8 |
| 4 | GET /api/humanware/voice-file/echo-test | 200 content 读回一致 |
| 5 | GET /api/humanware/status/echo-test | 200 `voice_file_exists:true, humanware_enabled:true, character_count:1` |
| 6 | POST /api/humanware/generate-voice-file | **501**（CLI 未部署，detail 明确） |
| 7 | GET /api/humanware/status/ghost | **404**（原为 500） |
| 8 | POST workspace_id=`../..` | **400**（穿越防护） |
| 9 | HEAD /api/novel-console/export/download（无成品） | 404（HEAD 路由存在且正常） |
| 10 | GET /openapi.json | 277 个 operationId，0 重复 |

临时工作区 echo-test 已在验证后删除，未污染 data 目录。服务验证后保持运行。

## 6. 优化建议与实施结果

| # | 问题 | 优化 | 状态 | 风险 | 优先级 |
|---|---|---|---|---|---|
| O1 | humanware CLI 经 asyncio.to_thread 执行，阻塞问题消除 | 已实施（B12-3） | 中收益 | 低 | 已做 |
| O2 | CLI 缺失时 500 → 501 明确「功能未部署」 | 已实施 | 排障收益 | 低 | 已做 |
| O3 | workspace_id 白名单 + resolve 包含校验 | 已实施 | 安全收益 | 低 | 已做 |
| O4 | 请求模型长度上限（防御超大 body） | 已实施 | 安全收益 | 低 | 已做 |
| O5 | 建议：conftest 跳过机制改为统一装饰器（R11-2 延续） | 未做（中改动，风险中） | 可维护性 | 中 | 下一轮 |
| O6 | 建议：前端 25 个 lint warning 清理 | 未做（均为预存于 settings/components 的 hooks warning，与本轮无关） | 可维护性 | 低 | 下一轮 |
| O7 | 建议：`.pytest-r12*.log` 已由 `.gitignore` 的 `_pytest*.log` 覆盖 | 已验证 | 防误提交 | — | 已确认 |

## 7. 风险与遗留问题

| 编号 | 问题 | 影响 | 状态 |
|---|---|---|---|
| R12-1 | **humanware 端到端不可用**：插件 0.1.13（4eed8cb）未提供 `humanware_helper` 脚本库；generate/score/check 均 501 | 角色声音生成、人味评分后端能力缺失（前端 UI 已就绪、读/写/状态端点已可用） | 需在 DeterminFlow-Plugins 仓库补发脚本库 + 重新 prepare（下一轮） |
| R12-2 | main agent model=null 回退告警（B12-2） | 仅日志噪音，行为正确（回退到唯一 provider 第一个模型） | 部署决策，不在版本库改 |
| R12-3 | 36 条 skipped（symlink 23/macOS 7/POSIX 2/Unix 2） | 逃逸防护与 macOS 打包未在本机验证 | 环境限制 |
| R12-4 | 工作区 52 个已跟踪修改 + 9 个未跟踪文件（含本轮 4 个）未提交 | 交接状态不稳固 | 建议下一轮分批提交 |
| R12-5 | conftest 跳过策略依赖测试函数体文本匹配（R11-2） | 可能漏判间接 symlink 用例 | 下一轮收敛为装饰器 |
| R12-6 | docs 残留 HANDOVER_ROUND10.md.bak-20261022 | 目录冗余 | 确认后删除 |
| R12-7 | 服务日志中文：本轮 `_svc_out.log`/job 输出中文正常（UTF-8）；先前乱码为读取编码不符（应 `-Encoding UTF8`） | 排障误导 | 已在本文档注明读取方式 |
| R12-8 | waves：`resolve_workflow_workspace(override=...)` 对相对路径会解析到项目根（B12-4 测试中观察到） | 仅影响调用方传参习惯（前端传完整路径无此问题） | 记录观察，不改 |

## 8. 下一轮迭代计划（按优先级）

1. **[P0] 补全 humanware_helper 脚本库（跨仓库，DeterminFlow-Plugins）**：实现 `humanware_cli.py`（`generate-voice` / `analyze-voice` / `score-text` / `score-chapter` / `check-dialogue`，输出约定的 JSON 契约），发布插件版本并重新 prepare runtime-resources；随后对本轮 501 端点做端到端验证（生成→读回→评分）。
   工作量：1.5–3 人日（含契约对齐与测试）；验收：上述 5 个命令在 8021 经 API 调用全部 200，且单元测试 mock CLI 的 9 条用例（T7/T8）照常通过。
2. **[P1] 收敛 conftest 跳过机制**：以统一 `@skip_without_symlink` 等装饰器替代函数体文本扫描（R11-2/R12-5）。
   工作量：0.5 人日；验收：36 skipped 分布不变；`pytest --collect-only` 能稳定复现；间接创建 symlink 的用例不再可能漏判。
3. **[P1] 差分提交工作区**：配置（7）/后端（8+2 本轮）/测试（19+1）/前端（18+1）/文档 分批提交；删 HANDOVER_ROUND10.md.bak-20261022。
   工作量：0.5 人日；验收：提交历史清晰可回滚，.pytest*.log 不入库。
4. **[P2] 前端 lint warning 清理**：25 个（多为 hooks 依赖数组），逐个补依赖或提取变量。
   工作量：0.5–1 人日；验收：lint 0 warnings，npm test + build 通过。
5. **[P2] 环境预检复跑**：在启用开发者模式的管理员会话或 WSL/Linux 复跑 23 条 symlink 用例、macOS 机器跑 7 条签名用例。
   工作量：环境依赖；验收：逃逸防护断言真实执行并全绿。

## 9. 命令记录（本轮）

```
git status --short / git log --oneline -5（交接基线复核）
Get-NetTCPConnection -LocalPort 8021（服务探活）→ 停止服务树（taskkill /T /F）
.\.venv\Scripts\python.exe -m pytest -q --tb=short → Tee .pytest-r12.log（1514/0/36）
cd web && npm.cmd run lint / npm.cmd test / npm.cmd run build（全过）
python -c 复现 duplicate operationId + 修复后复验（277 ops 0 dup）
git -C DeterminFlow-Plugins log/cat-file 验证 4eed8cb 与 humanware_helper 缺失（三层递归搜索）
python setup_plugins.py（幂等：1/1 已就绪，EXIT=0）
.\.venv\Scripts\python.exe -m pytest tests/test_humanware_routes.py -q（9 passed）
全量回归 .pytest-r12b.log（1523/0/36）
后台重启 run.py → 8021 冒烟 + humanware/novel/openapi 运行时验证（第 5.3 节）
```

## 10. 交接声明

- 本文档所有结论均来自命令输出与文件/仓库内容核实，无臆造。
- 本轮修改文件：`src/web/novel_routes.py`、`src/web/humanware_routes.py`、`web/src/components/CharacterVoiceEditor.tsx`、`tests/test_humanware_routes.py`（新增）。全部仍在未提交状态。
- 本轮未实施破坏性操作；临时测试工作区已清理（echo-test 删除）；服务在 8021 保持运行。
- 最重要的交接信息：**humanware 功能的后端 500 迷雾已澄清——根因是插件未随附 humanware_helper 脚本库；读/写/状态端点已修复可用，生成/评分端点返回明确的 501，端到端启用需要下一轮在插件仓库补发该脚本库。**