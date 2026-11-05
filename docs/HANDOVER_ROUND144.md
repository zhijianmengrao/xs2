# DeterminFlow (xs2) 交接报告 — Round 144（交接文档 §6 回填时限机判）

> 单 profile。五轮连推（六）第 1 轮：**把 R139 §9 点名的最后一处「人的
> 纪律」交给判据**——§6 的 CI 回填不再允许拖过下一轮。生产代码零改动；
> 顺带清掉三处实测漂移（R137 落后 6 轮、R143 待回填、R139 未提交）。

## 1. 一句话结论

- **实测缺口（现行犯）**：R139 §9 明确写着「§6 由下一轮回填……那是候选制
  的人的纪律」，S 系判据不覆盖。R144 开工实测：**R137 §6 仍是模板**
  （`<code-sha>`/`<run1>`/「预计」，落后 **6 轮**）；R143 §6 按单跑制待
  本轮回填；工作树里还有一份 **R139 §6 的回填未提交**。三处同证：没有
  判据的时限只是愿望。
- 新增 `tests/test_handover_ci_backfill.py`（2 函数 / 10 条，**D 系判据**）：
  **D1 时限**（R135..latest-1 的 §6 必须已回填、无占位符）；**D2 同账**
  （§6 引用的每个 run id 必须在 `history.json`，`A→B` 写回序号 == 该 run
  在账中的位置）。总用例 2984 → **2995**（+9 参数化、+1 边界、+1 N3 本篇）。
- 回填三处并逐条核验（GitHub API + `history.json` 双证）：R137
  `2ec2201`/run `41888611769`/66→67；R139 `be1bea8`/run `41896959067`/
  68→69；R143 `b195b72`/run `41909830139`/72→73——三个 run 均 10 job
  `success`。
- 变异 **M1–M3 3/3** 咬合（占位符回潮、run id 造假、写回序号漂移）。

## 2. 为什么是这一轮

单跑轮次制从 R135 起（docs 回填并入下一轮提交），至今 9 轮。九轮里
「回填」一直是**唯一没有判据的账**：R136 钉了 history↔git 双账，R137 钉了
索引 §1 三行快照，但交接文档 §6 写的 run id 与写回序号只有人眼。R137 的
模板在六轮后仍活着，正是这条缝隙的实测证据——它不影响任何一条既有判据，
因此无人被咬。

D 判据的锚点选在「改了就必须连动」的字面上：§6 要么点名 run id、要么
红；点名的 id 必须在 history 里、`A→B` 的 B 必须是它的序号。这样文档账
（§6）、写回账（history.json）、平台事实（run id）三者第一次同账。

## 3. 实现

### 3.1 `tests/test_handover_ci_backfill.py`

- **D1 时限**：扫描 `HANDOVER_ROUND135..latest-1.md`；§6 必须存在、不得
  出现 `<run`/`<code-sha>`/「预计」，且至少点名一个 11 位 run id。latest
  （当前轮）豁免：它的 run 在推送后才存在，由下一轮回填。
- **D2 同账**：§6 里每个 run id 必须在 `history.json`；按 bullet 解析
  `A→B` 写回区间，若该区间前有 run id，则 `A == B-1` 且 history 第 B 条
  的 run_id == `ci-<id>`。**不带 run id 的 `A→B` 不判**——那是下一轮 docs
  跑的预告（未来账）。
- 首跑咬出一处正则误吃：R136 §6 的耗时区间 `18:04:03→18:25:43` 被当成
  写回区间（`03→18`）。修复为冒号邻接排除后 8/8 绿（当时 R143 仍是
  latest 豁免）；这正是「判据先咬作者」的老现场。
- 扫描下限 R135：R134 及以前的双跑制文档「预计」是当时形态（索引 §6.2
  已登记），永久不扫。

### 3.2 回填与核对

| 轮 | 提交 | run | 写回 | bot 提交 | 平台结果 |
|---|---|---|---|---|---|
| R137 | `2ec2201` | `41888611769` | 66→67 | `20bda31` | 10 job success（17m18s） |
| R139 | `be1bea8` | `41896959067` | 68→69 | `744b544` | 10 job success（17m42s） |
| R143 | `b195b72` | `41909830139` | 72→73 | `e217624` | 10 job success（17m34s） |

- R137/R143 的 §6 改为实测值；R139 的工作树回填一并入库。
- 顺带修正索引 §1「代码基线」行：`096ff16`（R132）停更 12 轮，改为
  `e217624`（R143 代码 + CI 回写）。

### 3.3 刻意不做的

- 不判「10 job 全绿」等叙述真假：CI 平台的结论不在仓库内，D2 只判
  run id 在账与序号自洽；
- 不扫描 R134 及以前的双跑制文档（历史形态，不制造第二份账）；
- 不把 docs 跑的「下一轮预告」纳入判决（它涉及尚未发生的 run）。

## 4. 判据台账

- 新增 §10.16（D 系：交接 §6 回填时限 + run id 同账）；§10.15 尾部
  判据家族清单连动一行。

## 5. 验证

- 定向：`tests/test_handover_ci_backfill.py` **10 passed**（0.15s）。
- 本机全量：**2967 passed / 28 skipped / 0 failed**（2995 条，610.29s）。
  首跑是 1 failed 而非全绿：本机全局 `core.symlinks=false`，git 把用例造出
  的 symlink 存成普通文件，`test_symlink_cannot_escape_checked_out_package`
  因此不触发逃逸检测；以 `GIT_CONFIG core.symlinks=true` 重跑全绿（CI
  ubuntu 原生即为 true）。该前提未并入 `requires_symlink` 探测，作为
  边界登记在 §7 末尾，不单独立项。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 把 R143 §6 改回模板 | D1 红（占位符/无 run id） |
| M2 把 R142 §6 的 run id 改成未入账的 `41908008619` | D2 红（不在 history） |
| M3 把 R142 §6 的 `71→72` 改成 `71→70` | D2 红（第 70 条不是该 run） |

内存快照还原后 sha256 逐字节相同，3/3 咬合。

## 6. CI

- 提交 **`9253fd7`** 推送后 run **41950282866**：**10 job 全 `success`**
  （01:42:04→01:59:17 UTC，约 17m13s）；写回历史 **73→74**
  （`ci-41950282866`，bot 提交 `1dc3181`）。R145 回填。
- 本篇 docs 回填并入 R145 提交；其 run 执行 **74→75**。

## 7. 下一轮候选（R145–R148：全部先实测后登记）

五轮连推（六）主题：**文档与依赖的「第二份账」继续收口**。R148 为收口轮。

- **R145 依赖四源同账**：实测 `pyproject.toml [project].dependencies`
  17 个 `==` 钉版**全部**在 `requirements.txt` 且版本逐字相等；
  `requirements.txt` 另有 2 个 pyproject 没有的包（`tzdata==2026.3`、
  `uvicorn-worker==0.4.0`，服务/Windows 运行时补充）；dev 的
  `pytest==9.1.1` 在 requirements-dev.txt、lock、pyproject dev extra 三处
  一致。R143 的 W1/W2 只钉 requirements.txt↔lock，pyproject 与
  requirements-dev.txt 仍是无人把守的第三、四源。判据方向：pyproject ⊆
  requirements（按名 + 钉版同账）、requirements-dev ⊆ lock、dev extra ==
  requirements-dev；req 独有包登记为显式允许集。
- **R146 活文档的「轮次盖子」**：实测 R144 开工时 PROJECT_INFO H2「至
  R133」落后 11 轮；索引 H1「R24–R131」落后 13 轮、§4 H2「R24–R134」、
  §6.1「R24–R134」；§3 阶段表最后一行的 `五轮连推（五）R135–R139`
  未续到 R143；§6.4.3「42/109」、§6.4.4「38/107」；§1「判据登记 19 条」
  自 R139 起未再动。判据方向：当前时态的「至 R<n>/R24–R<n>/N 份」必须
  等于最新交接文档轮次；历史审计数字必须带显式轮次锚。
- **R147 索引 §4 行自描述同账**：实测 118 行日期与
  `git log --diff-filter=A` **0 漂移**，主题列与 H1 副标题有 **7 处**
  标点/措辞差（R117/118/123/125/126/129/132）。判据方向：日期 == 首次
  入库日期；主题 == H1 副标题（允许反引号/标点归一）；R118/R123 的 H1
  补轮次区间。
- **R148 收口轮（R144–R148 四账）+ 实测登记 R149–R152**：审计四轮
  handover/PROJECT_INFO/台账/记忆；开工前按候选制实测下一批主题。

**未立项的实测边界**：`requires_symlink` 只探测 OS 建链能力，不探测 git
`core.symlinks`；本机全局为 false 时该用例会失败而非 skip（R144 全量首跑
实测 1 failed，`GIT_CONFIG core.symlinks=true` 覆盖后全绿；CI ubuntu 原生
为 true）。证据只在本机环境，不单独立项——R148 收口时决定是并入 skip
判据还是只登记。

## 8. 提交

- 改动：`tests/test_handover_ci_backfill.py`、R144 文档、R137/R139/R143
  的 §6 回填、`PROJECT_INFO.md`、`HANDOVER_INDEX.md`（§1 三行 + 代码
  基线 + §4 一行）、`JUDGEMENT_LEDGER.md`（§10.16）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
