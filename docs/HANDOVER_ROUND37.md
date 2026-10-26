# DeterminFlow (xs2) 交接报告 — Round 37（维护轮：R36 §6 候选落地）

> 本轮定位：R36 §6 三项候选全部处置——**B24**（novel 面 workspace 覆盖白名单，
> R33 §3.2）、**B25**（空书导出拒缩，R33 §3.3）、**stream_chunk_timeout 收口**
> （R33 §3.1，核实后为文档缺口）；外加仓库根残留治理（%TEMP% 回落老问题）。
> 基线：`e51c037`（R36 文档尾）→ 本轮 xs2 三提交 + 插件 `a101515`（0.1.16）。

## 1. B24：novel 面 workspace 覆盖白名单（R33 §3.2 收口）

### 1.1 现象与活体复现（修复前，8021 实测）

```
GET /api/novel-console/progress?workflow_id=xs2-novel-flywheel
    &workspace=data/workspaces/../../r37-escape-probe
→ HTTP 200（把逃逸位置谎报成一本 0% 的书）+ 仓库根出现 r37-escape-probe/ 目录
```

相对 override 在核心解析器里只受「不得穿越出 BASE_DIR」约束，`BASE_DIR` 内任意
位置都被放行并真实 `mkdir`。仓库根的 `foo/`、`echo-test/`、空壳 `demo-voice/`
即历轮该面留下的产物。

### 1.2 修复（两层，语义兼容优先）

| 层 | 文件 | 内容 |
|---|---|---|
| 核心 | `src/core/workspace_manager.py` | 相对 override 在既有「穿越出 BASE_DIR 回退」之后追加「必须落在 `BASE_DIR/data` 之内」，越界**回退默认路径 + WARNING**（与同函数既有守卫同款语义，不抛异常，engine/main_task_creation 无需改动） |
| console | `src/web/novel_routes.py` | 新增 `_console_root()`：白名单外的 workspace 覆盖一律 **400 明确拒因**（`workspace 必须位于 data/workspaces 之下：…`）；27 个解析点全部收编，另 2 处任务记录比对点（938/1332）有意保留原生解析以兼容历史相对形态 |

**为什么不是 R33 设想的「必须位于 data/workspaces」**：既有钉值测试与在用面
要求更宽——绝对 override 允许 DATA_DIR/BASE_DIR（`test_absolute_override_
allows_external_data_dir` 钉死插件批处理面 `data/plugins/<plugin>/data/...`；
相对 `data/book/<uuid>` 形态也被钉死）。收紧到 `BASE_DIR/data` 覆盖全部观测
污染形态（`foo`、`data/workspaces/../../<name>`）且零钉值破坏；console 面
（书只会写在 data/workspaces 下）才用严格 400 白名单。

### 1.3 验证（全部实际执行）

- 定向回归：B24 涉及的 8 个测试文件 **106 passed / 1 skipped**（新增
  `tests/test_workspace_override_whitelist.py` 9 条：核心层 5 + console 层 4）。
- 活体（修复后 8021）：三种逃逸形态全部 **400 + 拒因**、仓库根零新建目录；
  合法书路径 200；真书 r33-flow 进度 100% 不受影响。
- 既有钉值保持：`test_absolute_override_*`、`test_pure_workspace_resolver...`
  （data/book 形态）不改一行通过。
- 测试夹具同步（4 处）：console 面白名单锚 `WORKFLOW_WORKSPACES_DIR`，
  `test_windows_path_guard`（fixture + R18 三用例）、`test_novel_chapters`、
  `test_novel_chapter_removal`、`test_novel_library_deletion`、
  `test_novel_project_state` 补该 patch（临时书目录必须落在被补丁根之下）。

## 2. B25：空书导出拒缩（R33 §3.3 收口，插件 0.1.16）

### 2.1 现象与活体复现（修复前，8021 实测）

新建探针书 `data/workspaces/books/r37-export-probe`（0 章）→ 启动 export 任务
→ **completed**，写出 **0 字节** `export/manuscript.md` + `chapter_count: 0`
manifest。`can_download` 门控（`novel_progress.py:63` 只看 manuscript.md 是否
存在）随即放行——用户可下载到一份空成品。

### 2.2 修复（插件仓库 `a101515`）

`resources/script-library/xs2/manuscript_export/manuscript_export.py`：非空
章节为零时抛 `EmptyManuscriptError`，不写任何产物；CLI 打印中文拒因到 stderr
并以**退出码 2** 结束——引擎把 stderr 首行作为任务错误透出（`script.py`
`exit_code != 0 → failed`），用户在任务上直接看到「导出终止：没有可导出的
章节…」。`extension.toml` 0.1.15→0.1.16 + 三处钉值同步；新增
`tests/test_manuscript_export.py` 4 条。

### 2.3 验证（全部实际执行）

- 插件套件（xs2 根目录口径）**98 passed / 0 failed**（94 + 4）。注意：从插件
  目录本地跑会有 2 个既有环境失败（深路径 WinError 206 / %TEMP% 回落，R33 §4
  在案）——R36 口径即从 xs2 根跑。
- 运行时资源刷新：服务进程 Low-IL 不可走 git 传输，仍按 R36 §2 方法——
  High-IL 解释器进程外 `PluginStore.update`（checkout 前进至 `a101515`）→
  重启 8021 → 资源重建。
- 活体双相（修复后 8021）：空书导出 **failed** + 拒因透出、零产物写出 ✓；
  补 1 章后导出 **completed**、manuscript 含正文、manifest `chapter_count: 1`
  ✓（正常路径无回归）。探针书验证后经 `DELETE /projects` 删除。

## 3. stream_chunk_timeout 收口（R33 §3.1：核实结论为「已暴露」，补文档）

逐层核实（非臆断）：R33 建议的「设置页暴露」**在 Agent 级已经成立**——
- 后端：`provider_adapters.py` 的 `MODEL_PARAM_FIELDS` 自上游同步 `96bf0ef`
  起即含该字段（type number、nullable、min 1、label「流式分块超时（秒）」），
  全部 openai 系适配器经 `_finalize_openai_request` 校验后进 `client_kwargs`；
  anthropic 有意不含。
- 前端：编排页 Agent 编辑器 `ModelParamsEditor` 对 schema 全动态渲染，number+
  nullable 字段呈现为「留空=自动」输入框（`AgentDefinitionEditor.tsx:375`）。
- 测试：转发与拒绝语义已由 `tests/test_llm_client_params.py` 钉死。
- 全局兜底：`LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S` 环境变量在安装的
  langchain-openai 源码中实证存在（`base.py:884` 默认 120.0s，负值禁用）。
- **本轮动作**：`.env.example` 新增注释条目（默认 120s 对免费档/长思考模型
  偏紧的说明 + 两处配置途径）。不改代码——把它再搬进供应商级 hyperparams
  反而违背「模型参数归 Agent 级」的既有分层（`model_manager.py:38`）。

## 4. 仓库根残留治理（%TEMP% 回落，PROJECT_INFO 注意事项 8）

- `tests/conftest.py` 两个探针目录（symlink/git-transport）显式 `dir=` 钉到
  `data/system/test-probes/`（与 R21 executor-runtimes 同款）；git-transport
  探针清理从 `rmtree(ignore_errors=True)`（遇 git 只读 pack 文件静默跳过——
  41 个残留的直接原因）改为解只读重试的 `_rmtree_force`（兼容 3.11 onerror /
  3.12+ onexc）。
- 清理历史残留：`git-transport-probe-*` ×41、`pip-*` ×13、`pytest-of-wenbo/`、
  `foo/`、`echo-test/`、`xs2-fullrepro-*`、空壳 `demo-voice/`——仓库根回归
  纯净（仅剩项目目录）。
- 插件仓库 `.gitignore` 增加 `/pytest-of-*/`（R36 §6 遗留项 4 闭合）。

## 5. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 收编前基线复验（Low-IL 全量） | **1788 passed / 96 skipped / 0 failed**（93.84s，= R36 终态） |
| 定向：B24 涉及 8 文件 | **106 passed / 1 skipped**（含新增 9 条回归） |
| 定向：插件套件（xs2 根口径） | **98 passed / 0 failed**（94 + 4 新增） |
| Low-IL 终态全量 | **1797 passed / 96 skipped / 0 failed**（94.92s；对账 1788+9 ✓，服务在跑故活体 e2e 17 条真实执行） |
| High-IL 终态（权威） | **1882 passed / 11 skipped / 0 failed**（110.13s；对账 Low 1797 + 85 = 1882 ✓） |
| 前端三连 | lint 0 problems；**8 组 447 passed / 0 fail**（前端零改动，与 R36 完全一致）；build ✓ 5.66s |
| 存储名审计 | `[clean]` exit 0 |
| B24 活体 | 三种逃逸形态 400+拒因、零新建目录；合法路径与真书不受影响 |
| B25 活体 | 空书 failed+拒因+零产物；有章 completed+正文落盘 |
| 插件状态 | `/api/plugins` 7 插件全部 running（flywheel 0.1.16 资源已重建） |

## 6. 服务与工程事项

- 插件 update 一次（High-IL 进程外）+ 服务重启一次（加载 B24 后端代码 + 新
  dist + 0.1.16 资源）；服务日志 `xs2_r37_service.log`（已 gitignore）。
- 临时探针脚本（活体复现/验证/插件 update）用毕即删，未入库。

## 7. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| 插件 | `a101515` | B25 空书导出拒缩 + 0.1.16 + 4 条回归 + gitignore |
| xs2 | B24 主体 | workspace 覆盖白名单（核心收紧 + console 400 层）+ 9 条回归 + 5 文件夹具同步 |
| xs2 | 残留治理 | conftest 探针目录钉位 + 只读 rmtree |
| xs2 | 文档 | .env.example stream_chunk_timeout 条目 + 本文档 + PROJECT_INFO R37 条目 |

## 8. 遗留与下一轮候选

1. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变。
2. R36 §6 遗留项 5（sync-history UI 按钮真实浏览器逐字走查）：仍需一本满足
   条件的书（有完成态历史任务但 refs 为空）；下轮全流程实跑时顺带验证。
3. `data/workspaces/nope_missing`（无名测试残留）仍在运行数据区，无 manifest
   不入作品列表；下轮顺带清理。
4. **High-IL 复核记录（已回填）**：终跑于全部改动落定后执行——**1882 passed /
   11 skipped / 0 failed**（110.13s，权威）。对账：Low-IL 1797 + 85（96−11 个
   skip 在 High-IL 转真执行）= 1882 ✓；相对 R36 口径 1873/11/0 的变化 = +9
   （test_workspace_override_whitelist.py）。
5. **前端聚合计数（已回填）**：8 组 **447 tests / 447 pass / 0 fail**——前端
   零改动，与 R36 完全一致。
