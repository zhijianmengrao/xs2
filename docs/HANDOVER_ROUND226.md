# DeterminFlow (xs2) 交接报告 — Round 226（应用显示名两脚本同账：W53）

> 单 profile。四轮连推（二十六）第 2 轮：把应用显示名 "DeterminFlow"
> 的三处来源（DMG 卷名 / app 产物名 / smoke 的 DisplayName 查找名）
> 钉成逐字同账。生产代码零改动，本轮无修复——显示名现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_display_name.py` 新增 **W53a/W53b**：volname 行、
  app 产物行、ProductName 行各恰一处（W53a）；三处名字逐字恰等
  （== "DeterminFlow"）（W53b）。总用例 3287 → **3291**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R225 §6 进入回填扫描区间）。
- 变异 **4/4**：volname / app 名 / ProductName 各自漂移（W53b 各自
  独红）、ProductName 行复制（W53a 独红——首版计数守卫耦合已拆）。
- **回填**：R225 §6（run `42452739029` / bot `34168ef`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

应用显示名 "DeterminFlow" 有三处来源：`build_macos.py` 的
`hdiutil create -volname "DeterminFlow"`（L44，DMG 卷名）与
`app = bundle / "macos" / "DeterminFlow.app"`（L31，app 产物名段）、
`smoke_installer.ps1` 的 `$ProductName = "DeterminFlow"`（L9，安装后
按 DisplayName 找已装应用）。显示名漂移无人判：一边改名（如加品牌
段）而其余没跟——DMG 卷名与 app 名不一致（Finder 里两个名字）、或
smoke 按 DisplayName 找不到已装应用（安装冒烟 run 时才炸）。W51 管
产物名**前缀**，显示名的**三处字面**第一次进射程。

W53 的分工沿用定式：W53a 管计数（三行各恰一处），W53b 管值（三处
== "DeterminFlow"）；首版把计数守卫放进共用的 `_names()`，「ProductName
复制」变异双红——拆出 `_first_names()`（只守存在）后各自独红
（W47 教训定式）。

## 3. 实现

### 3.1 生产代码

- 零改动（显示名现同账，纯钉住）。

### 3.2 `tests/test_desktop_display_name.py`（W53a / W53b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W53a | volname 行 / app 产物行 / ProductName 行各恰一处 | build_macos.py + smoke_installer.ps1 |
| W53b | 三处名字逐字恰等（== "DeterminFlow"；存在才判，缺失归 W53a） | 同上 |

实现要点：

- app 名从 `app = bundle / "macos" / "DeterminFlow.app"` 提取时剥掉
  `.app` 后缀再比——后缀是格式不是名字。
- W53b 的错误消息点名三处角色（DMG 卷名 / app 名 / DisplayName 查找
  名），漂移的后果写在账面上。

## 4. 验证

- 定向：`tests/test_desktop_display_name.py` 2 passed（首跑拆计数
  守卫后即过）；关联面 `test_community_current_version.py`（W52）、
  `test_desktop_product_prefix.py`（W51）、
  `test_desktop_paramless_scripts.py`（W47）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3263 passed / 28 skipped / 0 failed**（3291 条，
  约 13m19s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  build_macos.py 与 smoke_installer.ps1 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 volname `DeterminFlow` → `DeterminFlowX` | W53b 红（名不等）、W53a 绿 |
| M2 app 名漂移 | W53b 红（名不等）、W53a 绿 |
| M3 ProductName 漂移 | W53b 红（名不等）、W53a 绿 |
| M4 ProductName 行复制 | W53a 红（1→2）、W53b 绿（取首值同账） |

## 5. 边界与遗留

- 只判显示名的字面同账——不判 `.app` 后缀（路径面 W44 已管）、不判
  `$ProductName` 的查询语义（PowerShell Get-Package 行为）、不判执行
  行为（CI 负责）、不判其他 `DeterminFlow` 字面（产物名前缀 W51 已管）。
- 四轮连推（二十六）续 **R227 安装数据目录标识同账（W54）**、
  **R228 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_display_name.py`（W53）、R226 文档、R225
  §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4 H2/一行
  + §6.1）、`PROJECT_INFO.md`（H2 + R226 一条）、
  `JUDGEMENT_LEDGER.md`（§10.98）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
