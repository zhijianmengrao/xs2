# DeterminFlow (xs2) 交接报告 — Round 57（主闸门 `evaluate` 永不失败修复：外部政策上限 + 区间下界三分法）

> 本轮定位：R56 §10-4 / §11-1 挂账的那个「比主线更严重的独立缺陷」。
> 基线：`0cf3771`（R56 收尾，Low 2074/96/0、High 2159/11/0（权威）、总用例 2170、
> 前端 490/0）。落地形态由用户拍定：**外部绝对上限**——不是历史基线，也不是
> 「只出设计不写代码」。

## 1. 本轮最重要的一件事：阈值长在被测量的量上

`evaluate` 的原写法是三步：

```python
measured = rec_failed / rec_attempts * 100
threshold = min(100.0, max(0.0, measured + margin))
if measured > threshold: ...  # 触发闸门
```

`--margin` 默认 10，argparse 又禁止负值。于是 `threshold ≥ measured` 恒成立，
比较**恒假**。实测把 20 次尝试全判失败，走到这里的 `measured = 100`、
`threshold = min(100, 110) = 100`，`100 > 100` 为假 → 退出码 0。

这不是「阈值取小了」或「余量不够」的问题，是**同义反复**：结论被算进了前提里。
加多少余量都一样，余量为 0 也一样——它不需要「恰好等于」，数学上不可能为真。

R47 当初这样写是有理由的：注释里写着「阈值从快照自身算，不写死。写死阈值会在
快照重导后静默失准」。这个担心本身成立（写死的**期望值**确实会失准），但它把
基准选在了被测量的量上，于是「不写死」变成了「不判」。

## 2. 修法：把阈值移出被测量的量

新增 `--fail-if-above PCT`，与 `provider_failure_profile.py` 的同名开关同义：
**阈值由调用方给**，CI 里是一个写明数字的 8%，脚本内没有默认值。
`evaluate(data_dir, ceiling=None)`，阈值不参与任何从快照算出来的算术。

两种没选的修法，理由都是「这一轮不该同时引入新失效面」：

- **与历史基线比**（复用 R55 的 `compare_run_baseline`）：贴切，但需要一份持久
  基线，还要补保鲜与漂移处理；薄基线会重演 R56 的 `undetermined`。
- **只出设计**：这个缺陷的修法在参数层就能定死，拖一轮没有信息增量。

由此定下的一条分工：**阈值可以来自外部政策，精度必须来自数据**。
`--check-sample-size` 那一半仍然全部由快照自身算（Clopper-Pearson 精确界，没有
任何常量），所以 R47 担心的「写死会失准」只落在政策上限上——而政策上限不随
数据漂移：数据越过政策就该红，那正是它存在的意义。

## 3. 判决形状：三分法 + 主闸门与 per-workflow 共用一份算术

三处刻意复用，理由与 R56 §4 同类：

- `_cp_interval(attempts, failed)`：端点走闭式 `1 - 0.05**(1/n)`、中段走
  `_cp_bounds`，单位百分点。主闸门与 per-workflow 判决都调它——两处各写一份
  精确界，迟早出现「这边说超、那边说不超」。
- `_verdict_of_interval(lower, upper, threshold)`：`lower > threshold` → `exceeds`；
  `upper <= threshold` → `normal`；其余 → `undetermined`。
- `_rate_verdict`（R56 的 per-workflow）与新 `_ceiling_verdict`（主闸门）
  各自只组装判决文字，判定逻辑只有一份。

测试 `test_main_gate_and_per_workflow_share_the_same_interval` 在 5 组 `(n, k)`
× 5 个阈值上比对两处判决；任一处换口径（正态近似、点估计）就会分裂。

判定用**区间下界**而不是点估计，理由沿用 R56 §2：点估计判「超阈」等于「样本越小
越容易被判坏」。`undetermined` 不判失败——样本精度归 `--check-sample-size`
（退出码 7）。两处都红会让人对着一个只差精度的快照去查供应商，处置指错了。

入库快照（10/255 = 3.92%，区间 [2.14%, 6.56%]）在三种上限下的实测：

| 上限 | 判决 | 退出码 | 说明文字 |
|---|---|---|---|
| 8%（CI 真实判定） | `normal` | 0 | 整个区间都在阈值之内，判正常 |
| 4% | `undetermined` | 0 | 区间横跨阈值，样本不足以判是否超阈（不判失败） |
| 1%（CI 反向验证） | `exceeds` | 1 | 整个区间都在阈值之上，判超阈 |

## 4. 上限为什么取 8%

这是**政策值**，不是从数据反推的：`10/255 = 3.92%`，95% 上界 6.56%，明确在限
内；要让闸门判 `exceeds`，需要 255 次尝试里至少 29 次失败（11.4%）——因为判据
要求**整个区间**都在上限之上。

如实记录代价（这是本轮最该被下一轮看见的一句）：这个闸门对「失败率翻倍到
7.8%」仍然不会红，因为那时上界会跨过 8%，只会判 `undetermined`。它判的命题是
「**有证据表明政策被突破**」，不是「有变化」。变化检测属于趋势面
（`workflow_trend` / `compare_run_baseline`），不该塞进主闸门。

上限只写在 `ci.yml` 的两次调用里（ubuntu 与 windows），有测试逐字核对两边数字
相同：漂开的话，同一份快照会在一个 runner 上判红、另一个判绿，那种矛盾最难排查。

## 5. 报告模式：不许用沉默表达通过

不给 `--fail-if-above` 时仍然退出 0，但说明必须写明
「未给 --fail-if-above，本步只报告不判定（退出 0 不代表失败率合格）」。
有测试钉住这条文案，并断言说明里**不出现**「判正常」——「没给阈值」被沉默成
通过，就是这个缺陷换了一件外衣。

为什么允许报告模式存在、而不把开关设成必填：`--check-stale` / `--check-coverage`
/ `--check-sample-size` 共用同一个 CLI，必填会让所有模式都多一个无关参数；而且
人本地「看一眼数字」是合理用法。CI 那边不靠默认值兜底，靠三条静态测试：

1. `_gate_invocations()` 逐行取出**每一次**调用，每一次都必须带 `--fail-if-above`；
2. 第二次（反向验证）的上限必须低于第一次，且退出码变量来自第二次调用；
3. 两个 runner 的第一个上限相同。

`--margin` 的语义同步收窄：它现在只用于 `--check-*` 判据（样本量厚度与
per-workflow 判决都拿它当尺）。默认模式里给了就 `parser.error`——静默忽略会让
「我把余量收紧到 2，CI 却没变」变成一个无人排查的谜（与 R56 对
`--fail-on-exceeds` 的处理同一纪律）。argparse 默认值改成 `None`，才能区分
「没给」与「给了 10」。

参数边界还有一个必须钉死的值：**上限必须 < 100**。`--fail-if-above 100` 会被
接受却永远判不出超阈（Clopper-Pearson 上界最多 100%，而判据要求整个区间都在
上限之上）——那是写着「容忍一切」的恒绿配置，与本轮修掉的自指阈值同一类失效，
只是更容易被发现。测试里 `101` / `100` / `-0.5` 三个值都必须被拒绝。

## 6. CI 接线

- **ubuntu** `backend`：原有步骤改写为「8% 真实判定 + 反向验证压到 1% 必须判 1」。
  真实判定非 0 时立刻 `exit "$code"` 并标注语义（1=超 8% 上限 / 3=无样本 /
  4=元数据漂移）。
- **windows** `windows-backend`：**新增**同名步骤（此前主闸门只在 ubuntu 上跑）。
  与 ubuntu 一一对应，照 R52 纪律：`$ErrorActionPreference = 'Continue'`
  （那次故意以 1 退出的调用不能被包成 NativeCommandError）+ 末尾显式 `exit 0`
  （GHA 的 pwsh 包装器会追加 `exit $LASTEXITCODE`，而最后一条原生命令正是那次
  故意失败的调用）。
- 不再用 heredoc 写退出码说明（R56 记过：heredoc 体顶格会提前终止 YAML 块标量）。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2085 passed / 96 skipped / 0 failed**（124.41s） |
| High-IL 全量（权威） | **2170 passed / 11 skipped / 0 failed**（142.76s） |
| 前端 `npm test` | **490 passed / 0 fail**（8 个套件） |
| 本机 e2e | 未重跑（本轮零 e2e 相关改动；R56 记录 10/10） |

**对账**：

- Low-IL：R56 2074 **+11** = **2085** ✓
- High-IL：R56 2159 **+11** = **2170** ✓
- 总用例 R56 口径 2170 → **2181**（+11）✓
- 新增 13 条、删除 2 条：`test_live_snapshot_gate.py` 74 → **85**。
  删掉的是「阈值随余量变」与「余量归零仍通过」——它们钉的正是自指阈值的行为，
  留下来会与新语义自相矛盾；替换它们的 5 条断言更强（见 §8 第 1 个变异）。
- 前端零改动（490/0 口径不变）。

### 7.1 本轮供应商失败率（R41 起的每轮固定动作）

`python scripts/provider_failure_profile.py --summary`（默认 `--limit 3`，扫本机
`data/workflows`；与本轮改动无关，只为逐轮时间序列留一行）：

| workflow | runs | attempts | failed | rate | failing_stages |
|---|---|---|---|---|---|
| build | 3 | 27 | 1 | 3.7% | agent_corelaws（http_5xx） |
| character | 3 | 75 | 1 | 1.3% | agent_deep（stream_stall） |
| export | 3 | 3 | 0 | 0.0% | — |
| mvp | 2 | 56 | 4 | 7.1% | script_check_originality / script_smart_context |
| outline | 2 | 16 | 0 | 0.0% | — |
| polish | 2 | 14 | 0 | 0.0% | — |
| post-hoc | 3 | 24 | 1 | 4.2% | script_confirm_archive |
| reader-sim | 3 | 12 | 0 | 0.0% | — |
| story-plan | 2 | 16 | 0 | 0.0% | — |
| **TOTAL** | **23** | **243** | **7** | **2.9%** | — |

（R51–R56 的交接文档没贴这一段，本轮补上。注意它和入库快照不是同一批数据：
快照是 28 runs / 255 attempts / 10 failed，这里受 `--limit 3` 限制。）

### 7.2 推送与 CI 核对（已闭环）

推送 `53f8ad2`（代码）+ `b13d251`（文档）+ `b605d50`（上限 = 100 的边界修复）。

| run | 结果 |
|---|---|
| `CI` **41002780226**（b13d251） | **五 job 全绿**（backend / windows-backend / frontend / container-config / container-build） |
| `CI` **41003395830**（b605d50） | **五 job 全绿** |

CI 日志实证（下载日志解码后逐字比对，不是推断）：

- **新步骤在两个 runner 上都真跑了**：ubuntu `backend` 的第 8 步与 windows
  `windows-backend` 的第 7 步 `Provider failure-rate gate against real snapshot`，
  均 success。windows 那一步此前**不存在**（本轮新增）。
- **两个 runner 的判决逐字一致**：

  ```
  [live-gate] 失败率 3.92%（n=255, 失败 10），95% 区间 [2.14%, 6.56%]，
              阈值（政策上限）8.00%：整个区间都在阈值之内，判正常
  OK  真实失败率闸门双向生效：8% 上限通过，1% 上限触发 1
  ```

  windows 的措辞多一个平台后缀 `（Windows/Python 3.14）`，其余逐字相同
  （windows 日志里中文是 `\uXXXX` 转义，解码后比对）。
- **反向验证真跑**：ubuntu 日志里能看到第二次调用的输出
  `阈值（政策上限）1.00%：整个区间都在阈值之上，判超阈`，退出码 1 被显式断言；
  windows 那次输出被 `$null =` 收走（预期），由 `$LASTEXITCODE` 断言 ——
  两个 runner 都打印了上面那行 OK，说明断言真的执行过。
- **四面用例总数一致**：ubuntu `2117 passed / 64 skipped` = **2181**、
  windows `2152 / 29` = **2181**、本机 Low-IL `2085 / 96` = **2181**、
  High-IL `2170 / 11` = **2181**。
- 第二次 run 覆盖了 `b605d50`（拒绝上限 100）——那是参数校验，用例数不变，
  说明修复没有顺手改变任何判定。

`config/skills_config.json` 的运行时写入未被任何一次提交带入（三次提交后
`git status` 都只剩它一个）。

## 8. 变异验证（6 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| 自指阈值（退回 `measured + margin`） | 红 | ✓ 5 红（判定力／全失败／报告模式文案／undetermined／CLI 传参） |
| 主闸门改用点估计而非区间下界 | 红 | ✓ 3 红（undetermined／共用算术／per-workflow 漂移基线） |
| `undetermined` 判成失败 | 红 | ✓ 2 红 |
| 报告模式静默写成「通过」 | 红 | ✓ 1 红 |
| CI 真实判定那次调用丢掉上限 | 红 | ✓ 3 红（逐次检查／反向验证／两 runner 同数） |
| windows 上限改成 10（与 ubuntu 漂开） | 红 | ✓ 1 红 |

**还原方式**：`cp` 备份覆盖回去，**不是 `git checkout --`**（R55 的教训：
`git checkout --` 会抹掉整份未提交改动）。还原后 `diff` 与备份逐字节相同，
85 条测试全绿。

第 1 个变异值得说：它同时踩红 5 条测试，而其中「报告模式文案」那条与阈值算术
无关——因为退回自指写法后 `ceiling` 参数整个失去了作用，报告模式的分支也就不
存在了。这说明「参数是否真的被用上」需要单独的测试（`test_cli_default_mode_
honours_the_ceiling`），光测 `evaluate` 不够。

## 9. 本轮改动一览（3 处代码改动 + 交接文档 + 1 个单独文档提交）

| 文件 | 变更 |
|---|---|
| `scripts/check_live_snapshot_gate.py` | +141/−36：`_cp_interval`、`_verdict_of_interval`、`_ceiling_verdict`、`evaluate(ceiling)`、`--fail-if-above`、`--margin` 语义收窄与三处参数校验（含拒绝上限 100） |
| `tests/test_live_snapshot_gate.py` | +218/−26：13 条新测试、2 条自指语义测试替换、CI 接线四件套 |
| `.github/workflows/ci.yml` | +50/−5：ubuntu 主闸门改写 + windows 新增主闸门步骤 |
| `docs/PROJECT_INFO.md` | R57 基线条目追加（+3 行）；另有一个单独提交 `a2f5e4d`（R44 条目错位修复，见 §12） |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性），**不在本轮
改动内**。提交时照例显式按路径 add，排除它。

## 10. 未做与未验证的事（如实记录）

1. **没有与历史基线对比的模式**：本轮只有绝对上限。R55 的 `compare_run_baseline`
   能用，但那是「变化检测」，与「政策突破」是两个问题，混进一个诊断会让人分不清
   该查供应商还是查回归。
2. **上限 8% 没有校准数据**：它是政策值，第一次真实起作用要等失败率真的抬到那个
   量级。下一轮看 CI 日志时可以复核一次「是否逼近」。
3. **这个闸门的灵敏度有上限**（§4）：8% 上限 + 区间判据 = 需要 11.4% 才红。想让
   更小的漂移可见，得走趋势面，不是把上限调低（调低会让它现在就是 `undetermined`）。
4. **未接 per-workflow 硬门槛**：`--fail-on-exceeds` 已实现、已测试，CI 仍不接
   （R56 §3 第二步，留给下一轮决策）。
5. **桌面 Windows 未被触发**：路径过滤只认 `desktop/`、`src/`、`web/`、`config/`、
   `requirements.lock` 与 workflow 自身，本轮改的是 `scripts/`、`tests/`、`.github/`
   其它文件——预期行为。
6. **未跑 `docker build`**：本机仍无 docker/wsl；`container-build` 在 GHA 上真构建。
7. **前端未跑 `npm run build`**：零前端改动。（`npm test` 已跑，见 §7。）
8. **未重启 8021 服务**：本轮只改脚本与 CI 接线，不涉运行时装配。

## 11. 下一轮候选

1. **per-workflow 硬门槛**（R56 §3 第二步）：本轮把「主闸门能红」这件事做成了，
   机制可复用——但 per-workflow 的 8/9 `undetermined` 仍在，接硬门槛前得先决定
   「连续 N 轮 undetermined 就提示重导」这类次级信号。
2. **主闸门的历史基线模式**：与绝对上限并存时，退出码语义要写清 1 的两种来源
   （政策突破 / 回归），否则日志里分不清该查什么。
3. **`min_ratio` 判别力边界的精确定量**（R53 §11-2 / R55 §11-2）。
4. **`p=1.0` 的真实数据验证**（R53 §11-4）。
5. **`workflow_trend` 与 `workflow_health` 合并成一次画像扫描**（R55 §11-3）。
6. **8% 上限的首次校准**（§10-2）。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）。

## 12. 顺带做的一件文档修复（单独提交，与本轮代码无关）

`docs/PROJECT_INFO.md` 里 R44「CI 核对」条目错位：标题被粘在 R53 条目的行尾
（多出 68 个字符），正文的 14 行续行挂在 R55 名下，读起来像是 R55 的记录。
R56 §12 记过这件事但没修（跨轮文档，混在代码改动里会让 diff 无法审阅）。本轮按
用户拍定先单独提交：`a2f5e4d`。

校验方式（不是目测）：续行块 509 行的多重集与 `HEAD` 完全相等；除 R53 行尾那
68 个字符外，所有 `- 2026-.. R*` 条目与 `HEAD` **逐字节**相同；R44 标题行紧随
R44 双基线条目之后。
