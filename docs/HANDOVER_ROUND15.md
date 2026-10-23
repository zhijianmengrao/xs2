# DeterminFlow (xs2) 交接报告 — Round 15（契约 v3：错误码透传 + 超长内容 stdin 通道）

> 生成时间：2026-10-23
> 项目路径：`F:/DeterminFlow x2/xs2`（主仓库）；`F:/DeterminFlow x2/DeterminFlow-Plugins`（插件仓库）
> 分支：main（两个仓库各自）
> 本轮提交：xs2 `c3bbdad`（修复+测试+契约）、`c747a79`（端到端脚本）、文档提交（本文件 + 契约 §4 校正）；插件 `582de10`（修复）、`3c8ff4e`（性能）
> 上一轮：[HANDOVER_ROUND14.md](./HANDOVER_ROUND14.md)
> 接口契约：[humanware-helper-contract.md](./humanware-helper-contract.md)（本轮升 **v3**）
> 文档编码：UTF-8

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| 本轮定位：humanware 契约面（R12–R14 新建特性）系统化边界/异常/安全测试 | 见 §2 测试计划；缺口来自路由与 CLI 逐行审查 |
| **发现并修复 3 个真实缺陷**（B1/B2/B3），均先用失败测试固化再修 | §3 用例表、§4 Bug 报告；B3 有 `WinError 206` 实测证据 |
| 后端全量回归 **1529 passed / 36 skipped / 0 failed**（基线 1523 + 新增 6） | `pytest -q` 实跑，跳过分布不变（全为环境限制） |
| 插件侧测试 15 → **23** 条；xs2 humanware 路由 9 → **15** 条 | 两仓库 pytest 实跑 |
| 前端无改动，回归仍绿 | lint **0 problems** / `npm test` 全过 / build 成功 |
| 契约 v3 端到端 **9/9 PASS**（真实 8021 + 真实 runtime CLI） | `scripts/_hw_e2e_r15.py` 退出码 0 |
| 优化 O1：score-chapter 归属算法 `O(Q×N)` → `O(N+Q log S)`，等价性有测试守卫 | 插件 `3c8ff4e`；对照章 78 vs 归属章 92 |
| 工作区状态 | 两仓库均干净；插件 `582de10`/`3c8ff4e` **仍未推远端**（连同 R14 的 `e4ba419`） |

## 2. 测试计划（本轮）

- **范围**：humanware 契约面（`src/web/humanware_routes.py` 6 端点 + 插件 `humanware_helper.py` 5 命令）；全量回归；前端回归。选择理由：该面 R12–R14 新建，边界/异常覆盖相对最薄。
- **类型**：功能（契约五命令）、边界（内容长度上下界）、异常（业务失败码、超时、缺失文件、非法 id）、安全（路径穿越、workspace_id 白名单、无 shell 注入面）、性能（算法复杂度）、回归（全套 + 等价性对照）。
- **环境**：Windows 本机，venv Python 3.14.8，服务 `http://localhost:8021`，工作区 `welcome` / 临时隔离工作区。全量回归前已停服务避免干扰。
- **通过标准**：`pytest` 0 failed（环境类 skipped 允许）；前端 lint 0 errors / test 全过 / build 成功；契约偏差 0；新增用例全绿；e2e 脚本退出码 0。
- **运行命令**：
  ```
  cd "F:\DeterminFlow x2\xs2"
  .\.venv\Scripts\python.exe -m pytest -q                                   # 全量后端
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_routes.py -v    # 定向
  cd plugins/xs2-novel-flywheel && <xs2 venv python> -m pytest tests/test_humanware_helper.py -v
  cd web && npm.cmd run lint && npm.cmd test && npm.cmd run build            # 前端
  ```

## 3. 测试用例与执行结果

### 3.1 本轮新增（xs2 路由，`HumanwareContractHardeningTests`，9 → 15）

| 编号 | 场景 | 前置 | 预期 | 实际 | 状态 |
|---|---|---|---|---|---|
| TC-R15-01 | check-dialogue 未知角色（CLI 业务码 409） | 假 CLI 输出 error/code=409 | HTTP **409** | 修复前 500 → 修复后 409 | ✅（修后） |
| TC-R15-02 | score-content **42,000** 字符（> 命令行上限） | 假 CLI `-` 读 stdin | HTTP 200，`content_len` 完整往返 | 修复前 500(`WinError 206`) → 修复后 200 | ✅（修后） |
| TC-R15-03 | check-dialogue **50,000** 字符（同上） | 同上 | HTTP 200，`dialogue_len` | 修复前 500 → 修复后 200 | ✅（修后） |
| TC-R15-04 | score-content 短内容（3 字符） | 同上 | 200，仍走 argv | 200 / 3 | ✅ |
| TC-R15-05 | PUT voice-file：URL id 与 body id 不一致 | books=临时 | 200，以 **URL** 为准（beta 不影响） | 200，写入 alpha | ✅ |
| TC-R15-06 | CLI 超时（mock `TimeoutExpired`） | — | 内部 error/500 语义 | status=error, code=500 | ✅ |

> 红灯证据：TC-01/02/03 首跑 `3 failed`；stderr 实见 `[WinError 206] 文件名或扩展名太长`（B3 触发点 `humanware_routes.py:133` 的 `except OSError`）。

### 3.2 本轮新增（插件 CLI，15 → 23）

| 编号 | 场景 | 预期 | 状态 |
|---|---|---|---|
| TC-P15-01 | `score-text ... -` 进程内 stdin 读取（伪 stdin） | success / character 正确 | ✅ |
| TC-P15-02 | check-dialogue 无违规且**未命中**口头禅 | suggestion = `符合定义，保持。`（不含「已命中口头禅」） | ✅（修后） |
| TC-P15-03 | check-dialogue 命中口头禅 | suggestion = `已命中口头禅，语气一致。` | ✅ |
| TC-P15-04 | 真实子进程 `score-text` 42K 经 stdin | returncode 0 + total_score | ✅ |
| TC-P15-05 | 真实子进程 `check-dialogue` stdin | matches 判定 | ✅ |
| TC-P15-06 | 章节按 `## 角色名` 归属评分 | 2 段对白、维度分不同 | ✅ |
| TC-P15-07 | **等价性对照**：合成章节（CRLF、`###` 干扰标题、标题前对白、未定义角色标题） | 新算法（预计算+二分）逐条等于旧反序扫描 | ✅ |
| TC-P15-08 | 等价性：标题前首条对白 | 两实现均 None | ✅ |

### 3.3 契约级端到端（真实 8021 + `3c8ff4e` runtime CLI）

`.\.venv\Scripts\python.exe scripts/_hw_e2e_r15.py` → **9/9 PASS，EXITCODE=0**

| 编号 | 场景 | 实测 |
|---|---|---|
| E1 | generate-voice（argv 短路径） | 200，character_count=2 |
| E2 | **score-content 42,000 字符 → stdin 通道** | 200，total=93 / grade=A |
| E3 | score-content 短内容 argv | 200，total=96 |
| E4 | **check-dialogue 未知角色 → 409**（修复前 500） | 409，detail 含角色名 |
| E5 | **check-dialogue 50,000 字符 → stdin** | 200，matches=True |
| E6 | check-dialogue 文案（真实 CLI） | suggestion=`符合定义，保持。` |
| E7a | score-chapter 缺失章节 | 404（契约正确语义，**断言**而非兜容） |
| E7b1 | score-chapter 归属章（O1） | 200，scored=2，声音一致性=92 |
| E7b2 | score-chapter 对照章（无标题） | 声音一致性=78 < 92 → **归属生效实证** |

### 3.4 安全类复查

| 场景 | 结果 |
|---|---|
| workspace_id 穿越（`..`、`a/b`、`data/workspaces/books/../../../config`、URL 与 body 两层） | 全部 400/404，无 2xx 逃逸（既有用例复跑通过） |
| `chapter_file` 绝对路径/`..` 逃逸 | CLI `_resolve_in` → 400（既有 + 本轮 e2e 复现） |
| shell 注入面 | `subprocess.run([...])` 列表形式 + `text=False`，无 shell=True；stdin 传输不引入命令面 |
| 并发 | `_CLI_SEMAPHORE=4` + `asyncio.to_thread`（R12 已实现，本轮未改）；`_VOICE_FILE_LOCK` 保护写 |

## 4. Bug 报告与根因分析

### B1 — check-dialogue 把 CLI 业务错误固定映射为 HTTP 500
- **现象**：未知角色请求 `check-dialogue` 返回 500；同错误在 `score-content` 返回 409。
- **复现**：对存在 voice 文件的工作区 POST `/api/humanware/check-dialogue {character:"不存在的人"}` → 500（修复前）。
- **根因**：`humanware_routes.py` 中 `check_dialogue` 分支硬编码 `status_code=500`，未像 `_generate_voice_file`/`score_content`/`score_chapter` 那样读 `result["code"]`；契约 §2.2 要求 code 透传。
- **影响**：前端无法区分「角色未定义（可引导修复）」与「服务内部错误」，错误提示误导；契约一致性破坏。
- **修复**：`code = int(result.get("code", 500))` 后 `raise HTTPException(status_code=code, ...)`。
- **风险**：原依赖 500 的调用方需改判 409（前端目前未调用该端点，风险为零）。

### B2 — check-dialogue 的 suggestion 谎称命中口头禅
- **现象**：无违规且未命中口头禅时，返回「已命中口头禅，语气一致。」
- **根因**：三元链语义错位——`"符合定义，保持。" if not violations and tone_hits else ("已命中口头禅，语气一致。" if not violations else ...)`：`not violations and not tone_hits` 落到第二个分支。
- **修复**：改显式三分支（violations → 调整提示；tone_hits → 口头禅提示；否则 → 符合定义，保持）。
- **取舍**：备选方案是保留两分支只换文案，但显式分支可读且可测（TC-P15-02/03 分别钉住两个正向分支）。
- **风险**：极低（纯文案，字段与结构不变；既有用例只断言 `matches`）。

### B3 — 超长 content/dialogue 经 argv 传输在 Windows 必然失败
- **现象**：`score-content` 内容 ≥ ~33,000 字符返回 500 `命令启动失败: [WinError 206] 文件名或扩展名太长`；`check-dialogue` ≥ ~33K 同（其模型上限 200K）。而 HTTP 模型分别允许 10M / 200K —— **接口声明与可实现范围不一致**。
- **实测边界**（同一 venv 解释器，逐长度探测）：10,000 / 30,000 / 31,000 / 32,000 字符可启动；33,000 / 50,000 → `OSError [WinError 206]`。上限来源为 Windows `CreateProcess` 命令行 ≈32,767 UTF-16 单元；POSIX 侧受 `ARG_MAX` 约束同样存在此缺陷。
- **根因**：路由用 `subprocess.run([...], 内容作为 argv 末位)`，未考虑平台命令行长度上限。
- **修复（契约 v3）**：> 8,192 字符时 argv 传占位符 `-`，真实内容 UTF-8 经 **stdin** 传入；CLI 侧 `_arg_or_stdin()` 在值为 `-` 时读 stdin（`errors="replace"` 兜底）。阈值 8,192 远小于最紧平台上限，同时保持短内容走原 argv 路径。
- **备选方案与取舍**：
  1. *临时文件传路径*：需引入临时目录生命周期与清理，且 CLI 会读写工作区外文件（违反契约 §4「不得读写工作区之外」）→ 否。
  2. *API 层把 content 限制降到 32K*：破坏既有 HTTP 契约（10M），属功能回退 → 否。
  3. *始终走 stdin*：改动面与 CLI 直调用法全变，回归风险更高 → 否。
  4. *阈值 + `-` 约定*（选定）：增量、向后兼容，短内容行为完全不变。
- **已知边界语义**：内容恰为字面量 `"-"` 会被当作 stdin 通道（stdin 空 → 按无内容评分）。已在契约 §1 显式记录；单字符内容无评分意义，可接受。

### D1 — 文档与实现不一致（非代码缺陷）
- 契约 §4 曾称 `learning/candidates.json` 是 analyze-voice 输入；实现仅扫描 `references/`（grep `learning|candidates` 在 CLI 内 **0 命中**）。
- 处理：本轮做文档校正（标注「当前实现未读取」），把「candidates 接入 analyze-voice」列为下一轮可选功能项（见 §9 R15-3）。

## 5. 修复代码要点（补丁位置）

| 文件 | 位置 | 变更 |
|---|---|---|
| `src/web/humanware_routes.py` | `check_dialogue` 错误分支 | `int(result.get("code", 500))` 透传（B1） |
| `src/web/humanware_routes.py` | `_run_humanware_command_blocking` / `_run_humanware_command` | 新增 `stdin_text` 形参，`subprocess.run(..., input=bytes)` |
| `src/web/humanware_routes.py` | `_STDIN_ARG_THRESHOLD=8192` + `_content_arg()` | 长度判定返回 `(argv_value, stdin_text)` |
| `src/web/humanware_routes.py` | `score_content` / `check_dialogue` 调用点 | `content_arg, content_stdin = _content_arg(...)` |
| 插件 `humanware_helper.py` | `_arg_or_stdin()` | `-` → `sys.stdin.buffer.read().decode("utf-8", errors="replace")`（B3） |
| 插件 `humanware_helper.py` | `cmd_score_text` / `cmd_check_dialogue` | 内容参数经 `_arg_or_stdin` |
| 插件 `humanware_helper.py` | `cmd_check_dialogue` suggestion | 显式三分支（B2） |

> 完整 diff 见各仓库提交：xs2 `c3bbdad`、插件 `582de10`。

## 6. 回归测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| xs2 humanware 路由 | `pytest tests/test_humanware_routes.py -v` | **15 passed**（9 → 15） |
| 插件 CLI | `pytest tests/test_humanware_helper.py -v` | **23 passed**（15 → 23） |
| 后端全量 | `pytest -q`（**服务已停**） | **1529 passed / 36 skipped / 0 failed**（118.07s） |
| 跳过项 | 同前：23 symlink 特权 + 6 macOS + 2 fcntl + 2 Unix | 分布与基线一致（环境限制，非代码缺陷） |
| 前端（无改动） | `npm.cmd run lint` / `test` / `build` | 0 problems / 全过 / 成功 |
| 契约端到端 | `scripts/_hw_e2e_r15.py` | **9/9 PASS**，EXITCODE=0 |
| 插件激活链路 | `POST /api/plugins/xs2-novel-flywheel/update` → 重启 | `resolved_commit=3c8ff4e`、`runtime_status=running`、`restart_required=false`；runtime CLI 已含 `_arg_or_stdin` 与 `import bisect`（内容级核实） |

**O1 性能优化（附带项）**：`cmd_score_chapter` 原对每条对白 `text.find()` + 全前缀 `splitlines()` 反序扫描（`O(Q×N)`，长章节重复分配大列表）；改为 `_anchor_boundaries()` 一次线性扫描预计算标题偏移 + `_owner_at()` 二分（`O(N + Q log S)`）。语义等价由 TC-P15-07/08 用**内联旧算法为参照**逐条比对保证（含 CRLF、`###` 干扰标题、标题前对白、未定义角色标题）。生产代码不留兼容死函数（旧实现仅存在于测试参照中）。插件 `3c8ff4e`。

## 7. 优化清单（本轮）

| 编号 | 问题 | 方案 | 预期收益 | 风险 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| O1 | score-chapter 归属 `O(Q×N)` | 预计算边界 + 二分 | 大章节 CPU/内存显著下降，行为不变 | 等价性风险 → 对照测试守卫 | 中 | ✅ `3c8ff4e` |
| O2 | 契约与实现文档漂移（D1） | 契约 v3 同步 + §4 校正 | 后续实现不再误读输入面 | 无 | 高 | ✅ |
| O3 | e2e 断言过宽（曾把 404 当「数据状态」容错） | E7 拆为 E7a 显式断言 404 + E7b1/b2 对照 | 契约失败语义真正被测试覆盖 | 无 | 中 | ✅ `c747a79` |

## 8. 风险与遗留问题

| 编号 | 问题 | 说明 | 风险 |
|---|---|---|---|
| R15-1 | 插件三笔提交未推远端 | `e4ba419`、`582de10`、`3c8ff4e`（本地 main 领先）；他人无法复现激活链路 | 中（协作） |
| R15-2 | 36 条环境类 skipped 仍在 | 23 symlink 特权 + 6 macOS + 2 fcntl + 2 Unix；本机令牌无法启用（R14-5 已确认） | 低（非代码） |
| R15-3 | `learning/candidates.json` 未接入 analyze-voice | 契约 §4 已标注「当前实现未读取」；是否实现属**产品决策** | 低（待确认） |
| R15-4 | 8,192 阈值硬编码 | 短内容仍走 argv；极端受限环境（更小 ARG_MAX）阈值是否需可配置待定 | 低 |
| R15-5 | `score-chapter` 未支持 stdin | chapter_file 为路径（短），无命令行长度风险；如未来要评「贴入的整章文本」需另加通道 | 低 |
| R15-6 | 并发压测未做 | 本轮为契约/边界重点；`Semaphore(4)` 仅 R12 定性确认，无量化数据 | 低 |
| R15-7 | 前端 `HumanwareScoreCard` 仍无调用方 | score/check 端点已由脚本/第三方使用，UI 未接线 | 低（范围外） |
| R15-8 | `setup_plugins.py`「假安装」 | 前轮遗留，未动 | 低（待决策） |

## 9. 下一轮迭代计划（Round 16）

| 优先级 | 任务 | 预估工作量 | 验收标准 |
|---|---|---|---|
| **P0** | 推送插件仓库三笔提交（`e4ba419`/`582de10`/`3c8ff4e`）到远端 | 0.1h | `git log origin/main..main` 为空；他人可 `POST /update` 复现 v3 |
| **P0** | 契约回归纳入常规套件：把 `_hw_e2e_r15.py` 逻辑改写为 pytest（`pytest.mark.skipif` 服务未就绪），去掉一次性脚本 | 1h | `pytest tests/test_humanware_e2e.py` 在服务运行时全过；服务未运行时干净 skip |
| **P1** | humanware 并发与性能基线：N 路并发 `score-content`（短/长）测 P50/P95、Semaphore 排队行为；给出 `Semaphore(4)` 是否需调参的量化结论 | 2h | 产出数据表；若 Semaphore 成瓶颈，给出可配置环境变量方案 |
| **P1** | 路径/输入安全扩展 fuzz：workspace_id / chapter_file / character 的异常字符集（`%2e%2e`、Unicode 归一化、超长 200、NUL、`\\` 混合），断言无逃逸且状态码 ∈ {400,404,409} | 1.5h | 用例进套件；任一 2xx 越界即视为缺陷并修 |
| **P2** | 决策 R15-3：`candidates.json` 接入 analyze-voice（若产品需要，扩展 `_reference_files` 并同步契约 v4） | 2h（含确认） | 新输入源有 CLI + API 测试；契约更新 |
| **P2** | 阈值可配置（R15-4）：`DETERMINFLOW_HUMANWARE_STDIN_ARG_THRESHOLD`，默认 8192 | 0.5h | 环境变量生效且有单测 |
| **P3** | 前端接线 `HumanwareScoreCard`：在角色声音页/工作台调用 score-content（含超长内容真实用例，验证 stdin 通道对用户可见） | 2h | 组件测试 + 浏览器人工验收步骤；lint/test/build 全绿 |
| **P3** | 环境类 skipped 收敛：管理员会话或 WSL 复跑 23 symlink / 6 macOS 用例，回填结论 | 1h | 明确「通过 / 真缺陷」清单 |
| **P3** | `setup_plugins.py` 决策（R15-8）：改为真正写 PluginStore lock，或移除并更新文档 | 1h | 二选一落地，`/api/plugins` 状态与文档一致 |

## 10. 命令记录（本轮）

```
# 基线核实
git status / git log（两仓库干净，xs2 c7d0e39、插件 e4ba419）；8021 /api/system/status 200

# 阶段二：覆盖缺口分析（逐行审查 humanware_routes.py 437 行 + CLI 627 行 + 两侧既有测试）
# 平台边界实测（逐长度探测 argv 上限）
.venv python -c "...subprocess.run([... 'x'*size] ...)"   # 32000 OK / 33000 OSError WinError 206

# 红灯（固化缺陷）
pytest tests/test_humanware_routes.py::HumanwareContractHardeningTests -v
# → 3 failed：check-dialogue 500≠409；score-content/check-dialogue 超长 500 WinError 206
#   （首轮两个超长用例长度算错为 28K/25K，误判 PASS；改为 42,000/50,000 后正确复现）

# 阶段三：修复 + 绿灯
pytest tests/test_humanware_routes.py        → 15 passed
<venv> pytest tests/test_humanware_helper.py → 20 passed（1 failed 为测试类归位问题，非产品缺陷）
#   修正：test_banned_word_fails 误并入 StdinConventionSubprocessTests（其 _voice 无禁用词）→ 移回 CheckDialogueTests
pytest tests/test_humanware_helper.py        → 23 passed（含 O1 等价性对照）

# 阶段四：全量回归（先停服务）
Stop-Process <8021 pid 59840> → PORT 8021 FREE
.venv python -m pytest -q                   → 1529 passed / 36 skipped / 118.07s（exit 0）
cd web && npm.cmd run lint / test / build   → 0 problems / 全过 / ✓ built in 6.23s

# 提交与激活
插件 git commit 582de10（修复）/ 3c8ff4e（O1）；xs2 git commit c3bbdad / c747a79
run.py（后台）→ POST /api/plugins/xs2-novel-flywheel/update
#   → resolved_commit e4ba419 → 3c8ff4e，content_sha256 变化，restart_required=true
taskkill /T /F 清理进程树 → PORT 8021 FREE → NO ORPHANS → run.py（后台）
/api/plugins：resolved=3c8ff4e runtime=running restart_required=False
runtime CLI 内容核实：含 _arg_or_stdin=True、import bisect=True
.venv python scripts/_hw_e2e_r15.py → 9/9 PASS，EXITCODE=0
#   首跑 E7 断言过宽（404 被当数据状态）→ 拆 E7a/E7b1/E7b2 并补 os 导入后全绿

# 文档
契约 → v3（stdin 约定、错误码透传含 check_dialogue、§4 candidates 校正）
新增 docs/HANDOVER_ROUND15.md（本文件）
```
