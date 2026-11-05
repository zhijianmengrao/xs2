# DeterminFlow (xs2) 交接报告 — Round 154（索引 §1 CI 闸门行机械化：job 清单 / 矩阵展开 / 总数）

> 单 profile。四轮连推（八）第 2 轮：索引 §1 的最后一行手抄账——「CI
> 闸门 | 10 个 job（…）」——第一次与 ci.yml 对账。8 个顶层 job、两个
> 矩阵 job 各展开 2 个 run；展示行与工作流清单从此同账。

## 1. 一句话结论

- **实测索引行**：`10 个 job（backend / windows-backend / frontend /
  container-config / container-build / replay-ci-writeback ×2 /
  replay-ci-fetch-chain ×2 / e2e-history-writeback）`——8 个顶层 job
  键，两个 replay job 标 `×2`，展开后 10 个 job run。
- **此前的缺口**：I1 只钉 ci.yml 的 job 清单恰等与展开数，索引行本身
  无人对账——ci.yml 加一个 job、索引行没改，两本账照旧各自通过。
- 新增 `tests/test_index_snapshot.py` **S6**：行内总数 == 矩阵展开数、
  括号内顶层 job 名集合 == ci.yml 的 `jobs` 键、每项 `×k` == 该 job 的
  展开数（无 `×k` 视为 1）、各项声明数之和 == 总数。现状首跑即过。
- 总用例 3040 → **3043**（+1 S6、+1 N3 本篇、+1 D1 因 R153 进入扫描
  区间）；变异 **3/3** 咬合。生产代码零改动。

## 2. 为什么是这一轮

R149 把索引 §1 的五行钉死（S1–S5），只剩最后一行「CI 闸门」仍是手抄：

| 写入点 | 现状 | 判据 |
|---|---|---|
| ci.yml `jobs` 键 | 8 个顶层 job | I1（R135） |
| ci.yml 矩阵展开 | 10 个 job run | I1 的展开测试 |
| 索引 §1 CI 闸门行 | `10 个 job（… ×2 …）` | 无 |

「10 个 job」有两种读法：8 个顶层键、10 个矩阵展开后的 run。行里把
两者混写在一起，读者只能靠括号里的 `×2` 自己算。CI 加/删一个 job 时，
ci.yml 与 I1 会红，索引行却可能停在旧数——这正是「第二份账」的缺口。

## 3. 实现

### 3.1 `tests/test_index_snapshot.py`（S6）

- 行解析：`N 个 job` 取总数；第一个全角括号内的内容按 `/` 切分，每项
  用 `name [×k]` 解析；无 `×k` 视为 1。
- 实际展开：读 ci.yml 的 `jobs`；`strategy.matrix.include` 非空时按
  其长度展开，`matrix.os` 是列表时按列表长度，否则 1。
- 对齐三面：名集合、每项展开数、总数。任一面漂移都红；同名重复也红。
- 自洽：各项声明数之和 == 行内总数，防「列表对、总数错」。

| 判据 | 内容 | 锚点 |
|---|---|---|
| S6 | 总数 == 展开数；名集合 == ci.yml jobs 键；每项 `×k` == 该 job 展开数；各项之和 == 总数 | 索引行 + ci.yml |

I1 仍然钉「ci.yml 恰有 8 个顶层 job、展开 10 个 run」；S6 钉的是索引
行这份展示账与 ci.yml 同账。两者分工：I1 判工作流本身，S6 判第二份账。

### 3.2 实测（2026-11-05）

| 项 | 值 |
|---|---|
| 索引行总数 | 10 |
| 索引行顶层 job 名 | 8 个，与 ci.yml `jobs` 键集合相等 |
| `×2` 项 | replay-ci-writeback / replay-ci-fetch-chain，各 2 |
| ci.yml 展开 | 8 个顶层键 + 2 个矩阵 job 各多 1 = 10 |
| S6 首跑 | 通过 |

### 3.3 刻意不做的

- 不把 `10` 写成常量：新增 job 时 ci.yml、索引行与 I1 清单必须同时改，
  S6 只判「行 == ci.yml」；
- 不要求索引行的排列顺序与 ci.yml 一致（展示行按可读性分组）；
- 不判 job 的业务输出与步骤内容（I2/闸门脚本自己的判据）；
- 不解析 `strategy.matrix` 的表达式形态（`fromJSON` 等）——当前是
  字面量映射，遇到未知形态显式红，不静默漏判。

## 4. 判据台账

- 新增 §10.26（S 系续：索引 §1 CI 闸门行，S6），接在 §10.25 之后；
  家族清单不变（仍是 S 系）；编号表仍 18 条（S 系未编号）。

## 5. 验证

- 定向：`tests/test_index_snapshot.py -k ci_gate` **1 passed**。
- 相关回归：`test_ci_workflow_inventory.py`（I1–I2）、
  `test_ci_gate_wiring.py`、`test_readme_parity.py`（M1–M4）同跑。
- 本机全量：**3015 passed / 28 skipped / 0 failed**（3043 条，557.97s；
  带 `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.symlinks
  GIT_CONFIG_VALUE_0=true` 覆盖）。首跑 3014 passed / 1 failed 只因 §5
  编辑后没重算索引体量行（S4）；重算后复跑全绿——与 R149 的教训同因。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 索引行 `frontend` 改成 `front-end` | S6 红（名集合多一个、缺一个），S1–S5 绿 |
| M2 索引行删掉 `replay-ci-writeback ×2` 的 ` ×2` | S6 红（行写 ×1 vs 展开 2），S1–S5 绿 |
| M3 索引行总数 `10` 改成 `9` | S6 红（总数 vs 展开 10），S1–S5 绿 |

字节快照还原后 sha256 逐字节相同，3/3 咬合（三条变异都只打索引行，
S1–S5 全绿——S6 与其余五行互不串扰）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R155 回填。

## 7. 边界与遗留

- S6 只读 ci.yml 与索引行；矩阵 job 的平台集合仍由 I1 钉住（ubuntu-
  24.04 / windows-latest），S6 不重复。
- 索引行把「顶层 job 键」与「矩阵展开后的 run」写在同一个数字里，
  S6 用括号里的 `×k` 还原两者关系；行内总数永远是展开数。
- 下一轮 R155：两份锁的生成头 `--python-version` ↔ `requires-python`
  下限同账（R152 §7 登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_index_snapshot.py`（S6）、R154 文档、R153 §6 回填、
  `HANDOVER_INDEX.md`（§1 五行 + H1 + §3 标题/阶段行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R154 一条）、`JUDGEMENT_LEDGER.md`
  （§10.26）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
