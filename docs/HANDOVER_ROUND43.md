# DeterminFlow (xs2) 交接报告 — Round 43（维护轮：画像跨 run 对比视图 + POSIX 真跑调研收口）

> 本轮定位：落地 R41 §8-2 / R42 §8-2 的候选（画像跨 run 对比视图），把画像从
> 「单 run 快照」升级为「与上一次 run 的逐阶段差值」；同时完成用户指定的
> POSIX 真跑**调研**（只出结论不实施），调研过程中推翻了历轮「POSIX 未覆盖」
> 的表述——CI 的 ubuntu job 一直在真实 Linux 上跑全量。
> 基线：`a6e4927`（R42 文档尾）→ 本轮 xs2 提交 1 个（见 §5），插件仓零提交。

## 1. 画像跨 run 对比（R41 §9-2 / R42 §8-2）

### 1.1 设计决策（每条都有对应测试钉死）

沿用 R42 失败率闸门的取舍风格，把「对比语义」放进后端纯函数，前端只做渲染：

| 决策 | 理由 |
|---|---|
| 「上一次 run」由**后端**挑，前端不二次请求 | 前端两次 GET 会有时序竞态（两次扫描之间可能写入新 run），且对比对象选择口径必须可单测 |
| 「上一次」= 排序键**严格更小**的最大者 | 没有更早的 run 时诚实返回 `null`，不拿更晚的 run 冒充 |
| 排序键优先 `started_at`、坏值回落文件 `mtime` | run 记录两种形态都出现过（B31 前 `completed_at` 恒 null）；统一取 `timestamp()` 浮点，避开 aware/naive datetime 直接比较抛 TypeError |
| 阶段按 **node_id 汇总**同一 run 内的重复执行 | `agent_deep` 在一个 run 里可跑 4 次；按出现序号配对会在两次 run 执行次数不同时留下无对应孤儿 |
| 差值恒为 **current − previous**，未舍入比值算 | 正值=退步、负值=改善；先 `round(4)` 会让 1/3 这类边界判平（与闸门同理） |
| 任一侧该阶段无尝试 → `comparable=false` 且差值为 `null` | 「无数据」不等于 0%，不让它冒充 0% 改善或恶化 |
| `?compare` 缺省不带 | 不带参数就完全不走那次 `runs/` 目录扫描，既有调用零额外开销 |

### 1.2 后端（`src/workflow/run_profile.py`）

新增两个纯函数（均为只读入参、不触文件系统）：

- `pick_previous_run(current, candidates)`：从 `{run_id, started_at, mtime}` 元数据里
  挑严格更早的最大者。
- `compare_run_profiles(current, previous)`：输出 `previous_run_id / previous_status /
  时间戳 / delta_wall_seconds / totals{...delta...} / stages[]`，每阶段含
  `occurrences_* / attempts_* / failed_* / failure_rate_* / delta_failure_rate /
  delta_attempts / comparable`。

### 1.3 端点（`src/web/workflow_routes.py`）

`GET .../tasks/{task}/run-profile` 新增 `compare: bool = False` 查询参数。开启时
额外扫 `runs/` 目录（`_iter_run_metadata`，坏 JSON 与读失败一律跳过——一条损坏
记录不该把对比对象带歪）、载入上一次 run 画像（`_load_run_profile`）并挂
`comparison` 键。**仍属 GET 只读面**：不建目录不写状态，B26/B28 静态钉测的
零建目录断言同步扩到 `?compare=true` 变体。

### 1.4 前端

- `types/index.ts` 新增 `RunProfileComparison` / `RunProfileComparisonStage`，
  `RunProfile` 增可选 `comparison`。
- `api.ts` 的 `getTaskRunProfile` 增 `compare` 形参，用 `URLSearchParams` 拼参
  （顺带把 `run_id` 从手工 `encodeURIComponent` 改为同一套参数构造）。
- `runProfileView.ts` 新增四个展示映射纯函数：`formatFailureRateDelta`（`+17%` /
  `-17%` / `持平` / `-`）、`failureRateDeltaClass`（退步红/改善绿/中性）、
  `formatCountDelta`、`formatDurationDelta`。
- `RunProfilePanel.tsx`：「与上一次 run 对比」复选框 + 汇总对比卡（上次 run_id、
  状态、总失败率差值、尝试差值、总耗时差值 + 差值口径说明）+ 每张阶段卡一行
  对比（失败率差值 + 上次值 + 尝试差值）。

**一处刻意的 UX 取舍**：切换对比开关时重新取「当前正在看的那个 run」（
`profile?.run_id`），而不是跳回最新 run——用户可能在查历史 run 的过程中才想起
开对比，跳回最新会丢掉他选中的上下文。有测试钉死（先查 `run-99b3bd1b` 再开
对比，断言两次调用的 runId 都是 `run-99b3bd1b`）。

### 1.5 测试

后端 `tests/test_run_profile.py` 14 → **28**（+14）：

| 用例 | 断言 |
|---|---|
| `..._pools_repeated_nodes_and_uses_signed_deltas` | 一 run 内同 node 4 次执行汇总（occurrences 4 vs 2），差值恒 current−previous |
| `..._improvement_is_negative` | 改善场景差值为负（0.0 − 2/3 = −0.6667） |
| `..._stage_only_in_one_run_is_not_comparable` | 新增/消失阶段两侧 `comparable=false`、`delta_failure_rate=None` |
| `..._empty_runs_stay_non_comparable` | 两次空 run 的差值是 None 而非 0 |
| `..._delta_uses_unrounded_ratio` | 1/3 差值 = 0.3333（不是舍入后判平） |
| `test_pick_previous_run_picks_strictly_older`（3 参数） | 更早命中 / 只有更晚则不命中 / 当前缺 `started_at` 回落 mtime |
| `..._falls_back_to_mtime_for_unparsable_time` | 坏 started_at 下 mtime 比较不抛错且选择确定 |
| `..._endpoint_compare_block` | 200 载荷含 comparison，原画像字段不变 |
| `..._without_compare_has_no_comparison_key` | 不带参数**完全没有** `comparison` 键 |
| `..._compare_on_oldest_run_is_null` | 最早那个 run 的 comparison 诚实为 null |
| `..._compare_skips_corrupt_sibling` | 损坏兄弟记录不参与选择也不让请求失败 |
| `..._compare_creates_nothing` | `?compare=true` 仍零建目录 |

前端净增 **6**（`runProfileView.test.ts` 5→7、`RunProfilePanel.test.ts` 5→9，共 16）：
差值格式化与色调、计数/时长差值、对比开关透传当前 run、对比块与逐阶段行渲染、
`comparable=false` 诚实标注、无更早 run 的空态提示。

### 1.6 活体暴露并修掉的一处文案缺陷

真实数据（`xs2-novel-flywheel-character` / `run-cef95ebf` vs `run-04ea8e0b`）走查时
发现：阶段对比行显示「尝试 0（上次 1）」——本意是**差值为 0**，却被读成「尝试数
为 0」。修复：差值 0 显示「持平」，与失败率差值同款语义。汇总行同样处理。

## 2. POSIX 真跑调研（用户指定：只调研不实施）

### 2.1 结论先行：缺口比历轮记录的窄得多

历轮（R24–R42）一直把「POSIX 真跑」记为「前置：容器/WSL 环境」的未覆盖项。
本轮取证推翻了这个表述——

**`CI` 的 ubuntu `backend` job 一直在真实 Linux（ubuntu-24.04.5 LTS）上跑全量**：

| 平台 | passed | skipped | 说明 |
|---|---|---|---|
| ubuntu-24.04（CI `backend`） | **1870** | 64 | 真实 Linux 全量 |
| windows-latest（CI `windows-backend`） | **1905** | 29 | 真实 Windows 全量 |
| 本机 High-IL（权威） | 1937 | 11 | 权威基线 |

（三处数字不同是因为各平台 skip 面不同。ubuntu 64 条 = Windows 文件系统语义 40 +
humanware e2e（服务未运行）17 + macOS 签名/图标 7；Windows 29 条 = humanware e2e
17 + macOS 签名/图标 7 + POSIX fcntl 2 + Unix 进程树/组 2 + 其他 1。）

即：**除「Mac 桌面签名」与「真机服务 e2e」外，POSIX 语义已被 CI 每推一次全覆盖**。

### 2.2 剩余真实缺口（三项，均非代码缺陷）

1. **`docker compose config -q` 之外的容器面**：`container-config` job 只做配置
   语法校验，**从未 `docker build`**。`Dockerfile` 的多阶段构建（前端 `npm ci` +
   `npm run build`、`pip install -r requirements.lock`、`gunicorn` 启动）在 CI 上
   零验证。本机 `docker` / `wsl` 均未安装（实测 `docker: command not found`、
   `wsl --status` 报未安装内核），因此这一面在本机不可验证。
2. **真机服务 e2e**：`tests/test_humanware_e2e.py` 需要 8021 在跑。CI 不上服务，
   **17 条恒 skip**（ubuntu 与 Windows 两侧同为 17）。本机有服务时可真实执行
   （R21/R40/R41 都实跑过 17/0 或 15/0）。
3. **Mac 桌面签名**：`test_desktop_macos_signing.py` 6 条 + `icon.icns` 1 条，
   只在 macOS runner 上能跑。`desktop-macos.yml` 存在但历轮未核对过结果。

### 2.3 若要真补齐，三个选项（供下一轮决策，本轮不实施）

| 选项 | 覆盖什么 | 代价 | 风险 |
|---|---|---|---|
| **A. CI 加 `docker build` job**（推荐） | 缺口 1：镜像能否构建、`requirements.lock` 是否自洽、gunicorn 能否起 | 一次构建数分钟 + 镜像层缓存；`web/package-lock.json` 必须与 `package.json` 同步（`npm ci` 严格） | 低。失败即真缺陷，且 `container-config` 已证明 compose 语法没问题 |
| **B. CI 起 8021 再跑 e2e** | 缺口 2：17 条 e2e 从 skip 转真跑 | 需在 job 内后台起服务 + 等 `/docs` 就绪 + 拉起 agent 依赖（模型 provider 不可用会让 e2e 假失败） | **高**。CI 无模型凭据，e2e 会因 provider 不可达失败，需先做成「凭据缺失则诚实 skip」 |
| **C. 核对 `desktop-macos.yml` 历史结果** | 缺口 3：确认 macOS 签名流水线是否长期红 | 只需读 CI 记录（与 R42 排 `Desktop Windows` 同法，用 GCM token 拉日志） | 低，且属核对而非改动 |

**推荐**：下一轮做 A + C（低风险、覆盖真实构建面），B 需要先解决 CI 无模型凭据的
设计问题，建议另开一轮。

## 3. POSIX 调研的附带发现

- `.dockerignore` 排除了 `tests/` 与 `pytest.ini`，所以镜像内不含测试——这与
  「镜像是运行载体而非开发环境」的定位一致，不是缺陷，但意味着**镜像内的行为
  只能靠外部探测**（`HEALTHCHECK` 打 `/docs`）。
- `Dockerfile` 的 `HEALTHCHECK` 用 `curl -sf http://localhost:8020/docs`，而
  compose 把 `WEB_PORT` 设为 8020——两处一致 ✓。
- `scripts/docker-entrypoint.sh` 先跑 `session_retention` 再 `exec "$@"`，
  `test_plugin_docker_contract.py` 对这两点有静态钉死 ✓。

## 4. 供应商失败率时间序列（第 3 个数据点）

`python scripts/provider_failure_profile.py --summary`（每 workflow 最近 3 次 run）：

```
xs2-novel-flywheel-build:      runs=3 attempts=27 failed=1 failure_rate=3.7%  failing_stages=agent_corelaws                          error_classes={"http_5xx": 1}
xs2-novel-flywheel-character:  runs=3 attempts=75 failed=1 failure_rate=1.3%  failing_stages=agent_deep                              error_classes={"timeout": 1}
xs2-novel-flywheel-export:     runs=3 attempts=3  failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-mvp:        runs=2 attempts=56 failed=4 failure_rate=7.1%  failing_stages=script_check_originality,script_smart_context error_classes={"other": 4}
xs2-novel-flywheel-outline:    runs=2 attempts=16 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-polish:     runs=2 attempts=14 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-post-hoc:   runs=3 attempts=24 failed=1 failure_rate=4.2%  failing_stages=script_confirm_archive                  error_classes={"other": 1}
xs2-novel-flywheel-reader-sim: runs=3 attempts=12 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
xs2-novel-flywheel-story-plan: runs=2 attempts=16 failed=0 failure_rate=0.0%  failing_stages=-                                       error_classes={}
TOTAL: runs=23 attempts=243 failed=7 failure_rate=2.9%
```

**与 R41/R42 逐行完全一致**——本轮未产生新 run（纯维护轮），口径稳定可比。
R41 → R42 → R43：2.9% → 2.9% → **2.9%**。

闸门实跑：`--summary --fail-if-above 5` → exit 0，stderr
`[gate] 总失败率 2.88% 未超出阈值 5.0%（243 次尝试）`。

## 5. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | 本文档提交 | `feat(profile)` 画像跨 run 对比 + 交接文档 + PROJECT_INFO R43 条目 |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性，
与历轮一致）。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_run_profile.py` | **28 passed**（14 → 28） |
| 定向：画像 + 闸门脚本 | **38 passed** |
| Low-IL 全量 | **1852 passed / 96 skipped / 0 failed**（96.40s） |
| High-IL 全量（权威） | **1937 passed / 11 skipped / 0 failed**（129.80s） |
| 前端 8 组 | **463 passed / 0 fail**（净增 6） |
| 前端 workflow 组 | 33 passed / 0 fail |
| 前端 lint / build | 0 problems / ✓ 5.53s |
| 插件套件（双 CWD） | **98 passed ×2** |
| 存储名审计 | **[clean]** exit 0 |
| 索引污染复查 | **59 条，零 pytest 污染**，与 R40/R41/R42 一致 |
| CI（`a6e4927`，上一轮） | **四 job 全绿**（ubuntu 1870/64、windows 1905/29） |

对账：Low 1838 + 14 = **1852** ✓；High 1923 + 14 = **1937** ✓。
总用例 R42 口径 1934 → **1948**（High passed+skipped：1937+11）。

## 7. 活体走查（本轮有后端行为变更，按 R40 §7.5 纪律重启服务）

- **重启方式**：`Stop-Process` 旧 PID 22200 → `powershell Start-Process -WindowStyle
  Hidden` 启动，新 PID **26252**，`/api/system/status` 200。
- **API 探针**（真实数据 `xs2-novel-flywheel-character` / `task-0467488b`）：
  - `?compare=true` → 200，`comparison.previous_run_id = run-04ea8e0b`，
    总差值 `delta_failure_rate = -0.25`（本次 0% vs 上次 25%）、`delta_attempts = +26`；
    逐阶段：`script_extract` 差 −100%（修复确认）、`agent_belief` 等 `comparable=false`。
  - 最早 run（`run-22cf1120`）加 `compare=true` → `comparison` 为 **null**（诚实无对比对象）。
  - 穿越形态 `run_id=..%2F..%2Fx` → **400**；幻影 `run-ghost` → **404**。
- **UI 走查**（真实浏览器，工作流 → 任务历史 → 搜索 `task-0467488b` → 打开任务 →
  运行画像抽屉 → 勾选「与上一次 run 对比」）：
  - 汇总对比卡渲染 `run-04ea8e0b` / 上次 失败 / 总失败率 −25% / 尝试 +26 /
    总耗时 − / 差值口径说明；
  - 18 张阶段卡各自出现对比行（`对比 失败率 持平（上次 0%）`、`对比 不可比
    （上一次 run 无该阶段尝试）`）；
  - 发现并修掉「尝试 0」歧义文案（见 §1.6），修后复验为「持平」；
  - 截图 `data/system/test-probes/r43-run-profile-compare.png`。

## 8. 遗留风险与需人工确认事项

1. **容器镜像从未被构建验证**（本轮发现，见 §2.2 缺口 1）：`container-config`
   job 只校验 compose 语法，`Dockerfile` 的多阶段构建（`npm ci` + `pip install -r
   requirements.lock` + gunicorn）在 CI 上零覆盖，本机也无 docker/wsl 可自查。
   **这是本轮调研暴露的最大单项风险**，建议下一轮做 §2.3 选项 A。
2. **插件仓推进必须刷新本仓锁**（R42 纪律，本轮冻结）：本轮插件仓零提交，
   `official-plugins.lock.json` 无需刷新。
3. **CI 日志接口需 token**：`/actions/jobs/{id}/logs` 对匿名请求 403。本轮沿用
   R42 方法（`git credential fill` 取 GCM 存的 token）。
4. **vendor 文件 provenance 哈希依赖字节保真**（R42 纪律）：本轮未新增第三方快照。
5. **代理通道分流**：socks5 10808 对 TLS 不稳，HTTP 10509 稳定；git 传输用 socks5 正常。
6. **High-IL 跑法必须用 Windows 反斜杠路径**（PROJECT_INFO 平台注意事项 9）。
7. **`F:\DeterminFlow x2` 路径含空格会挡 Rust 构建**（R42 §3.3）：需
   `CARGO_TARGET_DIR` 指无空格路径。
8. **服务进程托管**：仍须 `powershell Start-Process -WindowStyle Hidden`，本轮
   实测有效（新 PID 26252）。
9. **本轮未推送**：1 个提交积压在本地，CI 未触发。

## 9. 下一轮候选

1. **CI 加 `docker build` job**（§2.3 选项 A，低风险高价值）：补齐镜像构建这个
   唯一完全无覆盖的面。需先确认 `web/package-lock.json` 与 `package.json` 同步
   （`npm ci` 严格），并接受每次 CI 多几分钟。
2. **核对 `desktop-macos.yml` 历史结果**（§2.3 选项 C，低成本）：与 R42 排
   `Desktop Windows` 同法读 CI 记录，确认 macOS 签名流水线是否长期红。
3. **推送 + CI 全量核对**（需维护者授权）：本轮 1 个提交积压。
4. **循环节点与重试语义区分**（R41 §9-3，需后端 Core 配合）：
   `attempt_history` 区分「循环第 N 轮」与「第 N 次重试」——本轮对比视图按
   node_id 汇总，正是这个语义缺口的绕行方案；真正区分后对比可以细化到逐轮。

其余：CI 起服务跑 e2e（§2.3 选项 B，需先解决模型凭据设计）、大陆下载加速
（待基础设施决策）。
