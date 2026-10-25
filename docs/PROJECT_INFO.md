# DeterminFlow（yuyang0702/xs2）项目信息

## 项目名称
DeterminFlow（`yuyang0702/xs2` 二次开发版）——面向生产的确定性 AI 工作流运行框架。把 LLM、脚本、API、数据库操作和人工审批组织成有版本、可校验、可重试、可恢复、可审计的工作流。

- 仓库：https://github.com/zhijianmengrao/xs2（**origin**，2026-10-24 迁移；原 `yuyang0702/xs2` 保留为 upstream 远程，真正上游为 `alikon-art/DeterminFlow`）
- 本地安装路径：`F:\DeterminFlow x2\xs2`

## 项目状态（2026-10-24 完结）

- **迭代完结于 Round 22（完结轮，纯终验+文档定稿）**（R15–R22 共 8 轮「审计→修复→
  回归→交接」循环，逐轮记录见 docs/HANDOVER_ROUND15..22.md）；全部提交已推送
  （`origin/main..main` = 0）。
- **交付摘要**：修复 13 个编号缺陷（B1–B13，涵盖 HTTP 500 逃逸、幻影目录数据损坏、
  内容静默丢失、409 谎报占用等类别）；「名字面」安全治理全线闭环（路径面 +
  标识符面，单一规则源 `src/core/win_names.py` + 历史数据只读体检
  `scripts/audit_storage_names.py`）；executor 临时目录治理（钉位
  `data/system/executor-runtimes`，仓库根残留清零）；总用例 1597（R17 口径）→
  **1828**（R21：High-IL **1817 passed / 11 skipped / 0 failed** 权威、Low-IL
  1732/96/0 快速）；CI 四 job 全绿（backend / windows-backend / frontend /
  container-config）。
- **有意遗留**（详见 HANDOVER_ROUND21 §9）：POSIX 真跑验证（需容器/WSL 环境）、
  HumanwareScoreCard 前端组件（纯新增 UI，无缺陷压力）、`start()` 失败时
  supervisor 状态悬挂（无实际泄漏）。
- **上游桌面发布管线（2026-10-24 已转绿）**：`.github/workflows/desktop-windows.yml`
  为上游继承的 Tauri/NSIS 发布流水线（发布清单指向 alikon-art 上游 release 与
  downloads.determinflow.com）。曾因缺 `TAURI_SIGNING_PRIVATE_KEY` 密钥在本 fork
  预期红；完结后已补齐：本地 minisign 密钥对（空密码，密钥文件已 gitignore）+
  GitHub secret 配置 + `tauri.conf.json` 的 updater `pubkey` 替换为本 fork 公钥
  （`25282d4`：core/full 两条 NSIS job **success**，管线史上首绿；macOS/release
  job 按 tag-only 规则正确跳过）。注意：`endpoints` 仍指向上游 latest.json，
  在自有分发地址落地前自动更新呈**安全失效态**（新公钥验上游签名不过即拒绝）；
  若要启用自动更新需替换 endpoints 为自己的 latest.json 地址。
- **维护入口**：接口契约 docs/humanware-helper-contract.md（**v3.4 完结版**，
  含 §6.1 常驻回归基线）；数据巡检 `python scripts/audit_storage_names.py`
  （exit 0 clean / 1 有发现）；回归命令与权威基线定义见下文「测试环境」。
- **R23 维护轮（2026-10-24，完结后首轮维护）**：HANDOVER_ROUND21 §9 候选起点
  落地——①P1「幻影目录免疫」复查以**真实 NTFS 证据**收口（`\\?\` 前缀创建
  真实 nul 目录实测：常规 `Path` 对其仍呈幻影属性语义但内部可读写；
  `_trusted_marketplace_skill_path` 未打补丁即正确拒绝 409，入口守卫链闭合，
  无需改码），证据钉成常驻回归 `tests/test_real_device_name_dirs.py`；
  ②修复 **B14**：`start()` 里 mkdtemp/restrict_private_path 失败时 supervisor
  状态悬挂 `starting`（移入 try 块，状态复位 stopped）；③O-a 审计脚本挂进
  CI windows-backend job；④O-b 活体 e2e F5–F7 探测公共管线去重。双基线
  **1735/96/0（Low-IL）、1820/11/0（High-IL 权威）**，总用例 1828→1831。
  详见 docs/HANDOVER_ROUND23.md。
- **R24 维护轮（2026-10-24，维护态第二轮）**：R23 §9 候选落地——①修复
  **B15**：活体 e2e `_get`/`_post` 补 URLError/OSError 分支（服务中途宕机返回
  -1 而非未捕获异常；F5–F7 探测的「-1→诚实 skip」路径此前是死代码）；
  ②修复 **B16**：supervisor `stop()` 与 monitor 重启竞态的兜底收割（防孤儿
  worker 带租约活到控制器退出）+ `start()` 失败清 stale client；
  ③P3 收口：`installation_state()` 真实 nul 目录证据钉成回归（R20 修复面）；
  ④关闭 R21「pool 语义」复核备注（部分失败处理经逐行复核无缺陷）。
  双基线 **1740/96/0（Low-IL）、1825/11/0（High-IL 权威）**，总用例
  1831→**1836**。注意：R23、R24 两个提交均未推送；工作树存在 15 个
  HANDOVER 文档的外来删除（未提交，需维护者核查）。详见 docs/HANDOVER_ROUND24.md。
- **R25 维护轮（2026-10-25，维护态第三轮，纯前端）**：R24 §9 P2 落地并修正
  认知——HumanwareScoreCard 组件其实自 `4854d47` 起就存在但**全仓零引用**，
  前端也从未调用 score-content/score-chapter/check-dialogue；本轮把
  **score-content（契约 §3.3）接入「角色声音」页**：角色下拉（解析自编辑器
  `## 角色名` 小节）+ 试评 textarea + HumanwareScoreCard 渲染，409 透传 CLI
  message，空输入双层守卫。后端零改动。验证：前端三连全绿（lint 0 /
  **8 组 415 条 0 fail**（净增 9：编辑器 +5、卡片 +4）/ build ✓）；
  **真实浏览器 e2e**（8021 新 dist）选林晚评分 → 卡片渲染 90/A/四维全出，
  截图存档；活体 e2e 17 passed；双基线数字不变（后端未动）：
  **1740/96/0（Low-IL）、1825/11/0（High-IL 权威）**。附带复核关闭 R24 §9 P3
  （e2e 宕机失败信息可读性足够，无需改动）。R23–R25 三个提交未推送。
  详见 docs/HANDOVER_ROUND25.md。
- **R26 维护轮（2026-10-25，维护态第四轮，纯前端）**：R25 §7 P2 落地——
  ①**score-chapter（契约 §3.4）接入「读者评估」页**：新组件
  ChapterHumanwareScore（workspaceKey 归一化 + `story/<四位>/chapter.md`
  padStart），成功渲染「共评分 N 段对话」+ HumanwareScoreCard，业务失败
  404/409 透传 CLI 拒因；②修复 **B17**（R25 引入）：score-content 业务失败
  的真实包络是 FastAPI `{detail}` 而非 CLI `{message}`，前端读错字段致 409
  拒因被兜底文案吞掉（R25 单测 mock 形状与活体不符而假通过）——错误提取改
  `detail` 优先并用真实形状重锚测试。后端零改动。验证：前端三连全绿
  （lint 0 / **8 组 422 条 0 fail**（净增 7）/ build ✓）；真实浏览器 e2e
  （8021 新 dist，demo-voice 第 1 章）评分卡 81/B/2 段对话渲染 + B17 活体
  409 拒因透传，截图存档；活体 e2e 17 passed；双基线不变：
  **1740/96/0（Low-IL）、1825/11/0（High-IL 权威）**。R23–R26 四个提交未推送。
  详见 docs/HANDOVER_ROUND26.md。
- **R27 维护轮（2026-10-25，维护态第五轮，纯前端）**：R26 §7 P2 两项落地——
  ①**check-dialogue（契约 §3.5）接入「角色声音」页**：检查区块（复用角色
  解析下拉 + violations/suggestion 渲染 + matches 两态徽章 + 409 detail
  透传），**humanware 五端点 UI 接线就此收官**；②api 层 4xx 错误人因化
  （B17 同族收口）：`http-client` 的 `describeErrorBody` 把 FastAPI
  `{"detail": ...}` 解成人话拒因再入 message，`getRoundtableErrorDescription`
  配套兼容（旧 JSON 格式优先、纯文本仅 4xx 直显、5xx 仍隐藏）。后端零改动。
  验证：前端三连全绿（lint 0 / **8 组 434 条 0 fail**（净增 12）/ build ✓）；
  真实浏览器 e2e 偏离/符合两态渲染（demo-voice 林晚，截图存档）+ 读者评估页
  alert 人因化活体验证；活体 e2e 17 passed；双基线不变：
  **1740/96/0（Low-IL）、1825/11/0（High-IL 权威）**。R23–R27 五个提交未推送。
  详见 docs/HANDOVER_ROUND27.md。
- **R28 维护者任务执行轮（2026-10-25，用户授权）**：①15 个 HANDOVER 外来
  删除正式提交归档（`a249e17`，连续五轮的「疑似用户归档」闭环）；
  ②**首次推送成功**——R23–R27 全部积压提交 + 后续修复共 7 个提交推送至
  origin（GCM 已存账号 zhijianmengrao，推送障碍未复发，`origin/main..main`=0）；
  ③CI 四 job 实跑核对发现并修复 **B18**：R23 挂 CI 的存储名审计步骤在
  cp1252 stdout（windows-latest PowerShell）下打印中文结论即崩
  （UnicodeEncodeError 把 clean 误报成失败；R23 后从未推送故从未真实执行）——
  脚本 stdout 重配 UTF-8 + `PYTHONIOENCODING=cp1252` 子进程回归锚
  （`d3d75d5`）。修复后 **CI 四 job 全绿**（backend/windows-backend/
  frontend/container-config）+ Desktop Windows NSIS 流水线 success。
  双基线 **1741/96/0（Low-IL）、1826/11/0（High-IL 权威）**，总用例
  1837。desktop updater 分发地址决策选项分析见 HANDOVER_ROUND28 §6。
  详见 docs/HANDOVER_ROUND28.md。
- **R29 updater 分发自托管轮（2026-10-25，方案 A 落地，用户选型）**：
  endpoints/GITHUB_UPDATE_ENDPOINT 切本 fork GitHub Releases
  （`2938a82`）；release manifest `--base-url` 改 `${{ github.repository }}`
  （修 latest.json 安装器链接指向上游的潜伏错误）；上游 R2/Gitee 源因 fork
  公钥验签必败保留为死通道（fail-closed，永不入选）；钉值测试同步。发版
  流程：打 tag + release-notes → release job 自动产 NSIS/.sig/latest.json
  → 桌面端更新可用。CI 四 job + Desktop NSIS 双构建全绿；双基线不变
  （1741/96/0、1826/11/0）。详见 docs/HANDOVER_ROUND29.md。
- **R30 维护轮（2026-10-25，维护态第六轮，纯前端重构）**：R29 §6 P2 落地——
  角色声音页三区块（试评/检查/编辑器）共享「角色下拉+内容输入」子组件抽取
  （R27 §6 遗留候选）：新 `CharacterVoiceInputs.tsx`（CharacterSelect +
  ContentTextarea），主组件三处 textarea + 两处 select 换用（净 -39/+24 行）；
  空态提示随提示进组件后检查区块也显示（原缺失属 UI 不一致，顺带收敛）；
  编辑器补 aria-label。DOM 契约（textarea 顺序 + aria-label）不变，
  CharacterVoiceEditor 22 条测试未改一行通过。后端零改动、无缺陷修复
  （Phase 2 全量基线复测全绿）。前端 `npm test` **8 组 439 条 0 fail**
  （净增 5：新组件单测）；lint 0 / build ✓；真实浏览器 e2e 三流程
  （试评评分卡 B/85、检查符合态、检查偏离态 85 字长句触发句法指纹违规）
  + 截图视觉核验；活体 e2e 17 passed（新 dist 重启后）；存储名审计 [clean]；
  双基线不变：**1741/96/0（Low-IL）、1826/11/0（High-IL 权威）**（改动前树
  复测 + 交叉文件复验 36/1 一致）。详见 docs/HANDOVER_ROUND30.md。
- **R31 发版演练轮（2026-10-25，用户决策版本号 v1.0.0）**：fork 首个 tag
  发版全链路落地——①版本号统一 `1.1.1→1.0.0` 六处（tauri/Cargo.toml/
  Cargo.lock 应用包/desktop package.json/**official-plugins.lock 的
  desktop_version**（load 硬校验必须同步）/钉值测试）+ release-notes；
  ②tag `v1.0.0` 推送 → 四个 run 全 success（**macOS core/full 构建为 fork
  首次真实执行**，ad-hoc 签名无证书依赖）→ release job 发布
  https://github.com/zhijianmengrao/xs2/releases/tag/v1.0.0（11 资产）；
  ③验收全过：updater 端点 latest.json **200**（R29 的 404 空态终结）、
  下载 URL 指向本仓库（R29 base-url 修复实测生效）、tauri pubkey↔本地
  .pub 逐字一致、**端到端 minisign 验签通过**（`scripts/verify_release_v100.py`：
  sha256 ✓ + ed25519 对 blake2b-512(安装器) ✓，与桌面更新器同链）。
  版本线说明：1.0.0 低于上游 1.1.1 属 fork 自有起点，上游客户端需全新
  安装；大陆直连下载慢（33MB 实测 ~30KB/s），痛点成真时按 R28 §6 选项 B
  迁移。详见 docs/HANDOVER_ROUND31.md。
- **R32 收官轮（2026-10-25，项目暂定最终版 v1.0.1）**：①R31 建议落地——
  评分/检查历史持久化（`web/src/lib/humanwareHistory.ts`，localStorage 按
  工作区隔离/20 条/受限降级 + 两组件接线 + 8 测试，活体验证含跨刷新）；
  发版固化（`scripts/verify_release.py` 参数化验收 + `docs/RELEASE_SOP.md`）；
  死通道清理因无 cargo 无法本地验证记有意遗留。②**小说创作全流程实测**：
  10 页面走查全绿；build 工作流实跑（世界观管线多 agent 真实 LLM 产出
  7,749 字世界观，首次因第三方模型跑飞失败【completion 打满 65536 截断，
  非代码缺陷】重试成功，进度 11%→22%）；reader-sim 实跑 30 秒出报告
  （25 分/3 问题/返修入口）。③无产品缺陷、无新增优化项 → **v1.0.1 定为
  暂定最终版**（六处 bump + notes + tag + 流水线 + 验收全过）。
  本轮基线：前端 **8 组 447 条 0 fail**（净增 8）、Low-IL 1741/96/0、
  High-IL 1826/11/0（一次 3-fail 为服务重启竞态自证非缺陷）、审计 clean、
  活体 e2e 17 passed。项目就此收官，维护入口与遗留清单见
  docs/HANDOVER_ROUND32.md §6。

## 技术栈与运行方式

| 项目 | 内容 |
|---|---|
| 后端语言 | Python ≥3.11（要求）；**本机 venv 实际为 Python 3.14.8**（`.venv\pyvenv.cfg` 的 `home = C:\Program Files\Python314`；早期文档误记 3.12.14） |
| 后端框架 | FastAPI 0.139.0 + uvicorn 0.50.2、LangGraph 1.2.8、MCP 1.28.1、LangChain、gunicorn |
| 前端 | React 18 + TypeScript + Vite 7.3.6 + Tailwind CSS + React Flow（node ≥22.12） |
| 核心依赖 | openai 2.44.0、fastapi、uvicorn[standard]、langgraph、langchain-core/openai/anthropic、mcp、httpx、cryptography、websockets、croniter、aiofiles |
| 数据 | 文件型（`data/` 工作区、JSON/SQLite 检查点），无独立数据库服务 |
| 启动命令（Windows） | `git clone` → `python -m venv .venv` → `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` → 复制 `.env`、`config\models_config.json` → `.\.venv\Scripts\python.exe run.py` |
| 前端构建 | `cd web && npm install && npm run build`（产出 `web/dist/`；`run.py` 启动时自动检测构建） |
| 环境变量 | `.env`：`WEB_HOST`、`WEB_PORT`（默认 8020）、`DEEPSEEK_API_KEY` 等，统一 `DETERMINFLOW_*` 前缀 |
| 模型配置 | `config/models_config.json`（供应商需在设置页或配置填写） |
| Docker 方式 | `docker compose up --build` |
| 启动后访问 | Web UI `http://localhost:8020` · API `/docs` · 插件 `/api/plugins` |

## 仓库结构

```
xs2/
├── run.py                  # 后端入口，负责前端构建/插件检查/启动 uvicorn
├── pyproject.toml          # 项目元数据与依赖（Python ≥3.11）
├── requirements.txt        # 运行时依赖锁定
├── requirements.lock / requirements-dev.lock
├── setup_plugins.py        # 自动检测并安装必需插件（xs2-novel-flywheel）
├── .env.example            # 环境变量模板
├── docker-compose.yml / Dockerfile
├── src/                    # Python 后端（web_server、agent、core、mcp、tools、skills、rules、prompts）
├── web/                    # React 前端（src/、dist/、vite.config.ts、package.json）
├── config/                 # 运行配置（models_config、extensions、plugin-sources、agents_config）
├── data/                   # 运行数据（workspaces、plugins checkouts、检查点）
├── scripts/                # 环境检查、启动辅助脚本
├── desktop/                # 桌面客户端（Tauri）
├── tests/ · docs/ · examples/
└── 启动脚本：start_determinflow.bat / start_determinflow_v2.ps1 / rebuild_now.ps1
```

- `config/extensions.json` — 启用 `xs2-novel-flywheel` 插件（`strict_startup: false`）
- `config/plugin-sources.json` — 官方/社区源 + 自定义本地源 `file:///F:/DeterminFlow%20x2/DeterminFlow-Plugins`（早期文档误记 `file:///C:/xs2/DeterminFlow-Plugins`，该路径不存在）及 `github.com/yuyang0702/xs2-plugins.git`

## 约束条件

- Python ≥3.11；Node.js ≥22.12（`web/package.json` 的 `engines`）
- 默认端口 8020；本机 8020 已被 `F:\DeterminFlow` 上既有 DeterminFlow 实例占用，新实例运行在 **8021**（`.env` 设 `WEB_PORT=8021`）
- 许可证 **GNU AGPL-3.0**
- 模型/凭据未配置时仅 Core 服务可启动；Agent 调用前需在 `models_config.json` 或设置页配置
- 第三方/社区插件与主进程同权限运行、无沙箱，安装前需确认风险
- 默认 4 个本机 Workflow Executor；单进程回退 `DETERMINFLOW_WORKFLOW_EXECUTOR_MODE=inline` + `DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT=1`
- 并发限制：`UVICORN_LIMIT_CONCURRENCY` 默认 200、`UVICORN_BACKLOG` 默认 2048

## 测试环境

- 本地沙箱/开发环境（Windows 本机 `F:\DeterminFlow x2\xs2`），非生产
- 已安装完成并可访问：Web UI `http://localhost:8021`、API `/docs`、插件 `/api/plugins`
- **禁止直接操作生产环境**；`F:\DeterminFlow`（端口 8020）为既有运行环境，未改动其数据
- 验证方式：`python -m pytest -q`；`cd web && npm run lint && npm run test:* && npm run build`；`docker compose -f docker-compose.yml config -q`
- 2026-10-22 最终本地回归（`.\.venv\Scripts\python.exe -m pytest -q`）：**1514 passed / 0 failed / 36 skipped**；所有剩余 skip 均为平台环境限制（Windows symlink 特权 / macOS 签名 / POSIX fcntl），不再有失败项；前端 `npm run lint` 0 errors、`npm test` 全过、`npm run build` 成功。
- 2026-10-24 R17 双基线（同一提交，Windows）：Low-IL（venv）`pytest -q` → **1501 passed / 96 skipped / 0 failed**；High-IL（`C:\Windows\py.exe` + venv site-packages 经 `PYTHONPATH`，见平台注意事项 9）→ **1586 passed / 11 skipped / 0 failed**。High-IL 是权威基线（symlink 与 msys git 用例都真实执行）；Low-IL 下这些用例转为 skip。
- 2026-10-24 R18 双基线（core 层 Windows 名称守卫 + 错误映射 + 测试健壮性修复）：Low-IL → **1623 passed / 98 skipped / 0 failed**；High-IL → **1708 passed / 13 skipped / 0 failed**（13 = 11 平台 skip + 2 条 `test_humanware_e2e` F6/F7，服务未重启加载 R18 代码时诚实 skip）。净增 **124** 条用例（core 名称守卫 20 + marketplace 规则等价性 99 + web 端到端 3 + 服务侧 e2e F6/F7 2；其中 F6/F7 在 Low/High 两种 IL 下各计 1 条 skip，故 passed 增 122、skip 增 2）。总用例数 R17 1597 → R18 1721。
  > R18 B9 已让 `test_workflow_executor_protocol` / `test_workflow_recovery_timeout` 与系统 locale
  > 解耦（子进程 env 内显式 `PYTHONIOENCODING=utf-8` + 父进程按 UTF-8 解码），因此下面两条命令
  > **无论会话是否预设 `PYTHONIOENCODING` 都会通过**（实测四种组合各 39 passed）。
- **基线政策（R19 起）**：本地 Low-IL（`.venv`）仅作**快速跑**；**权威基线**为 ① 本机 High-IL 命令
  （见平台注意事项 9）与 ② CI `windows-backend` job（`.github/workflows/ci.yml`：windows-latest +
  Python 3.14 + `requirements-dev.lock`，与本机 High-IL 平台一致，Windows 专属用例在 CI 真实执行）。
  ubuntu `backend` job 保留作跨平台快速信号。
- 2026-10-24 R20 双基线（插件 id / 资源 id / 市场 Skill id 设备名拒绝）：Low-IL → **1720 passed / 96 skipped / 0 failed**（服务在跑，故 e2e 15 条执行而非 skip）；High-IL → **1805 passed / 11 skipped / 0 failed**。净增 **93** 条用例（`test_plugin_name_guard.py` 60 + `test_marketplace_skill_id_guard.py` 33）。对账：Low-IL 1627+93=1720；High-IL 1697+93+15(e2e skip→pass)=1805。
- 2026-10-24 R21 双基线（executor runtime 目录钉位 + 存储名只读审计 + 市场安装真实包 e2e + update exists() 语义锚定）：Low-IL → **1732 passed / 96 skipped / 0 failed**；High-IL → **1817 passed / 11 skipped / 0 failed**。净增 **12** 条用例（`test_storage_name_audit.py` 5 + `test_executor_runtime_dir.py` 2 + `test_marketplace_install_e2e.py` 3 + update 锚定 2）。对账：Low-IL 1720+12=1732；High-IL 1805+12=1817。
- 2026-10-24 R23 双基线（维护态首轮：B14 修复 + 真实设备名常驻回归 + e2e 探测去重）：Low-IL → **1735 passed / 96 skipped / 0 failed**（105.49s）；High-IL → **1820 passed / 11 skipped / 0 failed**（122.78s，权威）。净增 **3** 条（`test_executor_runtime_dir.py` B14 回归 1 + `test_real_device_name_dirs.py` 2，后者 POSIX/不支持环境诚实 skip）。对账：Low-IL 1732+3=1735；High-IL 1817+3=1820。总用例 R21 口径 1828 → **1831**。
- 2026-10-24 R24 双基线（维护态二轮：B15 e2e 宕机语义 + B16 supervisor 竞态兜底 + installation_state 真实证据）：Low-IL → **1740 passed / 96 skipped / 0 failed**（109.75s）；High-IL → **1825 passed / 11 skipped / 0 failed**（125.27s，权威）。净增 **5** 条（`test_humanware_e2e.py` B15 逻辑回归 2（服务不在跑时随模块诚实 skip）+ `test_executor_runtime_dir.py` B16 回归 2 + `test_real_device_name_dirs.py` 1）。对账：Low-IL 1735+5=1740；High-IL 1820+5=1825。总用例 R23 口径 1831 → **1836**。
- 2026-10-25 R25 双基线（维护态三轮，纯前端接线，后端零改动）：Low-IL → **1740 passed / 96 skipped / 0 failed**；High-IL → **1825 passed / 11 skipped / 0 failed**（权威）——与 R24 完全一致（后端用例集未变）。前端 `npm test` **8 组 415 条 0 fail**（净增 9：`CharacterVoiceEditor.test.ts` +5、`HumanwareScoreCard.test.ts` +4，`test:desktop` 100→109）；lint 0 problems；build ✓ 6.78s；活体 e2e 17 passed（新 dist 重启后）；存储名审计 [clean]。另：真实浏览器 e2e 首次打通 UI→score-content→CLI→评分卡链路（详见 HANDOVER_ROUND25 §4.2）。
- 2026-10-25 R26 双基线（维护态四轮，纯前端，后端零改动）：Low-IL → **1740 passed / 96 skipped / 0 failed**（104.88s）；High-IL → **1825 passed / 11 skipped / 0 failed**（121.42s，权威）——与 R24/R25 完全一致。前端 `npm test` **8 组 422 条 0 fail**（净增 7：`ChapterHumanwareScore.test.ts`，`test:desktop` 109→116）；lint 0 problems；build ✓ 6.30s；活体 e2e 17 passed（新 dist 重启后）；存储名审计 [clean]；真实浏览器 e2e 打通 UI→score-chapter→CLI→聚合评分卡（demo-voice 第 1 章 81/B/2 段对话）+ B17 活体 409 拒因透传（详见 HANDOVER_ROUND26 §4.2）。
- 2026-10-25 R27 双基线（维护态五轮，纯前端，后端零改动）：Low-IL → **1740 passed / 96 skipped / 0 failed**（105.55s）；High-IL → **1825 passed / 11 skipped / 0 failed**（124.83s，权威）——不变。前端 `npm test` **8 组 434 条 0 fail**（净增 12：`CharacterVoiceEditor.test.ts` +5、`http-client.test.ts` 新文件 5、`roundtableStream.test.ts` +2；`test:desktop` 116→121、`test:conversation` 135→137）；lint 0 problems；build ✓ 6.34s；活体 e2e 17 passed（新 dist 重启后）；存储名审计 [clean]；真实浏览器 e2e 打通 UI→check-dialogue→CLI→violations/suggestion（demo-voice 林晚偏离/符合两态）+ 读者评估页 alert 人因化活体验证（详见 HANDOVER_ROUND27 §4.2）。
- 2026-10-25 R28 双基线（维护者任务执行轮：删除归档 + 首次推送 + CI 核对 + B18）：Low-IL → **1741 passed / 96 skipped / 0 failed**（102.25s）；High-IL → **1826 passed / 11 skipped / 0 failed**（118.84s，权威）。净增 **1** 条（B18 回归锚 `test_script_survives_non_utf8_stdout`）。总用例 1836→**1837**。**推送闭环**：`origin/main..main`=0；CI（`d3d75d5`，run 40149647827）**四 job 全绿**（backend/windows-backend/frontend/container-config，windows-backend 测试本体 1808 passed / 28 skipped 含 e2e 诚实 skip）；Desktop Windows NSIS（`a249e17`，run 40148872233）success。B18 细节与 CI 首败取证见 HANDOVER_ROUND28 §3。
- **2026-10-24 CI 首绿（仓库已迁移：origin → `zhijianmengrao/xs2` 与 `zhijianmengrao/xs2-plugins`，原
  `yuyang0702/*` 保留为 upstream 远程）**：commit `e925dda`，run 40088073223，四 job 全绿（backend /
  windows-backend / frontend / container-config），CI 全量 **1790 passed / 26 skipped**。首跑过程修复三个
  CI 环境缺陷：① backend/windows 缺兄弟目录 `../DeterminFlow-Plugins`（7 个测试文件按 `parents[2]` 读取
  本地开发布局，现 CI 显式 depth-1 克隆插件仓库）；② workflow 步骤名含冒号+空格致 YAML 解析失败（0 job，
  教训：改 workflow 须先 `yaml.safe_load` 本地验证）；③ `test_novel_progress` 两处 `write_text('正文')`
  未传 encoding——本机 cp936 掩盖、CI cp1252 必炸（注意事项 5 的实证；其余 1788 条在 cp1252 下全过 =
  全仓唯此两处残留）。
- 2026-10-22 运行状态抽查：`/api/plugins` 双插件 `runtime_status=running`（bishu-novel 0.2.2 / xs2-novel-flywheel 0.1.13）；`/api/system/status` 四执行器 `ready`（pid 为**真实 worker 解释器**，非启动桩）；`cd web && npm.cmd run build` 成功。
- 2026-10-24 R21 完结态抽查：8021 服务运行 R21 代码（重启加载 `29b8eb8`，4/4 执行器
  `ready`、`degraded=false`）；活体 e2e `tests/test_humanware_e2e.py` **15 passed /
  0 skipped**（F5/F6/F7 版本探测全部执行，确认新代码在线）；存储名审计
  `scripts/audit_storage_names.py` → `[clean]`；仓库根 `determinflow-executor-*`
  残留**清零**（runtime 目录已在 `data/system/executor-runtimes/`）；`29b8eb8`
  的 CI（ubuntu backend）success。

## 平台注意事项（Windows，2026-10-22 实测确认）

这些是**实测结论**，不是推测；修改相关代码前务必先读。

1. **venv 的 `python.exe` 是启动桩（stub launcher）**
   `.venv\Scripts\python.exe`（约 255 KB）会 fork 真正的解释器作为**子进程**。因此：
   - `subprocess.Popen().pid` / `asyncio.create_subprocess_exec().pid` **不等于**子进程的 `os.getpid()`；
   - 任何"用 spawn 返回的 pid 代表工作进程"的逻辑在 Windows 上都错位；
   - Python 3.12 与 3.14 的 stdlib venv **都是**该行为（与 `uv` 无关）。
   - 已有正确做法：`WorkflowExecutorSupervisor.pid` 采用 worker 在 `ping` 握手中自报的 pid。

2. **脚本（Script 节点）的 `os.getppid()` 不等于执行器 pid**
   进程链为：执行器解释器 → `sys.executable`（桩）→ 真正解释器（跑脚本）。脚本的直接父进程是桩。
   不要再以 `ppid == member_pid` 断言"任务跑在哪个执行器"；应使用下节的执行器身份环境变量。

3. **执行器身份环境变量（可用于脚本自证世代）**
   Workflow Executor 为子进程注入 `DETERMINFLOW_EXECUTOR_ID` 与 `DETERMINFLOW_EXECUTOR_EPOCH`，脚本可读取以确认自己由哪个执行器世代运行（脚本经 `os.environ` 继承）。

4. **POSIX 权限位在 NTFS 上不可用**
   `os.chmod(path, 0o600)` 会静默"成功"，但 `st_mode` 仍为 `0o666`。凡断言权限位的用例须 `if os.name == "posix":` 守卫。

5. **`Path.read_text()` 不传 `encoding` 会用系统 locale（本机 cp936）**
   读取 UTF-8 文件将得到乱码。本项目所有文件读写**应显式传 `encoding="utf-8"`**。

6. **`Path.write_text()` 默认把 `\n` 翻译为 `\r\n`**
   若后续对**原始字节**做哈希（如 marketplace 的 `source_sha256`），跨平台结果会不同；需要确定性字节时传 `newline="\n"`。

7. **symlink 相关用例仅在 Low-IL 解释器下不可用（R17 修正，见平台注意事项 9）**
   会话令牌中 `SeCreateSymbolicLinkPrivilege` 为 Disabled 且进程内启用无效，`os.symlink` 报 WinError 1314。根因与本机解释器被降为 **Low 完整性级别**有关，不必然需要管理员令牌或重新登录：以 High-IL 解释器（`C:\Windows\py.exe` + venv site-packages 经 `PYTHONPATH` 挂载）跑同一套件时，symlink 用例可正常创建链接并通过。

8. **`%TEMP%` 有 ACL 限制**，`tempfile.mkdtemp()` 会落到当前工作目录（实测
   `gettempdir()` 返回进程 CWD），导致仓库根出现 `determinflow-executor-*/`、
   `pytest-of-wenbo/`、`tmpXXXX` 等临时目录；建议加入 `.gitignore`。
   **R21 处置**：executor supervisor 已改显式 `dir=DATA_DIR/system/executor-runtimes`
   （`executor_supervisor._runtime_dir_root`），不再依赖 %TEMP%；仓库根 52 个历史残留
   已清理 48 个（余 4 个为当时在跑服务的活跃目录，重启服务后失效）。其余调用点
   （如 pytest 自身）仍可能回落 CWD，gitignore 规则保留。

9. **（2026-10-23 R16 发现 / R17 定位根因并给出处置）msys 引导被拒——影响所有需要 git 传输的测试**
   症状：由 python `subprocess` 派生的 Git for Windows msys 程序（`usr/bin/sh.exe`、`bash.exe`）
   启动即崩：`*** fatal error - NtCreateDirectoryObject(\BaseNamedObjects\msys-2.0S5-<hash>): 0xC0000022`。
   **R17 根因（实测，非推测）**：
   - 令牌的强制完整性级别（IL）随**可执行文件所在位置**变化：任何 `python.exe`（含改名副本）
     从 **F: 盘**启动即为 **Low IL（S-1-16-4096）**，同一二进制复制到 **C:** 启动为 **High IL**；
     `cmd.exe`/`node.exe`/`C:\Windows\py.exe` 在本会话均为 High IL。
   - 机器上已存在由更早的 msys 进程创建的共享对象 `\BaseNamedObjects\msys-2.0S5-<hash>`。
     实测（本会话，ctypes 直调 ntdll）：该对象**确实存在**——自建同名目录对象返回
     `0xC0000035`（OBJECT_NAME_COLLISION），说明先前某进程已创建它；
     Low-IL 进程 `NtOpenDirectoryObject` 时 `DIRECTORY_QUERY`/`LIST_DIRECTORY`/`MAXIMUM_ALLOWED`
     成功，而 `SYNCHRONIZE`/`WRITE_DAC`/`DIRECTORY_ALL_ACCESS` 一律 `0xC0000022`
     （STATUS_ACCESS_DENIED），`MAXIMUM_ALLOWED` 实际只授予 `SYNCHRONIZE|READ_CONTROL` 级别；
     msys 需要被拒绝的那部分访问，故引导失败。对象属主 SID 为本地用户 RID 1001。
     （DACL 明细未能可靠读出，因此此处只陈述可达/被拒的实测结果，不断言具体 ACE。）
     对照实验：`cmd.exe`(High IL) 直接 exec `sh.exe` → rc=0 正常；`cmd.exe` → `python.exe`(Low IL)
     → `sh.exe` → 崩溃。因此 R16 记为「疑似安全软件 / 重启可解」的结论**不成立**——判别变量是
     解释器令牌的 IL，而非机器状态；**无需重启机器**。
     （R16 当日 R15 全量绿、R16 全量红的差异，同样由该 IL 差异解释。）
   - 影响面：git 的 clone/fetch/push/ls-remote 传输（本地路径与 `file://` 也算）都要 exec msys `sh`；
     `init/add/commit/config/rev-parse/branch/tag/log/diff` 等原生动词**不受影响**。
     同理，Windows 建 symlink 需 `SeCreateSymbolicLinkPrivilege`，Low-IL 进程也拿不到——
     此前记录为「需管理员/重新登录」，R17 证据：High-IL 全量运行的 11 个 skip 恰为 macOS 签名(6)+icon.icns(1)+fcntl(2)+Unix进程树(2)，symlink 类 skip 消失且用例通过，故同样由令牌 IL 决定。
   - **处置（两者均已在仓库固化）**：
     1) `tests/conftest.py` 新增 msys 探测钩子：失败信息含 `NtCreateDirectoryObject` 签名，
        或失败发生在已知依赖 git 传输的 6 个插件测试模块内**且**探测确认本机传输不可用时，
        转成 skip（附原因）。探测通过（传输可用）时钩子完全不介入，真实缺陷照常失败。
     2) 需要真正执行这些用例时，改用 **High-IL 解释器**跑 pytest：
        ```powershell
        cd "F:\DeterminFlow x2\xs2"
        $sp = "$PWD\.venv\Lib\site-packages"
        $env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
        C:\Windows\py.exe -m pytest -q
        ```
        （`py.exe` 是 C: 上的原生启动器，它启动的 venv 包路径解释器仍为 Low IL，
        因此需把 venv 的 site-packages 经 PYTHONPATH 挂到 C: 侧解释器上。）
   - 实测基线：Low-IL（venv）`pytest -q` → **1497 passed / 96 skipped / 0 failed**；
     High-IL（py.exe + PYTHONPATH）同一提交 → **1582 passed / 11 skipped / 0 failed**
     （11 项为 macOS/POSIX 类平台 skip）。

11. **（2026-10-24 R18 实测）PowerShell / .NET `System.Uri` 会剥掉 URL 路径段的尾随点**
    `[System.Uri]"http://host/api/status/welcome."` 的 `AbsolutePath` 是 `/api/status/welcome`
    （`welcome...` 同样被剥成 `welcome`），因此 `Invoke-WebRequest` / `curl`（经 PowerShell
    参数绑定）发出的请求**根本不含尾随点**。后果：对「尾随点别名」这类缺陷做服务侧取证时，
    用 `Invoke-WebRequest` 会得到 **200**，误判成「服务端守卫失效」；实测同一 URL 用 Python
    `urllib` 直连则正确返回 **400**（`%2E` 编码形式亦 400）。
    **验证名字规范化类缺陷必须用不经 .NET URI 解析的客户端**（`urllib.request`、`httpx`，
    或本项目 `tests/test_humanware_e2e.py`）。R17 §3.4「实时取证」表中 3 行以
    `Invoke-WebRequest` 记录的 `welcome.`→200 属该客户端假象，而非服务端行为；R18 予以更正
    （服务端当时已正确 400，见 HANDOVER_ROUND18 §4 R18-ENV-2）。

12. **（2026-10-24 R18 实测）Windows 设备名作为「目录」与作为「文件」语义不同**
    R17 把 `CON`/`PRN`/`AUX`/`COM1`/`LPT1`/`CONIN$` 与 `NUL` 同等对待，实测有偏差：
    - 若已存在真实目录 `<x>\CON`，则 `CON\data.md` 的读写**完全正常**（`is_dir()=True`、
      `iterdir()` 可列出、`\\?\` 前缀读回一致），`mkdir` 亦成功。
    - `NUL` 是唯一「幻影目录」：`mkdir` 静默成功、`exists()` 恒真但 `is_dir()=False`，
      其下任何写入 → `FileNotFoundError(WinError 3)`，`shutil.rmtree` 删不掉。
    - 处置结论不变：一律**拒绝**（保持 R17 已上线的 web 面行为与跨工具一致性——资源管理器
      拒绝创建这些名字），但根因表述以此条为准，不再写作「CON 写入也会静默丢弃」。

13. **（2026-10-24 R20 实测）设备名不只是「路径段」问题，也是「标识符」问题**
    第 12 条讲的是设备名当**路径段**；R20 发现同一族缺陷也出现在**标识符**上——插件 id、
    资源 effective id、市场 Skill id 的合法字符集（kebab-case `^[a-z0-9]+(?:-[a-z0-9]+)*$`）
    与小写设备名同型，`nul`/`con`/`com1` 全部合法，而这些 id 会被直接拼成目录名：
    - **插件 id** → `checkouts/<id>`、`runtime-resources/<id>`、锁文件键。实测
      `prepare_plugin_resources(extension_id="nul")` 报 **WinError 87**、
      `os.replace(... → checkouts/nul/<rev>)` 报 **WinError 3**；两者都是 `OSError`，
      而 `_raise_http_error` 只映射 `ValueError`/`PluginStoreError`/`SourceTrustError`，
      故**逃逸成 HTTP 500 而非 400**。
    - **路径型资源 id**（workflow/script_library/skill/rule）→ `copytree` 目标目录名。
      实测 `copytree(src/nul → dst/nul)` 报 **WinError 1**，留下 `exists()=True` 的幻影，
      内容不可达且 `rmtree(ignore_errors=True)` 静默无效。
    - **市场 Skill id** → `marketplace-skills/<id>`。最隐蔽的一处：**`exists()` 恒真发生在
      任何创建动作之前**（NUL 设备本身），于是 `resolve_openable_skill("nul")` 会返回
      **409「本地存在同名但来源不同的 Skill」**——纯属谎报；该名字被永久占用，既装不上
      也卸不掉。
    - **处置**：三处入口统一拒绝，判定谓词为 `win_names.unsafe_device_name()`，
      **平台无关**（不按 `os.name` 门控）——因为这些 id 是跨平台共享键（写进
      `plugins.lock.json`、registry 清单、`skills_config.json`），条件式校验会让同一份配置
      在 POSIX 有效、在 Windows 永久损坏。仅**路径型**资源才拒；`agent`/`prompt`/
      `preset_phrase` 等纯 JSON 键不拒（否则误伤正文里恰好叫 `nul` 的键）。
