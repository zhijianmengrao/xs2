# DeterminFlow (xs2) 交接报告 — Round 197（R2 公网回落域名三源同账：W31）

> 单 profile。四轮连推（十九）第 1 轮：把 R2 分发域名的回落缺省钉成
> 三源同账（两份分发 workflow 的 `${{ vars.R2_PUBLIC_BASE_URL || … }}`
> + README 的「未设置时回落」说明）。生产代码零改动，本轮无修复
> ——三源现同值，判据钉住本来就对的账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_r2_fallback_domain.py` 新增 **W31a/W31b**：两份
  分发 workflow（desktop-windows / replace-desktop-assets）的回落缺省
  模式各恰一处、`--public-base-url "$R2_PUBLIC_BASE_URL"` 消费点各恰
  一处、desktop-macos.yml 实测不在 R2 更新通道（回落模式 0 处）、README
  的「未设置时回落」说明恰一处（W31a）；三源回落域名字面值逐字恰等
  （W31b）。总用例 3185 → **3189**（+2 钉测、+1 N3 本篇、+1 D1 因
  R196 §6 进入回填扫描区间）。
- 变异 **4/4**：两 workflow 与 README 各改回落域名（W31b 各自独红）、
  desktop-windows 消费点改名（W31a 独红：同账集合不变）。
- **回填**：R196 §6（run `42377380740` / bot `aa39207`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

R46 变量化分发域名时，`desktop-windows.yml` 的 env 注释自述「与
replace-desktop-assets.yml 同款，便于改域名时不改代码」——「同款」
是一份承诺，但从没人判。承诺的第三份账在 R195 出现：README 的
「只通过」清单补 `R2_PUBLIC_BASE_URL` 时附了回落说明（
`未设置时回落 https://downloads.determinflow.com`）。三份文件是同一
个回落缺省的三个来源，现同值；此后改域名若只改其一，其余两源的回落
就跟丢——未设变量的仓库会把公开对象 URL 发到旧域名上：发布命令本身
能成功（`--public-base-url` 只是拿到旧值），但公开校验与 `latest.json`
里的下载域名指向另一处，更新通道静默分叉。这条边此前无人判：W22–W30
各管一段桌面账，回落缺省的多源同账第一次进射程。

W31 的锚选在「字面值逐字恰等」而不是「模式存在」：模式存在只保证
回落还写得出，恰等才保证改域名时三源必须同改。

## 3. 实现

### 3.1 生产代码

- 零改动（三源现同值 `https://downloads.determinflow.com`，纯钉住；
  R195 的 README 回落说明是第三源入账的前提）。

### 3.2 `tests/test_desktop_r2_fallback_domain.py`（W31a / W31b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W31a | 两份分发 workflow 的回落缺省模式（`${{ vars.R2_PUBLIC_BASE_URL \|\| '…' }}`）各恰一处；`--public-base-url "$R2_PUBLIC_BASE_URL"` 消费点各恰一处（回落值必须真的被发布命令吃掉）；desktop-macos.yml 回落模式 0 处（多出来的第四源当场红）；README「未设置时回落」说明恰一处 | 两份分发 workflow + desktop-macos.yml + desktop/README.md |
| W31b | 三源回落域名字面值逐字恰等（双向：谁漂谁红） | 同上 |

实现要点：

- workflow 侧提取正则
  `` `\$\{\{\s*vars\.R2_PUBLIC_BASE_URL\s*\|\|\s*'([^']+)'\s*\}\}` ``，
  README 侧 `` `未设置时回落\s*`([^`]+)`` ``——域名字面值都在捕获组
  里，模式与取值分开判（模式漂移红 W31a，取值漂移红 W31b）。
- 消费点钉 `--public-base-url "$R2_PUBLIC_BASE_URL"` 全串（含引号与
  变量名）：只数 `--public-base-url` 会把 README 的说明也算进去。
- desktop-macos.yml 的 0 处是同账集合的封闭性守卫：macOS 候选包不在
  R2 更新通道，多出第四源要么删掉要么并入 W31b。

## 4. 验证

- 定向：`tests/test_desktop_r2_fallback_domain.py` 2 passed（首跑即
  过）；关联面 `test_desktop_r2_credentials.py`（W30）、
  `test_desktop_readme_packaging.py`（W27）、
  `test_desktop_workflow_name.py`（W28）、
  `test_desktop_flavor_vocabulary.py`（W29）、`test_readme_commands.py`
  （V6）全绿；S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正
  之前），本提交翻正后全绿。
- 本机全量：**3161 passed / 28 skipped / 0 failed**（3189 条，
  约 11m00s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 desktop/README 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 desktop-windows.yml 回落域名改值 | W31b 红（其余两源未跟）、W31a 绿 |
| M2 replace-desktop-assets.yml 回落域名改值 | W31b 红（其余两源未跟）、W31a 绿 |
| M3 README 回落 URL 改值 | W31b 红（其余两源未跟）、W31a 绿 |
| M4 desktop-windows.yml 消费点改名 | W31a 红（消费点恰一处破坏）、W31b 绿（同账集合不变） |

## 5. 边界与遗留

- 只判回落域名字面值与消费点的存在——不判未设变量时的回落触发行为
  （CI 负责）、不判 `vars.R2_PUBLIC_BASE_URL` 的取值、不判 R46 注释
  散文（「同款」自述不进射程，注释漂移不红）、不判
  `publish_r2_release.py` 的 URL 拼装逻辑（`public_object_url` 有
  自己的判据面）。
- 四轮连推（十九）续 **R198 desktop workflow 脚本引用路径逐处可解析
  （W32，17 处 / 9 脚本）**、**R199 README R2 发行路径 ↔
  publish_r2_release.py 两段同账（W33）**、**R200 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`5ad352f`** 推送后 run **42385614161**：**10 job 全
  `success`**（15:17:05→15:31:32 UTC，约 14m27s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42385614161`，bot 提交 **`37b72c7`**）。R198 回填。

## 7. 提交

- 改动：`tests/test_desktop_r2_fallback_domain.py`（W31）、R197 文档、
  R196 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R197 一条）、
  `JUDGEMENT_LEDGER.md`（§10.69）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
