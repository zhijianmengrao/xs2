# DeterminFlow (xs2) 交接报告 — Round 46（闸门真正接进 CI / R2 应急通道补门控）

> 本轮定位：按用户选定的两项（R45 §8-1 闸门接线 + R45 §8-2 R2 步骤收口）做维护轮。
> 基线：`0f64d43`（R45 收尾）→ 本轮 xs2 提交 1 个（见 §6），插件仓零提交。
> 用户同时确认：CI e2e **暂缓**（模型凭据设计未决）、画像对比演进本轮不做。

## 1. 为什么这一轮值得做

R45 把两件事做成了「只差一步」，本轮走完那一步：

1. **闸门没有自动使用者**（R45 §2.4 / §7-1）。`--require-sample` 与退出码 3 已落地
   并测得很细，但 `ci.yml` 五个 job 里没有任何一步调用它。R45 自己的判断是
   「退出码 3 已就位，接下来无论走哪条路都只需要加一步」——本轮加的就是这一步。
   不做的后果是：一个**测过但从不运行**的防护，和不存在没有区别。
2. **R2 应急通道无门控**（R45 §8-2）。`replace-desktop-assets.yml` 的 R2 步骤
   **无条件执行**，而常规发版路径 `desktop-windows.yml` 有
   `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`。与「大陆下载加速维持现状」的
   结论并存有歧义：任何人手动跑一次这个 workflow，线上 R2 就被写入并切换
   stable manifest。这是**活的**风险，不是文档问题。

两项的共同点：都是「代码里已经有一半，缺的是把两半接起来」。

## 2. 落地内容

### 2.1 闸门接进 CI（`.github/workflows/ci.yml` + `tests/fixtures/run_samples/`）

R45 §2.4 给了两条路：artifact 聚合 or 提交真实形状 fixture + `DETERMINFLOW_DATA_DIR`。
用户选后者。取证与实现：

| 决策点 | 取证 | 结论 |
|---|---|---|
| fixture 放哪 | `src/config.py:21` `DATA_DIR = Path(get_determinflow_env("DATA_DIR", BASE_DIR/"data"))`，`WORKFLOWS_DIR = DATA_DIR/"workflows"` | 放 `tests/fixtures/run_samples/workflows/`，`DETERMINFLOW_DATA_DIR` 指到 `run_samples` 即可命中，**不必破 `data/**` 的 gitignore** |
| import 有无副作用 | `src/config.py` 的建目录全在 `ensure_dirs()` 函数体内（210-228 行），模块级无调用 | 跑脚本不会在 CI 里凭空建目录 |
| 脚本依赖面 | `src.config` 只拉 `dotenv` + `default_resources`（纯标准库） + `skills.storage`（纯标准库） | `backend` job 装了 `requirements-dev.lock` 足够，无需额外安装 |
| 取哪些真实 run | 全库扫「带真实错误文本的尝试」共 16 条，挑覆盖 4 类错误分类 + 同 node 重复执行的 8 个 run | 见下表 |

**fixture 裁剪**：保留 `build_run_profile` 读的字段（`node_id` / `status` /
`attempt_count` / `attempt_history` / `automatic_retry_count` /
`output_repair_count` / `started_at` / `completed_at` / `error` /
`next_attempt_trigger`），删掉内容载荷（`summary` / `input_snapshot` /
`iteration_history` / `outputs` / `token_usage_calls` 等）。

**裁剪的正确性证据（不是靠印象）**：裁剪前后用 `build_run_profile` 各算一遍，
8 个 run 的画像**逐字段完全相同**（`profiles == profiles` 的字典相等，含
`attempts_detail` 里每一次尝试的 trigger/status/error/error_class/duration）。
体积 11M → 47KB。

8 个 fixture run 的真实构成：

| workflow | run | 真实错误类型 | attempts / failed |
|---|---|---|---|
| build | `run-107de93c` | `agent_society` 流式 120s 停摆 | 5 / 1 |
| build | `run-58206be9` | `agent_corelaws` Cloudflare 530 | 1 / 1 |
| build | `run-99009f61` | `agent_spacetime` 长度上限 | 3 / 1 |
| build | `run-c6105958` | `agent_corelaws` incomplete chunked read | 1 / 1 |
| build | `run-ff680fcd` | `agent_corelaws` Cloudflare 530 | 1 / 1 |
| character | `run-04ea8e0b` | `script_extract` JSON 解析失败 | 4 / 1 |
| character | `run-22cf1120` | 无失败，但 `agent_deep` 重复执行 4 次 | 30 / 0 |
| character | `run-99b3bd1b` | `agent_deep` 第 3 次 600s 停摆 | 15 / 1 |
| **合计** | | **TOTAL 60 次尝试 / 7 失败 / 11.67%** | |

**CI step 设计：三态全部真实断言**，这是本轮最有设计含量的决定。

只加一条 `--fail-if-above 15 --require-sample` 是没用的——它会永远绿，因为
fixture 固定，而「永远绿」正是 R45 §1 说的「静默失效」。所以 step 里把三种
退出码都真跑一遍：

| 断言 | 命令 | 退出码 | 证明了什么 |
|---|---|---|---|
| 未超阈 | `--fail-if-above 15` | **0** | 闸门在 CI 上真的判到了数据（60 次尝试） |
| 超阈 | `--fail-if-above 1` | **1** | 闸门**不是恒真**——真不合格时会红 |
| 无样本 | 空目录 + `--require-sample` | **3** | 「闸门没生效」会显式失败，不是静默放行 |

本地用同一段 shell（Git Bash 语义一致）实跑，三态命中：

```
[gate] 总失败率 11.67% 未超出阈值 15.0%（60 次尝试）
OK  阈值15  exit=0
[gate] 总失败率 11.67% 超出阈值 1.0%（60 次尝试）
OK  阈值1  exit=1
[gate] 无 run 样本（attempts=0），跳过失败率闸门（阈值 15.0%）
[gate] --require-sample: 一个 run 样本都没有，闸门未生效（退出码 3，...）
OK  无样本  exit=3
```

**判据边界（必须写清，否则下一轮会误读）**：fixture 是**固定**数据，所以这道
step 保护的命题是「闸门与脚本行为不退化」，**不是**「供应商今天健康」。真实数据
的失败率判定仍需要 run 记录进 CI（artifact 聚合或入库数据面），本轮**没有**做。

### 2.2 R2 应急通道补门控（`replace-desktop-assets.yml` + `desktop-windows.yml`）

两处对齐：

| 文件 | 改动 |
|---|---|
| `replace-desktop-assets.yml` | R2 步骤加 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`；`--public-base-url` 从硬编码改为 `$R2_PUBLIC_BASE_URL`（回落既有域名）；加注释说明它是**应急通道**、不属于常规发版路径 |
| `desktop-windows.yml` | 同样把 `--public-base-url` 改为变量取值，与上面保持一致（原本已有门控） |

域名变量写法 `${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}`
——未设变量时回落到既有域名，**行为与改动前相同**；设了变量才改域名。这样改域名
不必改代码，也不会让两处漂移。

### 2.3 契约测试 9 条（`tests/test_ci_gate_wiring.py`）

静态解析 yml，钉住四类回归：

| 用例 | 钉什么 |
|---|---|
| `test_ci_backend_job_invokes_the_failure_gate` | CI 真的调用闸门；函数定义带 `--require-sample`，每个调用点带 `--fail-if-above` |
| `test_ci_gate_points_at_the_fixture_data_dir` | `DETERMINFLOW_DATA_DIR` 指向 fixture，且有空数据态的显式改指 |
| `test_ci_gate_asserts_all_three_exit_codes` | 0/1/3 三态都被断言（只断言 0 = 恒真闸门） |
| `test_run_sample_fixture_exists_and_is_small` | fixture 非空且总量 < 200KB |
| `test_run_sample_fixture_matches_real_shape` | 画像算得出且自洽；真有失败尝试、真有错误文本、真有多 attempt 节点 |
| `test_run_sample_fixture_has_no_content_payload` | 裁剪纪律：正文/轨迹/token 明细不得进 fixture |
| `test_manual_workflow_r2_step_is_gated` | 应急通道的门控存在 |
| `test_regular_release_r2_step_keeps_its_gate` | 常规路径的门控不被反向改掉 |
| `test_both_r2_steps_take_base_url_from_variable` | 两处都从变量取域名，且变量真的传给脚本 |

**变异验证（四个全部咬合）**：

| 变异 | 预期 | 实测 |
|---|---|---|
| 删掉 `replace-desktop-assets.yml` 的 `if:` | 红 | ✓ `test_manual_workflow_r2_step_is_gated` 红 |
| 从 `run_gate` 去掉 `--require-sample` | 红 | ✓ `test_ci_backend_job_invokes_the_failure_gate` 红 |
| `DETERMINFLOW_DATA_DIR` 改指 `data/` | 红 | ✓ `test_ci_gate_points_at_the_fixture_data_dir` 红 |
| 删掉退出码 3 的断言 | 红 | ✓ `test_ci_gate_asserts_all_three_exit_codes` 红 |

**过程中暴露并修掉的一个自身缺陷**：最初的断言是「整个 run 块里出现过
`--require-sample`」，变异 2 加上去之后**测试仍然全绿**——因为空数据那一行还有
这个字符串。改成按「续行合并后的逻辑命令」逐条解析、把 shell 函数定义与调用点
分层断言后才真正咬住。这条记在这里，因为「断言粒度太粗导致变异逃逸」正是
防回归测试最常见的失效方式。

### 2.4 本轮**没有**做的事

1. **CI e2e**（R45 §8-3 / R43 §2.3 选项 B）：用户选择暂缓。前置条件是「CI 无
   模型凭据」的设计，两条路（桩 provider / 仅手工触发）各有代价，需要单独决策。
2. **画像跨 run 对比视图演进**（R45 §8-5）：本轮未动。
3. **闸门判真实数据**（R45 §2.4 的 artifact 路线）：未做，见 §2.1 判据边界。
4. **循环节点与重试语义**（R41 §9-3）：仍挂起，需后端 Core 配合。
5. **大陆下载加速**：维持现状（R44 §3.3 结论继续有效）。

## 3. 对 R45 记录的一处认知修正

R45 §8-2 描述 `replace-desktop-assets.yml` 时未点明 job 名，我在写测试时按
「`build` job」去取，实际它在 **`replace`** job；而 `desktop-windows.yml` 的 R2
步骤也不在 `build`，而在 **`release`** job（`build` job 有 16 步但零 R2 步骤，
`build-macos` 是空 job）。

这条修正的价值不在名字本身，而在于：**「R2 步骤在哪个 job 里」只能靠读 yml
确认，不能靠文档措辞推断**。静态契约测试第一版就因此红了一次——那正是它该做的事。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_ci_gate_wiring.py` | **9 passed** |
| 定向四文件（闸门 + 锁 + 容器 + 新契约） | **45 passed** |
| Low-IL 全量 | **1884 passed / 96 skipped / 0 failed**（105.16s） |
| High-IL 全量（权威） | **1969 passed / 11 skipped / 0 failed**（141.00s） |
| 前端 8 组 | **463 passed / 0 fail**（与 R45 一致，本轮零前端改动） |
| 前端 lint / build | 0 problems / ✓ 5.79s |
| 插件套件 | **98 passed / 0 fail** |
| 存储名审计 | **[clean]** exit 0 |
| fixture 实跑（阈值 5） | 60 尝试 / 7 失败 / **11.67%** → exit 1 |

**对账**：

- Low-IL：R45 1875 **+ 9**（新契约测试）= **1884** ✓
- High-IL：R45 1960 **+ 9** = **1969** ✓
- 总用例 R45 口径 1971 → **1980**（High passed+skipped：1969 + 11）

零净减，本轮无删除。

## 5. 未做与未验证的事（如实记录）

1. **CI 上的这条 step 本机没有真正跑过**：本机无 GitHub Actions，我在 Git Bash
   里用同一段 shell 实跑验证了逻辑与三态退出码，但**「CI runner 上 yml 解析、
   `${{ github.workspace }}` 展开、`env` 传递」只能在真实 CI 上验**。本轮推送后
   以 CI 日志为准。
2. **fixture 只覆盖 4 类错误分类中的 3 类**：`http_5xx` / `timeout` /
   `stream_stall` / `other` 都有真实样本，但 `connection` 分类（`peer closed
   connection`）文本实际被 `stream_stall` 或 `other` 吃掉——分类是关键词启发式，
   顺序敏感。**这不是本轮引入的**，但值得下一轮复核 `_ERROR_CLASS_PATTERNS`
   的判定顺序（`stream_stall` 的 `stream|chunk` 会先于 `connection` 命中）。
3. **R2 门控的实际效果依赖仓库变量**：`vars.R2_DISTRIBUTION_ENABLED` 若已被设为
   `true`，本次改动不改变行为（仍然发布）；门控的价值在于**它现在可以被关掉**，
   且与常规路径一致。仓库变量的当前值无法从代码侧核实。
4. **`R2_PUBLIC_BASE_URL` 是新引入的变量名**，仓库里未设置时回落既有域名（已测
   表达式语义正确性靠 yml 解析，运行时求值仍需 CI 实测）。
5. **`config/skills_config.json` 仍是未入库的运行时写入**（B23/R36 定性，与历轮一致）。
6. **本轮未重启 8021 服务**：改动面是 CI 配置 + workflow 配置 + 测试 + fixture，
   不涉及后端运行时代码，服务进程不受影响。

## 6. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | 本文档提交 | `ci(workflow)` 闸门接线 + `fix(workflow)` R2 门控 + `test` fixture 契约 + 交接文档 |

改动面（4 改 2 增）：

| 文件 | 变更 |
|---|---|
| `.github/workflows/ci.yml` | backend job 新增 `Provider failure-rate gate self-test (fixture)` step（三态断言） |
| `.github/workflows/replace-desktop-assets.yml` | R2 步骤补 `if:` 门控 + base-url 取变量 + 应急通道注释 |
| `.github/workflows/desktop-windows.yml` | R2 步骤 base-url 取变量（对齐） |
| `tests/test_ci_gate_wiring.py` | **新增**（9 条契约） |
| `tests/fixtures/run_samples/` | **新增**（8 个真实形状 run，共 47KB） |

## 7. 遗留风险与需人工确认事项

1. **fixture 会随真实数据形态演进而过时**：`build_run_profile` 若改变读取字段，
   fixture 需要同步重新裁剪。`test_run_sample_fixture_matches_real_shape` 会在画像
   算不出来时红，但**字段语义漂移**（例如新增一个影响成败判定的字段）不会被它抓
   到。重新生成 fixture 的做法见 §2.1 的裁剪表。
2. **阈值 15 是 fixture 专用值**，不构成对供应商健康度的建议。改 fixture 就要重算
   三态断言里的 15 和 1。
3. **`--require-sample` 仍无「真实数据」使用者**：本轮接的是自检场景。若将来做
   artifact 聚合，这条 step 与那条链路共存，不要互相顶替。
4. **High-IL 跑法必须用 Windows 反斜杠路径 + `py.exe` + PYTHONPATH**（PROJECT_INFO
   平台注意事项 9），本轮照做得到 1969/11/0。
5. **插件仓推进必须刷新本仓锁**（R42 纪律）：本轮插件仓零提交，
   `official-plugins.lock.json` 无需刷新。
6. **`F:\DeterminFlow x2` 路径含空格**：本轮未碰 Rust 构建，无影响。

## 8. 下一轮候选

1. **CI e2e**（R45 §8-3 / R43 §2.3 选项 B）：仍需先决定模型凭据方案——桩 provider
   （不依赖 secrets，fork PR 可跑，但只验编排）或仅手工触发（判真实模型，PR 无覆盖）。
2. **错误分类顺序复核**（本轮 §5-2 发现）：`stream_stall` 的 `stream|chunk` 模式会
   先于 `connection` 命中，导致 `peer closed connection` 被归到别的桶。分类是启发式，
   但顺序可以更合理（越具体的模式越先匹配）。工作量小，且能提升失败率时间序列的
   可解释性。
3. **闸门判真实数据**（R45 §2.4 artifact 路线）：若真实数据面变得重要，退出码 3 与
   本轮 step 都已就位，只需加聚合步骤。
4. **画像跨 run 对比视图演进**（R45 §8-5）：R43 基础版之上的展示面演进，风险最低。
5. **循环节点与重试语义区分**（R41 §9-3）：需后端 Core 配合，用户已确认继续挂着。

其余：POSIX 真跑已由 CI 覆盖（R43 结论），大陆下载加速维持现状（R44 结论）。

## 9. 本轮未实际运行

- **未在 CI 上验证新 step**：本机无 GitHub Actions，只能本地等价实跑 shell 逻辑
  （三态已验证）。真实 runner 上的 yml 解析与环境变量展开交给推送后的 CI 日志。
- **未重启 8021 服务**：改动面不含后端运行时代码。
- **未跑 `docker build`**：本机仍无 docker/wsl（R43/R44/R45 复核仍不可用）。

## 10. 补记：推送与 CI 全量核对（当轮执行）

推送 `93c1e03..c8f7c13`，`origin/main` 已同步。

### 10.1 xs2 `CI` run 40666712534（`c8f7c13`）五 job 全绿

| job | 结果 | 数据 |
|---|---|---|
| `frontend` | success | 463 passed / 0 fail |
| `container-config` | success | `docker compose config -q` |
| `backend`（ubuntu-24.04） | success | **1916 passed / 64 skipped**（95.25s） |
| `container-build` | success | 构建 + 冒烟全过 |
| `windows-backend` | success | **1951 passed / 29 skipped**（209.16s） |

**四口径总数均为 1980**：ubuntu 1916+64、windows 1951+29、本机 Low-IL 1884+96、
High-IL 1969+11 —— 与 §4 双基线逐项对齐，零未解释差异。

### 10.2 新 step 在真实 runner 上跑通，三态全部命中

这是本轮**唯一**能在真实 CI 上验证的改动，日志取证（`backend` job 第 7 步
`Provider failure-rate gate self-test (fixture)`，conclusion=success）：

```
[gate] 总失败率 11.67% 未超出阈值 15.0%（60 次尝试）
OK  阈值 15 未超阈  exit=0
[gate] 总失败率 11.67% 超出阈值 1.0%（60 次尝试）
OK  阈值 1 触发闸门  exit=1
[gate] 无 run 样本（attempts=0），跳过失败率闸门（阈值 15.0%）
[gate] --require-sample: 一个 run 样本都没有，闸门未生效（退出码 3，检查 data/workflows 是否存在）
OK  无样本时闸门显式失败  exit=3
```

`${{ github.workspace }}` 展开、`env` 传递、fixture 路径命中（60 次尝试说明
`DETERMINFLOW_DATA_DIR` 确实指到了入库 fixture）全部成立——§5-1 记录的未验证面
已闭合。

### 10.3 `Desktop Windows` run 40666712618（同 sha）：首跑 Full 失败，重跑全绿

首跑结果：`Build core NSIS installer` success，**`Build full NSIS installer` failure**。

**排除本轮回归**：`desktop-windows.yml` 的改动只落在 `release` job 的 env
（`R2_PUBLIC_BASE_URL`），而该 job 在本 run 里是 skip 的；`Build full NSIS
installer` 完全不读这个变量。逐行 diff 见 §6 改动表。

**真实根因**（诊断 artifact `installer-diagnostics-full` 的 `backend-console.log`）：

```
[src.web_server] INFO: Web 服务 初始化完成，主会话: ac02b561
[uvicorn.error] INFO: Application startup complete.
[uvicorn.error] ERROR: [Errno 10048] error while attempting to bind on address
    ('127.0.0.1', 55786): only one usage of each socket address (protocol/network
    address/port) is normally permitted
[uvicorn.error] INFO: Waiting for application shutdown.
```

即后端**初始化全部完成、在最后 bind 端口时失败**，随后自行关闭；而
`smoke_installer.ps1:214` 的就绪探测（180 秒窗口、每次 2 秒超时）因此一直读不到
200，抛出 `Installed DeterminFlow backend did not become ready`。

**机制**：`desktop/src-tauri/src/backend.rs:244` 的 `reserve_local_port()` 是
「`TcpListener::bind(("127.0.0.1", 0))` 拿到一个空闲端口号 → **listener 随函数
返回被 drop（端口释放）** → 把号码通过 `--port` 传给后端 → 后端重新 bind」的
**TOCTOU** 设计。两步之间任何进程占走该端口，后端就 bind 失败。该函数出自
`96b0a3c`（v1.0.2 之前），**不是本轮引入**。

**判定为 flake 而非确定性缺陷**：① 同 run 的 Core 版通过（Core 与 Full 走同一份
后端启动路径）；② 重跑同一 job（`run_attempt=2`）**success**，未改任何代码。

**留下的问题（下一轮候选）**：这个 TOCTOU 窗口在 CI runner 上命中率不低
（同日 `f9a1340` 那次 Full 也失败，但根因是插件锁，不同问题）。彻底修法是让
Rust 端用 `SO_REUSEADDR` + 重试，或把端口分配改为「后端自己选并在 stdout 上报
实际端口」，从根上消掉「先释放再复用」的两步。

### 10.4 本轮未复现的历史失败

`f9a1340`（01:21）的 Full 失败日志显示是另一回事：`50 passed, 1 skipped` 后
进入 `refresh_official_plugin_lock.py --check` 阶段——即 R42 记录的插件锁脱钩，
与本轮无关，也未在本轮出现。
