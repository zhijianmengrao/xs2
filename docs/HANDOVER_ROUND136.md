# DeterminFlow (xs2) 交接报告 — Round 136（history.json ↔ git 双账核对）

> 单 profile。五轮连推（五）「流程资产自描述」第 2 轮：**写回账本与它的
> 第二份账（git bot 提交）机械对账**。除给 backend / windows-backend 的
> checkout 补 `fetch-depth: 0` 外，生产代码与 CI 行为零改动。

## 1. 一句话结论

- **实测缺口**：`history.json`（索引 §6.2 的权威账本）与 git bot 提交之间
  的对齐此前只靠人眼。实测（2026-11-05，64 条）：56 条 `source=ci` +
  7 条 legacy（R93 标注之前的种子）；**第 1 条 run_id 是 ISO 时间戳形状**
  （唯一非 `ci-` 形状条目）；62 个 `chore(e2e): record CI run <id>` bot
  提交与 62 条 `ci-` 形状条目双向恰等——账目前对，但没有判据，漂了没人知道。
- 新增 `tests/test_history_ledger_accounts.py`（3 函数 / 3 条）：
  **H1** 逐条形状（ci 条目 run_id 形状、计数 int、`passed+failed==total`、
  scenarios dict 列表；时间戳形状 run_id 恰好 1 条且是第 1 条）；
  **H2** run_id 无重复 + `exported_at` 单调不减；**H3** 与 git bot 提交
  双向恰等，浅检出**显式红**（附 `git fetch --unshallow` 指引，不降级成
  skip）。总用例 2909 → **2913**（+3 钉测、+1 N3 本篇参数化）。
- **CI 配套**：backend / windows-backend 的 checkout 补 `fetch-depth: 0`
  （R136 注释）——浅检出会让 H3 在 CI 上失真；判据不许静默降级。
- 变异 **M1–M4 4/4** 咬合：第二条时间戳 run_id（2 红）、`exported_at`
  乱序（1 红）、假 run_id 条目即第二份账（1 红）、计数变字符串（1 红）；
  还原 sha256 一致。

## 2. 为什么是这一轮

索引 §6.2 说得很清楚：`history.json` 与 `git log --grep "CI run"` 是同一
份账的两个存放点——「第二份账」是这仓库几十轮登记的漂移根源（文档只写
「预计」不回改、索引 §1 数字过轮即陈旧都是同族病）。R133 把导航层交给
钉测、R135 把 CI 闸门清单交给钉测，这一轮轮到**账本与账本之间**：任何
一边多记、少记、改形状、乱顺序，都有判据当场红。

## 3. 实现

### 3.1 `tests/test_history_ledger_accounts.py`

- **H1 形状**：`source` 只允许 `'ci'`/`None`；`source='ci'` 与 legacy 的
  `ci-` 形状条目 run_id 必须匹配 `^ci-\d{8,}$`；五个计数字段必须是 int
  （bool 显式排除）；`passed+failed==total`（账内自洽）；`scenarios` 是
  带 `name/passed/attempts` 的 dict 列表。**时间戳形状的 run_id 恰好
  1 条且必须是第 1 条**——legacy 种子被点名钉住，新条目再以时间戳入库
  即红。
- **H2 账序**：run_id 全局唯一；`exported_at` 单调不减（乱序对逐一报出）。
- **H3 双账恰等**：对账集合按 **run_id 形状**取（不按 source 标注——
  6 条 R93 前的 legacy 条目没有 `source`，但同样有 bot 提交在账；标注是
  元数据，账是 run id 本身）。`git rev-parse --is-shallow-repository` 为
  true 时**判红**并给出 `git fetch --unshallow` 指引。
- **CI 配套**：backend（ubuntu-24.04）与 windows-backend 的 checkout 补
  `fetch-depth: 0`，注释写明 R136 依据；`e2e-history-writeback` job 原本
  就是 0（R95 起），replay 两 job 不跑 pytest 无需改。

### 3.2 刻意不做的

- **不核对 run 的测试结果对不对**（那是 R113 失败形状、R57 闸门判据的职责）；
- **不钉 history 长度**（每轮自然 +2，无魔法数——截断由 H3 的反向差额抓住）；
- **不重复 R83 的 `totals.runs` 内容复算**（已有锚点）；
- **不动 `record`/`writeback` 脚本**：账本形状对，脚本零改动。

## 4. 判据台账

- §10.13 同族补一段（账本对账判据：形状/账序/双账恰等；浅检出显式红），
  不新增编号判据。

## 5. 验证

- 定向：`tests/test_history_ledger_accounts.py` **3 passed**（0.10s）；
  CI 形状相关五文件合跑 52 passed（ci.yml 改动后既有钉测不破）。
- 本机全量：**2885 passed / 28 skipped / 0 failed**（2913 条，459.24s）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 第 5 条改为时间戳 run_id | 2 红（H1 种子唯一性 + H3） |
| M2 `exported_at` 相邻乱序 | 1 红（H2） |
| M3 追加 `ci-99999999999` 假条目（第二份账） | 1 红（H3 反向差额） |
| M4 `passed` 改字符串 | 1 红（H1） |

内存快照还原后 sha256 逐字节相同，4/4 咬合。
（M2 首版交换后仍是升序，被「先换再验」修正——变异必须真造成违例，
否则是假咬合；与 R128 的 M3 教训同族。）

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全绿；写回历史
  **65→66**。H3 首次在 CI 全历史检出上执行。
- 本篇 docs 回填提交预计 **66→67**。

## 7. 边界与遗留

- H3 依赖 git log 的提交主题格式 `record CI run <id>`：改格式必须同步本
  测试（与 R135 的步骤名判据同族）。
- 浅检出判红是**显式失败**而非 skip：本地开发者克隆过浅时按提示
  unshallow 即可；CI 已由本轮的 `fetch-depth: 0` 消除该形态。
- R137 预告（已实测）：索引 §1 的「当前用例」行在 R135 提交时写的
  2,909 与 R135 树收集数一致，但 R134 提交时写的 2,901 与该树实测
  2,903 已经漂过一次——下一轮把索引快照数字机械化的判据要处理
  「bot 提交落在提交与 CI 之间」的竞态（行值允许 N 或 N−1 的口径）。

## 8. 提交

- 改动：`tests/test_history_ledger_accounts.py`、`.github/workflows/ci.yml`
  （两处 `fetch-depth: 0` + 注释）、R136 文档、PROJECT_INFO、
  HANDOVER_INDEX。生产代码零改动。
