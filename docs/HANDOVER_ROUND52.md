# DeterminFlow (xs2) 交接报告 — Round 52（退避形状验证 + Windows 侧闸门 + 全失败信号 + 快照重导）

> 本轮定位：R51 §12 的候选 3（退避形状）作主线，附加三项由用户拍定一并做
> （Windows runner 接样本量闸门、更强运维信号徽章、重导 live 快照）。
> 收官走「双基线 + 推送 + CI 核对」。
> 基线：`24b4cf2`（R51 收尾，Low 1969/96/0、High 2054/11/0、前端 478/0）。

## 1. 四项的共同线索：判据的「另一半」

四条改动看起来互不相干，但它们补的是同一类空缺——**已有判据各自漏了同一侧**：

| 改动 | 已有判据回答的 | 缺的那一半 |
|---|---|---|
| 退避形状 | 「配的 1.2s 等到了吗」 | 「两段之间的增量对不对」（恒定/递增/递减不可分） |
| Windows 侧闸门 | 「在 ubuntu 上判得到」 | 「换一个平台还判得到吗」 |
| 全失败信号 | 「失败率在上升吗」 | 「现在是不是一直全挂」 |
| 快照重导 | 「三个判据都绿」 | 「样本够厚到判据还有判定力吗」 |

第三行是本轮最有价值的一条，见 §4。

## 2. 退避形状验证（R52-A，主线）

### 2.1 R51 那个场景为什么判不到形状

R51 的 `retry_backoff_is_honoured` 是**单点幅度**判据：配 `delays=[1.2]`，量到多等
1.21s，判「Core 的 delays 被等过」。它对形状完全失明：

| 配置 | 单点判据 | 真实语义 |
|---|---|---|
| `[0.4, 0.8]` | 「某个值被等过」✓ | 指数退避 |
| `[0.4, 0.4]` | 「某个值被等过」✓ | 恒定轮询 |
| `[0.8, 0.4]` | 「某个值被等过」✓ | 倒着来（配置写错） |

三种配置在单点判据下都合格，而它们的运维含义完全不同。更根本的是：**只有一次
失败时序列里只有一个退避段**，第二段根本不存在，形状无从谈起。

### 2.2 桩需要「失败两次」

新增标记 `[stub:fail_twice]`。改这一处时发现旧的配额实现有结构性问题：
`claim()` 用 `set` 记「这个键见过没有」，天然只能表达「一次」。改成计数：

```python
def claim(self, key, budget=1) -> bool:
    used = self._claims.get(key, 0)
    if used >= budget:
        return False
    self._claims[key] = used + 1
    return True
```

`_FAIL_BUDGETS = {"[stub:fail_once]": 1, "[stub:fail_twice]": 2}`，`decide()` 的
返回值里 `fail_once: bool` 相应换成 `fail_budget: int`（0 = 恒失败）。这是一处
**接口变更**，`tests/test_ci_e2e_stub.py` 里断言 `fail_once` 的两处随之更新。

### 2.3 判据用比值，不用绝对差值

```python
if second < first * 1.5:  # 配置 0.4 → 0.8，恒定给 1.0，递减给 0.5
    → 判不合格
```

为什么是比值：JIT 预热、日志、调度抖动会让两段**同时**偏移一个共模量。绝对差值
会被这个不可知量吞掉，只能取很松的阈值，于是「退避被改成一半」也能绿。比值对
共模偏移不敏感，而恒定（1.0）与递减（0.5）仍被 1.5 的门槛分开。

`_backoff_segments(stub, floor=0.2)` 先把「退避段」从所有间隔里挑出来：工具结果
回来后的收尾请求间隔通常只有几毫秒，混进来会让形状判断失真。该阈值只区分量级
（毫秒 vs 数百毫秒），不承担判据。

### 2.4 实测

```
[e2e] PASS retry_backoff_shape_is_honoured: 退避形状符合配置 [0.4, 0.8]：实测 [0.41, 0.816]
[e2e] 8/8 场景通过
```

与配置吻合到 0.02s 内。总耗时 0.4+0.8=1.2s，与 R51 那个场景同量级，CI 预算不变。

### 2.5 没做什么

不判 3 段及以上的形状（`[0.4,0.8,1.6]` 会引入约 2.8s 真实等待），不判真实 120s
级退避（属压测画像地盘），不判**跨 attempt 的递减/恒定**是否正确——那需要另一个
「只失败 3 次」的标记，而当前判据已经覆盖了最要紧的一类回归（把递增写成恒定）。

## 3. Windows runner 接样本量闸门（R52-B）

### 3.1 补的缺口

R51 §10-1 记录：`Snapshot sample-size gate` 只在 ubuntu-24.04 的 `backend` job 上跑，
`windows-backend` 没有。判据只用 `math` 与四则运算，看起来与平台无关——**但那正是
单环境验证最容易漏掉的地方**。stderr 编码、路径分隔、浮点格式化任一隐含假设，都
只在另一个 runner 上才显形。

### 3.2 PowerShell 写法的一个真问题

`windows-latest` 默认 shell 是 `pwsh`，其默认 `$ErrorActionPreference = 'Stop'`。
这条规则会把**非零退出码的原生命令**包成 `NativeCommandError`——而反向验证恰恰
要求被测脚本**故意**以 7 退出。不处理的话，这一步会在判据正常工作的时候红。

所以脚本第一行显式降级：

```powershell
$ErrorActionPreference = 'Continue'
...
$null = python scripts/check_live_snapshot_gate.py ... --margin 2 2>&1
$strict = $LASTEXITCODE   # 紧跟命令取，中间不放别的语句
```

这比恒绿更难排查：恒绿至少说明「没判」，而**红灯指向错误的东西**会把人引向
「闸门坏了」。有专门测试钉住这两点（`$LASTEXITCODE` 与 `Continue` 都在）。

### 3.3 本地验证的局限（如实记录）

本机没有 `pwsh`（只有 Windows PowerShell 5.1）。用 `powershell -NoProfile` 跑同一段
逻辑，双分支结论正确（默认 0 / margin 2 → 7）；但 5.1 与 pwsh 7 在 `$LASTEXITCODE`
与错误流处理上不完全一致，**最终确认只能靠 GHA 上的实跑**（§9.1）。

## 4. 「最近 N 次全失败」信号（R52-C）— 本轮最有价值的发现

### 4.1 `trend` 判据在这个形状上是瞎的

`compare_run_baseline` 判 `regressing` 的口径是：最近 2 次**相邻失败率差值全部 > 0**。
现在设想一个每次都 100% 失败的工作流：

| run | attempts | failed | failure_rate | 相邻差值 |
|---|---|---|---|---|
| run-a | 10 | 10 | 100% | — |
| run-b | 10 | 10 | 100% | 0 |
| run-c | 10 | 10 | 100% | 0 |
| run-d | 10 | 10 | 100% | 0 |

差值恒为 0 → 不满足「全部 > 0」→ 判 **`stable`**。

也就是说：**最难处理的运维状况（这么多天一直在全挂）在趋势字段里显示为「稳定」。**
这是 R45/R46/R47 反复批评的那类盲区的一个新具体形状——判据只回答了「有没有在
变坏」，没回答「现在是不是全坏」。

### 4.2 解法：正交的第二个信号

```python
FAILURE_STREAK_REQUIRED = 3

def failure_streak(points, required=FAILURE_STREAK_REQUIRED) -> dict:
    consecutive = 0
    for point in reversed(points or []):
        if str(point.get("status") or "") != "failed":
            break
        consecutive += 1
    return {"consecutive_failed": consecutive,
            "required": required,
            "all_failed": required > 0 and consecutive >= required}
```

三个刻意的取舍：

1. **只认 `failed`**。`stopped` 是人工停止，`running`/`pending` 还没结论。把它们
   算进连续失败，会让「我手动停了一个任务」变成运维告警。
2. **`required=0` 永不成立**。配置成 0 不该等于「一律告警」——这是「永远红的
   告警」与「永远绿的防护」互为镜像的那个坑。
3. **单独成字段，不并进 `trend`**。R51 §10-7 已经因为「两个指标混进一个 trend
   会让退步语义变糊」拒绝过耗时趋势，这是同一理由的第二次实例。字段放在同一个
   `baseline` 块里，因为它要的正是这条时间序列，另开一次目录扫描没有意义。

### 4.3 那条「正交性」测试是这一节的全部

```python
def test_all_failed_signal_is_invisible_to_trend_by_design():
    baseline = compare_run_baseline(_failed_profile("run-d"), [...abc 全失败])
    assert baseline["trend"] == "stable"     # 前提：趋势判不出问题
    assert baseline["failure_streak"]["all_failed"] is True
```

两个断言缺一不可。只断言后者，这个测试就退化成「信号会报警」；两个一起断言，它
钉住的是**「这两个字段互补」这个设计事实**——将来若有人「顺手」把全失败并进
`trend`（那样 `trend` 就会变成 `regressing`），前一个断言会红。

### 4.4 前端

任务历史里新增徽章 `data-all-failed`，文案「连续 N 次全失败」，门槛 N 由后端给
（`all_failed_required`），前端不重算——两处阈值迟早漂移。它与 `data-trend` 徽章
**各自独立**：一条任务可能同时挂两个，也可能只挂后一个（正是 §4.1 那个形状）。

## 5. 快照重导（R52-D）

### 5.1 为什么改 `--limit` 而不只是重导

R51 §10-2 挂账：快照停在 `--limit 2`，187 次尝试 / 7 失败 / 3.74% / 半宽 2.72。
重导时先量了三个候选：

| limit | runs | 尝试 | 失败 | 失败率 | 半宽 | 体积 |
|---|---|---|---|---|---|---|
| 2（旧） | 18 | 187 | 7 | 3.74% | 2.72 | 188KB |
| 3 | 23 | 243 | 7 | 2.88% | **2.10** | — |
| 5（采用） | 28 | 255 | 10 | 3.92% | **2.38** | 280KB |

**limit 3 不能用**：它的半宽 2.10 贴 CI 反向验证的门槛（要求 > 2 才能触发退出码 7）。
再厚一点点，`--margin 2` 就不再触发 7，那一步会从「能红的判据」退化成恒绿——而
它看起来还在跑、还在打印 OK。

这是一个值得记住的耦合：**快照变厚会让 CI 的反向验证失去判定力**。判据本身没错
（半宽变小是好事），但反向验证所依赖的「2 个百分点够不够」这个前提变了。选 limit 5
是让半宽留出余量（2.38 距 2 有 0.38 的空间），同时在 §9 记下这个约束。

### 5.2 重导后复核

- 三条判据：失败率 3.92% ≤ 13.9% ✓、样本量 2.38 ≤ 10 ✓、覆盖 9/9 ✓
- 双分支：默认 exit 0 / `--margin 2` exit 7 ✓
- `tests/test_live_snapshot_gate.py` 38 条全绿——说明它们都按快照自身推导
  （`test_threshold_is_derived_from_the_snapshot` 直接比数字），没有写死旧值

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_ci_e2e_stub.py` | **30 passed**（23 → 30） |
| 定向：`test_live_snapshot_gate.py` | **39 passed**（34 → 39） |
| 定向：`test_run_profile.py` | **52 passed**（45 → 52） |
| 收齐后 `--collect-only` | **2084 tests collected** |
| Low-IL 全量 | **1988 passed / 96 skipped / 0 failed**（120.60s） |
| High-IL 全量（权威） | **2073 passed / 11 skipped / 0 failed**（137.47s） |
| 前端 `npm test` | **479 passed / 0 fail**（478 + 1） |
| 前端 `npm run build` | **通过**（5.51s） |
| 本机 e2e | **8/8 场景通过** |

**对账**：

- Low-IL：R51 1969 **+19** = **1988** ✓
- High-IL：R51 2054 **+19** = **2073** ✓
- 总用例 R51 口径 2065 → **2084**（+19）
- 新增 19 条构成：`test_run_profile.py` 7 + `test_ci_e2e_stub.py` 7 +
  `test_live_snapshot_gate.py` 5。零删除。

### 6.1 High-IL 一次假红（已排除，值得记）

首次跑 High-IL 有两条 `test_core_default_resources.py` 失败：

```
ModuleNotFoundError: No module named 'aiofiles'
```

根因不是代码：这两条测试在 `cwd=tmp_path` 的子进程里跑验证器脚本，而我的
`PYTHONPATH` 用的是**相对路径** `.venv/Lib/site-packages`——子进程换了 cwd 之后
相对路径就指向了不存在的位置。换成绝对路径后 11 passed。

这与本项目反复记录的 CWD 回落问题是同一个根因家族。**High-IL 命令必须用绝对
`PYTHONPATH`**，这条已写进 §11 的正确命令里。

## 7. 变异验证（3 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| `all_failed` 恒 False | 红 | ✓ 3 红 |
| 把 `stopped`/`running` 当失败证据 | 红 | ✓ 1 红 |
| 删掉 Windows 步骤末尾 `exit 0` | 红 | ✓ 1 红 |

没有做「退避形状」那一侧的变异（比如把 1.5 倍门槛改成 1.0），因为它需要跑完整
e2e 才有意义，而契约测试钉的是「判据用了比值形式」这个结构性事实——实施变异
成本高于收益。这一点如实记下，不假装覆盖了。

另有第三个变异（§10.1 之后补做）：删掉 Windows 步骤末尾的 `exit 0` → **1 红**
（`test_windows_sample_size_step_ends_with_exit_zero`）。

## 8. 本轮改动一览（15 改 1 增 + 快照文件）

| 文件 | 变更 |
|---|---|
| `scripts/stub_llm_provider.py` | +~20 行：`FAIL_TWICE_MARKER`、`_FAIL_BUDGETS`、`fail_budget` 取代 `fail_once`、`claim(key, budget)` 改计数 |
| `scripts/e2e_workflow_stub.py` | +~115 行：`_backoff_segments`、`_install_retry_config` 提取、`retry_backoff_shape_is_honoured` 场景 |
| `.github/workflows/ci.yml` | +32 行：`windows-backend` 的 `Snapshot sample-size gate`（pwsh，双向验证） |
| `src/workflow/run_profile.py` | +~38 行：`FAILURE_STREAK_REQUIRED`、`failure_streak()`、baseline 块加 `failure_streak` |
| `src/web/workflow_routes.py` | +7 行：trend 块加三个全失败字段 |
| `web/src/types/index.ts` | +6 行：`TaskTrendBlock` 三个可选字段 |
| `web/src/components/workflow/runProfileView.ts` | +~20 行：`shouldFlagAllFailed`、`allFailedLabel` |
| `web/src/components/workflow/TaskHistoryPanel.tsx` | +11 行：`data-all-failed` 徽章 |
| `tests/test_ci_e2e_stub.py` | +7 条（含 `fail_once` → `fail_budget` 断言迁移、形状契约 6 条） |
| `tests/test_live_snapshot_gate.py` | +5 条（Windows 接线 4 + 末尾 `exit 0` 契约 1） |
| `tests/test_run_profile.py` | +7 条（全失败信号 + 正交性） |
| `web/src/components/workflow/TaskHistoryPanel.test.ts` | +1 条 |
| `tests/fixtures/live_snapshot/**` | 重导（18 → 28 个 run，meta 更新） |
| `docs/PROJECT_INFO.md` | 四节更新 + R52 双基线条目 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 9. 未做与未验证的事（如实记录）

1. **Windows 侧闸门只在本机 Windows PowerShell 5.1 上验过逻辑**，pwsh 7 的实跑
   结论靠 GHA（见 §10.1）。5.1 与 7 在错误流与 `$LASTEXITCODE` 上不完全一致。
2. **退避形状只验两段递增**：3 段以上、真实 120s 级、指数比例是否精确都不判。
3. **`FAILURE_STREAK_REQUIRED = 3` 是经验取值**：没有理论最优值。改它会同时影响
   后端判据与前端文案（文案里带 N），改一处即可，不需要动前端。
4. **全失败信号只看 `status`，不看失败原因**：一个「每天都被上游 401 拒」与一个
   「每天超时」在它眼里一样。要区分得另立判据，不是这个字段的职责。
5. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。本轮改了
   `src/web/` 与 `web/`，`container-build` job 会真构建并跑容器冒烟。
6. **未重启 8021 服务**：改动是新增只读字段与 CI 步骤，不涉运行时装配。列表趋势
   的真实数据验证用 TestClient + 临时目录完成。
7. **快照重导会让 CI 反向验证变脆**（§5.1 的耦合）：半宽越接近 margin 门槛，
   `--margin 2` 分支越可能不再触发 7。本轮 2.38 留了 0.38 余量，但这是一个
   **会随每次重导收紧的约束**，下一轮重导前应先算一遍半宽。
8. **未验 macOS/Windows 桌面构建**：本轮改了 `src/` 与 `web/`，按 paths 规则
   `desktop-windows.yml` 会被触发（见 §10.3）。

## 10. 推送与 CI 核对（本篇补记，2026-10-29）

推送 `fead4ea` 后触发两个 workflow（本轮改了 `src/`、`web/`、`scripts/`，
`desktop-windows.yml` 的 paths 过滤命中）。

### 10.1 第一次 CI 红：Windows 侧步骤的 pwsh 包装器坑（本轮最有价值的实证）

`CI` run **40801653541** 的 `windows-backend` job 在**我新加的那一步**上红。
日志里两个分支都判对了，也打印了 OK：

```
[live-gate] 快照样本量足够支撑失败率判定：失败率 3.92% 的 95% 半宽 2.38 个百分点≤ 余量 10.0（n=255, 失败 10）
OK  样本量判据双向生效（Windows/Python 3.14）：默认余量通过，余量 2 触发 7
##[error]Process completed with exit code 1.
```

**根因**：GHA 的 `pwsh` 包装器在脚本末尾追加 `exit $LASTEXITCODE`，而脚本最后
一条原生命令正是那次**故意**以 7 退出的反向验证。于是走到末尾的成功路径也被
透传成非零。

这正是本轮 §3.1 那条论断的活实例——**判据看着与平台无关，但平台的 shell 语义
把它弄红了**。而且它比恒绿更难排查：日志从头到尾都在说「判据是对的」。

修法（`3572cc2`）：末尾显式 `exit 0`，真正的失败仍由 `exit $code` / `exit 1`
提前退出。新增契约测试钉住末行（删掉它就红，已做变异验证）。

顺带修正一处本轮的认知：我原先以为只要把 `$ErrorActionPreference` 降成
`Continue` 就够了（那解决的是 NativeCommandError），但**末尾 exit 是另一件事**。
两个坑叠在同一个步骤里，只在本机 PowerShell 5.1 上验逻辑时都看不出来——
本机 `powershell` 不会替脚本追加 `exit $LASTEXITCODE`。

### 10.2 CI run 40802321401 —— 五 job 全绿

| job | 结论 |
|---|---|
| `backend` | **success** |
| `windows-backend` | **success** |
| `frontend` | **success** |
| `container-build` | **success** |
| `container-config` | **success** |

**新增的 Windows 侧第 7 步在 GHA 上真跑并通过**（Python 3.14.9 / pwsh 7）：

```
[live-gate] 快照样本量足够支撑失败率判定：失败率 3.92% 的 95% 半宽 2.38 个百分点≤ 余量 10.0（n=255, 失败 10）
OK  样本量判据双向生效（Windows/Python 3.14）：默认余量通过，余量 2 触发 7
```

ubuntu 侧（`backend` 第 9 步）输出同一个数字，**两个 runner 结论一致**。这同时
验证了重导后的快照（255/10/3.92%/半宽 2.38）与 §5.1 那个「半宽要留余量」的判断。

**e2e 在 GHA 上真跑 8/8 场景**，含本轮新增的形状场景：

```
[e2e] PASS retry_backoff_is_honoured: 退避生效：delays=0 → 0.01s，delays=1.2 → 1.20s（多 1.20s）
[e2e] PASS retry_backoff_shape_is_honoured: 退避形状符合配置 [0.4, 0.8]：实测 [0.403, 0.803]
[e2e] 8/8 场景通过
```

形状场景在 Linux runner 上量到 **`[0.403, 0.803]`**（本机 `[0.41, 0.816]`），
比值 1.99 vs 1.99——配置是 2.0。比本机还准一点，说明比值判据在两种平台都稳。

### 10.3 Desktop Windows run 40801653581 —— 双 NSIS success

| job | 结论 |
|---|---|
| `Build core NSIS installer` | success |
| `Build full NSIS installer` | success |
| `Publish GitHub Release` | skipped（不打 tag，预期） |

本轮改了 `src/workflow/`、`src/web/`、`web/`，paths 过滤命中，NSIS 构建真实执行。
（这个 run 跑的是 `fead4ea`，即修 CI 之前那个 commit——桌面构建与 CI 的
pwsh 问题无关，所以它当时就是绿的。）

## 11. 下一轮候选

1. **退避形状扩到 3 段**：`[stub:fail_thrice]` + `delays=[0.4,0.8,1.6]`，约 2.8s
   真实等待，仍在 CI 预算内。它能判出「第二段对了但第三段没跟上」这类只在长重试
   链上出现的回归。
2. **全失败信号的 workflow 级聚合**：当前是「每条任务」的信号。要在工作流列表上
   标「这个 workflow 最近 N 次全失败」，需要按 workflow 聚合（取最新 run 的
   `failure_streak`），语义与现状不同，是一次独立设计（与 R51 §12-1 的
   「趋势上到 workflow 列表」是同一类工作，可一起做）。
3. **`--check-sample-size` 加 per-workflow 判据**：R51 §12-2 的候选仍然有效。
   当前只判全局厚度，单个 workflow 很薄而全局够厚时看不出来。
4. **快照重导的半宽预算自动化**：§9-7 那个耦合可以做成导出脚本的一个检查——
   重导后若半宽 ≤ 1.6（离 margin 2 太近）就提示「CI 反向验证将失去判定力」。
5. **`sdk_max_retries` 的生产取值决策**：R51 §12-4 仍在，属生产重试行为变更。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）。
