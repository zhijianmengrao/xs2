# DeterminFlow (xs2) 交接报告 — Round 205（gh release 上传面同账：W37）

> 单 profile。四轮连推（二十一）第 1 轮：把 `gh release` 上传面钉成
> 两半同账（upload×2 / create 分支资产实参逐字恰等 + --repo 逐处 +
> --clobber 全带）。生产代码零改动，本轮无修复——上传面现同账。
> 变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_gh_release_uploads.py` 新增 **W37a/W37b**：
  `gh release` 调用逐份恰等（desktop-windows.yml 3 / replace-
  desktop-assets.yml 2，合计 5）、子命令形状就位（view ×1 / upload
  ×2 / create ×1 / edit ×1）、upload 全带 `--clobber`（W37a）；
  upload×2 与 create 分支的资产实参逐字恰等（== `release-assets/*`）
  + 全部调用带 `--repo "$GITHUB_REPOSITORY"`（create 的在续行，按
  块窗口判）（W37b）。总用例 3213 → **3217**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R204 §6 进入回填扫描区间）。
- 变异 **4/4**：replace upload 资产目录改值 / edit 丢 `--repo`
  （W37b 各自独红）、windows upload 丢 `--clobber` / view 行删除
  （W37a 各自独红）。
- **回填**：R204 §6（run `42403264786` / bot `8957b19`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

发版资产进 GitHub release 的 `gh release` 调用共 5 处、两份 workflow：
desktop-windows 的 view→（upload ∣ create）分支结构 + replace-desktop-
assets 的 upload/edit。两条 upload 与 create 的资产集合都是
`release-assets/*`——同一条账的三处引用。漂移无人判：改资产目录只改
一处，另一条 upload 或 create 分支就指向空目录（upload 静默传空集合、
create 挂空 release）；丢 `--clobber`，重跑发布时 upload 撞已存在资产
直接失败；丢 `--repo "$GITHUB_REPOSITORY"`，调用落到 gh 默认仓库（fork
场景下不是发版仓库）。这条边此前无人判：W32 管脚本路径、W35 管清单
端点、W36 管 release-notes 引用，`gh release` 调用面第一次进射程。

W37 的分工沿用 W32/W34 定式：语料守卫管锚的存在与结构（计数、子
命令形状、--clobber），值由同账判（资产实参恰等、--repo 逐处）。

## 3. 实现

### 3.1 生产代码

- 零改动（上传面现同账：5 处调用、资产实参 `release-assets/*`、
  --repo 逐处，纯钉住）。

### 3.2 `tests/test_desktop_gh_release_uploads.py`（W37a / W37b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W37a | 调用逐份恰等（3/2，合计 5）；子命令形状恰等（view×1/upload×2/create×1/edit×1）；upload 全带 `--clobber` | desktop-windows.yml + replace-desktop-assets.yml |
| W37b | upload×2 + create×1 的资产实参逐字恰等（== `release-assets/*`）；全部调用带 `--repo "$GITHUB_REPOSITORY"`（create 折行，按 create 起始的 400 字符窗口判） | 同上 |

实现要点：

- `gh release` 调用按行提取（`gh release (\w+)([^\n]*)`）——create 的
  `--repo` 在续行，行级提取吃不到；W37b 对 create 用「调用起始 +
  400 字符」窗口判 `--repo` 存在，其余调用逐行判。
- 资产实参提取 `upload "$RELEASE_TAG" ([^\s]+)` / `create "$RELEASE_TAG"
  ([^\s]+)`，恰等账 = {upload×2, create×1} 的提取值集合 == 
  {`release-assets/*`}——一处改目录整个集合翻红。

## 4. 验证

- 定向：`tests/test_desktop_gh_release_uploads.py` 2 passed（首跑即
  过）；关联面 `test_desktop_release_notes_refs.py`（W36）、
  `test_desktop_updater_channel.py`（W35）、
  `test_desktop_workflow_script_refs.py`（W32）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3189 passed / 28 skipped / 0 failed**（3217 条，
  约 10m46s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 replace upload 资产目录 `release-assets/*` → `release-out/*` | W37b 红（资产实参不同账）、W37a 绿 |
| M2 windows upload 丢 `--clobber` | W37a 红（--clobber 守卫）、W37b 绿 |
| M3 replace edit 丢 `--repo` | W37b 红（--repo 逐处）、W37a 绿 |
| M4 windows view 行改 `if true`（调用 3→2） | W37a 红（子命令形状 view×1 破坏）、W37b 绿 |

## 5. 边界与遗留

- 只判 gh 调用的字面形状——不判 release 是否真的存在/资产是否真的
  传上（CI 负责）、不判 `--verify-tag`/`--title` 的语义、不判
  `--notes-file` 的语义（edit/create 的 notes-file 面由 W36 的引用面
  覆盖）、不判 `$RELEASE_TAG` 的取值。
- 四轮连推（二十一）续 **R206 verify_bundle 调用面参数同账（W38）**、
  **R207 create_update_manifest 调用面参数同账（W39）**、**R208
  收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_gh_release_uploads.py`（W37）、R205 文档、
  R204 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R205 一条）、
  `JUDGEMENT_LEDGER.md`（§10.77）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
