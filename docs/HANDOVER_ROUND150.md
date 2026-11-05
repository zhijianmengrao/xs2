# DeterminFlow (xs2) 交接报告 — Round 150（双锁闭包同账：runtime lock ⊆ dev lock）

> 单 profile。四轮连推（七）第 2 轮：两份 uv 闭包——CI 装的 dev 锁与
> Docker/桌面装的运行时锁——第一次互相对账。生产代码零改动；实测 81 包
> 全部包含、0 个钉版漂移，补的是「闭包之间无人对账」这条缝。

## 1. 一句话结论

- **实测**：`requirements.lock` **81 包**、`requirements-dev.lock` **84 包**；
  运行时锁 81/81 全部在 dev 锁里（按名归一），共享的 **81 包钉版 0 漂移**；
  dev 独有 3 包（`pytest` / `pluggy` / `iniconfig`）。没有现行漂移。
- W8/W9 只钉「顶层声明 → 对应锁」的两条边：dev 锁少一个运行时闭包里的
  传递依赖、或两份锁把同一个包钉成两个版本，W8/W9 都不会红——而 CI 与
  Docker 会在两个环境里跑出不同依赖。
- 新增 `tests/test_dependency_sources.py` 两条 **W 系续判据**：W10 运行时
  锁按名 ⊆ dev 锁；W11 共享包钉版逐字相等。总用例 3022 → **3026**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R149 进入扫描区间）。
- 变异 **M1–M2 2/2** 咬合且相互隔离（删 `six` → 只红 W10；改 `six` 钉版
  → 只红 W11）。

## 2. 为什么是这一轮

依赖账在 R145 已经四源同账（pyproject / requirements / requirements-dev /
双锁），但四条边都只从**顶层声明**出发：

- W8：requirements-dev.txt（20 个直接依赖）→ dev 锁；
- W9：requirements.txt（19 个直接依赖）→ 运行时锁。

两份锁各自是完整闭包（81 / 84 包），其中 61 个传递依赖没有任何判据
比较过。真实的故障形态不是「顶层漏了」——那会被 W8/W9 咬住——而是：

1. 运行时锁里某个传递依赖（比如 `six`）在 dev 锁里消失：CI 的测试环境
   不装它，本机全量绿，Docker 启动时才 `ModuleNotFound`；
2. 同一个传递依赖在两份锁里钉成不同版本：CI 与镜像跑的不是同一套代码，
   而两份锁各自都「自洽」。

W10/W11 把这两条钉在**闭包之间**，锚点就是两份生成文件本身。

## 3. 实现

### 3.1 `tests/test_dependency_sources.py`（W10–W11）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W10 | `set(requirements.lock) − set(requirements-dev.lock)` 为空（`canonicalize_name` 归一） | 两份锁的包名集合 |
| W11 | 两份锁共享包的 `==` 钉版逐字相等 | 两份锁的钉版 |

实现要点：

- **只对账交集**：不要求 dev 闭包的独有集合等于登记表；`pytest` /
  `pluggy` / `iniconfig` 随 pyproject dev extra 变动，登记它们只会制造
  第四份账。
- **环境标记行整行接受**：`cffi==2.1.0 ; platform_python_implementation !=
  'PyPy'` 的钉版仍参与比较，标记不参与；锁是 universal 编译产物，标记
  是闭包的一部分。
- **W11 先断言 shared 非空**：两份锁若因解析失败变成空表，W11 不能
  静默通过——空交集上的「0 漂移」是假绿。

### 3.2 实测（2026-11-05）

| 项 | 值 |
|---|---|
| `requirements.lock` | 81 包 |
| `requirements-dev.lock` | 84 包 |
| 共享 | 81 包（运行时锁全部） |
| 共享包钉版漂移 | 0 |
| dev 独有 | `pytest` / `pluggy` / `iniconfig` |

当前无漂移，本轮补的是防复发：任何一边单独重生成锁、或手工改一行
钉版，W10/W11 都会在 CI 上直接点名包名与两个版本。

### 3.3 刻意不做的

- 不要求 dev 锁 ⊆ 运行时锁（反方向不成立：dev 独有 3 包是设计）；
- 不登记 dev-only 允许集：它随 dev extra 变，登记等于把 pyproject 抄一遍；
- 不判锁文件的生成命令与 `--python-version`（生成参数同账留作候选）；
- 不判 `uv.lock`（R148 已决定维持排除）。

## 4. 判据台账

- 新增 §10.22（W 系续：双锁闭包，W10–W11），接在 §10.21 之后；
  家族清单不变（仍是 W 系）。

## 5. 验证

- 定向：`tests/test_dependency_sources.py` **9 passed**（W3–W11）。
- 相关回归：`test_dependency_locks.py`、`test_requirements_lock_sync.py`、
  `test_desktop_packaging.py`、`test_living_doc_round_caps.py`（L1–L4）、
  `test_index_snapshot.py`（S1–S5）、`test_handover_ci_backfill.py`
  （D1–D2）同跑。
- 本机全量：**2998 passed / 28 skipped / 0 failed**（3026 条，1035.28s；
  带 `GIT_CONFIG_COUNT=1 … core.symlinks=true` 覆盖）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 dev 锁删掉 `six==1.17.0` | W10 红，其余 8 绿 |
| M2 dev 锁 `six` 1.17.0→1.16.0 | W11 红，其余 8 绿 |

字节快照还原后 sha256 逐字节相同，2/2 咬合。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **79→80**。R151 回填。

## 7. 边界与遗留

- 两份锁都是 `uv pip compile` 的产物；手工改锁仍可能绕过 W3 的「全部
  `==`」形状（例如写成范围），但会被 W3 当场红。
- **满窗滚动（R152）**：R149 的写回让 history 到 79 条，R150 的写回
  到 80 条——窗口在本轮之后满格；R151 的写回会让 `record` 首次裁掉
  最旧条目。D2/H3 的「当前下标/集合」口径届时会误判正确声明，R152
  收口轮必须改成按 bot 提交当时的快照对账。

## 8. 提交

- 改动：`tests/test_dependency_sources.py`（W10–W11）、R150 文档、
  R149 §6 回填、`HANDOVER_INDEX.md`（§1 五行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R150 一条）、
  `JUDGEMENT_LEDGER.md`（§10.22）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
