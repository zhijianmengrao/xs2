# DeterminFlow (xs2) 交接报告 — Round 230（installer 步 outputs 定义 == 消费：W56）

> 单 profile。四轮连推（二十七）第 2 轮：把 desktop-windows.yml
> installer 步的 GITHUB_OUTPUT 定义（path/checksum/signature）与消费
> 点钉成双向恰等。生产代码零改动，本轮无修复——输出键现同账。
> 变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_installer_outputs.py` 新增 **W56a/W56b**：定义块
  恰 3 行（W56a）；定义键集合 == 消费键集合（消费未定义的红、定义
  未消费的死输出也红）（W56b）。总用例 3301 → **3305**（+2 钉测、
  +1 N3 本篇、+1 D1 因 R229 §6 进入回填扫描区间）。
- 变异 **4/4**：消费 `outputs.signature` 错拼 / 定义 `signature=` 错拼
  （W56b 各自独红）、checksum 定义行删除（双红：计数与集合都断，
  如实登记）、复制（W56a 独红）。
- **回填**：R229 §6（run `42462212672` / bot `16c3d48`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop-windows.yml 的 installer 步定义三个 GITHUB_OUTPUT
（`"path=$($installer.FullName)" >> $env:GITHUB_OUTPUT` 等三行：
path/checksum/signature），消费点为 smoke_installer 的
`outputs.path`（L127）与 upload-artifact 的三个（L142–144）。定义与
消费漂移无人判：消费写错输出名（引用不存在的 output——空字符串传
给 smoke/artifact）、或定义改名/删除而消费没跟——安装冒烟拿到空
Installer 路径、或 artifact 上传空路径。W55 管 smoke 的参数默认值，
GITHUB_OUTPUT 的**定义↔消费**面第一次进射程。

W56 的锚选在「双向恰等」：消费未定义（引用打错）与定义未消费（死
输出）都红——单向 ⊆ 会漏掉后者。

## 3. 实现

### 3.1 生产代码

- 零改动（输出键现同账，纯钉住）。

### 3.2 `tests/test_desktop_installer_outputs.py`（W56a / W56b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W56a | 定义块恰 3 行（`"key=…" >> $env:GITHUB_OUTPUT` 形状） | desktop-windows.yml |
| W56b | 定义键集合 == 消费键集合（双向） | 同上 |

实现要点：

- 定义提取 `` "(\w+)=[^"]*"\s*>>\s*\$env:GITHUB_OUTPUT ``——首版把
  `>>` 写进了引号内（实际 YAML 行的引号在 `>>` 前闭合），提取 0 行；
  修正后 3 行。
- 消费提取 `` steps\.installer\.outputs\.(\w+) ``——smoke 步与
  upload-artifact 的 4 处引用全进。
- M3（删一行定义）是天然双红：计数与集合同时断——如实登记。

## 4. 验证

- 定向：`tests/test_desktop_installer_outputs.py` 2 passed（首跑修正
  定义正则的引号位置后即过）；关联面
  `test_desktop_smoke_flavor_default.py`（W55）、
  `test_desktop_display_name.py`（W53）、
  `test_desktop_tag_version_strip.py`（W46）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3277 passed / 28 skipped / 0 failed**（3305 条，
  约 13m10s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-windows.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 消费 `outputs.signature` 错拼 | W56b 红（消费未定义）、W56a 绿 |
| M2 定义 `signature=` 错拼 | W56b 红（定义未消费）、W56a 绿 |
| M3 checksum 定义行删除 | W56a 红（3→2）+ W56b 红（集合不等，双红） |
| M4 checksum 定义行复制 | W56a 红（3→4）、W56b 绿（集合不变） |

## 5. 边界与遗留

- 只判输出键名的字面同账——不判输出的取值（`$installer.FullName`
  的解析是 PowerShell 运行时）、不判 artifact 的上传行为（CI 负责）、
  不判其他 step 的 outputs（smoke 步没有 outputs）。
- 四轮连推（二十七）续 **R231 replace workflow inputs 定义 == 消费
  （W57）**、**R232 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`d4a5a47`** 推送后 run **42464619245**：**10 job 全
  `success`**（08:50:28→09:08:21 UTC，约 17m53s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42464619245`，bot 提交 **`f4c62cc`**）。R231 回填。

## 7. 提交

- 改动：`tests/test_desktop_installer_outputs.py`（W56）、R230 文档、
  R229 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R230 一条）、
  `JUDGEMENT_LEDGER.md`（§10.102）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
