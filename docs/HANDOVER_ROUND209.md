# DeterminFlow (xs2) 交接报告 — Round 209（跨平台脚本调用面同账：W40）

> 单 profile。四轮连推（二十二）第 1 轮：把 windows/macos 对称调用的
> 两个脚本（build_backend ×2、refresh_official_plugin_lock ×2）钉成
> 「计数对称 + 实参逐字同账」。生产代码零改动，本轮无修复——对称面
> 现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_symmetric_script_calls.py` 新增 **W40a/W40b**：
  两脚本各恰 2 处调用、windows/macos 各恰 1 处（W40a）；每脚本各处
  调用的参数尾（脚本路径后的全部实参，空白归一）逐字恰等——
  build_backend 两处均 `--flavor ${{ matrix.flavor }}`、
  refresh_official_plugin_lock 两处均 `--check`（W40b）。总用例
  3227 → **3231**（+2 钉测、+1 N3 本篇、+1 D1 因 R208 §6 进入回填
  扫描区间）。
- 变异 **4/4**：macos build_backend `--flavor` 错拼 / windows refresh
  丢 `--check`（W40b 各自独红）、macos build_backend 调用删除 /
  windows build_backend 调用复制（W40a 各自独红）。
- **回填**：R208 §6（run `42412908426` / bot `06d546a`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop workflow 里有两份脚本被 windows/macos **对称调用**：
`build_backend.py`（两平台构建 backend 的唯一入口）与
`refresh_official_plugin_lock.py`（两平台发版前的插件锁校验）。对称
面漂移无人判：一边改 flag、换值或丢 flag——macos 构建出的 backend
与 windows 语义分叉（如一边 `--flavor full` 一边丢 flag 走默认
core）、或一边校验插件锁一边不校验；CI 各自全绿，产物已经不同。
W32 管这些脚本的**路径**可解析，W38/W39 管单平台侧 verify_bundle 与
create_update_manifest 的 flag 面，对称调用的两份账第一次进射程。

W40 的锚选在「计数对称 + 实参恰等」：先钉形状（每脚本 2 处、两平台
各 1），再钉值（参数尾逐字同账）——实参取整个参数尾（空白归一）而
不是逐 flag 提取，加一个共享 flag 也算漂移。

## 3. 实现

### 3.1 生产代码

- 零改动（对称面现同账，纯钉住）。

### 3.2 `tests/test_desktop_symmetric_script_calls.py`（W40a / W40b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W40a | 两脚本各恰 2 处调用、windows/macos 各恰 1 处 | desktop-windows.yml + desktop-macos.yml |
| W40b | 每脚本各处调用的参数尾逐字恰等（空白归一） | 同上 |

实现要点：

- 参数尾 = 脚本路径后的整段（W38 的展开循环正则），`" ".join(tail.split())`
  归一空白后进恰等集合——`--flavor ${{ matrix.flavor }}` 这样的
  表达式原样参与对账。
- 判据按脚本分桶：一边删调用（计数破）红 W40a，一边改实参（值破）
  红 W40b，互不越界。

## 4. 验证

- 定向：`tests/test_desktop_symmetric_script_calls.py` 2 passed（首跑
  即过）；关联面 `test_desktop_verify_bundle_flags.py`（W38）、
  `test_desktop_manifest_flags.py`（W39）、
  `test_desktop_flavor_vocabulary.py`（W29，--flavor 词表）全绿；
  S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正之前），本提交
  翻正后全绿。
- 本机全量：**3203 passed / 28 skipped / 0 failed**（3231 条，
  约 10m54s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 macos build_backend `--flavor` 错拼 `--flavour` | W40b 红（实参不同账）、W40a 绿 |
| M2 windows refresh 丢 `--check` | W40b 红（实参不同账）、W40a 绿 |
| M3 macos build_backend 调用行删除 | W40a 红（macos 计数 1→0）、W40b 绿（剩余单侧平凡相等） |
| M4 windows build_backend 调用复制一份 | W40a 红（windows 计数 1→2）、W40b 绿（实参全同） |

## 5. 边界与遗留

- 只判 flag 与实参的字面同账——不判 `--flavor` 的取值空间（W29 的
  词表已钉）、不判脚本执行行为（CI 负责）、不判其他脚本的非对称
  调用面（smoke_backend 4 处归 W41、smoke_installer.ps1 归 W42、
  verify_bundle/create_update_manifest 已由 W38/W39 钉）。
- 四轮连推（二十二）续 **R210 smoke_backend 调用面同账（W41）**、
  **R211 smoke_installer.ps1 调用面参数同账（W42）**、**R212 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`7515647`** 推送后 run **42415277699**：**10 job 全
  `success`**（21:19:08→21:36:32 UTC，约 17m24s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42415277699`，bot 提交 **`8ac136a`**）。R210 回填。

## 7. 提交

- 改动：`tests/test_desktop_symmetric_script_calls.py`（W40）、R209
  文档、R208 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/
  阶段行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R209 一条）、
  `JUDGEMENT_LEDGER.md`（§10.81）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
