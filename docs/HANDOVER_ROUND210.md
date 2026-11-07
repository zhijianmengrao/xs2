# DeterminFlow (xs2) 交接报告 — Round 210（smoke_backend 调用面同账：W41）

> 单 profile。四轮连推（二十二）第 2 轮：把 `smoke_backend.py` 的
> 4 处调用钉成「计数恰等 3/1 + 超时预算逐字同账」。生产代码零改动，
> 本轮无修复——调用面现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_smoke_backend_timeouts.py` 新增 **W41a/W41b**：
  smoke_backend 调用逐份恰等（desktop-macos.yml 3 / desktop-windows.yml
  1，合计 4）（W41a）；每处调用恰有一个 `--timeout <N>` 且全部逐字
  同值（== 180）（W41b）。总用例 3231 → **3235**（+2 钉测、+1 N3
  本篇、+1 D1 因 R209 §6 进入回填扫描区间）。
- 变异 **4/4**：windows 超时改 120 / macos 一处丢 `--timeout`（W41b
  各自独红）、macos 一处调用删除 / 复制（W41a 各自独红）。
- **回填**：R209 §6（run `42415277699` / bot `8ac136a`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`smoke_backend.py`（backend 冒烟）被 desktop workflow 调用 4 处：
macos 3 处（构建后 / DMG 前核验 / 挂载副本核验）、windows 1 处，均带
`--timeout 180`。超时预算漂移无人判：一处改超时而其余没跟，四个冒烟
点的等待预算分叉——CI 各自能绿，但「冒烟到底等多久」在平台间/阶段间
语义不一致，慢机器上只有部分点会偶发超时（最难归因的那类 flake）。
W40 管的是对称调用的两个脚本，smoke_backend 的 4 处（3+1 非对称）
第一次进射程。

W41 的分工沿用定式：W41a 管计数（3/1），W41b 管每处恰一个
`--timeout` 且值全等——各处定位参数（app-bundle/挂载副本路径）是
各点的本意差异，不进同账。

## 3. 实现

### 3.1 生产代码

- 零改动（调用面现同账：4 处均 `--timeout 180`，纯钉住）。

### 3.2 `tests/test_desktop_smoke_backend_timeouts.py`（W41a / W41b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W41a | smoke_backend 调用逐份恰等（macos 3 / windows 1，合计 4） | desktop-macos.yml + desktop-windows.yml |
| W41b | 每处调用恰有一个 `--timeout <N>` 且全部 == 180 | 同上 |

实现要点：

- 折行提取沿用展开循环正则（W38 定式）；macos 的 L66/L77 是折行
  调用，L52 与 windows L88 是单行。
- 计数钉在 W41a，W41b 只对「逐处恰一个 --timeout + 值全等」负责
  ——首版把 `len(timeouts) == 4` 放进 W41b，删/复制调用变异双红，
  与 W32 首版同病，改后重跑变异确认各自独红。

## 4. 验证

- 定向：`tests/test_desktop_smoke_backend_timeouts.py` 2 passed（首跑
  修正计数耦合后即过）；关联面
  `test_desktop_symmetric_script_calls.py`（W40）、
  `test_desktop_verify_bundle_flags.py`（W38）、
  `test_desktop_gh_release_uploads.py`（W37）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3207 passed / 28 skipped / 0 failed**（3235 条，
  约 10m53s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 windows `--timeout 180` → `120` | W41b 红（值不同账）、W41a 绿 |
| M2 macos L52 丢 `--timeout 180` | W41b 红（该处恰一个 --timeout 破坏）、W41a 绿 |
| M3 macos L52 调用删除 | W41a 红（3→2）、W41b 绿（剩余处各恰一个 180） |
| M4 macos L52 调用复制一份 | W41a 红（3→4）、W41b 绿 |

## 5. 边界与遗留

- 只判调用计数与 `--timeout` 值的字面同账——不判各处定位参数
  （app-bundle/挂载副本路径是各点的本意差异）、不判 smoke 的执行
  行为（CI 负责）、不判 `--timeout` 取值合理性（180 是政策值，改动
  先红同账再改）。
- 四轮连推（二十二）续 **R211 smoke_installer.ps1 调用面参数同账
  （W42）**、**R212 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_smoke_backend_timeouts.py`（W41）、R210
  文档、R209 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R210 一条）、
  `JUDGEMENT_LEDGER.md`（§10.82）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
