# DeterminFlow (xs2) 交接报告 — Round 211（smoke_installer.ps1 调用面参数同账：W42）

> 单 profile。四轮连推（二十二）第 3 轮：把 PowerShell 冒烟脚本
> `smoke_installer.ps1` 的调用面钉成「参数集合恰等 + ValidateSet 第六
> 源并入 flavor 词表」。生产代码零改动，本轮无修复——调用面现同账。
> 变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_smoke_installer_params.py` 新增 **W42a/W42b**：
  smoke_installer.ps1 的 call site 在 desktop workflow 恰一处、脚本
  `param()` 恰 2 个参数（W42a）；call site 参数集合 == `param()`
  集合（双向恰等 `[$Installer, $Flavor]`）+ `ValidateSet` 值集合 ==
  {core, full}（W29 五源之外的 **flavor 词表第六源**，开工实测补面）
  （W42b）。总用例 3235 → **3239**（+2 钉测、+1 N3 本篇、+1 D1 因
  R210 §6 进入回填扫描区间）。
- 变异 **4/4**：call site `-Flavor` 错拼 / 脚本 `$Flavor` 改名 /
  `ValidateSet` 改值（W42b 各自独红）、call site 复制一份（W42a
  独红）。
- **回填**：R210 §6（run `42417724695` / bot `dd3f2f5`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`smoke_installer.ps1`（装包冒烟）被 desktop workflow 调用恰 1 处
（desktop-windows.yml 的 smoke 步）：`-Installer …` `-Flavor …`；
脚本 `param()` 定义恰 2 个参数（`$Installer` Mandatory / `$Flavor =
"core"`，带 `[ValidateSet("core", "full")]`）。调用面漂移无人判：
workflow 写错参数名（PowerShell 把绑不上的参数当位置参数吞掉或直接
报错）、或脚本改名参数而 workflow 没跟。且开工实测发现
`ValidateSet` 是 **flavor 词表的第六源**——W29 钉的五源（build_macos
choices+运行时集合、build_backend choices、verify_bundle choices、
两 workflow matrix）之外，冒烟脚本允许的 flavor 集合漂移无人判：
full 冒烟可能拿 core 的校验口径。W40 管对称调用的两脚本、W41 管
smoke_backend 的超时账，PowerShell 侧的参数面第一次进射程。

W42 的分工沿用定式：W42a 管锚（call site 恰一处、param() 恰 2 个
——**只钉数量**，参数名集合归 W42b 同账，避免改名变异双红）；W42b
管值（参数集合双向恰等 + ValidateSet 词表）。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现同账：`$Installer`/`$Flavor` 双向恰等、
  ValidateSet == {core, full}，纯钉住）。

### 3.2 `tests/test_desktop_smoke_installer_params.py`（W42a / W42b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W42a | call site 恰一处；`param()` 恰 2 个参数（只钉数量） | desktop-windows.yml + desktop/scripts/smoke_installer.ps1 |
| W42b | call site 参数集合 == `param()` 集合；`ValidateSet` 值集合 == {core, full} | 同上 |

实现要点：

- `param()` 块提取用 `param\((.*?)^\)`（re.S|re.M）——首版
  `param\((.*?)\)` 被第一个内层 `)`（`[Parameter(Mandatory = $true)]`）
  截断，块内空无一物；闭合锚必须是**行首独立 `)`**。
- `[string]$X` 提取只在 param() 块内做——脚本正文的局部变量同名
  形状不收（首版全脚本提取收到 11 个）。
- W42a 首版把参数名集合（sorted == [Flavor, Installer]）放进去，
  `$Flavor` 改名变异双红——改成只钉数量后重跑变异确认各自独红。

## 4. 验证

- 定向：`tests/test_desktop_smoke_installer_params.py` 2 passed（首跑
  修正 param 块提取与 W42a 数量钉后即过）；关联面
  `test_desktop_flavor_vocabulary.py`（W29 五源）、
  `test_desktop_symmetric_script_calls.py`（W40）、
  `test_desktop_smoke_backend_timeouts.py`（W41）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3211 passed / 28 skipped / 0 failed**（3239 条，
  约 11m01s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-windows.yml 与 smoke_installer.ps1 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 call site `-Flavor` 错拼 `-Flavour` | W42b 红（参数集合不等）、W42a 绿 |
| M2 脚本 `[string]$Flavor` 改名 | W42b 红（参数集合不等）、W42a 绿 |
| M3 `ValidateSet("core", "full")` → `("core", "complete")` | W42b 红（第六源词表漂移）、W42a 绿 |
| M4 call site 行复制一份 | W42a 红（恰一处破坏）、W42b 绿（参数集合不变） |

## 5. 边界与遗留

- 只判参数名与 ValidateSet 值的字面同账——不判 PowerShell 参数绑定
  语义（大小写不敏感是运行时行为）、不判 `$Flavor` 默认值取值
  （默认值在词表内即可）、不判脚本执行行为（CI 负责）。
- 四轮连推（二十二）收官 **R212 收口轮（R209–R212 四账）+ 登记
  R213–R216**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_smoke_installer_params.py`（W42）、R211
  文档、R210 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R211 一条）、
  `JUDGEMENT_LEDGER.md`（§10.83）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
