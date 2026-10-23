# 交付报告 — DeterminFlow (xs2) 第三轮测试与修复

> 交付日期：2026-10-22
> 交付对象：`F:\DeterminFlow x2\xs2`（分支 `main`，基线提交 `4854d47`）
> 环境：Windows 本机，venv Python 3.14.8，pytest 9.1.1，服务端口 8021
> 说明：本报告所有结论均来自本轮**实际执行**的命令与输出；未实际运行的内容已显式标注。

---

## 1. 交付摘要

| 指标 | 基线（本轮开始） | 交付态 | 变化 |
|---|---|---|---|
| pytest passed | 1501 | **1524** | **+23** |
| pytest failed | 34 | **21** | **−13** |
| pytest skipped | 5 | 5 | 0 |
| 合计用例数 | 1540 | 1550 | +10（新增回归） |
| 代码缺陷类失败 | 13 | **0** | −13 |
| 环境类失败 | 21 | 21 | 0（均为平台限制，已逐条归因） |

**验收结论：本轮范围内代码缺陷清零。** 剩余 21 项失败全部为平台环境限制（18 项 Windows symlink 特权 + 3 项 macOS 签名/打包），非代码缺陷，需在对应平台复跑。

---

## 2. 交付物清单

### 2.1 产品代码（4 文件，+86 / −10）

| 文件 | 变更 | 关联缺陷 |
|---|---|---|
| `src/workflow/executor_supervisor.py` | `pid` 属性改为返回握手自报的真实 worker pid；新增 `_record_worker_pid()` 校验畸形载荷；start/spawn 失败/stop 三处复位；`_spawn` 注入 `DETERMINFLOW_EXECUTOR_ID` / `DETERMINFLOW_EXECUTOR_EPOCH` | BUG-01 |
| `src/workflow/executor_transport.py` | 新增常量 `EXECUTOR_ID_ENV`、`EXECUTOR_EPOCH_ENV` | BUG-01 |
| `src/plugin_system/processes.py` | Windows 下停止进程时置 `was_killed=True`（`send_signal(SIGTERM)` 即 `TerminateProcess`，无优雅终止层） | BUG-02 |
| `desktop/scripts/build_macos.py` | `read_text(encoding="utf-8")`，消除 locale 依赖 | BUG-08 |

> 兼容性：`pid` 属性签名与返回类型未变；新增环境变量为纯增量的可选契约；无接口破坏。

### 2.2 测试代码（11 文件）

- 平台语义守卫：`test_core_account.py`、`test_marketplace_authoring.py`、`test_plugin_registry_release.py`
- 读写确定性：`test_desktop_packaging.py`、`test_marketplace_publish_target.py`
- 断言对齐刻意设计：`test_novel_configuration.py`
- 脚本注入路径安全：`test_plugin_host_integration.py`
- 语义化粘性路由断言：`workflow_executor_pool_harness.py`、`test_workflow_executor_pool_scenarios.py`
- pid 契约：`test_workflow_executor_protocol.py`
- **新增回归用例 10 个**：`test_workflow_executor_readiness.py`（1 个契约用例 + 9 个参数化畸形载荷用例）

### 2.3 文档

- `docs/HANDOVER.md` 新增 §11（本轮进展、根因、验证记录）
- `docs/PROJECT_INFO.md` 更新（Python 版本、插件源路径、测试基线、新增「平台注意事项」8 条）
- 本报告：`docs/DELIVERY_REPORT_ROUND3.md`

---

## 3. 已修复缺陷明细

| ID | 级别 | 类别 | 摘要 | 根因（实测证据） | 状态 |
|---|---|---|---|---|---|
| BUG-01 | P0 | 产品 | 执行器 pid 上报为启动桩而非真 worker | venv `python.exe` 是 stub，fork 真正解释器；`Popen.pid=40504` 而子进程 `os.getpid()=43316`；3.12/3.14 stdlib venv 均如此 | 已修复 |
| BUG-02 | P1 | 产品 | Windows 插件进程 `was_killed` 恒 False | Windows 无优雅终止层，`SIGTERM` 即 `TerminateProcess`，永不进入升级分支 | 已修复 |
| BUG-03 | P1 | 测试 | 插件宿主用例注入路径致 SyntaxError | `${DATA_DIR}` 展开含反斜杠，被拼进 Python 单引号字面量，`\x` 被当转义 | 已修复 |
| BUG-04 | P1 | 测试 | 中文断言乱码 | 文件按 UTF-8 写，用例用无参 `read_text()` → `locale` = cp936 解码 | 已修复 |
| BUG-05 | P1 | 测试 | 内容哈希与期望不一致 | `write_text()` 在 Windows 把 LF 转 CRLF；实测 LF=`8f5df79a…`、CRLF=`73308199…`，与断言精确吻合 | 已修复 |
| BUG-06 | P2 | 测试 | POSIX 权限位断言失败 | NTFS 不承载 POSIX 位，`st_mode` 恒 `0o666` | 已修复 |
| BUG-07 | P2 | 测试 | 过时断言与刻意设计冲突 | 提交 `1312d79` 将 `create_llm(timeout=)` 改为完成预算，并同提交新增 `test_novel_repair` 锁定该行为，但未更新旧用例 | 已修复 |
| BUG-08 | P2 | 产品 | `build_macos.py` 读 JSON 未指定编码 | 依赖 locale 默认编码 | 已修复 |

### BUG-01 生产验证（实测）

服务 8021 的 `/api/system/status` 返回：

| executor_id | 上报 pid | 该 pid 的 CommandLine | 其父进程 |
|---|---|---|---|
| workflow-executor-0 | 47380 | 含 `executor_worker` | 53568（`.venv\Scripts\python.exe` 桩） |
| workflow-executor-1 | 51068 | 含 `executor_worker` | 49364（桩） |
| workflow-executor-2 | 42432 | 含 `executor_worker` | 53084（桩） |
| workflow-executor-3 | 47536 | 含 `executor_worker` | 54180（桩） |

即：**上报值为真正的 worker 解释器**，而非修复前会误报的启动桩（53568/49364/53084/54180）。

---

## 4. 测试执行记录

### 4.1 回归（实跑）

```
# 基线
.\.venv\Scripts\python.exe -m pytest -q
→ 34 failed, 1501 passed, 5 skipped, 1 warning in 116.23s

# 交付态
.\.venv\Scripts\python.exe -m pytest -q
→ 21 failed, 1524 passed, 5 skipped, 1 warning in 114.74s
```

### 4.2 重点模块（实跑）

```
test_workflow_executor_protocol.py / _readiness.py / _pool_load.py / _pool_scenarios.py
→ 76 passed, 2 skipped（POSIX fcntl 预期跳过）

test_novel_configuration.py + test_novel_repair.py
→ 13 passed

test_marketplace_publish_target.py
→ 8 passed

test_plugin_host_integration.py
→ 10 passed

test_desktop_packaging.py
→ 33 passed, 1 skipped（macOS icon.icns 预期跳过）
```

### 4.3 运行态冒烟（实跑）

| 检查 | 结果 |
|---|---|
| `GET http://127.0.0.1:8021/` | HTTP 200 |
| `GET /api/plugins` | 双插件 `runtime_status=running`，`error` 为空，`restart_required=false` |
| `GET /api/system/status` | 4 执行器 `status=ready`、`degraded=false`、`restart_count=0` |
| `cd web && npm.cmd run build` | 成功，`✓ built in 6.12s` |

---

## 5. 剩余 21 项失败的归因（全部环境类）

| 类别 | 数量 | 代表用例 | 判定依据 |
|---|---|---|---|
| Windows symlink 特权（WinError 1314） | 18 | `marketplace_update`×3、`plugin_preflight_resources`×2、`plugin_config`×2、`plugin_store`、`workspace_manager`、`workspace_tools`、`workflow_variable_resolution`、`extension_lifecycle`、`core_default_resources`、`marketplace_bundle`、`marketplace_stage3_isolation`、`plugin_dependencies`、`plugin_processes::cwd_symlink`、`plugin_registry_release::git_symlinks` | 每条失败输出均为 `OSError: [WinError 1314]` |
| macOS 签名 / 打包 | 3 | `test_desktop_macos_signing`×3 | 需 Mach-O 工具链，Windows 不可用 |

复跑条件：管理员令牌（或启用 Developer Mode 后重新登录创建进程）/ POSIX 环境 / macOS 环境。

---

## 6. 变更影响面与风险

| 项 | 评估 |
|---|---|
| 接口兼容性 | `pid` 属性签名不变；新增 2 个只读环境变量为可选契约，旧代码不受影响 |
| 行为改变 | 仅 Windows 下 `was_killed` 语义变为真值（原先恒 False）；属可观测性字段，无逻辑分支依赖（全仓检索仅 status 输出使用） |
| 数据/配置迁移 | 无 |
| 性能 | 无影响（握手已存在，仅额外复用其返回值） |
| 回滚方式 | 按文件 `git checkout --` 即可；产品改动与测试改动相互独立 |

---

## 7. 遗留问题与建议（下一轮）

| 优先级 | 任务 | 预估 | 验收标准 |
|---|---|---|---|
| P0 | 管理员/POSIX 环境复跑 18 项 symlink 用例 | 0.5d | 转绿，或确认为平台不适用并显式 skip |
| P1 | 决策 `create_llm` 传输超时是否与总预算分离 | 0.5d | 两个 novel 用例同向通过，无回退 |
| P1 | 清理执行器临时目录泄漏 + `.gitignore` + 启动时回收陈旧目录 | 0.5d | 反复跑回归后仓库根不再增长 |
| P2 | 同步 `PROJECT_INFO.md` 其余历史描述 | 0.2d | 与实测一致 |
| P2 | 将 `was_killed` Windows 语义写入插件打包文档 | 0.2d | 文档明确无优雅终止层 |
| P3 | macOS 打包 3 项改显式 `skipif` | 0.2d | 非 macOS 平台 skip 而非 fail |

### 当前工作区状态提示

- 仓库根存在 12 个 `determinflow-executor-*/` 目录（崩溃测试遗留，仅含 `rpc.endpoint`）与 `pytest-of-wenbo/`；**未清理**，建议加 `.gitignore`。
- 服务运行于 8021，临时日志为仓库根 `_svc_out.log` / `_svc_err.log`。
- 上一轮遗留的未提交改动（`config/*.json`、`setup_plugins.py`、`src/extension_host/manifest.py`、`src/plugin_system/source_selection.py`、`src/workflow/execution_control.py`）保持原样，未被覆盖。

---

## 8. 未实际运行的内容（如实声明）

- 未在 POSIX/macOS/管理员令牌环境执行任何命令，故上述 21 项失败未取得"通过"证据。
- 未连接真实大模型进行端到端 Agent 调用（仅运行了使用 mock/fake 模型的用例）。
- 未执行 `docker compose config -q` 与前端 `npm run lint` / `npm run test:*`（仅执行了 `npm run build`）。
