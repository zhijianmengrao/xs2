# DeterminFlow (xs2) 交接报告 — Round 11

> 生成时间：2026-10-22
> 项目路径：F:/DeterminFlow x2/xs2
> 分支：main
> 基线提交：4854d47 添加角色声音功能前端组件和后端路由
> 文档编码：UTF-8 with BOM
> 重要说明：本轮所有代码改动仍在未提交的工作区中，接收者需自行比对后决定提交粒度。

---

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| 两轮完整套件用例总数一致 | 均为 1550 条 |
| 第二轮 0 failed | 但第一轮 21 个失败全部转为 skipped，并非修复 |
| 21 个失败根因一致 | Windows 账户无符号链接创建特权（WinError 1314） |
| 符号链接逃逸防护未经验证 | 相关断言在本机从未成功执行 |

必须强调：第二轮 0 failed 不等于 21 个问题已解决，只是这些断言没有执行。

## 2. 测试数据对照

| 指标 | 第一轮 _pytest_round4.log | 第二轮 .pytest-r11.log |
|---|---|---|
| 日志时间 | 2026-10-22 18:32:37 | 2026-10-22 23:02:21 |
| 日志大小 | 85524 字节 | 16004 字节 |
| passed | 1524 | 1514 |
| failed | 21 | 0 |
| skipped | 5 | 36 |
| 用例总数 | 1550 | 1550 |
| 耗时 | 113.95s | 116.37s |

换算验证：

- 1524 + 21 + 5 = 1550
- 1514 + 0 + 36 = 1550
- 21 个 failed 加 10 个 passed 共 31 条转为 skipped，与 skipped 从 5 增至 36 完全吻合

这证明第二轮是通过扩大跳过范围得到 0 failed。

## 3. 第一轮 21 个失败的根因

在 _pytest_round4.log 中检索 WinError 1314 得到 21 条，与 21 个失败一一对应，错误文本为：客户端没有所需的特权。

分类：

| 类别 | 数量 | 代表用例 |
|---|---|---|
| 插件与市场符号链接逃逸 | 14 | test_plugin_store.py::test_symlink_cannot_escape_checked_out_package、test_marketplace_update.py::test_update_validates_downloaded_version_and_refuses_symlinks |
| 工作区与工作流路径逃逸 | 4 | test_workspace_manager.py::test_absolute_override_rejects_symlink_escape_from_data_dir、test_workflow_variable_resolution.py::test_workflow_file_path_rejects_symlink_escape |
| macOS 打包与签名 | 3 | test_desktop_macos_signing.py 的 3 条 |

单点复核：用解释器在项目目录内创建目录符号链接，直接返回 WinError 1314，说明失败发生在测试准备阶段，被测防护函数从未被调用。因此这 21 条既不能算通过，也不能算被测代码存在缺陷。

## 4. 跳过机制的实际行为

tests/conftest.py 中包含：

- _can_create_symlink()：在临时目录实测创建符号链接
- _CAN_CREATE_SYMLINK：探测结果缓存
- _symlink_dependent_test_names()：按测试函数体是否出现符号链接相关字样生成跳过年名单

第一轮进入用例后在准备阶段抛异常；第二轮改为整体跳过。

风险：该机制依赖对测试函数体的文本匹配。若用例通过辅助函数间接创建符号链接，函数体本身不含关键字，就不会被纳入跳过名单，可能在别的环境静默通过而非真实校验。

## 5. 第二轮 36 条跳过分布

| 原因 | 数量 |
|---|---|
| 本环境无法创建符号链接 | 23 |
| macOS 签名工具链不可用 | 6 |
| 需要 macOS 生成 icon.icns | 1 |
| 负载脚本依赖 POSIX fcntl | 2 |
| Unix 进程组断言 | 1 |
| Unix 进程树断言 | 1 |
| 同源重复计数项 | 2 |

## 6. 工作区改动清单

git status 显示 52 个已跟踪文件被修改。

配置与脚本（7）：.gitignore、config/extensions.json、config/plugin-sources.json、config/rules_config.json、config/skills_config.json、setup_plugins.py、desktop/scripts/build_macos.py

后端（8）：src/extension_host/manifest.py、src/plugin_system/processes.py、src/plugin_system/source_selection.py、src/web/humanware_routes.py、src/web/novel_routes.py、src/workflow/execution_control.py、src/workflow/executor_supervisor.py、src/workflow/executor_transport.py

测试（19）：tests/conftest.py、tests/marketplace_fixtures.py、tests/test_core_account.py、tests/test_core_skill_catalog.py、tests/test_desktop_packaging.py、tests/test_extension_manifest.py、tests/test_marketplace_authoring.py、tests/test_marketplace_publish_target.py、tests/test_novel_configuration.py、tests/test_plugin_host_integration.py、tests/test_plugin_registry_release.py、tests/test_plugin_source_selection.py、tests/test_workflow_execution_control.py、tests/test_workflow_executor_pool_scenarios.py、tests/test_workflow_executor_protocol.py、tests/test_workflow_executor_readiness.py、tests/test_workflow_runtime_guards.py、tests/workflow_executor_pool_harness.py、tests/workflow_executor_pool_load_assets.py

前端（18）：web/src/components 下 15 个 tsx（CharacterVoiceEditor、HumanwareScoreCard、NovelAdvisorConversation、NovelArchiveContent、NovelConfigurationSuggestions、NovelManuscriptDownload、NovelPlotProposals、NovelReaderReport、NovelReferenceChoice、NovelReferenceContent、NovelRepairPanel、NovelStepModels、NovelWorkbenchPreferences、WritingLibraryReader、WritingLibraryView）、web/src/lib/novel-archive.ts、web/src/pages/NovelMarketPage.tsx、web/src/pages/NovelWorkbenchPage.tsx

未跟踪文件：uv.lock、.pytest-r11.log、docs/HANDOVER.md、docs/HANDOVER_ROUND10.md、docs/HANDOVER_ROUND10.md.bak-20261022、docs/PROJECT_INFO.md、docs/DELIVERY_REPORT_ROUND3.md

具体差异请用 git diff 逐项审阅，本文档不对改动内容做推断性描述。工作区存在大量 LF will be replaced by CRLF 警告，属换行符归一化提示，提交前应确认 .gitattributes 策略。

## 7. 服务与运行环境

- _svc_err.log 末尾可见 Application startup complete 与 Uvicorn running on http://0.0.0.0:8021。
- 同一次后台启动任务退出码为 1，当前是否仍在监听未经验证，不作运行中结论。
- 日志中文显示为乱码，属写入与读取编码不一致，影响排障可读性，建议统一 UTF-8。
- 日志出现 未找到 agents_config.json main agent 的 model 配置，回退到 agnes:agnes-2.5-flash 的告警，说明主 agent 模型配置缺失。

## 8. 已知问题

| 编号 | 问题 | 影响 |
|---|---|---|
| R11-1 | 21 个符号链接防护用例在 Windows 本机无法执行 | 安全逻辑未验证 |
| R11-2 | 跳过策略依赖函数体文本匹配 | 可能漏判间接用例 |
| R11-3 | 52 个文件与 7 个未跟踪文件未提交 | 交接状态不稳固 |
| R11-4 | 上一版 HANDOVER_ROUND10.md 正文含替换字符 | 旧文档不可靠 |
| R11-5 | 服务日志中文乱码 | 排障误导 |
| R11-6 | 主 agent 模型配置缺失走回退 | 行为可能不符预期 |
| R11-7 | docs 目录残留 .bak-20261022 | 目录冗余 |
| R11-8 | 测试日志未纳入忽略规则 | 易被误提交 |

## 9. 下一轮建议

1. 在启用开发者模式的 Windows、管理员会话或 WSL/Linux 环境复跑那 21 条，确认逃逸防护真实生效。
2. 把 macOS 签名与 icon.icns 相关 7 条放到 macOS 机器执行。
3. 把跳过条件收敛为统一装饰器，替代对测试函数体的文本扫描。
4. 按 配置 / 后端 / 测试 / 前端 / 文档 五批提交工作区。
5. 确认无用后删除 docs/HANDOVER_ROUND10.md.bak-20261022。
6. 服务日志统一 UTF-8。
7. 补齐 agents_config.json 中 main agent 的 model 配置。
8. 重启服务并验证 8021 监听与首页可访问后再记录结论。

## 10. 接收者第一步

cd F:/DeterminFlow x2/xs2
git status --short
git diff --stat
git log --oneline -5

随后按第 9 节执行。

## 11. 本轮命令记录

git status --short
git branch --show-current
git log --oneline -5
git diff --stat
Get-Content _pytest_round4.log -Tail 15
Get-Content .pytest-r11.log -Tail 40
Select-String -Path _pytest_round4.log -Pattern WinError 1314
Select-String -Path tests/conftest.py -Pattern symlink
解释器内 os.symlink 实测探测

## 12. 交接声明

- 本文档不含未经命令输出证实的推断。
- 本文档未修改任何代码，只记录现状。
- 21 个失败未修复，只是被跳过，这是本轮最重要的交接信息。