# DeterminFlow (xs2) 交接报告 — Round 193（desktop README 工作流名同账：W28）

> 单 profile。四轮连推（十八）第 1 轮：把 README 引用的桌面工作流名钉到
> `.github/workflows/desktop-*.yml` 的 `name:` 上；生产代码零改动，
> 文档一行修复。变异 3/3。

## 1. 一句话结论

- **实测修复**：desktop/README.md「桌面更新发布」节写「macOS 候选由
  `Desktop macOS candidate` 工作流生成」，而
  `.github/workflows/desktop-macos.yml` 的 `name:` 是
  `Desktop macOS`——引用的名字在仓库里不存在。R193 把 README 修为
  `Desktop macOS`（一行），候选制继 R177 P10、R187 W24 之后第三次修复
  登记阶段实测抓到的真实不一致（R192 §3 预检、本轮开工落地）。
- `tests/test_desktop_workflow_name.py` 新增 **W28a/W28b**：desktop-*.yml
  的 `name:` 集合 == 登记词表 {`Desktop macOS`, `Desktop Windows`} +
  README「`` `X` 工作流 ``」引用形状恰一处（W28a）、README 引用的名
  ∈ workflow name 集合（W28b，双向：改名不跟 / 写出集合外的名都红）。
  总用例 3171 → **3175**（+2 钉测、+1 N3 本篇、+1 D1 因 R192 §6 进入
  回填扫描区间）。
- 变异 **3/3**：README 回退 `Desktop macOS candidate`（W28b 红）、
  desktop-windows.yml `name:` 改词表外的 `Desktop Windows Installer`
  （W28a 独红：词表集合不等，但 README 引用的 macOS 名仍在集合）、
  desktop-macos.yml 删 `name:` 行（W28a+W28b 双红：结构守卫 + 解析不到）。
- **回填**：R192 §6（run `42352629011` / bot `9429ee1`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

工作流名是人在 GitHub Actions 页签、`gh run list` 与 README 之间对账的
主键：README 说「候选由某个工作流生成」，读者按名去找——名字对不上，
文档的指向就断了。这条边此前无人判：W26 管的是 Windows 表「工作流」行
引用的**路径**（`.github/workflows/desktop-windows.yml` 存在性），
desktop-macos.yml 连表行都没有，工作流 `name:` 与 README 的叙述更是
第一次进射程。`Desktop macOS candidate` 是候选制叙述（job 名
`Build Apple Silicon … candidate`、产物名 `…-adhoc-candidate`）渗进
工作流名的手误形状——只有 `name:` 从来没有 candidate。

W28 的锚选在「词表 + 集合双向」：desktop-*.yml 的 name 集合先钉死在
登记词表 {`Desktop macOS`, `Desktop Windows`}（新增/删除/改名先红词表，
强制显式扩表），README 的引用再钉进集合（引用必须逐字命中）。两道闸
分开后，「README 引用没跟改名」（词表不动、引用出集合）与「工作流
改名/增删」（词表先红）各自有显式的红。

## 3. 实现

### 3.1 生产代码与文档

- 生产代码零改动（两份 workflow 的 `name:` 本来就在词表内，纯钉住）。
- 文档一行修复：desktop/README.md L122 `Desktop macOS candidate` →
  `Desktop macOS`（同段其余叙述不变；job/产物名里的 candidate 是
  候选制叙述词，保留）。

### 3.2 `tests/test_desktop_workflow_name.py`（W28a / W28b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W28a | desktop-*.yml 每份有 `name:` 字符串；name 集合 == 词表 {Desktop macOS, Desktop Windows}；README「`` `X` 工作流 ``」引用形状全文档恰一处 | 两份 desktop workflow + desktop/README.md |
| W28b | README 引用的名 ∈ name 集合（逐字，双向） | 同上 |

实现要点：

- 引用形状用 `` `([^`]+)`\s*工作流 ``（反引号 token 紧跟「工作流」）：
  全文档恰一处。Windows 表「工作流」行的路径引用（token 在「工作流」
  **前**、属表格单元格）与「`.github` 公开发行工作流」（token 与词之间
  有「公开发行」间隔）都不进射程。
- 词表守卫用集合恰等（不是 ⊆）：desktop 工作流只有两份，集合恰等让
  「新增第三份」「删一份」「改名」都先红在词表。
- workflow 侧 `yaml.safe_load` 顶层 `name:`，解析不到显式红（W28 无锚）。

## 4. 验证

- 定向：`tests/test_desktop_workflow_name.py` 2 passed。
- 关联面：`test_desktop_windows_runner.py`（W26）、
  `test_desktop_macos_scope.py`（W24）、
  `test_desktop_readme_packaging.py`（W27）、
  `test_desktop_ui_paths.py`（W25）、`test_desktop_packaging.py` 全绿；
  S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正之前），本提交
  翻正后全绿。
- 本机全量：**3147 passed / 28 skipped / 0 failed**（3175 条，
  约 10m21s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop/README 与两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 README 回退 `Desktop macOS candidate` | W28b 红（不在 name 集合）、W28a 绿（形状仍恰一处） |
| M2 desktop-windows.yml `name:` → `Desktop Windows Installer` | W28a 红（词表集合不等）、W28b 绿（引用的 macOS 名仍在集合） |
| M3 desktop-macos.yml 删 `name:` 行 | W28a 红（结构守卫）、W28b 红（解析不到） |

## 5. 边界与遗留

- 只判 README 的「`` `X` 工作流 ``」引用形状与两份 desktop-*.yml 的
  `name:`——不判 Windows 表「工作流」行的路径引用（W26 射程）、不判
  `replace-desktop-assets.yml`（文件名不匹配 `desktop-*.yml` glob，
  `workflow_call` 复用工作流不在人读引用面）、不判 job 名与产物名里的
  candidate 词（候选制叙述，合法）、不判工作流触发条件与 step 行为。
- 四轮连推（十八）第 2 轮 **R194 flavor 词表五源闭包（W29）**（已登记，
  R192 §3；开工实测发现登记口径外第五源 `verify_bundle.py` 的
  `--expected-flavor` choices，同 W18/W13/W25 实测补面先例，见 R194）。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`e80549e`** 推送后 run **42369789774**：**10 job 全
  `success`**（11:49:23→12:06:15 UTC，约 16m52s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42369789774`，bot 提交 **`2d0b58b`**）。R194 回填。同推送因
  `desktop/**` 变更还触发了 Desktop Windows 工作流（约 12 分钟，
  同样全绿；该工作流没有写回账，§6 不引用其 run id——D2 只认有
  bot 快照的 run）。

## 7. 提交

- 改动：`tests/test_desktop_workflow_name.py`（W28）、desktop/README.md
  一行修复、R193 文档、R192 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题/批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R193
  一条）、`JUDGEMENT_LEDGER.md`（§10.65）。
- `config/skills_config.json` 不纳入（C1）。
