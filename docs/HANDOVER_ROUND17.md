# DeterminFlow (xs2) 交接报告 — Round 17（R16-ENV-1 根因推翻并修复 + 路径名安全面统一 + Windows 幻影目录缺陷）

> 生成时间：2026-10-24
> 项目路径：`F:/DeterminFlow x2/xs2`（主仓库）；`F:/DeterminFlow x2/DeterminFlow-Plugins`（插件仓库，本轮无代码改动）
> 分支：main（两仓库各自）
> 上一轮：[HANDOVER_ROUND16.md](./HANDOVER_ROUND16.md)
> 接口契约：[humanware-helper-contract.md](./humanware-helper-contract.md)（本轮升 **v3.2**）
> 文档编码：UTF-8

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| **R16-ENV-1 根因定位并推翻 R16 结论**：不是「机器状态/安全软件/需重启」，而是 **解释器令牌的完整性级别（IL）**。`python.exe` 从 **F: 盘**启动即为 **Low IL**，同一二进制在 C: 上为 **High IL**；msys 已存在的共享对象拒绝 Low-IL 进程附加 | §4 ENV；IL 矩阵 + 命名对象访问实测 |
| **该 60 项阻塞现已可执行**：High-IL 解释器跑同一套件 → **99 passed**（6 个插件文件），全量 **1585 passed / 12 skipped / 0 failed** | §6 两条基线实跑 |
| **顺带纠正 R15/R16 的 symlink 结论**：`SeCreateSymbolicLinkPrivilege` 失败同样源于 Low IL；High-IL 下 11 个 skip 全为 macOS/POSIX 类，**symlink 用例真实通过** | High-IL 全量 skip 清单 |
| **新发现并修复 3 个真实缺陷（B3/B4/B5）**，均先失败测试固化再修；B4/B5 为**静默数据丢失**与**未捕获异常 500** | §3 红灯证据、§4 |
| R16 §9 P1「语义对齐复查」完成：`_get_workspace_root` 无同型复制，但 novel-console 面存在**同型缺陷且更严重**；已抽 `src/web/path_guard.py` 统一两面 | §4 根因分析 |
| humanware 路由单测 22 → **24**；e2e 12 → **13**（新增 F5 服务侧别名验收，服务未加载新代码时诚实 skip）；**新文件 `tests/test_windows_path_guard.py` 10 条** | 三文件 pytest 实跑 |
| 全量回归 **0 失败**（两种 IL 各一次），并在 `tests/conftest.py` 固化 msys 探测钩子，Low-IL 跑不再刷 60 个假失败 | §6 |
| 前端无改动；本轮实测 **406 个前端测试全过（8 个套件）**、lint 0 problems、build ✓ 6.22s（R16 记录「6 pass」是 `Select-Object -Last` 截断造成的**误记**，见 §8 R17-5） | 前端三命令实跑 |
| **两仓库仍未推送**（插件 5 笔 / xs2 现 24 笔），本轮再次未擅自推送 | §4 P0-1 |

## 2. 测试计划（本轮）

- **范围**：执行 R16 交接 §9 计划（P0 ENV 复验 + 推送；P1 阈值 e2e、B1/B2 语义对齐复查），并对 humanware / novel-console 两个文件路径面做 Windows 名称语义边界测试。
- **类型**：功能（守卫不影响正常读写）、边界（设备名各变体、尾随点/空格、幻影目录）、异常（500 归零）、安全（路径名绕过黑名单）、回归（全套 + 前端 + 服务侧 e2e）、环境（IL/命名对象诊断）。
- **环境**：Windows 本机；venv Python 3.14.8（**Low IL**）与 `C:\Windows\py.exe` + venv site-packages（**High IL**）两种解释器分别跑全量；服务 `http://localhost:8021`（**本轮未重启**，理由见 §8 R17-1）。
- **通过标准**：两种 IL 下 `pytest -q` 均 0 failed；新增用例全绿；前端 lint/test/build 全过；High-IL 下原被阻塞的 6 个插件文件恢复执行。
- **运行命令**：
  ```
  cd "F:\DeterminFlow x2\xs2"
  .\.venv\Scripts\python.exe -m pytest tests/test_windows_path_guard.py -v    # 新文件（10）
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_routes.py -v      # 路由单测（24）
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_e2e.py -q -rs     # e2e（12 过 + 1 诚实 skip）
  .\.venv\Scripts\python.exe -m pytest -q                                    # 全量（Low-IL）

  # High-IL：恢复被 R16-ENV-1 阻塞的 git 传输 / symlink 用例
  $sp = "$PWD\.venv\Lib\site-packages"
  $env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
  C:\Windows\py.exe -m pytest -q
  ```

## 3. 测试用例与执行结果

### 3.1 Windows 名称语义（新文件 `tests/test_windows_path_guard.py`，10 条）

| 编号 | 场景 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| TC-R17-01 | 组件名矩阵：16 个应拒（`NUL`/`nul.`/`COM1.log`/`CONIN$`/`alpha.`/`aux.txt.bak`…）+ 11 个应放（`core`/`console-NUL`/`COM0`/`NULLU`…） | 拒/放正确 | 一致 | ✅ |
| TC-R17-02 | 拒因文本区分「保留设备名」/「剥离」 | 区分 | 区分 | ✅ |
| TC-R17-03 | `unsafe_windows_path` 逐段检查（含反斜杠形式） | 命中 | 命中 | ✅ |
| TC-R17-04 | `safe_target` 拒 `references/NUL`、`references/foo.` | 403 | 403 | ✅ |
| TC-R17-05 | **证明拒绝的必要性**：写 `NUL` 不抛异常、`exists()=True`、`is_file()=False`、读回为空、目录列表无此文件 | 静默丢失 | 静默丢失 | ✅（红灯证据） |
| TC-R17-06 | `library_path` 清洗后设备名（`"NUL"`→`"nul"`）→ 400；`"NUL.txt"`→`"nul-txt"` 属安全名 → 放行 | 400 / 放行 | 一致 | ✅ |
| TC-R17-07 | `PUT /novel-console/text` 真实路由：`references/NUL` → 403 且不落任何文件；`references/outline.` → 403；正常名 → 200 且按原名读回 | 一致 | 一致 | ✅ |
| TC-R17-08 | **B5**：`safe_target` 的工作区**根**为幻影目录（`<x>/NUL`，mkdir 静默成功、exists 恒真、非目录）→ 400 | 400 | 400 | ✅ |
| TC-R17-09 | **B5 端到端**：`PUT /text` 的 `workspace` 以 `NUL` 结尾 → 400（修复前 **500** 未捕获 `FileNotFoundError`） | 400 | 400 | ✅ |
| TC-R17-10 | **B5 破坏性面**：`DELETE /projects` 的 `workspace` 以 `NUL` 结尾 → 4xx，不得谎报删除成功 | 4xx | 400 | ✅ |

> 红灯证据：首跑 TC-04/05/07/08/09/10 全部失败（`safe_target` 与 `library_path` 原样接受设备名，
> `PUT /text` 对 `references/NUL` 返回 200 + sha256 而内容未写入；幻影根触发未捕获异常）。

### 3.2 humanware 路由层（22 → 24）

| 编号 | 场景 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| TC-R17-11 | `workspace_id="welcome."/"welcome.."/"welcome..."`（真实工作区 `welcome` 的 Windows 别名） | 400 | 修复前 **200 并命中真实工作区** | ✅（修后） |
| TC-R17-12 | 设备名 + 尾随点组合（`NUL.`/`nul.`/`COM1.`/`CON.txt`/`LPT9.`/`aux.txt.bak`） | 400 | 400 | ✅ |
| TC-R17-13 | 对照：`welcome` → 200、`alpha.md`（名字中间点）→ 404 | 不误伤 | 一致 | ✅ |
| （调整）| R16 的 `test_body_workspace_id_fuzz_all_rejected_400` 原断言 `"tail."` → 404 | — | 现语义为 **400**（别名一律拒绝），断言已随修复更新并在注释中说明理由 | ✅ |

### 3.3 服务侧 e2e（12 → 13）

| 编号 | 场景 | 实际 |
|---|---|---|
| E1–E7b2 / F1–F4 | R15/R16 既有 12 项契约验收 | **12 passed**（0.94s，真实 8021 服务 + 真实 runtime CLI） |
| **F5** | `GET /api/humanware/status/welcome.` 对**运行中的服务**必须 400（B3） | **诚实 skip**：探测到当前 8021 进程仍为 v3.2 之前代码（实测返回 200），用例明确写出「需重启服务后才会执行」，不伪装通过 |

> F5 采用「能力探测 + 不满足即 skip」而非硬断言：因为 8021 由上一会话的进程链持有
> **workflow-executor 独占租约**（本轮实测：另起 8022 在 pool 模式与 inline 模式下均以
> `ExecutorLeaseUnavailable: another Workflow Executor still owns the process lease` 启动失败），
> 未经确认不重启他人正在运行的服务。服务重启后该用例自动生效。

### 3.4 实时取证（对修复前的 8021，脚本 `scripts/_r17_live_check.py`，用后即删）

| 场景 | 实测响应 | 含义 |
|---|---|---|
| `GET /api/humanware/status/welcome.` | **200** `{"voice_file_exists":true,...}` | 不存在的工作区命中真实工作区（B3） |
| `GET /api/humanware/status/welcome...` | **200** 同上 | 任意尾随点数量均别名命中 |
| `POST generate-voice-file {"workspace_id":"welcome."}` | **200** `character_count=2` | 经由别名**写入真实工作区**（越界写） |
| `PUT /novel-console/text path=references/NUL` | **200** `{"success":true,"sha256":"732f…"}` | 声称保存成功并返回哈希，**内容实际被丢弃**（B4） |
| `PUT /novel-console/text path=references/outline.` | **200** path=`references/outline.` | 落盘为 `outline`（名字被剥离，按原名读不到） |
| `GET /api/humanware/status/NUL.`/`COM1.`/`CON.txt` | 400 | R16 黑名单已覆盖带点变体（本轮补齐其余组合） |

> 该取证脚本对 `welcome` 的副作用仅有一次 `generate-voice`（按 `character_profiles.md` 幂等重建
> `character_voice.md`，与 e2e E1 每轮所做的事完全相同）；`data/**` 为 gitignore，工作树无 diff。

### 3.5 环境诊断矩阵（R16-ENV-1）

| 实验 | 结果 |
|---|---|
| pwsh(High) → `sh.exe` | **rc=0 正常** |
| pwsh(High) → `bash.exe` | **rc=0 正常** |
| python(Low) → `sh.exe` / `bash.exe` | `0xC0000022` 崩溃 |
| python(Low) → `cmd.exe`（原生） | rc=0 正常 |
| cmd(High) → `python.exe` | 子 python **仍是 Low** |
| cmd(High) → `C:\Program Files\Python314\python.exe` | **High** |
| `C:\Windows\py.exe` → python | **High**，且 python → `sh.exe` **rc=0** |
| 复制 `python.exe` 到 C:\Temp 改名运行 | **High**（非按文件名降格） |
| 复制 `python.exe` 到 F: 运行 | **Low** |
| `node.exe` / `py.exe` | **High** |
| 目标对象 `NtCreateDirectoryObject` | `0xC0000035` NAME_COLLISION（**对象已存在**） |
| 同对象 `NtOpen` 各权限 | `DIRECTORY_QUERY`/`LIST_DIRECTORY`/`MAXIMUM_ALLOWED` 成功；`SYNCHRONIZE`/`WRITE_DAC`/`ALL_ACCESS` → `0xC0000022` |
| 对象属主 | SID `…-1001`（当前用户） |
| 对照组：自建同名对象 | create 成功、open 成功（说明不是 BaseNamedObjects 整体不可写） |
| IFEO / AppCompatFlags 中 python 相关项 | 无 |
| git 子命令是否都需 msys | clone/fetch/push/ls-remote **需要**；init/add/commit/config/rev-parse/branch/tag/log/diff/cat-file/merge-base/ls-files **不需要**；`archive` 不需要 |
| 4 种 clone 形式（plain / --no-hardlinks / --local / file://） | Low-IL 下**全部**失败 |
| 清理 | 临时 clone 残骸 `_tmp_clone_*`、探针目录、探针脚本均已删除 |

## 4. Bug 报告与根因分析

### B3 — `workspace_id` 尾随点成为真实工作区的别名（Windows 名规范化）
- **现象**（§3.4 实测）：`GET /api/humanware/status/welcome.` → **200** 并返回真实 `welcome` 工作区状态；`POST generate-voice-file {"workspace_id":"welcome."}` → 200 并写入真实工作区。
- **根因**：Windows 在解析路径段时**剥离尾随点/空格**，`books/welcome.` 与 `books/welcome` 是同一目录；而 `_SAFE_ID_RE` 允许点、`_get_workspace_root` 用 `resolve()` + `exists()` 判定存在性。POSIX 上两者是**不同名字**，故该行为跨平台不一致，可用于绕过名字校验并以「另一个 id」操作真实数据。
- **修复**：`_get_workspace_root` 增加 `unsafe_windows_component(candidate)` 判定，尾随点/空白 → **400**（与设备名同一守卫）。
- **取舍**：也可只在「解析后名字 ≠ 请求名」时拒绝，但那会把合法输入在两台平台上给出不同状态码；直接拒绝非规范名更简单、跨平台语义一致，且不存在需要尾随点的真实工作区（Windows 也无法创建这类目录）。

### B4 — `novel_routes.safe_target` 接受设备名：写「成功」但内容静默丢失（**数据丢失**）
- **现象**：`PUT /api/novel-console/text` 以 `path="references/NUL"` → **200**，响应含 `sha256`，但磁盘上没有任何文件、按原名读回为空字符串；`path="references/outline."` → 200 但落盘名是 `outline`（作者随后按 `outline.` 读不到自己的文件）。
- **根因**：`safe_target` 只做绝对路径 + containment 校验，未校验**名字**；Windows 把 `NUL` 解析为设备，写入被丢弃且不报错（实测 `write_text` 不抛异常、`exists()=True`、`is_file()=False`）。这是 humanware 面 B2 的同型缺陷，但后果更严重——B2 是读到假数据，B4 是**用户稿件被「保存成功」地丢掉**。
- **修复**：`safe_target` 在解析前用 `unsafe_windows_path(relative)` 逐段判定 → **403**（沿用该函数既有 403 语义，不改变已有错误码约定）。
- **风险**：极低。仅拒绝此前会丢数据的名字；`meta/console-NUL`、`outline.md`、`a.b.c.md`、`COM0` 等均不受影响（已有放行用例守卫）。

### B5 — 工作区**根**以设备名结尾：未捕获异常 → HTTP 500
- **现象**：`workspace` 覆盖参数解析到 `…/books/NUL` 时，`PUT /text` 抛 `FileNotFoundError [WinError 3]`（`target.parent.mkdir` 失败），未被端点捕获 → **500**；`DELETE /projects` 同型路径中 `root.exists()` 恒真、`shutil.rmtree(ignore_errors=True)` 静默「成功」，接口**谎报删除成功**。
- **根因**：Windows 下 `<dir>/NUL` 是「幻影目录」——`mkdir` 静默成功、`exists()` 恒真、`is_dir()` 为假，其下任何真实写入必然失败。`resolve_workflow_workspace` 的 override 分支只校验「是否落在 BASE_DIR 内」，不校验名字，因此幻影根能通过。
- **修复**：`safe_target` 开头增加 `unsafe_windows_root(root)` → **400**。选它作为唯一收敛点：novel 面 10 处调用全部经过 `safe_target`，一处修复覆盖读写；`delete_project` 经实测同样先命中既有 containment 检查返回 **400**（用例 TC-R17-10 记录为 4xx 允许集合）。
- **未一并处理**（记为 R18 建议）：`WorkspaceManager._sanitize_id` 只剥字符不查设备名，且 `resolve_workflow_workspace` 会**自动 mkdir**，可在 `data/workspaces/` 下留下 `NUL` 幻影项；在 core 层加守卫会影响所有调用方（含 CLI/内部服务），本轮按「最小改动」只在 web 路径面收敛。

### P0-1（R16 遗留，仍未完成）— 两仓库推送
- 插件 5 笔、xs2 24 笔未推送；会话内 `credential.helper=manager` 需弹窗、无人值守被拦。需用户手动：
  `cd "F:\DeterminFlow x2\DeterminFlow-Plugins" && git push origin main`，随后 xs2 同法。
- 验收：两仓库 `git log origin/main..main` 为空。

### R16-ENV-1（本轮定位为环境，非代码）
- **R16 的结论需要修正**：「疑似安全软件/系统更新、重启后可复跑」**不成立**。
- **真正机制**：可执行文件从 **F: 盘**启动时进程令牌为 **Low 完整性级别**（`python.exe` 换名、换副本均如此；`node.exe`/`py.exe`/`cmd.exe` 在本会话是 High）。机器上已存在由更早的 msys 进程创建的 `\BaseNamedObjects\msys-2.0S5-<hash>` 目录对象，Low-IL 进程只能以查询/列举权限打开，拿不到 msys 需要的写权限（`NtOpen` 对 `SYNCHRONIZE`/`WRITE_DAC`/`ALL_ACCESS` 返回 `0xC0000022`），于是 msys 一律在引导期死亡。
- **为什么同日 R15 绿、R16 红**：判别变量是解释器 IL，不是代码，也不是机器状态。**无需重启。**
- **影响面**：所有需要 git clone/fetch/push/ls-remote 的用例（60 项）；`init/add/commit` 等原生动词不受影响（实测）。同一 IL 也解释 R15/R16 记录的「symlink 需管理员」——High-IL 下 symlink 用例真实通过。
- **本轮处置（已固化进仓库）**：
  1. `tests/conftest.py` 增加 `pytest_runtest_makereport` 钩子：失败文本含 `NtCreateDirectoryObject` 签名 → 转 skip；对**已知依赖 git 传输的 6 个模块**，仅当内建探测（真实 `git clone` 本地仓库并检查该签名）确认传输不可用时才把失败转 skip。**探测通过时钩子完全不介入**，真实缺陷不可能被掩盖。
  2. `docs/PROJECT_INFO.md` 平台注意事项 9 改写为上述根因 + High-IL 复跑命令；注意事项 7 的 symlink 结论同步修正。

## 5. 修复代码要点（补丁位置）

| 文件 | 位置 | 变更 |
|---|---|---|
| **`src/web/path_guard.py`**（新） | 全文件 | Windows 名称约束单一实现：`WINDOWS_RESERVED_NAMES`（含 `CONIN$`/`CONOUT$`/`CLOCK$`）、`unsafe_windows_component`（设备名 + 尾随点/空白）、`unsafe_windows_path`（逐段）、`unsafe_windows_root`（幻影根）。非 `nt` 平台一律返回 `None`，POSIX 行为不变 |
| `src/web/humanware_routes.py` | 模块级 | 删除本地 `_WINDOWS_RESERVED_NAMES`，改 import `path_guard`（消除两面规则漂移） |
| `src/web/humanware_routes.py` | `_get_workspace_root` | 设备名 + 尾随点统一 `unsafe_windows_component` → 400（B3/B2） |
| `src/web/novel_routes.py` | `safe_target` | 进入即校验根（`unsafe_windows_root`→400，B5）与相对名（`unsafe_windows_path`→403，B4） |
| `src/web/novel_routes.py` | `library_path` | 清洗后设备名 → 400（B4 同族） |
| `tests/test_windows_path_guard.py` | 新文件 | 10 条（§3.1），含「拒绝的必要性」取证用例 |
| `tests/test_humanware_routes.py` | `HumanwareInputFuzzTests` | +2 条（尾随点别名、设备名组合）；`"tail."` 断言按新语义改为 400 |
| `tests/test_humanware_e2e.py` | F5 | +1 条服务侧别名验收（能力探测，服务未加载新代码时诚实 skip） |
| `tests/conftest.py` | msys 探测钩子 | 环境失败 → skip（探测通过时不介入） |
| `docs/humanware-helper-contract.md` | **v3.2** | §2.2 增补尾随点别名一律 400、守卫集中在 `path_guard` |
| `docs/PROJECT_INFO.md` | 注意事项 7、9 + 测试环境 | IL 根因、High-IL 复跑命令、双基线数字 |

## 6. 回归测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| Windows 名称守卫（新） | `pytest tests/test_windows_path_guard.py` | **10 passed** |
| humanware 路由单测 | `pytest tests/test_humanware_routes.py` | **24 passed**（22 → 24） |
| humanware e2e（服务运行中） | `pytest tests/test_humanware_e2e.py` | **12 passed / 1 skipped**（F5 因服务为修复前代码而诚实 skip） |
| novel 全部 13 个测试文件 + humanware 路由 | 合并跑 | **98 passed / 0 failed** |
| **全量（Low-IL / venv）** | `.\.venv\Scripts\python.exe -m pytest -q` | **1500 passed / 97 skipped / 0 failed**（105.86s） |
| **全量（High-IL / py.exe + PYTHONPATH）** | `C:\Windows\py.exe -m pytest -q` | **1585 passed / 12 skipped / 0 failed**（130.68s） |
| 被 R16-ENV-1 阻塞的 6 个插件文件（Low-IL） | 单独跑 | 37 passed / 62 skipped（环境 skip，0 失败） |
| 同上（High-IL） | 单独跑 | **99 passed / 0 failed** ← 阻塞已消除 |
| High-IL 剩余 12 个 skip 的构成 | 逐条核对 | macOS 签名 6、`icon.icns` 1、POSIX `fcntl` 2、Unix 进程组/树 2、e2e F5 1 = **11 + 1**；**symlink 类 skip 为 0** |
| 前端（无改动） | `npm.cmd run lint` / `test` / `build` | lint 0 problems；**406 个测试全过**（8 套件：48/17/135/81/100/1/18/6，fail 0）；✓ built in 6.22s |
| 工作树 | `git status` | 仅本轮预期改动，无临时文件残留（探针脚本与残骸已清理） |

> 与 R16 基线（1439 passed / 46 skipped，60 项阻塞）比较：本轮同一工作树在 High-IL 下 **1585 passed**，
> 即 **60 项恢复执行 + 13 项新增用例 + 其余存量**。

## 7. 优化清单（本轮）

| 编号 | 问题 | 方案 | 预期收益 | 风险 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| O1 | 同一 Windows 名称规则在两面各写一遍（humanware 本地集合 / marketplace `bundle._RESERVED` / novel 无） | 抽 `src/web/path_guard.py`，两面共用 | 规则漂移消除；新面接入成本 1 行 | 无（行为等价并有对照测试） | 高 | ✅ |
| O2 | R16-ENV-1 使全量 `pytest -q` 刷 60 个假失败，掩盖真实回归 | conftest 探测钩子（签名 + 探测双门控） | Low-IL 全量 0 失败；High-IL 钩子不介入 | 低（探测失败时不 skip） | 高 | ✅ |
| O3 | 缺少可执行的 High-IL 复跑路径 | 文档固化 `py.exe` + venv site-packages `PYTHONPATH` 命令 | 60 项 + symlink 项随时可真跑 | 无 | 高 | ✅ |
| O4 | 静默数据丢失面（B4/B5）无任何测试覆盖 | 新文件 10 条，含「拒绝的必要性」取证 | 该缺陷类从此有回归保护 | 无 | 高 | ✅ |
| O5 | e2e 对「服务是否已加载新代码」无感知，易误报通过 | F5 采用能力探测 + 不满足即显式 skip（写出原因） | 不会把未部署的修复当成已验证 | 无 | 中 | ✅ |

## 8. 风险与遗留问题

| 编号 | 问题 | 说明 | 风险 |
|---|---|---|---|
| **R17-1** | **8021 服务仍运行修复前代码**：B3/B4 在服务侧尚未生效（`welcome.` → 200 可越界写、`references/NUL` 假装保存成功） | 未重启原因：该进程由上一会话的进程链持有 workflow-executor **独占租约**，本轮实测另起 8022 在 pool 与 inline 两种模式下都因 `ExecutorLeaseUnavailable` 启动失败；未经确认不重启他人服务。**需要用户确认后重启 8021**，随后 e2e F5 会自动执行 | **高（修复未上线）** |
| R17-2 | 两仓库未推送（插件 5 笔 / xs2 24 笔） | 无缓存凭据，需用户手动 `git push`（GCM 弹窗） | 中（协作） |
| R17-3 | `WorkspaceManager` 层面仍无设备名守卫 | `_sanitize_id` 只剥字符；`resolve_workflow_workspace` 会 `mkdir(exist_ok=True)`，可在 `data/workspaces/` 下留 `NUL` 幻影项。本轮只在 web 面收敛（core 层改动影响所有调用方） | 中 |
| R17-4 | 本轮 `path_guard` 未接入 `skill_marketplace.bundle` | 该处已有等价内联规则（`_RESERVED` + `part.endswith(".")`），行为一致；替换属去重重构，按「不引入无关重构」暂缓 | 低 |
| R17-5 | **交接文档误记**：R16 §6 记「前端 6 pass」 | 本轮实测前端为 8 个套件 **406 个测试**；R16 用 `Select-Object -Last 12` 截断只看到最后一个套件 | 低（记录质量） |
| R17-6 | 本机 F: 盘启动的 python 为 Low IL 属**机器/盘配置**事实 | 影响所有 git 传输与 symlink 测试；已文档化并给出 High-IL 路径。若希望默认即 High，需排查 F: 盘上 exe 的降格来源（本机 IFEO/AppCompat 均无记录，ML 标签在文件/目录 SDDL 中亦无） | 低（环境） |
| R17-7 | `learning/candidates.json` 未接入 analyze-voice（R15-3/R16-3 延续） | 产品决策项，本轮未动 | 低 |
| R17-8 | 前端 `HumanwareScoreCard` 无调用方（R15-7/R16-5 延续） | UI 未接线 | 低 |
| R17-9 | `setup_plugins.py`「假安装」（R15-8/R16-6 延续） | 待决策 | 低 |
| **R17-10** | **本仓库存在并发写入者**：会话期间 `scripts/_hw_e2e_r15.py` 的删除被另一主体提交为 HEAD `ff0a8cf`（作者 `p`，message 仅 `c`，23:40:45），而 R16 的其余产物（`docs/HANDOVER_ROUND16.md`、`tests/test_humanware_e2e.py`、`scripts/_hw_bench_r16.py`、契约/PROJECT_INFO 改动）仍未提交 | 多主体同时在同一工作树上改动：一方 `git add -A` 会把另一方半成品一并提交；本轮因此只提交自己的改动而不用 `-A`。建议 R18 前先协调单一写入者或改用独立 worktree/分支 | **中（协作/历史完整性）** |

## 9. 下一轮迭代计划（Round 18）

| 优先级 | 任务 | 预估工作量 | 验收标准 |
|---|---|---|---|
| **P0** | **确认后重启 8021** 使 v3.2 守卫上线，并复跑 `pytest tests/test_humanware_e2e.py`（F5 应从 skip 转 PASS）+ `scripts` 侧一次 §3.4 实时取证复验（`welcome.` → 400、`references/NUL` → 403） | 0.3h | e2e 13/13 PASS；无 2xx 别名命中 |
| **P0** | 手动推送两仓库（插件 5 笔 / xs2 24 笔） | 0.2h | 两仓库 `git log origin/main..main` 为空 |
| P1 | R17-3：把设备名/尾随点守卫下沉到 `WorkspaceManager`（`_sanitize_id` 或 `resolve_workflow_workspace`），并禁止以 `mkdir` 兜底创建幻影根 | 2h | core 层新增用例；两面复用；全量 0 失败 |
| P1 | 以 High-IL 解释器为准建立「权威基线」并写入 CI/文档默认命令（Low-IL 仅作快速跑） | 1h | 文档明确两种模式数字与用途；一次全流程复跑记录 |
| P2 | R17-4：`skill_marketplace.bundle` 改用 `path_guard`，消除第三份同型规则；同时复查 `novel_reference_*`、`export` 等其余名字拼接点 | 1.5h | 单一实现；既有 marketplace 用例全过 |
| P2 | 决策 R17-7（candidates 接入 analyze-voice） | 2h（含确认） | 二选一落地并同步契约 |
| P3 | R17-8 前端接线 `HumanwareScoreCard`；P3 R17-9 `setup_plugins.py` 决策 | 2h / 1h | 组件测试 + lint/test/build 全绿 / 决策落地 |
| P3 | 若 F: 盘 Low-IL 降格来源需要根除：在干净登录环境对比 `python.exe` 的 IL，并检查杀软/盘策略（本轮未定位到具体策略项） | 1h | 明确成因或确认为不可控并保留 High-IL 路径 |

## 10. 命令记录（本轮）

```
# P0 复验 R16-ENV-1
python -c subprocess → GfW sh.exe：0xC0000022（仍存在）
矩阵：pwsh→sh OK；python→sh 崩；python→cmd OK；cmd(High)→python = Low
      C:\Temp 副本 pythonq.exe = High；F: 盘副本 = Low；node/py.exe = High
      IFEO、AppCompatFlags：无 python 相关项；文件/目录 SDDL：无 ML 标签
命名对象：create → 0xC0000035（已存在）；open QUERY/LIST/MAXIMUM_ALLOWED OK；
          SYNCHRONIZE/WRITE_DAC/ALL_ACCESS → 0xC0000022；属主 SID …-1001
git 动词矩阵：clone/fetch/push/ls-remote 需 msys；init/add/commit/config/
          rev-parse/branch/tag/log/diff/cat-file/merge-base/ls-files 不需；archive 不需
High-IL 恢复：py.exe -m pytest 6 个插件文件（PYTHONPATH 挂 venv site-packages）→ 99 passed

# 缺陷取证（scripts/_r17_live_check.py，用后即删）
welcome./welcome../welcome... → 200（别名命中真实工作区）
POST generate-voice-file welcome. → 200（越界写真实工作区）
PUT /text references/NUL → 200 + sha256（内容丢弃，无文件）
PUT /text references/outline. → 200（落盘名为 outline）
NUL./COM1./CON.txt → 400（R16 黑名单已覆盖带点变体）

# 红灯（新文件首跑）
pytest tests/test_windows_path_guard.py → 6 failed（守卫未接入前）
python 直证：写 NUL 不抛异常、exists=True、is_file=False、readback=''
幻影根：PUT /text → 未捕获 FileNotFoundError [WinError 3]（500）

# 修复（新增 src/web/path_guard.py；两面接入；conftest 钩子）
pytest tests/test_windows_path_guard.py → 10 passed
pytest tests/test_humanware_routes.py → 24 passed（22 → 24）
pytest tests/test_humanware_e2e.py → 12 passed / 1 skipped（F5 诚实 skip）
pytest <13 个 novel/humanware 文件合并> → 98 passed

# 全量回归
Low-IL ：pytest -q → 1500 passed / 97 skipped / 0 failed
High-IL：py.exe -m pytest -q → 1585 passed / 12 skipped / 0 failed
前端   ：lint 0 problems / test 406 pass 0 fail（8 套件）/ build ✓ 6.22s
8022 复现实例：pool 与 inline 均 ExecutorLeaseUnavailable（8021 持独占租约）→ 放弃，未重启他人服务

# 收尾
清理 scripts/_r17_*（18 个探针文件/输出）、_tmp_clone_*、r17_* 与 git-transport-probe-* 残骸、
  两个空 tmp* 目录；determinflow-executor-*/ 属 8021 服务且已 gitignore，未动
文档：契约 v3.2、PROJECT_INFO 注意事项 7/9 + 双基线、HANDOVER_ROUND17.md
```
