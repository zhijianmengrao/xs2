# DeterminFlow (xs2) 交接报告 — Round 189（desktop README 架构表路径同账：W25）

> 单 profile。四轮连推（十七）第 1 轮：把架构表「桌面适配」行背后的
> 四源路径链钉成同账；生产代码零改动。变异 3/3。

## 1. 一句话结论

- **实测（登记三锚 + 开工补第四锚）**：架构表「桌面适配」行的
  `ui/desktop-adapter.js` 按 README 基座目录（`desktop/`）解析为
  `desktop/ui/desktop-adapter.js`，在磁盘；`desktop/package.json` 的
  `test` script 引用同目录的 `ui/desktop-adapter.test.mjs`，也在；
  `desktop/src-tauri/tauri.conf.json` 的 `build.frontendDist == "../ui"`
  且 `desktop/ui/index.html` 在磁盘。开工实测补上第四源——
  `desktop/src-tauri/src/main.rs:118` 的注入点
  `include_str!("../../ui/desktop-adapter.js")`：它是四个引用点里唯一的
  生产代码（`include_str!` 是编译期路径，adapter 挪走时 Rust 构建硬失败，
  但 README / package.json / frontendDist 都不会红）。
- `tests/test_desktop_ui_paths.py` 新增 **W25a/W25b**：四源语料守卫 +
  逐基座解析性 + `index.html` 入口存在（W25a）、四源字面值逐字钉死 +
  同目录闭包（W25b）。总用例 3157 → **3161**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R188 §6 进入回填扫描区间）。
- 变异 **3/3**：README adapter 改名（W25a+W25b 红）、main.rs include_str
  指向同目录另一文件（W25b 独红、W25a 绿）、frontendDist 改指
  `../src-tauri`（W25a+W25b 红）。
- **回填**：R188 §6（run `42262128623` / bot `f409d73`）与索引 §1 的
  写回 / 基线两行（S2/S5 在 bot 之后按约定先红，本轮翻正）。

## 2. 为什么是这一轮

「桌面适配」行是架构表里唯一一行既有文档叙述又有完整工程链的：adapter
文件是 Tauri 注入的错误弹窗 + Provider Key 连通性检查脚本，README 声称
「仅由 Tauri 注入，服务版不加载」。这条声明的成立依赖四个引用点互相同
目录——README 的人读账、package.json 的测试账、tauri.conf 的打包账
（`frontendDist` 决定哪些前端资产进安装包，指错目录会打出空壳包）、
main.rs 的注入账。adapter 改名/移动时，`include_str!` 会让 Rust 构建
硬失败，但另外三个引用点静默失真；frontendDist 指错目录时四个点全都
「看起来正常」，只有装出来的包是空壳。此前无人判——W18 管版本五源、
W22 管 identifier 六处、W20 管最低版本、V8 管命令引用，这条 ui 路径链
不在任何一条判据的射程里。

W25 的锚选在「四源各恰一处 + 同目录闭包」：字面值逐字钉死（同 W22 的
逐字同账口径），目录闭包让「文件都存在但不在同一个目录」的中间态也红
（M2 变异就是这种形状：include_str 指向同目录的 test 文件，文件存在、
目录同账，只有字面值漂移可判）。

## 3. 实现

### 3.1 生产代码

- 零改动（四源本来就同账，纯钉住）。

### 3.2 `tests/test_desktop_ui_paths.py`（W25a / W25b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W25a | 四源各恰一处（架构表「桌面适配」行 / test script 的 `ui/*.test.mjs` / `build.frontendDist` / 引用 `ui/` 的 `include_str!`）；按各自基座解析后在磁盘；frontendDist 目录下 `index.html` 在磁盘 | README + package.json + tauri.conf + main.rs |
| W25b | 四源字面值逐字钉死；adapter 与 test script 文件的父目录 == frontendDist 解析目录 | 同上四源 |

实现要点：

- README 侧锚 `| 桌面适配 |` 行首、值取反引号内 token；package.json 的
  test script 按 `ui/<name>.test.mjs` 形状正则提取；main.rs 按
  `include_str!(…)` 正则提取后过滤含 `ui/` 的目标（本仓唯一）。
- `frontendDist` 的 `index.html` 存在性是空壳包守卫：main.rs 的
  `WebviewUrl::App("index.html")` 以它为窗口入口，打包目录指对但入口
  缺失同样是空壳。
- 同目录比较全部走 `resolve()`：四个引用点按各自基座（`desktop/`、
  `desktop/`、`desktop/src-tauri/`、`desktop/src-tauri/src/`）解析到
  绝对路径再比父目录，避免相对路径字面比较的假绿。

## 4. 验证

- 定向：`tests/test_desktop_ui_paths.py` 2 passed。
- 关联面：`test_desktop_packaging.py`、`test_desktop_pipeline_commands.py`
  （V8）、`test_desktop_dmg_reference.py`（W23）、
  `test_desktop_macos_scope.py`（W24）、`test_desktop_defaults.py`
  （W19）、`test_docs_navigation.py` 全绿；S2/S3/S5 在本提交前的红是
  约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3133 passed / 28 skipped / 0 failed**（3161 条，
  约 13m42s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 README `ui/desktop-adapter.js`→`ui/desktop_adapter.js` | W25a 红（解析不到）、W25b 红（字面值） |
| M2 main.rs include_str →`../../ui/desktop-adapter.test.mjs`（文件存在） | W25b 独红、W25a 绿 |
| M3 frontendDist `../ui`→`../src-tauri`（目录在、无 index.html） | W25a 红（空壳守卫）、W25b 红 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（README /
tauri.conf / main.rs 均为 CRLF）。

## 5. 边界与遗留

- 只判架构表「桌面适配」行与三个工程引用点：不判 Windows / macOS 表
  行（W26/W27 射程）、不判 frontendDist 的打包行为（CI 负责）、不判
  adapter 的运行时行为与测试执行（npm test / cargo test 负责）、不判
  Rust 侧其他 `include_str`（本仓引用 `ui/` 的只有这一处）。
- W25 登记时只数到三锚，开工实测补上 main.rs 注入点——候选制在实测
  阶段修正判据覆盖面（W18 五源、W13 八源、R175 同型）。
- 四轮连推（十七）下一轮 **R190 desktop README Windows 表 ↔
  desktop-windows.yml（W26）**。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`9bdb788`** 推送后 run **42345750962**：**10 job 全
  `success`**（06:09:37→06:23:06 UTC，约 13m29s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42345750962`，bot 提交 **`501346f`**）。R190 回填。

## 7. 提交

- 改动：`tests/test_desktop_ui_paths.py`（W25）、R189 文档、R188 §6
  回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/批次行 + §4 H2/
  一行 + §6.1）、`PROJECT_INFO.md`（H2 + R189 一条）、
  `JUDGEMENT_LEDGER.md`（§10.61）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
