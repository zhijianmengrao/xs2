# DeterminFlow (xs2) 交接报告 — Round 178（文档 npm 命令引用面：V7）

> 单 profile。四轮连推（十四）第 2 轮：三份开发者文档的
> `npm run` / `npm test` / `npm ci` 第一次与 `web/package.json` 的
> scripts、`web/package-lock.json` 对账。生产代码零改动；V7 首跑即过，
> 变异 3/3。

## 1. 一句话结论

- **实测**：`README.md` 3 处、`README.en.md` 3 处、`CONTRIBUTING.md`
  4 处，共 **10 处** `npm run <script>` 引用；`CONTRIBUTING.md` 另有
  **1 处** `npm ci`。工作目录由块内 `(cd web && …)` 与独立 `cd web`
  推进到 `web/`，10 个 script 全部命中 `web/package.json` 的 13 个
  scripts，锁文件 `web/package-lock.json` 在库。
- `tests/test_doc_npm_commands.py` 新增 **V7a/V7b**：三份文档各自
  ≥3/3/4 处 script 引用（合计 ≥9，实测 10）、`npm ci` ≥1；每个 script
  名与锁文件必须可解析。总用例 3119 → **3123**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R177 进入扫描区间）。
- 变异 **3/3**：删 `test:extensions` script / README 的 `npm run lint`
  → `lint:check` / 移走 `web/package-lock.json`，V7b 三红、V7a 保持绿。
- **回填**：R177 §6（run `42199142142` / bot `ccd81a3`）与索引 §1
  的写回 / 基线两行。

## 2. 为什么是这一轮

R169 的 V5 只钉 CI / Dockerfile 的 npm 引用；R176 的 V6 只钉两份
README 的 `python <file>.py` 与 `docker compose` 命令。文档里的 npm
命令仍是无人判的一面：`web/package.json` 删掉 `lint` /
`test:extensions` / `test:workflow`，或把 `npm test` 的聚合链改坏，
读者照 README / CONTRIBUTING 执行才会失败——CI 只跑它自己 yml 里的
命令，**从不执行文档命令**，没有任何现有闸门会咬住它。

V7 的锚选在「文档命令实际执行的那个目录」：`cd web` 之后的
`package.json` scripts 与 `package-lock.json`。不判 script 内部命令
（那是 script 自己的事），也不判 README 的 python / compose 面（V6）。

## 3. 实现

### 3.1 `tests/test_doc_npm_commands.py`（V7a / V7b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| V7a | 三份文档各 ≥3/3/4 处 script 引用（合计 ≥9），`npm ci` ≥1 | fenced 块内的 `npm run` / `npm test` / `npm ci` |
| V7b | 每个 script 名 ∈ 工作目录的 `package.json` scripts；每个 `npm ci` 的工作目录有 `package-lock.json` | 块内 `cd` 推进后的 `web/` |

实现要点：

- 只扫 fenced 代码块，块内按行与 `&&` / `;` 切 token；`(cd web && …)`
  的子壳与独立 `cd web` 都推进工作目录，每个块重置。
- `npm test` 归一为 script 名 `test`；`npm run <name>` 保留
  `test:extensions` 这类带冒号的键。
- 工作目录缺 `package.json` / 锁文件时显式报告路径，不静默跳过；
  README 里 `git clone … && cd DeterminFlow` 这类本地不存在的目录名
  后面没有 npm 命令，自然不进射程。

### 3.2 文档面

- 三份文档本身零改动：V7 钉的是「文档 → 仓库」的引用，不是文档措辞。
- `web/package.json` / `web/package-lock.json` 也零改动。

## 4. 验证

- 定向：`tests/test_doc_npm_commands.py` 2 passed；关联三文件
  （文档命令 / README 命令 / npm 引用）6 passed。
- 本机全量：**3095 passed / 28 skipped / 0 failed**（3123 条，约
  10m10s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 `web/package.json` 删 `test:extensions` | V7b 红，V7a 绿 |
| M2 `README.md` `npm run lint`→`lint:check` | V7b 红，V7a 绿 |
| M3 移走 `web/package-lock.json` | V7b 红，V7a 绿 |

三次变异均 `read_bytes`/`write_bytes`（或改名后移回）还原并逐字节复核。

## 5. 边界与遗留

- 只扫 `README.md` / `README.en.md` / `CONTRIBUTING.md` 的 fenced
  代码块；正文散文与行内代码不在射程。
- 不判 `desktop/README.md` 与其它 `docs/*.md` 的 npm 命令（留作后续
  轮次）；不判命令参数语义与 script 内部命令。
- 不判 `npm install`（没有锁文件的完整性闸门语义）与 `npx`。
- 四轮连推（十四）下一轮 **R179 desktop 默认配置覆盖（W19）**：
  `config/*.json` 15 个与 `stage_defaults` 的 15 项恰等；R180 收口 +
  登记下一批。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_doc_npm_commands.py`（V7）、R178 文档、R177 §6
  回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行
  + §6.1）、`PROJECT_INFO.md`（H2 + R178 一条）、
  `JUDGEMENT_LEDGER.md`（§10.50）。生产代码与文档命令零改动。
- `config/skills_config.json` 不纳入（C1）。
