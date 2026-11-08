# DeterminFlow (xs2) 交接报告 — Round 229（smoke_installer flavor 参数自洽：W55）

> 单 profile。四轮连推（二十七）第 1 轮：把 smoke_installer.ps1 的
> `$Flavor` 默认值钉进 ValidateSet 集合账（W42 已钉集合恰等）。生产
> 代码零改动，本轮无修复——默认值现自洽。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_smoke_flavor_default.py` 新增 **W55a/W55b**：
  默认值赋值与 ValidateSet 各恰一处（W55a）；默认值 ∈ ValidateSet
  集合（== {core, full} 的成员）（W55b）。总用例 3297 → **3301**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R228 §6 进入回填扫描区间）。
- 变异 **4/4**：默认值改成集合外的 "complete"（W55b 独红）、默认值
  赋值删除 / 复制、ValidateSet 删除（W55a 各自独红）。
- **回填**：R228 §6（run `42459940497` / bot `42feffd`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

`smoke_installer.ps1` 的 flavor 参数 `[string]$Flavor = "core"`（L7）
带 `[ValidateSet("core", "full")]`（L6，W42 已钉集合恰等）——默认值
"core" ∈ 集合。默认值漂移无人判：有人把默认值改成集合外的值（如
"complete"），PowerShell 在脚本启动时就抛
ParameterArgumentValidationError——workflow 里表现为「冒烟步骤秒
失败」，与集合漂移（W42）是两个不同的故障面。W42 管集合，默认值的
**∈ 关系**第一次进射程。

W55 的分工沿用定式（W47/W49 定式从一开始就应用）：W55a 管计数
（两锚各恰一处），W55b 存在才判（缺失归 W55a，首版 `[0]` 索引让
「删除」变异双红已修）。

## 3. 实现

### 3.1 生产代码

- 零改动（默认值现自洽，纯钉住）。

### 3.2 `tests/test_desktop_smoke_flavor_default.py`（W55a / W55b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W55a | 默认值赋值恰一处；ValidateSet 恰一处 | desktop/scripts/smoke_installer.ps1 |
| W55b | 默认值 ∈ ValidateSet 集合（存在才判） | 同上 |

实现要点：

- 默认值提取 `` [string]\$Flavor\s*=\s*"([^"]+)" ``；ValidateSet 提取
  与 W42/W51 同款。
- W55b 的 `if not defaults or not validatesets: return`——缺失归
  W55a 的计数账，W55b 只对共存时的 ∈ 关系负责。

## 4. 验证

- 定向：`tests/test_desktop_smoke_flavor_default.py` 2 passed（首跑
  把 W55b 改成存在才判后即过）；关联面
  `test_desktop_smoke_installer_params.py`（W42，集合恰等）、
  `test_desktop_display_name.py`（W53）、
  `test_desktop_flavor_vocabulary.py`（W29）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3273 passed / 28 skipped / 0 failed**（3301 条，
  约 13m16s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  smoke_installer.ps1 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 默认值改集合外的 "complete" | W55b 红（∉ 集合）、W55a 绿 |
| M2 默认值赋值删除 | W55a 红（1→0）、W55b 绿（缺失归 W55a） |
| M3 默认值赋值复制 | W55a 红（1→2）、W55b 绿 |
| M4 ValidateSet 删除 | W55a 红（1→0）、W55b 绿 |

## 5. 边界与遗留

- 只判默认值 ∈ 集合的字面同账——不判 ValidateSet 集合的内容（W42
  已管恰等 {core, full}）、不判 PowerShell 的参数绑定语义、不判执行
  行为（CI 负责）。
- 四轮连推（二十七）续 **R230 installer 步 outputs 定义 == 消费
  （W56）**、**R231 replace workflow inputs 定义 == 消费（W57）**、
  **R232 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_smoke_flavor_default.py`（W55）、R229
  文档、R228 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/
  阶段行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R229 一条）、
  `JUDGEMENT_LEDGER.md`（§10.101）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
