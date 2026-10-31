# DeterminFlow (xs2) 交接报告 — Round 71（msys skip 的归因：判据先被判据自己吞掉）

> 本轮定位：R70 §8 的 #4「会话级 msys 状态的判定」，用户拍定 **A1+B1**：
> 只改归因措辞 + 留可复现判据（A1），不追 `\BaseNamedObjects` 对象 ACL 的
> 根因（B1，R70 §7-1 继续挂账）。
> 基线 `749e609`（R70 补记）。落地形态：**仅测试基础设施 + 文档**，
> 生产代码零改动。

## 1. 一句话结论

旧 skip 文案把 113 skips 归因于「Low 令牌」——R70 已证明 High 下同样发生。
本轮把文案改成只写机制（挂不上共享对象），并为这条归因判据补了 5 条用例。
**但真正的产出是变异验证第一次跑出的假绿**：新用例判红时，断言消息里带着
`NtCreateDirectoryObject`，`conftest` 的钩子按签名把它转成了 skip——「判据发现
了错误」在输出里长成「环境不可用」，与 R66 那个「只可能误报的闸门」同型。

## 2. 最重要的一件事：判红的用例被钩子自己吞成 skip

第一轮变异验证（6 个变异）的结果长这样：

| 变异 | 期望 | 第一轮实测 |
|---|---|---|
| 1 `_msys_skip_reason` 退回旧文案（Low 令牌） | 文案用例红 | **0 failed / 183 passed / 1 skipped** |
| 2 探针退化成「clone 失败就算环境坏」 | 边界用例红 | 1 failed ✓ |
| 3 判据丢掉模块白名单 | 真值表用例红 | 1 failed ✓ |
| 4 悄悄放宽模块集合 | 集合用例红 | 1 failed ✓ |
| 5 机制写对、但仍开「High-IL 能修好」的处方 | 文案用例红 | **0 failed** |
| 6 拿掉 `no_msys_skip` 豁免 | 豁免用例红 | （此时尚无该用例） |

变异 1/5 的 `1 skipped` 就是答案：用例**确实红了**，但 `pytest_runtest_makereport`
把它的 `AssertionError` 消息扫了一遍，里面带着 `NtCreateDirectoryObject`
（断言消息会打印被检查的字符串），签名命中 → `report.outcome = "skipped"`。
所以「判据发现错误」与「环境不可用」在 pytest 输出里变成同一行，过程序上不可区分。

修法：`no_msys_skip` 标记（`pyproject.toml` 登记），带标记的用例失败时钩子原样
返回；`tests/test_msys_attribution.py` 整模块标记，并新增一条用例直接驱动钩子，
把「未标记 → skipped / 标记 → failed」两格都钉住。修完后六个变异全部咬合。

**教训（R66 同型，第二次）**：一个防护若会把「它要发现的失败」转换成别的状态，
它就不是防护。写钩子必须问：**判红之后，输出长什么样？**

## 3. 设计

1. **文案**（`_msys_skip_reason`，从钩子里抽出成纯函数）：
   `msys git transport cannot attach this session's shared msys-2.0 object
   (matched NtCreateDirectoryObject boot signature | unattributable inside a
   git-transport module); retry from a launcher that can attach
   \BaseNamedObjects\msys-2.0* (see PROJECT_INFO.md platform note 9)`。
   刻意不含 `integrity`，也不再写「改用 High-IL」——R70 会话里 High 同样被挡。
2. **判据抽取**（`_msys_skip_applies`，纯函数，行为逐字不变）：
   `signature_hit or (module in _GIT_TRANSPORT_MODULES and transport_blocked)`。
   两个自变量，令牌 IL 不是第三个。
3. **5 条用例**（`tests/test_msys_attribution.py`）：
   文案判据 / 真值表 / 探针边界（同一条 clone 失败，仅 stderr 不同必须翻转）/
   模块集合逐字 / 豁免机制本身。钩子对模块集合的调用保持短路：非传输模块
   不会触发探针（行为不变）。
4. **登记页**：§1 新增「环境型」、§2 新增 #11、§6 五条复核、§7 的「无数字
   容忍量」名单加上 #11、新增 §8（R70 四行矩阵 + 判据真值表 + skip 的代价）。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/conftest.py` | **+60 / −19** | 注释改准、`_msys_skip_reason`/`_msys_skip_applies` 抽取、`no_msys_skip` 豁免 |
| `tests/test_msys_attribution.py` | 新增（5 条） | 归因与判据边界 |
| `pyproject.toml` | **+1 行** | `no_msys_skip` 标记登记 |
| `docs/JUDGEMENT_LEDGER.md` | **+55 / −3** | §1/§2/#11/§6/§7/§8 |
| `docs/PROJECT_INFO.md` | **+17 / −1** | 平台注意事项 9 的 R71 更正 + 轮次条目 |
| `docs/HANDOVER_ROUND71.md` | 新增 | 本文 |

**生产代码零改动**：`scripts/check_live_snapshot_gate.py`（`7a329d3a…`）、
`scripts/e2e_workflow_stub.py`（`a5104e69…`）与 R70 记录逐字节相同。

## 5. 变异验证（六次，`cp` 备份还原）

跑的是**全部相关用例**（`test_msys_attribution` + `test_judgement_ledger` +
`test_judgement_flip_points` + `test_live_snapshot_gate`，基线 185）：

| # | 变异 | 实测（修好豁免之后） |
|---|---|---|
| 1 | 文案退回「Low-integrity token」 | 1 failed：文案判据用例 |
| 2 | 探针改成「clone 失败即环境坏」 | 1 failed：探针边界用例 |
| 3 | 判据丢掉模块白名单 | 1 failed：真值表用例 |
| 4 | 集合里偷偷加 `test_plugin_longpath` | 1 failed：模块集合用例 |
| 5 | 机制正确但加「High-IL 能修好」 | 1 failed：文案判据用例 |
| 6 | 拿掉 `no_msys_skip` 豁免 | 1 failed：豁免机制用例 |

每个变异恰好 1 红、且是对应的那一条；还原后 `cp` 覆写，conftest md5
`2ac012df1b74aedbdb208d19a6711989` 与备份逐字节相同，定向 **185 passed**。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 全量（本机，High 令牌） | **2279 passed / 28 skipped / 0 failed**（150.47s） |
| 全量（本机，**真降到 Low** `S-1-16-4096`，进程内回读确认） | **2194 passed / 113 skipped / 0 failed**（131.17s） |
| 定向：msys + ledger + flip points + live snapshot gate | **185 passed**（5.81s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（零生产代码改动） |

**对账**：总用例 **2302 → 2307**（+5）。High `2279+28` = 2307、Low `2194+113` = 2307。

### 6.1 28-skip profile 在本会话**又回来了**（与 R70 相反，如实记录）

R70 记录「High 也是 113 skips、28-skip 复现不出来」；本轮同一台机器、同一份
代码，**High 令牌跑出 2279/28**（R69 的权威 profile），**真降 Low 跑出
2194/113**。两轮相隔约 20 小时，生产代码 md5 未变。

这是「113 skips 是会话状态、不是 IL 的函数」的**第二个观测**，方向与 R70
相反：对象能不能挂接会自己变（谁先创建/挂接了那个共享对象、DACL 如何），
与令牌 IL 无关。五个新用例在两种 profile 下都通过（探针用例自己 monkeypatch
`subprocess.run`，不依赖现场状态）。

**未追根因**（B1）：`\BaseNamedObjects\msys-2.0S…` 的 ACL 为什么会话间变化，
没有做跨会话对照实验。

## 7. 未做与未验证的事（如实记录）

1. **没有追 msys 对象 ACL 的根因**（B1 拍定）；§6.1 只记录两次方向相反的观测。
2. **skip 不等于通过**：113 条在 Low 下没有执行；本轮只保证归因不再说假话。
3. **探针仍每进程只跑一次**（缓存）；同一进程内环境变化不会被重新探测。
4. **模块白名单仍是 6 个硬编码名字**：改名/新增传输模块需要同时改用例与登记页。
5. **未跑 e2e / docker build / npm run build / 未重启 8021**：零生产与零前端改动。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
7. **重导仍被数据卡住**：`data/workflows/*/runs/run-*.json` 仍是 **40 个**，
   最新 `run-dfe789fd.json` 仍是 `2026-10-28 08:34`（本轮实查）。

## 8. 下一轮候选

1. **有新 run 后再重导**：唯一被外部数据卡住的候选，已连续多轮。
2. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
3. **重跑频率的可观测性**（R68 §7-4）：重跑真的频繁出现时，该改的是容差。
4. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：本轮按 B1 未做；若要复现
   稳定 profile，这是唯一路径，但可能动正在被 shell 使用的命名对象。
5. **留一法基线的元数据漂移路径**（R70 §7-3）：把 `check_per_workflow_rate`
   的 3/4 两条退出路径与翻转点串起来。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

推送 `724218e`（两次提交：`1e9b466` test + `724218e` docs；一次 `git push`，
`749e609..724218e`，经 socks5 10808）。

| run | 触发 commit | 结果 |
|---|---|---|
| **41204197201** | `724218e` | 五 job 全部 `success`，**一次通过、无重跑**（13:08:15 → 13:12:05，约 3m50s） |
| — | `Desktop Windows` | **未触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`（`head_sha=724218e…` 下 `total_count=1`） |

| 项 | 实证（下载日志解码后逐字比对，不是推断） |
|---|---|
| 五个 job | backend（13:10:52）/ windows-backend（13:12:05）/ frontend（13:09:55）/ container-config（13:08:23）/ container-build（13:08:55）全部 `success` |
| 用例数（ubuntu） | `2242 passed, 65 skipped, 1 warning in 112.19s` = **2307** |
| 用例数（windows） | `2278 passed, 29 skipped, 1 warning in 174.03s` = **2307** |
| 新用例在 CI 上真跑 | ubuntu 2238/64 → **2242/65**（4 pass + 探针用例按设计在 POSIX skip）；windows 2273/29 → **2278/29**（5 条全 pass） |
| 校准步骤照旧 | `OK  逐 workflow 提前量已复算（本步不作判定）` |
| e2e | `[e2e] 10/10 场景通过`（只 ubuntu 有；windows 日志里 `e2e_workflow_stub` 出现 **0** 次） |
| 前端 | `# pass` 合计 **490**、`# fail` 合计 **0**（8 个块：48/60/137/81/139/1/18/6） |
| 容器 | `container-config` success；`container-build` 真跑 `buildx build`（GHA cache）+ `容器镜像冒烟全部通过: determinflow-core:ci` |

**四面一致**：本机 High `2279+28` = 2307、本机真降 Low `2194+113` = 2307、
ubuntu `2242+65` = 2307、windows `2278+29` = 2307。

**取证方法（本轮新增两个坑）**：
1. `actions/jobs/<id>/logs` 仍需认证（未认证 403）；但 302 到 Azure blob 后
   **SAS URL 自带签名，再带 `Authorization` 会 401**（`Server failed to
   authenticate`）——跳转后的请求必须去掉认证头。
2. **Low-IL 的 Python 里 `git credential fill` 会拉起 msys `sh`，直接撞上
   `NtCreateDirectoryObject: 0xC0000022`**（本机 venv 在 F: 盘即 Low）——这正是
   本轮登记的那条判据在 pytest 之外的现场例证。取 token 要在 Git Bash 里做，
   经环境变量传给下载脚本。
3. 302 后先 `-r 0-0` 读 `Content-Range` 总长（backend 137968、windows 77144、
   frontend 222133、container-config 9875、container-build 78847），再按 48KB
   分块 Range 拼接；五份实到字节数与总长逐字节相等。
