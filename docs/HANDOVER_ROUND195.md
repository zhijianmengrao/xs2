# DeterminFlow (xs2) 交接报告 — Round 195（README R2 分发凭据同账：W30）

> 单 profile。四轮连推（十八）第 3 轮：把 README 的「只通过…注入」
> 凭据清单钉到三份 desktop workflow 的 `secrets.*`/`vars.*` 引用上；
> 生产代码零改动，文档清单一行补齐。变异 3/3。

## 1. 一句话结论

- **实测修复**：desktop/README.md「桌面更新发布」节写「R2 凭据只通过
  `R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY` Secret 和 `R2_BUCKET`、
  `R2_ENDPOINT_URL` Variable 注入」，而 desktop 工作流实际消费七个名字
  ——「只」清单漏 `R2_PUBLIC_BASE_URL`（未设置时回落
  `https://downloads.determinflow.com`）。照清单配仓库的人会少配一个
  Variable，发版时 `--public-base-url` 拿到回落值而不是仓库配置值
  ——配置静默失效。R195 把该 Variable 补进清单（附回落说明），
  候选制第四处实测抓到的真实不一致落地修复（R177 P10、R187 W24、
  R193 W28 之后）。
- `tests/test_desktop_r2_credentials.py` 新增 **W30a/W30b**：「桌面更新
  发布」节凭据提名（`R2_*`/`TAURI_*` 形状反引号 token）可解析 + 「R2
  凭据只通过」清单句恰一处 + 三份 desktop workflow 的
  `secrets.*`/`vars.*` 引用可解析（W30a）、README 提名集合 == 三份
  workflow 消费集合（W30b，双向恰等：7 == 7）。总用例 3179 → **3183**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R194 §6 进入回填扫描区间）。
- 变异 **3/3**：README 清单删 `R2_ENDPOINT_URL`（W30b 红）、
  desktop-windows.yml 把 `secrets.TAURI_SIGNING_PRIVATE_KEY` 消费名改名
  （W30b 红）、清单句复制一份（W30a 独红：形状守卫，集合不变）。
- **回填**：R194 §6（run `42373110759` / bot `1289b49`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

「只通过…注入」是一份排他性清单：读者按它配置仓库凭据，清单里没有的
名字就不会配。R46 把两处 `--public-base-url` 改成
`${{ vars.R2_PUBLIC_BASE_URL || 'https://downloads.determinflow.com' }}`
时（变量化分发域名），desktop-windows.yml 与 replace-desktop-assets.yml
都开始消费 `vars.R2_PUBLIC_BASE_URL`，README 的清单没有跟上——「只」
字从此为假：注入 R2 凭据的 Variable 实际有五个，README 只认四个。这条
边此前无人判：W22/W23/W24/W25/W26/W27/W28 各管一段桌面账，凭据注入面
第一次进射程。

W30 的锚选在「提名集合双向恰等」：README 提名的凭据名集合必须恰等于
三份 desktop workflow 的 `secrets.*`/`vars.*` 引用名集合——workflow 加
消费而 README 不提名（少提）与 README 提名而 workflow 不消费（多提）
都红。`ci.yml` 实测无 `secrets.*`/`vars.*` 引用（非桌面分发面），不进
集合。

## 3. 实现

### 3.1 生产代码

- 零改动（workflow 消费面本来就是七个名字，纯钉住）。
- 文档清单修复：desktop/README.md「桌面更新发布」节的清单句补
  `R2_PUBLIC_BASE_URL` Variable，并附回落说明
  （`未设置时回落 https://downloads.determinflow.com`，与 workflow 内置
  回落一致；该域名字面值不在 W30 射程）。

### 3.2 `tests/test_desktop_r2_credentials.py`（W30a / W30b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W30a | 「桌面更新发布」节恰一处；节内凭据提名（`R2_*`/`TAURI_*` 形状反引号 token，容忍 `=true` 后缀）可解析非空；「R2 凭据只通过」清单句恰一处；三份 desktop workflow 的 `secrets.*`/`vars.*` 引用可解析（desktop-macos.yml 实测无引用，并集非空即可） | desktop/README.md + 三份 desktop workflow |
| W30b | README 提名集合 == 三份 workflow 消费集合（双向恰等） | 同上 |

实现要点：

- 提名提取用 `` `((?:R2|TAURI)_[A-Z0-9_]+(?:=[^`]*)?)` ``，名字取
  `=` 前段——`R2_DISTRIBUTION_ENABLED=true`（节内两处）与裸名字统一
  进集合；`CI` 这类短 token 不在形状内，不误收。
- workflow 侧 `(?:secrets|vars)\.([A-Z0-9_]+)` 扫三份文件取并集；
  `desktop-windows.yml` 7 名、`replace-desktop-assets.yml` 6 名、
  `desktop-macos.yml` 0 名，并集恰 7。
- 「R2 凭据只通过」清单句恰一处是形状守卫：清单被复制/改写成两份时
  集合不变、W30b 仍绿，只有 W30a 显式红。

## 4. 验证

- 定向：`tests/test_desktop_r2_credentials.py` 2 passed（修复后首跑）。
- 关联面：`test_desktop_readme_packaging.py`（W27）、
  `test_desktop_workflow_name.py`（W28）、`test_readme_commands.py`（V6）、
  `test_doc_npm_commands.py`（V7）全绿；S2/S3/S5 在本提交前的红是约定
  （bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3155 passed / 28 skipped / 0 failed**（3183 条，
  约 10m28s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop/README 与 desktop-windows.yml 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 README 清单删 `R2_ENDPOINT_URL` | W30b 红（workflow 消费但 README 未提名）、W30a 绿 |
| M2 desktop-windows.yml `secrets.TAURI_SIGNING_PRIVATE_KEY` → `…_X` | W30b 红（唯一消费名消失）、W30a 绿 |
| M3 清单句复制一份 | W30a 红（清单句恰一处破坏）、W30b 绿（集合不变） |

## 5. 边界与遗留

- 只判 README「桌面更新发布」节的凭据提名与三份 desktop workflow 的
  `secrets.*`/`vars.*` 引用名——不判 `ci.yml`（实测无引用）、不判凭据
  取值与回落域名字面值、不判 `env:` 里 `R2_*` → `AWS_*` 的别名映射
  （实现细节）、不判 step 执行行为（CI 负责）。
- 四轮连推（十八）收官 **R196 收口轮（R193–R196 四账）+ 登记
  R197–R200**。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_r2_credentials.py`（W30）、desktop/README.md
  清单修复、R195 文档、R194 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R195 一条）、
  `JUDGEMENT_LEDGER.md`（§10.67）。
- `config/skills_config.json` 不纳入（C1）。
