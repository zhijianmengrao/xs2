# DeterminFlow (xs2) 交接报告 — Round 198（desktop workflow 脚本引用路径逐处可解析：W32）

> 单 profile。四轮连推（十九）第 2 轮：把三份 desktop workflow 的
> `desktop/scripts/*` 引用（17 处 / 9 脚本）钉成「逐份计数恰等 +
> 逐处按仓库根解析后在磁盘」。生产代码零改动，本轮无修复——登记面
> 实测即全绿。变异 3/3。

## 1. 一句话结论

- `tests/test_desktop_workflow_script_refs.py` 新增 **W32a/W32b**：
  三份 workflow 的 `desktop/scripts/*` 引用数逐份恰等
  （desktop-windows.yml 8 / desktop-macos.yml 8 /
  replace-desktop-assets.yml 1，合计 17）（W32a）；17 处引用逐处按
  仓库根解析后在磁盘（W32b）。总用例 3189 → **3193**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R197 §6 进入回填扫描区间）。
- 变异 **3/3**：desktop-macos 与 replace-desktop-assets 各改一处脚本名
  （W32b 各自独红）、desktop-windows 删一处引用前缀（W32a 独红）。
- **回填**：R197 §6（run `42385614161` / bot `37b72c7`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）；R197 §7
  「生产代码与测试外零改动」笔误顺手翻正为「生产代码零改动」。

## 2. 为什么是这一轮

V8（R182）把 desktop README 的命令引用面钉成「逐条可执行」，但
workflow 侧没有锚：`desktop-*.yml` 的 run 步骤引用
`desktop/scripts/*.py`（和 `.ps1`）是纯字面路径，脚本改名/挪走时
push 阶段不查、CI 到 run 时才炸——而且是三个分发工作流一起炸
（refresh_official_plugin_lock 与 verify_bundle 同时被两份 workflow
引用），炸点还都在发版路径的深处（publish_r2_release 在
R2_DISTRIBUTION_ENABLED 门槛之后）。R198 开工实测：17 处引用 / 9 个
不同脚本，登记面与 R196 §3 的实测完全一致，全部在磁盘——纯钉住。

W32 的锚选在「计数与解析分工」：计数恰等是语料守卫（加/删引用强迫
并账），逐处解析是行为锚（改名/挪走不等 run 时才炸）。两者分开
——只数个数会让「8 处引用全指向不存在的脚本」漏网，只解析会让
「悄悄少了一处引用」不红。

## 3. 实现

### 3.1 生产代码

- 零改动（17 处引用全部可解析，纯钉住）。

### 3.2 `tests/test_desktop_workflow_script_refs.py`（W32a / W32b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W32a | 三份 workflow 的 `desktop/scripts/*` 引用数逐份恰等（8/8/1，合计 17）——加/删引用先红语料守卫 | 三份 desktop workflow |
| W32b | 每处引用按仓库根 `Path.is_file()` 解析——解析不到显式红 | 同上 |

实现要点：

- 引用形状 `desktop/scripts/[A-Za-z0-9_.\-]+`：`.ps1` 与 `.py` 都进
  同一份账（smoke_installer.ps1 是 17 处里唯一的 PowerShell 脚本，
  按路径解析不按后缀区分）。
- 语料守卫按文件分桶（8/8/1）而不是只钉总数：一份 workflow 删引用、
  另一份加引用（总数不变 17）也要红。
- 解析循环不与 17 耦合（首版把 `checked == 17` 放进 W32b，会让
  「删引用」变异双红；计数钉在 W32a，W32b 只管存在——变异各自独红）。

## 4. 验证

- 定向：`tests/test_desktop_workflow_script_refs.py` 2 passed（首跑即
  过）；关联面 `test_desktop_workflow_name.py`（W28）、
  `test_desktop_r2_credentials.py`（W30）、
  `test_desktop_r2_fallback_domain.py`（W31）、
  `test_desktop_flavor_vocabulary.py`（W29）全绿；S2/S3/S5 在本提交前
  的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3165 passed / 28 skipped / 0 failed**（3193 条，
  约 10m32s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  三份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 desktop-macos.yml `generate_macos_icon.py` 引用改名 | W32b 红（解析不到）、W32a 绿（计数不变） |
| M2 desktop-windows.yml 一处 `verify_bundle.py` 引用删 `desktop/` 前缀 | W32a 红（8→7）、W32b 绿（剩余引用全解析） |
| M3 replace-desktop-assets.yml `publish_r2_release.py` 引用改名 | W32b 红（解析不到）、W32a 绿 |

## 5. 边界与遗留

- 只判 `desktop/scripts/` 形状的字面引用——不判脚本内容、不判 step 的
  执行行为（CI 负责）、不判 README 侧命令引用面（V8 已管）、
  `ci.yml` 实测 0 处引用（非桌面分发面，不进账）。
- 四轮连推（十九）续 **R199 README R2 发行路径 ↔
  publish_r2_release.py 两段同账（W33）**、**R200 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_workflow_script_refs.py`（W32）、R198 文档、
  R197 §6 回填 + §7 笔误翻正、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R198 一条）、
  `JUDGEMENT_LEDGER.md`（§10.70）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
