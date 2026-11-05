# DeterminFlow (xs2) 交接报告 — Round 163（PROJECT_INFO 支持面行同账：Python/Node 下限）

> 单 profile。四轮连推（十）第 3 轮（R160 §7 登记）。PROJECT_INFO 是
> 支持面的**活文档第二份账**：§技术栈、§约束、§仓库结构里手抄的
> Python / Node 下限，此前无人对账——P4/P7 只钉 README，改
> requires-python / engines 时没人会记得改 PROJECT_INFO。本轮钉成
> **L8**（L 系的活文档扫描面早已覆盖 PROJECT_INFO，支持面行是它的
> 新子判据）。

## 1. 一句话结论

- `tests/test_living_doc_round_caps.py` 新增 **L8**（实测 R160 §7
  登记，首跑即过）：PROJECT_INFO 的全部「Python ≥X.Y」==
  requires-python 下限（实测 3 处全 3.11）；全部
  「node/Node.js ≥X.Y」== engines 下限（实测 2 处全 22.12）。集合
  恰等单一值——多出一处旧值即红；两类各自至少一处，否则显式红
  （判据不许空转）。
- 总用例 3067 → **3070**（+1 L8、N3/D1 因本篇与 R162 回填 +2）；
  变异 **2/2**。生产代码零改动。

## 2. 开工复核（实测 2026-11-06）

| 行 | 内容 |
|---|---|
| 438 §技术栈 | `Python ≥3.11（要求）` |
| 440 §技术栈 | `（node ≥22.12）` |
| 455 §仓库结构 | `# 项目元数据与依赖（Python ≥3.11）` |
| 476 §约束条件 | `Python ≥3.11；Node.js ≥22.12（web/package.json 的 engines）` |

## 3. 实现

- `PI_PY_FLOOR_RX`（`Python ≥X.Y`）与 `PI_NODE_FLOOR_RX`
  （`node/Node.js ≥X.Y`）扫全 PROJECT_INFO，各自汇成集合；判据
  要求集合 == {requires-python 下限} / {engines 下限}。
- 438 行的「本机 venv 实际为 Python 3.14.8」不带 `≥`，天然不在
  射程——L8 只钉**要求**面，不钉实测值。

## 4. 判据台账

- 新增 §10.35（L 系续：PROJECT_INFO 支持面行，L8），接在 §10.34
  之后；家族清单不变（仍是 L 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_living_doc_round_caps.py` **6 passed**
  （L1–L4 + L8）。
- 本机全量：**3042 passed / 28 skipped / 0 failed**（3070 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 §约束行 `Python ≥3.11` → `Python ≥3.12` | L8 红（文档 {3.11, 3.12} vs 下限 3.11），L1–L7 绿 |
| M2 §约束行 `Node.js ≥22.12` → `Node.js ≥22.11` | L8 红（文档 {22.11, 22.12} vs engines 22.12），L1–L7 绿 |

字节快照还原后 sha256 逐字节相同，2/2 咬合。

## 6. CI

- 提交 **`0380001`** 推送后 run **42102817053**：**10 job 全
  `success`**（20:22:48→20:40:09 UTC，约 17m21s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42102817053`，bot 提交 `4078392`）。R164 回填。

## 7. 边界与遗留

- L8 只钉「≥X.Y」要求面：3.14.8 之类的实测值与历史 bullet 里的
  版本叙述不在射程；`Python 3.11+`（加号写法）是 README 的 P4 面，
  PROJECT_INFO 用的是 ≥ 写法，两把正则互不越界。
- 四轮连推（十）下一轮 **R164 收口轮（R161–R164 四账）**：四账审计
  + 登记 R165–R168（先实测后登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_living_doc_round_caps.py`（L8）、R163 文档、
  R162 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R163 一条）、
  `JUDGEMENT_LEDGER.md`（§10.35）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
