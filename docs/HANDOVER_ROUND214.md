# DeterminFlow (xs2) 交接报告 — Round 214（macOS 产物路径前缀同账：W44）

> 单 profile。四轮连推（二十三）第 2 轮：把 `build_macos.py` 的产物
> 路径（pathlib 拼装）与 `desktop-macos.yml` verify 调用的字面路径钉
> 成两段同账（app 路径 + dmg 目录前缀）。生产代码零改动，本轮无修复
> ——路径现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_product_paths.py` 新增 **W44a/W44b**：脚本的
  bundle 组合行、app 产物行、dmg 产物行各恰一处 + yml 的
  `--app-bundle`/`--dmg` 各恰一处（W44a）；脚本拼出的 app 路径（段
  join）== yml `--app-bundle` 字面路径、脚本拼出的 dmg 目录前缀 ==
  yml `--dmg` 去 `*.dmg` 后的前缀（W44b）。总用例 3245 → **3249**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R213 §6 进入回填扫描区间）。
- 变异 **4/4**：yml app 路径改值 / 脚本 dmg 目录改值 / 脚本 app 名
  改值（W44b 各自独红）、yml `--app-bundle` 复制一份（W44a 独红）。
- **回填**：R213 §6（run `42424569207` / bot `5efa2d7`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

macOS 产物路径有两份账：`build_macos.py` 用 pathlib 拼出产物位置
（`bundle = desktop / "src-tauri" / "target" / "release" / "bundle"`，
`app = bundle / "macos" / "DeterminFlow.app"`，`dmg = bundle / "dmg" /
f"DeterminFlow_{version}_aarch64{suffix}.dmg"`），
`desktop-macos.yml` 的 verify 调用按字面路径消费（`--app-bundle
desktop/src-tauri/target/release/bundle/macos/DeterminFlow.app`、
`--dmg desktop/src-tauri/target/release/bundle/dmg/*.dmg`）。路径漂移
无人判：产物挪目录（如 tauri 升级改 bundle 布局）只改一边——build
出来的 app/dmg 落在新位置而 verify 按旧路径找，CI 到 run 时才炸
（FileNotFoundError），或 verify 找到的根本不是刚构建的产物。W34 管
dmg 的**文件名后缀词表**，这里的路径**目录前缀**第一次进射程。

W44 的锚选在「段 join == 字面路径」：脚本侧从组合行提取各段、join
成完整路径再与 yml 字面比——脚本改任何一段（或 yml 改字面）都翻红，
不用为 pathlib 的拼装方式做脆弱的字面匹配。

## 3. 实现

### 3.1 生产代码

- 零改动（路径现同账，纯钉住）。

### 3.2 `tests/test_desktop_product_paths.py`（W44a / W44b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W44a | 脚本 bundle 组合行 / app 产物行 / dmg 产物行各恰一处；yml `--app-bundle`/`--dmg` 各恰一处 | desktop/scripts/build_macos.py + desktop-macos.yml |
| W44b | 脚本拼出的 app 路径 == yml `--app-bundle`；脚本 dmg 目录前缀 == yml `--dmg` 去 `*.dmg` 后的前缀 | 同上 |

实现要点：

- 脚本侧三行各有专属形状正则（`bundle = desktop / "…" / …`、
  `app = bundle / "…" / "…"`、`dmg = bundle / "…" / f"`），段值进
  join——脚本改段值（M2/M3）W44a 仍绿、W44b 红。
- yml 的 `--dmg` 是通配（`*.dmg`），比对前先剥通配取目录前缀，形状
  不对（非 `<目录>/*.dmg`）显式红。

## 4. 验证

- 定向：`tests/test_desktop_product_paths.py` 2 passed（首跑即过）；
  关联面 `test_desktop_product_suffixes.py`（W34，dmg 文件名词表）、
  `test_desktop_verify_bundle_flags.py`（W38）、
  `test_desktop_symmetric_script_calls.py`（W40）全绿；S2/S3/S5 在
  本提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3221 passed / 28 skipped / 0 failed**（3249 条，
  约 11m12s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-macos.yml 与 build_macos.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 yml `--app-bundle` 路径改值 | W44b 红（app 路径不同账）、W44a 绿 |
| M2 脚本 dmg 目录 `"dmg"` → `"dmg-out"` | W44b 红（dmg 前缀不同账）、W44a 绿 |
| M3 脚本 app 名改值 | W44b 红（app 路径不同账）、W44a 绿 |
| M4 yml `--app-bundle` 复制一份 | W44a 红（恰一处破坏）、W44b 绿 |

## 5. 边界与遗留

- 只判路径字面同账——不判 dmg 文件名模板（W34 的 aarch64 后缀词表
  已管）、不判 tauri 实际输出布局（tauri 升级行为，CI 负责）、不判
  verify 的执行行为。
- 四轮连推（二十三）续 **R215 desktop workflow npm script 调用面
  （W45）**、**R216 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`02d6835`** 推送后 run **42427066751**：**10 job 全
  `success`**（23:50:43→00:09:18 UTC，约 18m35s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42427066751`，bot 提交 **`7593934`**）。R215 回填。

## 7. 提交

- 改动：`tests/test_desktop_product_paths.py`（W44）、R214 文档、
  R213 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R214 一条）、
  `JUDGEMENT_LEDGER.md`（§10.86）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
