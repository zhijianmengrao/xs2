# DeterminFlow (xs2) 交接报告 — Round 213（R2 分发门控变量同账：W43）

> 单 profile。四轮连推（二十三）第 1 轮：把 `R2_DISTRIBUTION_ENABLED`
> 门控钉成「两 workflow 条件全文恰等 + README 叙述值同账」。生产代码
> 零改动，本轮无修复——门控现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_r2_gate.py` 新增 **W43a/W43b**：两份分发 workflow
  的门控条件各恰一处（形状值无关，`==`/`!=` 都算门控）、README 的
  `R2_DISTRIBUTION_ENABLED=<值>` 提及恰 2 处（W43a）；两 workflow 的
  门控条件**全文**（含运算符）逐字恰等 + README 提及值集合 ==
  workflow 比较值集合（W43b）。总用例 3241 → **3245**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R212 §6 进入回填扫描区间）。
- 变异 **4/4**：windows 门控 `==` 翻 `!=` / replace 比较值改 `'True'`
  （W43b 各自独红）、README L126 提及删除 / windows 门控复制（W43a
  各自独红）。
- **回填**：R212 §6（run `42422351039` / bot `5e2de5e`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

R2 分发是否启用的门控有 4 份账：desktop/README.md 两处叙述（L120
「两个仓库必须保持 `R2_DISTRIBUTION_ENABLED=true`」、L126「当仓库
变量 `R2_DISTRIBUTION_ENABLED=true` 时」）+ desktop-windows.yml 与
replace-desktop-assets.yml 各一处
`if: vars.R2_DISTRIBUTION_ENABLED == 'true'`。门控漂移无人判：一边
改门控语义（如 `!= 'false'`——空值行为完全不同：`== 'true'` 空值
关闭、`!= 'false'` 空值开启）或换比较值（`'True'`/`'yes'`），另一边
没跟——README 教人配置 `=true`，workflow 却在等别的值，R2 分发静默
不启用（发布任务整段跳过，无人察觉）。W30/W31/W33 各管凭据、回落
域名、发行路径，门控变量本身第一次进射程。

W43 的锚选在「条件全文恰等」而不是「比较值恰等」：首版实现只比
捕获的比较值，`!= 'true'` 变异双绿（运算符没进账）——变异全绿和
双红一样要查原因，捕获组改成条件全文后才把运算符钉进同账。

## 3. 实现

### 3.1 生产代码

- 零改动（门控现同账，纯钉住）。

### 3.2 `tests/test_desktop_r2_gate.py`（W43a / W43b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W43a | 两份分发 workflow 的门控条件各恰一处（形状 `if: vars.R2_DISTRIBUTION_ENABLED [=!]= '<值>'`，值无关）；README 的提及恰 2 处 | desktop-windows.yml + replace-desktop-assets.yml + desktop/README.md |
| W43b | 两 workflow 的门控条件全文（含运算符）逐字恰等；README 提及值集合 == workflow 比较值集合（按集合，prose 重复提及不影响账面） | 同上 |

实现要点：

- 捕获组双出（条件全文, 比较值）——W43b 的「恰等」对全文、「值账」
  对比较值，两条账分开。
- README 侧按集合比较（两处叙述同值 → 集合 {'true'}）：prose 重复
  提及不翻红，值翻红。
- 形状正则容忍 `[=!]=`：运算符漂移是 W43b 的账（全文不等），不是
  W43a 的锚丢失。

## 4. 验证

- 定向：`tests/test_desktop_r2_gate.py` 2 passed（首跑修正「只比值
  不比运算符」后即过）；关联面 `test_desktop_r2_credentials.py`
  （W30）、`test_desktop_r2_fallback_domain.py`（W31）、
  `test_desktop_r2_release_paths.py`（W33）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3217 passed / 28 skipped / 0 failed**（3245 条，
  约 11m06s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 desktop/README 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 windows 门控 `==` 翻 `!=` | W43b 红（条件全文不等）、W43a 绿 |
| M2 replace 比较值改 `'True'` | W43b 红（条件全文与值账都断）、W43a 绿 |
| M3 README L126 提及删除 | W43a 红（提及 2→1）、W43b 绿（值集合仍 {'true'}） |
| M4 windows 门控复制一份 | W43a 红（恰一处破坏）、W43b 绿 |

## 5. 边界与遗留

- 只判门控条件的字面与值的同账——不判门控的求值行为（CI 负责）、
  不判 README 两处叙述的措辞（prose 措辞不进射程，只对值）、不判
  `R2_PUBLIC_BASE_URL` 等其他变量（W31/W30 已管）。
- 四轮连推（二十三）续 **R214 macOS 产物路径前缀同账（W44）**、
  **R215 desktop workflow npm script 调用面（W45）**、**R216 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_r2_gate.py`（W43）、R213 文档、R212 §6
  回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R213 一条）、
  `JUDGEMENT_LEDGER.md`（§10.85）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
