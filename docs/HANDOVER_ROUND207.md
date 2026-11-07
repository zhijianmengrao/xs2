# DeterminFlow (xs2) 交接报告 — Round 207（create_update_manifest 调用面参数同账：W39）

> 单 profile。四轮连推（二十一）第 3 轮：把 `create_update_manifest.py`
> 的调用面钉成「flag 多重集 == argparse option 集合」的恰等账。生产
> 代码零改动，本轮无修复——调用面现恰等。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_manifest_flags.py` 新增 **W39a/W39b**：
  create_update_manifest 的 call site 在 desktop workflow 恰一处、
  脚本 argparse 定义非空（W39a）；call site 的 flag 多重集 ==
  argparse option 集合（7 个 sorted 逐字恰等——漏 flag、错字、重复、
  脚本侧增删都翻红）（W39b）。总用例 3221 → **3225**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R206 §6 进入回填扫描区间）。
- 变异 **4/4**：call site 删 `--pub-date` / 脚本 `--base-url` 改名 /
  call site 重复 `--output`（W39b 各自独红）、整个 call site 复制
  一份（W39a 独红）。
- **回填**：R206 §6（run `42408122329` / bot `5fcf0f6`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`create_update_manifest.py` 生成更新通道的 `latest.json`，被 desktop
workflow 调用**恰 1 处**（desktop-windows.yml 的 create_update_manifest
步），脚本 argparse 定义 7 个 option（--version / --installer /
--signature / --base-url / --notes-file / --pub-date / --output），
call site 把 7 个全用——脚本 option 集合与调用面是一份账的两半。漂移
无人判：workflow 写错 flag 字、或脚本增删 option 而 call site 没跟
——清单缺一段账（如 `--pub-date` 丢了，latest.json 的发布时间就缺）
或 run 时 unrecognized arguments。W35 管的是 `--base-url`/`--output`
的**取值形状**，这里管 flag 名本身的可解析。W38 的同型面推进到
「call site flag 多重集 == option 集合」的恰等（W38 是单向 ⊆，
这里因为 7 个全用可以双向恰等）。

W39 开工实测抓到过一个提取陷阱：call site 的 `--pub-date` 取值里内嵌
`$(git show -s --format=%cI …)`——naive 的「块内所有 `--xxx`」提取会
把 git 的 `--format` 误收成第 8 个 flag。修正：flag 只认**续行行首**
（`(?:\\\r?\n)\s*(--[a-z][a-z0-9-]*)`），7 个真 flag 全部在续行首，
`$(…)` 内的都在行中。

## 3. 实现

### 3.1 生产代码

- 零改动（call site 7 flag == argparse 7 option，纯钉住）。

### 3.2 `tests/test_desktop_manifest_flags.py`（W39a / W39b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W39a | call site 恰一处；脚本 argparse 定义非空（锚存在） | desktop-windows.yml + desktop/scripts/create_update_manifest.py |
| W39b | call site 的 flag 多重集 == argparse option 集合（sorted 逐字恰等，option 数恰 7） | 同上 |

实现要点：

- 折行提取沿用 W38 的展开循环正则 `((?:[^\\\n]|\\\r?\n)*)`。
- flag 提取只认续行行首——`--pub-date` 取值内嵌的
  `$(git show -s --format=%cI …)` 的 `--format`（git flag）不误收。
- 恰等用 sorted 列表逐字比较（多重集语义）：重复 flag（8 项）与
  缺 flag（6 项）都翻红。

## 4. 验证

- 定向：`tests/test_desktop_manifest_flags.py` 2 passed（首跑修正
  flag 提取后即过）；关联面 `test_desktop_verify_bundle_flags.py`
  （W38）、`test_desktop_updater_channel.py`（W35）、
  `test_desktop_release_notes_refs.py`（W36）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3197 passed / 28 skipped / 0 failed**（3225 条，
  约 10m52s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-windows.yml 与 create_update_manifest.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 call site 删 `--pub-date` 行 | W39b 红（6 ≠ 7）、W39a 绿 |
| M2 脚本 `--base-url` 改名 `--base-uri` | W39b 红（集合不等）、W39a 绿 |
| M3 call site 重复 `--output` 行 | W39b 红（8 ≠ 7，多重集翻红）、W39a 绿 |
| M4 整个 call site 复制一份（完整 7 flag 块） | W39a 红（恰一处破坏）、W39b 绿（每块各自 == option 集合） |

## 5. 边界与遗留

- 只判 flag 名的字面同账——不判 flag 取值（`--base-url` 的形状由 W35
  钉、`--notes-file` 引用由 W36 覆盖、`--output` 文件名由 W35 钉）、
  不判脚本执行行为（CI 负责）。
- 四轮连推（二十一）收官 **R208 收口轮（R205–R208 四账）+ 登记
  R209–R212**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`722c03e`** 推送后 run **42410769833**：**10 job 全
  `success`**（20:22:46→20:35:35 UTC，约 12m49s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42410769833`，bot 提交 **`52a3e2a`**）。R208 回填。

## 7. 提交

- 改动：`tests/test_desktop_manifest_flags.py`（W39）、R207 文档、
  R206 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R207 一条）、
  `JUDGEMENT_LEDGER.md`（§10.79）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
