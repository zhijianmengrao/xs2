# DeterminFlow (xs2) 交接报告 — Round 215（desktop workflow npm script 调用面：W45）

> 单 profile。四轮连推（二十三）第 3 轮：把 desktop workflows 的
> `npm run <X>` 调用面钉成「计数恰等 2/2 + script 名 ∈ package.json
> scripts」。生产代码零改动，本轮无修复——调用面现可解析。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_npm_scripts.py` 新增 **W45a/W45b**：`npm run`
  调用逐份恰等（desktop-macos.yml 2 / desktop-windows.yml 2，合计 4）
  （W45a）；每个 `npm run <X>` 的 `<X>` ∈ desktop/package.json
  `scripts` 键集合（解析 JSON；实测键 {build, build:macos, tauri,
  test}）（W45b）。总用例 3249 → **3253**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R214 §6 进入回填扫描区间）。
- 变异 **4/4**：macos `build:macos` 改名 / package.json `build` 改名
  （W45b 各自独红）、windows `build` 调用删除 / macos `build:macos`
  复制（W45a 各自独红）。
- **回填**：R214 §6（run `42427066751` / bot `7593934`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop workflows 的 `npm run <X>` 共 4 处：macos 的 `npm ci && npm
run build`（L48）与 `npm run build:macos -- --flavor …`（L58）、
windows 的 `npm run build` ×2（L83/L99）；desktop/package.json 的
`scripts` 实测 {build, build:macos, tauri, test}。调用面漂移无人判：
workflow 的 script 名写错（npm 报 `Missing script` 退非零，run 时
才炸）、或 package.json 改名 script 而 workflow 没跟。V6/V7 管的是
README 与文档 npm 命令面，workflow 侧第一次进射程。

W45 的分工沿用定式：W45a 管计数（2/2），W45b 管 script 名可解析
（∈ package.json scripts 键集合；`build`/`build:macos` 作为基础键
显式断言存在，防 scripts 集合被整段清空后「调用也清空」的双绿）。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现可解析，纯钉住）。

### 3.2 `tests/test_desktop_npm_scripts.py`（W45a / W45b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W45a | `npm run` 调用逐份恰等（macos 2 / windows 2，合计 4） | desktop-macos.yml + desktop-windows.yml |
| W45b | 每个 `npm run <X>` 的 `<X>` ∈ package.json `scripts` 键集合；基础键 {build, build:macos} 显式存在 | 同上 + desktop/package.json |

实现要点：

- package.json 用 `json.load` 解析取 `scripts` 键集合（不用正则，
  JSON 结构自身的账）。
- macos L48 的 `npm ci && npm run build` 是复合行——`npm run (\S+)`
  照常命中 `build`；`npm ci` 不在射程。
- windows L83/L99 形状不同（10 空格缩进独立行 / `run:` 前缀行），
  提取正则都命中；变异锚按各自形状取。

## 4. 验证

- 定向：`tests/test_desktop_npm_scripts.py` 2 passed（首跑即过）；
  关联面 `test_desktop_product_paths.py`（W44）、
  `test_desktop_r2_gate.py`（W43）、
  `test_desktop_symmetric_script_calls.py`（W40）全绿；S2/S3/S5 在
  本提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3225 passed / 28 skipped / 0 failed**（3253 条，
  约 11m48s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 package.json 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 macos `build:macos` 改名 `build-macos` | W45b 红（script 未定义）、W45a 绿 |
| M2 package.json `build` 改名 `compile` | W45b 红（3 处调用未定义）、W45a 绿 |
| M3 windows L83 `build` 调用删除 | W45a 红（2→1）、W45b 绿（剩余全定义） |
| M4 macos `build:macos` 调用复制 | W45a 红（2→3）、W45b 绿 |

## 5. 边界与遗留

- 只判 script 名可解析——不判 script 内容（package.json 的
  build/tauri 命令行是各 script 自己的账）、不判 `npm ci`（不是
  npm run 面）、不判 `npm exec tauri` 直调（tauri CLI 面）、不判
  执行行为（CI 负责）。
- 四轮连推（二十三）收官 **R216 收口轮（R213–R216 四账）+ 登记
  R217–R220**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_npm_scripts.py`（W45）、R215 文档、R214
  §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4 H2/一行
  + §6.1）、`PROJECT_INFO.md`（H2 + R215 一条）、
  `JUDGEMENT_LEDGER.md`（§10.87）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
