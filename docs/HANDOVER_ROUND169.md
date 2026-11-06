# DeterminFlow (xs2) 交接报告 — Round 169（npm 引用面：V5）

> 单 profile。四轮连推（十二）第 1 轮：CI 与 Dockerfile 里的 npm 引用
> 第一次变成机判。生产代码零改动；V5 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：三份 workflow 共 7 处 `npm run` / `npm test` 引用，加
  `Dockerfile` 的 1 处，合计 **8 处**；`npm ci` 共 **6 处**。8 处全部
  命中 `web/package.json`（13 个 scripts）或 `desktop/package.json`
  （4 个 scripts），两份 `package-lock.json` 都在磁盘。
- 新增 `tests/test_npm_references.py` 两条 **V 系续判据**：V5a 脚本引用
  可解析（按 `working-directory` / `cd` / Dockerfile `WORKDIR` 推进）、
  V5b 每个 `npm ci` 目录有锁文件。总用例 3085 → **3089**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R168 进入扫描区间）。
- 变异 **3/3**：删 web 的 `lint` script / 改 ci.yml 的 `lint` 引用 /
  删 web 的 lockfile，V5a 与 V5b 各自独红。

## 2. 为什么是这一轮

CI 里的 `npm run lint` 与 `npm test` 是两道真实闸门，`npm run build` 是
前端与桌面打包的共同入口；Dockerfile 的 `npm ci` / `npm run build` 决定
镜像里的前端产物。这些名字都是字符串，改名或换目录后：

- `npm run <缺失脚本>` 只在跑到那个 job 时才报错；desktop 两条发布
  流水线不在每个 PR 上跑，错误可能潜伏到发版；
- `npm ci` 没有 lockfile 会直接失败，但失败点远在构建阶段，且
  `package-lock.json` 被误删时 `package.json` 本身仍然合法。

V5 的锚选在「引用点的工作目录」：workflow 的 `working-directory`、
run 脚本里的 `cd <dir>`、Dockerfile 的 `WORKDIR`。同一个 `build` 在
`web/` 与 `desktop/` 是两份不同的 scripts，只有按目录解析才能对账。

## 3. 实现

### 3.1 `tests/test_npm_references.py`（V5a / V5b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| V5a | 每个 `npm run <script>` / `npm test` 必须命中该 step 工作目录下 `package.json` 的 scripts 键；工作目录按 `working-directory` → `cd` 顺序 → Dockerfile `WORKDIR` 推进（`/app/<x>` 映射回仓库 `<x>`）。至少 8 处引用的语料守卫 | `package.json` 的 scripts 映射 |
| V5b | 每个 `npm ci` 的工作目录必须有 `package-lock.json`。至少 6 处 `npm ci` 的语料守卫 | 锁文件存在性 |

实现要点：

- workflow 的 run 脚本按 `;` / 换行切分，`cd <dir>` 只影响其后的命令；
  `cd` 到仓库外显式红。
- `npm test` 是裸命令，映射到 scripts 键 `test`；`npm run build:macos`
  保留冒号后缀，不做前缀匹配。
- Dockerfile 按 `WORKDIR` 推进；当前 npm 命令都在 `/app/web` 阶段，
  映射回 `web/`。

## 4. 验证

- 定向：`tests/test_npm_references.py` 2 passed（0.14s）。
- 本机全量：**3061 passed / 28 skipped / 0 failed**（3089 条，约 10 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 删除 web 的 `lint` script | V5a 红，V5b 绿 |
| M2 ci.yml `npm run lint`→`npm run lnt` | V5a 红，V5b 绿 |
| M3 删除 web/package-lock.json | V5b 红，V5a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 npm 引用与 lockfile 存在：不判脚本内部命令、不判依赖版本与锁
  一致性（`npm ci` 自带完整性闸门）、不判 workflow 的矩阵/条件是否
  真的会跑到（CI 平台语义不在仓库内）。
- `npm install`（非 ci）不判——它不要求锁文件，也不在 CI 路径上。
- 四轮连推（十二）下一轮 **R170 `.env.example` 环境模板（W15）**。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`7ef1ded`** 推送后 run **42156626644**：**10 job 全
  `success`**（03:27:05→03:44:55 UTC，约 17m50s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42156626644`，bot 提交 `78ab6a3`）。R170 回填。

## 7. 提交

- 改动：`tests/test_npm_references.py`、R169 文档、R168 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R169 一条）、
  `JUDGEMENT_LEDGER.md`（§10.41）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
