# DeterminFlow (xs2) 交接报告 — Round 234（create_manifest import 调用面同账：W59）

> 单 profile。四轮连推（二十八）第 2 轮：把 replace-desktop-assets.yml
> 的 `create_manifest` import 调用（6 个 kwarg）与函数 keyword-only
> 形参、脚本 `main()` 自调用钉成三方恰等。生产代码零改动，本轮无修复
> ——调用面现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_manifest_import_call.py` 新增 **W59a/W59b**：
  workflow 调用恰一处、函数定义恰一处且 keyword-only 形参非空、脚本
  自调用恰一处（W59a）；两处调用的 kwarg 集合 == 函数 keyword-only
  形参集合（W59b）。总用例 3315 → **3319**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R233 §6 进入回填扫描区间）。
- 变异 **4/4**：workflow kwarg 错拼 / `notes` kwarg 删除（W59b 各自
  独红）、workflow 调用块复制 / 脚本自调用删除（W59a 各自独红）——
  均为单红（W59b 遍历现有调用、不做出席守卫，W55 的 `[0]` 索引双红
  教训已避开）。
- **回填**：R233 §6（run `42629037234` / bot `f94b1a7`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 用
`from desktop.scripts.create_update_manifest import create_manifest`
（L70）引入函数，并按 6 个 keyword-only 实参调用（L92–97：version /
installer / signature / base_url / notes / pub_date）；函数签名
（create_update_manifest.py L11–18）恰为这 6 个 keyword-only 形参；
脚本 `main()` 内另一处调用同 6 键（L53–60）。任何一处漂移：workflow
写错 kwarg 名 → 运行时 `TypeError: unexpected keyword argument`；
脚本增删形参而 call site 没跟 → 同上——发版第 2 步（校验安装器之后、
上传之前）直接失败。

W39 已钉 desktop-windows.yml 的 **CLI flag** 面（create_update_manifest
的 7 个 argparse option），W59 把 **import 调用面**（kwargs ↔ 函数
keyword-only 形参）第一次推进射程。

W59 的锚选在「三方恰等」：workflow 调用、脚本自调用、函数形参。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现同账，纯钉住）。

### 3.2 `tests/test_desktop_manifest_import_call.py`（W59a / W59b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W59a | workflow 调用恰 1 处；函数定义恰 1 处且 kwonly 非空；自调用恰 1 处 | replace-desktop-assets.yml + create_update_manifest.py |
| W59b | 两处调用的 kwarg 集合 == 函数 keyword-only 形参集合 | 同上 |

实现要点：

- workflow 侧：`create_manifest\(([^)]*)\)` 取调用块，再用
  `(?:^|,)\s*(\w+)\s*=` 取 kwarg 名——块内 f-string 无嵌套括号。
- 脚本侧用 **ast**（`FunctionDef.args.kwonlyargs` / `Call.keywords`）
  ——比正则稳，定义缺失/重复由 W59a 计数。
- W59b 遍历现有调用判值，调用缺失直接跳过（缺失归 W59a）；
  这是 W47/W49 定式，避免 W55 首版 `[0]` 索引在「删除」变异上
  制造 IndexError 双红。

## 4. 验证

- 定向：`tests/test_desktop_manifest_import_call.py` 2 passed（首跑
  即过）；关联面 `test_desktop_manifest_flags.py`（W39）全绿。
- 本机全量：**3291 passed / 28 skipped / 0 failed**（3319 条，
  约 8m26s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两文件均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 workflow kwarg `base_url` 错拼为 `baseurl` | W59b 红（形参缺 base_url）、W59a 绿 |
| M2 workflow kwarg `notes` 删除 | W59b 红（形参缺 notes）、W59a 绿 |
| M3 workflow 调用块复制 | W59a 红（1→2）、W59b 绿（两处 kwarg 仍恰等） |
| M4 脚本自调用删除 | W59a 红（1→0）、W59b 绿（无自调用可判） |

## 5. 边界与遗留

- 只判 kwarg 名的字面同账——不判取值（version/notes 等由其他判据
  负责）、不判 `create_manifest` 的执行行为（CI 负责）、不判 CLI 面
  （W39 已钉）。
- 四轮连推（二十八）续 **R235 publish_r2_release 调用面同账（W60）**、
  **R236 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`6c7c2c3`** 推送后 run **42637802235**：**10 job 全
  `success`**（14:45:33→15:01:05 UTC，约 15m32s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42637802235`，bot 提交 **`35073ee`**）。R235 回填。

## 7. 提交

- 改动：`tests/test_desktop_manifest_import_call.py`（W59）、R234
  文档、R233 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R234 一条）、
  `JUDGEMENT_LEDGER.md`（§10.106）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
