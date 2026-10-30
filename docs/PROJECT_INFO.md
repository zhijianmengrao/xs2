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
  **R51 起追加样本量判据**：`python scripts/check_live_snapshot_gate.py
  --check-sample-size`（退出码 0 足够 / 7 太薄 / 3 无样本 / 4 元数据漂移）。
  前面几条都在判「这个数字合不合格」，这一条判「这个数字的精度够不够当基线」：
  快照只有 14 次尝试、1 次失败时实测 7.1% 只是粗估，重导一次就可能变成 0% 或
  21%。**判据没有写死的样本量常量**——有失败时要求失败率 95% 半宽 ≤ `--margin`，
  零失败时改用 Clopper-Pearson 单侧上界（正态近似在零失败下恒给 0，那是个恒绿
  的坑：2 次尝试 0 失败若判合格，真实上界其实高达 78%）。它判精度不判条数——
  一次 run 里 50 次尝试不比 5 次 run 共 10 次尝试差。
  **R51 起它是第一条进 CI 的快照判据**（`ci.yml` 的 `Snapshot sample-size gate`），
  因为它只读快照自身、不需要 `data/workflows`。R54 的 per-workflow 样本量、
  R56/R58 的 per-workflow 失败率硬门槛与 R59 的历史基线回归同样只读快照自身，
  现在也都在 CI 里。该 step 双向验证：默认余量必须
  通过，收紧到 `--margin 2` 必须触发退出码 7——只跑前者会得到一个恒绿步骤。
  **R52 起在 Windows runner 上也判**：`windows-backend` job 有同名 step（PowerShell
  写法），补掉 R51 §10-1 记的「只在 ubuntu 判」缺口。判据只用 `math` 与四则运算，
  看着与平台无关——但那正是单环境验证最容易漏掉的地方（stderr 编码、路径分隔、
  浮点格式化任一隐含假设只在另一个 runner 上才显形）。该 step 里显式把
  `$ErrorActionPreference` 降成 `Continue`：反向验证要求被测脚本**故意**以 7
  退出，而 pwsh 默认的 `Stop` 会把它包成 NativeCommandError，让这一步在判据
  正常工作时反而红。
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
  **R51 加退避场景 `retry_backoff_is_honoured`（共 7 个场景）**：差分测量同一
  场景在 `delays=[0]` 与 `delays=[1.2]` 下的请求间隔（桩在收包时打 monotonic
  时间戳），比的是「多出来的等待」≈ 配置值。**必须配 `retry.sdk_max_retries=0`**：
  SDK 层若开着会用自身指数退避抢先救回，实测 sdk=2 + core delays=[3.0] 时间隔
  只有 0.48s，Core 的 3 秒一次都没被等到——这正是 R50 §3.4「关掉 Core
  max_retries 后仍绿」的根因。该配置项**默认不出现**（不写就不改 SDK 策略），
  因为它被纳入 `model_runtime_sha256`——无条件多一个键会让在途任务 resume 时
  被判「运行身份漂移」而拒绝启动（fail-closed 守卫）。
  **R52 加退避形状场景 `retry_backoff_shape_is_honoured`（共 8 个场景）**：
  R51 那个场景只判**单点幅度**（配了 1.2s 就等到 1.2s），对形状完全失明——
  `[0.4,0.8]`（指数）、`[0.4,0.4]`（恒定）、`[0.8,0.4]`（倒着来）在它眼里只是
  「某个值被等过」。形状场景让桩**失败两次**（新标记 `[stub:fail_twice]`，配额
  计数而非集合）以产生两个退避段，配置 `delays=[0.4, 0.8]`，断言第二段 ≥
  第一段 1.5 倍。用**比值**不用绝对差值：JIT/日志/调度会让两段同时偏移一个
  共模量，比值对它不敏感，而恒定（1.0）与递减（0.5）仍被 1.5 的门槛分开。
  本机实测 `[0.41, 0.816]`。
  **R53 再加三段场景 `retry_backoff_long_chain_shape_is_honoured`（共 9 个场景）**：
  两段判据抓不到「只在长链后段显形」的回归（`delays` 只读前两项、循环边界少
  一次、填充逻辑补错第三项）——那些在 `max_retries=2` 下第三段根本不存在。
  新标记 `[stub:fail_thrice]`（配额 3）+ `delays=[0.4, 0.8, 1.6]`，逐对判
  1→2、2→3 都递增。判据抽成 `_rising_shape_violations(segments, configured,
  min_ratio=1.5)` 与两段场景**共用**——各写一份阈值迟早漂移成两套。顺带修正
  一处隐患：多标记并存时取**最大**配额而非字典序第一个（`[stub:fail_once]
  [stub:fail_thrice]` 这种复制粘贴残留若取到 1，形状判据会报「段数不够」而不是
  「配额写错」，把配置笔误伪装成实现回归）。GHA 实测 `[0.406, 0.806, 1.606]`。
- **画像趋势接入任务列表（R51）**：`GET .../tasks?with_trend=true&baseline_limit=N`
  与 `GET /api/tasks?with_trend=true`（全局）给每条任务附 `trend` 块，字段刻意
  比抽屉的 `baseline` 窄（`trend`/`run_id`/`consecutive_required`/
  `points_considered`/`comparisons`/`delta_failure_rate`）——一页 20 条塞每阶段
  明细只会让响应膨胀。**默认关**：算趋势要扫 workflow 的 `runs/` 目录并解析
  run JSON，是列表端点里最重的一段 I/O，而列表的主要用途（找任务、点进去）
  不需要它。实现上是**按 workflow 分组、每目录扫一次**，并按 `run_id` 缓存画像
  （多个任务常指向同一批 run）——逐任务调 run-profile 等于把同一目录读 N 次。
  前端任务历史加「标注连续退步」开关，只有 `regressing` 渲染徽章
  （`data-trend`）：`insufficient` 是「判不了」，挂徽章会被读成「有问题」。
  **R52 加正交的第二个信号「最近 N 次全失败」**（`consecutive_failed` /
  `all_failed` / `all_failed_required`，N = `FAILURE_STREAK_REQUIRED` = 3）：
  `trend` 比的是失败率的**相邻差值**，所以一个每次都 100% 失败的工作流差值恒为
  0、判成 `stable`——「一直在全挂」在趋势里是隐形的。这正是 R45/R46/R47 反复
  批评的那类盲区（判据只回答了「有没有在变坏」，没回答「现在是不是全坏」）。
  它单独成字段而不是并进 `trend`（R51 §10-7 已因「两个指标混进一个字段会让
  语义变糊」拒绝过耗时趋势，同一理由的第二次实例）。`failure_streak()` 只认
  `failed`：`stopped`（人工停止）与 `running`/`pending`（还没结论）都不是失败
  证据，算进去会让「我手动停了一个任务」变成运维告警；`required=0` 永不成立
  （不等于「一律告警」）。前端徽章 `data-all-failed`，文案「连续 N 次全失败」，
  门槛值由后端给、前端不重算（两处阈值迟早漂移）。
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
- 2026-10-28 R45 双基线（维护轮：三笔技术债收口——uvicorn-worker 迁移 / 孤儿脚本清理 / 闸门空转防护）：Low-IL → **1875 passed / 96 skipped / 0 failed**（103.11s）；High-IL → **1960 passed / 11 skipped / 0 failed**（137.23s，权威）。净增 **+6**（`test_dependency_locks.py` 1→4：Dockerfile 必须用打包版 worker 1 + Dockerfile 声明的 worker class 必须由锁文件提供 1 + txt/双锁版本一致且 uvicorn≥0.36 1；`test_provider_failure_profile.py` 10→15：无样本 exit 3 / 有样本 exit 0 / 超阈优先 exit 1 / 不加开关仍 exit 0 / 单独用 --require-sample 被 argparse 拒 5），同时**净减 2**（删 `tests/test_gitee_sync_script.py`）→ 对账 Low-IL 1869−2+3+5=1875；High-IL 1954−2+3+5=1960。总用例 R44 口径 1965 → **1971**（High passed+skipped：1960+11）。前端零改动 **463 passed / 0 fail**、lint 0、build ✓ 6.37s；插件套件 98/0 双 CWD；插件相关 High-IL `-k plugin` **308 passed / 0 skipped**；存储名审计 [clean]。**A. uvicorn-worker 迁移**：`uvicorn>=0.36` 起 `uvicorn.workers` 已弃用（导入即发 DeprecationWarning）。取证先行——`uvicorn_worker/_workers.py` 与 `uvicorn/workers.py` 逐行 diff **仅差异为删掉那条 warnings.warn**（+两处 URL 注释 + 一个 pragma），故属纯搬家零行为变更；gunicorn 26.0.0 的 `util.load_class` 对点分字符串做 import_module+getattr，新路径符合。Dockerfile `--worker-class` → `uvicorn_worker.UvicornWorker`，`requirements.txt` + `uvicorn-worker==0.4.0`。**锁文件用约束式重编译避免整树漂移**（直接 compile 会连 starlette/pydantic/jiter/orjson/httptools 等 40+ 项一起升级；改用当前锁生成约束文件再 compile，实测两份锁**各只多一行**，传递依赖零变化，且约束式编译可逐字节复现现有锁）。头部注释曾被临时路径污染，已手工恢复规范命令。三处变异验证均咬住（改回旧路径→红；锁里删包→红）。本机 `import uvicorn_worker` 失败于缺 `fcntl`/`pwd`/`socket.AF_UNIX`——**与旧路径同因**（gunicorn 整体 POSIX-only），故 **worker class 能否真起只有 Linux 容器能验**，权威证据在 `container-build` job。**B. 孤儿脚本清理**：删 `scripts/sync_gitee_release.py`（455 行）与 `tests/test_gitee_sync_script.py`（50 行），删前复核 config/.github/src/web/desktop 零引用（仅历轮 HANDOVER 提及，`.github/workflows/` 内零 Gitee 命中）。**C. 闸门空转防护**：R42 已落地 `--fail-if-above`（判据 TOTAL 口径/严格大于/未舍入/空样本诚实放行），真实缺口是 R42 §8-1——CI 克隆无 `data/workflows`（gitignore），挂进 CI 只会「诚实放行」= **静默空转**。新增 `--require-sample`：无样本时退出码 **3**（≠1），四态语义＝有样本未超阈 0 / 有样本超阈 1 / **无样本+开关 3** / 无样本不加开关 0（默认行为不变，有独立测试守）；超阈优先于空转（不会被 3 顶替）；开关必须与 `--fail-if-above` 同用否则 argparse 拒。真实数据实跑（243 尝试/7 失败/2.88%）四态全部成立。**明确未做**：未把闸门挂进 `ci.yml`——接线需先决定「run 记录怎么进 CI」（artifact 聚合 或 提交真实形状 fixture + `DETERMINFLOW_DATA_DIR` 覆盖，`src/config.py:21` 支持），退出码 3 已就位待接。**修正 R44 两处记录**：①「`--fail-if-above` 待做」不成立（R42 已完成），本轮做的是空转面；②本机导入失败不止缺 `fcntl`，还缺 `pwd`/`AF_UNIX`。**失败率时间序列第 4 点**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41/R42/R43 逐行一致，本轮无新 run）。**新发现遗留**：`replace-desktop-assets.yml` 第 114 行 R2 发布步骤**无门控**（常规路径 `desktop-windows.yml` 有 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`），手动触发即写 R2 并切 stable manifest，与「大陆加速维持现状」有歧义。详见 HANDOVER_ROUND45.md。
- 2026-10-28 R46 双基线（维护轮：闸门真正接进 CI + R2 应急通道补门控）：Low-IL → **1884 passed / 96 skipped / 0 failed**（105.16s）；High-IL → **1969 passed / 11 skipped / 0 failed**（141.00s，权威）。净增 **+9**（`test_ci_gate_wiring.py` 新增）：CI 真调用闸门且函数定义带 `--require-sample`、调用点带 `--fail-if-above` 1；`DETERMINFLOW_DATA_DIR` 指向 fixture 且空数据态显式改指 1；0/1/3 三态都被断言 1；fixture 非空且 <200KB 1；fixture 画像可算且含真实失败/错误文本/多 attempt 1；裁剪纪律（正文/轨迹/token 明细不得入库）1；应急通道门控存在 1；常规路径门控不被反向改掉 1；两处 base-url 都取变量且真传给脚本 1。对账：Low-IL 1875+9=1884；High-IL 1960+9=1969。总用例 R45 口径 1971 → **1980**（High passed+skipped：1969+11）。前端零改动 **463 passed / 0 fail**、lint 0、build ✓ 5.79s；插件套件 98/0；存储名审计 [clean]。**A. 闸门接进 CI**：R45 把「无样本空转」做成退出码 3，但闸门仍无任何自动使用者。本轮走 fixture 路线（`src/config.py:21` 的 `DETERMINFLOW_DATA_DIR` 可覆盖 `DATA_DIR`，故 fixture 放 `tests/fixtures/run_samples/workflows/` 即可，**不必破 `data/**` 的 gitignore**；`src/config.py` 的建目录全在 `ensure_dirs()` 函数体内，import 无副作用）。fixture 由 8 个真实 run 裁剪而来（保留 `build_run_profile` 读的字段，删 `summary`/`input_snapshot`/`iteration_history`/`outputs`/`token_usage_calls` 等内容载荷），体积 **11M → 47KB**，且**裁剪前后画像逐字段完全相同**（字典相等，含每次尝试的 trigger/status/error/error_class/duration）——这是「裁剪不改变语义」的直接证据，不靠印象。8 个 run 覆盖 `http_5xx`(2)/`timeout`(2)/`stream_stall`(1)/`other`(2) 与 `agent_deep` 重复执行 4 次，TOTAL **60 尝试 / 7 失败 / 11.67%**。**step 设计的核心取舍**：只加一条 `--fail-if-above 15` 会永远绿（fixture 固定），那正是 R45 §1 说的静默失效；故把三种退出码都真跑一遍——阈值 15→**exit 0**（真判到数据）、阈值 1→**exit 1**（闸门不是恒真）、空目录+`--require-sample`→**exit 3**（没判到东西会显式失败）。本地 Git Bash 等价实跑三态全命中。**判据边界**：fixture 固定，故本 step 保护「闸门与脚本行为不退化」，**不是**「供应商今天健康」；真实数据的失败率判定仍需 run 记录进 CI（artifact 聚合），本轮未做。**B. R2 应急通道补门控**：`replace-desktop-assets.yml` 的 R2 步骤此前**无条件执行**（常规路径 `desktop-windows.yml` 有 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`），任何人手动触发即写线上 R2 并切 stable manifest。本轮补同款门控 + 加注释定性为「应急通道，不属于常规发版路径」；两处 `--public-base-url` 均改为 `${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}`（未设变量时回落既有域名，**行为不变**；设了才改域名，避免两处漂移）。**修正 R45 一处措辞遗漏**：R2 步骤在 `replace-desktop-assets.yml` 的 **`replace`** job、`desktop-windows.yml` 的 **`release`** job（不在 `build`；`build` 有 16 步但零 R2），写静态测试时按「build」取导致首版红——「R2 在哪个 job 里」只能读 yml 确认，不能靠文档措辞推断。**变异验证四个全部咬合**：删应急通道门控→红、去掉 `--require-sample`→红、`DATA_DIR` 改指 `data/`→红、删退出码 3 断言→红。**过程中修掉自身一个断言缺陷**：最初断言「整个 run 块里出现过 `--require-sample`」，变异 2 后**仍全绿**（空数据那行还有该字符串），改为按续行合并后的逻辑命令逐条解析、函数定义与调用点分层断言后才真正咬住——「断言粒度太粗导致变异逃逸」是防回归测试最常见的失效方式。**明确未做**：CI e2e（用户选暂缓，需先定模型凭据方案）、画像对比演进、闸门判真实数据、循环节点重试语义（仍挂起）。**失败率时间序列本轮未跑**（未产生新 run，纯维护轮）。**未验证面**：新 step 未在真实 CI 上跑过（本机无 Actions，只做 Git Bash 等价实跑），yml 解析/`${{ github.workspace }}` 展开/env 传递以推送后 CI 日志为准。详见 HANDOVER_ROUND46.md。
- 2026-10-28 R47 双基线（维护轮：错误分类分层 / 端口 TOCTOU 根治 / 真实快照闸门 / 画像结论层）：Low-IL → **1899 passed / 96 skipped / 0 failed**；High-IL → **1984 passed / 11 skipped / 0 failed**（权威）。总用例 R46 口径 1980 → **1995**。推送 `81b3fbf` 后 CI 五 job 全绿；Desktop Windows 的 core 与 full NSIS **都 success**，即 `backend.rs` 的端口协议重写在真实 Windows runner 上编译并通过冒烟（本机 `cargo check` 卡在 `ring` 的 C 编译，此改动从此不再是未验证项）。真实快照闸门 step 在 GHA 上判出与本地逐数字相同的结论（3.74% / 187 次尝试 / 阈值 13.7%）。详见 HANDOVER_ROUND47.md。
- 2026-10-28 R48 双基线（快照保鲜自动化 `--check-stale`）：Low-IL → **1905 passed / 96 skipped / 0 failed**（118.74s）；High-IL → **1990 passed / 11 skipped / 0 failed**（134.85s，权威）。净增 **+6**（`test_live_snapshot_gate.py` 11→17）。总用例 R47 口径 1995 → **2001**（High passed+skipped：1990+11）。前端零改动 471/0。**核心取舍**：`--check-stale` 只看时间不看覆盖度，且**刻意不接进 CI**（CI 检出无 `data/workflows`，接进去只会永远判不到），加 `test_stale_check_is_not_wired_into_ci` 反向钉死。两个变异均咬合（只读 `completed_at` → 3 红；`EXIT_STALE=1` → 1 红）。推送 `aaec0de` 后 CI 全绿、Desktop Windows 双 NSIS success。详见 HANDOVER_ROUND48.md。
- 2026-10-28 R49 双基线（CI e2e 桩 provider + 快照覆盖度退出码 6 + macOS 触发误记纠正）：Low-IL → **1925 passed / 96 skipped / 0 failed**（124.90s）；High-IL → **2010 passed / 11 skipped / 0 failed**（142.19s，权威）。净增 **+20**（`test_ci_e2e_stub.py` 新文件 12 + `test_live_snapshot_gate.py` 覆盖度 7 + `test_desktop_packaging.py` macOS 触发 1），零删除。总用例 R48 口径 2001 → **2021**（High passed+skipped：2010+11）。前端零改动 **471 passed / 0 fail**。**A. CI e2e（连续三轮 R45/R46/R47 挂着的缺口）**：卡点一直是凭据（fork PR 拿不到 secrets），本轮用 `scripts/stub_llm_provider.py`（真实 HTTP + SSE 的 OpenAI 兼容桩，纯标准库，无新依赖）解开。`scripts/e2e_workflow_stub.py` 在**独立进程 + 临时 `DETERMINFLOW_DATA_DIR`** 里装配真组件（SessionManager / WorkflowManager / Engine / AgentNode / ToolRegistry 35 个真工具 / PromptBuilder），走完整链路 ChatOpenAI SDK → LangGraph → 工具调用 → 引擎回调 → Task 落盘，只有「谁生成 token」是假的。三场景：`happy_path`（2 agent + 1 script 全 completed，且 `{{writer_output}}` 已解析、上游文本真的出现在下游模型请求里）/ `failure_propagates`（`[stub:fail]` 节点 failed、下游未执行、任务未 completed）/ `turn_terminates`（关 auto_flow 仍收敛，请求数 ≤8）。独立进程而非 pytest 用例的理由：`src/config.py` 在 import 期就把 DATA_DIR/WORKFLOWS_DIR 求值成常量，进程内只能逐个 monkeypatch 十来个模块常量（每加模块漏一处）且会污染同进程后续用例。接进 `ci.yml` backend job 第八步（`timeout-minutes: 10`），**不引 secrets**（有测试反向钉死）。**过程中改掉自己一个坏取舍**：初版把退出码 3 降级成 warning 级提示 + `exit 0`，随即发现那正是历轮批评的「永远绿的防护」（环境起不来通常是 import 链断了，本身就是回归），改为全部透传并加 `test_ci_e2e_step_is_not_a_permanently_green_step` 反向钉死不得 exit 0、不得降级成 warning。**B. 快照覆盖度 `--check-coverage`（退出码 6，用户拍定单独成码）**：治的是 `--check-stale` 判不到的那一半——新增 workflow 而快照里没有，时间上可能仍「尚新」却已不代表覆盖面（R48 §8-2）。判据是「真实有 run 的工作流名集合 − 快照同名集合」，只判单向（快照独有项不报，那只是冗余样本）。6 与 5 必须分开：5 是重导就好，6 还要看新工作流是否真进了样本。同样不进 CI（同一条理由）。本机真实数据实跑：覆盖完整 → 0；手工造一个多出来的 workflow → **6**（实跑确认，非仅单测）。**C. 纠正 R48 一处误记**：R48 §8-4/§9-3 把 `desktop-macos.yml` 记成 tag-only，据此把「`--port 0` 在 macOS 未复核」又挂一轮。实际读文件：它是 `workflow_dispatch` + `workflow_call` + `pull_request(paths: desktop/**)`，**没有** tag 触发器。本轮不改 workflow（本来不需要改），加测试钉死「可手动触发 / PR 路径含 desktop/** / 无 tags 过滤器」。**四个变异全部咬合**：桩忽略 `role=tool` → `turn_terminates` 红（10 次请求 > 8）；桩忽略 `[stub:fail]` → `failure_propagates` 红；覆盖度集合方向反 → 4 红；`EXIT_COVERAGE_GAP=5` → 1 红。第一个变异是本轮最关键的验证：没有请求数上限，桩写错会让三场景全绿而 CI 只是在空转。**失败率时间序列**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41–R48 逐行一致，本轮无新 run）。**未验证面**：新 e2e step 未在真实 GHA 上跑过（本机无 Actions，只做本机三场景实跑 + yml 结构校验）；macOS 仍只是「可手动触发」而**未真触发过**，`process_group(0)` 在 darwin 上的缺口从「不可验证」降级为「可验证但本轮没做」。详见 HANDOVER_ROUND49.md。
- 2026-10-29 R50 双基线（桩故障注入 + 画像多 run 基线 + macOS `--port 0` 实证 + 循环轮次语义）：Low-IL → **1945 passed / 96 skipped / 0 failed**（117.88s）；High-IL → **2030 passed / 11 skipped / 0 failed**（134.21s，权威）。净增 **+20**（`test_ci_e2e_stub.py` 故障注入 8 + `test_run_profile.py` 多 run 基线 8 + `test_workflow_failure_policy.py` 循环轮次 2 + `test_workflow_loop_rejections.py` 1 + `test_desktop_packaging.py` macOS `--port 0` 契约 1），零删除。总用例 R49 口径 2021 → **2041**（High passed+skipped：2030+11）。前端 **475 passed / 0 fail**（471 + 4：baseline 开关/序列/insufficient 三态 + 循环轮次徽章）。**A. R49 遗留的唯一未验证项已关闭**：推送 `8727da3` 后 GHA run **40723820649** 的 backend job 第 9 步 `Workflow orchestration e2e (stub provider)` **真跑并 success**，日志三场景输出与本机逐字一致（4/2/2 次请求，3/3 通过）。同时确认 `desktop-windows.yml` 的 paths 过滤未被本轮改动带起（只触发 CI）。**B. macOS `--port 0` 缺口关闭**：手动触发 `desktop-macos.yml`（run **40723984654**，不打 tag、不产发布物），`Build Apple Silicon full candidate` **success**，四步 smoke 全绿——`smoke_backend.py` 确实以 `--port 0` 启动冻结后端并读到 `config/backend-port`；新增契约测试钉死「workflow 调了 smoke」+ 「脚本真传 `--port 0`」两层，避免只验前者造成「已覆盖」的假象。**C. 桩故障注入**：按真实 provider 响应格式注入 503/429/401/SSE 停摆 + `[stub:fail_once]`，三个新场景。**四个变异中三个咬合、一个不咬合并由此发现真问题**：关掉 Core `retry.max_retries` 后 transient 场景**仍绿**——因为 ChatOpenAI 自带 `max_retries=2`；同时关掉两层才红（1 次请求、任务 failed）。这条已写进场景 docstring 与 PROJECT_INFO，避免下一轮把它误当 Core 层守卫。其余咬合：`is_permanent_provider_error` 恒 False → 3 次请求红；停摆不发 chunk（走 httpx 读超时）→ 3 次请求红；401 伪装成 5xx 类**没咬合**（分类以 HTTP 状态码为准，说明该变异本身不是有效变异）。**D. 画像多 run 基线**：`pick_recent_runs` + `compare_run_baseline`，trend 四态，端点 `?baseline_limit=N`。两个变异咬合：改成「与首个基线比」→ 2 红（含尖峰用例）；`insufficient` 改 `stable` → 3 红。真实数据实跑 `xs2-novel-flywheel-build`：6 点 / 5 次可比差 / trend `stable`；端点 TestClient 验证 baseline 与 comparison 相互独立、`baseline_limit=0` 不返回。**E. 循环轮次语义**：`attempt_history` 加 `loop_iteration`，变异（不写轮次）→ 1 红；前端变异（不渲染徽章）→ 1 红。**失败率时间序列**：2.9%（23 runs / 243 尝试 / 7 失败，与 R41–R49 一致，本轮无新 run）。**未做面**：未重导快照（两条判据都绿）、未跑 `docker build`、未重启 8021（改动不涉运行时代码）、macOS run 40723984654 的**总体 conclusion 是 failure**，但原因是 core candidate job 被 GHA 并发策略 **cancelled**（full candidate job 本身 success）；两者跑同一份 `smoke_backend.py`，`--port 0` 结论由 full 支撑，勿把 run 级 failure 读成「macOS 验证失败」。详见 HANDOVER_ROUND50.md。
- 2026-10-29 R51 双基线（样本量闸门进 CI + 退避策略可观察 + 趋势接入任务列表）：Low-IL → **1969 passed / 96 skipped / 0 failed**（119.81s）；High-IL → **2054 passed / 11 skipped / 0 failed**（135.16s，权威）。净增 **+24**（`test_live_snapshot_gate.py` 样本量 11 + `test_run_profile.py` 列表趋势 6 + `test_llm_client_params.py` 重试分层 5 + `test_ci_e2e_stub.py` 退避契约 2），零删除。总用例 R50 口径 2041 → **2065**。前端 **478 passed / 0 fail**（475 + 3：`TaskHistoryPanel.test.ts` 新增 opt-in/开关/徽章三态）。**8 个变异全部咬合**。**A. 样本量判据（R51-2）**：`--check-sample-size` 退出码 7，只读快照自身；有失败要求 95% 半宽 ≤ margin，零失败改用 Clopper-Pearson 单侧上界（零失败下正态近似恒给 0，是个恒绿的坑）。实测入库快照 3.74% / 半宽 2.72 / n=187 通过，`--margin 2` 触发 7。变异：零失败恒合格 → 1 红；有失败也恒合格 → 1 红。**B. 闸门接 CI（R51-3）**：`Snapshot sample-size gate` 是**唯一进 CI 的快照判据**（另两条要真实数据，接进去永远判不到）。step 双向验证（默认过 + `--margin 2` 必须 7），反向钉死「不许 exit 0」。**C. 退避可观察（R51-4）**：新增 `retry.sdk_max_retries`（默认不出现，避免改动 `model_runtime_sha256` 导致在途任务 resume 被拒），e2e 加 `retry_backoff_is_honoured` 差分测量（实测 0.01s vs 1.21s，多 1.21s ≈ 配置 1.2s）。**这一步直接解掉 R50 §3.4 的死结**：实测 sdk=2 + core delays=[3.0] 时间隔仅 0.48s，证明当时量到的不是 Core 的退避。变异：配置被忽略 → 1 红；ainvoke 不退避 → 1 红。**D. 趋势接入列表（R51-1）**：`?with_trend=true&baseline_limit=N`（单工作流与全局两条），按 workflow 分组每目录扫一次 + 按 run_id 缓存画像；前端「标注连续退步」开关，只有 `regressing` 挂徽章。变异：取消缓存 → 1 红；多扫一次目录 → 1 红；`insufficient` 也挂徽章 → 1 红；默认开启 → 3 红。**推送 + CI 核对（`bb0df1d`）**：CI run **40796688120** 五 job 全绿；新增的第 9 步 `Snapshot sample-size gate` **在 GHA 上真跑并通过**（`快照样本量足够…半宽 2.72 ≤ 余量 10.0（n=187, 失败 7）` + `OK 样本量判据双向生效：默认余量通过，余量 2 触发 7`——第二半走到才说明这步能红），runner 是 **Python 3.11.17** 而非本机 3.14，判据跨版本一致。e2e 第 10 步在 GHA 上**真跑 7/7 场景**，退避场景量到 **1.20s**（本机 1.21s），差分判据跨平台成立。**macOS `core candidate` 挂账闭合**：`desktop-macos.yml` run **40796761709** 的 **core 与 full 两个 candidate 都 success**，run 级 conclusion 也是 success（R50 那次 core 被并发策略 cancelled）。`Desktop Windows` run **40796688136** 双 NSIS success（本轮改 `src/core/`、`src/web/`、`web/`，paths 过滤命中）。**未做面**：未重导快照（三条判据都绿）、未跑 `docker build`、未重启 8021。详见 HANDOVER_ROUND51.md。
- 2026-10-29 R52 双基线（退避形状验证 + Windows runner 接样本量闸门 + 「最近 N 次全失败」信号 + 快照重导）：Low-IL → **1988 passed / 96 skipped / 0 failed**（120.60s）；High-IL → **2073 passed / 11 skipped / 0 failed**（137.47s，权威）。净增 **+19**（`test_run_profile.py` 全失败信号 7 + `test_ci_e2e_stub.py` 形状契约 6 + `test_live_snapshot_gate.py` Windows 接线 5 + `test_ci_e2e_stub.py` fail_twice 真端口 1），零删除。总用例 R51 口径 2065 → **2084**。前端 **479 passed / 0 fail**（478 + 1：全失败徽章与趋势徽章正交）。**2 个变异全部咬合**（`all_failed` 恒 False → 3 红；把 `stopped` 当失败证据 → 1 红）。**A. 退避形状（R52 主线）**：R51 的场景只判单点幅度，对形状失明——`[0.4,0.8]`/`[0.4,0.4]`/`[0.8,0.4]` 在它眼里都只是「某个值被等过」。新桩标记 `[stub:fail_twice]`（配额从集合改成计数，才能让第二次仍失败）产生两个退避段，配置 `delays=[0.4,0.8]`，断言第二段 ≥ 第一段 1.5 倍。用**比值**不用绝对差值：共模偏移（JIT/日志/调度）同时抬高两段，比值对它不敏感，而恒定（1.0）/递减（0.5）仍被 1.5 分开。本机实测 `[0.41, 0.816]`，CI 预算与 R51 那个场景同量级（0.4+0.8=1.2s）。**B. Windows runner 接样本量闸门（R52 附加 A）**：补掉 R51 §10-1 的缺口，`windows-backend` job 加同名 step（PowerShell 写法，双向验证同 ubuntu），跑在 Windows + Python 3.14 上。关键取舍：脚本里把 `$ErrorActionPreference` 降成 `Continue`——反向验证要求被测脚本**故意**以 7 退出，而 pwsh 默认的 `Stop` 会把它包成 NativeCommandError，让这一步在判据正常工作时反而红（比恒绿更难排查：红灯指向错误的东西）。**C. 「最近 N 次全失败」信号（R52 附加 B）**：`trend` 比的是失败率**相邻差值**，一个每次都 100% 失败的工作流差值恒为 0 → 判 `stable`，最难处理的运维状况恰好被趋势判据漏掉。新增 `failure_streak()`（`FAILURE_STREAK_REQUIRED`=3）与 `consecutive_failed`/`all_failed`/`all_failed_required` 三字段，单独成字段而不并进 `trend`（R51 §10-7 同一理由的第二次实例）。只认 `failed`：`stopped` 是人工停止、`running`/`pending` 还没结论，算进去会让「手动停了任务」变成告警；`required=0` 永不成立。前端徽章 `data-all-failed`，门槛由后端给、前端不重算。**特意写了一条「正交性」测试**：全失败序列的 `trend` 必须判 `stable` 且 `all_failed` 为真，两个字段同时断言，钉住「它们是互补的两个信号」。**D. 快照重导（R52 附加 C）**：R51 §10-2 挂账的快照从 `--limit 2`（187 次尝试 / 7 失败 / 3.74% / 半宽 2.72）重导到 `--limit 5`（**255 次尝试 / 10 失败 / 3.92% / 半宽 2.38**，28 个 run，280KB < 400KB 上限，9 个工作流不变）。选 limit 5 而非 3 的理由是可判性：limit 3 的半宽 2.10 贴 CI 反向验证的门槛（要求 > 2），样本再厚一点就会让「收紧到 margin 2」不再触发 7，判据从可用退化成恒绿。实测双分支仍成立（默认 0 / margin 2 → 7）。重导后 38 条快照测试全绿，说明它们都按快照自身推导而非写死数字。**High-IL 一次假红已排除**：`test_core_default_resources.py` 两条在相对 `PYTHONPATH` 下红，根因是这两个用例在 `cwd=tmp_path` 的子进程里跑、相对路径失效（本机已知的 CWD 回落坑），换成绝对路径后 11 passed，与代码无关。**推送 + CI 核对**：`fead4ea` 推后 `Desktop Windows` run **40801653581** 双 NSIS success（paths 过滤命中）；`CI` run **40801653541** 的 `windows-backend` 在**新加的样本量步骤**上红——日志里两个分支都判对、也打了 OK，根因是 GHA 的 pwsh 包装器在脚本末尾追加 `exit $LASTEXITCODE`，而最后一条原生命令正是那次**故意**以 7 退出的反向验证，于是成功路径也被透传成非零（bash 版没有此行为，正是「单环境验证漏掉平台隐含假设」的活实例）。修法 `3572cc2`：末尾显式 `exit 0` + 契约测试钉末行。修复后 `CI` run **40802321401** **五 job 全绿**，Windows 第 7 步与 ubuntu 第 9 步输出同一数字（3.92% / 半宽 2.38 / n=255），**两个 runner 结论一致**；e2e 在 GHA 上真跑 8/8，形状场景量到 **`[0.403, 0.803]`**（本机 `[0.41, 0.816]`，配置比值 2.0）。**未做面**：未跑 `docker build`（本机无 docker/wsl，与历轮一致；本轮改了 `src/web/` 与 `web/`，`container-build` 会真构建并跑冒烟）、未重启 8021（改动是新增只读字段与 CI 步骤，不涉运行时装配）、未验真实 120s 级退避（属压测画像地盘）。详见 HANDOVER_ROUND52.md。
- 2026-10-29 R53 双基线（三段退避形状 + 快照半宽预算检查 + **比例判据 p=1.0 退化点修复**）：Low-IL → **2023 passed / 96 skipped / 0 failed**（119.55s）；High-IL → **2108 passed / 11 skipped / 0 failed**（136.73s，权威）。净增 **+35**（`test_ci_e2e_stub.py` +12、`test_export_run_samples.py` 新文件 +14、`test_live_snapshot_gate.py` +5、`test_run_profile.py` +2、`test_llm_client_params.py` +2），零删除。总用例 R52 口径 2084 → **2119**。前端零改动 **479 passed / 0 fail**。**4 个变异全部咬合**（`max()`→`next()` 1 红；`min_ratio` 1.5→1.0 3 红；只判前两段 3 红；`p=1.0` 回落正态近似 3 红）。**本轮最有价值的发现不在主线里**：写半宽预算测试时构造了一份「2 次尝试全失败」的样本，预期合格却判了不合格，查下去发现 `_failure_rate_precision` 的 `p(1-p)` 在 **`p=0` 与 `p=1` 两端都等于 0**，R51 只补了 `p=0`（零失败→单侧上界），`p=1` 一直漏着——一个 100% 失败的快照会被判「样本量足够」，闸门拿它当基线后阈值封顶成 100% **永远不触发**。这是同一盲区家族的第三个形状（R52 §4 `trend` 对全失败序列判 `stable`；R51 `p=0`；R53 `p=1`），共同点是**比例类判据在退化点回落到恒真**。修法：两端共用同一个 Clopper-Pearson 单侧界 `1-0.05**(1/n)`，中段仍走正态近似；算术抽成 `sample_size_margin_needed()` 供导出脚本复用，两处不再各写一份公式。**A. 三段退避形状（R53 主线）**：两段判据（`max_retries=2`）抓不到「只在长链后段显形」的回归（`delays` 只读前两项、循环边界少一次、填充逻辑补错第三项）——那些在 `max_retries=2` 下第三段根本不存在。新桩标记 `[stub:fail_thrice]`（配额 3）+ 场景 `retry_backoff_long_chain_shape_is_honoured`（`delays=[0.4,0.8,1.6]`，逐对判 1→2、2→3 都递增）。判据抽成 `_rising_shape_violations(segments, configured, min_ratio=1.5)` 与两段场景**共用**——各写一份阈值迟早漂移。顺带修正 R52 留下的隐患：多标记并存时取**最大**配额而非字典序第一个，否则 `[stub:fail_once][stub:fail_thrice]` 这种复制粘贴残留会让形状判据报「段数不够」而不是「配额写错」。实测本机 `[0.408,0.809,1.618]`、GHA `[0.406,0.806,1.606]`（配置比值 2.0），总等待 2.8s 仍在 CI 预算内。**B. 快照半宽预算检查（R53 附加）**：R52 §9-7 挂账的耦合（快照越厚→半宽越小→CI 的 `--margin 2` 反向验证越可能不再触发 7）做成导出时的自动检查。三档结论：所需余量 <2.0 不合格（`--strict-half-width` 时退出码 1）、2.0~2.5 合格+告警「一次重导就可能越线」、>2.5 合格。**判据方向相反不能合并**——`--check-sample-size` 要求「≤ margin」（样本够厚），半宽预算要求「> margin」（判据还能红）。导出脚本此前 R47 起**零测试**，本轮新建 `test_export_run_samples.py`（14 条）把「裁剪正确性判据是画像逐字段相等」与「半宽预算的边界与方向」一起钉住。**C. `FAILURE_STREAK_REQUIRED=3` 复核**：结论**不改**（取 2 意味着单次失败就报警，而单次失败在这类长流程里是常态；3 要求「连续两次重试机会都没救回来」）。但发现一处脆弱耦合：门槛在 `run_profile.py`、`baseline_limit` 默认值在 `workflow_routes.py`，**两个数在不同文件**，`limit=1` 时点数 2 < 门槛 3 → 信号永不触发。用测试钉住该约束。**D. `sdk_max_retries` 生产取值**：结论**维持不设**（两层各管一类故障：SDK 管连接级 TCP 重置/读超时，Core 管协议级 5xx/429；关上层会让连接级故障用掉 Core 给长间隔留的配额）。写 0 把最坏请求数从 12 降到 4 但改变生产行为，需单独一轮评估。**E. macOS 桌面构建补验**：查 workflow 定义发现它只认 `desktop/**` 的 **pull_request**、**不认 push**——R52 §9-8 担心的「会被触发」对 Windows 成立、对 macOS 不成立。用 `workflow_dispatch` 触发 run **40876413164**，双 candidate（core/full）**success**，该挂账项闭合。**推送 + CI 核对**：`6b81ffb` → `CI` run **40874361728** **五 job 全绿**，三段场景在 GHA 上真跑 **9/9**（`[0.406,0.806,1.606]`），Windows 与 ubuntu 侧样本量步骤输出同一数字（3.92%/2.38/n=255，证明 p=1.0 修复不影响常态快照）。**High-IL 一次环境坑**：首次 136 个收集错误 `No module named 'dotenv'`，根因**不是** R52 记的「相对路径失效」而是**路径分隔符**——Git Bash 的 `$(pwd)` 给 `/f/...`（msys 形式），Windows `py.exe` 不认识，`PYTHONPATH` 整个失效；须用 `cygpath -w` 转成 Windows 路径（与 R52「必须用绝对 PYTHONPATH」是两条不同规则，两条都要满足）。**未做面**：未判四段以上、未跑 `docker build`（本机无 docker/wsl，`container-build` 在 GHA 真构建通过）、未重启 8021（改动是脚本与测试不涉运行时装配）、p=1.0 修复无真实全失败快照验证（本机数据 255/10 无此形状）。详见 HANDOVER_ROUND53.md。
- 2026-10-29 R54 双基线（workflow 级全失败聚合 + per-workflow 样本量判据）：Low-IL → **2044 passed / 96 skipped / 0 failed**（119.75s）；High-IL → **2129 passed / 11 skipped / 0 failed**（136.45s，权威）。净增 **+21**（`test_run_profile.py` +9、`test_live_snapshot_gate.py` +12），零删除。总用例 R53 口径 2119 → **2140**。前端 **484 passed / 0 fail**（479 → +5，新文件 `WorkflowTemplatePanel.test.ts`），`npm run build` ✓ 6.37s。**4 个变异全部咬合**（`workflow_health` 不排序 1 红；关闭 per-workflow 漂移检测 3 红；`health_limit` 裁最早那段 1 红；把「薄」当硬失败 3 红）。**本轮最重要的一件事：恒红门槛与恒绿防护是同一个错误的两面。**「给 `--check-sample-size` 加 per-workflow 判据」按直觉写会**永远红**——真实快照 9 个 workflow 里 5 个的失败率精度达不到 margin=10（`flywheel-export` 5 次尝试零失败，零失败 95% 上界 45 个百分点，压到 10 要 29 次尝试，而该 workflow 真实数据总共只有 10 个 run，**物理上补不到**）。所以 per-workflow 判据最后只有两件事能红：①`per_workflow` 元数据与内容不一致 → 退出码 4；②薄只进报告不判失败。叫它判据就会变成假防护。**A. workflow 级全失败聚合（R54 主线）**：R52 的 `failure_streak` 判的是「这一条任务」的 run 序列，有两个结构性盲区（只覆盖当前页 `page_size` 默认 20 的任务、已删任务引用的 run 完全不在内）。失效形状：三个任务各跑一次各失败一次，任务级每条只看到 **1 连败**（`required=3` 不成立），而 workflow 整体已连续输 3 次。新增 `workflow_health(runs, required)` 内部把 run 映射成 `failure_streak` 要的 `{run_id, status}` 后直接调它——不写第二份连续失败计数，理由与 R53 `_rising_shape_violations` 相同（两条路径迟早对「什么算失败」产生分歧）。一处细节：**内部按 `_order_key` 排序**，不信调用方顺序（文件名字典序把 `run-10` 排在 `run-9` 前，不排序会把最早那次当最新，「最近是否全挂」判反）。路由 `GET /api/workflows` 加 `with_health`（默认关，与 `with_trend` 同取舍）与 `health_limit`（默认 **0=全部** 而 `baseline_limit` 默认 5——前者是「够不够判趋势」、后者问「最近是不是一直挂」，裁短会把全失败序列头部截掉反而更不安全）。成本实测 21 个工作流全量扫 `runs/` **0.028s**，故前端模板列表直接开，不做按需展开。**B. per-workflow 样本量判据（R54 附加）**：`recompute_totals` 只比全局 attempts/failed，一次「把 A 工作流的失败改成 B 工作流的」改动全局合计分毫不动、全局校验通过，而 `per_workflow` 块已在说谎——实测构造样本对照：**per-workflow 判 4 并点名两个 workflow，全局判 0**。这就是分组复算的唯一价值：补全局校验**结构上**看不见的那一层。CI ubuntu+windows 各加一步，并**注入一处漂移断言退出码 4**（否则判据失效时这步照样绿）。实现坑：注入漂移的 Python 用**单行 `python -c`** 而非 heredoc——heredoc 体必须顶格会提前终止 YAML 块标量，整份 workflow 变非法 YAML。**前端**：`WorkflowPage` 模板列表请求改带 `with_health=true`，卡片加「连续 N 次全失败」徽标（`AlertTriangle` + destructive），只在 `all_failed` 时渲染，N 用后端给的 `consecutive_failed`（门槛不写死，与 R52 任务级徽标同一纪律）；`listWorkflows()` 加可选参数，默认行为不变。**本机 e2e 9/9 通过**（三段退避 `[0.408,0.811,1.61]` 仍绿）。**未做面**：§11 四项挂账按用户拍定本轮不做（四段退避、`min_ratio` 判别力边界、`p=1.0` 真实数据验证、`FAILURE_STREAK_REQUIRED` 未改）；未按 workflow 判失败率（需先把闸门改成 per-workflow 基线，是另一次改动）；`trend` 仍是任务级（workflow 级 trend 与本次 health 正好配成一对，列下轮首选）；未跑 `docker build`（本机无 docker/wsl，`container-build` 在 GHA 真构建）；未重启 8021（默认路径行为不变）。详见 HANDOVER_ROUND54.md。
- 2026-10-30 R55 双基线（workflow 级失败率趋势 + 样本量精确界 + 四段退避形状）：Low-IL → **2058 passed / 96 skipped / 0 failed**（127.85s）；High-IL → **2143 passed / 11 skipped / 0 failed**（155.58s，权威）。净增 **+14**（`test_run_profile.py` +12、`test_live_snapshot_gate.py` +2），零删除。总用例 R54 口径 2140 → **2154**。前端 **490 passed / 0 fail**（484 → +6，全在 `WorkflowTemplatePanel.test.ts`），`npm run build` ✓ 6.36s。**5 个变异全部咬合**（`workflow_trend` 不排序 1 红；样本量中段回退正态近似 3 红；`trend_limit` 裁最早 2 红；门槛 3→2 1 红；health 误用 trend 窗口 1 红）。**本轮最重要的一件事：一条判据在说反话。** `sample_size_margin_needed` 原本三段拼接（两端 Clopper-Pearson 闭式、中段正态近似），在 `p` 从 0 跳到 `1/n` 处留了个方向错误的台阶——n=10 时零失败要 25.89 个百分点、一次失败只要 **18.59**，「多了一次失败」反而让样本显得更可信，正好把最该被看见的那一刻放过去。修法是**全线用同一个精确界**（`_cp_bounds` 二项分布精确分位数，两端的 `1-0.05**(1/n)` 正是它的解析解，不是另一个估计），合并后台阶消失：n=10 变成 25.89→29.42→30.69 单调上升；n∈[5,300] 全区间一次失败恒比零失败要求更厚，高端镜像同样成立。**代价如实记录**：精确界更宽，入库快照全局 10/255 由 2.38 升到 2.64（仍远小于 margin=10，闸门不受影响）；per-workflow 诊断里 build（9.81→12.76）与 post-hoc（7.99→14.12）由达标变不达标，但该块**恒退出 0**，变的只是报告文字；导出脚本半宽余量 0.38→0.64 越过 0.5 告警带，故 `test_thin_headroom_still_passes_but_warns` 改为显式 margin=2.3 构造带内样本。**残余无害且已钉住**：`n ≤ 4` 低端仍有轻微反转（n=2 时 77.6→47.5），但那几个 n 的每个 k 都 ≥45 个百分点，判决不可能因此不同；写成独立测试限定豁免范围，防止被扩成「小样本可以不管」。**A. workflow 级趋势（R55 主线）**：开工前核对 run JSON 实际字段发现 **`task_id = None`**——所以 workflow 级趋势无法由任务级合并，只能直接沿 `runs/` 时间序列判。新增 `workflow_trend(profiles, limit)`（内部按 `_order_key` 排序后**复用** `compare_run_baseline`，不写第二份趋势判据，理由同 R53 `_rising_shape_violations` / R54 `failure_streak`）。路由加 `with_trend`（默认关）与 `trend_limit`（默认 5，上限 20）；与 `with_health` 正交，两者同开时**共用一遍目录扫描**（`_collect_workflow_diagnostics`）。14 个工作流实测响应 92ms；真实数据里没有 regressing/all_failed 的 workflow，7 个正确判 `insufficient`（不冒充 `stable`）。**B. 常量表合并（R53 §12-5 挂账关闭）**：`DEFAULT_BASELINE_LIMIT=5`/`MAX_BASELINE_LIMIT=20` 收进 `run_profile.py`，端点三处默认值与裸 20 上限全部改引用，两数不再分处两文件。**C. `FAILURE_STREAK_REQUIRED` 补数据依据**：结论**保持 3**，但依据换成实测——40 次 run 逐点回放，`required=2` 触发 2 次（build 的 6 连败 + **character 的 2 连败且之后立即成功**，即一次假告警），`required=3`/`4` 都只触发 1 次；取 3 是「能抓住真实事件、又不报 2 连败」的最小值，取 4 只推迟发现时点。**D. 四段退避形状（R53 §12-1 挂账关闭）**：新增 `[stub:fail_four_times]` + 场景，`delays=[0.4,0.8,1.6,3.2]`。初版把量级降到 0.2 起，随即发现 0.15s 共模偏移会把首对压到 1.57（离 `min_ratio=1.5` 只剩 0.07，CI 易翻假红），改回 0.4 起（同偏移 1.73）。实测本机 `[0.413,0.812,1.610,3.210]`。**E. 前端与浏览器走查（补 R54 §10-7）**：模板列表请求改带 `with_health=true&with_trend=true`（网络面板确认），新增上升（warning）/下降（success）徽标，与全失败徽标**并列而非互斥**。真实数据无样本，故用页内 fetch 拦截注入 regressing/all_failed/improving 后**切换子标签触发组件内重取**（`reload()` 会冲掉注入），实测三个徽标同时正确渲染 `['失败率连续上升','连续 4 次全失败','失败率连续下降']`，随后 `reload()` 恢复真实数据（14 卡、零徽标、`patched:false`）。走查踩坑：主导航 `<Tab>` 用 Playwright role locator 点击会超时（`count()=1` 且 `isVisible()=true` 却不可 actionable），改走 `/?tab=workflow` URL。**F. 本轮重启了 8021**（旧 PID 26252 → 新进程，与 R53/R54 的「未重启」不同）：接口与前端走查都在含 R55 的新进程上做。**未做面**：仍未按 workflow 判失败率（需先把闸门改成 per-workflow 基线，R54 §10-1）；`p=1.0` 仍无真实全失败快照验证；`min_ratio` 判别力边界未重算（本轮反而通过量级回避）；`workflow_trend` 未判耗时趋势（沿用 R51 §10-7 结论）；未跑 `docker build`（本机无 docker/wsl）。详见 HANDOVER_ROUND55.md。
- 2026-10-30 R56 双基线（**per-workflow 失败率判据**：留一法基线 + 三分法 + 报告模式）：Low-IL → **2074 passed / 96 skipped / 0 failed**（129.78s）；High-IL → **2159 passed / 11 skipped / 0 failed**（145.82s，权威）。净增 **+16**（`test_live_snapshot_gate.py` 11 条判据 + 5 条 CI 接线），零删除。总用例 R55 口径 2154 → **2170**。前端 **490/0 不变**（本轮零前端改动），`npm run build` ✓ 6.32s；本机 e2e **10/10**。**5 个变异全部咬合**（留一法退回全局合计 2 红；`undetermined` 归并成 `normal` 3 红；`exceeds` 改用点估计 3 红；报告模式失效 1 红；失败率路径跳过漂移校验 1 红）。**本轮最重要的一件事：全局合计当基线是自指的。** 原先 `evaluate` 用 `failed_all/attempts_all` 当基线，这个数里**包含被判的那个 workflow 自己**——一个全挂的 workflow 既抬高自己的观测值、也同时抬高拿它比的阈值，两者一起涨，工作流越多越厚这个自指就越紧，它永远判不出自己。改用**留一法基线** `(F-k)/(A-n)`：判某 workflow 时基线只算其余 workflow，问的问题本来就该是这个。**判决是三分法，由真实数据逼出来**：入库快照 9 个工作流里 **8 个的 95% 区间横跨阈值**（如 `export` 的 [0%, 45%] 对阈值 14%）——既不是「合格」也不是「不合格」，是「样本不足以回答」。二分只有两个结果，都是假防护：判「不是 normal 就失败」→恒红（样本太薄冒充在变坏），判「不是 exceeds 就通过」→恒绿。故 `undetermined` 是**一等判决**，处置是调大 `--limit` 重导，不是查供应商（1）、不是确认新工作流该不该进样本（6）。判定用**区间下界**而非点估计，理由同 R55 §1「判据不许说反话」——点估计几乎必然越过某阈值，等于「样本越小越容易被判坏」（有测试钉住：30 次 6 失败点估计 20% > 阈值 10%，但下界 4.45% 必须判 `undetermined`）。**真实快照实测（margin=10）：0 个超出 / 1 个正常 / 8 个样本不足。** **落地形态=报告模式（用户拍定两步走）**：即使判 `exceeds` 也退出 0，加 `--fail-on-exceeds` 才按 1 退出；因为当下 8/9 是 `undetermined`，直接硬门槛红的会是「样本太薄」冒充「在变坏」，是一个训练人忽略该步骤的假红。CI 上 ubuntu 与 windows 各加一步报告，能红的路径仍只有元数据漂移(4)与无样本(3)，故照例注入漂移验证必须判 4（windows 段末尾显式 `exit 0`，规避 R52 记的 pwsh 包装器 `exit $LASTEXITCODE` 坑）。**顺带修一处测试定位缺陷**：`_per_workflow_step` 原按子串 `--check-per-workflow` 匹配，被新开关 `--check-per-workflow-rate` 当词前缀误伤（1→2 处），改为完整 token 正则 `(?![-\w])`。**未做面（含一个比本轮主线更严重的独立缺陷）**：① **主闸门 `evaluate` 永不失败**——阈值 `measured+margin` 配触发条件 `measured > threshold`，只有 `margin<0` 才可能成立而 argparse 禁负余量，实测 20 次尝试全失败仍判 0；修法需单独设计退出码语义，本轮只记录不动（R57 第一候选）；② per-workflow 硬门槛未接（§3 第二步）；③ `p=1.0` 全失败快照仍无真实数据验证；④ Desktop Windows 未被触发属预期（其 paths 只认 `desktop/`、`src/`、`web/`、`config/`、`requirements.lock` 与自身文件）。详见 HANDOVER_ROUND56.md。
- 2026-10-30 R57 双基线（**主闸门 `evaluate` 永不失败修复**：外部政策上限 + 区间下界三分法）：Low-IL → **2085 passed / 96 skipped / 0 failed**（124.41s）；High-IL → **2170 passed / 11 skipped / 0 failed**（142.76s，权威）。净增 **+11**（`test_live_snapshot_gate.py` 74 → 85，**13 新、2 换**——「阈值随余量变」「余量归零仍通过」钉的正是自指阈值的行为，留下会与新语义自相矛盾，替换后断言更强），总用例 R56 口径 2170 → **2181**。前端 **490/0 不变**（零前端改动，`npm test` 实跑 8 套件）。**缺陷**：`evaluate` 用 `measured + margin` 当阈值、判据又是 `measured > threshold`，而 argparse 禁负余量 → 阈值恒 ≥ 实测，比较**恒假**——阈值长在被测量的量上，闸门就成了同义反复，这是全套判据里唯一「判了且判不出问题」的一处（实测 20 次尝试全失败仍退出 0）。
  **修法（用户拍定：外部绝对上限）**：把阈值移出被测量的量，新增 `--fail-if-above PCT`（与 `provider_failure_profile.py` 同名同义），脚本内无默认值，CI 里是写明数字的 **8%**；判决沿用 R56 的三分法与同一把精确界——抽出 `_cp_interval` + `_verdict_of_interval` 供主闸门与 per-workflow 共用（测试在 5 组 (n,k) × 5 个阈值上比对两处判决，任一处换口径就会分裂）：95% **下界** > 上限才判 `exceeds`，上界 ≤ 上限才判 `normal`，横跨则 `undetermined`；`undetermined` 不判失败（精度归 `--check-sample-size` 的退出码 7，两处都红会把处置指向供应商）。入库快照 10/255 = 3.92%（区间 [2.14%, 6.56%]）实测：上限 8% → normal(0)、4% → undetermined(0)、1% → exceeds(1)。上限取 8% 的依据：当前上界 6.56% 明确在限内，要判红需 255 次尝试里至少 29 次失败（11.4%）——**如实记的代价**：失败率翻倍到 7.8% 仍不会红，它判的是「有证据表明政策被突破」，不是「有变化」；变化检测属趋势面。
  不给上限即**报告模式**（退出 0，但说明必须写「未给 --fail-if-above，本步只报告不判定」，不许沉默成通过；有测试钉住文案且断言不许出现「判正常」）。CI 不靠默认值兜底，靠三条静态测试：**每一次**调用都必须带上限、第二次（反向验证）上限必须更低且退出码变量来自它、两个 runner 的上限数字必须相同。`--margin` 语义收窄为只服务 `--check-*`，默认模式给了就 `parser.error`（静默忽略会让「收紧余量却没变」成谜）；上限须 **< 100**（=100 与 >100 都永远判不出超阈，是「容忍一切」的恒绿配置，测试拒绝 101/100/−0.5）。CI：ubuntu 原步骤改成「8% 判定 + 反向验证 1% 必须判 1」，windows **新增**同名步骤（此前主闸门只在 ubuntu 跑；照 R52 纪律降 `$ErrorActionPreference` + 末尾 `exit 0`）。**6 个变异全部咬合**（自指阈值 5 红／点估计 3 红／undetermined 判失败 2 红／报告模式写成「通过」1 红／CI 丢上限 3 红／windows 上限漂开 1 红），还原用 `cp` 备份。顺带修 PROJECT_INFO 里 R44「CI 核对」条目错位（标题粘在 R53 行尾、正文挂在 R55 名下），按用户拍定**单独提交** `a2f5e4d`。详见 HANDOVER_ROUND57.md。
- 2026-10-30 R58 双基线（**per-workflow 硬门槛 + 连续 3 轮 undetermined 次级信号**）：Low-IL → **2082 passed / 113 skipped / 0 failed**（126.33s）；High-IL → **2167 passed / 28 skipped / 0 failed**（140.09s，权威）。净增 **+14**（`test_live_snapshot_gate.py` 85 → 96：+11；`test_export_run_samples.py` 14 → 17：+3），零删除。总用例 R57 口径 2181 → **2195**。前端 **490/0 不变**（零前端改动，`npm test` 实跑）。**6 个变异全部咬合**（连续轮数不含当前 2 红；历史纳入漂移校验 2 红；导出不携带旧历史 1 红；`undetermined` 触发硬门槛 2 红；ubuntu 真实判定丢开关 1 红；历史封顶失效 1 红）。**本轮最重要的一件事：连续轮数的历史必须随快照入库。** 硬门槛机制 R56 已实现，真正的设计问题是次级信号的历史放在哪——在 CI 里写状态不成立（检出是临时的，job 结束即消失，于是「连续 3 轮」在 CI 里永远等于「1 轮」，又是一个写着「在看趋势」的恒绿防护）；历史因此放进 `snapshot-meta.json` 的 `history` 块，由导出脚本每次追加（`HISTORY_MAX_ROUNDS=5`，只记 `attempts/failed` 不记判决——判决依赖调用方的 margin），闸门只读。三条性质：当前轮不重复计数（最后一条==当前计数才不追加）、历史缺失/不匹配时把当前补成新的一轮（不让提示晚一轮）、历史**不参与**漂移校验（描述的是过去几轮各自的快照，纳入则每次重导都判 4）。**硬门槛（用户拍定接两 runner）**：有 `exceeds` 且给 `--fail-on-exceeds` → 1；`undetermined` 永远 0（含连续 3 轮）；漂移 4；无样本 3。真实快照实测 **0 超出 / 1 正常 / 8 样本不足**、退出 0；全挂合成快照 `tests/fixtures/live_snapshot_exceeds`（40/40 + 两个 40/0，下界 92.78% 对阈值 10%）判 1、不加开关判 0——反向验证用**入库 fixture** 而非 CI 现场造数据，理由是可审阅、测试与 CI 共用同一份（`test_the_exceeds_fixture_really_exceeds` 先钉住判决）、fixture 数字漂了测试先红。**次级信号只提示不判失败**，文案最后一句答 R56 §10-3：重导后仍连续不足说明数据量本身撑不起逐 workflow 判决，需在文档里接受该限制（`export` 只有 10 个 run 物理补不到 margin=10）。**历史覆盖必须可见**：不足 3 轮明说「提示需要 ≥3 轮历史，当前未生效」，坏条目跳过并计数（低估好过编造序列），workflow 在历史轮缺席则中断计数。**CI 逐次调用检查**：`_rate_invocations` 先把 `\` 续行拼回一行，断言**每次** `--check-per-workflow-rate` 调用都带开关——只删一次调用里的开关，旧式「这一段里出现过」断言照样通过（变异 5 实证）。windows 段保留 R52 两条坑处理（`$ErrorActionPreference='Continue'` + 末尾显式 `exit 0`）。入库快照回填 1 轮历史（`exported_at` 与计数取自同一份文件，命令见交接 §12），下一轮重导 2 轮、第三轮起提示生效。**未做**：①「轮」是导出轮不是 CI 轮（CI 无法写回仓库；要每次 CI 推进需设计写回动作）；② 提示对物理上补不到的 workflow 也会发（不做「理论上限」推断——真实 run 总数不在快照里）；③ per-workflow 仍只有 `baseline+margin`（没有绝对上限，各 workflow 合理失败率不同，不发明政策值）；④ 8% 上限维持未校准；⑤ Desktop Windows 未触发（paths 只认 `desktop/`、`src/`、`web/`、`config/`、`requirements.lock` 与自身）；⑥ 未跑 docker build（本机无 docker，GHA 真构建）；⑦ 新增 fixture 暂未纳入载荷扫描（下一轮清理项）。**推送与 CI 已闭环**：`477eb68` + `d024d78` + `88aaafd`，run **41018667020** 与 **41019944805** 均五 job 全绿；两 runner 的 gate 输出逐字一致（0 超出 / 1 正常 / 8 样本不足 + 历史 1 轮未生效），`OK … 硬门槛双向生效：真实快照通过，全挂快照触发 1，注入漂移触发 4` 两边都打印；四面用例数一致 2195（ubuntu 2131/64、windows 2166/29、Low 2082/113、High 2167/28）。推送通道：直连 DNS 把 github.com 解析到不可达 IP，改用本地 CONNECT 隧道指向 140.82.112.3，临时脚本用完即删，未改远端/系统代理配置。详见 HANDOVER_ROUND58.md。
- 2026-10-30 R59 双基线（**主闸门历史基线回归 + 载荷扫描扩到所有快照 fixture**）：Low-IL → **2106 passed / 113 skipped / 0 failed**（134.28s）；High-IL → **2191 passed / 28 skipped / 0 failed**（150.98s，权威）。净增 **+24**（`test_live_snapshot_gate.py` 96 → 120：载荷扫描/裁剪契约 +4、回归判据与 CI 接线 +20），零删除。总用例 R58 口径 2195 → **2219**。前端 **490/0 不变**（零前端改动，`npm test` 实跑 8 套件）。**6 个变异全部咬合**（去基线厚度守卫 1 红；基线取当前轮 7 红；去集合检查 1 红；不记回归来源 6 红；ubuntu 真实判定丢 `--regression-margin` 1 红；fixture 加 `summary` 2 红）。**用户拍定三项**：主线=载荷扫描+历史基线模式；「轮」按**导出轮**推进（CI 不写回仓库）；物理上补不到样本量的 workflow 维持现状提示。**本轮最重要的一件事：退出码 1 有两个来源，日志里必须分得清。** R57 主闸门只有政策上限（判绝对失败率），判不了「相对上一轮显著变坏」（2%→7% 仍在 8% 内）；R59 加 `--fail-on-regression`，两条并存且都退出 1，报告显式写 `退出码 1 的来源：政策突破；回归`（单条只写那条，都没有写「无（已启用的判据都没有判失败）」）；不给开关时写「未给 --fail-on-regression，本步不判回归」——不把没判沉默成判过。**基线取 history 的上一轮，不合并多轮**：相邻导出常含同一批 run，合并会伪造精度（区间假性收窄），忽略重叠只会让区间偏宽（偏保守，不会误报回归）。**薄基线不判**（`sample_size_margin_needed(基线) ≤ 回归余量`，与 `--check-sample-size` 同一把尺；0/10 的上界 25.9pp 拿来当阈值会把任何非零失败判成回归）；**两轮 workflow 集合不同不判**（覆盖变化让失败率不可比，与 R58「缺席即中断」同一条纪律）。**回归余量取 3 而非 10**：入库快照 10/255 的精确界半宽 2.64pp，再小会被重导噪声触发；10 会让阈值 13.92% 恒高于 8% 上限，回归这一层永远被政策上限挡在前面（写着「在看回归」的恒绿步骤）。实测判定窗口真实存在：255 次尝试里 26 次失败（10.20%）回归先红，29 次（11.37%）才轮到政策上限。配置层另有恒绿告警：基线+余量 ≥ 上限时明写「回归判据不会先于政策上限触发」。`--regression-margin` 单列开关（`--margin` 问精度、它问变化，混用会出现「调精度顺手改判据」的暗耦合）。**反向验证**：`live_snapshot_exceeds` 补 `history` 两轮（健康上一轮 0/120 + 当前 40/120），同一份 fixture 同时钉住硬门槛与回归两条判据，测试先钉判决、CI 再断言 1。**§11-1 载荷扫描**：从写死 `live_snapshot` 改为**自动发现** `tests/fixtures/*/snapshot-meta.json`（以后新增 fixture 自动纳入），加一条「已知两个 fixture 必须在范围内」防空集退化，并新增**裁剪契约**测试——对每份 run 调导出脚本的 `trim_run`，结果必须与文件逐字段相同（比 7 字段黑名单更强，手工加任何字段都会红）。**CI**：ubuntu 与 windows 各加一步 `Snapshot historical-baseline regression gate`（真实快照退出 0 + 全挂快照断言 1；windows 照 R52 纪律 `$ErrorActionPreference='Continue'` + 末尾 `exit 0`），逐次调用检查要求每次调用都带 `--fail-on-regression` 与 `--regression-margin`，两 runner 余量必须一致且等于脚本默认值。**当前状态**：入库快照 history 只有一轮（R58 回填），真实快照的回归判据现在判 `undetermined` 并退出 0，**下一次重导后开始真判**（导出轮口径）。**未做**：①相邻两轮可能重叠、history 只记计数不记 run_id，无法扣除（偏保守）；②回归只判全局合计，per-workflow 变坏由 R56/R58 留一法硬门槛负责；③8% 上限维持未校准；④物理补不到的 workflow 维持现状提示；⑤Desktop Windows 未触发（paths 只认 `desktop/`、`src/`、`web/`、`config/`、`requirements.lock` 与自身）；⑥未跑 docker build（本机无 docker，GHA 真构建）；⑦零前端改动故未跑 `npm run build`；⑧未重启 8021；⑨未重导快照（故回归判据尚未在真实数据上生效）。**推送与 CI 已闭环**：`7cb70b0` + `13ecfeb`，run **41029676149** 五 job 全绿；新步骤 ubuntu 第 9 步 / windows 第 8 步均 success，两 runner 的真实快照判决逐字一致（判不了回归·历史 1 轮），全挂 fixture 判 1 且两 runner 都打印 `OK … 历史基线回归判据双向生效`；政策上限那一层不受影响（8% 正常、1% 反向验证判 1 且来源行只写政策突破）；四面用例数一致 **2219**（ubuntu 2155/64、windows 2190/29、Low 2106/113、High 2191/28）。推送通道：socks5 10808 未运行（连接被拒），`git -c http.proxy= -c https.proxy= push` 直连成功，未改任何配置。详见 HANDOVER_ROUND59.md。
- 2026-10-30 R60 双基线（**快照重导让历史基线回归判据上线**）：Low-IL → **2106 passed / 113 skipped / 0 failed**（130.84s）；High-IL → **2191 passed / 28 skipped / 0 failed**（143.90s，权威）。净增 **0**（数据轮，零代码/零测试改动），总用例 **2219 不变**；前端 **490/0 不变**（`npm test` 实跑 8 套件）。**用户拍定三项**：主线=重导快照让回归上线；范围=只做主线收口；口径=`--limit 5`。**本轮最重要的一件事：判据上线了，但这一轮是「自比自」。** 本机 `data/workflows` 最新的 run 停在 2026-10-26/27（2026-10-29 那次导出之后没有新 run），重导选中的仍是同一批 **28 个 run**，255 次尝试 / 10 失败 / 3.92% 逐字段相同——`history` 第二条是第一轮的完全副本，只有 `exported_at` 不同（`2026-10-29T01:28:46Z` → `2026-10-30T09:26:54Z`）。回归判据因此第一次在真实快照上判出结论：基线取自历史上一轮（9 个 workflow，10/255）+ 余量 3 = 阈值 6.92%，当前区间 [2.14%, 6.56%] 整个在阈值内 → 判没有回归，退出 0，来源行写「无（已启用的判据都没有判失败）」。**证明了**基线选取/集合比对/区间/来源行在真实数据上全部走通（CI 里这一步不再是「判不了」的占位）；**没证明**质量在时间上稳定（两轮是同一批 run，是自比自）——这是 R59 §9-2「相邻两轮可能重叠」的极端值 100%，方向仍保守（区间偏宽、偏判不出、不会误报回归），真实的时间序列比较要等下一次**有新 run** 的导出。状态：`undetermined_streaks` 的「连续 3 轮样本不足」提示需第 3 轮才生效，现 history 2 轮仍未启用。**改动只有一份入库 JSON**：`tests/fixtures/live_snapshot/snapshot-meta.json` **+42/−1**；28 个 run 文件重写后**逐字节相同**（`trim_run` 是纯函数），git 无 diff；`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性），照例排除。半宽预算照旧 **2.64pp > 反向验证余量 2.0**（余量 0.64），`--limit 5` 与上一轮同口径。**八条闸门步骤本地预演（与 CI 同命令、同数据）**：`--fail-if-above 8`→0、`--fail-if-above 1`→1、`--check-sample-size`→0、`--check-sample-size --margin 2`→7（期望值，反向验证）、`--check-per-workflow`→0、`--check-per-workflow-rate --fail-on-exceeds`→0、真实快照回归→0、全挂 fixture 回归→1。**数据轮不加测试**：判据行为 R59 已用 120 条测试覆盖，重导只改变量的取值；给入库真实快照加数值断言会让下一次重导先红，与「反向验证 fixture 数字漂了测试先红」的纪律正好相反。**未做**：①重导没有带来新样本（本机无新 run）；②history 仍只记计数不记 run_id，完全重叠无法从数据上识别，只能靠文档记录这一轮的事实；③8% 上限维持未校准；④per-workflow 历史基线/画像扫描合并/`min_ratio` 定量本轮未做（用户拍定只做主线）；⑤未跑 docker build（本机无 docker，GHA 真构建）；⑥未跑 `npm run build`（零前端改动）；⑦未重启 8021；⑧Desktop Windows 预期不触发（paths 只认 `desktop/`、`src/`、`web/`、`config/`、`requirements.lock` 与自身）。**推送与 CI 已闭环**：`818faf5`，run **41034747483** 五 job 全绿；新步骤 ubuntu 第 9 步 / windows 第 8 步均 success，两 runner 的真实快照判决逐字一致（判没有回归·基线 10/255·阈值 6.92%），ubuntu 另打印全挂 fixture 的「判回归 + 来源：回归」，windows 该行被 `$null =` 吞掉、按退出码断言 1 与 OK 行通过；四面用例数一致 **2219**（ubuntu 2155/64、windows 2190/29、Low 2106/113、High 2191/28）。推送通道：本轮 **socks5 10808 在运行**（`curl --socks5` 实测 api 200），`git push` 走配置代理成功；先试的「清空代理 + `curloptResolve` 三个 IP」全部 reset——与 R59 的通道状态相反。详见 HANDOVER_ROUND60.md。
- 2026-10-30 R61 双基线（**8% 政策上限首次校准：维持 8%，它是突破线不是健康线**）：Low-IL → **2106 passed / 113 skipped / 0 failed**（124.26s）；High-IL → **2191 passed / 28 skipped / 0 failed**（144.01s，权威）。净增 **0**（注释/文档轮：闸门 docstring +11、CI +9/−4、新增校准文档 148 行；零代码逻辑、零测试改动），总用例 **2219 不变**；前端 **490/0 不变**（`npm test` 实跑 8 子套件 48+60+137+81+139+1+18+6）。**用户拍定三项**：主线=8% 上限校准；范围=只做主线收口；收尾=照常推送 + 五 job 逐字核对。**本轮最重要的一件事：判 `normal` 的实际门槛是 5.10%，不是 8%。** n=255 的三条判决带：k≤13（5.10%）`normal` / 14–28（5.49%–10.98%）`undetermined` / k≥29（11.37%）`exceeds`；真实失败率恰为 8% 时 P(normal)=4.9%、P(undetermined)=91.5%——点估计落在上限上时上界必然高于上限，任何样本量都如此；检出率：2 倍基线 7.84% 只有 **2.85%**，10% 为 26.0%、12% 为 65.0%，50%/80%/95% 功效分别在 **11.25%/12.96%/14.75%**——它不是漂移探测器（漂移归 `--fail-on-regression`）。**维持 8% 的三条依据**：①全历史 40 个 run 合计 16/297=5.39%、95% 上界 **8.07%**，8% 是其整数化；②上限 ≤6.56%（快照上界）时当前数据立刻判不了——6%/6.5% 两档会让闸门再也说不出「正常」；③**7% 时政策带与回归带逐 k 完全重合**（都是 normal≤10 / exceeds≥26），8% 是第一个让政策层有独立判决带（≤13 / ≥29）的整数，与回归层隔 3 次失败（1.17pp）。候选对照（检出率 @10%/@12%）：6% 72.9/94.5、7% 48.9/83.7、**8% 26.0/65.0**、9% 10.8/42.2、10% 3.4/22.3、12% 0.3/4.7。**两个可执行结论**：①样本量门槛——normal 覆盖到 6% 观测需约 **475** 次尝试，10% 真实率 80% 功效需约 **1221**（精确实算 n=600 52.0%、800 61.0%、1000 71.6%）；②`_binomial_cdf_le` 的 `math.comb` 溢出**按形状记不按 n 记**：n=1100/k=550（50% 形状）溢出，本项目 k≈4%n 形状 **n=4000 仍可算**（[3.50%, 4.55%]），当前 255 远离边界，真到时是响亮 traceback 非静默放行，记为独立技术债。**CI 注释顺带校正一处过期事实**：原文还写着「入库快照只有一轮，这一步现在判 undetermined」，R60 之后已是两轮、判没有回归。**八条闸门本地预演全绿**（8→0、1→1、sample-size→0、margin 2→7、per-workflow→0、rate→0、回归→0、全挂 fixture→1），`ci.yml` 改后 `yaml.safe_load` 解析通过、5 job 齐全。**为什么没有新测试**：判据算术一行未动（120 条测试已覆盖），给校准表写数值断言只会在下次重导时先红，与「真实快照随导出变化」的纪律相反；可复核性由校准文档 §9 四条复现命令承担，且已逐条实跑（输出与文档逐字一致）。**未做**：①8% 是否业务可接受是价值判断（政策若改 6%，样本量须同步涨到 ~475）；②per-workflow 仍无绝对上限（不发明政策值）；③失败成因未分层（10 次失败：build 3 / mvp 4 / character 2 / post-hoc 1）；④CP 溢出未修；⑤未重导（本机最新 run 仍 2026-10-28，只会再写完全副本）；⑥未跑 docker build、未跑 `npm run build`（零前端改动）、未重启 8021；⑦Desktop Windows 预期不触发（paths 不含本轮改动面）。**下一轮第一候选**：有新 run 后再重导（回归判据首次真做两批比较，目前被数据卡住）。**推送与 CI 已闭环**：`977863b` + `3273156`，run **41041804988** 与 **41043045796** 均五 job 全绿；两 runner 的 8% 判决与回归判决逐字一致（判正常·来源无；判没有回归·阈值 6.92%），ubuntu 另打印全挂 fixture 的「判回归·来源：回归」；四面用例数一致 **2219**（ubuntu 2155/64、windows 2190/29、Low 2106/113、High 2191/28）；前端日志 8 个 `# pass` 块合计 **490**、`# fail` 合计 0、`✓ built in 10.26s`。推送通道：本轮 socks5 与直连同时可用（两条都 200），按配置走 socks5 成功。详见 HANDOVER_ROUND61.md。
- 2026-10-30 R62 双基线（**per-workflow 历史基线：判定力 2/9，提前量 2/5 次失败**）：Low-IL → **2127 passed / 113 skipped / 0 failed**（133.69s）；High-IL → **2212 passed / 28 skipped / 0 failed**（152.37s，权威）。净增 **+21**（`test_live_snapshot_gate.py` 120 → 141：新判据 16 个函数，其中一个参数化 ×5），零删除。总用例 R61 口径 2219 → **2240**；前端 **490/0 不变**（零前端改动，`npm test` 实跑 8 子套件 490 条）。**用户拍定三项**：主线=per-workflow 历史基线；范围=只做主线收口；收尾=照常推送 + 五 job 逐字核对。**本轮最重要的一件事：这个判据只有 2/9 个 workflow 说得出话，而这 2 个是自比自。** 可判集合由 `sample_size_margin_needed` 决定，与 `--check-per-workflow` 判「精度达标」的那批**完全重合**（同一把尺，不另立门槛）：character 2/79（半宽 5.22pp）、mvp 4/56（8.46pp）可判；build 12.76、post-hoc 14.12、outline/story-plan 17.07、polish 19.26、reader-sim 22.09、export 45.07 判不了——拿 0/5 的 95% 上界 45pp 当阈值，当前只要一次失败就会被判回归，那是向错方向的假红。而可判的两个两轮计数**完全相同**（history 第二轮是副本，R60 的自比自），输出里逐字写「这是样本没有新增，不是质量结论」——「没红」不能被读成「逐 workflow 都健康」。**真实增量（同一份基线实算）**：character 逐 workflow 16/79（下界 13.14% > 阈值 12.53%）就判回归，合并层要 18/79（全局下界 7.24% > 6.92%）→ **早 2 次失败**；mvp 15/56（17.29% > 17.14%）vs 20/56 → **早 5 次**。中间那一段合并层结构性看不见：大体量 workflow 变坏被其余 7 个摊薄，全局率只挪几个千分点。**设计**：阈值 = 上一轮失败率 + `--margin`(10)，与合并层共用 `_baseline_verdict` / `_cp_interval` 三分法；`undetermined` 永不判失败（区间横跨 / 覆盖变化 / 基线太薄三类），处置是重导更多 run；覆盖变化逐 workflow 显式写「失败率不可比」（与 R58「缺席即中断」、R59「集合不同不判回归」同一纪律）；`unchanged` 单独计数不折进 `normal`；「可判 0 个」与「没有可比上一轮」都明写「**本步没有判定力**，退出 0 不代表没有回归」（R61 恒绿教训的直接应用）；退出码 1 只在 `exceeds`，来源行写 `退出码 1 的来源：逐 workflow 回归（wf-bad）`；无样本 3、元数据漂移 4；不设报告模式开关（回归的含义就是判据，报告用途归 `--check-per-workflow`）。**顺带去重**：抽出 `_per_workflow_drift` + `_drift_message` 供三条 per-workflow 判据共用（删掉两份重复的 19 行检查），并用测试钉住三者退出码 4 的文案**逐字相同**；原 137 条测试在重构后全部通过。**改动**：脚本 **+254/−38**、`ci.yml` **+58**（两个 job 各加一步，含反向验证）、测试 **+258**，合计 **+570/−38**。**两次变异全部咬合**：判决恒 `normal` → 5 红（jump/straddle/exceeds fixture/malformed/CLI）；关掉 eligible 守卫 → 2 红（only_judges/committed snapshot）；`cp` 备份还原后 141 绿（不用 `git checkout --`，R55 教训）。**十条闸门本地预演全绿**（8→0、1→1、sample-size→0、margin 2→7、per-workflow→0、rate→0、回归→0、全挂 fixture 回归→1、**逐 workflow 回归→0（2 可判/7 判不了/2 unchanged）**、全挂 fixture 逐 workflow→1）；`ci.yml` 改后 `yaml.safe_load` 解析通过、5 job 齐全、新步骤两 job 各 1 处。**未做**：①7/9 判不了是数据事实（16 次需约 29 次尝试才到 margin 10，export 5 次物理补不到）；②判定力只在两个大 workflow 上验算过，真实数据从未见 `exceeds`，靠 `live_snapshot_exceeds` 反向验证；③8% 上限 / 失败成因分层 / `min_ratio` 定量 / 画像扫描合并均未做（范围只做主线）；④未重导（本机最新 run 仍 2026-10-28 08:34，只会再写完全副本）；⑤CP 溢出未修；⑥未跑 docker build、未跑 `npm run build`（零前端改动）、未重启 8021；⑦Desktop Windows 预期不触发（paths 不含本轮改动面）。**下一轮第一候选**：有新 run 后再重导（本轮新判据首次能做真正的两批比较，当前被数据卡住）。详见 HANDOVER_ROUND62.md。
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
