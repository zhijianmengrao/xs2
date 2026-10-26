# DeterminFlow (xs2) 交接报告 — Round 36（收编轮：R34/R35 未提交工作落地 + 基线修复）

> 本轮定位：用户下发标准全周期测试模板。当时工作树里压着 **R34（B20）与 R35
> （B21/B22）两轮的全部未提交改动，且两轮均无交接文档**；后端基线自 R33 起常挂
> 1 失败（外来 skills_config.json）。本轮做了四件事：①以 diff + 实测收编 R34/R35
> 工作（后端 5 个提交）；②修复钉值测试 **B23** 使基线归零；③关闭 R35 观察项
> 「纯 API 跑完进度显 0%」（诚实提示，不改语义）；④发现并闭合 **B22 未生效于
> 运行时**的部署缺口（运行时资源停留在修复前版本）。
> 基线：`bcefc55`（R33 文档尾）→ 本轮 `0f636c5`（xs2）+ `6804876`（插件）。

## 0. 收编内容溯源（R34/R35 无交接文档，以下经未提交 diff + 轮次记忆重建）

| 来源轮 | 缺陷 | 内容 | 本轮提交 |
|---|---|---|---|
| R34 | B20 | 清单损坏致整书静默重置：`read_manifest` 判损坏、`/projects` 打 `_corrupt`、保存前隔离备份 `.corrupt-<ts>`、修订号保护不放宽 | `553c249` |
| R34 | B20 配套 | `NovelWorkbenchPage` 损坏提示（+R36 0% 提示，见 §3） | `6395e43` |
| R35 | B21 | 未知参数键谎报 404 → 422 结构化拒因（manager 结构化返回 + 路由映射） | `aa0e7ec` |
| R35 | B22 | 插件 story_support 引文抄写叠字容差（精确匹配失败后仅在折叠单字重复且首末句锚定一致时放行） | 插件 `6804876`（含 0.1.15 bump） |

R34 回归文件 `tests/test_novel_full_flow_round34.py`（38 条：创作主链 C1–C20、
损坏四态 C21–C24、边界/异常）随 `553c249` 入库。定向执行 **36 passed**（B20+B21
范围），插件 `test_story_support.py` **40 passed**。

## 1. B23：钉值测试与产品行为矛盾（本轮修复）

### 1.1 现象
Low/High-IL 全量各挂 1 失败：`test_skills_config_matches_versioned_core_catalog`
断言 `set(config["skill_configs"]) == CORE_SKILL_IDS`（恰为 6 个 core），实际多出
24 个社区插件 skill 条目。

### 1.2 根因（取证，非推测）
- `config/extensions.json` 启用 5 个社区插件（apocalypse-writer / humanizer-zh /
  lieflat-less-ai-tone / oh-story / webnovel-writer），`plugins.lock.json` 一致；
- `src/extension_host/manager.py:87` 的 `_JSON_RESOURCE_SCHEMAS` 把插件 skills 资源
  映射进 `skills_config.json` 的 `skills`/`skill_configs` 两节——**安装并启用社区
  插件后，扩展宿主把它们的 skill 条目合法写入该文件**（`{enabled,priority,auto_inject}`
  同步默认形；`skills` 节为 `{}`）。
- 结论：该测试把「core 目录精确」（另一测试已单独钉住）与「配置文件永不含社区条目」
  （与产品行为矛盾）混为一谈，属**测试设计缺陷**，不是配置被污染。

### 1.3 修复（`f59fe30`）
core 六条目逐字钉死不变；非 core 条目只校验「同步器产出结构」（dict + enabled:bool）。
修复后该文件 9 passed，全量基线归零。

## 2. B22 运行时部署缺口（发现并闭合）

R35 修复 B22 时只改了插件源仓库；本轮实测 **runtime-resources 里的
`story_support.py` 不含修复**（`_collapse_repeats` 计数 0）——即修复从未生效于
活体服务。闭合步骤（全部实际执行）：

1. 插件版本纪律：`extension.toml` 0.1.14→0.1.15 + 3 处钉值同步（`test_plugin_portability`
   ×2、`test_resources` ×1），随 B22 一起提交（`6804876`）；
2. **服务侧 update 端点在本机不可用**：`POST /api/plugins/xs2-novel-flywheel/update`
   必崩 msys（`NtCreateDirectoryObject 0xC0000022`）——服务进程为 Low-IL 令牌
   （F: 盘 venv 解释器，PROJECT_INFO 注意事项 9），插件源为 `file://` 本地路径也走
   git 传输。**今后刷新插件资源：用 High-IL 解释器在进程外调 `PluginStore.update`**
   （构造参数同 `src/extension_host/manager.py:151`），本轮已实测成功；
3. checkout 前进至 `6804876c`（lock 的 `active_revision.commit` 证实）→ 重启 8021
   → runtime-resources 重建，`_collapse_repeats` 落位 ✓。

## 3. 观察项收口：纯 API 跑完进度显 0%

- `novel_progress.progress()` 的归属语义：每阶段以 manifest `refs`（console 启动
  任务时写入）定位任务文件，无 refs 时退回 `state.completed` 手动通道；
  `test_novel_full_flow_round34.py::test_c16` **有意钉死**「无 refs 时即使存在产物
  与已完成任务也不算完成」（防历史残留/其他流程的任务被误认成本书成果）。
- 现状核查（本轮实测）：r33-flow（R35 九段实跑之书）manifest 已含 refs=9/
  completed=9，活体 `/projects` 显示 **100%**——数据层已无 0% 残留；历史观察项
  属「驱动脚本未模拟 console 写入」的过程现象（R33 §3.4 已预告）。
- 处置：**不改进度语义**（尊重 c16 钉值的防误报理由），展示层加诚实提示——
  进度 0% 且检测到章节产物时，进度行追加「检测到已有章节产物，但本作暂无流程
  记录（经 API 直接启动的任务不计入进度，从创作流程页启动后开始统计）」
  （`6395e43`）。文案已进入新 dist（`NovelWorkbenchPage-DmN7Z_wr.js` 含该串）。
  活体 UI 未逐字走查：现数据无满足条件的书，拒绝为验证而篡改真实作品数据。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：round34 + B21 文件 | **36 passed** |
| 定向：插件 test_story_support | **40 passed** |
| Low-IL（`.venv`）全量 | **1783 passed / 96 skipped / 0 failed**（103.74s，服务在跑故 e2e 真实执行） |
| High-IL（`py.exe`+PYTHONPATH，权威） | 见 §6 复核记录 |
| 插件套件（0.1.15 bump 后复跑） | **94 passed**（两次：bump 前后各一次） |
| 前端 | lint 0 problems；**8 组 447 passed / 0 failed**；build ✓ 6.31s |
| 活体 e2e `tests/test_humanware_e2e.py` | **17 passed**（重启后） |
| 存储名审计 | `[clean]` exit 0 |
| B21 活体探针 | `POST .../mvp/tasks` 仅未知键 → **422** `{"code":"unknown_parameters","message":"...题材创意...可用变量: action_writer_cache, ..."}`（修复前为 404「工作流不存在」）；无副作用目录 |
| B22 活体 | runtime-resources 版本含 `_collapse_repeats` ✓ |
| 插件状态 | `/api/plugins` 7 插件全部 `running` |

对账说明：R35 记录 Low 1782/96/1 → 本轮 1783/96/0；-1 失败（B23）+1 passed 为
服务在跑时 e2e 用例真实执行（R35 记录时点差异），总用例 1879 不变。

## 5. 服务与工程事项

- 8021 服务已重启加载本轮全部后端代码 + 插件 0.1.15 资源 + 新 dist；
- `.gitignore` 新增 `/xs2_r*_service*.log`（历轮服务日志残留在仓库根，本轮起忽略）；
- 提交清单（xs2）：`553c249`(B20) → `aa0e7ec`(B21) → `f59fe30`(B23) → `6395e43`(web) → `0f636c5`(chore) → 本文档；
  插件：`6804876`(B22 + 0.1.15)。

## 6. 遗留与下一轮候选

1. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变。
2. **High-IL 权威基线数字**：见 §6 复核记录（运行中时本文档以 Low-IL + 定向 + 活体为准，
   High-IL 结果回填于文末）。
3. R33 §3.1（stream_chunk_timeout 暴露到设置页，P2）与 §3.2（workspace_override 白名单，
   P3）、§3.3（空书导出 409，P3）仍未实施，作为下一轮优化候选。
4. 插件仓库 `pytest-of-wenbo/` 临时目录残留（%TEMP% ACL 回落老问题），可加 ignore。

### High-IL 复核记录（回填）

- High-IL 全量：**1868 passed / 11 skipped / 0 failed**（118.35s，权威）。
  对账：R35 口径 1867/11/1 → -1 失败（B23）+1（服务在跑 e2e 执行），净 1868，
  与 Low 1783 + 85（96−11 个 skip 转真执行）一致。

## 7. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | `553c249` | B20 清单损坏防护 + round34 回归文件（收编 R34） |
| xs2 | `aa0e7ec` | B21 未知参数 422（收编 R35） |
| xs2 | `f59fe30` | B23 钉值测试收敛 |
| xs2 | `6395e43` | web 两处进度诚实化（B20 配套 + 0% 观察项收口） |
| xs2 | `0f636c5` | chore: 忽略服务日志 |
| 插件 | `6804876` | B22 叠字容差 + 0.1.15 bump + 钉值同步 |
