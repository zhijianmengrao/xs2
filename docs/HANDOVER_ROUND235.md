# DeterminFlow (xs2) 交接报告 — Round 235（publish_r2_release 调用面同账：W60）

> 单 profile。四轮连推（二十八）第 3 轮：把两处 `publish_r2_release.py`
> 调用面（desktop-windows 7 flags / replace 8 flags）与 argparse 9 个
> option 钉成「⊆ 且两处对称差恰 {--revision}」。生产代码零改动，本轮
> 无修复——调用面现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_publish_call_site.py` 新增 **W60a/W60b**：两
  workflow 各恰一处调用、argparse 定义非空（W60a）；每处 flags ⊆
  argparse option 集合、两处调用面对称差恰 == {--revision}（W60b）。
  总用例 3319 → **3323**（+2 钉测、+1 N3 本篇、+1 D1 因 R234 §6 进入
  回填扫描区间）。
- 变异 **4/4**：windows flag 错拼 / replace 丢 `--revision` / 脚本
  option 改名（W60b 各自独红）、windows 调用块复制（W60a 独红）——
  均为单红。
- **回填**：R234 §6（run `42637802235` / bot `35073ee`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`desktop/scripts/publish_r2_release.py` 的 argparse 定义 9 个 option
（--assets-dir / --version / --revision / --notes-file / --pub-date /
--bucket / --endpoint-url / --public-base-url / --aws-binary，
L196–204）；两处 call site——desktop-windows.yml（L225，7 flags，常规
发版不带 `--revision`）与 replace-desktop-assets.yml（L132，8 flags，
补发通道带 `--revision`）。调用面漂移无人判：workflow 写错 flag 字、
脚本增删 option 而 call site 没跟——run 时 `unrecognized arguments`；
两处调用面分叉（常规发版误带 `--revision` 覆盖不可变资产、补发通道
丢 `--revision` 同版本覆盖）也没人拦。

W30/W31 管 R2 凭据与回落域、W33/W43 管发行路径与门控，W60 把
**调用面**（flags ↔ argparse）推进射程。

W60 的锚选在「⊆ + 差集恰等」：单向恰等在 `--aws-binary`（有默认值、
两处都不用）上不成立，所以钉「无未定义 flag」+「两处差集恰
{--revision}」。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现同账，纯钉住）。

### 3.2 `tests/test_desktop_publish_call_site.py`（W60a / W60b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W60a | 两 workflow 各恰一处调用；argparse 定义非空 | 两 workflow + publish_r2_release.py |
| W60b | flags ⊆ argparse；两处对称差恰 == {--revision} | 同上 |

实现要点：

- 调用块提取 `desktop/scripts/publish_r2_release\.py((?:[^\\\n]|\\\r?\n)*)`
  ——续行 `\`+换行 全部吃进；replace 侧一行多 flag 也能收全。
- 先剥命令替换 `$(…)` 再取 `--[a-z][a-z0-9-]*`：desktop-windows 的
  `$(git show -s --format=%cI …)` 里的 `--format` 不误收。
- W60b 对现有调用遍历判 ⊆；两处数量不唯一时跳过差集断言（缺失/重复
  归 W60a）——W47/W49 定式。

## 4. 验证

- 定向：`tests/test_desktop_publish_call_site.py` 2 passed（首跑即
  过）；关联面 `test_desktop_r2_release_paths.py`（W33）、
  `test_desktop_r2_fallback_domain.py`（W31）全绿。
- 本机全量：**3295 passed / 28 skipped / 0 failed**（3323 条，
  约 8m47s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两 workflow 与脚本均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 windows 调用 `--bucket` 错拼为 `--buckets` | W60b 红（不在 argparse）、W60a 绿 |
| M2 replace 调用丢掉 `--revision` | W60b 红（差集为空 ≠ {--revision}）、W60a 绿 |
| M3 windows 调用块复制 | W60a 红（1→2）、W60b 绿（两处均 ⊆） |
| M4 脚本 option `--notes-file` 改名 `--notesfile` | W60b 红（两处 call site 越界）、W60a 绿 |

## 5. 边界与遗留

- 只判 flag 名的字面同账——不判取值（bucket/endpoint 由 W30/W31
  负责）、不判脚本执行行为（CI 负责）、不判 required/default
  （argparse 自身负责）。
- 四轮连推（二十八）续 **R236 收口**（R233–R236 四账 + R237–R240
  登记）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`762d247`** 推送后 run **42642327945**：**10 job 全
  `success`**（15:12:38→15:30:11 UTC，约 17m33s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42642327945`，bot 提交 **`c380892`**）。R236 回填。

## 7. 提交

- 改动：`tests/test_desktop_publish_call_site.py`（W60）、R235 文档、
  R234 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R235 一条）、
  `JUDGEMENT_LEDGER.md`（§10.107）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
