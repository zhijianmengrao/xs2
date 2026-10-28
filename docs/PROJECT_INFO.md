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
- **每轮收官固定动作（R41 起）**：跑 `python scripts/provider_failure_profile.py
  --summary`，把输出的每 workflow 一行 + TOTAL 行贴进当轮交接文档的同口径
  表格——逐轮累积即供应商失败率时间序列（脚本本身严格只读，有测试钉死
  「扫描不改文件树」）。
  **R42 起追加硬闸门**：同一条命令加 `--fail-if-above <PCT>`，总失败率严格
  大于 PCT 时退出码 1，可直接挂进 CI/shell `&&` 链。判据是 TOTAL 口径
  （failed 之和 / attempts 之和，不是逐 workflow 平均），结论文案写 stderr
  使 stdout 的表格与 `--json` 保持纯净。R42 基线 **2.9%**（23 runs / 243
  尝试 / 7 失败），建议阈值 5。
  **R48 起追加快照保鲜**：先重导真实快照
  （`python scripts/export_run_samples.py --dest tests/fixtures/live_snapshot
  --limit 2`），再用 `python scripts/check_live_snapshot_gate.py --check-stale`
  判保鲜（退出码 0 尚新 / 5 过期 / 3 判不到）。**这一步不进 CI**：CI 检出里
  没有 `data/workflows`，接进去只会永远「判不到」。快照不重导不会报错（旧数据
  自身自洽），只是闸门判的判据逐渐失真——`--check-stale` 是唯一能让这件事显形
  的手段。
  **R49 起追加覆盖度判据**：同一条链再加一步
  `python scripts/check_live_snapshot_gate.py --check-coverage`（退出码 0 覆盖
  完整 / 6 缺工作流 / 3 判不到）。它治的是 `--check-stale` 判不到的那一半：
  新增了 workflow 而快照里没有，时间上可能仍然「尚新」，快照却已不代表真实
  覆盖面（HANDOVER_ROUND48 §8-2）。同样是收官动作，**同样不进 CI**（同一条
  理由：CI 无真实数据）。至此收官链为「重导 → 判新鲜 → 判覆盖 → 判失败率」。
- **CI e2e 用桩 provider（R49 起；R50 加故障注入）**：`.github/workflows/ci.yml`
  的 backend job 有一步 `Workflow orchestration e2e (stub provider)`，跑
  `python scripts/e2e_workflow_stub.py`。桩是 `scripts/stub_llm_provider.py`
  ——真实 HTTP + SSE 的 OpenAI 兼容服务，走的是 ChatOpenAI SDK → LangGraph →
  引擎回调的完整链路，只有「谁生成 token」是假的。**这一步不引 secrets**，
  所以 fork PR 也能跑（有测试反向钉死）。本地单跑：
  `python scripts/e2e_workflow_stub.py --verbose`（`--only <场景>` 挑单个
  场景，`--keep-data` 保留临时数据目录）。退出码 0 通过 / 1 编排行为不符 /
  3 环境无法启动。
  **R50 加故障注入**：任务文本里的标记让桩按**真实 provider 的响应格式**报错
  ——`[stub:5xx]`（503 + `service_unavailable`）、`[stub:429]`
  （429 + `rate_limit_exceeded`）、`[stub:401]`（401 + `invalid_api_key`，
  永久错误）、`[stub:stall]`（SSE 头已发、正文停住，触发
  `stream_chunk_timeout`）。加 `[stub:fail_once]` 表示只失败第一发、之后
  正常回复——这是「重试确实救回来了」的唯一可观察证据。新增三场景
  `transient_error_is_retried` / `permanent_error_is_not_retried` /
  `stream_stall_fails_fast`（共 6 个场景）。**判据边界**：transient 场景判的
  是「重试总效果」，不是「Core 层重试」——关掉 `retry.max_retries` 后场景仍绿，
  因为 LangChain 的 ChatOpenAI 自带 `max_retries=2`；Core 层语义由
  `tests/test_llm_client_params.py` 一类单测守。注入的是真实状态码而非自造
  失败类型，仍走完整分类/重试链路（R49 §7-5 拒绝的是伪造失败语义）。
- **画像多 run 基线与趋势（R50）**：`GET /api/workflows/{wf}/tasks/{task}/run-profile`
  新增 `?baseline_limit=N`（N≤20），返回 `baseline` 块：`points`（时间序列，
  含 `is_current`）、`deltas`（相邻差值）、`trend`、`consecutive_required`、
  `baseline_run_ids`。`trend` 四态：`regressing` / `improving`（最近
  `consecutive_required`=2 次相邻对比**全部**同向）/ `stable`（有涨有跌或
  持平）/ `insufficient`（历史不足以构成序列——**不冒充 stable**）。与
  `?compare=true` 独立：comparison 判「比上一步退了没有」，baseline 判
  「是否在连续变坏」。前端运行画像抽屉有「连续趋势（最近 5 次）」开关。
  判据刻意用**连续相邻**而不是「与首个基线比」：后者会被一次偶发尖峰带偏
  （50%→0%→20%→40% 与首点比是改善，实际在退步）。
- **循环轮次与重试语义区分（R50）**：`attempt_history` 每条记录新增
  `loop_iteration`（0 = 非循环节点）。循环体每轮会把 `next_attempt_trigger`
  重置成 `initial`，导致 attempt_history 里「循环第 2 轮」与「第 2 次执行」
  无法区分（R41 §7 观察项）。轮次单独记在 `NodeExecutionState.loop_iteration`
  上，**不影响 trigger 语义**（重试仍由 trigger 表达）。前端尝试明细在轮次
  > 0 时显示「循环第 N 轮」徽章。
- **插件仓推送后必须刷新本仓锁（R42 起）**：凡向 `xs2-plugins` 推送，随后
  在 xs2 跑 `python desktop/scripts/refresh_official_plugin_lock.py` 并提交
  `desktop/official-plugins.lock.json`。该锁决定 Full 版实际捆绑哪个插件
  快照，脱钩会导致 `Desktop Windows` CI 红 **且** 打出的安装包捆绑旧版插件
  （R42 实例：锁停在 0.1.13/`1b42dec`，实际最新已是 0.1.16/`1504a88`）。
- **带 sha256 provenance 的快照入库必须配 `-text`（R42 起）**：凡把记录了文件
  哈希的第三方 vendor 快照提交进仓，必须在该目录的 `.gitattributes` 标
  `-text` 并用 `git add --renormalize` 按真实字节入库。否则
  `core.autocrlf=true` 会把内容存成 LF（哈希基准是 CRLF），**Windows 开发机
  假绿、Linux/CI 必红**——这类缺陷本地跑多少遍都发现不了。
- **POSIX 覆盖的真实边界（R43 起，取代历轮「POSIX 真跑未覆盖」的表述）**：
  CI 的 ubuntu `backend` job 一直在真实 Linux 上跑全量（R43 实测
  **1870 passed / 64 skipped**），POSIX 语义已被覆盖；64 条 skip 的构成是
  Windows 文件系统语义 40 + humanware e2e（服务未运行）17 + macOS 签名 7。
  **剩余缺口**：①容器镜像构建面——**R44 已补齐并由 CI run 40641422351 首次
  真跑验证**（`container-build` job 真 `docker build` + 起容器验行为，见下条）；
  ②真机服务 e2e（17 条需 8021 在跑）；③macOS 桌面签名——**已核对，缺口不成立**
  （见下条）。细节见 HANDOVER_ROUND43 §2 / HANDOVER_ROUND44 §2。
- **macOS 桌面签名面（R44 核对闭合）**：`desktop-macos.yml` 的 run 列表显示
  `total_count=0` **不代表流水线没跑过**——它是 `workflow_call` 型可复用工作流，
  结果并入调用方 run 而不单独计数。真实证据在 `desktop-windows.yml` 的
  `build-macos` job（`if: github.ref_type == 'tag'`）：v1.0.2 tag run
  **40202145251** 中 core / full 两个矩阵**都 success**（各约 6–7 分钟），
  含 `verify_bundle.py --verify-macos-signatures --verify-dmg-container`、
  装载 DMG 后 `codesign --verify --deep --strict` 与安装副本 backend 冒烟。
  结论：macOS 签名/打包链在最近一次发版上是真跑通的真机产物，不是未验证面。
- **容器构建面（R44 起，已由 CI run 40641422351 首次真跑验证）**：`container-config`
  仍只做 compose 语法快校验；另有 `container-build` job 用 buildx（GHA 层缓存）
  真构建镜像并运行
  `scripts/smoke_container.py` 做行为断言——status 契约（process 模式 4/4
  Executor ready、未降级）、内置前端产物（`/` 返回 `/assets/*.js` 而非
  `/src/main.tsx`）、镜像自带 `HEALTHCHECK` 报 healthy、entrypoint 先跑
  session 裁剪再 exec、镜像不含 `tests/`/`pytest.ini` 与预先烘焙的
  `config/models_config.json`。**首次真实构建实测（2026-10-28，run 40641422351，
  job 1m56s）**：全程零 `CACHED`——`npm ci` 实装 497 包 8.6s、`pip install
  -r requirements.lock` 15.0s（正确忽略 win32-only 的 `colorama`/`pywin32`）、
  `exporting layers` 3.9s；冒烟四断言全过（`ready=4/4 degraded=False`、
  `/assets/index-C5eX4JWL.js`、`HEALTHCHECK=healthy`、entrypoint 裁剪证据、
  布局契约成立）。**二次推送（run 40648992383）实测缓存生效**：18 层全部
  `CACHED`（含 `npm ci` 与 `pip install`），耗时降到 **56 秒**，冒烟断言不变。
  因此「增量 1–3 分钟」成立且偏保守；「每推必验」的成本可接受。
  **两条本轮实测出的纪律**：①镜像布局必须在
  启动前对镜像本体探测——`ModelManager` 会在缺失时从模板生成
  `models_config.json`，跑起来之后探测，「不烘焙凭据」这条断言会恒假红；
  ②docker 缺失时脚本退出码 **2**（环境问题），与镜像缺陷的 **1** 分开，
  否则 runner 少装 docker 会被读成产品故障。
- **画像跨 run 对比口径（R43 起）**：`GET .../run-profile?compare=true` 返回
  与「上一次 run」的逐阶段差值。口径=按 node_id 汇总同一 run 内重复执行、
  差值恒 current−previous（正=退步）、未舍入比值算、任一侧无尝试则
  `comparable=false` 且差值为 null（无数据不等于 0%）。缺省不带 `compare`
  时完全不做 `runs/` 扫描。
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
- **R36 收编轮（2026-10-26）**：R34/R35 两轮未提交工作全部落地并补齐文档（此前
  无交接文档）——①**B20**（R34）：清单损坏不再静默重置整书（损坏判定 + `_corrupt`
  标记 + 保存前隔离备份 + 38 条 round34 回归，`553c249`）；②**B21**（R35）：未知
  参数键由谎报 404 改 422 结构化拒因（`aa0e7ec`）；③**B23**（本轮）：钉值测试
  `test_skills_config_matches_versioned_core_catalog` 与产品行为矛盾——社区插件
  安装后扩展宿主合法写入 skills_config.json（extensions.json 启用的 5 个社区插件
  共 24 条目），改为 core 逐字钉死 + 非 core 校验结构（`f59fe30`），基线归零；
  ④**B22 运行时部署缺口闭合**（本轮发现）：R35 的插件修复从未进入
  runtime-resources，且服务进程 Low-IL 令牌下插件 update 端点必崩 msys——处置：
  插件 bump 0.1.15（`6804876`）+ High-IL 进程外 `PluginStore.update` + 重启，
  修复实测落位；⑤R35 观察项「纯 API 跑完进度显 0%」收口（三层处置，归属语义
  零变更）：诚实提示（`6395e43`）+ 新增 `POST /api/novel-console/progress/sync-history`
  显式历史任务登记端点（按 workspace_override 反查完成态任务、只为空缺 stage 补
  refs、幂等；R35 设想的「自动反查」与 test_c16 钉死的流程重置防护正面冲突，故
  定为用户触发，`dd749eb`），r33-flow 活体幂等探针零改动 ✓。
  基线：Low-IL **1788/96/0**、High-IL **1873/11/0（权威）**、插件 94/0、前端
  447/0；活体 e2e 17 passed、B21 活体 422 探针 ✓、审计 [clean]。详见
  docs/HANDOVER_ROUND36.md（§2 记录 High-IL 插件资源刷新方法）。
- **R37 维护轮（2026-10-26，R36 §6 候选落地）**：①修复 **B24**——novel 面
  workspace 覆盖白名单（R33 §3.2）：核心解析器相对 override 收紧到
  `BASE_DIR/data` 之内（越界回退默认路径），console 面 27 个解析点收编
  `_console_root()` 白名单外一律 400 明确拒因；修复前实测
  `data/workspaces/../../<name>` 逃逸到仓库根且被谎报为 0% 书；绝对路径
  DATA_DIR/BASE_DIR 允许面与相对 `data/book/<uuid>` 钉值形态零破坏（插件
  批处理面在用）。新增 9 条回归 + 5 文件夹具同步。②修复 **B25**（插件
  `a101515`，0.1.15→0.1.16）：空书导出拒缩（R33 §3.3）——0 章时任务 failed
  并透出中文拒因，不再写出 0 字节 manuscript.md；插件套件 98/0；High-IL
  进程外 PluginStore.update + 重启后双相活体验证通过。③**stream_chunk_
  timeout 收口**（R33 §3.1）：核实为「已暴露」——Agent 级模型参数动态渲染
  可配、后端全 openai 系适配器已接线（钉测在库）、env var 全局兜底实证；
  `.env.example` 补文档条目，零代码改动。④仓库根残留治理：conftest 探针
  目录钉位 `data/system/test-probes` + 只读 rmtree（41 个 git-transport-
  probe 残留根因），历史残留 50+ 目录清零；插件仓库 gitignore 补
  `/pytest-of-*/`。基线：Low-IL **1797/96/0**（+9 B24 回归）、High-IL
  **1882/11/0（权威）**、插件 98/0、前端 447/0（零改动）；活体 e2e 17
  passed、B24 三形态 400 探针 ✓、B25 双相探针 ✓、审计 [clean]。详见
  docs/HANDOVER_ROUND37.md。
- **R38 维护轮（2026-10-27，R37 §8 候选落地）**：①修复 **B26**——console 读端点
  「查询即建目录 + 谎报 0% 书」（B24 家族残留面）：`resolve_workflow_workspace`
  新增 `create=True` 可选参数（任务执行/建书面语义零变化），`_console_root` 透传，
  13 个 GET 读端点 + sync-history + DELETE 翻转为 `create=False`，GET progress 用
  新增的 `_console_existing_root`（不存在即 **404**）；10 个写端点保持默认。
  修复前实测 `GET progress` 对不存在的书返回 200 并静默建目录——R37 §8.3 的
  `nope_missing` 残留即该机制产物（已一并删除）。新增 6 条回归（9→15），
  7 处测试桩补 `create` 形参。②修复 **B27**（本轮 P0 引入、本轮修）：B26 新用例走
  `PUT /projects` 成功分支，夹具只 patch `DATA_DIR` 未 patch 模块级常量 `_index`，
  把 9 条 pytest 临时路径写进真实 `data/novel-console/workspaces.json`；补
  `_index` patch + 清理污染（教训：写路径用例须审计每个 import 期求值的路径常量）。
  ③**纯 API 全流程实跑收官**（R36 §6 遗留项 5）：新建 r38-flow 书，9 阶段
  build→export 全部 completed，任务时间合计 129.9 分钟（build 2 次、character 3 次
  重试）；终态完整复现 0% 观察项（`percent=0, chapter_count=1, can_download=true`）；
  **真实浏览器走查**登记按钮：0% 诚实提示逐字吻合 → 点击 →「本篇已导出 ·
  已完成 9/9」+ 按钮消失，截图存档；活体幂等二次/三次调用均 `synced: []`。
  ④`stream_chunk_timeout` 实证升级：默认 120s 在 AMD 免费档必然踩雷（build
  `agent_society` 1400+ chunk 后静默 120s），`.env` 设 600s 后跑通，但 600s 仍被打穿
  一次（character `agent_deep`）——供应商分钟级流式停摆，属质量面非代码缺陷。
  ⑤`nope_missing` 残留清理。基线：Low-IL **1803/96/0**、High-IL **1888/11/0（权威）**、
  插件 98/0、前端 447/0（零改动）、审计 [clean]。详见 docs/HANDOVER_ROUND38.md。
- **R40 维护轮（2026-10-28，R39 §6 三候选全落地）**：①契约 §6.1 常驻回归
  基线 R25 起首次专项复跑，四层全绿零未解释差异（L1 24 / L2 活体 17/0
  双轮 / L3 106+1skip / L4 插件 98/0 双 CWD / 审计 [clean]×2）。②
  **B26/B28 同族机械化终局**：`test_read_endpoints_static_guard.py` 以纯
  AST 扫描全部 14 个路由模块（119 GET 处理器、9 resolver 调用点），断言
  GET 处理链可达的 `resolve_workflow_workspace` 必显式 `create=False`
  （含 `_console_root` 参数化传播），防空转下限防改名空转，双变异咬合
  验证零误报。③**供应商失败率画像**（R38 §7.4 落地）：`run_profile.py`
  纯函数聚合 + 只读端点 `GET …/tasks/{id}/run-profile` + 挖矿脚本
  `provider_failure_profile.py`；历史数据复现 R38 §2.0 的 agent_deep
  629.7s timeout；r38-flow 两次 export 实跑产出画像（30s 内完成）。
  ④修复 **B31**——run 记录 `completed_at` 恒空（两条执行路径只给 task
  盖章），`_finalize_run_artifacts` 终态盖章（retry_waiting 不盖），
  画像 wall_seconds 从此可算。基线：Low-IL **1826/96/0**、High-IL
  **1911/11/0（权威）**（对账 1811+15、1896+15）、前端 447/0（零改动）、
  索引 59 条零变化；8021 重启两次均 4/4 ready。运维注意：ZCode 后台
  shell 启动的服务会被连带回收，须 PowerShell Start-Process 脱离启动。
  详见 docs/HANDOVER_ROUND40.md。
- **R39 维护轮（2026-10-28，R38 §7 候选落地 + B26 家族全面收口）**：①修复
  **B28**——B26 的 workflow 面残留：`GET workspace-files`、
  `GET workspace-files/content`、`GET tasks/{id}/workspace-file` 与
  `get_task_result`/`read_task_artifact`（agent 工具面）共 5 处解析翻转
  `create=False`，幻影工作区统一 404「作品工作区不存在」；活体根因=资料蒸馏页
  每次打开以新 `job-<时间戳>` 工作区触发建目录，真实数据残留 4 个
  `reference-jobs/job-*` 空目录 + 5 条索引死条目（本轮清理，索引 64→59，
  备份 `data/system/workspaces.json.r39-bak`）。新增 6 条回归（白名单文件
  15→21）。②修复 **B29**——preflight 暂存目录从 CWD 回落钉位
  `BASE_DIR/data/system/preflight`（锚 BASE_DIR 而非可被 .env 覆盖为相对
  路径的 DATA_DIR）+ `resource_preparation` 四处 copytree/copy2 的 dst 补
  `extended_path`（longpath 教义缺口）；`.env.example` 相对路径覆盖注释化；
  新增 2 条回归。③**B27 家族机械化**：conftest autouse 守卫逐用例对真实
  运行索引做 pytest 临时路径集合差比对，污染即归因报错。④修复 **B30**
  （插件仓 `1504a88`）：资源卫生扫描测试容忍 PermissionError——pytest
  capture 的 TemporaryFile 在本机 %TEMP% 受限时回落 CWD 与扫描碰撞；插件
  套件从插件子目录跑恢复 98/0（此前仅仓库根口径能过）。基线：Low-IL
  **1811/96/0**、High-IL **1896/11/0（权威）**（对账 1803+8、1888+8）、
  插件 **98/0（双 CWD 口径）**、前端 447/0（零改动）、审计 [clean]、
  索引零污染；8021 服务重启加载全部 R39 代码，4/4 执行器 ready、活体
  探针复验通过。详见 docs/HANDOVER_ROUND39.md。
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
- 验证方式：`python -m pytest -q`；`cd web && npm run lint && npm run test:* && npm run build`；`docker compose -f docker-compose.yml config -q`；`docker build -t determinflow-core:local . && python scripts/smoke_container.py --image determinflow-core:local --skip-build`（需 docker，本机不可用；CI 的 `container-build` job 会自动跑）。
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
- 2026-10-27 R38 双基线（维护轮：B26 console 读端点建目录/404 化 + B27 测试索引污染 + 纯 API 全流程实跑 + sync-history UI 走查）：Low-IL → **1803 passed / 96 skipped / 0 failed**（98.64s）；High-IL → **1888 passed / 11 skipped / 0 failed**（118.04s，权威）。净增 **6** 条（`test_workspace_override_whitelist.py` 9→15：create=False 不建目录 1、GET progress 幻影 404 两形态 2、sync-history 幻影 404 1、DELETE 幻影不建目录 1、建书后 progress 仍 200 1）。对账：Low-IL 1797+6=1803；High-IL 1882+6=1888。总用例 R37 口径 1893 → **1899**。前端零改动 `npm test` 8 组 447 条 0 fail、lint 0、build ✓ 5.94s；插件 98/0；审计 [clean]。**全流程实跑**：r38-flow 9/9 阶段 completed（129.9 任务分钟，build 2 次 / character 3 次重试）；终态复现 0% 观察项后经 UI 登记按钮转 100%。详见 HANDOVER_ROUND38.md。
- 2026-10-28 R40 双基线（维护轮：契约 §6.1 基线 R25 起首次专项复跑 + B26/B28 同族静态防复发钉测 + 供应商失败率画像 + B31 run 记录 completed_at 恒空修复）：Low-IL → **1826 passed / 96 skipped / 0 failed**（98.41s）；High-IL → **1911 passed / 11 skipped / 0 failed**（131.38s，权威）。净增 **15** 条（`test_read_endpoints_static_guard.py` 3：GET 链 create≠False 主断言 + 防空转下限 + task_queries 跨模块钉，双变异咬合验证；`test_run_profile.py` 12：聚合五态/分类六桶/B31 引擎盖章/端点 200+404 三态+零建目录）。对账：Low-IL 1811+15=1826；High-IL 1896+15=1911。总用例 R39 口径 1907 → **1922**。§6.1 四层复跑全绿零未解释差异（L1 24 / L2 17/0 双轮 / L3 106+1skip / L4 插件 98/0 双 CWD / 审计 [clean]×2）；前端零改动 447/0、lint 0、build ✓ 5.59s；索引 59 条零变化。**画像实跑**：r38-flow 两次 export 30s 内 completed（run-dfe789fd wall 0.071s，B31 盖章生效）；历史挖矿复现 R38 §2.0 的 agent_deep 629.7s timeout。8021 重启两次均 4/4 ready、degraded=false。详见 HANDOVER_ROUND40.md。
- 2026-10-28 R41 双基线（维护轮：画像三面闭环——`?run_id=` 历史查询 + 前端运行画像抽屉 + 挖矿脚本周期化）：Low-IL → **1833 passed / 96 skipped / 0 failed**（100.54s）；High-IL → **1918 passed / 11 skipped / 0 failed**（131.33s，权威）。净增 **7** 条后端（`test_run_profile.py` 12→14：`?run_id=` 历史 run 查询 1 + 非法入参 400 四形态与幻影 404 1；`test_provider_failure_profile.py` 新增 5：跨 run 汇总口径/limit 按有效解析计数/workflow 过滤/空目录诚实/扫描严格只读）。对账：Low-IL 1826+7=1833；High-IL 1911+7=1918。总用例 R40 口径 1922 → **1929**。前端 **457 passed / 0 fail**（R40 447 → +10：`runProfileView.test.ts` 5 + `RunProfilePanel.test.ts` 5，happy-dom），lint 0、build ✓ 5.53s；插件 98/0 双 CWD；审计 [clean]；索引 59 条零污染。**活体全链路**：8021 新 PID 22200 4/4 ready、degraded=false，e2e 17/0；真实数据探针 `?run_id=run-99b3bd1b` 直达 `agent_deep` 第 3 次 **629.707s timeout**（R38 §2.0 实录），3 种穿越形态全 400、幻影 run 404；浏览器走查抽屉 18 卡/30 尝试与 API 逐项一致，**修掉同名节点重复 key**（`agent_deep`×4 → `#1`–`#4` 序号，活体暴露的真实缺陷），截图 `data/system/test-probes/r41-run-profile-panel.png`。挖矿 `--summary` 首数据点：23 runs / 243 尝试 / 7 失败 / **2.9%**。详见 HANDOVER_ROUND41.md。
- 2026-10-28 R42 双基线（维护轮：首次推送 CI 全量核对收口 + 失败率硬闸门 + 死通道依赖收尾）：Low-IL → **1838 passed / 96 skipped / 0 failed**（102.02s）；High-IL → **1923 passed / 11 skipped / 0 failed**（135.83s，权威）。净增 **5** 条（`test_provider_failure_profile.py` 5→10：严格大于边界/未舍入比较/TOTAL 口径 vs 逐行平均/空样本诚实/结论文案含双数）。对账：Low-IL 1833+5=1838；High-IL 1918+5=1923。总用例 R41 口径 1929 → **1934**。前端零改动 457/0、lint 0、build ✓ 5.88s；插件 98/0 双 CWD；审计 [clean]；索引 59 条零污染。**推送 + CI 核对首次真实触发，暴露并修掉四条从未在本地发现的红**：① xs2 ubuntu `backend` 红于 `test_c19_write_text_rejects_unsafe_paths[references/NUL]`——根因不是产品缺陷，`unsafe_windows_path` 在 POSIX 按设计返回 None，测试把平台专属断言混进跨平台 parametrize，拆档加 `skipif(os.name != "nt")`；② 插件仓 CI **连红 3 次**，`bishu-novel`/`public-api` 两个已删除插件 job 仍在（checkout 即败）且 Core 仓用 `github.repository_owner` 拼出 fork 不存在的 `DeterminFlow`，删 job + 改 `vars.CORE_REPOSITORY || 'alikon-art/DeterminFlow'`，顺带 source-url 改 `${{ github.repository }}`；③ xs2 `Desktop Windows` 红于官方插件构建锁脱钩（locked=1b42dec vs latest=1504a88）——**锁决定 Full 包实际捆绑哪个插件快照，旧锁意味着打的是 0.1.13 而非 0.1.16**，刷新后插件仓 HEAD 再前进又跟一次。**新纪律：推送插件仓后必须刷新本仓锁**。**闸门**：`--fail-if-above <PCT>` 判据为 TOTAL 口径、严格大于、未舍入比较、空样本诚实放行、结论写 stderr（stdout 保持纯 JSON）；真实数据实测 0.1→exit 1（2.88%）、5→exit 0。**死通道**：核实 R2/Gitee 在 v1.0.2 已彻底移除，但发现 3 个孤儿依赖（futures-util/reqwest/semver）零引用，移除并首次装 Rust 1.99.1 + MSVC 验证 `cargo check` **exit 0**；过程中定位两个环境前提——项目路径含空格使 cc-rs 的 `-Fo` 未引号致 ring C 编译失败（须 `CARGO_TARGET_DIR` 指无空格路径）、build.rs 需 generated/bundled-plugins 与 runtime/backend 存在。失败率时间序列第 2 点：2.9% → **2.9%**（与 R41 逐行一致，本轮无新 run）。**CI 最终全绿**：xs2 `CI`（四 job）+ `Desktop Windows`（含 NSIS 与插件锁校验）均 success，插件仓 `CI` **首次绿**（此前连红 4 次）。过程中二次暴露一条只在 CI 可见的缺陷：插件套件 `test_actual_upstream_files_and_runtime_functions` 的 vendor sha256 钉值在 Linux 上必错——`UPSTREAM.json` 记的是 CRLF 原始字节哈希，而仓库 blob 被 `core.autocrlf=true` 存成 LF，本机检出转回 CRLF 故**假绿**；修法是 `.gitattributes` 标 `-text` + `git add --renormalize` 按真实 CRLF 字节入库（模拟 Linux 检出 14/14 匹配）。**新纪律二：带 sha256 provenance 的第三方快照入库必须配 `-text`**。详见 HANDOVER_ROUND42.md。
- 2026-10-28 R43 双基线（维护轮：画像跨 run 对比视图 + POSIX 真跑调研收口）：Low-IL → **1852 passed / 96 skipped / 0 failed**（96.40s）；High-IL → **1937 passed / 11 skipped / 0 failed**（129.80s，权威）。净增 **14** 条（`test_run_profile.py` 14→28：重复节点汇总/改善为负/单侧阶段不可比/空 run 诚实/未舍入差值/`pick_previous_run` 三参数 + mtime 回落/端点 compare 块/无 compare 键/最早 run 为 null/坏兄弟跳过/compare 零建目录）。对账：Low-IL 1838+14=1852；High-IL 1923+14=1937。总用例 R42 口径 1934 → **1948**。前端 **463 passed / 0 fail**（457 → +6：`runProfileView.test.ts` 5→7、`RunProfilePanel.test.ts` 5→9），lint 0、build ✓ 5.62s；插件 98/0 双 CWD；审计 [clean]；索引 59 条零污染。**对比视图**：`?compare=true` 返回与上一次 run 的逐阶段差值，口径=按 node_id 汇总同 run 内重复执行、差值恒 current−previous（正=退步）、未舍入比值、单侧无尝试则 `comparable=false` 且差值 null、缺省不带参数则完全不扫 `runs/`；前端抽屉加复选框 + 汇总对比卡 + 每卡对比行，切换开关时保持当前查看的 run 不跳回最新。**活体**：8021 重启新 PID 26252；真实数据 `run-cef95ebf` vs `run-04ea8e0b` → 总差值 −25%、`script_extract` −100% 修复确认、`agent_belief` 等不可比；最早 run 加 compare → null；穿越 400、幻影 404。**修掉一处活体暴露的文案缺陷**：「尝试 0（上次 1）」被读成尝试数为 0，改为差值 0 显示「持平」。截图 `data/system/test-probes/r43-run-profile-compare.png`。**POSIX 调研（用户指定只调研不实施）推翻了历轮表述**：CI ubuntu `backend` 一直在真实 Linux 跑全量（**1870 passed / 64 skipped**，64 = Windows 文件系统语义 40 + e2e 17 + macOS 7），POSIX 语义已被覆盖；真正的剩余缺口是①**容器镜像从未被构建验证**（`container-config` 只跑 `compose config -q`，`Dockerfile` 多阶段构建零覆盖，本机无 docker/wsl）②真机 e2e 17 条③macOS 签名流水线未核对。失败率时间序列第 3 点：2.9% → **2.9%**（本轮无新 run，与 R41/R42 逐行一致）。详见 HANDOVER_ROUND43.md。
- 2026-10-28 R44 双基线（维护轮：容器构建面补齐 + 大陆下载加速调研）：Low-IL → **1869 passed / 96 skipped / 0 failed**（98.98s）；High-IL → **1954 passed / 11 skipped / 0 failed**（131.71s，权威）。净增 **17** 条（`test_container_build_contract.py` 新增：CI 真构建断言 3 + 判据自身可用 10（含反例）+ 判据与 Dockerfile/entrypoint/compose 不脱钩 4）。对账：Low-IL 1852+17=1869；High-IL 1937+17=1954。总用例 R43 口径 1948 → **1965**。前端零改动 **463 passed / 0 fail**、lint 0、build ✓ 5.59s；插件 98/0 双 CWD；审计 [clean]。**容器构建面**：`ci.yml` 新增 `container-build` job（ubuntu-24.04，30min 超时）——buildx + GHA 层缓存真 `docker build`（`load: true`，tag `determinflow-core:ci`）后跑 `scripts/smoke_container.py` 做行为断言：status 契约（process 模式 configured/member/ready/reachable 全 4、未降级）、内置前端产物（`/` 返回 `/assets/*.js` 且不含 `/src/main.tsx`）、镜像自带 `HEALTHCHECK` 报 healthy、entrypoint 先跑 session 裁剪再 exec、镜像不含 `tests/`/`pytest.ini`/预先烘焙的 `config/models_config.json`；失败时上传 `container-logs` artifact。与 `container-config`（compose 语法快校验）并存而非合并，测试钉死两者都在。**本地无 docker（复核仍不可用）**，改用两条替代取证：①临时目录模拟镜像环境（只放 `config/*` 不含 `models_config.json` + 空 `data/`/`logs/`）起真服务，实测 `/api/system/status` 200、**ready 4/4**、`degraded=false`，`evaluate_status` 零违规；`GET /` 200 产物 `/assets/index-Di62suE6.js`，`GET /docs` 200；②判据双向校准——真实 8021 与 `web/dist/index.html` 上零违规，开发态 `web/index.html` 上正确报出两条违规。**活体暴露并改掉一处设计缺陷**：最初在运行中的容器里 `docker exec test -e` 探测布局，但 `ModelManager` 会在启动时从模板**生成** `config/models_config.json`，「不烘焙凭据」断言恒假红；改为对镜像本体跑一次性 `--rm` 容器、在 teardown 之后探测，并用顺序断言钉死。**大陆下载加速调研（用户指定只调研不实施）**：结论=**当前不实施，触发条件未成立**——更新源已是单源 GitHub（`tauri.conf.json` endpoints 与 `updater.rs` 的 `GITHUB_UPDATE_ENDPOINT`），`updater.rs` 注释钉死「check() 阶段不验签，多源会让上游更高版本号穿透成误报」；`publish_r2_release.py` + `if: vars.R2_DISTRIBUTION_ENABLED == 'true'` 发布步骤已就位，缺的只是仓库 vars/secrets + 域名（约 ¥50+/年，1–2h）。若痛点成真走 R28 §6 选项 B，实施清单含「**必须同时改两处端点**」否则回到多源穿透问题。顺带发现 `scripts/sync_gitee_release.py` 与 `tests/test_gitee_sync_script.py` 属零接线的孤儿残留（本轮只记录未删）。**如实记录的未验证面**：真实 `docker build` 本地从未执行（本机无 docker/wsl），CI 首跑即首次真构建；事前已核对 `web/package*.json` 依赖完全同步（`npm ci` 不会因锁不同步失败）、`requirements.lock` 无排除 Python 3.12 的包。另记录 `uvicorn.workers.UvicornWorker` 在 uvicorn 0.50.2 会发弃用告警（既有 Dockerfile 选择，本轮未改）。失败率时间序列本轮未跑（未产生新 run，纯维护轮）。详见 HANDOVER_ROUND44.md。
- 2026-10-28 R45 双基线（维护轮：三笔技术债收口——uvicorn-worker 迁移 / 孤儿脚本清理 / 闸门空转防护）：Low-IL → **1875 passed / 96 skipped / 0 failed**（103.11s）；High-IL → **1960 passed / 11 skipped / 0 failed**（137.23s，权威）。净增 **+6**（`test_dependency_locks.py` 1→4：Dockerfile 必须用打包版 worker 1 + Dockerfile 声明的 worker class 必须由锁文件提供 1 + txt/双锁版本一致且 uvicorn≥0.36 1；`test_provider_failure_profile.py` 10→15：无样本 exit 3 / 有样本 exit 0 / 超阈优先 exit 1 / 不加开关仍 exit 0 / 单独用 --require-sample 被 argparse 拒 5），同时**净减 2**（删 `tests/test_gitee_sync_script.py`）→ 对账 Low-IL 1869−2+3+5=1875；High-IL 1954−2+3+5=1960。总用例 R44 口径 1965 → **1971**（High passed+skipped：1960+11）。前端零改动 **463 passed / 0 fail**、lint 0、build ✓ 6.37s；插件套件 98/0 双 CWD；插件相关 High-IL `-k plugin` **308 passed / 0 skipped**；存储名审计 [clean]。**A. uvicorn-worker 迁移**：`uvicorn>=0.36` 起 `uvicorn.workers` 已弃用（导入即发 DeprecationWarning）。取证先行——`uvicorn_worker/_workers.py` 与 `uvicorn/workers.py` 逐行 diff **仅差异为删掉那条 warnings.warn**（+两处 URL 注释 + 一个 pragma），故属纯搬家零行为变更；gunicorn 26.0.0 的 `util.load_class` 对点分字符串做 import_module+getattr，新路径符合。Dockerfile `--worker-class` → `uvicorn_worker.UvicornWorker`，`requirements.txt` + `uvicorn-worker==0.4.0`。**锁文件用约束式重编译避免整树漂移**（直接 compile 会连 starlette/pydantic/jiter/orjson/httptools 等 40+ 项一起升级；改用当前锁生成约束文件再 compile，实测两份锁**各只多一行**，传递依赖零变化，且约束式编译可逐字节复现现有锁）。头部注释曾被临时路径污染，已手工恢复规范命令。三处变异验证均咬住（改回旧路径→红；锁里删包→红）。本机 `import uvicorn_worker` 失败于缺 `fcntl`/`pwd`/`socket.AF_UNIX`——**与旧路径同因**（gunicorn 整体 POSIX-only），故 **worker class 能否真起只有 Linux 容器能验**，权威证据在 `container-build` job。**B. 孤儿脚本清理**：删 `scripts/sync_gitee_release.py`（455 行）与 `tests/test_gitee_sync_script.py`（50 行），删前复核 config/.github/src/web/desktop 零引用（仅历轮 HANDOVER 提及，`.github/workflows/` 内零 Gitee 命中）。**C. 闸门空转防护**：R42 已落地 `--fail-if-above`（判据 TOTAL 口径/严格大于/未舍入/空样本诚实放行），真实缺口是 R42 §8-1——CI 克隆无 `data/workflows`（gitignore），挂进 CI 只会「诚实放行」= **静默空转**。新增 `--require-sample`：无样本时退出码 **3**（≠1），四态语义＝有样本未超阈 0 / 有样本超阈 1 / **无样本+开关 3** / 无样本不加开关 0（默认行为不变，有独立测试守）；超阈优先于空转（不会被 3 顶替）；开关必须与 `--fail-if-above` 同用否则 argparse 拒。真实数据实跑（243 尝试/7 失败/2.88%）四态全部成立。**明确未做**：未把闸门挂进 `ci.yml`——接线需先决定「run 记录怎么进 CI」（artifact 聚合 或 提交真实形状 fixture + `DETERMINFLOW_DATA_DIR` 覆盖，`src/config.py:21` 支持），退出码 3 已就位待接。**修正 R44 两处记录**：①「`--fail-if-above` 待做」不成立（R42 已完成），本轮做的是空转面；②本机导入失败不止缺 `fcntl`，还缺 `pwd`/`AF_UNIX`。**失败率时间序列第 4 点**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41/R42/R43 逐行一致，本轮无新 run）。**新发现遗留**：`replace-desktop-assets.yml` 第 114 行 R2 发布步骤**无门控**（常规路径 `desktop-windows.yml` 有 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`），手动触发即写 R2 并切 stable manifest，与「大陆加速维持现状」有歧义。详见 HANDOVER_ROUND45.md。
- 2026-10-28 R46 双基线（维护轮：闸门真正接进 CI + R2 应急通道补门控）：Low-IL → **1884 passed / 96 skipped / 0 failed**（105.16s）；High-IL → **1969 passed / 11 skipped / 0 failed**（141.00s，权威）。净增 **+9**（`test_ci_gate_wiring.py` 新增）：CI 真调用闸门且函数定义带 `--require-sample`、调用点带 `--fail-if-above` 1；`DETERMINFLOW_DATA_DIR` 指向 fixture 且空数据态显式改指 1；0/1/3 三态都被断言 1；fixture 非空且 <200KB 1；fixture 画像可算且含真实失败/错误文本/多 attempt 1；裁剪纪律（正文/轨迹/token 明细不得入库）1；应急通道门控存在 1；常规路径门控不被反向改掉 1；两处 base-url 都取变量且真传给脚本 1。对账：Low-IL 1875+9=1884；High-IL 1960+9=1969。总用例 R45 口径 1971 → **1980**（High passed+skipped：1969+11）。前端零改动 **463 passed / 0 fail**、lint 0、build ✓ 5.79s；插件套件 98/0；存储名审计 [clean]。**A. 闸门接进 CI**：R45 把「无样本空转」做成退出码 3，但闸门仍无任何自动使用者。本轮走 fixture 路线（`src/config.py:21` 的 `DETERMINFLOW_DATA_DIR` 可覆盖 `DATA_DIR`，故 fixture 放 `tests/fixtures/run_samples/workflows/` 即可，**不必破 `data/**` 的 gitignore**；`src/config.py` 的建目录全在 `ensure_dirs()` 函数体内，import 无副作用）。fixture 由 8 个真实 run 裁剪而来（保留 `build_run_profile` 读的字段，删 `summary`/`input_snapshot`/`iteration_history`/`outputs`/`token_usage_calls` 等内容载荷），体积 **11M → 47KB**，且**裁剪前后画像逐字段完全相同**（字典相等，含每次尝试的 trigger/status/error/error_class/duration）——这是「裁剪不改变语义」的直接证据，不靠印象。8 个 run 覆盖 `http_5xx`(2)/`timeout`(2)/`stream_stall`(1)/`other`(2) 与 `agent_deep` 重复执行 4 次，TOTAL **60 尝试 / 7 失败 / 11.67%**。**step 设计的核心取舍**：只加一条 `--fail-if-above 15` 会永远绿（fixture 固定），那正是 R45 §1 说的静默失效；故把三种退出码都真跑一遍——阈值 15→**exit 0**（真判到数据）、阈值 1→**exit 1**（闸门不是恒真）、空目录+`--require-sample`→**exit 3**（没判到东西会显式失败）。本地 Git Bash 等价实跑三态全命中。**判据边界**：fixture 固定，故本 step 保护「闸门与脚本行为不退化」，**不是**「供应商今天健康」；真实数据的失败率判定仍需 run 记录进 CI（artifact 聚合），本轮未做。**B. R2 应急通道补门控**：`replace-desktop-assets.yml` 的 R2 步骤此前**无条件执行**（常规路径 `desktop-windows.yml` 有 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`），任何人手动触发即写线上 R2 并切 stable manifest。本轮补同款门控 + 加注释定性为「应急通道，不属于常规发版路径」；两处 `--public-base-url` 均改为 `${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}`（未设变量时回落既有域名，**行为不变**；设了才改域名，避免两处漂移）。**修正 R45 一处措辞遗漏**：R2 步骤在 `replace-desktop-assets.yml` 的 **`replace`** job、`desktop-windows.yml` 的 **`release`** job（不在 `build`；`build` 有 16 步但零 R2），写静态测试时按「build」取导致首版红——「R2 在哪个 job 里」只能读 yml 确认，不能靠文档措辞推断。**变异验证四个全部咬合**：删应急通道门控→红、去掉 `--require-sample`→红、`DATA_DIR` 改指 `data/`→红、删退出码 3 断言→红。**过程中修掉自身一个断言缺陷**：最初断言「整个 run 块里出现过 `--require-sample`」，变异 2 后**仍全绿**（空数据那行还有该字符串），改为按续行合并后的逻辑命令逐条解析、函数定义与调用点分层断言后才真正咬住——「断言粒度太粗导致变异逃逸」是防回归测试最常见的失效方式。**明确未做**：CI e2e（用户选暂缓，需先定模型凭据方案）、画像对比演进、闸门判真实数据、循环节点重试语义（仍挂起）。**失败率时间序列本轮未跑**（未产生新 run，纯维护轮）。**未验证面**：新 step 未在真实 CI 上跑过（本机无 Actions，只做 Git Bash 等价实跑），yml 解析/`${{ github.workspace }}` 展开/env 传递以推送后 CI 日志为准。详见 HANDOVER_ROUND46.md。
- 2026-10-28 R47 双基线（维护轮：错误分类分层 / 端口 TOCTOU 根治 / 真实快照闸门 / 画像结论层）：Low-IL → **1899 passed / 96 skipped / 0 failed**；High-IL → **1984 passed / 11 skipped / 0 failed**（权威）。总用例 R46 口径 1980 → **1995**。推送 `81b3fbf` 后 CI 五 job 全绿；Desktop Windows 的 core 与 full NSIS **都 success**，即 `backend.rs` 的端口协议重写在真实 Windows runner 上编译并通过冒烟（本机 `cargo check` 卡在 `ring` 的 C 编译，此改动从此不再是未验证项）。真实快照闸门 step 在 GHA 上判出与本地逐数字相同的结论（3.74% / 187 次尝试 / 阈值 13.7%）。详见 HANDOVER_ROUND47.md。
- 2026-10-28 R48 双基线（快照保鲜自动化 `--check-stale`）：Low-IL → **1905 passed / 96 skipped / 0 failed**（118.74s）；High-IL → **1990 passed / 11 skipped / 0 failed**（134.85s，权威）。净增 **+6**（`test_live_snapshot_gate.py` 11→17）。总用例 R47 口径 1995 → **2001**（High passed+skipped：1990+11）。前端零改动 471/0。**核心取舍**：`--check-stale` 只看时间不看覆盖度，且**刻意不接进 CI**（CI 检出无 `data/workflows`，接进去只会永远判不到），加 `test_stale_check_is_not_wired_into_ci` 反向钉死。两个变异均咬合（只读 `completed_at` → 3 红；`EXIT_STALE=1` → 1 红）。推送 `aaec0de` 后 CI 全绿、Desktop Windows 双 NSIS success。详见 HANDOVER_ROUND48.md。
- 2026-10-28 R49 双基线（CI e2e 桩 provider + 快照覆盖度退出码 6 + macOS 触发误记纠正）：Low-IL → **1925 passed / 96 skipped / 0 failed**（124.90s）；High-IL → **2010 passed / 11 skipped / 0 failed**（142.19s，权威）。净增 **+20**（`test_ci_e2e_stub.py` 新文件 12 + `test_live_snapshot_gate.py` 覆盖度 7 + `test_desktop_packaging.py` macOS 触发 1），零删除。总用例 R48 口径 2001 → **2021**（High passed+skipped：2010+11）。前端零改动 **471 passed / 0 fail**。**A. CI e2e（连续三轮 R45/R46/R47 挂着的缺口）**：卡点一直是凭据（fork PR 拿不到 secrets），本轮用 `scripts/stub_llm_provider.py`（真实 HTTP + SSE 的 OpenAI 兼容桩，纯标准库，无新依赖）解开。`scripts/e2e_workflow_stub.py` 在**独立进程 + 临时 `DETERMINFLOW_DATA_DIR`** 里装配真组件（SessionManager / WorkflowManager / Engine / AgentNode / ToolRegistry 35 个真工具 / PromptBuilder），走完整链路 ChatOpenAI SDK → LangGraph → 工具调用 → 引擎回调 → Task 落盘，只有「谁生成 token」是假的。三场景：`happy_path`（2 agent + 1 script 全 completed，且 `{{writer_output}}` 已解析、上游文本真的出现在下游模型请求里）/ `failure_propagates`（`[stub:fail]` 节点 failed、下游未执行、任务未 completed）/ `turn_terminates`（关 auto_flow 仍收敛，请求数 ≤8）。独立进程而非 pytest 用例的理由：`src/config.py` 在 import 期就把 DATA_DIR/WORKFLOWS_DIR 求值成常量，进程内只能逐个 monkeypatch 十来个模块常量（每加模块漏一处）且会污染同进程后续用例。接进 `ci.yml` backend job 第八步（`timeout-minutes: 10`），**不引 secrets**（有测试反向钉死）。**过程中改掉自己一个坏取舍**：初版把退出码 3 降级成 warning 级提示 + `exit 0`，随即发现那正是历轮批评的「永远绿的防护」（环境起不来通常是 import 链断了，本身就是回归），改为全部透传并加 `test_ci_e2e_step_is_not_a_permanently_green_step` 反向钉死不得 exit 0、不得降级成 warning。**B. 快照覆盖度 `--check-coverage`（退出码 6，用户拍定单独成码）**：治的是 `--check-stale` 判不到的那一半——新增 workflow 而快照里没有，时间上可能仍「尚新」却已不代表覆盖面（R48 §8-2）。判据是「真实有 run 的工作流名集合 − 快照同名集合」，只判单向（快照独有项不报，那只是冗余样本）。6 与 5 必须分开：5 是重导就好，6 还要看新工作流是否真进了样本。同样不进 CI（同一条理由）。本机真实数据实跑：覆盖完整 → 0；手工造一个多出来的 workflow → **6**（实跑确认，非仅单测）。**C. 纠正 R48 一处误记**：R48 §8-4/§9-3 把 `desktop-macos.yml` 记成 tag-only，据此把「`--port 0` 在 macOS 未复核」又挂一轮。实际读文件：它是 `workflow_dispatch` + `workflow_call` + `pull_request(paths: desktop/**)`，**没有** tag 触发器。本轮不改 workflow（本来不需要改），加测试钉死「可手动触发 / PR 路径含 desktop/** / 无 tags 过滤器」。**四个变异全部咬合**：桩忽略 `role=tool` → `turn_terminates` 红（10 次请求 > 8）；桩忽略 `[stub:fail]` → `failure_propagates` 红；覆盖度集合方向反 → 4 红；`EXIT_COVERAGE_GAP=5` → 1 红。第一个变异是本轮最关键的验证：没有请求数上限，桩写错会让三场景全绿而 CI 只是在空转。**失败率时间序列**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41–R48 逐行一致，本轮无新 run）。**未验证面**：新 e2e step 未在真实 GHA 上跑过（本机无 Actions，只做本机三场景实跑 + yml 结构校验）；macOS 仍只是「可手动触发」而**未真触发过**，`process_group(0)` 在 darwin 上的缺口从「不可验证」降级为「可验证但本轮没做」。详见 HANDOVER_ROUND49.md。
- 2026-10-29 R50 双基线（桩故障注入 + 画像多 run 基线 + macOS `--port 0` 实证 + 循环轮次语义）：Low-IL → **1945 passed / 96 skipped / 0 failed**（117.88s）；High-IL → **2030 passed / 11 skipped / 0 failed**（134.21s，权威）。净增 **+20**（`test_ci_e2e_stub.py` 故障注入 8 + `test_run_profile.py` 多 run 基线 8 + `test_workflow_failure_policy.py` 循环轮次 2 + `test_workflow_loop_rejections.py` 1 + `test_desktop_packaging.py` macOS `--port 0` 契约 1），零删除。总用例 R49 口径 2021 → **2041**（High passed+skipped：2030+11）。前端 **475 passed / 0 fail**（471 + 4：baseline 开关/序列/insufficient 三态 + 循环轮次徽章）。**A. R49 遗留的唯一未验证项已关闭**：推送 `8727da3` 后 GHA run **40723820649** 的 backend job 第 9 步 `Workflow orchestration e2e (stub provider)` **真跑并 success**，日志三场景输出与本机逐字一致（4/2/2 次请求，3/3 通过）。同时确认 `desktop-windows.yml` 的 paths 过滤未被本轮改动带起（只触发 CI）。**B. macOS `--port 0` 缺口关闭**：手动触发 `desktop-macos.yml`（run **40723984654**，不打 tag、不产发布物），`Build Apple Silicon full candidate` **success**，四步 smoke 全绿——`smoke_backend.py` 确实以 `--port 0` 启动冻结后端并读到 `config/backend-port`；新增契约测试钉死「workflow 调了 smoke」+ 「脚本真传 `--port 0`」两层，避免只验前者造成「已覆盖」的假象。**C. 桩故障注入**：按真实 provider 响应格式注入 503/429/401/SSE 停摆 + `[stub:fail_once]`，三个新场景。**四个变异中三个咬合、一个不咬合并由此发现真问题**：关掉 Core `retry.max_retries` 后 transient 场景**仍绿**——因为 ChatOpenAI 自带 `max_retries=2`；同时关掉两层才红（1 次请求、任务 failed）。这条已写进场景 docstring 与 PROJECT_INFO，避免下一轮把它误当 Core 层守卫。其余咬合：`is_permanent_provider_error` 恒 False → 3 次请求红；停摆不发 chunk（走 httpx 读超时）→ 3 次请求红；401 伪装成 5xx 类**没咬合**（分类以 HTTP 状态码为准，说明该变异本身不是有效变异）。**D. 画像多 run 基线**：`pick_recent_runs` + `compare_run_baseline`，trend 四态，端点 `?baseline_limit=N`。两个变异咬合：改成「与首个基线比」→ 2 红（含尖峰用例）；`insufficient` 改 `stable` → 3 红。真实数据实跑 `xs2-novel-flywheel-build`：6 点 / 5 次可比差 / trend `stable`；端点 TestClient 验证 baseline 与 comparison 相互独立、`baseline_limit=0` 不返回。**E. 循环轮次语义**：`attempt_history` 加 `loop_iteration`，变异（不写轮次）→ 1 红；前端变异（不渲染徽章）→ 1 红。**失败率时间序列**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41–R49 一致，本轮无新 run）。**未做面**：未重导快照（两条判据都绿）、未跑 `docker build`、未重启 8021（改动不涉运行时代码）、macOS run 40723984654 的**总体 conclusion 是 failure**，但原因是 core candidate job 被 GHA 并发策略 **cancelled**（full candidate job 本身 success）；两者跑同一份 `smoke_backend.py`，`--port 0` 结论由 full 支撑，勿把 run 级 failure 读成「macOS 验证失败」。详见 HANDOVER_ROUND50.md。
- 2026-10-28 R44 CI 核对（推送闭环：R43 `1bb2880` + R44 `2b5bba6` 首次一起进 CI）：
  xs2 `CI` run **40641422351**（`2b5bba6`）**五 job 全绿**——`backend` 1901 passed /
  64 skipped（76.44s）、`windows-backend` 1936 / 29（186.83s）、`frontend` 463 / 0、
  `container-config`（`compose config -q`）、**`container-build`（首次真构建 + 冒烟，1m56s）**。
  四口径总数均为 **1965**（ubuntu 1901+64、windows 1936+29、本机 Low-IL 1869+96、
  High-IL 1954+11），与本机双基线逐项对齐。win-29 与本机 High-11 的 18 条差额构成
  已逐条核对：humanware e2e **17**（CI 无 8021 服务，诚实 skip）+ `test_plugin_longpath`
  **1**（CI runner 已启用 `LongPathsEnabled`，`MAX_PATH` 用例按设计 skip）。剩余 11 条
  与本机 High-IL 完全一致（macOS 签名 6 + macOS icns 1 + Unix 进程组/进程树 2 +
  POSIX fcntl 2）。
  `Desktop Windows` run **40641422247**（同 sha）success。
  **同轮闭合 R43 缺口 3**：`desktop-macos.yml` 是 `workflow_call` 型，run 列表
  `total_count=0` 属正常；真实结果在 v1.0.2 tag run **40202145251** 的
  `build-macos` job——core / full 双矩阵均 success，签名与 DMG 校验真跑。详见
  HANDOVER_ROUND44 §9（本轮补记）。
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
