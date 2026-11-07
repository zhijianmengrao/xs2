# DeterminFlow (xs2) 交接报告 — Round 201（产物后缀词表四源同账：W34）

> 单 profile。四轮连推（二十）第 1 轮：把桌面发行产物的文件名后缀
> 词表钉成四源同账（replace-desktop-assets 期望词表 ↔ desktop-windows
> NSIS 对 + bash 列表 ↔ build_macos DMG 对）。生产代码零改动，本轮
> 无修复——四源现同账。变异 5/5。

## 1. 一句话结论

- `tests/test_desktop_product_suffixes.py` 新增 **W34a/W34b**：五处
  提取锚各恰一处、结构形状就位（replace 元组恰 4 项引号 token、
  NSIS 对带前导下划线的 if/else 对、bash 发布列表存在、build_macos
  三元分支 + DMG 模板）（W34a）；NSIS 对（剥 `_`）∪ DMG 对 ==
  replace 词表 == bash 列表，且两族不相交（W34b）。总用例 3199 →
  **3203**（+2 钉测、+1 N3 本篇、+1 D1 因 R200 §6 进入回填扫描
  区间）。
- 变异 **5/5**：replace 词表改值 / NSIS 对改值 / build_macos 分支
  改值 / bash 列表删项（W34b 各自独红）、NSIS 对行复制一份（W34a
  独红：W32 同型分工，值由同账判）。
- **回填**：R200 §6（run `42392721258` / bot `26b295e`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

R196 §3 登记候选面时留了一句「replace-desktop-assets.yml 期望资产
词表（4 后缀）↔ desktop-windows NSIS 后缀对 ↔ build_macos DMG 模板
后缀对的三源产物名词表」；R200 登记前实测发现是**四源**——
desktop-windows.yml 的 bash 发布步自带同款四后缀列表
（`for suffix in x64-setup.exe … aarch64-full.dmg`），与
replace-desktop-assets 的期望词表逐项同值。四份账是同一条词表：
NSIS 对（`_x64-setup.exe`/`_x64-full-setup.exe`，带前导下划线）∪
DMG 对（`aarch64{""|"-full"}.dmg`）== replace 词表 == bash 列表。
任何一处加减/改后缀而其余未跟：replace-desktop-assets 的补资产步
漏找新产物（资产不齐、静默少发），或 desktop-windows 的 sha256sum
找不到旧名（发布步当场炸）。

W34 的分工沿用 W32 的教训：语料守卫只管锚的存在与结构（值无关的
形状），词表值只由同账判——「NSIS 对改值」不再像首版那样把值字面
钉进形状正则而双红。

## 3. 实现

### 3.1 生产代码

- 零改动（四源现同账，纯钉住）。

### 3.2 `tests/test_desktop_product_suffixes.py`（W34a / W34b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W34a | 五处锚各恰一处（replace 元组 / NSIS 对 / bash 列表 / build_macos 分支 / DMG 模板）+ 结构形状（元组 4 项、NSIS 对两项带 `_` 前缀、分支含 full/else 两值） | replace-desktop-assets.yml + desktop-windows.yml ×2 + build_macos.py |
| W34b | NSIS 对（剥 `_`）∪ DMG 对 == replace 词表 == bash 列表；NSIS 与 DMG 两族不相交 | 同上 |

实现要点：

- W34a 与 W34b 分用两套守卫：`_require`（恰一处，W34a）与 `_first`
  （只守存在，W34b）——锚被复制时 W34a 独红、W34b 取首值照常比较
  （W33 的 M5 同型）；锚被删时两半都红（无锚可比）。
- NSIS 对的形状正则值无关（`\{ "(_[^"]+)" \} else \{ "(_[^"]+)" \}`），
  只钉「两项、带前导下划线」；剥 `_` 后进同账集合。
- DMG 集合从两处拼出：分支正则提取 `-full`/空两支，模板正则提取
  基底（单捕获组，`_require` 解包后就是字符串——首跑抓到过对它再
  `[0]` 取成首字符的 bug，`aarch64` 变 `a`，立即修正）。

## 4. 验证

- 定向：`tests/test_desktop_product_suffixes.py` 2 passed（首跑抓
  bug 修正后即过）；关联面 `test_desktop_flavor_vocabulary.py`
  （W29）、`test_desktop_workflow_script_refs.py`（W32）、
  `test_desktop_r2_release_paths.py`（W33）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3175 passed / 28 skipped / 0 failed**（3203 条，
  约 10m34s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **5/5**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 build_macos.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 replace 词表 `aarch64-full.dmg` 改值 | W34b 红（NSIS ∪ DMG 对不上）、W34a 绿 |
| M2 NSIS 对 `_x64-setup.exe` 改值 | W34b 红（并集对不上）、W34a 绿 |
| M3 build_macos 分支 `-full` 改值 | W34b 红（DMG 对漂移）、W34a 绿 |
| M4 bash 列表删 `aarch64-full.dmg` | W34b 红（列表对不上词表）、W34a 绿 |
| M5 NSIS 对行复制一份 | W34a 红（锚恰一处破坏）、W34b 绿（取首值集合不变） |

## 5. 边界与遗留

- 只判后缀词表字面同账——不判产物名里 version 段的取值（W18 的
  版本五源已管）、不判 `.sha256`/`.sig` 派生后缀（由同一 name 推出，
  词表同账即覆盖）、不判 workflow/脚本的执行行为（CI 负责）。
- 四轮连推（二十）续 **R202 更新通道清单端到端同账（W35）**、
  **R203 release-notes 引用面（W36）**、**R204 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`d1e3c2d`** 推送后 run **42395500680**：**10 job 全
  `success`**（17:16:43→17:34:42 UTC，约 17m59s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42395500680`，bot 提交 **`cb18ec1`**）。R202 回填。

## 7. 提交

- 改动：`tests/test_desktop_product_suffixes.py`（W34）、R201 文档、
  R200 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R201 一条）、
  `JUDGEMENT_LEDGER.md`（§10.73）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
