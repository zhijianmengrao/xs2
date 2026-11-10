# DeterminFlow (xs2) 交接报告 — Round 239（replace 下载清单 ↔ 两 producer artifact 名同账：W63）

> 单 profile。四轮连推（二十九）第 3 轮：把 replace-desktop-assets.yml
> provenance heredoc 的两份下载清单与两个 producer workflow 的
> artifact 名模板（按各自 matrix 展开）钉成双向恰等。生产代码零改动，
> 本轮无修复——清单现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_replace_download_manifest.py` 新增 **W63a/W63b**：
  replace 恰两份平台清单、各恰 2 个条目；两个 producer 各恰 1 个
  artifact 名模板、恰 1 份 flavor matrix、每份恰 2 个 flavor（W63a）；
  模板按各自 matrix 展开后的集合 == 对应平台的消费清单集合（W63b，
  双向）。总用例 3333 → **3337**（+2 钉测、+1 N3 本篇、+1 D1 因
  R238 §6 进入回填扫描区间）。
- 变异 **4/4**：windows 模板改名（双红：模板形状守卫 + 展开恰等，
  如实登记）、消费 macos 条目改名 / windows matrix flavor 错拼
  （W63b 各自独红）、消费 windows 条目复制（W63a 独红）。
- **回填**：R238 §6（run `42734910789` / bot `1e96c3a`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 的 provenance heredoc 用两个字面清单声明
要从构建 run 下载的 artifact 名：windows
`['DeterminFlow-Windows-x64-core', 'DeterminFlow-Windows-x64-full']`
（L44）、macos
`['DeterminFlow-macOS-arm64-core-adhoc-candidate', 'DeterminFlow-macOS-arm64-full-adhoc-candidate']`
（L46）。对面是两个 producer workflow 的上传名模板：desktop-windows.yml
`name: DeterminFlow-Windows-x64-${{ matrix.flavor }}`（L140，matrix
为块式列表 `- core` / `- full`）与 desktop-macos.yml
`name: DeterminFlow-macOS-arm64-${{ matrix.flavor }}-adhoc-candidate`
（L81，matrix 内联 `[core, full]`）。消费与生产漂移无人判——
`test_desktop_packaging` 只钉模板单源，不与 replace 的清单对账：
matrix 增 flavor 或改名而 replace 没跟 → 应急通道
`gh run download --name` 失败；replace 清单改名而 workflow 没跟，
同样失败。

W58–W62 已把 replace workflow 的 outputs/inputs/import 调用面/env
消费/目录名钉齐，W63 把同账推到**跨 workflow 的 artifact 名生产 ==
消费**（模板按各自 matrix 展开后恰等）。

W63 的锚选在「展开双向恰等」：producer 侧提取模板与 flavor matrix、
按 matrix 展开成集合；消费侧提取清单字面成集合——谁多谁少都红。
两种 matrix 写法（块式列表 / 内联 `[a, b]`）各自有提取正则。

## 3. 实现

### 3.1 生产代码

- 零改动（清单现同账，纯钉住）。

### 3.2 `tests/test_desktop_replace_download_manifest.py`（W63a / W63b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W63a | 消费恰 2 份清单、各 2 条目；生产各恰 1 模板、1 matrix、2 flavor | replace-desktop-assets.yml + desktop-windows.yml + desktop-macos.yml |
| W63b | 模板按 matrix 展开后的集合 == 消费清单集合（双向，逐平台） | 同上 |

实现要点：

- 消费提取锚在元组行：`\('windows', 'WINDOWS_RUN',\s*'[^']*',\s*\[([^\]]+)\]`
  ——路径字面把两份清单与平台元组绑死，不会误吃别处。
- 生产模板提取 `name: (DeterminFlow-…-\$\{\{ matrix\.flavor \}\}…)$`
  ——job 名（`Build … installer`）不含 `DeterminFlow-` 前缀，天然
  不匹配；模板恰 1 个由提取时断言。
- matrix 两写法分治：windows 块式
  `^ {8}flavor:\n((?: {10}- [a-z]+\n)+)`、macos 内联
  `^ {8}flavor: \[([a-z, ]+)\]`。
- M1（模板改名）是天然双红：模板形状守卫与展开恰等同时断——如实
  登记。

## 4. 验证

- 定向：`tests/test_desktop_replace_download_manifest.py` 2 passed
  （首跑即过）；关联面 `test_desktop_packaging.py`（模板单源钉测）
  全绿。
- 本机全量：**3308 passed / 28 skipped / 0 failed**（3337 条，
  约 10m00s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核）：

| 变异 | 结果 |
|---|---|
| M1 windows 模板 `DeterminFlow-Windows-x64-` → `DeterminFlow-Win-x64-` | W63a 红（模板形状守卫）+ W63b 红（展开不等，双红） |
| M2 消费 macos 条目 `-adhoc-candidate` → `-candidate` | W63b 红（消费未生产）、W63a 绿 |
| M3 windows matrix flavor `- full` → `- ful` | W63b 红（展开不等）、W63a 绿（仍 2 flavor） |
| M4 消费 windows 清单复制一个条目 | W63a 红（2→3）、W63b 绿（集合不变） |

## 5. 边界与遗留

- 只判 artifact 名的字面同账——不判 artifact 内容（校验由
  provenance/release 步脚本负责）、不判 gh run download/
  upload-artifact 行为（CI 负责）、不判 installer-diagnostics 等其余
  artifact 名（不进 replace 下载清单）。
- 四轮连推（二十九）续 **R240 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_replace_download_manifest.py`（W63）、
  R239 文档、R238 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3
  标题/批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R239
  一条）、`JUDGEMENT_LEDGER.md`（§10.111）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
