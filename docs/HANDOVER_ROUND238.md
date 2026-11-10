# DeterminFlow (xs2) 交接报告 — Round 238（replace workflow 资产目录名四源同账：W62）

> 单 profile。四轮连推（二十九）第 2 轮：把 replace-desktop-assets.yml
> 里「发版资产暂存目录」字面 release-assets 的四个来源（shell 建目录 /
> gh 下载 --dir / 清单脚本 Path() / publish_r2_release --assets-dir）
> 钉成逐字恰等。生产代码零改动，本轮无修复——四源现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_replace_assets_dir.py` 新增 **W62a/W62b**：四种
  来源形状各恰 1 处（W62a）；四源提取值的并集 == {release-assets}
  （W62b）。总用例 3329 → **3333**（+2 钉测、+1 N3 本篇、+1 D1 因
  R237 §6 进入回填扫描区间）。
- 变异 **4/4**：mkdir -p / `--dir` / `Path()` / `--assets-dir` 四源
  各改一处（W62b 各自独红，W62a 全绿）。
- **回填**：R237 §6（run `42730782762` / bot `ebdfcf8`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 里「发版资产的暂存目录」字面
`release-assets` 出现在四处、四个不同来源：

- `mkdir -p release-assets`（L36，shell 建目录）；
- `'--dir', 'release-assets'`（L58，gh run download 的下载目录）；
- `Path('release-assets')`（L71，清单脚本读取资产目录）；
- `--assets-dir release-assets`（L133，publish_r2_release 的实参）。

W37 只钉 gh release upload 的 `release-assets/*` 实参，不钉这四源。
四处漂移无人判：下载目录与清单读取目录分叉 → 发版资产校验/清单生成
失败（第二步读不到下载的安装包）；或 R2 发布拿到空目录 → 上传半套
产物。

W58/W59/W60/W61 已把 replace workflow 的 outputs/inputs/import 调用
面/env 消费钉齐，W62 把同一形态推到 **目录名四源同账**。

W62 的锚选在「四源逐字恰等」：任何一处漂移都让并集离开
{release-assets}——四源各配一个独立变异，全部单红。

## 3. 实现

### 3.1 生产代码

- 零改动（四源现同账，纯钉住）。

### 3.2 `tests/test_desktop_replace_assets_dir.py`（W62a / W62b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W62a | mkdir -p / `'--dir'` / `Path('…')` / `--assets-dir` 四种形状各恰 1 处 | replace-desktop-assets.yml |
| W62b | 四源提取值的并集 == {release-assets} | 同上 |

实现要点：

- 四个正则各管一个来源：`mkdir -p (\S+)` /
  `'--dir', '([^']+)'` / `Path\('([a-z-]+)'\)`（`build-runs.json`
  等带点路径天然不匹配）/ `--assets-dir (\S+)`——四源互不重叠、
  各恰 1 处。
- W62b 用并集恰等而非逐源判同：任一源漂移都红，四源全绿才过。

## 4. 验证

- 定向：`tests/test_desktop_replace_assets_dir.py` 2 passed
  （首跑即过）；关联面 `test_desktop_gh_release_uploads.py`（W37）
  全绿。
- 本机全量：**3304 passed / 28 skipped / 0 failed**（3333 条，
  约 11m39s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  replace-desktop-assets.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 `mkdir -p release-assets` → `staging-assets` | W62b 红、W62a 绿 |
| M2 `'--dir', 'release-assets'` → `'dl-assets'` | W62b 红、W62a 绿 |
| M3 `Path('release-assets')` → `Path('assets-stage')` | W62b 红、W62a 绿 |
| M4 `--assets-dir release-assets` → `--assets-dir staging` | W62b 红、W62a 绿 |

## 5. 边界与遗留

- 只判目录名的字面同账——不判目录内文件（expected 集合由 release
  步脚本自校验）、不判 gh/publish_r2_release 行为（CI 负责）、不判
  build-runs.json 等其余路径字面。
- 四轮连推（二十九）续 **R239 replace 下载清单 ↔ 两 producer
  artifact 名同账（W63）**、**R240 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_replace_assets_dir.py`（W62）、R238 文档、
  R237 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/批次行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R238 一条）、
  `JUDGEMENT_LEDGER.md`（§10.110）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
