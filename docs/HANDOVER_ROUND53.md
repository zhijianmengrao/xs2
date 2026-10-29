# DeterminFlow (xs2) 交接报告 — Round 53（三段退避形状 + 半宽预算 + 全失败退化点）

> 本轮定位：R52 §11-1 的候选 1（退避形状扩到 3 段）作主线，附加四项由用户拍定
> 一并做（快照半宽预算自动化、补验 macOS 桌面构建、复核 `FAILURE_STREAK_REQUIRED`、
> 评估 `sdk_max_retries` 生产取值）。收官走「双基线 + 推送 + CI 核对」。
> 基线：`170d6a2`（R52 收尾，Low 1988/96/0、High 2073/11/0、前端 479/0、8 场景 e2e）。

## 1. 本轮最重要的一件事：比例类判据的退化点在**两端**

主线（三段形状）按计划做完了，但本轮真正有价值的发现不在主线里，在附加项的
一次**测试写歪**里。

写「半宽预算」的测试时，我构造了一份「2 次尝试全失败」的临时样本，预期它
判合格，结果判了**不合格**——于是去查闸门的 `_failure_rate_precision`，发现：

```python
if failed > 0:
    p = failed / attempts
    half_width = Z_95 * (p * (1 - p) / attempts) ** 0.5   # p=1 时这里是 0
```

`p(1-p)` 在 `p=0` 与 `p=1` 时**都等于 0**。R51 补了 `p=0` 那一端（零失败时改用
单侧上界，否则「0/n 永远合格」），但 `p=1` 那一端一直漏着：

| 样本 | 修复前 | 修复后 |
|---|---|---|
| 2 次尝试 0 失败 | 不合格（R51 已修） | 不合格 |
| **2 次尝试 2 失败** | **「样本量足够」** | 不合格 |
| 10 次尝试 10 失败 | **「样本量足够」** | 不合格 |
| 30 次尝试 30 失败 | 「样本量足够」 | 合格（单侧距离 9.50 ≤ 10） |

后果不是「少报一个警」那么轻：闸门 `evaluate` 拿实测失败率当基线，一个 100%
失败的快照会让阈值封顶到 `min(100, 100+margin) = 100`，于是**永远不触发**。
最难处理的运维状况被判成「最健康的基线」。

这已经是同一个盲区家族的**第三个形状**了：

| 轮次 | 判据 | 漏的那一端 |
|---|---|---|
| R52 §4 | `trend` | 相邻差值为 0 → 全失败判 `stable` |
| R51 | `--check-sample-size` | `p=0` → 半宽 0 → 永远合格 |
| **R53** | 同上 | **`p=1` → 半宽 0 → 永远合格** |

三次都是「判据在退化点回落到恒真」。这不是巧合，是**比例类判据的结构性
问题**：点估计在 0 与 1 处方差为 0，任何基于正态近似的宽度都会塌成 0。写这类
判据时该问的第一句话是「p=0 和 p=1 时它还判得动吗」，而不是「中段够不够准」。

## 2. 三段退避形状（R53-A，主线）

### 2.1 两段判据抓不到的那一类回归

R52 §11-1 的判断是对的：两段场景（`delays=[0.4, 0.8]`、`max_retries=2`）能抓
「把递增写成恒定」，但抓不到**只在长链后段显形**的回归——

- 实现里 `delays` 只读前两项、第三项回落到默认值；
- 循环边界少一次，最后一段用错下标；
- 配置是 3 段但填充逻辑（`while len(delays) < max_retries`）把第三项补错。

这三种在 `max_retries=2` 下**完全不可见**，因为那时根本不存在第三段。

### 2.2 桩：加标记 + 一处顺带修正

`[stub:fail_thrice]`（配额 3）。改的时候发现 R52 留下的配额选择有隐患：

```python
# 之前：按键的插入顺序取第一个匹配
fail_budget = next(
    (budget for marker, budget in _FAIL_BUDGETS.items() if marker in markers), 0)
# 现在：取最大
fail_budget = max(
    (budget for marker, budget in _FAIL_BUDGETS.items() if marker in markers),
    default=0)
```

`[stub:fail_once][stub:fail_thrice]` 这种复制粘贴残留，取到 1 会让场景只失败
一次，形状判据看到「段数不够」——那是在报告一个**与真实原因不同**的缺陷。
取最大值让组合至少满足最长的那个要求，不会把配置笔误伪装成实现回归。

### 2.3 判据抽成共享函数

两段与三段如果各写一份「第二段 ≥ 第一段 1.5 倍」，短期没差别，长期必然漂移。
所以抽出 `_rising_shape_violations(segments, configured, min_ratio=1.5)`，两个
场景都调它。它判的是**每一对相邻段的比值**：

```python
for index in range(len(configured) - 1):
    first, second = segments[index], segments[index + 1]
    if second / first < min_ratio:  → 不合格
```

三段配置 `[0.4, 0.8, 1.6]` 于是被检查 1→2 与 2→3 两对。

### 2.4 实测（三处）

| 环境 | 实测段 | 比值 |
|---|---|---|
| 本机（首次） | `[0.408, 0.809, 1.618]` | 1.98 / 2.00 |
| 本机（复跑） | `[0.419, 0.806, 1.611]` | 1.92 / 2.00 |
| **GHA ubuntu** | **`[0.406, 0.806, 1.606]`** | **1.99 / 1.99** |

配置是 2.0。总等待 0.4+0.8+1.6 = 2.8s，仍在 CI 预算内（R52 §11-1 已算过）。

### 2.5 那个「段数不足」的分支不能默默通过

`len(segments) < len(configured)` 时返回一条明确的问题，而不是空列表。少一段
却判合格，正是「永远绿的防护」的入口——这条有专门测试
（`test_rising_shape_requires_one_segment_per_configured_delay`）。

## 3. 快照半宽预算检查（R53-B）

### 3.1 补的是哪半个缺口

R52 §9-7 挂账：快照越厚，半宽越小，而 CI 的反向验证要求半宽 **> 2.0** 才能
触发退出码 7。半宽一旦 ≤ 2，那一步从「能红的判据」退化成恒绿。R52 当时的
补救是「选一个余量够的 limit，并把它记进文档」——但那要求下一个人也记得算。

现在导出时就算：

```
[half-width] 所需余量 2.38 个百分点，距反向验证余量 2.0 只剩 0.38：
             仍能触发 7，但一次重导就可能越线
```

三档结论：

| 所需余量 | 结论 | 处置 |
|---|---|---|
| < 2.0 | 不合格（默认告警，`--strict-half-width` 时退出码 1） | 加大 `--limit` 重导 |
| 2.0 ~ 2.5 | 合格 + 告警「一次重导就可能越线」 | 留意 |
| > 2.5 | 合格 | 无 |

### 3.2 不自己算公式

第一版我让导出脚本自己实现了一遍半宽公式，然后在测试里断言「两处的数字相等」。
那仍然会分裂——两个公式各自演进时，测试只在你想起跑它时才红。

改成**直接问闸门**：把闸门的算术抽成 `sample_size_margin_needed(attempts, failed)`，
导出脚本 import 它。现在只有一个公式，不可能分裂。

### 3.3 判据方向相反，不能合并

`--check-sample-size` 要求「所需余量 ≤ margin」（样本够厚），半宽预算要求
「所需余量 > margin」（判据还能红）。**两者方向相反**，合并会让人看不懂该调大
还是调小 limit。这一点写进了两个函数的 docstring，也写进了测试。

### 3.4 导出脚本此前没有测试

R47 引入 `export_run_samples.py` 以来，它一直**零测试**——只靠「用过几次、
看起来对」。本轮新建 `tests/test_export_run_samples.py`（14 条），把两件事
钉住：

- **裁剪的正确性判据是画像逐字段相等**（含一条反向验证：抽掉
  `automatic_retry_count` 必须被判出来）；
- **半宽预算的边界与方向**（严格大于、余量档位、`--strict-half-width` 双向）。

## 4. `FAILURE_STREAK_REQUIRED = 3` 复核（R53-C）

### 4.1 结论：不改，但要钉住它与窗口的耦合

复核走了三步：

1. **语义边界**：`failure_streak` 只认 `failed`、`required=0` 永不成立——这两条
   R52 已有测试，无需改。
2. **取值理由**：取 2 意味着「上一次 + 这一次都失败」就报警，而单次失败在这类
   长流程里是常态（一次节点超时就让 run failed）。3 至少要求「连续两次重试机会
   都没救回来」。与 `TREND_STREAK_REQUIRED=2` 同量级但语义不同：趋势判方向，
   这条判当前状态。
3. **真正的问题**：门槛必须能被回溯窗口满足。时间序列长度由调用方的
   `baseline_limit` 决定（列表视图默认 5、上限 20），最多 `limit + 1` 个点。

### 4.2 新发现的一处脆弱耦合

`FAILURE_STREAK_REQUIRED` 在 `src/workflow/run_profile.py`，而 `baseline_limit`
的默认值在 `src/web/workflow_routes.py`。**两个数在不同文件里，谁改都碰不到
另一处**：

| `baseline_limit` | 可提供的点数 | 门槛 3 是否可满足 |
|---|---|---|
| 1 | 2 | **永不触发** |
| 2 | 3 | 刚好等于门槛 |
| 5（默认） | 6 | 有余量 |

新增 `test_failure_streak_threshold_fits_inside_the_default_baseline_window`
把这条约束写成断言。另加一条钉住「门槛随结果返回」（`required` 字段），
因为前端文案用的是后端给的 `all_failed_required`，前端不写死 N。

## 5. `sdk_max_retries` 生产取值评估（R53-D）

### 5.1 结论：维持生产不设

这一项是 R51 为**可观察性**加的（关掉 SDK 层才能量到 Core 的 `delays`）。
把它写进生产配置是另一件事——那会改变实际重试行为。

两层叠加的最坏情况：

| 配置 | 最坏请求数 | 最坏退避 |
|---|---|---|
| 默认（sdk 不设=2，core 3 次 `[5,15,30]`） | (2+1)×(3+1) = **12** | 50s Core + SDK 指数退避 |
| `sdk_max_retries=0` | 4 | 50s（完全可预测） |

### 5.2 为什么不选「更少请求数」

写 0 把最坏请求数从 12 降到 4，听起来更好。但两层的**故障类型不同**：

- SDK 层处理**连接级**瞬时故障（TCP 重置、读超时）；
- Core 层（`delays=[5,15,30]`）处理**协议级**错误（HTTP 5xx / 429）。

关掉上层会让连接级故障直接冒到 Core，用掉一次宝贵的重试配额——而 Core 的
配额是给「供应商暂时不可用」这种需要长间隔的场景留的。

所以结论是「保持不设，让两层各管各的故障类型」。要改这个决策，需要一次单独的
行为评估（含真实供应商的故障画像），不是顺手在配置里加一行。

### 5.3 钉成测试

- `test_production_config_does_not_pin_the_sdk_retry_layer`：两份 models 配置
  都不得出现 `sdk_max_retries`。
- `test_disabling_the_sdk_layer_is_for_observability_not_production_policy`：
  e2e 脚本**必须**有 `sdk_max_retries=0`，而生产代码里**不得**硬编码。
  同一个开关，目的相反。

## 6. macOS 桌面构建补验（R53-E）

R52 §9-8 挂账项。查 workflow 定义时发现一个**触发条件**的事实：

```yaml
# desktop-macos.yml
on:
  workflow_dispatch:     # 手动
  workflow_call:         # 被别的 workflow 调
  pull_request:
    paths: [desktop/**, .github/workflows/desktop-macos.yml]
```

它只认 `desktop/**` 的 PR，**不认 push**。所以「本轮改了 `src/` 与 `web/`，
按 paths 规则会被触发」这句话对 **Windows** 成立（`desktop-windows.yml` 有
`push` + `src/** web/**`），对 **macOS 不成立**。R52 §9-8 的顾虑因此不成立——
macOS 那侧本轮根本不会自动跑，必须显式 dispatch。

用 `workflow_dispatch` 触发（run **40876413164**）：

| job | 结论 |
|---|---|
| `Build Apple Silicon core candidate` | **success** |
| `Build Apple Silicon full candidate` | **success** |

这项闭合。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_ci_e2e_stub.py` | **42 passed**（30 → 42） |
| 定向：`test_live_snapshot_gate.py` | **44 passed**（39 → 44） |
| 定向：`test_run_profile.py` | **54 passed**（52 → 54） |
| 定向：`test_llm_client_params.py` | **27 passed**（25 → 27） |
| 定向：`test_export_run_samples.py` | **14 passed**（新文件） |
| 收齐后 `--collect-only` | **2119 tests collected** |
| Low-IL 全量 | **2023 passed / 96 skipped / 0 failed**（119.55s） |
| High-IL 全量（权威） | **2108 passed / 11 skipped / 0 failed**（136.73s） |
| 前端 `npm test` | **479 passed / 0 fail**（零改动） |
| 本机 e2e | **9/9 场景通过** |
| GHA e2e | **9/9 场景通过** |

**对账**：

- Low-IL：R52 1988 **+35** = **2023** ✓
- High-IL：R52 2073 **+35** = **2108** ✓
- 总用例 R52 口径 2084 → **2119**（+35）✓
- 新增 35 条构成：`test_ci_e2e_stub.py` 12 + `test_live_snapshot_gate.py` 5 +
  `test_run_profile.py` 2 + `test_llm_client_params.py` 2 +
  `test_export_run_samples.py` 14。零删除。

### 7.1 High-IL 的一次环境坑（与 R52 同族，但不同的具体原因）

首次跑 High-IL 直接 136 个收集错误：

```
ModuleNotFoundError: No module named 'dotenv'
```

根因**不是** R52 记的「相对路径失效」，而是**路径分隔符**：Git Bash 里
`$(pwd)` 给的是 `/f/DeterminFlow x2/xs2`（msys 形式），Windows 的 `py.exe`
不认识，于是整个 `PYTHONPATH` 无效。用 `cygpath -w` 转换后正常：

```bash
sp="$(cygpath -w "$(pwd)/.venv/Lib/site-packages")"
PYTHONPATH="$sp;$sp\\win32;$sp\\win32\\lib;$sp\\pythonwin;$sp\\pywin32_system32" \
  /c/Windows/py.exe -m pytest -q
```

这条与 R52 的「必须用绝对 PYTHONPATH」是**两条不同的规则**：R52 说的是「不能
用相对路径」，本条说「在 Git Bash 下必须转成 Windows 路径」。两条都要满足。

## 8. 变异验证（4 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| 桩：`max()` 改回 `next()` | 红 | ✓ 1 红 |
| 判据：`min_ratio` 1.5 → 1.0 | 红 | ✓ 3 红 |
| 判据：只判前两段（`range(min(1, ...))`） | 红 | ✓ 3 红 |
| 闸门：`p=1.0` 回落正态近似 | 红 | ✓ 3 红 |

第 3 个变异值得单说：它模拟的正是「两段判据」的形状——把三段场景的循环限制成
只判第一对。**只有纯函数测试红了，源码契约测试全绿**。这说明契约测试（「场景
里出现了 `_rising_shape_violations`」）确实只在钉「用了哪个函数」，判据本身
对不对必须靠纯函数测试。两类测试分工明确，不是冗余。

## 9. 本轮改动一览（8 改 1 增）

| 文件 | 变更 |
|---|---|
| `scripts/stub_llm_provider.py` | +~10 行：`FAIL_THRICE_MARKER`、配额选择改 `max()` |
| `scripts/e2e_workflow_stub.py` | +~105 行：`_rising_shape_violations` 共享判据、三段场景、场景列表 |
| `scripts/check_live_snapshot_gate.py` | +~66 行：`sample_size_margin_needed` 抽出、**p=1.0 退化点修复** |
| `scripts/export_run_samples.py` | +~82 行：`half_width_budget`、`--strict-half-width`、导出后打印 |
| `tests/test_ci_e2e_stub.py` | +~198 行：12 条（fail_thrice 配额/真端口/最大配额/三段契约/纯函数 6 条） |
| `tests/test_live_snapshot_gate.py` | +~74 行：5 条（p=1.0 拒与收、两端对称、非零宽度、中段仍用正态） |
| `tests/test_run_profile.py` | +~45 行：2 条（门槛与窗口耦合、门槛随结果返回） |
| `tests/test_llm_client_params.py` | +~57 行：2 条（生产配置不钉、可观察性 vs 生产策略） |
| `tests/test_export_run_samples.py` | **新文件** 343 行 / 14 条 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性，与历轮一致），
**不在本轮改动内**，提交时显式按路径 add 排除。

## 10. 推送与 CI 核对

推送 `6b81ffb`。

### 10.1 CI run 40874361728 —— 五 job 全绿

| job | 结论 |
|---|---|
| `backend` | **success** |
| `windows-backend` | **success** |
| `frontend` | **success** |
| `container-build` | **success** |
| `container-config` | **success** |

**三段场景在 GHA 上真跑**（ubuntu，Python 3.11）：

```
[e2e] PASS retry_backoff_long_chain_shape_is_honoured:
      三段退避形状符合配置 [0.4, 0.8, 1.6]：实测 [0.406, 0.806, 1.606]
[e2e] 9/9 场景通过
```

比值 1.99 / 1.99 vs 配置 2.0。Windows 侧样本量步骤与 ubuntu 侧输出同一个数字
（3.92% / 2.38 / n=255），**p=1.0 的修复没有影响常态快照的判定**——这是要注意
的一点：那条修复改的是退化分支，中段仍走正态近似，两平台结论不变。

### 10.2 Desktop macOS run 40876413164 —— 双 candidate success

见 §6。

## 11. 未做与未验证的事（如实记录）

1. **三段以上仍不判**：四段（`[0.4,0.8,1.6,3.2]` 约 6s）没做。判据本身支持任意
   段数（`_rising_shape_violations` 按 `len(configured)-1` 循环），缺的只是标记
   与场景。真要做时只需加 `[stub:fail_four_times]`，但真实等待翻倍。
2. **`min_ratio=1.5` 的适用量级有限**：测试
   `test_rising_shape_tolerates_common_mode_offset_at_configured_scale` 里钉了
   边界——同样的 0.15s 共模偏移，配置 0.4→0.8 时比值 1.73（合格），配置
   0.1→0.2 时只有 1.40（不合格）。偏移相对配置越大，判别力越弱。本场景把量级
   放在数百毫秒就是为了让偏移始终是小量。
3. **半宽预算不判「快照太薄」**：那是 `--check-sample-size` 的职责。导出脚本只
   回答「反向验证还能不能红」。两者方向相反（§3.3）。
4. **p=1.0 的修复没有真实数据验证**：本机真实数据里没有「全部尝试都失败」的
   快照（当前 255/10），所以这条只用构造样本验证。真实场景下的表现要等某次
   真出现全失败快照时才知道——但那时它会判不合格并给出「需要约 29 次尝试」
   的提示，比原来判合格要安全。
5. **`FAILURE_STREAK_REQUIRED` 仍未改**：复核结论是「3 合理、不改」（§4.1）。
   改它会同时影响后端判据与前端文案（文案里带 N）。
6. **`sdk_max_retries` 未改生产取值**：结论是维持不设（§5.1），需要一次单独的
   行为评估才能改。
7. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致）。本轮改的是
   `scripts/` 与 `tests/`，`container-build` 在 GHA 上真构建并通过。
8. **未重启 8021 服务**：改动是脚本与测试，不涉运行时装配。服务仍在跑
   （PID 26252）。
9. **未验 macOS 的符号链接类用例**：High-IL 的 11 个 skip 是 macOS/POSIX 平台
   专属（icon.icns 1、fcntl 2、Unix 进程树 4、symlink 4 等），本机跑不到。

## 12. 下一轮候选

1. **四段退避形状**：判据已支持任意段数，缺标记与场景（约 6s 真实等待）。
   价值低于三轮——只在「前两段对、第三段对、第四段错」这类形状上才有增量，
   而那种 bug 的实现形态很罕见。
2. **全失败信号的 workflow 级聚合**：当前是「每条任务」的信号。要在工作流列表
   上标「这个 workflow 最近 N 次全失败」，需要按 workflow 聚合（取最新 run 的
   `failure_streak`）。与 R51 §12-1 的「趋势上到 workflow 列表」是同一类工作，
   可一起做。
3. **`--check-sample-size` 加 per-workflow 判据**：R51 §12-2 的候选仍然有效。
   当前只判全局厚度，单个 workflow 很薄而全局够厚时看不出来。
4. **`sample_size_margin_needed` 的两端界换精确算法**：当前两端用
   `1 - 0.05**(1/n)`（Clopper-Pearson 单侧），中段用正态近似。跳变点
   （`p` 从 0 变成 `1/n`）会有一个不连续的台阶。真实影响很小，但如果将来
   margin 收紧到 2 以下，这个台阶值得看一眼。
5. **`baseline_limit` 与 `FAILURE_STREAK_REQUIRED` 合并成一个常量表**：本轮用
   测试钉住了耦合（§4.2），但两个数仍在不同文件。合并成一处配置能根治。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；CI 五 job 与 macOS 双 candidate 全绿。
