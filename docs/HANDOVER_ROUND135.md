# DeterminFlow (xs2) 交接报告 — Round 135（CI 闸门形状：job 清单恰等）

> 单 profile。五轮连推（五）「流程资产自描述」第 1 轮：**CI 闸门的 job
> 清单与欠引用 job 的形状**。生产代码与 CI 行为零改动——本篇只加一条
> 钉测，让「闸门还在、载体没空」从人记变成机判。

## 1. 一句话结论

- **实测缺口**：ci.yml 的顶层 job 清单没有一处「恰等」断言——
  `test_write_permission_belongs_only_to_the_writeback_job` 只遍历在册 job
  查写权限归属，**删除 job 不红**；逐名 grep 实测 `frontend` 在 tests/ 里
  **零引用**，今天删掉它 2902 条用例照样全绿。
- `desktop-macos.yml`、`replace-desktop-assets.yml`、replay/writeback/
  fetch-chain/backend 接线已有既有钉测覆盖，不在本轮重复。
- 新增 `tests/test_ci_workflow_inventory.py`（5 函数 / 5 条）：四个
  workflow 文件存在可解析；顶层 job 键集合**恰等**八个在册 job；矩阵展开
  恰为 10 个 run（索引 §1 口径）；frontend 四连步骤按序在场；
  windows-backend 五个快照闸门 + 存量名字审计在场。总用例 2902 → **2909**
  （+5 钉测、+1 N3 本篇参数化）。
- 变异 **M1–M4 4/4** 咬合：删 frontend（3 红）、加 rogue job（2 红）、
  删 `npm run lint`（1 红）、改审计步骤名（1 红）；还原 sha256 一致。
- 钉测当场咬住作者：本机首跑 `test_index_covers_every_handover_doc` 红——
  本篇 handover 建了文件、索引行还没加。补行后绿（N2 防复发机制的现场
  证据，记入 §5）。

## 2. 为什么是这一轮

R134 收口把「下一轮先办」指向流程资产自描述。CI 闸门是全部 63 次写回、
每轮双跑的**地基**：replay/writeback 的安全边界有 R88 起逐条钉测，但
「地基上有哪几根柱子」本身没人守。job 删除与步骤瘦身都是静默的——
`npm run lint` 从 frontend 消失不会让任何测试红，npm test 照跑。
清单恰等把「悄悄出现/悄悄消失」都堵死：新 job 必须改清单 + handover
记账，与 R133 的「新交接文档必须登记索引」同构。

## 3. 实现

### 3.1 `tests/test_ci_workflow_inventory.py`

- **存在性**：四个 workflow 文件在库、非空、可解析（删文件直接红）。
- **I1 清单恰等**：顶层 job 键集合 == {backend, windows-backend, frontend,
  container-config, container-build, replay-ci-writeback,
  replay-ci-fetch-chain, e2e-history-writeback}，双向差额逐一报出。
- **展开口径**：矩阵 include 的 os 集合恰为 {ubuntu-24.04, windows-latest}，
  展开总数恰为 10——与索引 §1「CI 10 job」同一把尺。
- **I2a frontend**：runs-on ubuntu-latest；`npm ci → npm run lint →
  npm test → npm run build` 按序在场。
- **I2b windows-backend**：runs-on windows-*；五个快照闸门步骤名 +
  `Storage name audit (read-only)` 在场（步骤名集合成员，不钉顺序）。

### 3.2 刻意不做的

- **不重复既有覆盖**：desktop-macos（R48 起三处）、replace-desktop-assets
  （test_ci_gate_wiring §R2 门控）、replay/writeback 接线（R88/R95/R101）
  已各有锚点。
- **不钉超时/并发/环境变量**：那些字段变更属于行为调优，不是「闸门消失」。
- **不改 ci.yml 一行**：本轮生产 YAML 零改动，变异只在本地内存中进行。

## 4. 判据台账

- §10.13 同族补一段（导航层判据扩展到 CI 闸门：清单恰等 + 欠引用形状），
  不新增编号判据。

## 5. 验证

- 定向：`tests/test_ci_workflow_inventory.py` **5 passed**（0.19s）；
  导航钉测 112 条（含本篇 N3）。
- 本机全量：**2881 passed / 28 skipped / 0 failed**（2909 条）。
  首跑 1 红（N2 咬本篇漏登记索引），补索引行后复跑全绿。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 删除 frontend job | 3 红（清单恰等 + frontend 形状 + 展开数） |
| M2 新增 rogue-job | 2 红（清单恰等 + 展开数） |
| M3 删除 `npm run lint` 步骤 | 1 红（frontend 形状） |
| M4 改 `Storage name audit (read-only)` 步骤名 | 1 红（windows-backend 形状） |

内存快照还原后 sha256 逐字节相同，4/4 咬合。变异过程本身踩到一次
「mutation 脚本崩溃后 ci.yml 停留在删了 frontend 的状态」——该文件本轮
无其他改动，`git checkout --` 还原安全；此例外与本轮 M1 无关，教训已由
R133 §5 记录（带本轮改动的文件一律内存快照还原）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全绿；写回历史
  **64→65**。
- 本篇 docs 回填提交预计 **65→66**。

## 7. 边界与遗留

- 清单恰等是「名单」判据：新 job 上线必须显式改 `EXPECTED_JOBS`——这是
  特性不是负担（与 R133 的索引覆盖同构）。
- windows-backend 的步骤名是英文原样引用：上游改名即红，改名者需同步本
  文件与 handover。
- R136 预告（已实测）：history.json 第 1 条 run_id 是时间戳形状
  （legacy 种子，2026-11-01）、7 条无 source 标注、56 条 `ci` 来源；
  git 对账需要全历史检出（写回 job 已 `fetch-depth: 0`，backend job 是
  浅检出——对账测试放哪/要不要加深检出在 R136 定夺）。

## 8. 提交

- 改动：`tests/test_ci_workflow_inventory.py`、R135 文档、PROJECT_INFO、
  HANDOVER_INDEX。生产代码、CI YAML、web/ 零改动。
