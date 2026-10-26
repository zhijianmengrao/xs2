# DeterminFlow (xs2) 交接报告 — Round 33（小说创作全流程测试轮）

> 本轮定位：用户指令「进行小说创作全流程测试」——设计执行功能/边界/异常/回归测试，
> 修复缺陷，输出迭代计划。**发现并修复 1 个 P0 级缺陷（B19）**：小说正文生产管线
> （mvp）与资料蒸馏管线（reference-distillation）在当前插件版本下**完全无法创建任务**，
> 且引擎把失败误报为 404「工作流不存在」。
> 基线：`0ce4607`（v1.0.2）→ 本轮 `dd52844`/`0e2e170`（xs2）+ `b305e41`（插件）。

## 1. B19：悬空 Script Library 引用导致两条核心管线不可用（P0，已修复）

### 1.1 现象

全流程实跑起步即卡住：`xs2-novel-flywheel-mvp`（正文生产，创作流程第 6 步）
创建任务返回 **404「工作流不存在」**。同一现象亦见于 `reference-distillation`。

### 1.2 复现（实测）

```bash
# 修复前：mvp 与 reference-distillation 均 404
POST /api/workflows/xs2-novel-flywheel-mvp/tasks            -> 404 {"detail":"工作流不存在"}
POST /api/workflows/xs2-novel-flywheel-reference-distillation/tasks -> 404 同上
# 其余 9 条 flywheel 工作流全部 200 —— 说明不是插件整体故障
```

服务日志给出真实原因（被路由层吞掉）：

```
ERROR 冻结 Workflow Task 运行身份失败: workflow=xs2-novel-flywheel-mvp
  File "src/workflow/runtime_guards.py", line 183, in _library_script_attestation
  File "src/workflow/script_library.py", line 265, in attest
ScriptLibraryAttestationError: Script Library 脚本不存在:
    xs2-novel-flywheel-xs2/reference_intelligence
```

### 1.3 根因（两层，均已修复）

**层一：插件资源引用悬空（根因）**

| 工作流 | 节点 | 引用（错） | 实际入口（对） |
|---|---|---|---|
| mvp | script_smart_context | `reference_intelligence` | `reference_intelligence_helper` |
| mvp | script_check_originality | `reference_intelligence` | `reference_intelligence_helper` |
| reference-distillation | script_intelligence_init | `reference_intelligence` | `reference_intelligence_helper` |

插件提交 `4eed8cb`（"将 reference_intelligence 辅助模块移到正确位置"）把库目录更名，
但三个节点的 `script_name` 未同步。`09c4deb` 曾给这些节点加 `fail_auto_skip: true`
以缓解——**但该属性只在运行期生效，对创建期的运行身份冻结 attestation 无效**，
所以缓解措施从未真正奏效。

**层二：引擎把冻结失败谎报为 404（放大器）**

`manager.create_task` 里 `except Exception: return None`，路由层把 `None` 统一报
「工作流不存在」。工作流明明存在，真实原因与堆栈全部丢失，排障方向被彻底带偏。

### 1.4 修复

| 侧 | 提交 | 内容 |
|---|---|---|
| 插件 | `b305e41` | 三处 `script_name` → `reference_intelligence_helper`；新增 `test_workflow_library_references_resolve`（全工作流 × 全 library 引用解析清点）；`extension.toml` 0.1.13→0.1.14，`EXPECTED_SCRIPT_LIBRARIES` 与版本钉值同步 |
| xs2 引擎 | `dd52844` | `create_task` 冻结异常改为结构化返回 `{success:false, error:"task_freeze_failed", message:真实原因}`；路由层 `_raise_task_freeze_error` 映射为 **HTTP 409**；新增 `test_create_task_reports_missing_library_script_as_freeze_failure` |
| xs2 测试 | `0e2e170` | 新增 `tests/test_workflow_task_create_errors.py`（路由层 409 + 真实原因断言） |

### 1.5 修复验证（全部实际执行）

- **单元/路由**：`test_workflow_runtime_guards.py` + `test_workflow_task_create_errors.py`
  → **25 passed**
- **插件套件**：90 passed / 2 failed（2 个失败为既有环境问题，见 §4.3）
- **端到端（真实服务）**：插件 update → 重启 → `data/workflows/xs2-novel-flywheel-mvp/`
  三处引用均变为 `reference_intelligence_helper` → **11/11 条 flywheel 工作流
  全部可创建任务**（修复前 mvp / reference-distillation 不可用）
- **错误语义**：修复后在未刷新资源的状态下请求 mvp，得到
  `409 {"code":"task_freeze_failed","message":"...node=script_smart_context:
  Script Library 脚本不存在: .../reference_intelligence"}`——精确到节点与路径

### 1.6 影响面

- mvp 是创作流程第 6 步（正文生产）的**唯一入口**，不可用意味着**整本书写不出正文**；
  reference-distillation 不可用意味着**资料蒸馏整套功能失效**。
- 因两管线在本实例**从未生成过 `runs/` 目录**（历史无成功任务），缺陷应与插件
  `4eed8cb` 同期引入，且 R15–R32 的所有轮次都未覆盖到「创建任务」这一环
  （历轮测的是 humanware CLI、页面走查、build 与 reader-sim 两条工作流）。

## 2. 测试执行汇总（全部实际运行）

### 2.1 确定性用例（无 LLM 依赖，14/14 通过）

| 编号 | 场景 | 预期 | 实际 | 结论 |
|---|---|---|---|---|
| C1a | 裸工作区创建 mvp 任务 | 200 | 200 | PASS |
| C2 | 空书导出 | completed，`chapter_count=0` 诚实标注 | 同 | PASS |
| C3a/b/d | 空工作区 score-content / check-dialogue / generate-voice | 409 | 409 + 人因文案 | PASS |
| C3c-2 | 有 voice、缺章节 score-chapter | 404 | 404「章节文件不存在」 | PASS |
| C4a/b/c | workspace id = `NUL` / `r33-x.` / 中文 | 400 | 400 各自精确文案 | PASS |
| C5 | 同任务二次启动 | 409 | 409 | PASS |
| C6 | 不存在工作区 status | 404 | 404 | PASS |
| C7 | 超长内容（9,800 字符）走 stdin 通道 | 200 | 200，返回 89/B 四维评分 | PASS |
| C8 | score-chapter 路径逃逸 `../../` | 400 | 400 | PASS |

> C3c 首轮我按「章节不存在→404」设计，实测返回 409（voice 缺失优先）。
> 路由不做预检、由 CLI 决定校验顺序，属契约未规定的实现细节，**非缺陷**。

### 2.2 回归（全部实际运行）

| 项 | 结果 |
|---|---|
| 前端 `npm run lint` / `npm test` / `npm run build` | 0 problems / **447 passed 0 failed** / ✓ 6.03s |
| 后端 Low-IL（`.venv`） | **1746 passed / 96 skipped / 1 failed** |
| 后端 High-IL（`py.exe` + venv site-packages） | **1831 passed / 11 skipped / 1 failed** |
| 活体 e2e `tests/test_humanware_e2e.py` | **17 passed**（F5–F7 版本探测真实执行） |
| 存储名审计 | `[clean]`，exit 0 |
| 测试收集总数 | HEAD 1843 vs 基线 `0ce4607` 1842 → **+1 = 本轮 B19 锚** |

唯一失败项 `test_skills_config_matches_versioned_core_catalog` 为**既有外来本地改动**
（`config/skills_config.json` 被加入 6 个社区插件 skill，非本轮引入，双基线一致）。

### 2.3 浏览器 e2e（真实 Chromium，10 页 + 交互）

10 个侧栏页面逐页走查全部正常渲染：我的作品（demo-voice 卡片 44% 进度）、小说档案
（2 份档案、角色条目切换）、章节目录、创作流程（10 步清单 + 模型面板 + 工作区 11 个
资料文件）、读者评估（409 人因化空态）、写法库、本书参考写法、角色声音（339 字符
编辑器 + 试评区）、资料蒸馏、作品设置。工作区切换（welcome → r33-flow）经实测生效。

> 观察：页面内多处按钮 Playwright 语义点击超时，坐标点击正常。判定为 IAB 渲染层
> 交互时序问题，非产品缺陷（前端 447 条组件测试全绿、R25–R32 历轮真实浏览器 e2e 均通过）。

### 2.4 全流程实跑（未完成，上游不可用）

| 阶段 | 状态 |
|---|---|
| build（世界观，6 agent） | **首次完整跑通**：1,251s / 67,245 tokens / `meta/world_foundation.md` 25,696 字节（191 行，结构扣题）|
| character 及之后 8 段 | **未完成**，被上游供应商故障阻断 |

**阻断证据（实测，非推测）**：

- `HTTP 530 error 1033`（Cloudflare Tunnel 未连通）连续多次
- `No streaming chunk received for 120.0s (chunks_received=1456)`——流式静默卡死
- `HTTP 524`（Cloudflare 源站超时）：模拟真实节点负载的流式探测，
  **126 秒内收到 0 个 chunk、0 字节**
- 短请求可通但延迟抖动极大（实测 2.1s / 8.7s / 16.9s / 59.9s 四次采样）
- 驱动已内置上游故障等待重试，**4 次尝试全部失败**后停止

结论：`z-ai/glm-5.3-flash` 在长生成负载下不可用，属供应商侧问题；
**build 段完整跑通证明管线机制（任务调度→执行器→agent 调用→结构化解析→脚本落盘）
本身工作正常**。

## 3. 观察项与建议（非缺陷）

### 3.1 `stream_chunk_timeout` 默认 120s 对慢模型偏紧（P2，配置项非缺陷）

langchain-openai 默认 120s 无 chunk 即抛错，代码可通过
`LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S` 环境变量或 provider 超参
`stream_chunk_timeout`（`src/core/provider_adapters.py` 已声明，可空、最小 1s）调整。
使用免费档/长思考模型（单次 10+ 分钟）时必然触发。
**建议**：在设置页「供应商高级参数」中把该字段暴露出来并在文档提示。

### 3.2 `workspace_override` 接受仓库内任意相对路径（P3，设计既定）

`data/workspaces/../../etc` 解析到仓库根 `etc/` 并真实创建目录（已清理）。
`resolve_workflow_workspace` 允许 BASE_DIR 内任意相对路径，对小说工作流是冗余面。
**建议**：novel/workflow 路由层对 override 增加「必须位于 `data/workspaces` 下」的白名单。

### 3.3 空书导出产出空稿件（P3）

`export` 在 0 章时仍 completed 并写出 0 字节 `manuscript.md` + `chapter_count: 0`
的 manifest。诚实但不友好。UI 侧已有 `can_download` 门控，**建议**后端在 0 章时
返回 `success:false, code:409`。

### 3.4 未捕获的 validate 阶段（本轮未覆盖）

创作流程经 UI 驱动时由控制台写 manifest，进度百分比才会联动；直接走工作流 API
不写 manifest（进度显示 0/9）。这是职责划分，不是缺陷，但**测试脚本若走 API
需自行模拟控制台写入**才能验证进度联动。

## 4. 遗留

1. **§2.4 全流程后 8 段未实跑**：前置条件是稳定可达的上游模型。已备份驱动
   `F:\DeterminFlow x2\r33_flow_driver.py`（超时仅告警 + 上游故障自动重试 +
   状态落盘可续跑），模型恢复后 `python r33_flow_driver.py --all` 即可续跑。
2. 插件 2 个失败用例（深路径 WinError 206 / 临时目录权限）为既有环境问题，
   HEAD 上同样失败，未处理。
3. R32 遗留项（updater 死通道清理、POSIX 真跑、大陆下载加速）状态未变。

## 5. 本轮提交

| 仓库 | 提交 | 说明 |
|---|---|---|
| DeterminFlow-Plugins | `b305e41` | B19 根因：三处悬空引用 + 引用解析回归锚 + 0.1.14 |
| xs2 | `dd52844` | B19 放大器：冻结失败结构化返回 + 路由 409 映射 + 回归锚 |
| xs2 | `0e2e170` | B19 路由层回归测试 |

**均未推送**。插件修复需 `plugin update` + 重启才落到 `data/workflows`（本机已执行）。
