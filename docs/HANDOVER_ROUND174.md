# DeterminFlow (xs2) 交接报告 — Round 174（Dockerfile node 基础镜像 ↔ engines：P9）

> 单 profile。四轮连推（十三）第 2 轮：前端构建阶段的 Node 基础镜像
> 第一次与 `engines.node` 对账。生产代码零改动；P9 首跑即过，变异 2/2。

## 1. 一句话结论

- **实测**：`Dockerfile` 的 `FROM node:22-alpine`（前端构建阶段）与
  `web/package.json` 的 `engines.node = ">=22.12.0"` major 同为 22；
  python 基础镜像 `FROM python:3.12-slim` 已由 P3 覆盖（X.Y ∈
  requires-python 与 classifiers），P9 不重复。
- `tests/test_python_support_surface.py` 新增 **P9a/P9b**：node 基础镜像
  可解析且 major 唯一；major == engines major。总用例 3103 → **3107**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R173 进入扫描区间）。
- 变异 **2/2**：`node:22-alpine`→`node:24-alpine`（major 不同账）/
  删除 node `FROM`（语料守卫红）。

## 2. 为什么是这一轮

R157 的 P7 把 README 的 Node 下限与 workflow 的 `node-version` 钉到
`engines`；R151 的 P3 把 Dockerfile 的 **python** 基础镜像钉到
requires-python / classifiers。**node 基础镜像**是唯一没有对账的容器
声明面：升级 `engines` 到 24 而忘了改 Dockerfile，镜像仍按 Node 22
构建前端；反过来把 Dockerfile 升到 24 而 `engines` 仍是 22，构建产物
可能用了 24 才有的特性，而本地/CI 的 Node 22 跑不了。

P9 的锚选在「`FROM node:<major>`」：major 是唯一稳定的兼容边界
（`node:22-alpine` 是 floating minor，`engines` 的 minor 只用于下限，
不参与 major 对账）；两级构建的 node base 必须唯一。

## 3. 实现

### 3.1 `tests/test_python_support_surface.py`（P9a / P9b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| P9a | Dockerfile 至少一个 `FROM node:<major>`，且所有 node base 的 major 唯一；`engines.node` 可解析 | `FROM node:` 行 + `engines.node` |
| P9b | 每个 node base 的 major == `engines.node` 的 major | 同上 |

实现要点：

- 复用 P7 的 `_node_floors()` 解析 `engines`（`>=X.Y.0`），不重复写
  解析逻辑；解析不到显式红。
- `FROM node:<major>` 允许 `-alpine` / `-slim` 等后缀；只取 major 数字。
- python base 不在 P9 射程：P3 已覆盖，重复钉会把同一条账记两次。

## 4. 验证

- 定向：`tests/test_python_support_surface.py` 全绿（P1–P9）。
- 本机全量：**3079 passed / 28 skipped / 0 failed**（3107 条，约 10 分钟）。
- 变异 **2/2**：

| 变异 | 结果 |
|---|---|
| M1 `node:22-alpine`→`node:24-alpine` | P9b 红，P9a 绿 |
| M2 删除 `FROM node:22-alpine` 行 | P9a 红（P9b 同时无锚） |

两次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 major：不判 floating minor（`node:22-alpine` 不带 minor）、
  不判 python base（P3 负责）、不判镜像 digest / 发行版（`-alpine`
  与 `-slim` 是打包选择）。
- 四轮连推（十三）余下 **R175 desktop 版本双源（W18）** 与
  **R176 README 命令引用面（V6）** 已登记，待下一轮执行。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`5b40b09`** 推送后 run **42172719808**：**10 job 全
  `success`**（06:10:03→06:22:37 UTC，约 12m34s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42172719808`，bot 提交 `3a817ea`）。R175 回填。

## 7. 提交

- 改动：`tests/test_python_support_surface.py`（P9）、R174 文档、
  R173 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R174 一条）、
  `JUDGEMENT_LEDGER.md`（§10.46）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
