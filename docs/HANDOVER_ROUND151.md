# DeterminFlow (xs2) 交接报告 — Round 151（Python 支持面同账：CI / Dockerfile / classifiers / README）

> 单 profile。四轮连推（七）第 3 轮：Python 支持面的四处声明第一次互相
> 对账。实测 3.14 是 Windows 权威 CI，却不在 classifiers——补上一条
> 元数据；CI 矩阵、Dockerfile 与 README 下限从此都有判据把守。

## 1. 一句话结论

- **实测四处声明**：`pyproject requires-python = ">=3.11"`、classifiers
  3.11/3.12；CI 的 ubuntu backend 与三个桌面 workflow 声明 3.11、
  windows-backend（Windows 权威基线）声明 **3.14**；`Dockerfile`
  `FROM python:3.12-slim`；`README.md` / `README.en.md` 写「Python 3.11+」。
- **3.14 是权威 CI，却不在 classifiers**——PyPI 元数据宣称的支持面与
  实际测试面不一致；README 的下限也是手抄，改 requires-python 时没有
  任何判据会提醒。
- 新增 `tests/test_python_support_surface.py` 四条 **P 系判据**：P1 语料
  守卫、P2 CI → 范围 + classifiers、P3 Dockerfile → 范围 + classifiers、
  P4 README 下限 == requires-python 下限。修法只有一处：补
  `Programming Language :: Python :: 3.14`。总用例 3026 → **3032**
  （+4 钉测、+1 N3 本篇、+1 D1 因 R150 进入扫描区间）。
- 变异 **M1–M4 4/4** 咬合且相互隔离。

## 2. 为什么是这一轮

Python 支持面有四个写入点，此前各自独立：

| 写入点 | 现状 | 判据 |
|---|---|---|
| `pyproject requires-python` | `>=3.11` | 无 |
| `pyproject classifiers` | 3.11 / 3.12 | 无 |
| CI `python-version` | 3.11（ubuntu + 桌面）/ 3.14（Windows 权威） | 无 |
| `Dockerfile` | `python:3.12-slim` | 无 |
| README / README.en | 「Python 3.11+」 | 无 |

`classifiers` 是唯一会进 PyPI 元数据的声明；它写少了，安装器不会报错，
只是支持面被静默缩小。3.14 已经在 CI 上跑全量，元数据却不说——这是
「第二份账」里最典型的漏记。反方向（README 下限）同理：改
requires-python 而忘了 README，用户看到的下限就是旧的。

## 3. 实现

### 3.1 `tests/test_python_support_surface.py`（P1–P4）

| 判据 | 内容 | 锚点 |
|---|---|---|
| P1 | requires-python 有 `>=X.Y` 下限；classifiers 至少一个 X.Y；CI 至少一个 `python-version`；Dockerfile 有 `FROM python:X.Y…`；两份 README 各有一个「Python X.Y+」 | 四处声明 |
| P2 | 每个 workflow 的每个 `python-version` ∈ requires-python 范围且 ∈ classifiers | 范围 + classifiers |
| P3 | Dockerfile 的 python X.Y 同样 ∈ 范围与 classifiers | 范围 + classifiers |
| P4 | README.md / README.en.md 的「Python X.Y+」下限 == requires-python 下限 | README 文本 |

实现要点：

- **只判声明面**：replay 矩阵里的 `python: python3` / `python` 是解释器
  名，不是版本声明，不参与 P2；`python-version-file` 一旦出现显式红，
  不静默漏判。
- **P1 是语料守卫**：任何一处解析为空都在此红，防止 P2–P4 在空集合上
  空转。
- **不要求 classifier 都被 CI 覆盖**：3.12 由 Dockerfile 覆盖，3.11 由
  ubuntu/桌面覆盖；判据只保证「跑过的版本都声明了」。
- **README 两份都判**：中文与英文是两处写入点，漏一处就是半份声明。

### 3.2 实测与修正（2026-11-05）

| 位置 | 修前 | 修后 |
|---|---|---|
| classifiers | 3.11 / 3.12 | 3.11 / 3.12 / **3.14** |
| CI 3.14 | 不在 classifiers | 通过 |
| Dockerfile 3.12 | 已在 classifiers | 通过 |
| README 下限 3.11 | == requires-python | 通过 |

P2 首跑当场红在 `ci.yml: 3.14 不在 classifiers`；补一条元数据后四条全绿。
这正是「权威 CI 已跑、元数据没说」的形状——不是运行时缺陷，是声明账。

### 3.3 刻意不做的

- 不把 `requires-python` 收窄到 `>=3.11,<3.15`：当前没有上界，判据不
  发明政策；
- 不要求 classifiers ⊆ CI（3.12 没有 backend job，由容器构建覆盖）；
- 不解析 `setup-python` 的缓存键、镜像 digest 等实现细节；
- 不判 README 里其他运行时版本（Node 22.12+ 与 `web/package.json`
  engines 同账留作候选）。

## 4. 判据台账

- 新增 §10.23（P 系：Python 支持面，P1–P4），接在 §10.22 之后；
  家族清单 +P。

## 5. 验证

- 定向：`tests/test_python_support_surface.py` **4 passed**。
- 相关回归：`test_dependency_sources.py`（W3–W11）、
  `test_ci_workflow_inventory.py`（I1–I2）、`test_index_snapshot.py`
  （S1–S5）、`test_living_doc_round_caps.py`（L1–L4）、
  `test_handover_ci_backfill.py`（D1–D2）同跑。
- 本机全量：**3004 passed / 28 skipped / 0 failed**（3032 条，993.43s；
  带 `GIT_CONFIG_COUNT=1 … core.symlinks=true` 覆盖）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 删 3.14 classifier | P2 红，其余 3 绿 |
| M2 CI 3.14→3.13 | P2 红，其余 3 绿 |
| M3 Dockerfile 3.12→3.10 | P3 红，其余 3 绿 |
| M4 README 下限 3.11+→3.12+ | P4 红，其余 3 绿 |

字节快照还原后 sha256 逐字节相同，4/4 咬合。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗首次滚动：追加后裁剪最旧一条，history 仍 80
  条）。R152 回填。

## 7. 边界与遗留

- **满窗滚动（R152）**：R150 的写回让 history 到 80 条（满格）；本轮
  的写回会首次裁掉最旧一条，计数不再递增。§6 因此改用「第 N 条」而不是
  `A→B`；R152 的 D2 必须同时认两种写法，并按 bot 提交当时的快照对账。
- README 徽章仍写 `Python-3.11`（展示层，不随下限自动变）；P4 只判
  正文的「3.11+」下限。
- 桌面 workflow 的 3.11 与 backend 的 3.11 是两处独立声明，P2 分别报红。

## 8. 提交

- 改动：`tests/test_python_support_surface.py`（P1–P4）、`pyproject.toml`
  （3.14 classifier）、R151 文档、R150 §6 回填、`HANDOVER_INDEX.md`（§1
  五行 + H1 + §3 标题/阶段行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`
  （H2 + R151 一条）、`JUDGEMENT_LEDGER.md`（§10.23）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
