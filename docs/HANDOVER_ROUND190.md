# DeterminFlow (xs2) 交接报告 — Round 190（desktop README Windows 表 ↔ desktop-windows.yml：W26）

> 单 profile。四轮连推（十七）第 2 轮：把 Windows 表「构建」行的
> runner 钉到 workflow 首个 job 的 `runs-on` 上；生产代码零改动。
> 变异 3/3。

## 1. 一句话结论

- **实测**：Windows 表「构建」行写 GitHub Actions `windows-2025`，
  `.github/workflows/desktop-windows.yml` 第一个 job `build` 的
  `runs-on` 也是 `windows-2025`；「配置」行
  `desktop/src-tauri/tauri.conf.json` 与「工作流」行
  `.github/workflows/desktop-windows.yml` 都在磁盘。workflow 实际有
  三个 job——`build`（windows-2025，flavor 矩阵 core/full）、
  `build-macos`（callable workflow，无自己的 `runs-on`）、`release`
  （`ubuntu-latest`，仅 `v*` tag）——锚只钉第一个 job。
- `tests/test_desktop_windows_runner.py` 新增 **W26a/W26b**：三行表
  语料守卫 + runner `windows-YYYY` 形状守卫 + 两路径存在（W26a）、
  README runner == workflow 首个 job `runs-on`（W26b）。总用例
  3161 → **3165**（+2 钉测、+1 N3 本篇、+1 D1 因 R189 §6 进入回填
  扫描区间）。
- 变异 **3/3**：README 构建行 runner 改 `windows-2022`（W26b 红）、
  workflow `runs-on` 改 `windows-2022`（W26b 红）、配置行路径改
  `tauri.probe.json`（W26a 红）。
- **回填**：R189 §6（run `42345750962` / bot `501346f`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

Windows 表「构建」行是 runner 的人读账——它告诉照表理解的人构建跑在
哪个镜像上。runner 换代（`windows-2025` → `windows-latest` 之类）时，
只改 workflow 不改表行，表行静默失真；反向只改表行不改 workflow，文档
描述与 CI 实际运行分叉。runner 还有一个形状陷阱：`windows-latest`
这类浮动标签会随微软下线旧镜像悄悄漂移，所以 W26a 的形状守卫只认
`windows-YYYY` 显式年份——换代必须写显式值，浮动的「最新」不可对账。
这条边此前无人判：W24 管的是 macOS 表的范围行与矩阵，Windows 表的
构建/配置/工作流三行没有锚。

W26 的锚选在「首个 job 的 `runs-on`」而不是「全文件任意 `runs-on`」：
`desktop-windows.yml` 的 `release` job 用 `ubuntu-latest`（仅 tag 触发
的发版收尾），把它卷进射程会把一条真实存在的差异误报成分叉。首个 job
的定位走 YAML 解析（job 映射顺序），名字不写死——job 改名或换位时
结构守卫显式红。

## 3. 实现

### 3.1 生产代码

- 零改动（runner 本来就同账，纯钉住）。

### 3.2 `tests/test_desktop_windows_runner.py`（W26a / W26b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W26a | Windows 表构建/配置/工作流三行各恰一处；构建行 runner 恰一处 `windows-YYYY` 形状；配置行与工作流行路径在磁盘；workflow 首个 job 有 `runs-on` 字符串值 | README Windows 表 + desktop-windows.yml |
| W26b | README 构建行 runner == workflow 首个 job `runs-on`（逐字） | 同上 |

实现要点：

- 小节定位按 `## Windows` 标题到下一个 `## `，行级锚定 `| 构建 |` /
  `| 配置 |` / `| 工作流 |`，各行恰一处——表形状变了显式红。
- workflow 侧用 `yaml.safe_load` 解析（同 S6 对 ci.yml 的做法），
  `next(iter(jobs))` 取第一个 job——映射顺序即 YAML 顺序。
- 形状守卫在 W26a：`windows-latest` 这类无年份标签解析不到
  `windows-YYYY` token 直接红，强制显式年份进账。

## 4. 验证

- 定向：`tests/test_desktop_windows_runner.py` 2 passed。
- 关联面：`test_desktop_ui_paths.py`（W25）、`test_ci_workflow_inventory.py`、
  `test_desktop_macos_scope.py`（W24）、`test_index_snapshot.py` 全绿；
  S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正之前），本提交
  翻正后全绿。
- 本机全量：**3137 passed / 28 skipped / 0 failed**（3165 条，
  约 10m30s）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  README / desktop-windows.yml 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 README 构建行 `windows-2025`→`windows-2022` | W26b 红（不同账）、W26a 绿 |
| M2 workflow `runs-on: windows-2025`→`windows-2022` | W26b 红（不同账）、W26a 绿 |
| M3 配置行路径 →`tauri.probe.json` | W26a 红（路径不存在）、W26b 绿 |

## 5. 边界与遗留

- 只判 Windows 表三行与 workflow 首个 job 的 runner：不判「安装包」
  「更新」两行（W27 射程）、不判 `build-macos` 与 `release` 两个 job
  的 runner、不判矩阵展开行为、不判工作流触发条件与 step 行为。
- 四轮连推（十七）下一轮 **R191 desktop README 表 ↔ tauri conf 键
  同账（W27）**。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_windows_runner.py`（W26）、R190 文档、
  R189 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/批次行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R190 一条）、
  `JUDGEMENT_LEDGER.md`（§10.62）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
