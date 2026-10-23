# DeterminFlow (xs2) 测试与修复交接文档

> 交接时间：2026-10-22 00:40 (Asia/Shanghai)
> 接手对象：下一轮测试/修复工作的执行者
> 本文档仅记录**本会话已实际确认的事实**，未验证项均标注「待验证」，不含臆造内容。
>
> **第二轮更新（2026-10-22 08:20）**：问题 A、B 均已定位并修复，验证通过；详见 §10。

---

## 1. 项目快照

| 项 | 值 |
|---|---|
| 项目路径 | `F:\DeterminFlow x2\xs2` |
| Git 分支 | `main`（最新提交 `4854d47 添加角色声音功能前端组件和后端路由`） |
| Python 运行时 | 项目 venv `F:\DeterminFlow x2\xs2\.venv\Scripts\python.exe` (3.12.14, pytest 9.1.1, fastapi 0.139.0, langgraph 已装) |
| 系统 Python | 3.14.8 已装（`C:\Program Files\Python314`，py launcher 可用）；venv 3.12.14 不受其影响 |
| 服务端口 | 8021（`.env` 设 `WEB_PORT=8021`）；既有实例 `F:\DeterminFlow` 占 8020，勿动其数据 |
| 前端 | React 18 + TS + Vite 7.3.6（`web/`，Node ≥22.12） |
| 测试规模 | pytest 收集 **1520 个测试**（修复收集错误前） |

## 2. 本会话已确认的事实（实测）

1. **测试收集被单个错误阻断**：`pytest --collect-only -q` 实际输出 `1520 tests collected, 1 error`（exit 1）。
2. **唯一收集错误**：
   ```
   ERROR tests/test_novel_story_assistant.py - FileNotFoundError:
   'F:\DeterminFlow x2\DeterminFlow-Plugins\plugins\xs2-novel-flywheel\resources\script-library\xs2\story_support\story_support.py'
   ```
3. **根因**：该测试在第 12-15 行做**模块级加载副作用**，从兄弟目录 `F:/DeterminFlow x2/DeterminFlow-Plugins` 加载 `story_support.py`（`Path(__file__).resolve().parents[2]` = `F:/DeterminFlow x2`）。当时该插件未克隆 → 文件不存在 → import 失败 → 全部测试无法收集。
4. **更正**：初判"两个收集错误"不准确。第二个 `bishu-novel` 的 `test_plugin_portability.py` 位于 `data/plugins/checkouts/`（pytest rootdir `tests/` 之外），**不产生**收集错误。
5. **模型配置已就绪**（`config/models_config.json`）：提供商 `agnes`，`base_url: https://api.agnes-ai.cn/v1`，api_key 已配置，模型 `agnes-2.5-flash` / `agnes-3.0-flash`，`maxContextTokens: 512000`。
6. **插件源配置**（`config/plugin-sources.json`）：custom 源优先级为 `file:///C:/xs2/DeterminFlow-Plugins`（本地，注意是 **C: 盘路径**），备用 `https://github.com/yuyang0702/xs2-plugins.git`。注意 PROJECT_INFO.md 第 48 行也写的是 `file:///C:/xs2/...`。
7. **用户已执行**：克隆 `xs2-plugins` 至 **`F:\DeterminFlow x2\DeterminFlow-Plugins`**、启动服务、配置 agnes API Key。
8. **当前新阻塞（用户实测）**：服务运行后 `xs2-novel-flywheel` 插件提示 **"已配置启用，但 Plugin 尚未安装"**。
9. **安装位置核验（用户实测）**：
   - `data\plugins\checkouts\` 下**仅 `bishu-novel`**，**无 `xs2-novel-flywheel`** → 系统判"未安装"直接证据。
   - `F:\DeterminFlow x2\DeterminFlow-Plugins\` 下含 `plugins\`、`plugin-repository.toml`、README 等 → 克隆仓库结构正常。

## 3. 当前未解决问题

### 问题 A（高优先）：`xs2-novel-flywheel` 已启用但未安装
- **现象**：`config/extensions.json` `enabled` 含该插件（`strict_startup: false`），但运行时判定"尚未安装"。
- **已确认**：插件系统识别的安装目录是 `data/plugins/checkouts/`（此处缺失），与用户克隆位置 `F:/DeterminFlow x2/DeterminFlow-Plugins` **不一致**。
- **待验证根因方向**（尚未定位确切代码路径）：
  1. 插件源 URL 与克隆位置不匹配：custom 源指向 `file:///C:/xs2/DeterminFlow-Plugins`（C 盘），实际克隆在 `F:/DeterminFlow x2/DeterminFlow-Plugins`（F 盘）。需确认 `source_selection.py` 如何选源。
  2. `setup_plugins.py` 是否按需把插件从源 checkout 到 `data/plugins/checkouts/`，及触发时机（`run.py` 启动时自动检测）。
  3. `config/extensions.json` 当前内容（本会话有未提交改动：启用列表为 `["xs2-novel-flywheel","bishu-novel"]`，见 §6）。

### 问题 B（高优先）：pytest 收集错误（Bug XS2-001）
- 即 §2 第 1-3 条。插件克隆后**可能已缓解**（文件已存在于兄弟目录），但**尚未重新验证收集是否通过**。

## 4. 待执行的测试/验证命令（人工）

在 `F:\DeterminFlow x2\xs2` 下，使用项目 venv：

```powershell
# B1: 确认测试收集是否已恢复（克隆插件后）
.\.venv\Scripts\python.exe -m pytest --collect-only -q
#   期望: 无 error，~1520 collected

# B2: 跑修复目标文件
.\.venv\Scripts\python.exe -m pytest tests/test_novel_story_assistant.py -q

# B3: 跑全套回归
.\.venv\Scripts\python.exe -m pytest -q

# A1: 诊断插件安装判定（读代码 + 日志）
Get-Content .\config\extensions.json
Get-Content .\setup_plugins.py
# 查看启动日志中 plugin 相关报错

# A2: 可选——手动触发插件安装后再比对 checkouts 目录
Get-ChildItem .\data\plugins\checkouts
```

## 5. 拟采用的修复方案（建议，未实施/未验证）

### 针对问题 B（pytest 收集）
将 `tests/test_novel_story_assistant.py` 第 12-15 行模块级硬加载改为**健壮条件加载**：插件文件存在则加载，缺失则提供最小兼容占位模块（含测试用到的 `write/read/apply_plan/prepare_context` 方法，缺失路径时抛 `unittest.SkipTest`）。
- **取舍**：保留 patch 注入用例的可执行性；仅真正依赖插件方法的用例在缺失时跳过；不阻断收集；不改生产代码。
- **风险**：占位方法须覆盖测试真实调用的 API；若遗漏会以 SkipTest 报出，便于补齐。
- 注：若问题 A 修复后插件文件已真实存在于兄弟目录，问题 B 可能**不再复现**，则无需此补丁，仅需回归验证。

### 针对问题 A（插件未安装）
需先读代码确认安装判定与选源逻辑（见下方"待读代码清单"），再定最小修复。**切勿臆造修复**。

## 6. 工作区未提交改动（接手前须知）

`git status` 显示已修改（M），**勿覆盖、勿随意还原**：
```
config/extensions.json          （enabled: ["xs2-novel-flywheel","bishu-novel"]）
config/rules_config.json        （last_updated 2026-10-21）
src/extension_host/manifest.py  （Windows 根相对路径校验加固）
src/plugin_system/source_selection.py （新增 _is_native_windows_drive_path，Windows 盘符路径识别）
src/workflow/execution_control.py
tests/marketplace_fixtures.py
tests/test_core_skill_catalog.py
tests/test_workflow_execution_control.py
新增: docs/PROJECT_INFO.md（未跟踪）
```

## 7. 待读代码清单（定位问题 A）

- `setup_plugins.py` — 自动检测/安装必须插件的逻辑
- `src/plugin_system/source_selection.py` — 插件源选择（含本次未提交的 Windows 路径改动）
- `src/extension_host/manifest.py` — manifest 校验
- `run.py` — 启动流程中的插件检测触发点
- `data/plugins/checkouts/bishu-novel/...` — 参考"已安装"插件的实际布局，对照缺失项

## 8. 已知风险与注意事项

1. **勿触碰 8020**：`F:\DeterminFlow` 为既有运行环境，禁止改动其数据。
2. **npm.ps1 被执行策略拦截**：前端操作请用 `npm.cmd`。
3. **Agent 类测试**（如 `test_startup_llm`）依赖模型凭据，agnes key 已配置，但**未实际运行验证**。
4. **前端构建未验证**：`cd web && npm run build` 未执行（web/dist 状态未知）。
5. **严格启动**：`extensions.json` 的 `strict_startup: false` 意味着插件缺失不阻断启动，故服务能起但插件显示未安装——务必确认改动后语义。

## 9. 下一步迭代计划（建议）

| 优先级 | 任务 | 验收标准 |
|---|---|---|
| P0 | 定位"已启用未安装"根因（读 §7 代码 + 日志） | 明确选源/安装链路断在哪 |
| P0 | 重新跑 `pytest --collect-only` 确认 Bug XS2-001 | 无收集错误 |
| P1 | 修复 A，重启服务后 `/api/plugins` 显示 xs2-novel-flywheel 已安装 | 插件状态=installed |
| P1 | 跑全套 pytest 回归 | 全绿（真实依赖用例默认 skip） |
| P2 | 前端 build + Web UI 冒烟（8021） | 构建成功、页面可访问 |
| P2 | 补 Windows 路径边界单测，锁定已有改动回归 | 新增测试通过 |

---

## 10. 第二轮进展（2026-10-22 08:20，全部经实测）

### 问题 A 已修复（根因确认 + 修复 + 验证）

**根因（两层，均已读码确认）**：
1. `config/plugin-sources.json` 的 `custom-xs2-local.url` 指向 `file:///C:/xs2/DeterminFlow-Plugins`（C 盘，**不存在**），实际克隆在 `F:\DeterminFlow x2\DeterminFlow-Plugins`。
2. 更深层：`run.py` 启动时调用的 `setup_plugins.py` **只写 `plugins_installed.json`（运行时无任何代码读取它），从不写入 `data/plugins/plugins.lock.json`**——运行时判定「已安装」只认 PluginStore 的 lock + `data/plugins/checkouts/`。所以即使克隆了仓库、启动脚本打印「插件已就绪」，运行时仍判「未安装」。

**已实施的修复**：
1. `config/plugin-sources.json`：`custom-xs2-local.url` → `file:///F:/DeterminFlow%20x2/DeterminFlow-Plugins`。
2. 通过与 API 安装完全相同的路径（`PluginStore.install` + `validate_plugin_checkout` 预检）把 `xs2-novel-flywheel` 装入 PluginStore：commit `4eed8cb`，checkout `data/plugins/checkouts/xs2-novel-flywheel/4eed8cb...-e0fa97cde7e45dbc`，trust=`third_party`，subdirectory=`plugins/xs2-novel-flywheel`。

**验证结果**：重启服务后 `/api/plugins`：`xs2-novel-flywheel` **runtime_status=running**、error 为空、restart_required=false；`bishu-novel` 亦 running。启动日志可见「扩展工具已注册: xs2-novel-flywheel」、skills 6→8、Agent 定义 6→76。Web UI 冒烟：HTTP 200（8021）。

### 问题 B 已确认消除

`pytest --collect-only -q`：**1523 tests collected, 0 error, exit 0**（克隆插件后模块级加载恢复，无需 §5 的占位补丁）。

### 前端构建已验证

`cd web && npm.cmd run build`：**构建成功（6.21s）**，dist 已产出。

### 已补充的回归单测（P2）

- `tests/test_plugin_source_selection.py`：新增 9 个用例，覆盖 `_is_native_windows_drive_path` 边界（NT/POSIX 门控、盘符形式、UNC、scp-like）、原生盘符路径与 `file:///` URL 的 canonicalize、authority/凭据拒绝、https 规范化。
- `tests/test_extension_manifest.py`：新增 3 个用例，锁定 `_validate_relative_path` 的根相对（`/`、`\`）与 Windows 盘符绝对路径拒绝。
- 两文件合计 40 通过。

### 待办与注意

1. **全套回归已完成（最终态）**：`1501 passed, 34 failed, 5 skipped`（118s，服务运行中）。
   - **已转绿（本轮修复）**：原 3 项 `test_agent_node_rejects_mid_task_execution_identity_drift[agent/prompt/model]` 已按用户确认的方案，在测试模板中声明 `model_id` 变量对齐 `create_task` 的未知键校验 → `test_workflow_runtime_guards.py` 23 项全绿；原 tzdata 相关的 31 项（token_usage 等）在安装 `tzdata` 后全绿。
   - **剩余 34 项均为环境限制（非代码缺陷）**：
     - **symlink 特权 ×17**：`SeCreateSymbolicLinkPrivilege` 在 DSH 会话令牌中为 Disabled，且**进程内启用无效**（`AdjustTokenPrivileges` 返回成功但令牌属性仍 0x00，`os.symlink` 仍报 WinError 1314）。等价复现已脚本化验证。涉及 marketplace_×5、plugin_×7、core_default_resources、extension_lifecycle、plugin_store、workflow_variable_resolution、workspace_manager。
     - **POSIX 权限位 ×2**（marketplace_authoring 0o666 vs 0o600、plugin_registry_release deterministic）。
     - **macOS 打包/签名 ×3**（desktop_macos_signing，Windows 上无 Mach-O 工具链）。
     - **编码 ×2**（desktop_packaging 中文断言乱码、core_account 字节数）。
     - **真实进程托管 ×7**（executor_protocol×2、executor_pool_scenarios×3、plugin_host_integration、plugin_processes::stop_kills）——在真实终端/CI 需复跑确认。
     - **配置相关 ×1**（novel_configuration 600!=180）、**cache ×1**（workspace_tools）。
   - **验收结论**：全部非环境类失败已清零；剩余项需在管理员令牌/POSIX 或 macOS 环境复跑。
2. ~~`setup_plugins.py` 的「假安装」缺陷仍在~~ → **已修复（2026-10-22 09:50，用户确认方案 A）**：`setup_plugins.py` 重写为真实安装：已安装则零副作用跳过；缺失时用本地兄弟仓库（`../DeterminFlow-Plugins`，subdirectory 优先取仓库 `plugin-repository.toml` 声明）经 `PluginStore.install` + `validate_plugin_checkout` 预检写入 `plugins.lock.json`（本地源按第三方信任 `acknowledge_risk=True`）；本地仓库缺失时只打印指引、**不联网**，不再写无人读取的 `plugins_installed.json`。已隔离验证三条路径：已安装跳过（lock 未改动, exit 0）、缺失真实安装（lock+checkout 落地, exit 0）、本地仓库缺失（提示, exit 1）。
3. `config/skills_config.json` 被服务启动自动同步改动（6→8 skills），属预期副作用。
4. 工作区新增未提交（本轮）：`config/plugin-sources.json`（URL 修正）、`tests/test_plugin_source_selection.py` 与 `tests/test_extension_manifest.py`（新增路径单测）、`tests/workflow_executor_pool_load_assets.py`（`_process_alive` Windows 修复）、`setup_plugins.py`（真实安装重写）、`tests/test_workflow_runtime_guards.py`（3 项对齐 `create_task` 未知键校验）。
5. **环境修复**：venv 安装了 `tzdata`（Windows Python 缺时区库，曾致 test_workflow_token_usage 29+2 项失败）。重建 venv 需重装。

### 第二轮中定位并修复的隐藏阻断（重要）

- **全套回归诡异中断的根因**：`tests/workflow_executor_pool_load_assets.py::_process_alive` 在 Windows 下调 `os.kill(pid, 0)`——CPython 把 signal 0 映射为 `GenerateConsoleCtrlEvent(CTRL_C_EVENT)`，**向自身进程组发 Ctrl+C**，异步打断整个 pytest 运行（表现为「每次跑到 ~76% 无声死掉」，并曾产生 lastfailed 1506 条的假象）。已修复为 Windows 下用 `OpenProcess(0x1000)+GetExitCodeProcess` 探活，POSIX 行为不变。修复后该文件 7 passed + 2 POSIX-fcntl 预期跳过，全套方可跑完。

### 收尾状态（2026-10-22 09:05）

- 服务已重启并保持运行：`http://localhost:8021`，`/api/plugins` 双插件 `running`（bishu-novel 0.2.2 / xs2-novel-flywheel 0.1.13），首页 HTTP 200。
- 本轮改动相关文件聚焦回归：`test_plugin_source_selection / test_extension_manifest / test_plugin_source_catalog / test_workflow_executor_pool_load / test_workflow_execution_control / test_core_skill_catalog` → **69 passed, 2 skipped**（POSIX fcntl 预期跳过），无连带影响。
- 诊断用临时日志已清理；`determinflow-executor-*` 与 `pytest-of-wenbo` 为本轮之前既存的运行时目录，未改动。

---

**交接说明**：上一会话在反复的工具调用格式问题上消耗较多，实际落地成果=已读配置文件 + 已跑通一次 pytest 收集诊断（经子代理）+ 明确两类问题的证据链。第二轮（§10）已完成问题 A/B 的定位、修复与验证。

---

## 11. 第三轮进展（2026-10-22，全部经实测）

### 11.1 回归终态对比

| 轮次 | passed | failed | skipped |
|---|---|---|---|
| 本轮基线（复现 §10 终态） | 1501 | 34 | 5 |
| **本轮终态** | **1524** | **21** | **5** |

新增 10 个用例（1 个 + 9 参数化），故总数 1540 → 1550。净修 **13 项失败**，零新增失败。
**剩余 21 项全部为环境限制**：18 项 `SeCreateSymbolicLinkPrivilege`（WinError 1314）+ 3 项 macOS 签名/打包。代码缺陷已清零。

### 11.2 本轮确认的根因（含对 §10 误分类的更正）

1. **Windows venv `python.exe` 是启动桩（stub）**——本项目 venv 由 3.14.8 创建，`Scripts\python.exe`(255200B) 会 fork 真正解释器作子进程；`Popen.pid` ≠ 真正 worker pid。实测：`Popen.pid=40504` 而子进程 `os.getpid()=43316`；stdlib 原生创建的 3.14 与 3.12 venv 均为同一行为，故与 uv 无关，**是 Windows venv 固有机理**。这是 §10 中 7 项「真实进程托管」失败的主因（此前未定性）。
2. **`pool.member_pids` / `supervisor.pid` 因此一直上报启动桩 pid**，实测生产 `/api/system/status` 曾会上报桩 pid，而桩并非执行器。
3. **Script 节点的 `os.getppid()` 永远不等于执行器 pid**：链条为 执行器(interp) → `sys.executable` 桩 → 真正解释器(跑脚本)，故脚本的直接父进程是桩。原用例用 `ppid == member_pid` 断言「粘性路由」是**设计上错误**的断言，非仅 Windows 不兼容。
4. **`reader_repair` 超时语义是刻意设计**：commit `1312d79` 同时（a）把 `create_llm(timeout=)` 从 180s 改为 `completion_timeout`，（b）**新增** `test_novel_repair::test_full_chapter_repair_can_complete_after_short_analysis_deadline` 锁定该行为，（c）未更新旧用例。故 `test_novel_configuration` 的 `timeout==180` 是**遗留过时断言**，不是代码 bug（§10 记为「配置相关」不准确）。曾误改产品代码，已回滚，`novel_assistant.py` 与 HEAD 一致。
5. **`test_desktop_packaging` 中文乱码真因**：文件按 UTF-8 写入，但用例用无参 `read_text()` 读取 → 走 `locale.getpreferredencoding()` = **cp936** → 乱码。属读取端缺 `encoding=`，非源码损坏（源码磁盘字节正确）。
6. **`test_marketplace_publish_target` 哈希不一致真因**：`write_text()` 在 Windows 把 `\n` 翻译成 `\r\n`，产品按原始字节做 sha256。LF sha=`8f5df7…`(期望) / CRLF sha=`733081…`(实得)，实测精确吻合。属夹具非确定性，非编码问题。
7. **`test_core_account` 失败真因**：`os.chmod(0o600)` 正确执行，但 NTFS 不承载 POSIX 权限位（`st_mode` 恒 0o666）。§10 记为「编码」有误，实为 POSIX 权限位类。

### 11.3 已实施的产品代码改动（4 文件，+86/−10）

| 文件 | 改动 | 目的 |
|---|---|---|
| `src/workflow/executor_supervisor.py` | `pid` 属性改为返回握手得到的真实 worker pid（`_worker_pid`）；新增 `_record_worker_pid()`（拒绝 bool/非 int/≤0/等于桩 pid 等畸形载荷）；start/spawn 失败/stop 三处复位；`_spawn` 注入 `DETERMINFLOW_EXECUTOR_ID/EPOCH` | 修 BUG-01 误报 pid；让脚本可自证所属执行器世代 |
| `src/workflow/executor_transport.py` | 新增 `EXECUTOR_ID_ENV`、`EXECUTOR_EPOCH_ENV` | 常量集中 |
| `src/plugin_system/processes.py` | Windows 下 `was_killed=True`（`send_signal(SIGTERM)` 即 `TerminateProcess`，无优雅层） | 修 BUG-04 可观测性失真 |
| `desktop/scripts/build_macos.py` | `read_text(encoding="utf-8")` | 消除区域设置依赖 |

**生产验证（实测）**：服务 8021 `/api/system/status` 四个执行器 pid=47380/51068/42432/47536，逐个核对 `CommandLine` 含 `executor_worker` 且其父进程为 `.venv\Scripts\python.exe` 桩 → 证明上报的是真 worker 而非桩。

### 11.4 已修改的测试（13 项转绿）

- 平台语义守卫（POSIX 权限位）：`test_core_account`、`test_marketplace_authoring`、`test_plugin_registry_release`
- 读取/写入确定性：`test_desktop_packaging`（`encoding="utf-8"`）、`test_marketplace_publish_target`（`newline="\n"`）
- 过时断言对齐刻意设计：`test_novel_configuration`（600）
- 脚本注入路径安全：`test_plugin_host_integration`（宿主路径改经 `environment` 传递，避免反斜杠被 Python 当转义）
- 语义化断言粘性路由：`workflow_executor_pool_harness.py`(`QUICK_SCRIPT` 记录执行器身份) + `test_workflow_executor_pool_scenarios.py`×3
- pid 契约：`test_workflow_executor_protocol.py`×2（改用 `supervisor.pid`）
- 新增回归：`test_workflow_executor_readiness.py` +10（pid 契约 1 个 + 畸形握手 9 参数化）

### 11.5 遗留与风险

1. 21 项环境类失败需在管理员令牌 / POSIX / macOS 环境复跑（清单见 §10.1，本轮已逐条核实原因）。
2. 仓库根残留 8 个 `determinflow-executor-*/`（崩溃的测试运行遗留，仅含 `rpc.endpoint`），未清理，**建议加 `.gitignore` 并定期清理**。
3. 服务当前运行于 8021，日志写在仓库根 `_svc_out.log` / `_svc_err.log`（为本轮冒烟临时产物）。
4. `docs/PROJECT_INFO.md` 记 Python 3.12.14，实际 venv 为 3.14.8（§10 已更正，PROJECT_INFO 未同步）。
5. 前端未改动，本轮复验 `npm.cmd run build` 成功（6.12s）。
