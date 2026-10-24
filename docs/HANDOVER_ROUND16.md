# DeterminFlow (xs2) 交接报告 — Round 16（输入安全加固 + e2e 套件化 + 并发基线 + 环境阻塞记录）

> 生成时间：2026-10-23
> 项目路径：`F:/DeterminFlow x2/xs2`（主仓库）；`F:/DeterminFlow x2/DeterminFlow-Plugins`（插件仓库）
> 分支：main（两个仓库各自）
> 本轮提交：xs2（修复+测试+契约 v3.1+文档）；插件仓库无新提交（无代码改动）
> 上一轮：[HANDOVER_ROUND15.md](./HANDOVER_ROUND15.md)
> 接口契约：[humanware-helper-contract.md](./humanware-helper-contract.md)（本轮升 **v3.1**）
> 文档编码：UTF-8

> **⚠️ 勘误（2026-10-24，Round 17 勘正，两处）**
> 1. **R16-ENV-1 根因结论有误**：本文 §4「疑似安全软件/系统更新、需重启」**不成立**。真正机制是
>    **F: 盘启动的 `python.exe` 进程令牌为 Low 完整性级别**（High-IL 解释器跑同一套件 60 项全部恢复，
>    symlink 类 skip 也随之消失），**无需重启机器**。详见 [HANDOVER_ROUND17.md](./HANDOVER_ROUND17.md)
>    §4 与 `PROJECT_INFO.md` 注意事项 9（已被 R17 改写）。
> 2. **§6「前端 test 6 pass」为记录错误**：`tail` 截断只看到最后一个套件；实际为 8 个套件
>    **406 个测试全过**（R17-5 已勘正）。
> 本文档其余内容（B1/B2 修复、e2e 套件化、并发基线）不受影响。

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| 本轮定位：执行 R15 交接 §9 计划（P0 e2e 套件化 / P1 安全 fuzz + 并发基线 / P2 阈值可配置） | §2 测试计划；完成度 6/9（见 §9） |
| **发现并修复 2 个真实缺陷**（B1/B2），均先用失败测试固化再修 | §3 红灯证据、§4 Bug 报告 |
| **R16-ENV-1：本机 msys 引导被拒，60 个插件系统测试无法在本会话执行**（机器级状态故障，非代码缺陷） | §4 ENV 报告；最小复现 + 7 项排除实验 |
| 排除阻塞后全量回归 **1439 passed / 46 skipped / 0 failed**（R15 基线 1529 中相应 60 项被阻塞） | `pytest -q --ignore=<6 个插件测试文件>` 实跑 |
| humanware 路由单测 15 → **22**；e2e 由脚本改写为 pytest **12 条**（服务未运行时干净 skip） | 两文件 pytest 实跑 |
| e2e 套件对真实 8021 服务 **12/12 PASS**（含 4 条真实 CLI fuzz） | 重启服务后实跑 |
| 并发基线：**Semaphore(4) 吞吐封顶 ~50–56 req/s，16 并发 P95 < 310ms，零失败 → 无需调参** | `scripts/_hw_bench_r16.py` 数据表 |
| 前端无改动，回归仍绿 | lint 0 problems / test 6 pass / build 5.99s |
| **P0-1 推送插件仓库未完成**：会话内无可用 GitHub 推送凭据（GCM 弹窗被拦） | §4 ENV；转待用户操作 |

## 2. 测试计划（本轮）

- **范围**：R15 交接 §9 的 P0/P1/P2 项；humanware 契约面扩展 fuzz；并发性能基线；全量回归。
- **类型**：功能（e2e 套件化）、边界（NUL、保留设备名、长度上界、超长 stdin）、异常（非法输入语义）、安全（路径/输入 fuzz：URL 编码、全角点、混合反斜杠、非法首字符、Windows 设备名）、性能（并发 P50/P95/吞吐）、回归（全套 + 前端）。
- **环境**：Windows 本机，venv Python 3.14.8，服务 `http://localhost:8021`（本轮重启 3 次），工作区 `welcome` + 临时隔离工作区（e2e fixture 按 UUID 命名、用后即删）。
- **通过标准**：除 R16-ENV-1 阻塞文件外 pytest 0 failed；新增用例全绿；前端 lint/test/build 全过；e2e 12/12。
- **运行命令**：
  ```
  cd "F:\DeterminFlow x2\xs2"
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_routes.py -v      # 路由单测（22）
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_e2e.py -v         # 需服务运行
  .\.venv\Scripts\python.exe scripts\_hw_bench_r16.py                          # 并发基线
  .\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_plugin_store.py \
      --ignore=tests/test_plugin_routes.py --ignore=tests/test_plugin_host_integration.py \
      --ignore=tests/test_plugin_registry.py --ignore=tests/test_plugin_source_catalog.py \
      --ignore=tests/test_plugin_resource_namespace.py                          # 全量（排除 ENV 阻塞）
  cd web && npm.cmd run lint && npm.cmd test && npm.cmd run build
  ```

## 3. 测试用例与执行结果

### 3.1 新增：路由层 fuzz + 阈值（`HumanwareInputFuzzTests`，15 → 22）

| 编号 | 场景 | 预期 | 实际 | 状态 |
|---|---|---|---|---|
| TC-R16-01 | body workspace_id fuzz（`%2e%2e`、全角点、`..\..`、URL 与 body 双层编码、NUL、`-` 首字符、`.` 首字符、空格） | 400 | 修复前 NUL 类 → 500 | ✅（修后） |
| TC-R16-02 | 合法模式但不存在（`ghost`、`tail.`） | 404 | 404 | ✅ |
| TC-R16-03 | Windows 保留设备名（`NUL`/`nul`/`Con`/`NUL.txt`/`COM1`/`LPT9`/`aux`）GET status+voice-file | 400 | 修复前 NUL → **200** | ✅（修后） |
| TC-R16-04 | character 含 NUL（score-content / check-dialogue） | 400 | 修复前 500 | ✅（修后） |
| TC-R16-05 | dialogue / chapter_file 含 NUL | 400 | 修复前 500 | ✅（修后） |
| TC-R16-06 | 阈值环境变量下调为 10，12 字符内容 | argv=`-`（stdin 生效） | 生效 | ✅ |
| TC-R16-07 | 未设环境变量（默认 8192），12 字符 | argv 原样 | 不回归 | ✅ |
| TC-R16-08 | 阈值环境变量非法值（`abc`/`-5`/`0`） | 回退 8192 且不 500 | 回退 + warning 日志 | ✅ |

> 红灯证据：首跑 `5 failed`（TC-03/04/05 + 阈值两条），与探针实测一一对应。

### 3.2 e2e pytest 化（`tests/test_humanware_e2e.py`，新文件 12 条）

| 编号 | 场景 | 实测 |
|---|---|---|
| E1–E7b2 | R15 九项契约验收（argv/stdin 通道、409 透传、归属对照） | 全部保留，9/9 PASS |
| F1 | 真实 CLI：character 含 NUL → 400（修复前 500） | PASS |
| F2 | 真实 CLI：chapter_file 含 NUL → 400 | PASS |
| F3 | 真实服务：`workspace_id=NUL/nul/COM1` → 400 | PASS |
| F4 | 真实 CLI：绝对路径 / `..` 逃逸 / `/etc/passwd` → 400 | PASS |

- 模块级 `_probe()`：服务未运行或 welcome 缺 voice 文件时整模块 skip（全量回归停服跑实测 skip 12，干净）。
- 原一次性脚本 `scripts/_hw_e2e_r15.py` 已 `git rm`；临时探针 `scripts/_hw_probe_r16.py` 用后即删。

### 3.3 并发性能基线（`scripts/_hw_bench_r16.py`，真实服务）

| 场景 | N | 吞吐(req/s) | 均值(ms) | P50(ms) | P95(ms) | Max(ms) | 失败 |
|---|---|---|---|---|---|---|---|
| 短内容 argv | 1 | 11.1 | 89 | 89 | 89 | 89 | 0 |
| 短内容 argv | 4 | 53.8 | 73 | 73 | 74 | 74 | 0 |
| 短内容 argv | 8 | 56.0 | 107 | 139 | 142 | 142 | 0 |
| 短内容 argv | 16 | 56.0 | 176 | 205 | 282 | 282 | 0 |
| 长内容 42K stdin | 1 | 13.2 | 75 | 75 | 75 | 75 | 0 |
| 长内容 42K stdin | 4 | 37.8 | 86 | 80 | 105 | 105 | 0 |
| 长内容 42K stdin | 8 | 50.8 | 117 | 154 | 155 | 155 | 0 |
| 长内容 42K stdin | 16 | 51.4 | 192 | 224 | 304 | 304 | 0 |

**结论（R15-6 关闭）**：`_CLI_SEMAPHORE=4` 使吞吐封顶 ~50–56 req/s（N=4/8/16 几乎不变 = 闸门生效）；16 并发下 P95 < 310ms、零失败。单请求 ~75–90ms，解释器拉起为主要成本。对人工创作 UI 场景余量极大，**无需调参**；如未来出现机器评分批量场景，优先把 Semaphore 改为可配置（`DETERMINFLOW_HUMANWARE_CLI_CONCURRENCY`）而非上调。

## 4. Bug 报告与根因分析

### B1 — NUL 字符输入导致 500（违反契约 §2.2 语义）
- **现象**：`character`/`dialogue`/`chapter_file` 含 NUL（JSON `\u0000`，合法 JSON、合法 UTF-8）→ HTTP 500 `{"detail":"评分失败: embedded null character"}`（探针实测 4 个端点全部 500）。
- **根因**：`subprocess.run` 对含 NUL 的 argv 抛 `ValueError("embedded null character")`；`_run_humanware_command_blocking` 只捕获 `TimeoutExpired`/`OSError`，`ValueError` 冒泡到端点兜底 `except Exception` → 500。契约把「输入错误」定为 400。
- **修复**：`_run_humanware_command_blocking` 新增 `except ValueError` → `{"code": 400}`。选择在 CLI 调用层统一拦截（而非各端点预校验），因为 NUL 可出现在多个参数位，单点防御不漏。
- **风险**：极低——仅把原本 500 的失败改为 400，不触碰成功路径。

### B2 — `workspace_id="NUL"` 可通过校验（Windows 保留设备名）
- **现象**（真实 8021 实测）：GET `/api/humanware/status/NUL` → **200**（不存在的"工作区"）；PUT voice-file → 500 `[WinError 3]`。本机 `Path(".../books/NUL").exists()` 恒为 True（设备名重定向）。
- **根因**：`_SAFE_ID_RE` 允许 `NUL`/`CON` 等（`COM1`、`CON.txt` 形式均匹配 `[A-Za-z0-9][A-Za-z0-9_.-]*`），Windows 对保留设备名的 `exists()` 语义与普通目录不同，存在性校验被绕过。
- **修复**：nt 平台下 `_get_workspace_root` 增加 `candidate.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES` → 400（覆盖 `NUL.txt`/`con.md` 变体与大小写）。POSIX 不受影响，不加守卫则跳过。
- **备选取舍**：改用「工作区必须含 meta/ 子目录」的存在性增强也可挡住，但会把合法空工作区拒之门外（工作区可先于 meta 创建），故选黑名单。设备名清单为 Windows 官方固定集合，无维护风险。
- **风险**：极低——已存在名为 CON/NUL 的真实工作区的概率为零（Windows 无法创建）。

### R16-ENV-1 — 本机 msys 全新引导被拒（环境故障，非代码缺陷）
- **现象**：全量回归 60 failed，全部集中在 `test_plugin_store/routes/host_integration/registry/source_catalog/resource_namespace`（所有需要 `git clone/fetch` 的用例）；错误统一为
  `0 [main] sh (...) C:\Program Files\Git\usr\bin\sh.exe: *** fatal error - NtCreateDirectoryObject(\BaseNamedObjects\msys-2.0S5-<hash>): 0xC0000022`（STATUS_ACCESS_DENIED）。
- **最小复现**：`.venv python -c "subprocess.run([r'C:\Program Files\Git\usr\bin\sh.exe','-c','echo OK'], capture_output=True)"` → 0xC0000022。而 bash 内直接 `git clone file:///...`（同样派生 sh）成功（GIT_TRACE 实证 sh 正常执行 upload-pack）。
- **规律**：由既有 msys 进程链（bash → …）派生的 msys 程序可用（child_info 继承共享节区）；任何**独立引导**（python/cmd/计划任务派生）一律拒绝。
- **已排除**（7 项实验）：ZCode 沙箱（`dangerouslyDisableSandbox` 仍崩）、msys 祖先链（cmd 父仍崩）、环境变量（去 MSYSTEM/CYGWIN/干净 PATH 均崩）、CWD、管道捕获、git `insteadOf` URL 重写（只重写目标不改变传输方式）、`protocol.version=0`（file:// 仍走 sh）。
- **影响**：仅测试执行环境；R15 基线同日全绿证明非代码回归；本轮全部改动（humanware 路由/测试/文档）与失败文件零交集，且排除阻塞后其余 **1439 passed / 0 failed**。
- **处置**：详见 `PROJECT_INFO.md` 平台注意事项第 9 条。建议：**重启机器后在新终端复跑全量 pytest**；若仍复现，排查当日更新的安全软件。下轮（R17）接手时应先做此验证。

### P0-1 未完成 — 插件仓库推送（转待用户操作）
- `git push origin main`（5 笔提交：`fea68e5`、`91c4914`、`e4ba419`、`582de10`、`3c8ff4e`）在会话内挂起：credential.helper=manager 需要弹窗交互，无人值守上下文被拦（`GCM_INTERACTIVE=never` 显式失败：`Cannot prompt`）。
- 另发现：**xs2 主仓库也有 23 笔未推送提交**（R15 只记录了插件仓库）；本轮未擅自推送。
- **需要的用户动作**：在终端手动执行 `cd "F:\DeterminFlow x2\DeterminFlow-Plugins" && git push origin main`（弹出 GCM 窗口完成认证）；随后可一并推送 xs2 主仓库。验收：`git log origin/main..main` 为空。

## 5. 修复代码要点（补丁位置）

| 文件 | 位置 | 变更 |
|---|---|---|
| `src/web/humanware_routes.py` | imports | 新增 `os` |
| `src/web/humanware_routes.py` | 模块级 | 新增 `_WINDOWS_RESERVED_NAMES`（CON/PRN/AUX/NUL/COM1-9/LPT1-9） |
| `src/web/humanware_routes.py` | `_get_workspace_root` | nt 平台保留设备名 → 400（B2） |
| `src/web/humanware_routes.py` | `_run_humanware_command_blocking` | 新增 `except ValueError` → code 400（B1） |
| `src/web/humanware_routes.py` | `_STDIN_ARG_THRESHOLD` 区块 | 新增 `_STDIN_ARG_THRESHOLD_ENV` + `_stdin_arg_threshold()`（缺失/非整数/<1 回退默认 + warning，R15-4） |
| `src/web/humanware_routes.py` | `_content_arg` | 改读 `_stdin_arg_threshold()` |
| `tests/test_humanware_routes.py` | 新类 `HumanwareInputFuzzTests` | 8 条（§3.1） |
| `tests/test_humanware_e2e.py` | 新文件 | 12 条 e2e（§3.2），`git rm scripts/_hw_e2e_r15.py` |
| `scripts/_hw_bench_r16.py` | 新文件 | 并发基线脚本（§3.3） |
| `docs/humanware-helper-contract.md` | v3.1 | 阈值环境变量、§2.2 后端预校验语义 |
| `docs/PROJECT_INFO.md` | 平台注意事项 #9 | R16-ENV-1 记录 |

## 6. 回归测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| humanware 路由单测 | `pytest tests/test_humanware_routes.py -v` | **22 passed**（15 → 22） |
| e2e（服务运行中） | `pytest tests/test_humanware_e2e.py` | **12 passed**（1.03s） |
| e2e（停服，全量回归内） | 同上模块级 skip | 12 skipped，干净 |
| 全量（排除 ENV 阻塞 6 文件） | `pytest -q --ignore=...`（**服务已停**） | **1439 passed / 46 skipped / 0 failed**（85.36s） |
| 全量（含阻塞文件，如实记录） | `pytest -q` | 1476 passed / 60 failed / 48 skipped——60 个失败全部为 R16-ENV-1（msys 引导拒绝），详见 §4 |
| 跳过分布 | 基线 36 环境类 + e2e 12 + 插件文件内 2 | 与基线一致（环境限制） |
| 前端（无改动） | `npm.cmd run lint` / `test` / `build` | 0 problems / 6 pass 0 fail（**勘误：实为 8 套件 406 全过**，见文首） / ✓ built in 5.99s |
| 服务状态抽查 | `GET /api/plugins` | bishu-novel running；xs2-novel-flywheel running；restart_required=False |

## 7. 优化清单（本轮）

| 编号 | 问题 | 方案 | 预期收益 | 风险 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| O1 | e2e 一次性脚本不可持续（R15 §9 P0） | 改写为 pytest + `skipif` 探针，删除脚本 | 契约回归纳入常规套件；停服跑不炸 | 无 | 高 | ✅ |
| O2 | 阈值硬编码（R15-4） | 环境变量 + 非法值回退 + 3 条单测 | 极端受限环境可调 | 无 | 中 | ✅ |
| O3 | 输入安全面未覆盖 NUL/保留设备名 | fuzz 用例固化 + 两处修复 | 消除 500 噪声与设备名绕过 | 无 | 高 | ✅ |
| O4 | Semaphore 无量化数据（R15-6） | 基线脚本 + 数据表 + 明确「不调参」结论 | 后续调参有据可依 | 无 | 中 | ✅ |

## 8. 风险与遗留问题

| 编号 | 问题 | 说明 | 风险 |
|---|---|---|---|
| **R16-1** | **R16-ENV-1 环境故障未修复** | 60 个插件测试本会话无法执行；需重启机器复跑确认。**R17 第一步必须是全量 pytest 复验** | 高（验证盲区，待消除） |
| R16-2 | 插件仓库 5 笔 + xs2 主仓库 23 笔未推送 | 无缓存凭据，需用户手动推送（GCM 弹窗） | 中（协作） |
| R16-3 | `learning/candidates.json` 未接入 analyze-voice（R15-3 延续） | 产品决策项，本轮未动 | 低 |
| R16-4 | e2e 模块级探针在停服全量跑时增加 ~1–3s 收集时间 | `_probe()` 3s 超时上限；可改为 session fixture 若嫌慢 | 低 |
| R16-5 | 前端 `HumanwareScoreCard` 仍无调用方（R15-7 延续） | UI 未接线 | 低 |
| R16-6 | `setup_plugins.py`「假安装」（R15-8 延续） | 待决策 | 低 |
| R16-7 | 36 条环境类 skipped 仍在（R15-2 延续） | symlink/macOS/fcntl 平台限制 | 低 |

## 9. 下一轮迭代计划（Round 17）

| 优先级 | 任务 | 预估工作量 | 验收标准 |
|---|---|---|---|
| **P0** | **重启机器后复跑全量 pytest**，确认 R16-ENV-1 消除、60 个插件测试恢复；若仍失败按 PROJECT_INFO #9 排查安全软件 | 0.5h | `pytest -q` 恢复 ≥1529 passed / 0 failed（基线 + 本轮新增） |
| **P0** | 手动推送两仓库：插件 5 笔、xs2 23 笔 | 0.2h | 两仓库 `git log origin/main..main` 为空 |
| P1 | 契约 v3.1 的 e2e 增补：阈值环境变量在真实服务的生效用例（设置 env → 重启 → 超阈值内容走 stdin） | 1h | 用例进 `test_humanware_e2e.py`，或以单测 + 文档说明替代 |
| P1 | B1/B2 的语义对齐复查：`workspace_id` 预校验是否同样适用于 novel 等其他路由面的同型函数（若存在复制粘贴的 `_get_workspace_root`） | 1h | grep 全部同型函数并统一；否则记录「仅 humanware 面」结论 |
| P2 | 决策 R16-3（candidates 接入 analyze-voice） | 2h（含确认） | 二选一落地并同步契约 |
| P2 | `DETERMINFLOW_HUMANWARE_CLI_CONCURRENCY` 可配置化（仅在出现批量评分需求时） | 0.5h | 环境变量生效 + 单测 |
| P3 | 前端接线 `HumanwareScoreCard`（R15/R16 延续） | 2h | 组件测试 + lint/test/build 全绿 |
| P3 | 环境类 skipped 收敛（管理员/WSL 复跑 symlink 用例） | 1h | 明确「通过 / 真缺陷」清单 |

## 10. 命令记录（本轮）

```
# 基线核实
git status（两仓库干净）；xs2 HEAD 3927a65；插件 origin/main..main = 5 笔（R15 只记录 3 笔，少计 fea68e5/91c4914）
8021 未运行 → run.py 后台启动 → READY

# P1-2 探针（scripts/_hw_probe_r16.py，用后即删）
NUL character → 500 embedded null character；ws=NUL → 200 / PUT 500 WinError 3
CON → 404（正常）；绝对路径/.. 逃逸 → 400；工作区内 .. → 409（containment，契约允许）

# 红灯
pytest tests/test_humanware_routes.py::HumanwareInputFuzzTests -v → 5 failed
# 修复（humanware_routes.py：ValueError→400、保留设备名→400、阈值环境变量）
pytest tests/test_humanware_routes.py → 22 passed
重启 8021 → 探针复跑：NUL → 400、ws=NUL → 400

# P0-2 e2e 套件化
pytest tests/test_humanware_e2e.py → 12 passed（1.06s）；git rm scripts/_hw_e2e_r15.py

# P1-1 基准
scripts/_hw_bench_r16.py → EXITCODE=0（数据表见 §3.3）

# 全量回归
停 8021 → pytest -q → 60 failed（全部 msys 0xC0000022）
#   排查链：沙箱/祖先链/环境变量/CWD/捕获/insteadOf/protocol.version=0 全排除
#   最小复现：python subprocess 派生 GfW sh.exe 必崩；bash 链内正常（GIT_TRACE 实证）
pytest -q --ignore=<6 插件测试文件> → 1439 passed / 46 skipped / 0 failed
cd web && npm.cmd run lint / test / build → 0 problems / 6 pass / ✓ built in 5.99s

# 收尾
清理：schtasks delete、git config --global --unset insteadOf、临时目录/脚本
重启 8021 → e2e 12 passed；/api/plugins 双插件 running
文档：契约 v3.1、PROJECT_INFO #9、HANDOVER_ROUND16.md
```
