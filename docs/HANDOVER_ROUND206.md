# DeterminFlow (xs2) 交接报告 — Round 206（verify_bundle 调用面参数同账：W38）

> 单 profile。四轮连推（二十一）第 2 轮：把 `verify_bundle.py` 的
> 调用面从「路径可解析」（W32）推进到「flag 可解析」——三处 call
> site 的每个 flag ∈ 脚本 argparse option 集合。生产代码零改动，
> 本轮无修复——调用面现可解析。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_verify_bundle_flags.py` 新增 **W38a/W38b**：
  三处 call site 各恰一处（desktop-macos.yml 1 / desktop-windows.yml
  2）、每处 flag 数语料守卫（**7/1/3**）（W38a）；三处用到的每个
  flag ∈ 脚本 argparse 的 option 集合，单向（定义未调用是脚本 API
  不判，调用未定义当场红）（W38b）。总用例 3217 → **3221**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R205 §6 进入回填扫描区间）。
- 变异 **4/4**：workflow flag 写错字 / 脚本 option 改名（W38b 各自
  独红）、macos call site 删 flag / windows call site 删 flag（W38a
  各自独红）。
- **回填**：R205 §6（run `42405676802` / bot `387b7b0`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`verify_bundle.py` 被 desktop workflow 调用 3 处，flag 家族随平台/
阶段不同：macos 1 处 7 flag（flavor + app-bundle + dmg + 三个
--verify-macos-* + --forbid-updater-artifacts）、windows 2 处（构建
后核验 1 flag、发布前核验 3 flag）。调用面漂移无人判：workflow 里
flag 写错字、或脚本改名 option 而 workflow 没跟，argparse 直接
`unrecognized arguments` 退非零——CI 到 run 时才炸，且炸在发版路径
深处。W32 管的是脚本**路径**可解析，这里把面推进到 **flag** 可解析。

R204 §3 登记时写的是「macos 六 flag」——开工实测发现是 **7 flag**：
`--forbid-updater-artifacts` 在第 65 行，登记时 sed 窗口截断漏看
（实测先行纪律的又一次兜底：判据写的是实测值 7/1/3，不是登记值
6/1/3）。

## 3. 实现

### 3.1 生产代码

- 零改动（三处 call site 的 flag 全部可解析，纯钉住）。

### 3.2 `tests/test_desktop_verify_bundle_flags.py`（W38a / W38b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W38a | 三处 call site 各恰一处（macos 1 / windows 2）；每处 flag 数恰等 7/1/3 | desktop-macos.yml + desktop-windows.yml |
| W38b | call site 用到的每个 flag ∈ 脚本 argparse option 集合（单向） | 同上 + desktop/scripts/verify_bundle.py |

实现要点：

- 折行调用提取用**展开循环**正则 `` ((?:[^\\\n]|\\\r?\n)*) ``：
  首版写 `` ([^\n]*(?:\\\r?\n[^\n]*)*) `` 时贪婪行吞吃让可选组零
  迭代就完成匹配（无失败不回溯），折行永远吃不到——两个互斥分支
  （非反斜杠字符 ∣ 反斜杠+换行）才让续行稳定进组。
- macOS call site 是 CRLF 折行（``\\\r\n``），正则容忍
  ``\\\r?\n``；windows 两处是单行。
- flag 计数锚 7/1/3 是实测值（R204 §3 登记的 6 被 --forbid-updater-
  artifacts 修正）；W38b 的 option 集合从
  ``add_argument\(\s*"(--[^"]+)"`` 提取。

## 4. 验证

- 定向：`tests/test_desktop_verify_bundle_flags.py` 2 passed（首跑
  修正折行正则与 flag 计数后即过）；关联面
  `test_desktop_flavor_vocabulary.py`（W29，--expected-flavor
  choices）、`test_desktop_workflow_script_refs.py`（W32，路径）、
  `test_desktop_gh_release_uploads.py`（W37）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3193 passed / 28 skipped / 0 failed**（3221 条，
  约 10m46s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 verify_bundle.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 macos `--dmg` 写成 `--dmag` | W38b 红（调用未定义 flag）、W38a 绿（计数不变） |
| M2 脚本 `--updater-signature` 改名 `--updater-sig` | W38b 红（调用未定义 flag）、W38a 绿 |
| M3 macos call site 删 `--verify-dmg-container` | W38a 红（7→6）、W38b 绿（剩余 flag 全定义） |
| M4 windows call site 删 `--desktop-executable` | W38a 红（3→2）、W38b 绿 |

## 5. 边界与遗留

- 只判 flag 名的字面可解析——不判 flag 取值（`--expected-flavor`
  choices 由 W29 钉）、不判 flag 顺序与折行写法、不判脚本执行行为
  （CI 负责）、不判 `--forbid-updater-artifacts` 等 workflow 侧未用
  option（脚本 API 面不收缩）。
- 四轮连推（二十一）续 **R207 create_update_manifest 调用面参数
  同账（W39）**、**R208 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_verify_bundle_flags.py`（W38）、R206 文档、
  R205 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R206 一条）、
  `JUDGEMENT_LEDGER.md`（§10.78）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
