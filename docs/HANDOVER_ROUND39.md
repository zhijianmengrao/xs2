# DeterminFlow (xs2) 交接报告 — Round 39（维护轮：B26 家族 workflow 面收口 + B27 教训机械化）

> 本轮定位：R38 §7 候选中「测试卫生纪律」的机械化落地，顺带以 B26 同族
> 审计开题——实测发现并修复 **B28**（workflow 面 5 处读端点仍「查询即建
> 目录」，活体根因=资料蒸馏页每次开页建目录）、**B29**（preflight 暂存
> CWD 回落 MAX_PATH + longpath dst 教义缺口 + .env 相对路径地雷）、
> **B30**（插件仓资源卫生扫描与 pytest capture 暂存文件碰撞）。
> 基线：`12c356b`（R38 文档尾）→ 本轮 xs2 提交 `5bfea10`/`6683139`/
> `3f2d78f`（见 §6），插件仓 `1504a88`。

## 1. 缺陷与修复

### B28：workflow 面读端点「查询即建目录」（B26 家族，R38 未收编面）

- **现象/根因**：R38 只翻转了 novel_routes console 面；`workflow_routes.py`
  3 个 GET（`workspace-files`、`workspace-files/content`、
  `tasks/{id}/workspace-file`）与 `task_queries.py` 2 处
  （`get_task_result`、`read_task_artifact`，后者同时是 agent 工具
  `main_result_tools` 的底座）仍走默认 `create=True` → 幻影工作区查询
  即建目录。活体受害者：**资料蒸馏页**（NovelWorkbenchPage
  `DistillationView`）每次打开以新 `job-<时间戳>` 工作区调
  `listWorkspaceFiles` → 真实数据残留 4 个 `data/workspaces/reference-jobs/
  job-*` 空目录 + 5 条索引死条目（4 job + 1 父目录条目；均无 state.json、
  无任务引用，纯幻影，已清理并备份索引）。
- **修复**：5 处解析翻转 `create=False`；workflow_routes 新增
  `_existing_workspace_root()`（只解析不创建 + 不存在即 404
  「作品工作区不存在」，与 B26 `_console_existing_root` 同语义）。前端
  四处调用全部已容忍 404（refreshFiles catch 置空、DistillationView
  `.catch(()=>{})`、outline 备份 try/catch、章节读取 allSettled 过滤
  404），零前端改动。
- **验证**：定向 21 passed（15 旧 + 6 新）；8021 活体（重启加载）：
  幻影相对/绝对/content 三形态 404 + 零目录，真书 r38-flow 200/52 文件
  （绝对+相对双形态）。
- **novel_routes 957/1351 复核**：均有「任务已存在」前置守卫（R38 复核
  结论维持），非幻影面，有意保留 create=True。

### B29：preflight 暂存 CWD 回落 → MAX_PATH + longpath dst 教义缺口

- **现象**：插件套件从 `plugins/xs2-novel-flywheel/` 子目录跑 2 failed
  （WinError 206 文件名太长，copytree 进 `determinflow-plugin-preflight-*`
  暂存树）；从仓库根跑 98/0——CWD 敏感。
- **根因**（三层）：①`plugin_preflight.py` 的 `TemporaryDirectory` 不带
  `dir=`，本机 %TEMP% 受限（平台注意事项 8）回落 CWD；深 CWD 下深层
  vendor 树跨过 MAX_PATH。②`resource_preparation.py` 四处 copytree/copy2
  的 **dst 未过 `extended_path`**（违反 longpath.py「checkout 树复制必须
  经 extended_path」自家教义；源侧已过、dst 侧漏）。③`.env.example` 教
  `DETERMINFLOW_DATA_DIR=./data` 相对路径——`DATA_DIR` 随进程 CWD 漂移，
  首版钉位（用 DATA_DIR）曾把暂存树放进被测插件检出内部被验证扫描排除
  （FileNotFoundError/WinError 145 连锁）。
- **修复**：暂存根钉位 `config.BASE_DIR/data/system/preflight`（BASE_DIR
  无环境覆盖、与代码位置锚定）；四处 dst 补 `extended_path`；
  `.env.example` 与本地 `.env` 三行相对路径覆盖注释化（本地 .env 为
  gitignore 文件，仅记录不入库）。
- **回归**：`test_plugin_preflight_resources.py` 20→22（钉位断言 +
  深 CWD 功能守卫）；插件套件双 CWD 均 98/0（修复前子目录口径 2 fail）。

### B30：插件资源卫生扫描 × pytest capture 暂存文件碰撞（插件仓 1504a88）

- **现象**：`test_public_package_has_no_private_pipeline_markers`
  （rglob 扫描插件根全部文件）在本机从插件子目录跑必挂
  PermissionError，失败目标每次是新建的 `tmpXXXXXXXX` 条目。
- **根因**：pytest capture 每测试经 `tempfile.TemporaryFile()`
  （`_pytest/capture.py:16` 早绑定、`:493` 调用）建捕获文件；本机
  Low-IL 下 %TEMP% 不可写 → 回落 CWD=插件根 → O_TEMPORARY
  delete-pending 文件拒绝打开。裸 python 复刻扫描不触发（无 capture）；
  tempfile 包装探针日志为空（早绑定逃过包装）——最终以 pytest 源码
  位置 + CWD 依赖性定位。从仓库根跑时捕获文件落仓库根，扫描器看不到。
- **修复**：扫描 `read_text` 容忍集 `{UnicodeDecodeError}` 扩为
  `{UnicodeDecodeError, PermissionError}`（最小、与既有容忍同款）。
  双 CWD 98/0。

### B27 家族机械化（R38 §7.5 教训 → 代码）

`tests/conftest.py` 新增 autouse 夹具：每用例前后对真实
`data/novel-console/workspaces.json` 做「pytest 临时路径条目」集合差比对
（`pytest-of-` 签名 + 系统 tempdir 前缀，后者在 %TEMP% 回落 CWD 时自动
降级关闭防误伤），新增污染即在污染用例上 fail（精确归因）。四态负向验证
通过（合成条目标记/合法条目不误报/损坏与缺失索引返回空集）。本轮双基线
全程伴随守卫零误报、跑后索引零污染。

## 2. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：白名单文件（B24/B26/B28/B29 主场） | 21 passed（+6 B28） |
| 定向：preflight 文件 | 22 passed / 4 skipped（+2 B29） |
| 广域定向（13 个改动面相关文件） | 157 passed / 1 skipped |
| Low-IL 全量 | **1811 passed / 96 skipped / 0 failed**（98.90s） |
| High-IL 全量（权威） | **1896 passed / 11 skipped / 0 failed**（132.67s） |
| 插件套件（插件子目录 + 仓库根双口径） | **98 passed / 0 failed ×2** |
| 前端三连 | lint 0 problems；**8 组 447 passed / 0 fail**（零改动）；build ✓ 6.14s |
| 存储名审计 | [clean] exit 0 |
| 索引污染复查 | 0 条（总数 64→59，本轮清理 5 条死条目） |
| 活体（8021，最终代码） | 幻影 404+零目录；真书 200/52；4/4 执行器 ready degraded=false |

对账：Low 1803+6(B28)+2(B29)=1811 ✓；High 1888+8=1896 ✓。总用例 R38 口径 1899 → **1907**。

## 3. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | `5bfea10` | B28 主体：workflow 面 5 处 create=False + `_existing_workspace_root` 404 化 + 6 条回归 |
| xs2 | `6683139` | B29 主体：preflight 暂存钉位 BASE_DIR + 4 处 dst extended_path + .env.example 治理 + 2 条回归 |
| xs2 | `3f2d78f` | B27 家族防污染守卫（conftest autouse） |
| xs2 | 本文档提交 | 交接文档 + PROJECT_INFO R39 条目 |
| 插件 | `1504a88` | B30：资源卫生扫描容忍 PermissionError |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性）；
索引/目录清理均为运行数据；本地 `.env` 注释化（gitignore 文件）。

## 4. 运行数据清理记录

- 删除 `data/workspaces/reference-jobs/`（4 个空 job 目录 + 父目录）。
- 索引移除 5 条对应死条目（64→59）。备份：`data/system/workspaces.json.r39-bak`。
- 插件仓清理：`plugins/xs2-novel-flywheel/pytest-of-wenbo/`、
  `tmp*` 残留、半截 `data/system/preflight/` 暂存树（B29 修复前中断产物）。

## 5. 遗留风险与需人工确认事项

1. **推送**：xs2 积压 19 个提交（R29 起 + 本轮 4 个）、插件仓 4 个——需
   维护者授权推送触发 CI 全量核对（外向操作，未执行）。
2. **POSIX 真跑 / updater 死通道清理 / 大陆下载加速**：R32 起状态未变；
   分别需容器环境、cargo 工具链、外部基础设施决策（T2 类）。
3. **`.env` 相对路径覆盖已注释化**：下次服务重启后 `DETERMINFLOW_DATA_DIR`
   等不再生效（默认值 BASE_DIR/data 与原意一致，已实测 8021 正常）；若
   维护者有意用非默认数据目录，需改回绝对路径写法。
4. **Low-IL %TEMP% 不可写**是本机多项 CWD 回落现象的共同根因（平台注意
   事项 8 的延伸），已三处治理（executor-runtimes/test-probes/preflight），
   `pytest capture` 与 `pytest-of-*` 落 CWD 属 pytest 侧行为，仓库无法
   收口，靠 gitignore + 本轮 B30 容忍兜底。
5. **get_task_result 的 HTTP 面不存在**（仅 agent 工具暴露）：本轮探针
   曾按 HTTP 路径探测得 404，属路由不存在而非缺陷；该面由单测覆盖。

## 6. 下一轮候选（优先前 3）

1. **契约 §6.1 常驻回归基线复跑**（低风险，~30min）：R25 起未专项复跑，
   对照 `humanware-helper-contract.md` §6.1 清单逐项活体验证；验收=逐项
   记录 + 差异表。
2. **「读端点建目录」静态防复发检查**（低风险，~1h）：新增脚本/单测，扫描
   `resolve_workflow_workspace` 全部调用点断言「GET 路由处理链不含
   create=True」（B26/B28 两轮同族缺陷的机械化终局）；验收=审计脚本入
   CI 或钉测，零误报。
3. **供应商失败率画像**（中等工作量）：R38 §7.4 建议落地——为工作流任务
   增加每阶段尝试/失败计数输出（API 或日志），供后续压测参考；验收=一次
   小规模实跑产出画像数据。

其余：推送（待授权）、updater 死通道（待 cargo）、POSIX（待环境）、
大陆下载加速（待基础设施决策）。

## 7. 本轮未实际运行

无。本轮全部结论均有实际命令/测试/探针输出支撑。
