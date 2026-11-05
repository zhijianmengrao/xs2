# DeterminFlow (xs2) 交接报告 — Round 145（依赖四源同账：pyproject / requirements-dev / 双锁）

> 单 profile。五轮连推（六）第 2 轮：R143 的 W1/W2 只把守
> `requirements.txt ↔ requirements-dev.lock` 一条边；本轮把 pyproject、
> requirements-dev.txt 与运行时锁 `requirements.lock` 也接进同一张账。
> 生产代码零改动。

## 1. 一句话结论

- **实测缺口**：依赖账有四个写入点，此前只有一条边有判据。R143 的 W1/W2
  钉住 requirements.txt → requirements-dev.lock；**pyproject 的 17 个钉版
  是否都在 requirements.txt、requirements-dev.txt 的 `-r` 展开是否恰等于
  requirements ∪ dev extra、requirements.txt 是否被运行时锁覆盖**，三处全
  无人把守。实测当前四源一致（无漂移），缺的是防复发。
- 新增 `tests/test_dependency_sources.py`（7 条，**W3–W9 判据**）：
  W3 语料守卫（四源非空、全 `==` 钉版、`-r` 递归展开且冲突当场红）；
  W4 pyproject ⊆ requirements 名字覆盖；W5 钉版逐字同账；W6
  requirements 独有包恰等于显式允许集（tzdata / uvicorn-worker）；
  W7 展开后的 requirements-dev == requirements ∪ dev extra；
  W8 requirements-dev ⊆ dev lock；W9 requirements ⊆ runtime lock。
- 实测四源规模：pyproject 17 / requirements 19 / dev extra 1 /
  requirements-dev 展开 20 / requirements.lock 81 / requirements-dev.lock 84
  ——四条边全部成立（17/17、2/2、19+1、20/20、19/19）。总用例 2995 →
  **3004**（新增 7 条 + R145 文档本身触发的 D1/N3 各 +1）。
- 变异 **M1–M5 5/5** 咬合（pyproject 钉版漂移、requirements-only 未登记、
  dev 丢 `-r`、dev 锁钉版漂移、运行时锁漏包），每条只红对应用例。

## 2. 为什么是这一轮

R143 收官时把依赖账写成「双源」，实际只覆盖了开发者安装路径的一半：
`requirements.txt` 与 CI 的锁对上了，但**打包元数据**（pyproject）与
**开发顶层依赖**（requirements-dev.txt）各自还有一份清单。三条边各有
现成的事故形态：

- pyproject 加了包、requirements.txt 没加 → `pip install -e .` 能装、
  `pip install -r requirements.txt` 装不上，本地与 CI 分叉；
- requirements-dev.txt 升了 pytest、pyproject dev extra 没跟 → `pip
  install -e .[dev]` 与 `-r requirements-dev.txt` 装出两个版本；
- requirements.txt 升了包、只刷 dev 锁不刷 runtime 锁 → Dockerfile 与
  桌面管线仍装旧版本，镜像启动时才炸。

四条边此前都没有判据（R143 只覆盖了 requirements → dev lock 这一条）；本轮
按「改了就必须连动另一份清单」的字面把它们钉住。与 R143 同族：不判闭包
内部（锁文件是超集是常态），只判**顶层声明在每一份账上都能对上**。

## 3. 实现

### 3.1 `tests/test_dependency_sources.py`（W 系续）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W3 | 六份语料（pyproject 运行时/dev extra、requirements、requirements-dev 展开、双锁）非空且每项 `==` 钉版；`-r` 递归展开，重复声明版本冲突即红 | 解析结果：空 / 范围规格 / 同名异版 |
| W4 | pyproject 每个运行时依赖（extras 剥离、`canonicalize_name` 归一）都在 requirements.txt | 包名字面 |
| W5 | 同一包在 pyproject 与 requirements.txt 的 `==` 钉版逐字相等 | 版本字面 |
| W6 | `requirements.txt − pyproject` **恰等于** `REQUIREMENTS_ONLY`（`tzdata==2026.3`、`uvicorn-worker==0.4.0`），且钉版与登记值相同 | 显式允许集（双向恰等） |
| W7 | 展开 `-r` 后的 requirements-dev == requirements.txt ∪ pyproject dev extra（名字 + 钉版） | `-r` 展开结果 |
| W8 | requirements-dev 每个包都在 requirements-dev.lock，钉版同账 | CI 实际安装源 |
| W9 | requirements 每个包都在 requirements.lock，钉版同账 | Dockerfile / 桌面管线安装源 |

实现要点：

- 统一用 `packaging.requirements.Requirement` 解析，`canonicalize_name`
  归一（`uvicorn_worker` → `uvicorn-worker`、extras 剥离）；不比 R143 的
  正则解析更宽松，但能正确处理环境标记行。
- `-r` 递归展开按文件所在目录解析，展开时同名异版直接抛错——避免
  「后写覆盖前写」把冲突吞掉。
- W6 采用双向恰等：新增 requirements 独有包必须登记，删除后登记表也必须
  连动——允许集不会自己腐烂。
- 首版 M2 变异选 `six` 失败：`six` 是锁文件里的传递依赖，补进 requirements
  后锁文件出现重复声明，W3 先红。改用 `tabulate`（两份锁都不存在）后
  隔离成功——变异设计也要避开闭包里的名字。

### 3.2 实测四源（2026-11-05 开工）

| 源 | 规模 | 钉版 |
|---|---|---|
| `pyproject.toml [project].dependencies` | 17 | 17/17 `==` |
| `pyproject.toml [project.optional-dependencies].dev` | 1（pytest） | 1/1 |
| `requirements.txt` | 19 | 19/19 |
| `requirements-dev.txt`（`-r` 展开） | 20 | 20/20 |
| `requirements.lock` | 81 | 81/81 |
| `requirements-dev.lock` | 84 | 84/84 |

四条边的实测结果：pyproject ⊆ requirements **17/17** 且钉版 0 漂移；
requirements-only **恰为 2 个**登记包；dev 展开 **== 19+1**；dev → dev lock
**20/20**；requirements → runtime lock **19/19**。没有需要修的现行漂移——
本轮补的是「没有判据」本身。

### 3.3 刻意不做的

- 不要求锁文件 ⊆ 顶层声明：lock 是传递闭包，超集是常态；
- 不判 `build-system.requires`（`setuptools>=77`、`wheel`）：构建隔离环境
  自管，且是范围规格；
- 不判 `uv.lock`：仓库内零引用（CI/Docker/scripts 均不读它），见 §7；
- 不判环境标记（`; sys_platform …`）：按整行接受，平台差异不属于同账。

## 4. 判据台账

- 新增 §10.17（W 系续：依赖四源同账，W3–W9），接在 §10.16 之后；
  家族清单不变。

## 5. 验证

- 定向：`tests/test_dependency_sources.py` **7 passed**（0.12s）。
- 相关回归：`test_requirements_lock_sync.py`（W1/W2）、
  `test_dependency_locks.py` 同时绿。
- 本机全量：**2976 passed / 28 skipped / 0 failed**（3004 条，554.89s；
  带 `GIT_CONFIG_COUNT=1 … core.symlinks=true` 覆盖）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 pyproject `openai==2.44.0` → `2.44.1` | W5 红，其余 6 绿 |
| M2 requirements + 双锁补 `tabulate==0.9.0`（不登记） | W6 红，其余 6 绿 |
| M3 requirements-dev 删 `-r requirements.txt` | W7 红，其余 6 绿 |
| M4 dev lock `pytest==9.1.1` → `9.1.0` | W8 红，其余 6 绿 |
| M5 runtime lock 删 `httpx==0.28.1` | W9 红，其余 6 绿 |

内存快照还原后 sha256 逐字节相同，5/5 咬合（每条只红对应用例）。

## 6. CI

- 提交推送后 run `<run1>`：10 job 预计全绿；写入历史 **74→75**。
- 本篇 §6 由 R146 回填（单跑轮次制）。

## 7. 边界与遗留

- **`uv.lock` 是未被引用的第五份锁**：87 个包、包含 pyproject 的 17 个
  依赖，但 `.github/`、`scripts/`、Dockerfile、桌面管线全部零引用——CI 与
  本地安装都走 requirements*.lock。本轮不把它接进判据（接进来等于给一份
  没人读的文件上锁）；**删除或接入留 R148 收口决定**。
- **R146 的实测起点**（本轮收尾复核）：`PROJECT_INFO` H2「至 R133」；
  索引 H1「R24–R131」；§4 H2「R24–R134」；§6.1「R24–R134」；§3 标题
  「106 份文档的骨架」；§3 的 R135–R139 行尾仍写「R140–R143 已登记」；
  §6.4.3「42/109」；§6.4.4「38/107」；§1「判据登记 19 条」。本轮新增
  §10.17 后该行更旧——R146 用机判统一。
- **本机全量前提不变**：全局 `core.symlinks=false` 时需
  `GIT_CONFIG core.symlinks=true` 重跑（R144 登记）；CI ubuntu 原生通过。
- **轮次盖子不属本轮**：索引 §1 的三行由 S1–S3 强制，已翻到 120 份 /
  3004 / 74；其余「至 R<n>」与份数叙述留给 R146。

## 8. 提交

- 改动：`tests/test_dependency_sources.py`、R145 文档、R144 §6 回填、
  `HANDOVER_INDEX.md`（§1 三行 + 代码基线 + §3 阶段行 + §4 一行）、
  `PROJECT_INFO.md`（R145 一条）、`JUDGEMENT_LEDGER.md`（§10.17）。
  生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
