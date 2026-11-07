# DeterminFlow (xs2) 交接报告 — Round 191（desktop README 表 ↔ tauri conf 打包三键：W27）

> 单 profile。四轮连推（十七）第 3 轮：把三行打包声明表钉到 tauri
> 配置的三个键上；生产代码零改动。变异 3/3。

## 1. 一句话结论

- **实测**：macOS 表「产物 | `.app` + `.dmg`」↔
  `tauri.macos.conf.json` 的 `bundle.targets == ["app", "dmg"]`；macOS
  表「更新包 | `createUpdaterArtifacts=false`」↔ 同键 `false`；Windows
  表「安装包 | NSIS `currentUser`」↔ `tauri.conf.json` 的
  `bundle.windows.nsis.installMode == "currentUser"`。三键与三行表逐项
  同账。
- `tests/test_desktop_readme_packaging.py` 新增 **W27a/W27b**：三行表
  语料守卫 + token 形状 + conf 三键类型守卫（W27a）、产物扩展名集合
  == `targets` 集合（双向）、updater 布尔与安装模式逐字同账（W27b）。
  总用例 3165 → **3169**（+2 钉测、+1 N3 本篇、+1 D1 因 R190 §6 进入
  回填扫描区间）。
- 变异 **3/3**：`targets` 加 `deb`（W27b 红）、更新包行删
  `createUpdaterArtifacts=false` token（W27a+W27b 双红）、`installMode`
  改 `perMachine`（W27b 红）。
- **回填**：R190 §6（run `42347861422` / bot `532e389`）与索引 §1 的写回 /
  基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

三行表是打包形态的人读账：macOS 表声明「产物是 `.app` + `.dmg`」「不
生成 updater 产物」，Windows 表声明「安装包不申请管理员权限
（`currentUser`）」。三行各自对应一个 tauri 配置键——`targets` 决定
打哪些产物、`createUpdaterArtifacts` 决定有没有 `.sig`/updater tar.gz、
`installMode` 决定装到哪个范围。改 conf 单边（加减打包目标、翻转
updater 开关、换安装模式）时 README 静默失真：照表验收的人会拿不到
声明的产物、照表发布的人会漏掉 `.sig` 或多出更新产物、照表支持的人
会答错权限问题。这条边此前无人判——W22 管定位符、W23 管 DMG 产物名、
W24 管候选范围、W25 管 ui 路径链、W26 管 runner，打包三键没有锚。

W27 的锚选在「集合双向同账」：产物行的扩展名集合必须恰等于
`targets` 集合——conf 加目标而 README 不提（少提）与 README 提了而
conf 不打（多提）都红。更新包 token 的 `<bool>` 形状让开关翻转在
W27b 与 conf 值对不上时红；安装模式同理。

## 3. 实现

### 3.1 生产代码

- 零改动（三键本来就同账，纯钉住）。

### 3.2 `tests/test_desktop_readme_packaging.py`（W27a / W27b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W27a | 产物/更新包行（macOS 小节）与安装包行（Windows 小节）各恰一处；产物行同时含 `.app` 与 `.dmg` token；更新包行恰一处 `createUpdaterArtifacts=<bool>` token；安装包行恰一处 NSIS 安装模式 token；conf 三键存在且类型正确 | README 两小节 + 两份 tauri conf |
| W27b | 产物扩展名集合 == `targets` 集合（双向）；更新包 token 布尔 == conf 值；安装模式 token == conf 值 | 同上 |

实现要点：

- 「安装包」行在 Windows 小节有两处 `| 安装包 |` 形状（正式表 +
  「同一版本生成两个安装包」表的表头）——锚带 `NSIS` 前缀消歧
  （`| 安装包 | NSIS`），表头行与另一表不进射程。
- 产物行的扩展名 token 按已知打包类型词表（`app/dmg/deb/rpm/appimage/
  msi/nsis`）提取；集合比较天然双向，词表只服务提取不设限 conf 侧
  （conf 出现词表外目标时集合不等，W27b 红）。
- macOS/Windows 两份 conf 的键路径固定（`bundle.targets` /
  `bundle.createUpdaterArtifacts` / `bundle.windows.nsis.installMode`），
  解析不到显式红。

## 4. 验证

- 定向：`tests/test_desktop_readme_packaging.py` 2 passed。
- 关联面：`test_desktop_ui_paths.py`（W25）、
  `test_desktop_windows_runner.py`（W26）、`test_desktop_macos_scope.py`
  （W24）、`test_desktop_dmg_reference.py`（W23）、
  `test_desktop_packaging.py`、`test_index_snapshot.py` 全绿；S2/S3/S5
  在本提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3141 passed / 28 skipped / 0 failed**（3169 条，
  约 12m12s）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  README / 两份 tauri conf 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 `targets` `["app","dmg"]`→`["app","dmg","deb"]` | W27b 红（README 少提 `.deb`）、W27a 绿 |
| M2 更新包行删 `createUpdaterArtifacts=false` token | W27a 红（语料守卫）、W27b 红（解析不到） |
| M3 `installMode` `"currentUser"`→`"perMachine"` | W27b 红、W27a 绿 |

## 5. 边界与遗留

- 只判三行表与三个键：不判基础 `tauri.conf.json` 的
  `bundle.targets == ["nsis"]` 与 `bundle.createUpdaterArtifacts == true`
  （Windows 侧的 NSIS 目标与发版 `.sig` 账，README「桌面更新发布」节
  另行叙述，登记口径未含）、不判 `nsis` 的其余键（compression /
  languages / installerHooks 等）、不判 `flavor` 矩阵（W24 射程）、
  不判打包的执行行为（CI 负责）。
- 四轮连推（十七）收官轮 **R192 收口轮（R189–R192 四账）+ 登记
  R193–R196**。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`f58328b`** 推送后 run **42350304034**：**10 job 全
  `success`**（07:12:38→07:26:15 UTC，约 13m37s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42350304034`，bot 提交 **`6a1a0f4`**）。R192 回填。

## 7. 提交

- 改动：`tests/test_desktop_readme_packaging.py`（W27）、R191 文档、
  R190 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/批次行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R191 一条）、
  `JUDGEMENT_LEDGER.md`（§10.63）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
