# DeterminFlow (xs2) 交接报告 — Round 183（前端构建输出目录同账：W21）

> 单 profile。四轮连推（十五）第 3 轮：Vite 产物目录与两处后端读取点
> 第一次做成三处同账。生产代码零改动；W21 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：`web/vite.config.ts` 没有 `build.outDir`（有效值 = Vite 默认
  `dist`）；`run.py` 的 `dist_dir = web_dir / "dist"`；`src/web_server.py`
  的 `web_dist = BASE_DIR / "web" / "dist"`。三处当前同账，但没有任何
  判据盯着。
- `tests/test_frontend_build_output.py` 新增 **W21a/W21b**：语料守卫
  （Vite 至多一处 `outDir`、两处后端路径各恰一处）+ 三值逐字相等。
  总用例 3137 → **3141**（+2 钉测、+1 N3 本篇、+1 D1 因 R182 进入
  扫描区间）。
- 变异 **3/3**：Vite 加 `build.outDir: "public"` / `run.py` 改
  `public` / `web_server` 改 `public`，W21b 三红、W21a 绿。
- **回填**：R182 §6（run `42230515703` / bot `d2c1da6`）与索引 §1 的
  写回 / 基线两行。

## 2. 为什么是这一轮

服务版启动链有两处读前端产物：

- `run.py` 启动时看 `web/dist/index.html` 是否存在，缺失就执行
  `npm run build`；
- `src/web_server.py` 把 `web/dist` 挂到 `/`，产物不在就没有 UI。

Vite 侧此前没有显式 `build.outDir`，靠默认值 `dist` 与两边对上。一旦
给 `web/vite.config.ts` 加 `build.outDir: "public"`：

- 构建产物落到 `web/public`，`run.py` 仍看 `web/dist`，于是**每次启动
  都重新构建**（构建完仍看旧目录，永远不满足跳过条件）；
- `web_server` 挂载不到产物，页面 404；
- frontend CI job 只跑 `npm run build`，不会走 `run.py`，所以 CI 全绿。

三处同账是「默认值刚好一致」的运气，不是被守住的账。W21 把它钉住。

## 3. 实现

### 3.1 `tests/test_frontend_build_output.py`（W21a / W21b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W21a | Vite 至多一处 `outDir`（缺省取默认 `dist`）；`run.py` 恰一处 `dist_dir = web_dir / "<dir>"`；`web_server.py` 恰一处 `web_dist = BASE_DIR / "web" / "<dir>"`；目录名是单段 | 三份源码 |
| W21b | 有效 `outDir` == `run.py` 子目录 == `web_server.py` 子目录（逐字） | 同上 |

实现要点：

- 有效值按 Vite 的默认语义取：没有显式 `outDir` 时就是 `dist`——判据
  不为「必须有 outDir」而红，只要求三处一致。
- 两处后端赋值按整行锚定（`dist_dir = web_dir / "…"`、
  `web_dist = BASE_DIR / "web" / "…"`），改结构或加第二处会显式红，
  防止判据静默漏看。
- 单段目录名守卫：`web/../dist` 或绝对路径这种写法不进入同账比较。

### 3.2 生产代码

- 零改动：`web/vite.config.ts`、`run.py`、`src/web_server.py` 都不动。

## 4. 验证

- 定向：`tests/test_frontend_build_output.py` 2 passed。
- 关联面：`test_dev_proxy_port.py`（同读 Vite 配置）、
  `test_web_server_lifespan.py`、`test_container_build_contract.py` 全绿。
- 本机全量：**3113 passed / 28 skipped / 0 failed**（3141 条，约 10m01s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 Vite 加 `build.outDir: "public"` | W21b 红、W21a 绿 |
| M2 `run.py` 的 `dist_dir` 改 `public` | W21b 红、W21a 绿 |
| M3 `web_server.py` 的 `web_dist` 改 `public` | W21b 红、W21a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核
（`web/vite.config.ts`、`run.py`、`src/web_server.py` 均为 CRLF）。

## 5. 边界与遗留

- 只判产物**目录名**：不判 Vite 的其它构建选项、不判 `web/public`
  静态资源目录（Vite 输入）、不判构建是否真的执行（frontend CI job
  负责）；不判 `desktop/README.md` 里 `web/dist` 的叙述。
- 四轮连推（十五）下一轮 **R184 收口轮（R181–R183 四账）**：四账审计
  + 登记下一批（R185–R188）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`b836fa9`** 推送后 run **42235408330**：**10 job 全
  `success`**（14:36:17→14:52:14 UTC，约 15m57s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42235408330`，bot 提交 **`f867987`**）。R184 回填。

## 7. 提交

- 改动：`tests/test_frontend_build_output.py`（W21）、R183 文档、
  R182 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R183 一条）、
  `JUDGEMENT_LEDGER.md`（§10.55）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
