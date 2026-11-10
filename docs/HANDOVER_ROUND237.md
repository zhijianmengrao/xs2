# DeterminFlow (xs2) 交接报告 — Round 237（replace workflow provenance 步 env 定义 == os.environ 消费：W61）

> 单 profile。四轮连推（二十九）第 1 轮：把 replace-desktop-assets.yml
> provenance 步的两个 env 键（WINDOWS_RUN/MACOS_RUN，值来自
> inputs.*）与 heredoc 的 `os.environ` 消费键钉成双向恰等。生产代码
> 零改动，本轮无修复——env 键现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_replace_provenance_env.py` 新增 **W61a/W61b**：
  env 定义（值来自 `inputs.*`）恰 2 键、heredoc 存在、
  `os.environ[key]` 循环读取恰 1 处、引号大写键字面恰 2 个（W61a）；
  env 键集合 == heredoc 键字面集合（消费未定义的红、定义未消费的
  死键也红）（W61b）。总用例 3325 → **3329**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R236 §6 进入回填扫描区间）。
- 变异 **4/4**：env 键改名 / heredoc 元组字面改名（W61b 各自独红）、
  env 键删除（双红：计数与集合都断，如实登记）、元组字面复制
  （W61a 独红）。
- **回填**：R236 §6（run `42647655708` / bot `f603864`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 的 provenance 步 env 定义两键：
`WINDOWS_RUN: ${{ inputs.windows_run }}`（L33）/ `MACOS_RUN:
${{ inputs.macos_run }}`（L34，输入名由 W57 钉住）。heredoc 内的
消费形态是「元组字面 → 循环变量 → `os.environ[key]`」：两键作为
`'WINDOWS_RUN'`/`'MACOS_RUN'` 字面（L43/L45）流进
`for platform, key, workflow, artifacts in (…)` 的循环变量，在
`os.environ[key]`（L48）统一取出。定义与消费漂移无人判：env 键改名
而元组没跟 → `os.environ[key]` 抛 `KeyError`——应急通道当场失败，
两个平台的构建 run 校验全部中断；或元组改字面而 env 没跟，同样
KeyError。

W57 管 workflow inputs 的定义 == 消费，W58 管 release 步 outputs，
W61 把同一形态推到 provenance 步的 **env 定义 ↔ os.environ 消费**。

W61 的锚选在「双向恰等」：消费未定义（KeyError）与定义未消费
（死 env 键）都红——单向 ⊆ 会漏掉后者。heredoc 内
`os.environ['GITHUB_REPOSITORY']` 等**直接读取**是 runner 注入键，
无定义侧可对，先剥再数（W61a 语料守卫明确这一边界）。

## 3. 实现

### 3.1 生产代码

- 零改动（env 键现同账，纯钉住）。

### 3.2 `tests/test_desktop_replace_provenance_env.py`（W61a / W61b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W61a | env 定义恰 2 键；heredoc 存在、`os.environ[key]` 恰 1 处、引号大写键字面恰 2 个 | replace-desktop-assets.yml |
| W61b | env 键集合 == heredoc 键字面集合（双向） | 同上 |

实现要点：

- 定义提取 `^ {10}([A-Z_]+): \$\{\{ inputs\.(\w+) \}\}$`——GH_TOKEN
  用 `github.token`、发布步用 secrets/vars/steps，都不匹配，恰
  L33/L34 两处。
- heredoc 边界 `python - <<'PY'\n(.*?)\n {10}PY\n`——首个 heredoc
  即 provenance 步；`os.environ\[[^\]]*\]` 先剥直接读取（L40 的
  GITHUB_REPOSITORY/GITHUB_SHA），再数 `'([A-Z_]+)'` 键字面（恰
  WINDOWS_RUN/MACOS_RUN）。
- M3（删一行 env 定义）是天然双红：计数与集合同时断——如实登记。

## 4. 验证

- 定向：`tests/test_desktop_replace_provenance_env.py` 2 passed
  （首跑即过）；关联面 `test_desktop_replace_inputs.py`（W57）、
  `test_desktop_replace_outputs.py`（W58）全绿。
- 本机全量：**3301 passed / 28 skipped / 0 failed**（3329 条，
  约 10m51s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  replace-desktop-assets.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 env 键 `WINDOWS_RUN` 改名 `WINDOWS_RUN_ID`（L33） | W61b 红（定义未消费）、W61a 绿 |
| M2 元组字面 `'WINDOWS_RUN'` 改名 `'WINDOWS_RUN_ID'`（L43） | W61b 红（消费未定义）、W61a 绿 |
| M3 env `MACOS_RUN` 定义行删除 | W61a 红（2→1）+ W61b 红（集合不等，双红） |
| M4 元组字面 `'WINDOWS_RUN'` 复制 | W61a 红（2→3）、W61b 绿（集合不变） |

## 5. 边界与遗留

- 只判 env 键名的字面同账——不判键值（`inputs.*` 的取值由 W57 钉
  输入名）、不判 `os.environ['GITHUB_*']` 直接读取（runner 注入，
  无定义侧可对）、不判 `gh api` 的运行时校验（脚本负责）、不判
  workflow 触发与下载行为（CI 负责）。
- 四轮连推（二十九）续 **R238 replace workflow 资产目录名四源同账
  （W62）**、**R239 replace 下载清单 ↔ 两 producer artifact 名同账
  （W63）**、**R240 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_replace_provenance_env.py`（W61）、R237
  文档、R236 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/
  批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R237 一条）、
  `JUDGEMENT_LEDGER.md`（§10.109）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
