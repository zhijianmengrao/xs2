# DeterminFlow (xs2) 交接报告 — Round 77（元数据不是 JSON：4 不是 1/3/8）

> 本轮定位：R76 §7-3 挂的账——`check_per_workflow_rate` /
> `check_per_workflow_regression` 的**坏 JSON 分支**没有用例。
> 落地形态：**测试 + 登记**；`scripts/` 与 `src/` 一行未动（闸门 md5 不变）。

## 1. 一句话结论

R72/R73/R76 把「退出 4 / 退出 3」两道门接到了判决与报告上，但它们造的元数据
**全是合法 JSON**，坏也只坏形状（R75 §9）。于是 `json.loads` 抛异常这条分支在
三条判据上都没有用例，而两种改法在既有 2328 条上**全绿**：

- **读不懂就按内容重算**——元数据问题（处置是重导）被翻译成「判了且不合格」；
- **读不懂当空元数据继续**——退出码从 4 变成 3；回归那条还会把「上一轮基线
  丢了」说成「只有当前这一轮」（退出 0）。

本轮用 #4 / #3 各自的**边界外计数**把这条分支钉住：先证明元数据可读时它确实
说话，再把元数据换成 `{not json` 看它闭嘴；另在 CLI 层钉「退出 4，不是 8」。

## 2. 为什么 8 是这一格最容易冒充的码

`main()` 用 `_run_judgement` 包判据，它把 `ValueError` 归成 **8（判据算术
失败）**——而 `json.JSONDecodeError` 正是 `ValueError` 的子类。判据里那条
`except (OSError, ValueError)` 一旦被删，进程就从 **4** 变成 **8**：

| 改法 | CLI 退出码 | 读的人会去做什么 |
|---|---|---|
| 现状 | 4 | 重导快照（正确） |
| 删掉内层 `except` | **8** | 查判据算术（错误） |
| 换成 `EXIT_NO_SAMPLE` | 3 | 重导更多 run（错方向：数据没缺，是文件坏了） |

8 是 R75 §9 记的三种冒充（1 / 3 / 8）里唯一还没在坏 JSON 上钉过的一种。

## 3. 设计

1. 复用 R72 的 `_write_rate_snapshot` 与 R73 的 `_write_regression_snapshot`
   造落盘快照，走各判据的真实入口（读盘 → 形状校验 → 漂移 → 报告 → 退出码）。
2. `test_unparseable_metadata_is_not_a_verdict_for_the_leave_one_out_rate`
   两格：
   - **控制组**：rest 30/0 + target 4/10（#4 的边界外）→ 硬门槛退出 1、
     消息有「1 个超出」；
   - **坏 JSON**：同一份内容 + `{not json` → `fail_on_exceeds` 两种取值都退出
     4，消息含「无法解析」、不含「超出」「报告模式」。
3. `test_unparseable_metadata_is_not_a_verdict_for_the_per_workflow_regression`
   两格：上一轮 2/79、当前 16/79（#3 的边界外）→ 退出 1；换成 `{not json` →
   退出 4，消息不含「判回归」「退出码 1」。
4. `test_unparseable_metadata_exits_four_from_the_cli`（参数化两条判据）：
   同一个坏快照分别走 `--check-per-workflow-rate` /
   `--check-per-workflow-regression`，`main()` 必须返回 4。
5. 模块 docstring 补 R77 一段；登记页新增 §7.5、§6 加一行。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/test_judgement_flip_points.py` | **+65 / −0** | 2 条用例 + docstring |
| `tests/test_live_snapshot_gate.py` | **+22 / −0** | 1 条参数化用例（2 个参数） |
| `docs/JUDGEMENT_LEDGER.md` | **+33 / −0** | §6 一行 + 新增 §7.5 |
| `docs/PROJECT_INFO.md` | **+1 行** | R77 轮次条目 |
| `docs/HANDOVER_ROUND77.md` | 新增 | 本文 |

**闸门脚本 md5 未变**：`1d0e0ac027f3732fad7586cf81ac05fa`（R75/R76 之后的值）。
`src/` 与前端零改动。

## 5. 变异验证（七次，`cp` 备份还原）

跑的是全部相关用例（基线 **203** = R76 的 199 + 本轮 4）：

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | rate：坏 JSON 返回 `EXIT_NO_SAMPLE`（3） | **2 failed** | 函数级 + CLI（rate） |
| 2 | rate：坏 JSON 按内容重算（说出判决） | **2 failed** | 函数级 + CLI（rate） |
| 3 | rate：`except` 只捕 `OSError`（ValueError 漏到 `_run_judgement`） | **2 failed** | 函数级 + CLI（rate） |
| 4 | regression：坏 JSON 返回 `EXIT_NO_SAMPLE` | **2 failed** | 函数级 + CLI（regression） |
| 5 | regression：坏 JSON 当「只有当前这一轮」（退出 0） | **2 failed** | 函数级 + CLI（regression） |
| 6 | regression：消息里先写「退出码 1 的来源」 | **1 failed** | **函数级（唯一）** |
| 7 | rate：退出码不变，消息里先写「1 个超出（报告模式）」 | **1 failed** | **函数级（唯一）** |

每次还原后 `md5sum` 与备份逐字节相同（`1d0e0ac027f3732fad7586cf81ac05fa`）。

**如实记录**：M1–M5 上函数级与 CLI **同时判红**，CLI 用例**不是唯一咬合者**
——它的价值是把外部退出码钉住（M3 下函数级只表现为抛异常，CLI 才是「以 8
退出」这个可观测结果），而不是多发现一种改法。唯一咬合只有 M6/M7，都是
「退出码不变、消息里先写出判决词」那一类。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`-k "unparseable"`（flip points） | **2 passed** |
| 定向：`-k "unparseable"`（live gate） | **2 passed** |
| 相关集：msys + ledger + flip points + live snapshot gate | **203 passed**（5.96s，基线复跑） |
| 全量（本机，Low `S-1-16-4096`） | **2219 passed / 113 skipped / 0 failed**（138.18s，最终代码复跑） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（闸门不在 e2e 链路；CI 会跑 container-build） |

**对账**：总用例 **2328 → 2332**（+4；`test_judgement_flip_points.py` 20 → 22、
`test_live_snapshot_gate.py` 169 → 171）。Low `2219+113` = **2332**。

**工作树外来改动**：`config/skills_config.json`（+146 / −2，他人新增
skill 条目）**保持未提交**，提交用显式路径 add。

## 7. 未做与未验证的事（如实记录）

1. **只钉了「读不懂」这一格**：`snapshot-meta.json` 是目录而非文件、权限拒绝
   等 `OSError` 分支仍无用例（同一条 `except`，但注入方式不同）。
2. **`history` 里的畸形条目仍由 `_history_entry_counts` 跳过并计数**（R58 起），
   不进判决；本轮没有触碰（R76 §7-1 同一条挂账）。
3. **`check_per_workflow`（诊断）的坏 JSON** 已由 R76 覆盖，本轮不重复。
4. **本会话仍只有 Low profile**：28-skip 未复现。
5. **未重导**：`data/` 下 `run-*.json` 仍 **40 个**，最新 `2026-10-28 08:34`
   （本轮实查；`tests/fixtures/live_snapshot` 里是 28 个 run 文件、
   `exported_at=2026-10-30T09:26`，保鲜判据比的是「快照滞后真实数据」，
   当前滞后为负，未到期）。
6. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。

## 8. 下一轮候选

1. **重跑率的跨 run 趋势**（R74 §8-3）：存储位置已拍定（随被判数据入库、
   快照式），但「每轮由谁追加」仍未定（本机跑 e2e 时追加 / CI 回写仓库），
   要动 `scripts/` + 新历史文件 + 可能动 `ci.yml`。
2. **`history` 畸形条目纳入判决**（R58 起的缺口）：需先定处置（只报告 /
   计入退出 4 / 连续畸形轮提示重导），会动 `scripts/`。
3. **重导快照 / `p=1.0` 真实数据**：**继续挂账**，每轮查一次 run 数。
4. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile
   的路径，风险最高（可能动 shell 正在用的命名对象）。
5. **`snapshot-meta.json` 的 `OSError` 分支**：本轮 §7-1 的同型缺口，成本低
   （只差一个注入方式：把 meta 写成目录）。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 提交、推送与 CI 核对

**本轮未提交、未推送**：用户未就推送选项作答，按「先本地、等确认」执行——
改动全部停在工作树（3 个改动文件 + 本文 + `_r77_mutate.py` /
`_r77_gate_backup.py` 两个辅助文件）。CI 面（ubuntu / windows 计数、五 job、
容器冒烟）本轮**无实证**。

工作树里另有他人的 `config/skills_config.json`（+146 / −2）未提交，与本轮无关；
将来提交时须用显式路径 add，不要带上它。
