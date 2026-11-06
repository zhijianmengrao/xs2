# DeterminFlow (xs2) 交接报告 — Round 187（desktop README macOS 候选范围 ↔ workflow 矩阵：W24）

> 单 profile。四轮连推（十六）第 3 轮：候选制第二次在登记阶段抓到
> **真实文档不一致**并修复——`desktop/README.md` 的 macOS 表行仍写
> 「范围 | 只构建 Core，不构建 Full」，而 `desktop-macos.yml` 的 matrix
> 是 `[core, full]`。R187 先修文档（一行）再钉同账；变异 3/3。

## 1. 一句话结论

- **实测（修复前）**：macOS 小节三处叙述里只有表行是旧值——表行
  「只构建 Core，不构建 Full」；小节导语「当前提供 Apple Silicon
  （arm64）Core / Full 候选」；「桌面更新发布」节「分别生成 Apple
  Silicon Core 与 Full」。`desktop-macos.yml` 的 `flavor` 矩阵是
  `[core, full]`。
- **修复**：表行改为「Core 与 Full 两种候选都构建，与 workflow 矩阵
  一致」。生产代码零改动，`desktop/README.md` 一行。
- `tests/test_desktop_macos_scope.py` 新增 **W24a/W24b**：范围行 ↔
  矩阵（点名全部 flavor、词表守卫、否定式禁用、配置行路径存在）+
  macOS 小节叙述段 flavor 双覆盖。总用例 3151 → **3155**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R186 进入扫描区间）。
- 变异 **3/3**：矩阵删 `full`（W24a+W24b 红）、范围行回退旧值
  （W24a 红）、导语去掉 `Full`（W24b 红）。
- **回填**：R186 §6（run `42251651068` / bot `12e0565`）与索引 §1
  的写回 / 基线两行。

## 2. 为什么是这一轮

macOS 候选范围的「事实源」是 `desktop-macos.yml` 的 build 矩阵——它
决定 CI 真的构建哪些 flavor。README 的 macOS 小节是同一事实的人读
账。历史上 Full 候选后来才加进矩阵（`desktop/**` 触发、纯文档 PR 不
会跑它），表行没跟上：照表理解的人会以为 Full 候选不存在，与同文档
导语、「桌面更新发布」节的叙述互相矛盾。这条边此前无人判——W18 管
版本、V8 管命令引用、W20/W22 管版本与 identifier，范围叙述没有锚。

W24 的锚选在「矩阵 ↔ 范围行」：矩阵是唯一事实源，范围行必须点名
矩阵里的每一个 flavor、不得出现矩阵外的值；「只构建 / 不构建」这类
否定式就是本次分叉的形状，直接禁用（矩阵加 flavor 时范围行必须显式
改写，而不是加一个「不构建 X」）。配置行的 `tauri.macos.conf.json`
路径顺手钉存在性。

## 3. 实现

### 3.1 生产文档修复

- `desktop/README.md` macOS 小节表行：
  `| 范围 | 只构建 Core，不构建 Full |` →
  `| 范围 | Core 与 Full 两种候选都构建，与 workflow 矩阵一致 |`。
- 其余叙述（导语「Core / Full 候选」、「桌面更新发布」节）本来就与
  矩阵同账，不改。

### 3.2 `tests/test_desktop_macos_scope.py`（W24a / W24b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W24a | 矩阵非空、值在 `{core, full}` 词表内；范围行点名矩阵全部 flavor、无矩阵外值、无「只构建 / 不构建」；配置行路径在磁盘 | workflow YAML + README 表行 |
| W24b | macOS 小节叙述段提 flavor 必须双覆盖（提一个必须提两个；完全不提也是一致态） | README 小节 prose |

实现要点：

- 小节定位按 `## macOS` 标题到下一个 `## `，行级锚定 `| 范围 |` /
  `| 配置 |`，两行各恰一处——表形状变了显式红。
- flavor 词匹配大小写不敏感（README 写 `Core` / `Full`，矩阵写
  `core` / `full`）；词表守卫让未来加第三个 flavor 时先红在词表，
  强制同步更新 README 范围行与本判据。
- 否定式禁用只作用于范围行（架构行的「不构建 universal 或 Intel」是
  架构排除，不是 flavor 范围，不进射程）。

## 4. 验证

- 定向：`tests/test_desktop_macos_scope.py` 2 passed。
- **反向验证**：把范围行临时改回旧值，W24a 红在否定式守卫（
  `实测 ['只构建', '不构建']`）——修复前状态确实会被判红。
- 关联面：`test_ci_workflow_inventory.py`、`test_desktop_packaging.py`、
  `test_desktop_pipeline_commands.py`、`test_macos_minimum_version.py`
  全绿。
- 本机全量：**3127 passed / 28 skipped / 0 failed**（3155 条，约 10m18s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 矩阵 `[core, full]`→`[core]` | W24a 红、W24b 红 |
| M2 范围行回退「只构建 Core，不构建 Full」 | W24a 红、W24b 绿 |
| M3 导语去掉 `Full` | W24b 红、W24a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（README /
desktop-macos.yml 均为 CRLF）。

## 5. 边界与遗留

- 只判 macOS 小节的范围 / 配置两行与叙述段双覆盖：不判 Windows 小节、
  不判矩阵执行行为（CI 负责）、不判「桌面更新发布」节的历史叙述
  （其 macOS 段与矩阵同账，但该节职责是发版收尾）。
- R187 是候选制第二次「登记阶段抓到真实不一致」（第一次是 R177 的
  P10：checker Node 下限 18+）；这次是纯文档修复，无生产代码改动。
- 四轮连推（十六）下一轮 **R188 收口轮（R185–R188 四账）**：四账审计
  + 登记下一批（R189–R192）。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`8c124bf`** 推送后 run **42256984163**：**10 job 全
  `success`**（16:56:19→17:13:43 UTC，约 17m24s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42256984163`，bot 提交 **`5ab418a`**）。R188 回填。同推送因
  `desktop/**` 变更还触发了 Desktop Windows 工作流（构建 NSIS 候选，
  约 13 分钟，同样全绿；该工作流没有写回账，§6 不引用其 run id——
  D2 只认有 bot 快照的 run）。

## 7. 提交

- 改动：`tests/test_desktop_macos_scope.py`（W24）、`desktop/README.md`
  范围行修复（一行）、R187 文档、R186 §6 回填、`HANDOVER_INDEX.md`
  （§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 + §6.1）、
  `PROJECT_INFO.md`（H2 + R187 一条）、`JUDGEMENT_LEDGER.md`
  （§10.59）。
- `config/skills_config.json` 不纳入（C1）。
