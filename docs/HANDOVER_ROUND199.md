# DeterminFlow (xs2) 交接报告 — Round 199（README R2 发行路径两段同账：W33）

> 单 profile。四轮连推（十九）第 3 轮：把 README「桌面更新发布」节的
> 两段发行路径（`desktop/releases/vX/` 前缀 + `desktop/stable/latest.json`
> 稳定键）与 `publish_r2_release.py` 的实现侧钉成两段逐字同账。生产
> 代码零改动，本轮无修复——两段现同账，判据钉住本来就对的账。
> 变异 5/5。

## 1. 一句话结论

- `tests/test_desktop_r2_release_paths.py` 新增 **W33a/W33b**：README
  的 `` `…/vX/` `` 发行前缀 token 与「最后更新 `<stable>`」句各恰一处、
  脚本 `version_prefix` 定义与 `publish_latest` 稳定键实参各恰一处
  （W33a，`vX`/`v{version}` 形状钉在提取正则里）；发行目录前缀
  （README token 去 `/vX/` == 脚本 f-string 去 `/v{version}`）与稳定
  清单键逐字恰等（W33b）。总用例 3193 → **3197**（+2 钉测、+1 N3
  本篇、+1 D1 因 R198 §6 进入回填扫描区间）。
- 变异 **5/5**：脚本改发行目录 / 改稳定键、README 改发行目录（W33b
  各自独红）、README 复制发行 token（W33a 独红：值不变）、README
  `vX` 形状漂移（W33a 锚丢失 + W33b 无锚可比，双红——形状既是语料
  也是账面）。
- **回填**：R198 §6（run `42387980656` / bot `3b8efb8`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

README 的「桌面更新发布」节是一份操作说明书：先校验
`desktop/releases/vX/` 下的不可变资产，最后更新
`desktop/stable/latest.json`。脚本的
`version_prefix = f"desktop/releases/v{version}"` 与
`publish_latest(manifest_path, "desktop/stable/latest.json")` 是同一
份账的实现侧——README 的 `vX` 对脚本的 `v{version}`。两段任何一段
单侧漂移（发版脚本改目录布局、稳定键改名），发布物落在新位置而
README 指着旧位置：按文档核对发版的人校验不到新键，稳定通道的
消费者拿不到更新。这条边此前无人判：W30/W31 各管凭据与回落域名，
发行路径的面第一次进射程。

W33 的锚选在「两段分离」：目录前缀与稳定键是两个独立的漂移方向
（改目录布局 ≠ 改键名），提取、守卫、同账都按段分开做——一段漂移
只红自己那段的消息。

## 3. 实现

### 3.1 生产代码

- 零改动（两段现同账：`desktop/releases/` + `desktop/stable/latest.json`，
  纯钉住）。

### 3.2 `tests/test_desktop_r2_release_paths.py`（W33a / W33b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W33a | README `` `([^`]+?)/vX/` `` token 恰一处、`最后更新 `([^`]+)`` 恰一处；脚本 `version_prefix = f"…"` 定义恰一处、`publish_latest(…, "…")` 实参恰一处（vX/v{version} 形状钉在提取正则里） | desktop/README.md + desktop/scripts/publish_r2_release.py |
| W33b | 发行目录前缀逐字恰等（README 去 `/vX/` == 脚本去 `/v{version}`，脚本侧形状漂移显式红）；稳定清单键逐字恰等 | 同上 |

实现要点：

- README 稳定键锚「最后更新 `` `token` ``」带反引号：L118 的「最后
  更新稳定 Manifest」不带 token，不误收。
- 脚本侧只钉 `version_prefix` 的**定义行**（`publish_immutable` 的
  `{version_prefix}/latest.json` 由同一前缀推出，前缀同账即覆盖）。
- 同账比较的是目录前缀而不是整段 token：`vX`（文档）与 `v{version}`
  （代码）形状本来就不同，形状各自钉在提取正则里，比较只对目录。

## 4. 验证

- 定向：`tests/test_desktop_r2_release_paths.py` 2 passed（首跑即
  过）；关联面 `test_desktop_r2_fallback_domain.py`（W31）、
  `test_desktop_workflow_script_refs.py`（W32）、
  `test_desktop_r2_credentials.py`（W30）、`test_readme_commands.py`
  （V6）全绿；S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正
  之前），本提交翻正后全绿。
- 本机全量：**3169 passed / 28 skipped / 0 failed**（3197 条，
  约 10m37s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **5/5**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop/README 与 publish_r2_release.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 脚本 `desktop/releases/v{version}` 目录改值 | W33b 红（README 未跟）、W33a 绿 |
| M2 脚本稳定键改值 | W33b 红（README 未跟）、W33a 绿 |
| M3 README `vX` → `v2X`（形状漂移） | W33a 红（锚丢失）+ W33b 红（无锚可比，双红） |
| M4 README 发行目录改值 | W33b 红（脚本未跟）、W33a 绿 |
| M5 README 发行 token 复制一份 | W33a 红（恰一处破坏）、W33b 绿（值不变） |

## 5. 边界与遗留

- 只判两段路径的字面同账——不判发布行为与不可变校验（CI 与脚本自身
  的判据面负责）、不判 `latest.json` 内容结构、不判
  `publish_immutable` 的逐资产键（`{version_prefix}/latest.json` 由
  同一前缀推出，前缀同账即覆盖）。
- 四轮连推（十九）收官 **R200 收口轮（R197–R200 四账）+ 登记
  R201–R204**（候选面已见 replace-desktop-assets.yml 期望资产词表 ↔
  desktop-windows NSIS 后缀对 / build_macos DMG 后缀对的三源产物
  名词表，登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_r2_release_paths.py`（W33）、R199 文档、
  R198 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R199 一条）、
  `JUDGEMENT_LEDGER.md`（§10.71）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
