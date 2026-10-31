# DeterminFlow (xs2) 交接报告 — Round 69（判据容忍量的翻转点：把「数字等于常量」升级成「数字是判决的边界」）

> 本轮定位：R65 §9-5「判据全景登记的迁移验证」（挂账 4 轮：R65 起）。
> 基线 `0daed11`（R68 收尾：Low 2177/113/0、High 2262/28/0（权威）、
> 总用例 2290、前端 490/0）。落地形态：**主线 = 翻转点验证**；
> **范围 = 主线 + 两个默认值具名 + 幅度判据抽成纯函数**；
> **收尾 = 照常推送 + 五 job 逐字核对**。

## 1. 一句话结论

`test_judgement_ledger.py` 钉的是「登记页的数 == 代码里的常量」。这还不够：同一
个容忍量在代码里还有一个**没被钉住**的属性——它是**开区间还是闭区间**（`>` 还是
`>=`）。阈值一点没动、常量完全相等，只把比较符改一个字，「恰好等于容忍量」的那
一侧就翻面了。本轮给登记页上每个带数字的容忍量加了一条**翻转点**用例：边界内
必须通过、边界外必须判失败，并用覆盖守卫保证「有数字 ⇒ 有翻转点」。

## 2. 最重要的一件事：先把预期摆正——阈值已有人守，边界没人守

（本节初稿写错过一次，如实留在这里。）

初稿的说法是「把阈值写成 `基线 + margin * 2`，所有既有用例都看不出来」。实跑
之后**不成立**：这个变异会让既有用例红 **6 条**（R62 的 3 条判决用例 + R67 的
3 条提前量用例）。

| 变异 | 既有 232 条用例（e2e stub 64 + 登记页 5 + gate 163） | 翻转点用例 |
|---|---|---|
| 阈值 `基线 + margin` → `基线 + margin * 2` | **6 红**（含提前量表 16→8） | 3 红 |
| 形状 `deviation > over_tol` → `>=` | **全绿**（232 passed） | 1 红 |
| 幅度 `extra < 0.7` → `<=` | 全绿 | 1 红 |
| 新鲜度 `lag > max_lag_days` → `>=` | 全绿 | 1 红 |

所以 R69 的真实增量是**后三行**：比较符的一字之差（开/闭区间）**没有任何既有
用例覆盖**——而这三种恰好都是真实数据会正撞上的点：「恰好 0.30s 的抖动算不算
超睡」「恰好 7.0 天算不算过期」「恰好多出 0.700s 算不算等过」。7.0 天尤其现实：
它是每次重导都可能落在整数值上的边界。

**教训（又一次「文档会替判据吹牛」，R63）**：论证一个新用例的价值时，必须把
变异跑在**全部**相关用例上，而不是只跑新用例；否则「只有它能发现」这句话本身
就没有依据。

## 3. 覆盖范围：登记页 §2 里每个带数字的容忍量

| # | 判据 | 边界内（通过） | 边界外（判失败） |
|---|---|---|---|
| 1 | 政策上限 8 个百分点 | n=255, k=28 | k=29 |
| 2 | 合并层回归 +3 | 基线 10/255, k=25 | k=26 |
| 3 | 逐 workflow +10 | character 15/79 | 16/79 |
| 4 | 留一法 +10 | 基线 0/30, k=3/10 | 4/10 |
| 5 | 样本量 margin 10 | 零失败 29 次尝试 | 28 次 |
| 6 | 新鲜度 7 天 | 滞后 7.0 天（含恰好 7.0） | 7.1 天 |
| 8 | 形状 −0.05 / +0.30 | −0.050 / +0.300 | −0.051 / +0.301 |
| 9 | 幅度 0.7s | extra 0.700s | 0.699s |

**三个没有被翻转点覆盖的量，如实写在登记页 §7**：2.64 个百分点（入库快照的
95% 半宽）是测量结果不是容忍量；0.4s（形状相邻配置差）由场景配置决定且
`judgeable` 已写成不等式；3 次（连续 undetermined 提示）不改变退出码。

**两侧都测**：只测「边界外」会漏掉 `>` 写成 `>=` 这种一字之差（它把「恰好
0.30s」的抖动判红）；只测「边界内」会漏掉阈值被整体挪走。§5 的第 2/3/4 条
变异各自只被边界的一侧咬住——这三条变异在既有 232 条用例上**全绿**（§2 表）。

## 4. 设计

1. **新测试模块 `tests/test_judgement_flip_points.py`**（10 条）：每个判据一条
   翻转点用例 + 一条覆盖守卫。阈值一律取自代码常量（`REGRESSION_MARGIN`、
   `DEFAULT_MARGIN`、`DEFAULT_MAX_LAG_DAYS`、`UNDER_SLEEP_TOLERANCE`、
   `OVER_SLEEP_TOLERANCE`、`BACKOFF_EXTRA_MIN_SECONDS`），不写第二份字面量。
2. **覆盖守卫** `test_every_numeric_tolerance_has_a_registered_flip_point`：
   解析登记页 §2 的容忍量列，**出现数字的行**必须在本文件登记一个用例，且用例名
   必须出现在登记页 §7——「有数字」与「有翻转点」互为充要，两个方向都查。
3. **两个默认值具名**：`DEFAULT_MARGIN = 10.0`、`DEFAULT_MAX_LAG_DAYS = 7.0`，
   `main()` 与翻转点用例共用同一个数（原先 10 只写在 `main()` 的字面量里）。
4. **单点幅度判据抽成纯函数**：`BACKOFF_EXTRA_MIN_SECONDS = 0.7` +
   `_backoff_amplitude_problems(samples)`。写在场景函数里时，「0.700 通过 /
   0.699 失败」这两个点只能靠真机碰运气。
5. **登记页 §7「翻转点」**：表格 + 三个未覆盖面 + 指向用例名。

### 4.1 一个差点犯的错（如实记录）

给 `--margin` 的默认值具名时，最自然的写法是 `default=DEFAULT_MARGIN`。但
`main()` 里有一句

```python
if options.margin is not None and not chosen:
    parser.error("--margin 只用于 --check-* 判据；…")
```

`--margin` 的 `None` **不是「没有默认值」，而是「用户没有显式给」**。改成非
`None` 默认之后，所有默认判定模式（`--fail-if-on-regression` 不带 `--margin`）
都会在参数层直接报错——CI 的六步里就有这种调用。这处陷阱由既有用例当场抓住，
最终保留 `default=None` + `margin = DEFAULT_MARGIN if … is None else …`，
帮助文字用 f-string 插常量。

**教训与 R66 同型**：一个值同时承担「默认值」与「是否显式给出」两个含义时，
把默认值挪进声明的写法会静默改变语义——而它看起来只是「把魔数提成常量」。

## 5. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | **+11 / −3** | `DEFAULT_MARGIN` / `DEFAULT_MAX_LAG_DAYS` 具名并接进 `main()` 与帮助文字 |
| `scripts/e2e_workflow_stub.py` | **+25 / −6** | 幅度判据抽成 `_backoff_amplitude_problems` + 常量 `BACKOFF_EXTRA_MIN_SECONDS` |
| `tests/test_judgement_flip_points.py` | **新增 223 行** | 10 条：8 个翻转点 + 默认值 + 覆盖守卫 |
| `docs/JUDGEMENT_LEDGER.md` | **+32 / −0** | 新增 §7「翻转点」 |

## 6. 变异验证（五次全部咬合，`cp` 备份还原）

| 变异 | 期望 | 实测 |
|---|---|---|
| `_rate_verdict` 阈值改成 `baseline + margin * 2` | #2/#3/#4 三条必须掉 | **3 failed**（翻转点模块内；既有用例另有 **6 红**，见 §2） |
| 形状超睡侧 `>` 改成 `>=` | 边界内那一条（+0.300）必须掉 | **1 failed**（`shape_tolerances_flip_on_both_sides`） |
| 幅度 `extra < 0.7` 改成 `<=` | 边界内那一条（0.700）必须掉 | **1 failed**（`backoff_amplitude_flips_at_the_registered_minimum`） |
| 新鲜度 `lag > max` 改成 `>=` | 「恰好 7.0 通过」必须掉 | **1 failed**（`freshness_flips_at_the_registered_days`） |
| 登记页 §7 里改掉一个用例名 | 覆盖守卫必须掉 | **1 failed**（`every_numeric_tolerance_has_a_registered_flip_point`） |
| 还原后 | 全绿 | **10 passed**；三个 md5 与备份逐字节相同（gate `7a329d3a…`、stub `a5104e69…`、ledger `935a0d61…`） |

还原用 `cp` 备份覆写，不用 `git checkout --`（R55 教训）。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2187 passed / 113 skipped / 0 failed**（131.75s） |
| High-IL 全量（权威） | **2272 passed / 28 skipped / 0 failed**（147.59s） |
| 定向：`test_judgement_flip_points.py` | **10 passed**（0.2s） |
| 定向：`test_live_snapshot_gate.py` + `test_judgement_ledger.py` | **168 passed** |
| 定向：`test_ci_e2e_stub.py` | **64 passed** |
| e2e 全量 | 未重跑（stub 只做了纯函数抽取，`tests/test_ci_e2e_stub.py` 覆盖；R68 的 10/10 仍适用） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |

**对账**：总用例 **2290 → 2300**（+10）。
Low `2187+113` = 2300、High `2272+28` = 2300。

## 8. 未做与未验证的事（如实记录）

1. **翻转点不是「判决的统计性质」**：它只证明阈值在比较里被**原样使用**，
   不证明 3 个百分点 / 8 个百分点这些数选得对——后者属于 R61 的校准
   （`docs/failure-ceiling-calibration.md`）与 R67 的提前量，不在本轮。
2. **#4（留一法）只测了 `_rate_verdict` 那一层**：它的基数是「其余 workflow 的
   合并失败率」，由 `per_workflow_baselines` 算；那条基线单独有 R56 的用例，
   本轮没有把它与翻转点串起来。
3. **#6 的「恰好 7.0 天」依赖 `total_seconds()` 的浮点**：测试用的是整点时间戳，
   没有覆盖「6 天 23 小时 59 分 59.999 秒」这种贴边输入。
4. **未重跑 e2e**：`_backoff_amplitude_problems` 是纯抽取，行为等价；但严格说
   「抽取没改行为」只有单测与 R68 的 CI 10/10 作为间接证据。
5. **未跑 `docker build` / `npm run build` / 未重启 8021 服务**：改动是离线脚本、
   测试与文档。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
7. **R60~R63 的重导仍被数据卡住**：`run-*.json` 仍是 40 个，最新
   `run-dfe789fd.json` 仍是 `2026-10-28 08:34`。

## 9. 下一轮候选

1. **有新 run 后再重导一次**（R60 §7-1 起的直接后续）：本机已 5 天没有新 run，
   这是唯一被数据卡住的候选。
2. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照（合成路径已有
   `live_snapshot_exceeds` 覆盖）。
3. **#4 留一法基线与翻转点的串联**（本轮 §8-2）：把「其余 workflow 合并基线」
   也算成一条可翻转的量，防止有人给留一法换一套阈值。
4. **贴边浮点**（本轮 §8-3）：`total_seconds()` 的边界在毫秒级是否稳定，可以
   用 7 天 ±1 微秒的输入钉一次。
5. **重跑频率的可观测性**（R68 §7-4）：如果 CI 上重跑开始频繁出现，说明容差
   已经贴着环境抖动边界，那时要改的是容差而不是继续加重试。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定，CI 不写回仓库）。

## 10. 推送与 CI 核对

推送 `446ff30`（`5d6256e` R68 CI 补记 + `446ff30` R69 代码/用例/登记页/交接文档，
**一次** `git push`）。

| run | 触发 commit | 结果 |
|---|---|---|
| **41188162422** | `446ff30` | 五 job 全部 `success`，**一次通过、无重跑**（09:18:32 → 09:23:24，约 4m52s） |
| — | `Desktop Windows` | **未触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/` |

| 项 | 实证（下载日志解码后逐字比对，不是推断） |
|---|---|
| 五个 job | backend / windows-backend / frontend / container-config / container-build 全部 `conclusion=success` |
| 用例数（ubuntu） | `2236 passed, 64 skipped, 1 warning in 109.21s` = **2300** |
| 用例数（windows） | `2271 passed, 29 skipped, 1 warning in 227.30s` = **2300** |
| 四面一致 | 本机 Low `2187+113` = 2300、本机 High `2272+28` = 2300、ubuntu `2236+64` = 2300、windows `2271+29` = 2300 |
| 新模块在 CI 上真跑 | 两个 runner 都跑全量套件，`test_judgement_flip_points.py` 在内且全部通过（用例数从 2226/64 涨到 2236/64，正好 +10） |
| 校准步骤照旧 | `OK  逐 workflow 提前量已复算（本步不作判定）` |
| e2e | `[e2e] 10/10 场景通过`（只 ubuntu 有；windows 日志里 `e2e_workflow_stub` 出现 **0** 次） |
| 前端 | `# pass` 合计 **490**，`# fail` 合计 **0** |
| 容器 | `container-config` 与 `container-build` 均 `success` |

**取证方法**：`actions/jobs/<id>/logs` 302 到 blob 主机后整段 GET 会超时，先
`-r 0-0` 读 `Content-Range` 得总长（backend 137799、windows 76986、frontend
222122），再按 48KB 分块 Range 拼接；三份实到字节数与总长逐字节相等。

### 10.1 本轮文档自己在推送后被改过一次（如实记录）

`446ff30` 里的 §2 初稿写着「阈值 ×2 时既有 168 条用例全绿」——那是我只跑了翻转点
模块得出的结论。推送后补跑全部相关用例，发现既有用例会红 **6 条**，于是 §2 被
重写成「阈值已有人守、边界没人守」的准确版本。修订随补记提交推送，其 run 只用于
确认五 job 绿，不再回填（R66 的纪律）。**这条也写进 §2 的教训里**：论证价值时
变异必须跑在全部相关用例上。

