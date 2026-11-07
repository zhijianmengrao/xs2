# DeterminFlow (xs2) 交接报告 — Round 202（更新通道清单端到端同账：W35）

> 单 profile。四轮连推（二十）第 2 轮：把桌面更新通道的清单钉成
> 端到端同账（tauri updater 端点 ↔ create_update_manifest 的
> --base-url/--output，端点 owner/repo 对 git origin）。生产代码
> 零改动，本轮无修复——两段现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_updater_channel.py` 新增 **W35a/W35b**：tauri
  端点数组恰一条（形状 `github.com/<owner>/<repo>/releases/latest/
  download/<file>.json`）、desktop-windows 的 `--base-url`
  （`github.repository` + `/releases/download/`）与 `--output
  release-assets/<file>` 各恰一处（W35a）；端点文件名 == `--output`
  文件名（清单改名两端必须同改）+ 端点 owner/repo == git origin 的
  owner/repo（仓库身份同账）（W35b）。总用例 3203 → **3207**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R201 §6 进入回填扫描区间）。
- 变异 **4/4**：端点文件名改值 / 端点 owner/repo 改值 / workflow
  `--output` 改值（W35b 各自独红）、端点条目复制一份（W35a 独红）。
- **回填**：R201 §6（run `42395500680` / bot `cb18ec1`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

桌面更新通道的清单有两份账：消费端 `tauri.conf.json` 的
`plugins.updater.endpoints` 恰一处
`https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json`
（updater 启动时拉它判断有无新版本）；生产端 desktop-windows.yml 的
create_update_manifest 用 `--base-url "https://github.com/${{
github.repository }}/releases/download/$RELEASE_TAG"` 生成 `--output
release-assets/latest.json` 再 `gh release upload`。两段任何一段单侧
漂移：清单改名而端点没跟 → updater 拉 404；仓库改名而端点的**硬编码**
owner/repo 没跟（workflow 侧 `${{ github.repository }}` 永远跟走）→
同样 404。updater 的失败只发生在用户机器上——CI 全绿、更新通道已断。
这条边此前无人判：W33 管的是 R2 侧的 `desktop/stable/latest.json`，
GitHub releases 侧的 `latest.json` 第一次进射程。

W35b 的 owner/repo 账选 git `origin` 做第二源：workflow 用
`${{ github.repository }}`（运行时永远正确），端点是字面值——fork/
改名/搬移后 origin 变而端点不变，恰等判据当场红，把「静默 404」变
成「push 阶段显式红」。

## 3. 实现

### 3.1 生产代码

- 零改动（端点/清单现同账：`latest.json` + `zhijianmengrao/xs2`，
  纯钉住）。

### 3.2 `tests/test_desktop_updater_channel.py`（W35a / W35b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W35a | tauri `plugins.updater.endpoints` 数组恰一条 github.com/…/latest/download/<file>.json 形状；`--base-url`（github.repository 表达式 + releases/download）与 `--output release-assets/<file>` 各恰一处 | desktop/src-tauri/tauri.conf.json + desktop-windows.yml |
| W35b | 端点文件名 == `--output` 文件名；端点 owner/repo == git origin owner/repo | 同上 + git remote |

实现要点：

- 端点提取先锁 `endpoints` 数组块（`"endpoints"\s*:\s*\[([^\]]*)\]`）
  再在块内取 URL——数组外的同名键不误收。
- `--base-url` 的形状正则钉 `${{ github.repository }}` 表达式：生产
  端若改硬编码 owner/repo（与端点同病）也要红——发布地址该跟仓库走。
- git 不可用显式红不 skip（R136 纪律）；origin URL 兼容
  `https://github.com/<o>/<r>.git` 与 ssh 形状。

## 4. 验证

- 定向：`tests/test_desktop_updater_channel.py` 2 passed（首跑即
  过）；关联面 `test_desktop_r2_release_paths.py`（W33）、
  `test_desktop_product_suffixes.py`（W34）、
  `test_desktop_workflow_script_refs.py`（W32）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3179 passed / 28 skipped / 0 failed**（3207 条，
  约 10m39s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  tauri.conf.json 与 desktop-windows.yml 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 端点文件名 `latest.json` → `manifest.json` | W35b 红（文件名不同账）、W35a 绿 |
| M2 端点 owner/repo → `zhijianmengrao/xs2-old` | W35b 红（与 origin 不同账）、W35a 绿 |
| M3 workflow `--output` → `release-assets/manifest.json` | W35b 红（文件名不同账）、W35a 绿 |
| M4 端点条目复制一份 | W35a 红（恰一条破坏）、W35b 绿 |

## 5. 边界与遗留

- 只判端点/清单的字面同账——不判 updater 的运行行为与签名校验
  （tauri 运行时负责）、不判 `latest.json` 内容结构
  （create_update_manifest 的输出形状有自己的判据面）、不判
  `gh release upload` 的执行（CI 负责）。
- 四轮连推（二十）续 **R203 release-notes 引用面（W36）**、
  **R204 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_updater_channel.py`（W35）、R202 文档、
  R201 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R202 一条）、
  `JUDGEMENT_LEDGER.md`（§10.74）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
