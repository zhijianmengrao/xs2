# DeterminFlow (xs2) 交接报告 — Round 217（tag→version 剥离逻辑同账：W46）

> 单 profile。四轮连推（二十四）第 1 轮：把 desktop-windows.yml 的
> `version="${RELEASE_TAG#v}"`（tag 剥 v 得版本号）三处复制钉成逐字
> 恰等。生产代码零改动，本轮无修复——剥离逻辑现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_tag_version_strip.py` 新增 **W46a/W46b**：
  `version="${RELEASE_TAG#v}"` 恰 3 处（W46a）；3 处逐字恰等（集合
  大小 1）（W46b）。总用例 3255 → **3259**（+2 钉测、+1 N3 本篇、
  +1 D1 因 R216 §6 进入回填扫描区间）。
- 变异 **4/4**：一处改 `${RELEASE_TAG:1}` 写法（W46b 独红）、一处丢
  剥离 / 一处删除 / 加第四处（W46a 各自独红）。
- **回填**：R216 §6（run `42432050406` / bot `aacd04a`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

desktop-windows.yml 的 `version="${RELEASE_TAG#v}"`（bash 参数展开
剥掉 tag 的 v 前缀）出现在三个发版步骤：bash 后缀循环（L172）、
create_update_manifest（L184）、publish_r2_release（L223）。同一条
「tag→版本」剥离逻辑三处复制：一处改剥离逻辑（如换成
`${RELEASE_TAG:1}`、或支持无 v 前缀的 tag）而其余没跟——同一 tag
构建出的清单/发布资产版本号分叉：latest.json 写一种、R2 资产前缀写
另一种，更新通道与资产目录对不上。W45 管 npm script 名，版本号的
**来源逻辑**第一次进射程。

W46 的锚选在「恰 3 处 + 集合大小 1」：计数钉语料（三处是设计——
三个步骤各自需要版本号），值恰等钉逻辑（改写法即翻红）。

## 3. 实现

### 3.1 生产代码

- 零改动（剥离逻辑现同账，纯钉住）。

### 3.2 `tests/test_desktop_tag_version_strip.py`（W46a / W46b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W46a | `version="${RELEASE_TAG#v}"` 恰 3 处 | desktop-windows.yml |
| W46b | 3 处逐字恰等（集合大小 1） | 同上 |

实现要点：

- 形状正则钉整条赋值 `version="\$\{RELEASE_TAG#v\}"`——`${RELEASE_TAG:1}`
  等价写法也翻红（等价与否是维护者语义，账面要求逐字）。
- W46b 集合比较：一处漂移 → 集合大小 2 → 红。

## 4. 验证

- 定向：`tests/test_desktop_tag_version_strip.py` 2 passed（首跑即
  过）；关联面 `test_desktop_npm_scripts.py`（W45）、
  `test_desktop_r2_gate.py`（W43）、`test_desktop_product_paths.py`
  （W44）全绿；S2/S3/S5 在本提交前的红是约定（bot 之后、索引翻正
  之前），本提交翻正后全绿。
- 本机全量：**3231 passed / 28 skipped / 0 failed**（3259 条，
  约 11m47s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  desktop-windows.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 一处 `${RELEASE_TAG#v}` → `${RELEASE_TAG:1}` | W46b 红（集合大小 2）、W46a 绿 |
| M2 一处丢剥离 `${RELEASE_TAG}` | W46a 红（3→2）、W46b 绿 |
| M3 一处删除 | W46a 红（3→2）、W46b 绿 |
| M4 加第四处 | W46a 红（3→4）、W46b 绿 |

## 5. 边界与遗留

- 只判该赋值语句的字面同账——不判 tag 的取值（RELEASE_TAG 来自
  github.ref_name，CI 负责）、不判 `${RELEASE_TAG#v}` 的 bash 语义、
  不判发布版本与代码版本五源的关系（tag 驱动发版的设计语义，见
  R216 §5 实测观察）。
- 四轮连推（二十四）续 **R218 macOS 无参前置脚本调用面（W47）**、
  **R219 backend 安装段同账（W48）**、**R220 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`c10b0b0`** 推送后 run **42434262921**：**10 job 全
  `success`**（01:26:29→01:43:38 UTC，约 17m09s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42434262921`，bot 提交 **`7e21fe4`**）。R218 回填。

## 7. 提交

- 改动：`tests/test_desktop_tag_version_strip.py`（W46）、R217 文档、
  R216 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R217 一条）、
  `JUDGEMENT_LEDGER.md`（§10.89）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
