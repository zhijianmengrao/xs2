# DeterminFlow (xs2) 交接报告 — Round 203（release-notes 引用面：W36）

> 单 profile。四轮连推（二十）第 3 轮：把 `desktop/release-notes/` 的
> 引用面钉成「生产端 workflow 引用逐份计数恰等 + 占位符形状同账 +
> 消费端 docs 链接可解析」。生产代码零改动，本轮无修复——引用面
> 现自洽。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_release_notes_refs.py` 新增 **W36a/W36b**：三份
  发版 workflow 的 release-notes 引用逐份恰等（desktop-windows.yml 3 /
  replace-desktop-assets.yml 3，合计 6）且占位符形状 ∈
  {`$RELEASE_TAG`, `{tag}`}（目录前缀 + `.md` 后缀钉在提取正则里）、
  community-updates 的链接恰 2 处（W36a）；community-updates 每条链接
  按 docs/ 为基解析后在磁盘（W36b）。总用例 3207 → **3211**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R202 §6 进入回填扫描区间）。
- 变异 **4/4**：community 链接指向不存在的日志（W36b 独红）、
  workflow 后缀改 `.MD` / 占位符改 `{tagx}` / 链接复制一份（W36a
  各自独红）。
- **回填**：R202 §6（run `42398290269` / bot `f587a2f`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`desktop/release-notes/<tag>.md` 是发版叙事的承载文件，引用面有两
半：生产端三份发版 workflow 恰 6 处引用（desktop-windows 3：smoke 后
上传 / create_update_manifest / publish_r2_release；replace-desktop-assets
3：python 读内容 / `gh release edit` / publish_r2_release），tag 占位
符两写法（bash 的 `$RELEASE_TAG.md`、python f-string 的 `{tag}.md`）；
消费端 `docs/community-updates.md` 恰 2 处 docs 链接指向具体版本的
实盘文件（v1.1.1 / v1.1.0）。生产端一处改目录/换后缀/换占位符写法，
发版自动化在 run 时才炸；消费端链接指向被改名/删除的日志，读者点开
404。这条边此前无人判：V8/V6/V7 管的是 README 与文档 npm 命令的
命令面，release-notes 的路径引用面第一次进射程。

W36 的锚选在「生产端形状同账 + 消费端可解析」分工：workflow 引用的
tag 是运行时值（无从解析，只判形状与计数），community-updates 引用
的是具体版本（逐条按 docs/ 为基解析）——各判各能判的。

## 3. 实现

### 3.1 生产代码

- 零改动（引用面现自洽：6 处 workflow 引用同形状、2 处 docs 链接
  全部可解析，纯钉住）。

### 3.2 `tests/test_desktop_release_notes_refs.py`（W36a / W36b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W36a | workflow 引用逐份恰等（3/3，合计 6），占位符形状 ∈ {`$RELEASE_TAG`, `{tag}`}；community-updates 链接恰 2 处 | desktop-windows.yml + replace-desktop-assets.yml + docs/community-updates.md |
| W36b | community-updates 每条链接按 docs/ 为基解析后在磁盘 | 同上 |

实现要点：

- 提取正则 `` desktop/release-notes/([^"'\s)]+)\.md ``：同时吃到
  bash 引号内、python f-string 内两种写法，目录前缀与 `.md` 后缀
  钉死（`.MD` / 换目录直接掉出提取 → 计数红）。
- 占位符形状账是白名单不是黑名单：新写法（如 `{tagx}`）先进红再进
  账，防止第三次写法悄悄分叉。
- docs 链接按 markdown `](…)` 形状提取，`docs/<ref>` resolve 后
  `is_file()`。

## 4. 验证

- 定向：`tests/test_desktop_release_notes_refs.py` 2 passed（首跑即
  过）；关联面 `test_docs_navigation.py`（N 系）、
  `test_desktop_updater_channel.py`（W35）、
  `test_desktop_product_suffixes.py`（W34）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3183 passed / 28 skipped / 0 failed**（3211 条，
  约 10m39s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  community-updates.md 与两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 community 链接 v1.1.1 → v9.9.9（指向不存在的日志） | W36b 红（解析不到）、W36a 绿 |
| M2 desktop-windows 一处 `.md` → `.MD` | W36a 红（引用掉出提取，3→2）、W36b 绿 |
| M3 replace-desktop-assets `{tag}` → `{tagx}` | W36a 红（占位符形状同账）、W36b 绿 |
| M4 community 链接复制一份 | W36a 红（恰 2 处破坏）、W36b 绿 |

## 5. 边界与遗留

- 只判引用路径的字面与可解析——不判日志内容、不判 workflow 的执行
  行为（CI 负责）、不判 README（实测 0 处 release-notes 引用）、不判
  历史日志是否该存在（消费端引用到的必须在盘，没被引用的旧日志不判）。
- 四轮连推（二十）收官 **R204 收口轮（R201–R204 四账）+ 登记
  R205–R208**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`8c21e24`** 推送后 run **42400637729**：**10 job 全
  `success`**（18:18:39→18:35:49 UTC，约 17m10s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42400637729`，bot 提交 **`3ad5451`**）。R204 回填。

## 7. 提交

- 改动：`tests/test_desktop_release_notes_refs.py`（W36）、R203 文档、
  R202 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R203 一条）、
  `JUDGEMENT_LEDGER.md`（§10.75）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
