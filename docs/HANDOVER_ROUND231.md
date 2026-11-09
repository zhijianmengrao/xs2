# DeterminFlow (xs2) 交接报告 — Round 231（replace workflow inputs 定义 == 消费：W57）

> 单 profile。四轮连推（二十七）第 3 轮：把 replace-desktop-assets.yml
> 的 `workflow_dispatch.inputs` 定义（windows_run/macos_run）与消费点
> （provenance 步 env 两行）钉成双向恰等。生产代码零改动，本轮无修复
> ——输入名现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_replace_inputs.py` 新增 **W57a/W57b**：inputs 块
  恰 2 个键行（W57a）；定义键集合 == 消费键集合（消费未定义的红、定义
  未消费的死输入也红）（W57b）。总用例 3305 → **3309**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R230 §6 进入回填扫描区间）。
- 变异 **4/4**：消费 `inputs.macos_run` 错拼 / 消费行删除（W57b 各自
  独红）、macos_run 定义行删除（双红：计数与集合都断，如实登记）、
  windows_run 定义行复制（W57a 独红）。
- **回填**：R230 §6（run `42464619245` / bot `f4c62cc`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 的 `workflow_dispatch.inputs` 定义两个输入
（`windows_run` L6 / `macos_run` L9），消费点为 provenance 步的 env
两行（`WINDOWS_RUN: ${{ inputs.windows_run }}` L33 / `MACOS_RUN:
${{ inputs.macos_run }}` L34）。定义与消费漂移无人判：消费引用不
存在的输入时 gh 拿到空字符串（脚本抛 `Invalid build run ID`——应急
通道当场失败），或定义改名/删除而消费没跟（死输入留在触发面板，
误导手动触发者）。

W56 管 desktop-windows.yml 的 step outputs 定义↔消费，W57 把同一
形态推到 **workflow inputs** 面：`workflow_dispatch.inputs` 的定义
与 `inputs.*` 消费第一次进射程。

W57 的锚选在「双向恰等」：消费未定义（引用打错）与定义未消费
（死输入）都红——单向 ⊆ 会漏掉后者。

## 3. 实现

### 3.1 生产代码

- 零改动（输入名现同账，纯钉住）。

### 3.2 `tests/test_desktop_replace_inputs.py`（W57a / W57b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W57a | inputs 块恰 2 个键行（`      <key>:` 形状） | replace-desktop-assets.yml |
| W57b | 定义键集合 == 消费键集合（双向） | 同上 |

实现要点：

- 定义提取先锚 `^    inputs:` 块（`(?:      .*\n)+`），再取 6 空格键行
  ——文件其余 6 空格行不存在，块锚避免把别处 YAML 键吃进来。
- 消费提取 `\$\{\{[^}\n]*?inputs\.(\w+)[^}\n]*?\}\}`——允许表达式修饰
  （`||` 等）；同一表达式只取第一个名，多输入表达式会以「定义未消费」
  形式红，逼显式改判据。
- `read_text` 统一换行，CRLF 工作树与 LF 检出同一结果。
- M3（删定义行）是天然双红：计数与集合同时断——如实登记。

## 4. 验证

- 定向：`tests/test_desktop_replace_inputs.py` 2 passed（首跑即过）；
  关联面 `test_desktop_installer_outputs.py`（W56）、
  `test_desktop_smoke_flavor_default.py`（W55）全绿。
- 本机全量：**3281 passed / 28 skipped / 0 failed**（3309 条，
  约 9m38s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  replace-desktop-assets.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 消费 `inputs.macos_run` 错拼为 `macos_runs` | W57b 红（消费未定义）、W57a 绿 |
| M2 `MACOS_RUN` 消费行删除 | W57b 红（定义未消费）、W57a 绿 |
| M3 `macos_run` 定义行删除 | W57a 红（2→1）+ W57b 红（集合不等，双红） |
| M4 `windows_run` 定义行复制 | W57a 红（2→3）、W57b 绿（集合不变） |

## 5. 边界与遗留

- 只判输入名的字面同账——不判 description/required 等其余键、不判
  `gh api` 的运行时校验（脚本负责）、不判 workflow 触发与下载行为
  （CI 负责）。
- 四轮连推（二十七）续 **R232 收口**（R229–R232 四账 + R233–R236
  登记）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`b39b2fc`** 推送后 run **42558804151**：**10 job 全
  `success`**（03:53:26→04:11:42 UTC，约 18m16s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42558804151`，bot 提交 **`4d6a597`**）。R232 回填。

## 7. 提交

- 改动：`tests/test_desktop_replace_inputs.py`（W57）、R231 文档、
  R230 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R231 一条）、
  `JUDGEMENT_LEDGER.md`（§10.103）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
