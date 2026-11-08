# DeterminFlow (xs2) 交接报告 — Round 227（安装数据目录标识同账：W54）

> 单 profile。四轮连推（二十六）第 3 轮：把 smoke_installer.ps1 的
> UserData 目录标识与 tauri.conf.json 的 identifier 钉成逐字同账。
> 生产代码零改动，本轮无修复——标识现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_user_data_identifier.py` 新增 **W54a/W54b**：
  脚本的 `$UserData` 赋值恰一处 + conf 的 `identifier` 存在（W54a）；
  两处 id 逐字恰等（== `io.determinflow.desktop`；存在才判，缺失归
  W54a）（W54b）。总用例 3291 → **3295**（+2 钉测、+1 N3 本篇、+1 D1
  因 R226 §6 进入回填扫描区间）。
- 变异 **4/4**：脚本 id 漂移 / conf identifier 漂移（W54b 各自独红）、
  UserData 行删除 / 复制（W54a 各自独红）。
- **回填**：R226 §6（run `42455344656` / bot `1a0c9b8`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

安装数据目录的标识有两份账：`smoke_installer.ps1` 的
`$UserData = Join-Path $env:LOCALAPPDATA "io.determinflow.desktop"`
（L10，冒烟校验已装应用的数据目录）与 `tauri.conf.json` 的
`"identifier": "io.determinflow.desktop"`（L5，tauri 按 identifier
建数据目录）。标识漂移无人判：identifier 改名（换品牌/换域）而
smoke 的 UserData 没跟——smoke 检查的是一个不存在的目录（或旧应用
的目录），安装冒烟「通过」但什么都没验到。W22 管过 bundle
identifier 的 macOS 面与 conf 的其他键，identifier 与 **UserData
目录**的对应第一次进射程。

W54 的分工沿用定式（W47/W49 定式从一开始就应用）：W54a 管计数
（UserData 行恰一处 + identifier 存在），W54b 只判存在的值（`for
value in findall(...)` 循环，缺失归 W54a）。

## 3. 实现

### 3.1 生产代码

- 零改动（标识现同账，纯钉住）。

### 3.2 `tests/test_desktop_user_data_identifier.py`（W54a / W54b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W54a | 脚本 `$UserData` 赋值恰一处；conf 的 `identifier` 存在（json.load 解析） | smoke_installer.ps1 + tauri.conf.json |
| W54b | 两处 id 逐字恰等（存在才判） | 同上 |

实现要点：

- conf 侧用 `json.load` 解析取 `identifier` 键（不用正则）。
- W54b 的循环体对每个存在的 UserData 赋值判值——行删除时循环体不
  执行（W54a 已红），不做存在断言。

## 4. 验证

- 定向：`tests/test_desktop_user_data_identifier.py` 2 passed（首跑
  补缺失的 `_text` 辅助后即过）；关联面
  `test_desktop_display_name.py`（W53）、`test_desktop_macos_identifier`
  （W22，bundle identifier 面）、`test_desktop_paramless_scripts.py`
  （W47）全绿；S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正
  之前），本提交翻正后全绿。
- 本机全量：**3267 passed / 28 skipped / 0 failed**（3295 条，
  约 13m07s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  tauri.conf.json 与 smoke_installer.ps1 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 脚本 id 漂移（…desktop2） | W54b 红（id 不等）、W54a 绿 |
| M2 conf identifier 漂移 | W54b 红（id 不等）、W54a 绿 |
| M3 脚本 UserData 行删除 | W54a 红（1→0）、W54b 绿（无值可判） |
| M4 脚本 UserData 行复制 | W54a 红（1→2）、W54b 绿 |

## 5. 边界与遗留

- 只判标识的字面同账——不判 `LOCALAPPDATA` 的平台语义、不判 tauri
  按 identifier 建目录的运行时行为（tauri 负责）、不判 conf 的其他键
  （W22/W27 已管）、不判执行行为（CI 负责）。
- 四轮连推（二十六）收官 **R228 收口轮（R225–R228 四账）+ 登记
  R229–R232**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_user_data_identifier.py`（W54）、R227
  文档、R226 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R227 一条）、
  `JUDGEMENT_LEDGER.md`（§10.99）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
