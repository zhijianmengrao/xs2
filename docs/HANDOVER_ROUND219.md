# DeterminFlow (xs2) 交接报告 — Round 219（backend 安装段同账：W48）

> 单 profile。四轮连推（二十四）第 3 轮：把 `build_backend.py` 的
> backend 安装段（pathlib 拼装）与 `desktop-macos.yml` 两处 smoke
> 定位段的字面路径钉成同账。生产代码零改动，本轮无修复——段名现
> 同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_backend_install_segment.py` 新增 **W48a/W48b**：
  脚本的 runtime_root/backend_dir 组合行与可执行名三元各恰一处 +
  yml 的 `runtime/backend…` 段恰 2 处（段形状值无关）（W48a）；yml
  两处的 `runtime/backend/determinflow-backend` 全段 == 脚本拼出的段
  与可执行名（W48b）。总用例 3263 → **3267**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R218 §6 进入回填扫描区间）。
- 变异 **4/4**：yml L67 段漂移 / 脚本 backend_dir 改名 / yml L78
  可执行名漂移（W48b 各自独红）、yml L67 定位段删除（W48a 独红）。
- **回填**：R218 §6（run `42436741168` / bot `22ada6b`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

backend 可执行文件的安装位置有两份账：`build_backend.py` 用 pathlib
拼装（`runtime_root = desktop_root / "runtime"`、`backend_dir =
runtime_root / "backend"`、可执行名 `"determinflow-backend.exe" if
win32 else "determinflow-backend"`），`desktop-macos.yml` 的两处
smoke 定位参数按字面路径消费（`…/Contents/Resources/runtime/backend/
determinflow-backend`，L67 构建产物、L78 挂载副本）。段名漂移无人判：
打包资源布局挪动（tauri resources 配置改）只改一边——build 出的
backend 落在新段而 smoke 按旧段找，CI 到 run 时才炸，或 smoke 冒烟的
根本不是打包进去的 backend。W44 管 macOS 产物目录前缀，backend 的
**安装段与可执行名**第一次进射程。

W48 的锚选在「段形状值无关 + 全段同账」：W48a 的 yml 段正则容忍
段名变体（`runtime/backend[^"\s]*`——`backend-x` 也进形状），值由
W48b 与脚本拼出的全段直接比较。

## 3. 实现

### 3.1 生产代码

- 零改动（段名现同账，纯钉住）。

### 3.2 `tests/test_desktop_backend_install_segment.py`（W48a / W48b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W48a | 脚本 runtime_root 行 / backend_dir 行 / 可执行名三元各恰一处；yml `runtime/backend…` 段恰 2 处 | desktop/scripts/build_backend.py + desktop-macos.yml |
| W48b | yml 两处的全段 == 脚本拼出的 `runtime/backend/determinflow-backend` | 同上 |

实现要点：

- yml 段提取 `runtime/backend[^"\s]*`：既排除引号（L78 的路径带引号，
  `\S+` 会吃进尾引号），也容忍段名变体（`backend-x` 进形状归 W48b
  判值，不丢锚）。
- 脚本可执行名从三元 `` `"…exe" if win32 else "…"` `` 提取非 win32
  名（macOS smoke 只会走到 else 分支）。

## 4. 验证

- 定向：`tests/test_desktop_backend_install_segment.py` 2 passed（首跑
  修正段提取（引号误收 / 形状值无关）后即过）；关联面
  `test_desktop_paramless_scripts.py`（W47）、
  `test_desktop_tag_version_strip.py`（W46）、
  `test_desktop_smoke_backend_timeouts.py`（W41）全绿；S2/S3/S5 在本
  提交前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3239 passed / 28 skipped / 0 failed**（3267 条，
  约 11m54s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-macos.yml 与 build_backend.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 yml L67 段 `runtime/backend` → `runtime/backend-x` | W48b 红（全段不等）、W48a 绿（段形状仍进） |
| M2 脚本 `backend_dir` 的 `"backend"` 改名 | W48b 红（全段不等）、W48a 绿 |
| M3 yml L78 可执行名改值 | W48b 红（全段不等）、W48a 绿 |
| M4 yml L67 定位段删除 | W48a 红（2→1）、W48b 绿（剩余处仍等） |

## 5. 边界与遗留

- 只判段名与可执行名的字面同账——不判 win32 侧的 `.exe` 名（windows
  smoke 直接调 onedir 产物，另账）、不判 `Contents/Resources` 前缀
  （tauri 打包布局，tauri 升级行为）、不判 smoke 的执行行为（CI
  负责）。
- 四轮连推（二十四）收官 **R220 收口轮（R217–R220 四账）+ 登记
  R221–R224**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`4cd8f02`** 推送后 run **42439135653**：**10 job 全
  `success`**（02:34:42→02:50:34 UTC，约 15m52s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42439135653`，bot 提交 **`b874423`**）。R220 回填。

## 7. 提交

- 改动：`tests/test_desktop_backend_install_segment.py`（W48）、R219
  文档、R218 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R219 一条）、
  `JUDGEMENT_LEDGER.md`（§10.91）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
