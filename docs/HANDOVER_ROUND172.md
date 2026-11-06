# DeterminFlow (xs2) 交接报告 — Round 172（收口轮：R169–R172 四账 + R173–R176 登记）

> 单 profile。四轮连推（十二）收口轮：四账审计 + 下一批主题实测登记。
> 本轮无新判据。R169–R171 三条判据全部首跑即过、生产代码零改动——
> 连续第五批（R153–R155、R157–R159、R161–R163、R165–R167、R169–R171）
> 呈现同一形态：候选制实测登记的边在钉住时都是对的。

## 1. 一句话结论

- R169–R171 全部完成：R169 npm 引用面（V5）；R170 `.env.example`
  环境模板（W15）；R171 compose 挂载点 ↔ config 目录（W16）。
- 三轮变异合计 **9/9**（R169 3 + R170 3 + R171 3 + R172 0——收口
  无新判据，无变异面）。
- §3 登记 **R173–R176**（全部先实测后登记）：Vite 开发代理端口
  （W17）、Dockerfile node 基础镜像 ↔ engines（P9）、desktop 版本双源
  （W18）、README 命令引用面（V6）。
- 总用例 3093 → **3099**（N3/D1 因本篇与 R171 回填 +2）。

## 2. 四账审计（R169–R172）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R169 / R170 / R171 / R172 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R169–R172 四条专述 bullet，H2「至 R172」 | 齐 |
| 判据台账 | §10.41（V5）/ §10.42（W15）/ §10.43（W16）/ §10.44（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R172（main、用例数、写回 80/80、R173–R176 登记） | 齐 |

三轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R169 | npm 引用面（V5） | 3089 | 3/3 | 第 80 条 |
| R170 | .env.example 模板（W15） | 3093 | 3/3 | 第 80 条 |
| R171 | compose 挂载点（W16） | 3097 | 3/3 | 第 80 条 |
| R172 | 收口 + R173–R176 登记 | 3099 | — | 第 80 条（本篇） |

## 3. 下一轮候选（R173–R176：全部先实测后登记）

- **R173 Vite 开发代理端口（W17）**：实测 `web/vite.config.ts` 的
  `server.proxy` 有两个目标——`/api` → `http://localhost:8020`、
  `/ws` → `ws://localhost:8020`；后端 config 的 `WEB_PORT` 默认值是
  8020。R165 的 W13 明确把开发代理留在射程外，这条边仍是第二份账：
  后端改端口而代理没改，`npm run dev` 下所有 API 调用连接拒绝。判据
  方向：两个 target 的端口都 == config 默认值；协议不参与。
- **R174 Dockerfile node 基础镜像 ↔ engines（P9）**：实测
  `Dockerfile` 的两级基础镜像——`node:22-alpine`（前端构建）与
  `python:3.12-slim`（运行时）；`web/package.json` 的 engines 是
  `>=22.12.0`。python 基础镜像已由 P3 覆盖（X.Y ∈ requires-python
  与 classifiers），**不重复**；P9 只钉 node 基础镜像的 major ==
  engines 的 major（22 == 22）——升级 engines 到 24 而忘了改
  Dockerfile，镜像仍跑旧 Node。判据方向：major 相等 + 语料守卫。
- **R175 desktop 版本双源（W18）**：实测 `desktop/package.json` 与
  `desktop/src-tauri/tauri.conf.json` 的 version 都是 **1.0.2**。
  R161 的 W12 只钉 pyproject ↔ `web/package.json`（0.1.0，核心版本）；
  desktop 是独立的发布版本线（1.0.x），两份清单必须同账——Tauri
  打包用的是 `tauri.conf.json`，npm 清单写另一个版本时安装器与
  关于页会各说各话。判据方向：两处都 X.Y.Z 且逐字相等。
- **R176 README 命令引用面（V6）**：实测两份 README 各 3 条可解析的
  文件引用——`python run.py`、`docker compose up --build`（默认
  compose 文件）、`docker compose -f docker-compose.yml config -q`；
  `run.py` 与 `docker-compose.yml` 都在磁盘。V3 已钉 `pip install -r`
  与 Dockerfile COPY 引用，V6 补「文档命令里的脚本/编排文件」这一面。
  判据方向：`python <file>.py` / `docker compose -f <file>` 的文件
  必须存在，`docker compose up` 要求默认文件存在；语料守卫至少 6 条
  引用（两份 README 各 3）。

## 4. 验证

- 无新判据，无新用例。定向回归（本轮动的全是文档 + 三条新判据的
  语料面）：S1–S6、L1–L8、N1–N3、B1–B2、D1–D2、P1–P8、V1–V5、
  W1–W16、M1–M5 全绿。
- 本机全量：**3071 passed / 28 skipped / 0 failed**（3099 条）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148/R156/R160/
  R164/R168 同型）。
- 连续五批（八/九/十/十一/十二）共 17 条新判据全部首跑即过——候选制
  「先实测后登记」把「钉住本来就对的账」变成了常态；判据的价值是保持。
- 生产默认值不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`af338ac`** 推送后 run **42165642447**：**10 job 全
  `success`**（04:58:49→05:17:09 UTC，约 18m20s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42165642447`，bot 提交 `4fe4722`）。R173 回填。

## 7. 提交

- 改动：R172 文档、R171 §6 回填、`HANDOVER_INDEX.md`（§1 六行 +
  H1 + §3 标题/一行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`
  （H2 + R172 一条）、`JUDGEMENT_LEDGER.md`（§10.44）。生产代码与
  测试零改动。
- `config/skills_config.json` 不纳入（C1）。
