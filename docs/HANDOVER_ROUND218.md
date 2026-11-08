# DeterminFlow (xs2) 交接报告 — Round 218（macOS 无参前置脚本调用面：W47）

> 单 profile。四轮连推（二十四）第 2 轮：把 desktop-macos.yml 的两个
> 无参前置脚本调用钉成「各恰一处 + 真无参」。生产代码零改动，本轮
> 无修复——调用面现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_paramless_scripts.py` 新增 **W47a/W47b**：
  `install_macos_build_dependencies.py` 与 `generate_macos_icon.py`
  在 desktop-macos.yml 各恰 1 处调用（W47a）；两处调用的参数尾为空
  （真无参，任何一方加参显式红）（W47b）。总用例 3259 → **3263**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R217 §6 进入回填扫描区间）。
- 变异 **4/4**：install 调用加 `--verbose` / icon 调用加 `--force`
  （W47b 各自独红）、icon 调用删除 / install 调用复制（W47a 各自
  独红）。
- **回填**：R217 §6（run `42434262921` / bot `7e21fe4`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop-macos.yml 里有两个无参前置脚本：`install_macos_build_
dependencies.py`（装构建依赖）与 `generate_macos_icon.py`（生成图标）。
至此 9 脚本调用面（W32 的 17 处路径账）全部有参数/计数账：带参脚本
由 W38（verify_bundle 7/1/3）、W39（create_update_manifest 7==7）、
W40（build_backend/refresh 对称）、W41（smoke_backend 超时）、W42
（smoke_installer PowerShell 参数）钉住，这两个无参脚本由 W47 收口
——有人给前置脚本加 flag（脚本不认识，argparse run 时才炸）或删
调用（依赖没装/图标没生成，后续步骤炸得更隐蔽）都显式红。

W47 的分工沿用定式：W47a 管计数（各恰 1 处），W47b 管无参形状
（参数尾为空）；调用缺失归 W47a，W47b 不做存在守卫（首版的
`assert tails` 让「删调用」变异双红，改后各自独红）。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现同账，纯钉住）。

### 3.2 `tests/test_desktop_paramless_scripts.py`（W47a / W47b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W47a | 两脚本在 desktop-macos.yml 各恰 1 处调用 | desktop-macos.yml |
| W47b | 存在的调用的参数尾为空（空白归一） | 同上 |

实现要点：

- 参数尾提取沿用展开循环正则（W38 定式）+ 空白归一（W40 定式）。
- W47b 的无参账只对「存在的调用」判——调用缺失（计数 0）是 W47a
  的账；`assert not tails or tails[0] == ""`。

## 4. 验证

- 定向：`tests/test_desktop_paramless_scripts.py` 2 passed（首跑修正
  存在守卫耦合后即过）；关联面
  `test_desktop_workflow_script_refs.py`（W32，路径账）、
  `test_desktop_symmetric_script_calls.py`（W40）、
  `test_desktop_tag_version_strip.py`（W46）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3235 passed / 28 skipped / 0 failed**（3263 条，
  约 12m27s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-macos.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 install 调用加 `--verbose` | W47b 红（无参破坏）、W47a 绿 |
| M2 icon 调用删除 | W47a 红（1→0）、W47b 绿（无调用可判） |
| M3 install 调用复制一份 | W47a 红（1→2）、W47b 绿 |
| M4 icon 调用加 `--force` | W47b 红（无参破坏）、W47a 绿 |

## 5. 边界与遗留

- 只判调用计数与无参形状——不判脚本内部行为（CI 负责）、不判脚本
  间执行顺序（step 顺序是 workflow 结构账）、不判 windows 侧（两
  脚本都是 macOS 专属，desktop-windows.yml 实测 0 处）。
- 四轮连推（二十四）续 **R219 backend 安装段同账（W48）**、
  **R220 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_paramless_scripts.py`（W47）、R218 文档、
  R217 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R218 一条）、
  `JUDGEMENT_LEDGER.md`（§10.90）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
