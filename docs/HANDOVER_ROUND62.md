# DeterminFlow (xs2) 交接报告 — Round 62（逐 workflow 历史基线：只有 2/9 说得出话，提前量 2/5 次失败）

> 本轮定位：R59 §10-2 挂账两轮的「per-workflow 历史基线」。
> 基线：`be67b84`（R61 收尾：Low 2106/113/0、High 2191/28/0（权威）、
> 总用例 2219、前端 490/0）。落地形态由用户拍定三项：**主线 = per-workflow
> 历史基线**；**范围 = 只做主线收口**；**收尾 = 照常推送 + 五 job 逐字核对**。

## 1. 本轮最重要的一件事：这个判据的判定力是 2/9，必须写在输出里

逐 workflow 回归不是「每个 workflow 各判一次」。入库快照 9 个 workflow 的
上一轮基线与精度：

| workflow | 上一轮 | 95% 半宽 | 可判 |
|---|---|---|---|
| character | 2/79 | 5.22pp | ✓ |
| mvp | 4/56 | 8.46pp | ✓ |
| build | 3/33 | 12.76pp | ✗ |
| post-hoc | 1/24 | 14.12pp | ✗ |
| outline / story-plan | 0/16 | 17.07pp | ✗ |
| polish | 0/14 | 19.26pp | ✗ |
| reader-sim | 0/12 | 22.09pp | ✗ |
| export | 0/5 | 45.07pp | ✗ |

**7 个判不了**，因为拿 0/5（95% 上界 45.07pp）当阈值时，当前只要出现一次
失败就会判回归——那是向错方向的假红。可判集合由 `sample_size_margin_needed`
决定，与 `--check-per-workflow` 判「精度达标」的那批**完全重合**（同一把尺，
不另立门槛）。

而这 2 个可判的，两轮计数**完全相同**（`history` 第二轮是第一轮的副本，
R60 已记录的自比自）。所以真实快照上的判决是「2 个没有回归、7 个判不了」，
输出里必须逐字写出「这是样本没有新增，不是质量结论」，否则「没红」会被读成
「逐 workflow 都健康」。

## 2. 真实增量：比合并层早 2 次（character）/ 5 次（mvp）失败开口

这是本判据存在的唯一理由，用同一份基线实算：

| 场景 | 逐 workflow 判回归 | 合并层判回归 | 提前 |
|---|---|---|---|
| character 2/79 → k/79 | k=16（20.3%，下界 13.14% > 12.53%） | k=18（22.8%，全局下界 7.24% > 6.92%） | **2 次** |
| mvp 4/56 → k/56 | k=15（26.8%，下界 17.29% > 17.14%） | k=20（35.7%，全局下界 7.24% > 6.92%） | **5 次** |

中间那一段（character 16–17 次、mvp 15–19 次）合并层**结构性地看不见**：
大体量 workflow 的一次变坏被其余 7 个摊薄，全局率只挪几个千分点。逐 workflow
层在这段里就开口。这不是「更细所以更好」，是两次失败的可测差距。

## 3. 设计：三分法 + 可判集合 + 覆盖变化 + 无判定力显式

1. **阈值 = 上一轮失败率 + margin**（默认 10），与合并层共用 `_baseline_verdict`
   与 `_cp_interval`：`exceeds`（整个区间在阈值上）/ `normal`（整个区间在阈值
   内）/ `undetermined`（横跨）。
2. **`undetermined` 永不判失败**：区间横跨、覆盖变化、基线太薄三类都归这里，
   处置是重导更多 run，不是「不合格」。
3. **覆盖变化逐 workflow 显式**：只在上一轮或只在当前轮出现的 workflow 各自
   判 `undetermined` 并写明「覆盖变化，失败率不可比」——与 R58「缺席即中断」、
   R59「集合不同不判回归」同一条纪律。
4. **两轮计数完全相同单独计数**（`unchanged`）：不折进 `normal` 的语义里，
   报告里写「样本没有新增，不是质量结论」。
5. **「可判 0 个」与「没有可比上一轮」都要写成文字**：退出码仍是 0，但输出
   里明写「本步没有判定力，退出 0 不代表没有回归」。这是 R61「恒绿步骤」那条
   教训的直接应用——能判 2 个和能判 0 个都是 0 退出，但语义完全不同。

退出码：有 `exceeds` → 1，来源行写 `退出码 1 的来源：逐 workflow 回归（wf-bad）`；
无样本 3；元数据漂移 4。不设「报告模式」开关——回归的含义就是判据，
报告用途由 `--check-per-workflow` 的诊断承担。

## 4. 顺带的去重：三条 per-workflow 判据共用一份漂移检查

`check_per_workflow` 与 `check_per_workflow_rate` 原来各有一份逐字相同的
`per_workflow` 元数据/内容比对块（约 19 行 × 2）。加第三条判据时再抄一份就是
三份会各自演化的检查。本轮抽出 `_per_workflow_drift` + `_drift_message`，
三条判据共用，并用 `test_three_per_workflow_judges_share_one_drift_message`
钉住三者的退出码 4 文案**逐字相同**。原有 137 条测试在重构后全部通过。

## 5. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/check_live_snapshot_gate.py` | **+254 / −38** | 新判据（纯函数 + check + CLI）+ 漂移检查去重 + docstring |
| `.github/workflows/ci.yml` | **+58 / −0** | 两个 job 各加一步（含反向验证） |
| `tests/test_live_snapshot_gate.py` | **+258 / −0** | 21 条新用例（16 个函数，其中 1 个参数化 ×5） |
| `config/skills_config.json` | 未入库的运行时写入（B23/R36 定性），照例排除 | 排除 |

`git show --numstat` 合计 **+570 / −38**。删掉的 38 行是两份重复的漂移检查。

## 6. 变异验证（两次，均被测试咬住，`cp` 备份还原）

| 变异 | 期望 | 实测 |
|---|---|---|
| 判决恒为 `normal` | 有 `exceeds` 的用例红 | **5 failed**（fires_on_jump / straddle / exceeds fixture / malformed history / CLI） |
| 关掉 `eligible` 守卫（全部可判） | 薄基线用例红 | **2 failed**（only_judges / committed snapshot） |
| 还原后 | 全绿 | **141 passed** |

还原用 `cp` 备份覆写，不用 `git checkout --`——R55 的教训（会抹掉整份未提交改动）。

## 7. 十条快照闸门本地预演（与 CI 同命令、同数据）

| 步骤 | 期望 | 实测 |
|---|---|---|
| `--fail-if-above 8` | 0 | ✓ 0 |
| `--fail-if-above 1` | 1 | ✓ 1 |
| `--check-sample-size` | 0 | ✓ 0 |
| `--check-sample-size --margin 2` | 7 | ✓ 7 |
| `--check-per-workflow` | 0 | ✓ 0 |
| `--check-per-workflow-rate --fail-on-exceeds` | 0 | ✓ 0 |
| `--fail-on-regression --regression-margin 3` | 0 | ✓ 0 |
| 同上（`live_snapshot_exceeds`） | 1 | ✓ 1 |
| **`--check-per-workflow-regression --margin 10`** | **0** | **✓ 0（2 可判 / 7 判不了 / 2 unchanged）** |
| 同上（`live_snapshot_exceeds`） | 1 | ✓ 1（wf-bad） |

`ci.yml` 改后先 `yaml.safe_load` 验证：解析通过，5 job 齐全，新步骤在两个
job 各 1 处。

## 8. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2127 passed / 113 skipped / 0 failed**（133.69s） |
| High-IL 全量（权威） | **2212 passed / 28 skipped / 0 failed**（152.37s） |
| 前端 `npm test` | **490 passed / 0 fail**（8 子套件：48+60+137+81+139+1+18+6） |
| 本机 e2e | 未重跑（零产品代码改动，R56 记录 10/10） |

**对账**：总用例 **2219 → 2240**（+21，全部在 `test_live_snapshot_gate.py`
120 → 141），零删除；前端 490 不变。Low/High 两侧增量都是 +21，说明新用例在
两种完整性级别下都真实执行（无新增 skip）。

## 9. 未做与未验证的事（如实记录）

1. **逐 workflow 判据的判定力受数据限制**：7/9 判不了，2/9 可判且是自比自。
   要让 `outline`/`story-plan`（16 次）达到 margin 10 需要约 29 次尝试，
   `export`（5 次）物理上补不到。这是数据事实，不是实现缺陷。
2. **判定力只在两个大 workflow 上经过验算**（§2 的表是用当前基线算的静态分析），
   真实数据上从未见过 `exceeds`——它的判定力由 `live_snapshot_exceeds` 的反向
   验证承担。
3. **8% 上限、失败成因分层、`min_ratio` 定量、画像扫描合并**均未做（范围只做主线）。
4. **未重导快照**：本机最新 run 仍是 `2026-10-28 08:34`（`data/workflows` 实测），
   重导只会再写完全副本（R60/R61 已记录）。
5. **CP 溢出未修**（R61 §4-2，n=4000 形状才需处理，独立技术债）。
6. **未跑 `docker build`**：本机仍无 docker/wsl；`container-build` 在 GHA 真构建。
7. **未跑 `npm run build`**：零前端改动（`npm test` 已跑 8 子套件 490 条）。
8. **未重启 8021 服务**：本轮不涉运行时装配。
9. **Desktop Windows 预期不触发**：paths 过滤只认 `desktop/`、`src/`、`web/`、
   `config/`、`requirements.lock` 与 workflow 自身；本轮改 `scripts/`、
   `.github/workflows/ci.yml`（自身）、`docs/`。

## 10. 下一轮候选

1. **有新 run 后再重导一次**（R60 §7-1 / R61 §10-1 的直接后续）：这是本轮
   新判据第一次能做真正的两批比较。**当前仍被数据卡住**。
2. **`min_ratio` 判别力边界的精确定量**（R53 §11-2 / R55 §11-2）——与
   R61/R62 同一方法（用判据自己的算术算操作特征）。
3. **`p=1.0` 的真实数据验证**（R53 §11-4）。
4. **`workflow_trend` 与 `workflow_health` 合并成一次画像扫描**（R55 §11-3）。
5. **CP 精确界的溢出加固**（R61 §10-6）：仅当样本长到 4000+ 或失败率接近 50%
   才需要，改法是二项分布转到对数空间求和。
6. **（新）逐 workflow 判据的「提前量」固化成文档化校准**：本轮 §2 的表是手算
   一次，`min_ratio` 那一轮可以用同一份算术把它写成可复核的命令。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定，CI 不写回仓库）。

## 11. 推送与 CI 核对

（待推送后补写）
