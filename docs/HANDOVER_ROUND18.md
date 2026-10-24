# DeterminFlow (xs2) 交接报告 — Round 18（Windows 名称守卫下沉 core + 客户端错误 500 归零 + 测试与 locale 解耦 + R17 取证假象更正）

> 生成时间：2026-10-24
> 项目路径：`F:/DeterminFlow x2/xs2`（主仓库）；`F:/DeterminFlow x2/DeterminFlow-Plugins`（插件仓库，本轮**无代码改动**）
> 分支：main（两仓库各自）
> 上一轮：[HANDOVER_ROUND17.md](./HANDOVER_ROUND17.md)
> 接口契约：[humanware-helper-contract.md](./humanware-helper-contract.md)（本轮升 **v3.3**）
> 文档编码：UTF-8

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| **R17-3 完成**：Windows 名称守卫从 web 面**下沉到 core**（新 `src/core/win_names.py` 为单一规则源，`src/web/path_guard.py` 退为兼容门面），`WorkspaceManager` 从此拒绝设备名 id 与幻影 override | §4 B8、§5；`tests/test_core_workspace_name_guard.py` 20 条 |
| **新发现并修复 4 个真实缺陷 B6–B9**，均先红灯固化再修。B6/B7 是**错误码语义**缺陷（500 与谎报 200），B9 是**测试健壮性**缺陷（与本机 locale 耦合） | §3 红灯证据、§4 |
| B6 实测：`workflow_id="中文"` 在 novel/workflow 面 → **HTTP 500**（core 裸 `ValueError` 逃逸），现统一 **400** 且带拒因 | §3.4 探针、`src/web/error_handlers.py` |
| B7 实测：`workspace=…/books/NUL` 在只读面 → **200 + `files:[]`**（把一个写不了、删不掉的幻影目录报告成「存在且为空的工作区」），现 **400** | §3.4 探针、`_ensure_resolvable_root` |
| **R17 §3.4 的「实时取证」有 3 行是客户端假象**：PowerShell/.NET `System.Uri` 会剥掉 URL 路径段的尾随点，故 `Invoke-WebRequest` 发不出 `welcome.`。同一 URL 用 `urllib` 直连为 **400**——服务端当时**已正确**。R18 更正并固化为平台注意事项 11 | §4 R18-ENV-2 实测 |
| **纠正 R17 的设备名表述**：`CON`/`PRN`/`AUX`/`COM1`/`LPT1`/`CONIN$` 作为**目录**可创建且读写正常，只有 `NUL` 是幻影目录。拒绝结论不变，根因表述以实测为准（注意事项 12） | §3.5 探针矩阵 |
| **R17-4 完成**：marketplace `bundle.py` 改用同一规则源；新增 **99 条**等价性用例（内联旧规则 vs 新谓词逐段对照），证明行为完全一致 | `tests/test_skill_bundle_name_rule_equivalence.py` |
| 全量回归 **0 失败**（两种 IL 各一次）：Low-IL **1623 passed / 98 skipped**；High-IL **1708 passed / 13 skipped**（较 R17 **净增 124 条用例**：passed +122、skipped +2 为 F6/F7） | §6 实跑 |
| 前端无改动：lint 0 problems、**406 个测试全过（8 套件，fail 0）**、build ✓ 6.32s | §6（本轮用完整落盘输出统计，不再用 `-First/-Last` 截断） |
| 性能：守卫开销实测 **0.88 μs/id**（纯 Python、无 IO），对每次请求最多 1 次的路径，可忽略 | §7 O3 |
| 两仓库**仍未推送**（xs2 **29 笔** = R17 收尾时 26 + 本轮代码 `ec52c89` + 文档 `5cffeb5` + 本更正提交；插件 5 笔）；本轮再次未擅自推送 | §8 R18-1 |

## 2. 测试计划（本轮）

- **范围**：执行 R17 §9 计划。核心是 P1「守卫下沉 `WorkspaceManager`」与 P2「marketplace 去重」；
  并对 core 层错误码语义（`_sanitize_id` → HTTP 状态码）与幻影根在全调用链上的表现做边界/异常测试。
  附带两条 P0（协调并发写入者、推送）属协作事项，非代码可验证，见 §8。
- **类型**：功能（守卫不误伤常规 id 与既有 override）、边界（设备名各家族、override 段、anchor 退化）、
  异常（500 归零、谎报 200 归零）、安全（core 层名字绕过）、回归（两种 IL 全套 + 前端 + 服务侧 e2e）、
  **等价性**（marketplace 旧内联规则 vs 新单一源，逐段对照）、性能（守卫微基准）、
  环境（IL/编码/locale 诊断）。
- **环境**：Windows 本机；venv Python 3.14.8（**Low IL**）与 `C:\Windows\py.exe` + venv site-packages
  （**High IL**）两种解释器；服务 `http://127.0.0.1:8021`（pid 78636，本轮**未重启**，
  因此只加载到 v3.2，R18 的服务侧用例诚实 skip）。
- **通过标准**：两种 IL 下 `pytest -q` 均 0 failed；新增用例全绿；marketplace 等价性 99 条全过；
  前端 lint/test/build 全过；既有 override 数据零误伤。
- **运行命令**：
  ```powershell
  cd "F:\DeterminFlow x2\xs2"
  .\.venv\Scripts\python.exe -m pytest tests/test_core_workspace_name_guard.py -v        # 新（20）
  .\.venv\Scripts\python.exe -m pytest tests/test_skill_bundle_name_rule_equivalence.py -v # 新（99）
  .\.venv\Scripts\python.exe -m pytest tests/test_windows_path_guard.py -v                # 10 → 13
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_e2e.py -q -rs                 # 13 过 + 2 诚实 skip
  .\.venv\Scripts\python.exe -m pytest -q                                                 # 全量 Low-IL

  # High-IL 权威基线
  $sp = "$PWD\.venv\Lib\site-packages"
  $env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
  $env:PYTHONIOENCODING = "utf-8"   # R18 B9 后设与不设都应通过（本轮两种都验过）
  C:\Windows\py.exe -m pytest -q
  ```

## 3. 测试用例与执行结果

### 3.1 core 层名称守卫（新文件 `tests/test_core_workspace_name_guard.py`，20 条）

| 编号 | 场景 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| TC-R18-01 | `win_names` 平台钩子注入 posix → 四个判定函数全放行 | 放行 | 一致 | ✅ |
| TC-R18-02 | 平台无关纯谓词（`is_reserved_device_name`/`has_unsafe_trailing_char`）在 posix 仍照常判定 | 照判 | 一致 | ✅ |
| TC-R18-03 | `create_workflow_workspace("NUL")` → 拒绝，且父目录**无该目录项**、其下 mkdir 失败 | 拒绝 | 修复前静默建幻影 | ✅（修后） |
| TC-R18-04 | 7 个设备名家族（`NUL`/`nul`/`CON`/`PRN`/`AUX`/`COM1`/`LPT9`）× {workflow, chat} 两个入口 | 全拒 | 全拒 | ✅ |
| TC-R18-05 | **不误伤**：`welcome`/`xs2-novel-flywheel`/`wf-1`/`b11663a6`/`core`/`console-NUL`/`NULLU`/`COM0`/`nultxt` | 全放行且建目录成功 | 一致 | ✅ |
| TC-R18-06 | 「拒绝的必要性」取证：幻影 `mkdir` 静默成功、`exists()=True`、`is_dir()=False`、写入失败、`rmtree` 删不掉 | 全部成立 | 成立 | ✅（红灯证据） |
| TC-R18-07 | `cleanup_workflow_workspace("NUL")` 不得谎报 True | 拒绝 | 修复前 **True**（谎报已删） | ✅（修后） |
| TC-R18-08 | 清洗后为空（纯中文）抛的是 `UnsafeWorkspaceIdError`，且**仍是 `ValueError` 子类**（兼容既有 `except ValueError`） | 成立 | 成立 | ✅ |
| TC-R18-09 | 设备名 id 亦抛同一类型 | 成立 | 成立 | ✅ |
| TC-R18-10 | 既有清洗规则不变：`wf_1`→`wf_1`、`"  sp  "`→`sp`、`nul.txt`→`nultxt` | 不变 | 不变 | ✅ |
| TC-R18-11 | **B7**：`resolve_workflow_workspace(override=…/books/NUL)` → 拒绝，且不顺手建出 `books` | 拒绝 | 修复前**返回幻影路径** | ✅（修后） |
| TC-R18-12 | 守卫须在 `mkdir` **之前**：走 id 路径不得留下删不掉的残骸 | 无残骸 | 一致 | ✅ |
| TC-R18-13 | `create_main_task_workspace` 的 session/task/workspace_ref 三处入参 | 拒绝 | 拒绝 | ✅ |

> 红灯证据：首跑 15 failed（core 层完全无守卫 + 裸 `ValueError`）。
> 其中 TC-R18-03 首版断言写错被我自纠：Windows 上**任何**以 `NUL` 结尾的路径 `exists()` 恒真，
> 不能用它证明「没建出来」；正确判据是父目录无该目录项 + `is_dir()=False`。

### 3.2 web 端到端（`tests/test_windows_path_guard.py` 10 → **13** 条）

| 编号 | 场景 | 预期 | 实际（修复前） | 状态 |
|---|---|---|---|---|
| TC-R18-14 | `PUT /api/novel-console/text` 与 `GET /api/workflows/workspace-files`，`workflow_id="中文书"` | **400** 且带 `detail` | **500 Internal Server Error** | ✅（修后，B6） |
| TC-R18-15 | `GET /api/workflows/workspace-files?workspace=…/books/NUL` | **400** | **200 `{"files":[]}`**（谎报空工作区） | ✅（修后，B7） |
| TC-R18-16 | 对照：真实 `WorkspaceManager` + 常规 id 与常规 override 的读写 | 200 且按原名读回 | 一致 | ✅ |

> 与 R17 的 10 条区别：R17 用 `SimpleNamespace` 替换 `_ws_manager`，**不经过** core；
> 本轮三条用**真实 WorkspaceManager** + `create_app` 的同一错误处理器，验证收敛点在真实调用链上生效。

### 3.3 marketplace 规则等价性（新文件，**99** 条）

| 编号 | 场景 | 结果 |
|---|---|---|
| TC-R18-17 | **47** 个路径段（设备名/大小写/带扩展名/尾随点/尾随空格/`$` 家族/设备名前缀/非法字符）逐一对照**内联旧规则 vs 新单一源**的拒/放判定 | **47 passed**（判定完全一致） |
| TC-R18-18 | 同 47 段落到 `validate_paths` 整包层面，验收/拒行为与替换前一致 | **47 passed** |
| TC-R18-19 | 分隔符面（`a/b/NUL.md`、`NUL/a.md`、`a/../b.md`、`./a.md`、`a//b.md`）先拆段再逐段拒 | **5 passed** |
| TC-R18-20 | 合计 = 2 × 47 + 5 | **99 passed**（`--collect-only` 实测 99，与算式吻合） |

> 关键取舍（见 §4 O1）：marketplace 用 `win_names` 中**平台无关**的两个纯谓词，
> 而不是按 `os.name` 门控的 `unsafe_windows_component`——Skill 包必须跨平台可移植，
> POSIX 上也应拒 `NUL.md`。旧实现同样是跨平台正则，故行为一致。
> 差异说明：新集合含 `CONIN$`/`CONOUT$`/`CLOCK$`，但它们带 `$`，早被 `_COMPONENT` 字符集拒绝，
> 故等价性成立（对照表已覆盖）。

### 3.4 实时取证（脚本 `scripts/_r18_probe*.py`，用后即删）

**core 层（无 HTTP，直证）**

| 场景 | 修复前实测 | 含义 |
|---|---|---|
| `create_workflow_workspace("NUL")` | 返回 `…/ws/NUL`；`exists()=True`、`is_dir()=False`；其下写 → `FileNotFoundError` | 幻影目录，污染 `data/workspaces/` |
| `cleanup_workflow_workspace("NUL")` | **True** | **谎报已删除**（`rmtree` 实际删不掉） |
| `resolve_workflow_workspace(override=…/books/NUL)` | 返回该幻影路径；其下 `mkdir` → `WinError 3` | 只读端点据此谎报 200 |
| `_sanitize_id("welcome.")` / `("welcome..")` | 均 → `welcome` | core 内别名被清洗吃掉（**返回名与落盘名一致**，非读写错位） |
| `_sanitize_id("中文")` / `("...")` | **裸 `ValueError`** | web 面不捕获 → 500 |

**web 面（真实 WorkspaceManager + TestClient，进程内）**

| 场景 | 修复前 | 修复后 |
|---|---|---|
| `PUT /novel-console/text` `workflow_id="中文"` | **500** | 400 |
| `GET /workflows/workspace-files` `workflow_id="中文"` | **500** | 400 |
| `GET /workflows/workspace-files` `workspace=…/books/NUL` | **200** `{"files":[]}` | 400 |
| `GET /novel-console/progress` `workspace=…/books/NUL` | **200** 完整进度结构 | 由 core 守卫一并拒绝 |

**8021 真实服务（只读探测，未写入任何数据）**

| 场景 | 结果 | 判定 |
|---|---|---|
| `GET /api/workflows/workspace-files?workflow_id=中文书` | **500** | B6 在线上真实存在（进程内已复现并修复） |
| `GET /api/workflows/workspace-files?workspace=…/books/NUL` | **200** `{"workspace":"…NUL","files":[]}` | B7 在线上真实存在 |
| `GET /api/humanware/status/welcome.`（`urllib` 直连） | **400** | v3.2 守卫**确实已上线**（见 §4 R18-ENV-2） |
| `GET /api/humanware/status/welcome.`（`Invoke-WebRequest`） | 200 | **客户端假象**：.NET `System.Uri` 把 URL 剥成 `welcome` |
| `PUT /novel-console/text path=references/NUL` | **403** 且无落盘文件 | v3.2 novel 面守卫在线 |

> 该取证仅对 8021 发只读请求 + 一次被拒绝（403、无副作用）的 PUT；`data/workspaces/` 与
> `data/workflows/` 均为 gitignore，工作树无残留。探针目录 `_r18probe*` 已全部删除。

### 3.5 环境/语义诊断矩阵

| 实验 | 结果 |
|---|---|
| 已存在真实目录 `<t>\CON`，读写 `CON\data.md` | **正常**（`is_dir()=True`、`iterdir()` 列出、内容可读回） |
| `<t>\PRN`/`AUX`/`COM1`/`LPT1`/`CONIN$` 同上 | **正常**（与 CON 一致） |
| `<t>\NUL` | `mkdir` 静默成功、`exists()=True`、`is_dir()=False`、写入 `FileNotFoundError`、`rmtree(ignore_errors=True)` 后**仍存在** |
| 客户端差异：同一 URL `welcome.` 经 `Invoke-WebRequest` vs `urllib` | 200 vs **400**；`[System.Uri].AbsolutePath` 显示尾随点被剥掉 |
| `urllib` 对 `welcome` / `welcome.` / `welcome...` / `NUL.` / `alpha.md` | 200 / 400 / 400 / 400 / 404（与进程内 HEAD 完全一致） |
| `data/workflows/*.json` 42 个真实 workflow id 过新守卫 | **0 拒绝**（全 ASCII；`.extension`→`extension` 亦通过）→ 零误伤 |
| `data/workspaces/**` 既有目录名 | 均为安全名（`books`/`welcome`/`demo-voice`/`wf-*`/`b11663a6`/`reference-jobs`） |
| 测试 `override` 传参全仓扫描 | 无持久化的 workspace-ish 脏值；既有 override 均为真实目录 |
| B9 复现条件（High-IL + `PYTHONIOENCODING=utf-8`） | 修复前 2 failed；修复后 **四种组合各 39 passed**（High/Low × 设 utf-8/不设/设 gbk） |
| 守卫开销 | `_sanitize_id`（含守卫）0.88 μs/id；`unsafe_windows_component` 单独 0.4 μs/id |

## 4. Bug 报告与根因分析

### B6 — core 的客户端输入错误逃逸为 **HTTP 500**
- **现象**：`PUT /api/novel-console/text` 与 `GET /api/workflows/workspace-files` 对
  `workflow_id="中文"`（清洗后为空）返回 **500 Internal Server Error**；8021 线上同样 500。
- **根因**：`WorkspaceManager._sanitize_id` 抛**裸 `ValueError`**，novel 面 26 处与
  workflow 面 3 处 `resolve_workflow_workspace` 调用点（实测 grep 计数）都不捕获它，异常直达 Starlette 兜底。R15 曾在 humanware 面把
  subprocess 的 `ValueError` 映射为 400，但那是**另一处**（CLI argv 校验），core 这条路径漏了。
  后果：作者填了中文名只会看到"服务器错误"，不知道是自己名字不合法，且反复重试。
- **修复**：
  1. `_sanitize_id` 改抛 `UnsafeWorkspaceIdError`（**`ValueError` 子类**，既有
     `except ValueError` 一律兼容，接口不破）；
  2. 新增 `src/web/error_handlers.py::install_workspace_error_handlers`，在 `create_app` 注册
     `UnsafeWorkspaceIdError` → **400 + 拒因**。单测与线上用同一注册函数，保证被测路径一致。
- **取舍**：另一种做法是在 29 个端点各加 `try/except`。否决理由：改动面 29 处、极易漏（本轮就
  有 3 处宽 `except Exception` 会把它静默吞成 `continue`/`pass`），而集中式异常处理器一处覆盖
  全部现在与未来的调用点，符合"最小修复 + 防回归"。风险极低：仅新增一条异常→状态码映射，
  不改任何成功路径。

### B7 — 幻影目录作为 workspace override：只读端点**谎报 200 + 空工作区**
- **现象**：`GET /api/workflows/workspace-files?workspace=data/workspaces/books/NUL` →
  **200**，body 为 `{"workspace":"…\\books\\NUL","files":[]}`；`GET /novel-console/progress`
  同样返回完整进度结构（全 `not_started`）。前端会把它显示成一个「存在、可读、只是还没写」的作品。
- **根因**：`resolve_workflow_workspace` 把 `mkdir(exist_ok=True)` 过的路径原样返回；
  Windows 下 `NUL` 段"mkdir 成功、exists 恒真"，于是**存在性校验全部通过**，而任何真实
  IO 必然失败。R17 只在 `safe_target`（写路径 + 部分读路径）拦了，**只读的
  workspace-files / progress 面完全绕过** `safe_target`。
- **修复**：下沉到 core——`resolve_workflow_workspace_path` 在算出 override 路径后、
  返回**之前**调用新私有函数 `_ensure_resolvable_root(resolved, anchor)` → 抛
  `UnsafeWorkspaceIdError`（经 B6 的映射即 400）。29 个 web 调用点**零改动**全部受益。
- **设计要点**：只检查 `anchor` **以下**由调用方提供的段（`resolved.relative_to(anchor)`），
  不复查仓库自身的祖先目录——否则路径里含 `NUL` 的部署会被整体打死。
  anchor 退化（`override == BASE_DIR`，`relative_to` 得 `.`、`parts` 为空）时自然放行，已实测。
- **风险**：低。真实数据扫描（§3.5）显示 42 个 workflow id 与全部既有 override 均不受影响。

### B8 — `WorkspaceManager` 无设备名守卫：造出删不掉的幻影目录 + cleanup 谎报（R17-3 收尾）
- **现象**：`create_workflow_workspace("NUL")` 静默"成功"；其下写入 `FileNotFoundError`；
  `cleanup_workflow_workspace("NUL")` 返回 **True** 但目录仍在（`shutil.rmtree` 删不掉）。
  `create_workspace`/`create_main_task_workspace`/`resolve_workflow_workspace` 同型。
- **根因**：`_sanitize_id` 只做字符白名单（`[^a-zA-Z0-9_-]` 剥离），**`NUL` 清洗后原样保留**；
  随后一律 `mkdir(parents=True, exist_ok=True)`。POSIX 上 `NUL` 是合法名，故该守卫跨平台"看着没问题"。
- **修复**：`_sanitize_id` 清洗后追加 `unsafe_windows_component` 判定（非 `nt` 恒放行），
  命中即抛 `UnsafeWorkspaceIdError`；`cleanup_*`/`workflow_workspace_exists`/`get_workspace_size`
  等全部复用同一入口，一处覆盖。
- **取舍（重要）**：**不在 core 拒尾随点**。理由是实测驱动的：`_sanitize_id` 本身已剥掉点/空格
  （`welcome.`→`welcome`），返回名与落盘名**一致**，不构成读写错位；若在 core 拒反而会
  **新创建**的工作区比既有行为更严格，而真正的危险（别名命中）已由 R17 的 web 面在**原始入参**上
  解决。此判断写在代码注释里，避免后来者重复推理。
- **对 R17 表述的更正**：`CON`/`PRN`/`AUX`/`COM1`/`LPT1`/`CONIN$` 作为**目录**可正常读写
  （§3.5 实测），并非"写入静默丢弃"；只有 `NUL` 是幻影。拒绝它们的理由改为
  **跨工具一致性**（资源管理器拒建、部分 Win32 API 仍按设备解析、备份/压缩工具易漏），
  且与 R17 已上线的 web 面保持一致——不改变已上线行为。

### B9 — 测试与本机 locale 耦合：`PYTHONIOENCODING` 一变即失败（High-IL 权威基线）
- **现象**：High-IL 全量首跑 **2 failed**：
  `test_workflow_executor_protocol.py::test_executor_count_reads_prefixed_environment_and_rejects_invalid_value`
  与 `test_workflow_recovery_timeout.py::test_executor_recovery_timeout_config_is_strict_and_prefixed`。
  报错不是断言不符，而是 `TypeError: argument of type 'NoneType' is not a container or iterable`。
- **根因**（`UnicodeDecodeError` traceback 直证）：两个用例
  `subprocess.run(..., env=os.environ.copy(), text=True, capture_output=True)` 断言**中文** stderr。
  `text=True` 时父进程按**本机 locale（cp936）**解码，而 `env` 复制了外部环境——一旦会话里设了
  `PYTHONIOENCODING=utf-8`，子进程就按 UTF-8 输出中文，父进程 cp936 解码失败，读取线程崩溃，
  `stderr` 置为 **None** → `in None` 抛 `TypeError`。R17 的 High-IL 命令没有设该变量，所以从未暴露。
  影响：权威基线命令对调用环境**敏感**，任何人带自己的 shell 配置跑就会红，属真实可维护性缺陷。
  与本项目平台注意事项 5（`read_text()` 不传 encoding 会用 cp936）同族。
- **修复**：`subprocess.run` 改为**显式** `encoding="utf-8", errors="replace"`，并在子进程 env 内
  写定 `PYTHONIOENCODING="utf-8"`（两端约定同一编码），再加 `assert invalid.stderr is not None`
  把"解码失败"从 `TypeError` 变成可读断言失败。共 4 处调用点（含同文件内另外 2 处同模式）。
- **验证**：修复后四种组合（High-IL/Low-IL × 不设 / 设 `utf-8` / 设 `gbk`）各 **39 passed**。
- **取舍**：也可以只把断言改成 `assert invalid.stderr and "…" in invalid.stderr`——但那会
  **掩盖**解码失败（None 也"通过"）。显式约定编码才是根治。全仓扫描确认同类模式只在这 2 个文件。

### R18-ENV-2 — **R17 取证假象（更正，非代码缺陷）**
- **发现过程**：本轮对 8021 复验时 `Invoke-WebRequest …/status/welcome.` 返回 **200**，
  一度判定为"v3.2 守卫在线上失效"（严重回归）。逐条排查：同一 URL 用 Python `urllib`
  直连返回 **400**；`[System.Uri]"…welcome.".AbsolutePath` 显示为 `…/welcome`。
- **结论**：**.NET `System.Uri` 会剥掉 URL 路径段的尾随点**，请求根本没带点。服务端行为正确，
  R17 §3.4 表中 3 行（`status/welcome.`、`status/welcome..`、`status/welcome...` → 200，
  以及 `PUT …/outline.`）**记录的是客户端假象**，不是漏洞；R17 据此所做的修复与 e2e（用 `urllib`）
  都是对的，其结论未受影响。
- **处置**：写入平台注意事项 11，明确"名字规范化类缺陷必须用不经 .NET URI 解析的客户端验证"，
  并把该判据固化在 `tests/test_humanware_e2e.py`（`urllib`）上。
- **附带澄清**：`NUL.` / `COM1.` 这类**带点设备名**经 .NET 会被剥成 `NUL`/`COM1`，仍被拒，
  所以 R17 那几行「→ 400」也是巧合正确（测的其实是去掉点的名字）。

### P0-1（R17 遗留，仍未完成）— 两仓库推送
- xs2 **28 笔**（R17 收尾时 26 + 本轮 `ec52c89` 代码 + `5cffeb5` 文档 + 本更正提交）/ 插件 5 笔未推送；`credential.helper=manager` 需弹窗，
  无人值守被拦。需用户手动：
  `cd "F:\DeterminFlow x2\DeterminFlow-Plugins" && git push origin main`，随后 xs2 同法。
- 验收：两仓库 `git log origin/main..main` 为空。

### P0-2（R17 遗留）— 并发写入者协调（本轮状态）
- 本轮观察：`git status` 干净，HEAD 为 `0e4f9bd`（R17 收尾，09:32 amend）；
  `git config user.name` = `yuyang0702` 与历史提交作者**同一身份**，`ff0a8cf`（作者 `p`、
  message 仅 `c`）是**唯一**异质主体。本轮全程**只用显式路径 `git add`，未用 `-A`**，
  未覆盖他人文件；8021（pid 78636，09:07 启动，本工作树 `run.py`）归属另一会话，本轮未动。
- 遗留：仍需单一写入者约定或独立 worktree/分支（见 §9 P0）。

## 5. 修复代码要点（补丁位置）

| 文件 | 位置 | 变更 |
|---|---|---|
| **`src/core/win_names.py`**（新） | 全文件 | Windows 名称约束**单一规则源**：`WINDOWS_RESERVED_NAMES`、`is_reserved_device_name` / `has_unsafe_trailing_char`（**平台无关**纯谓词，供 marketplace 复用）、`unsafe_windows_component`/`path`/`root`（按 `_on_windows()` 门控）、`UnsafeWorkspaceIdError`、`ensure_safe_component`。文档写明 R18 实测的目录/文件语义差异 |
| `src/core/workspace_manager.py` | `_sanitize_id` | 清洗后追加设备名判定；空结果与设备名统一抛 `UnsafeWorkspaceIdError`（`ValueError` 子类，兼容既有捕获）。注释解释**为何不在 core 拒尾随点** |
| `src/core/workspace_manager.py` | 新 `_ensure_resolvable_root` | B7：override 解析后、返回前只检 `anchor` 以下段 |
| `src/core/workspace_manager.py` | `resolve_workflow_workspace_path` | 两个成功返回分支（绝对/相对 override）各接一处守卫 |
| **`src/web/error_handlers.py`**（新） | 全文件 | `install_workspace_error_handlers(app)`：`UnsafeWorkspaceIdError` → **HTTP 400 + 拒因**；线上与单测共用 |
| `src/web_server.py` | `create_app` | import + 在 `include_router` 之后调用 `install_workspace_error_handlers`（一处注册，29 个端点全覆盖） |
| `src/web/path_guard.py` | 全文件 | 由「重复实现」退为 `win_names` 的**再导出门面**（`__all__` 明确），`humanware_routes`/`novel_routes` 的 import 与错误文案**逐字不变** |
| `src/skill_marketplace/bundle.py` | `validate_paths` | 删本地 `_RESERVED`，改用 `has_unsafe_trailing_char` + `is_reserved_device_name`（R17-4 去重） |
| `tests/test_core_workspace_name_guard.py` | 新文件 | 20 条（§3.1），含「拒绝的必要性」取证与平台门控注入 |
| `tests/test_skill_bundle_name_rule_equivalence.py` | 新文件 | 99 条（§3.3）：内联旧规则 vs 新单一源逐段对照 + 整包层面 + 分隔符面 |
| `tests/test_windows_path_guard.py` | 文件尾 | +3 条真实 `WorkspaceManager` 端到端（§3.2），含 B6/B7 修复前后状态码对照注释 |
| `tests/test_humanware_e2e.py` | F6/F7 | +2 条服务侧验收（能力探测，服务未加载 R18 代码时**诚实 skip** 并写明原因）；补 `urllib.parse` import |
| `tests/test_workflow_executor_protocol.py` · `tests/test_workflow_recovery_timeout.py` | 4 处 `subprocess.run` | B9：显式 `encoding="utf-8"` + 子进程 `PYTHONIOENCODING` + `stderr is not None` 断言 |
| `docs/humanware-helper-contract.md` | **v3.3** | §2.2 增补 core 层同名守卫与 `UnsafeWorkspaceIdError`→400 语义 |
| `docs/PROJECT_INFO.md` | 测试环境 + 注意事项 11、12 | R18 双基线数字；.NET URI 剥尾随点；设备名目录 vs 幻影文件语义差异 |

## 6. 回归测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| core 名称守卫（新） | `pytest tests/test_core_workspace_name_guard.py` | **20 passed** |
| marketplace 等价性（新） | `pytest tests/test_skill_bundle_name_rule_equivalence.py` | **99 passed** |
| Windows 名称守卫（web） | `pytest tests/test_windows_path_guard.py` | **13 passed**（10 → 13） |
| 三文件合并 | 上三项 | **132 passed / 0 failed** |
| humanware 路由单测 | `pytest tests/test_humanware_routes.py` | **24 passed**（无退化） |
| humanware e2e（服务未重启） | `pytest tests/test_humanware_e2e.py -rs` | **13 passed / 2 skipped**（F6/F7 诚实 skip，原因写明需重启） |
| novel + workflow + workspace 相关 12 文件 | 合并跑 | **216 passed / 1 skipped** |
| B9 目标 2 文件（High-IL，设 `utf-8`） | `py.exe -m pytest …` | **39 passed**（修复前 2 failed） |
| 同上（High-IL 不设 / Low-IL 不设 / Low-IL 设 `gbk`） | 三种组合 | 各 **39 passed** |
| **全量 Low-IL（终态）** | `.\.venv\Scripts\python.exe -m pytest -q` | **1623 passed / 98 skipped / 0 failed**（111.91s；R17 为 1501/96 → passed **+122**、skip **+2**，总数 +124） |
| **全量 High-IL（权威基线，终态）** | `C:\Windows\py.exe -m pytest -q` | **1708 passed / 13 skipped / 0 failed**（133.03s；R17 为 1586/11 → passed **+122**、skip **+2**；13 = 11 平台 + F6/F7） |
| 前端（无改动） | `npm.cmd run lint` / `test` / `build` | lint 0 problems；**406 个测试全过（8 套件，fail 0，not-ok 0）**；✓ built in 6.32s |
| 导入/编译健康 | `import src.web_server, …bundle, …path_guard, …win_names` + `py_compile` 6 文件 | 全部通过 |
| 工作树 | `git status` | 仅本轮预期改动；探针脚本与 `_r18probe*` 残骸已清理，无临时文件残留 |

> **计数核对**：净增 **124** = 20（core 守卫）+ 99（marketplace 等价性 = 2×47 段对照 + 5 分隔符）+ 3（web 端到端）+ 2（e2e F6/F7）。
> 总用例数：R17 = 1501+96 = 1597 → R18 = 1623+98 = 1721（High-IL 同为 1708+13 = 1721），差值 124，逐项可解释。
> 六个文件的 `--collect-only` 实测：core 20 / 等价性 99 / path_guard 13 / e2e 15 / humanware 路由 24 / workspace_manager 8，全部与本文表格一致。
> Low-IL skip 98 = R17 的 96 + 2（新 F6/F7 服务未重启）；High-IL 13 = 11 + 2。两种 IL 的差值均可解释。
> 前端统计本轮改为**完整落盘后汇总**（`# tests` 8 项求和 = 406、`# fail` 求和 = 0），
> 避免重演 R17-5 的 `Select-Object -First/-Last` 截断误记。

## 7. 优化清单（本轮）

| 编号 | 问题 | 方案 | 预期收益 | 风险 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| O1 | 同一 Windows 名称规则存在**第三份**实现（`bundle._RESERVED`），且 core 层根本没有规则（R17-3/R17-4） | 新建 `src/core/win_names.py` 单一源；web `path_guard` 退为再导出门面；`bundle` 与 `WorkspaceManager` 共用 | 3 份实现 → 1 份；新面接入成本 1 行；规则漂移从结构上不可能 | 无（99 条等价性用例 + 两面既有测试全过） | 高 | ✅ |
| O2 | 客户端输入错误在 web 面表现为 500，且**无处收敛**（29 个端点各写 try/except 不现实） | `UnsafeWorkspaceIdError`（ValueError 子类）+ `create_app` 集中注册异常→状态码映射 | 500 归零；错误信息可指导用户；未来新端点自动继承 | 低（仅新增映射，不改成功路径；兼容既有 `except ValueError`） | 高 | ✅ |
| O3 | 守卫是否值得每次调用都跑，无数据支撑 | 微基准（§3.5） | 结论：0.88 μs/id，每请求 ≤1 次，相对 HTTP 往返可忽略 | — | 中 | ✅ |
| O4 | 权威基线（High-IL）对调用环境敏感，他人带自己 shell 配置跑就红 | 测试内显式约定两端 UTF-8（B9），文档同步 | 基线可复现；去掉一个隐性前置条件 | 无（四组合实测全绿） | 高 | ✅ |
| O5 | 服务侧验收无法区分「修复未生效」与「服务未加载新代码」 | F6/F7 沿用能力探测 + 显式 skip（写出原因与所需动作） | 不把未部署的修复当成已验证 | 无 | 中 | ✅ |
| O6 | 测试自身断言可能写错（本轮 TC-R18-03 就踩了 `exists()` 恒真） | 把「判据为何有效」写进注释，并用 `iterdir()`/`is_dir()` 双证 | 后续维护者不会照着错误判据再写一遍 | — | 中 | ✅ |

## 8. 风险与遗留问题

| 编号 | 问题 | 说明 | 风险 |
|---|---|---|---|
| **R18-1** | 两仓库未推送（xs2 **29 笔**：R17 收尾 26 + 本轮 3 笔含本文档更正；插件 5 笔） | 无缓存凭据，需用户手动 `git push`（GCM 弹窗）；以 `git log origin/main..main` 实测为准 | 中（协作/备份） |
| **R18-2** | 8021 仍运行 **v3.2** 代码（pid 78636，另一会话持有） | B6/B7 的**线上**表现未变（500 / 谎报 200），进程内与单测已修复并验证；需重启才会生效。e2e F6/F7 当前诚实 skip | **中**（修复未上线；本轮未擅自重启他人进程） |
| R18-3 | `web/dist/` 由本轮 `npm run build` 重新生成（前端代码未改） | 若服务以静态目录对外，产物时间戳变化但内容等价 | 低 |
| R18-4 | marketplace 去重后新增集合含 `CONIN$`/`CONOUT$`/`CLOCK$` | 实测被 `_COMPONENT` 字符集先拒，**行为等价**（99 条对照）；若将来放宽 `_COMPONENT` 允许 `$`，新集合会多拒这三族——方向安全（更严），但需知悉 | 低 |
| R18-5 | 更正：R17 §3.4 三行「welcome.→200」为客户端假象 | R17 的修复与其 `urllib` e2e 结论**不受影响**；仅取证表需按注意事项 11 重读 | 低（记录质量） |
| R18-6 | 并发写入者（P0-2） | 本轮只用显式路径 `git add`；8021 进程归属另一会话未动；`ff0a8cf` 作者 `p` 仍是唯一异质主体 | 中（协作/历史完整性） |
| R18-7 | 本机 F: 盘启动的 python 为 Low IL | R17 已定位并给出 High-IL 路径；本轮沿用，未再排查降格来源 | 低（环境） |
| R18-8 | `learning/candidates.json` 未接入 analyze-voice（R15-3/R16-3/R17-7 延续） | 产品决策项，本轮未动 | 低 |
| R18-9 | 前端 `HumanwareScoreCard` 无调用方（R15-7/R16-5/R17-8 延续） | UI 未接线 | 低 |
| R18-10 | `setup_plugins.py`「假安装」（R15-8/R16-6/R17-9 延续） | 待决策 | 低 |
| R18-11 | core 层守卫**只覆盖设备名 + 空清洗**，尾随点仍在 web 面拒 | 有意取舍（§4 B8）：`_sanitize_id` 已剥点，返回名与落盘名一致，core 再拒会**严于**既有创建行为。若将来 core 出现「按原始 id 字符串定位既有工作区」的需求，需回到 core 补非规范名拒绝 | 低（设计债，已注释） |

## 9. 下一轮迭代计划（Round 19）

| 优先级 | 任务 | 预估工作量 | 验收标准 |
|---|---|---|---|
| **P0** | 重启 8021 使 v3.3（core 守卫 + 400 映射）上线；随后 `pytest tests/test_humanware_e2e.py` 应 **15 passed / 0 skipped**（F6/F7 由 skip 转 PASS） | 0.5h（需用户确认，进程属另一会话） | 服务侧 `workflow_id=中文`→400、`workspace=…/NUL`→400；行为指纹记录 |
| **P0** | 手动推送两仓库（xs2 29 笔 / 插件 5 笔，以 `git log origin/main..main` 实测为准） | 0.2h | 两仓库 `git log origin/main..main` 为空 |
| **P0** | 协调单一写入流：与并发会话约定各自 `git add` 显式路径或改用独立 worktree/分支（R17-10 / R18-6） | 0.5h | 无第三主体半提交；交接中 HEAD 与工作树状态可解释 |
| P1 | 名字拼接点全面复查（R17 §9 P2 的剩余部分）：`novel_reference_*`、`export` 下载名、插件 `runtime-resources` 目录名、`attachments`/`mentions` 文件名 | 1.5h | 列出清单 + 每个危险点有测试或明确豁免理由 |
| P1 | 以 High-IL 为准把「权威基线」写入 CI（GitHub Actions windows runner 或文档化 job），Low-IL 仅作快速跑 | 1h | CI 文件或 `.github/workflows` 一次成功记录；文档写明两种模式数字与用途 |
| P2 | 会话/工作区 id 的**非规范名**策略统一（R18-11）：确认 web 面拒绝 + core 清洗剥点的双重语义是否需要收敛为单一入口 | 1h | 决策落地并在 `win_names` 文档写明；新增对照用例 |
| P2 | 决策 R18-8（candidates 接入 analyze-voice） | 2h（含确认） | 二选一落地并同步契约 §4 |
| P3 | R18-9 前端接线 `HumanwareScoreCard`；P3 R18-10 `setup_plugins.py` 决策 | 2h / 1h | 组件测试 + lint/test/build 全绿 / 决策落地 |
| P3 | 若在 Linux/macOS 上验证：POSIX 应完全放行设备名与尾随点（`win_names` 门控的另一侧），本轮仅有 monkeypatch 注入用例，缺真实 POSIX 运行 | 0.5h | 一次非 Windows 全量跑记录（skip 数与平台差异对得上） |

## 10. 命令记录（本轮）

```
# 基线复现
Low-IL：pytest -q → 1501 passed / 96 skipped / 0 failed（110.34s）= R17 终态一致，起点干净

# 取证（scripts/_r18_probe1..5.py，用后即删）
core：create_workflow_workspace('NUL') → exists=True is_dir=False；其下写 FileNotFoundError；cleanup → True（谎报）
core：override=…/books/NUL → 返回幻影路径；其下 mkdir → WinError 3
core：_sanitize_id('welcome.')='welcome'、('nul.txt')='nultxt'、('CONIN$')='CONIN'、('中文')→裸 ValueError
web(进程内)：workflow_id='中文' → PUT/text 500、workspace-files 500
web(进程内)：workspace=…/books/NUL → workspace-files 200 {"files":[]}、progress 200
8021(只读)：同上 500 / 200 —— 线上真实存在
设备名目录语义：CON/PRN/COM1/LPT1/AUX/CONIN$ 作目录可正常读写；仅 NUL 幻影（mkdir 成功、写失败、rmtree 删不掉）
URI 假象：[System.Uri]…welcome. → AbsolutePath …/welcome；IRW 200 vs urllib 400（含 %2E 亦 400）
零误伤核查：data/workflows 42 个 id 过新守卫 → 0 拒绝；data/workspaces 既有目录名全安全；全仓 override 无脏值

# 红灯（修复前首跑）
pytest tests/test_core_workspace_name_guard.py → 15 failed / 4 passed
（TC-R18-03 断言自纠：NUL 结尾路径 exists() 恒真，改用 iterdir()+is_dir() 双证）

# 修复（src/core/win_names.py + _sanitize_id + _ensure_resolvable_root + error_handlers + path_guard 门面 + bundle）
pytest 三文件（core 20 + 等价性 99 + web 13）→ 132 passed
pytest 12 个 novel/workflow/workspace 文件 → 216 passed / 1 skipped
pytest tests/test_humanware_e2e.py -rs → 13 passed / 2 skipped（F6/F7 诚实 skip）

# B9（High-IL 首跑发现 2 failed，根因 cp936 解码子进程 UTF-8 stderr → stderr=None → TypeError）
修复前：High-IL + PYTHONIOENCODING=utf-8 → 2 failed
修复后：High-IL 设 utf-8 / High-IL 不设 / Low-IL 不设 / Low-IL 设 gbk → 各 39 passed

# 全量回归（终态）
Low-IL ：pytest -q → 1623 passed / 98 skipped / 0 failed（111.91s）
High-IL：py.exe -m pytest -q → 1708 passed / 13 skipped / 0 failed（133.03s）
前端   ：lint 0 problems / test 406 pass 0 fail（8 套件，完整落盘统计）/ build ✓ 6.32s
健康度 ：4 模块 import OK；6 文件 py_compile OK；守卫微基准 0.88 μs/id

# 收尾
清理 scripts/_r18_probe*.py 与 _r18probe*/ 残骸；工作树仅剩预期改动
文档：契约 v3.3、PROJECT_INFO（R18 双基线 + 注意事项 11/12）、HANDOVER_ROUND18.md
提交：显式路径 git add（不用 -A），两仓库仍未推送（需用户手动 git push，GCM 弹窗）
```
