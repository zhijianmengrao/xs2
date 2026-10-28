# DeterminFlow (xs2) 交接报告 — Round 42（维护轮：首次推送 CI 全量核对收口 + 失败率硬闸门 + 死通道依赖收尾）

> 本轮定位：R41 §8-1 积压推送（用户授权）首次真实触发 CI 全量核对，
> 暴露出**四条从未在本地被发现的红**，全部取证修复；同时落地 R41 §9-1
> （失败率告警闸门）与 §8-2 的 updater 死通道收尾（用户选定 + 授权自行装
> 工具链）。
> 基线：`f9a1340`（R41 文档尾）→ 本轮 xs2 提交 6 个、插件仓 1 个。

## 1. 推送与 CI 全量核对（R41 §8-1，用户授权）

两个仓库积压共 30 个提交推上去（xs2 26 个 → `0ce4607..f9a1340`；插件仓 4 个 →
`1b42dec..1504a88`），推送本身顺畅（走已打通的 GCM + socks5 传输）。

**CI 结果：xs2 `windows-backend`（权威）绿、`frontend`/`container-config` 绿，
`backend`（ubuntu）红；插件仓连红 3 次；xs2 `Desktop Windows` 红。**
逐条取证如下——四条都不是本轮改动引入，是积压期间潜伏的缺陷。

### 1.1 xs2 ubuntu `backend` 红：c19 设备名用例平台错配

`test_novel_full_flow_round34.py::test_c19_write_text_rejects_unsafe_paths`
的 `[references/NUL]` 与 `[references/tail. ]` 两个参数化用例在 Linux 上失败
（`assert 200 in (403, 422)`）。

**根因不是产品缺陷**：`safe_target` 调的 `unsafe_windows_path` 在 POSIX 上
**按设计返回 None**——设备名重定向与尾随点剥离都是 Windows 文件系统语义，
POSIX 上它们是合法普通文件名（`src/web/path_guard.py` 与
`src/core/win_names.py` 的 docstring 都写明了这一点）。测试把这两条平台专属
断言和跨平台断言混在同一个 parametrize 里，在 Linux 上必然与实现契约相反。

**修复**：拆成两条用例——跨平台四条（`../escape.md` / `references/../../escape.md`
/ `/abs.md` / `C:/Windows/x.md`）保留原断言；Windows 专属两条加
`skipif(os.name != "nt")` 并写明原因。与仓库既有 `IS_NT` 门控风格一致，
ubuntu 跳过、windows-backend 仍真实执行。本机实跑 36 → **38 passed**。

### 1.2 插件仓 CI 连红 3 次：残留 job + Core 仓地址不存在

`ci.yml` 从 `3c8ff4e` 起就一直红，但此前无人核对。取证（GitHub API + 用
GCM 存的自有 token 拉 job 日志）得到两个独立缺陷：

1. **残留 job**：`bishu-novel` 和 `public-api` 两个 job 仍在，而 `1b42dec`
   已把这两个插件从仓库删除 → job 在 `actions/checkout@v4`（step 3）失败。
2. **Core 仓地址不存在**：所有 job 用 `${{ github.repository_owner }}/DeterminFlow`
   拼 Core 仓，但本仓是 fork（owner = `zhijianmengrao`），该 owner 下没有
   `DeterminFlow` → checkout 必然失败。

**修复**：删两个 job，`publish-registry` 的 needs 改指唯一存活的
`xs2-novel-flywheel`；Core 仓改 `vars.CORE_REPOSITORY || 'alikon-art/DeterminFlow'`
（默认指向真实存在的上游，需要指向别处时用仓库变量覆盖）。顺带修两处同源问题：
`--source-url` 原硬编码上游插件仓、改为 `${{ github.repository }}`（签名登记的
规范源必须与客户端实际拉取的源一致）；`.gitignore` 的 `/pytest-of-*/` 只锚定
根目录、漏掉插件子目录下的同名残留，补无前缀规则。

**本地按 CI 调用方式模拟验证**：Core 仓的 `requirements-dev.lock` /
`requirements.lock` / `validate_definition.py` / `registry_release.py` 四项
API 均 200；插件套件按 `PYTHONPATH=<core>` 跑 **98 passed**；
`validate_definition.py` 对 14 个 workflow 全部 `[PASS]` exit 0；
`ci.yml` 经 `yaml.safe_load` 通过。

### 1.3 xs2 `Desktop Windows` 红：官方插件构建锁脱钩

红在「Verify latest official Plugin lock for Full candidate」步骤：

```
locked=1b42dec7f5d1…, latest=1504a8816c9e…
```

桌面 Full 构建锁仍钉在插件仓迁移前的旧提交。**这不只是 CI 形式问题**——锁
决定 Full 版实际捆绑哪个插件快照，旧锁意味着打出的安装包捆绑 0.1.13 而不是
已发布的 0.1.16。刷新后 version `0.1.13→0.1.16`、commit 前进；随后插件仓 CI
修复提交（`74b7ddc`）推上去 HEAD 又前进，锁再跟一次（机制预期行为，内容版本
仍 0.1.16，只更新 commit 指针）。

**教训**：插件仓推进后必须同步刷新本仓锁，否则桌面分发与插件发布脱钩。
这一条已写进 §7 遗留风险第 1 项。

## 2. 失败率告警闸门 `--fail-if-above`（R41 §9-1）

`--summary` 的周期化口径已在 R41 落地，本轮补上**可判定的闸门**，让「人工比对
时间序列」升级为能挂 CI/shell `&&` 链的硬闸门。

### 设计要点（每条都有对应测试钉死）

| 决策 | 理由 |
|---|---|
| 判据用 **TOTAL 口径**（failed 之和 / attempts 之和） | 逐 workflow 平均会让「1 次尝试」的小 workflow 与大样本等权。反例：200 次 40 失败 + 1 次 0 失败 = 19.9%，逐行平均只有 10% |
| **严格大于**才触发（阈值 5.0 表示 5.0% 通过） | 卡在阈值上算通过，否则回落一档就红 |
| 比较用**未舍入**比值 | 先 `round(4)` 会把 1/3 = 33.3333% 舍成 33.33 与阈值 33.33 判平 |
| 空样本 `failure_rate=None` 且**诚实放行** | 「无数据」不等于 0% 也不等于 100% |
| 结论写 **stderr** | stdout 的表格与 `--json` 是机器可读出口，不得被结论行污染 |
| 阈值越出 0..100 由 argparse 显式拒绝 | 单位是百分比，静默接受 150 会得到永远绿的假闸门 |

### 测试（`test_provider_failure_profile.py` 5 → 10）

| 用例 | 断言 |
|---|---|
| `test_gate_triggers_only_strictly_above_threshold` | 5/100 @5.0 通过、6/100 @5.0 触发、0/100 @0.0 通过 |
| `test_gate_compares_unrounded_ratio` | 1/3 @33.33 判超出，展示字段仍是 0.3333 |
| `test_gate_uses_pooled_rate_not_per_workflow_average` | 40/201 = 0.199 @15.0 触发（逐行平均 10% 会误判通过） |
| `test_gate_honest_on_empty_sample` | 空 rows 与「有行无尝试」都放行且 reason 含「无 run 样本」 |
| `test_gate_reason_states_both_numbers` | 结论文案同时含实测值与阈值 |

### 真实数据实跑（非合成）

| 命令 | 结果 |
|---|---|
| `--summary --fail-if-above 0.1` | `[gate] 总失败率 2.88% 超出阈值 0.1%（243 次尝试）` → **exit 1** |
| `--summary --fail-if-above 5` | `[gate] … 未超出阈值 5.0% …` → **exit 0**，stderr 与 stdout 分离 |
| `--summary --json --fail-if-above 0.1` | stdout 仍是可 `json.load` 的纯 JSON（9 行），stdout 无结论行 |
| `--fail-if-above 150` | argparse 拒：`需在 0..100 之间（单位是百分比）` |

## 3. updater 死通道收尾（R41 §8-2，用户选定）

### 3.1 现状核实：R2/Gitee 早已彻底移除

先核对事实再动手：`5732d53`（v1.0.2 单源化）已经把 `updater.rs` 里的
`R2_UPDATE_ENDPOINT`、`GITEE_LATEST_RELEASE_API`、`plan_update_sources`、
`join3` 全部删除，`tauri.conf.json` 的 `endpoints` 只剩本仓 GitHub Releases
一条，`choose_update` 与 `fallback_rid` 机制保持 fail-closed。
**R29 记录的「保留为死通道」在 v1.0.2 已经收尾，本轮无活可清。**

### 3.2 但发现真正的遗留：3 个孤儿依赖

逐文件核实（`src/*.rs` + `build.rs`）确认 `futures-util`、`reqwest`、`semver`
**零引用**——它们只服务于已删除的多源并发探测（`join3` + semver 比对 + 自建
HTTP 请求）。移除后 `Cargo.lock` 相应删 3 行；`tauri-plugin-updater` 自身仍
会引入所需传递依赖，功能面无变化。

### 3.3 工具链自行安装 + 编译验证（用户授权）

本轮首次具备 cargo 环境：装 **Rust 1.99.1**（`rustup-init.exe` 走 10509 HTTP
代理下载，`--profile minimal --no-modify-path`；MSVC BuildTools 2022 本机已有）。

`cargo check` 过程中发现**两个必须记录的环境前提**（都不是代码缺陷，但会让
后来者卡住）：

1. **项目路径含空格 → ring 的 C 编译失败**。cc-rs 传给 `cl.exe` 的 `-Fo` 参数
   是未加引号的 `-FoF:\DeterminFlow x2\...`，路径里的空格让它解析失败，错误
   只表现为 `cl.exe` exit code 2、**stderr 空**（极易误判成工具链没装好）。
   实测：手动用同样参数编译 `curve25519.c` 是 exit 0（`-Fo` 后加引号即可），
   差别全在引号。绕过方式：`CARGO_TARGET_DIR` 指到无空格路径（本轮用
   `C:\zt-r42`）。
2. **build.rs 要求两个产物目录存在**：`desktop/generated/bundled-plugins`
   （`stage_official_plugins.py` 产出）与 `desktop/runtime/backend`
   （`build_backend.py` 冻结后端产出）。本地只做 `check` 时用占位目录即可，
   验证后已清理（`desktop/generated/` 本就在 `.gitignore` 里）。

**验证结果：`cargo check` exit 0**（`Finished dev profile`，依赖图里
`tauri-plugin-updater v2.10.1` 等全部 Checked 通过）。清理时同时还原了
build 期自动改写的 `permissions/autogenerated/*.toml`（仅 CRLF/LF 差异，
内容不变）。

## 4. 供应商失败率时间序列（第 2 个数据点）

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

**与 R41 逐行完全一致**——本轮未产生新 run（纯维护轮，未做实跑），说明口径
稳定、时间序列可比。R41 → R42：2.9% → 2.9%。

## 5. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | `2406359` `feat(scripts)` | 失败率告警闸门 `--fail-if-above` + 测试 5→10 |
| xs2 | `971958a` `test(novel)` | c19 设备名/尾随点用例按平台分档（修 ubuntu 假红） |
| xs2 | `1f68c4c` `chore(desktop)` | 移除死通道遗留的 3 个孤儿依赖 |
| xs2 | `bb3af56` `fix(desktop)` | official-plugins.lock 刷新到插件仓 HEAD |
| xs2 | `c995746` `fix(desktop)` | lock 跟随插件仓再次推进到 74b7ddc |
| xs2 | 本文档提交 | 交接文档 + PROJECT_INFO R42 条目 |
| plugins | `74b7ddc` `ci` | 删除残留 job + Core 仓地址改真实仓库 + source-url/gitignore |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性，
与前几轮一致）。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：挖矿闸门 | **10 passed** |
| 定向：c19 分段后 | **38 passed** |
| 定向：桌面锁/打包 | **36 passed / 1 skipped** |
| Low-IL 全量 | **1838 passed / 96 skipped / 0 failed**（102.02s） |
| High-IL 全量（权威） | **1923 passed / 11 skipped / 0 failed**（135.83s） |
| 插件套件（双 CWD） | **98 passed / 0 failed ×2** |
| 前端 8 组 | **457 passed / 0 fail**（零改动） |
| 前端 lint / build | 0 problems / ✓ 5.88s |
| 存储名审计 | **[clean]** exit 0 |
| 索引污染复查 | **59 条，零 pytest 污染**，与 R40/R41 完全一致 |
| Rust | `cargo check` **exit 0**（Rust 1.99.1 + MSVC BuildTools 2022） |

对账：Low 1833 + 5(闸门) = **1838** ✓；High 1918 + 5 = **1923** ✓。
总用例 R41 口径 1929 → **1934**（High passed+skipped：1923+11）。

## 7. 遗留风险与需人工确认事项

1. **插件仓推进必须刷新本仓锁**（本轮新增纪律）：`official-plugins.lock.json`
   必须等于插件仓当前 main，否则 Desktop Windows CI 会红、且打出的 Full 包
   捆绑旧版插件。凡推送插件仓，随后就要在 xs2 跑
   `python desktop/scripts/refresh_official_plugin_lock.py` 并提交。
   **本轮为了修 CI 已经两次刷新（bb3af56、c995746），这是机制预期而非返工。**
2. **CI 日志接口需 token**：`/actions/jobs/{id}/logs` 对匿名请求返回 403
   「Must have admin rights to Repository」。本轮用 GCM 里已存的自有 token
   （`git credential fill` 取，Authorization: Bearer）才拉到日志。
   后续排 CI 若只拿到注解（annotations 无正文），按此方式取。
3. **代理通道分流**：socks5 口 10808 对 TLS 连接不稳（curl/requests 都
   `RemoteDisconnected`），但 **HTTP 口 10509 稳定**——GitHub API、rustup
   下载都走它。git 传输仍用 socks5 且正常。
4. **High-IL 跑法必须用 Windows 反斜杠路径**：本轮首次用 Git Bash 的正斜杠
   拼 PYTHONPATH，131 个模块收集期 `ModuleNotFoundError`。正确写法见
   PROJECT_INFO 平台注意事项 9，需 `F:\...\site-packages;F:\...\win32;…`
   （反斜杠 + 分号）。
5. **`F:\DeterminFlow x2` 路径含空格会挡 Rust 构建**：见 §3.3 第 1 条。
   要跑 `cargo build/check` 必须设 `CARGO_TARGET_DIR` 到无空格路径。
6. **POSIX 真跑 / 大陆下载加速**：R32 起状态未变，分别需容器环境与外部基础
   设施决策（T2 类）。本轮用户只选了 updater 死通道（已收尾）。
7. **服务进程托管**：仍须 `powershell Start-Process -WindowStyle Hidden`
   脱离会话启动（R40 §7.5 纪律，本轮未重启服务故未复验）。

## 8. 下一轮候选

1. **把闸门挂进 CI**（低工作量）：`--fail-if-above 5` 已可用，可在
   `windows-backend` job 末尾加一步。但需先决定：CI 克隆不含运行期
   `data/workflows`，该步骤在 CI 上只会得到「无 run 样本 → 诚实放行」，
   等于空转。若要真正生效，需改为在**有真实数据的机器**上跑（或把 run
   记录作为 artifact 上传后聚合）。这一权衡留给下一轮决策。
2. **画像跨 run 对比视图**（R41 §9-2，中等工作量，纯前端）：抽屉内加
   「与上一次 run 对比」列。
3. **循环节点与重试语义区分**（R41 §9-3，需后端 Core 配合）：
   `attempt_history` 区分「循环第 N 轮」与「第 N 次重试」。

其余：POSIX（待环境）、大陆下载加速（待基础设施决策）。

## 9. 本轮未实际运行

- **未重启 8021 服务**：本轮后端改动只有脚本与测试，服务进程未受影响，
  故未做活体走查（R40/R41 的活体纪律在有后端行为变更时才需要）。
- **未跑完整 `cargo build`**：只做了 `cargo check`（编译验证依赖移除后代码
  仍健全），未产出 NSIS 安装包——完整打包需 PyInstaller 冻结后端 + NSIS，
  属发版流程，与「验证依赖移除无副作用」这一目标不成比例。
