# DeterminFlow (xs2) 交接报告 — Round 221（verify 调用第三段同账：W49）

> 单 profile。四轮连推（二十五）第 1 轮：把 desktop-macos.yml verify
> 调用的第三段路径（`--forbid-updater-artifacts` 取值）钉进 W44 的
> bundle 前缀账。生产代码零改动，本轮无修复——三段现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_forbid_bundle_path.py` 新增 **W49a/W49b**：
  `--forbid-updater-artifacts` 取值恰一处 + 脚本 bundle 组合行恰一处
  （W49a）；forbid 取值 == 脚本拼出的 bundle 前缀（W49b）。总用例
  3269 → **3273**（+2 钉测、+1 N3 本篇、+1 D1 因 R220 §6 进入回填
  扫描区间）。
- 变异 **4/4**：yml forbid 取值漂移 / 脚本 bundle 段漂移（W49b 各自
  独红）、forbid 行删除 / 复制（W49a 各自独红）。
- **回填**：R220 §6（run `42441266199` / bot `4430300`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop-macos.yml 的 verify_bundle 调用有三段路径：`--app-bundle` 与
`--dmg`（W44 已钉）+ `--forbid-updater-artifacts
desktop/src-tauri/target/release/bundle`（L65，禁 updater 资产混入
bundle 根）。第三段取值 == build_macos.py 的 bundle 组合前缀——同
一次 verify 调用里的第三份路径账。漂移无人判：bundle 根挪目录只改
--app-bundle/--dmg 而漏 forbid（W44 的两段同账不覆盖它），updater
资产的禁入检查指向旧根——核验通过但检查的范围错了。W44 管两段，第三
段第一次进射程。

W49 的提取逻辑与 W44 同款（判据文件彼此独立不互相 import，各自带
同款正则）；W49b 沿 W47 教训不做存在守卫——forbid 行缺失归 W49a
计数，W49b 只判存在的值。

## 3. 实现

### 3.1 生产代码

- 零改动（三段现同账，纯钉住）。

### 3.2 `tests/test_desktop_forbid_bundle_path.py`（W49a / W49b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W49a | yml `--forbid-updater-artifacts` 取值恰一处；脚本 bundle 组合行恰一处 | desktop-macos.yml + desktop/scripts/build_macos.py |
| W49b | forbid 取值 == 脚本拼出的 bundle 前缀（存在才判） | 同上 |

实现要点：

- 脚本 bundle 前缀提取与 W44 同款正则（四段 join）。
- W49b `for value in findall(...)` 循环判值——行缺失时循环体不执行
  （W49a 已红），不做存在断言。

## 4. 验证

- 定向：`tests/test_desktop_forbid_bundle_path.py` 2 passed（首跑即
  过）；关联面 `test_desktop_product_paths.py`（W44，两段账）、
  `test_desktop_verify_bundle_flags.py`（W38）、
  `test_desktop_backend_install_segment.py`（W48）全绿；S2/S3/S5 在
  本提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3245 passed / 28 skipped / 0 failed**（3273 条，
  约 12m22s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-macos.yml 与 build_macos.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 yml forbid 取值漂移（bundle → bundle2） | W49b 红（取值不等）、W49a 绿 |
| M2 脚本 bundle 段漂移（bundle → bundle-out） | W49b 红（取值不等）、W49a 绿 |
| M3 yml forbid 行删除 | W49a 红（1→0）、W49b 绿（无值可判） |
| M4 yml forbid 复制一份 | W49a 红（1→2）、W49b 绿 |

## 5. 边界与遗留

- 只判 forbid 取值与脚本 bundle 前缀的字面同账——不判
  --app-bundle/--dmg（W44 已管）、不判 forbid 的语义（哪些文件算
  updater 资产是 verify_bundle 自己的逻辑）、不判执行行为（CI 负责）。
- 四轮连推（二十五）续 **R222 核心安装包名两 workflow 同账（W50）**、
  **R223 产物名前缀多源同账（W51）**、**R224 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`9431f7f`** 推送后 run **42443606070**：**10 job 全
  `success`**（03:39:05→03:56:03 UTC，约 16m58s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42443606070`，bot 提交 **`b23a0e1`**）。R222 回填。

## 7. 提交

- 改动：`tests/test_desktop_forbid_bundle_path.py`（W49）、R221 文档、
  R220 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R221 一条）、
  `JUDGEMENT_LEDGER.md`（§10.93）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
