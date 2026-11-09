# DeterminFlow (xs2) 交接报告 — Round 233（replace workflow release 步 outputs 定义 == 消费：W58）

> 单 profile。四轮连推（二十八）第 1 轮：把 replace-desktop-assets.yml
> release 步的三个 GITHUB_OUTPUT（version/tag/pub_date）与消费点钉成
> 双向恰等。生产代码零改动，本轮无修复——输出键现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_replace_outputs.py` 新增 **W58a/W58b**：定义恰
  一处 `f.write`、恰 3 个键行（W58a）；定义键集合 == 消费键集合
  （消费未定义的红、定义未消费的死输出也红）（W58b）。总用例
  3311 → **3315**（+2 钉测、+1 N3 本篇、+1 D1 因 R232 §6 进入回填
  扫描区间）。
- 变异 **4/4**：消费 `outputs.tag` 错拼 / 消费行删除（W58b 各自独
  红）、`tag` 定义删除（双红：计数与集合都断，如实登记）、`tag`
  定义复制（W58a 独红）。
- **回填**：R232 §6（run `42620863849` / bot `d76db83`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

replace-desktop-assets.yml 的 release 步用一行 `f.write` 向
GITHUB_OUTPUT 写三个键（L105 的格式串
`version={version}\ntag={tag}\npub_date={stamp}\n`），消费点为后续
两步的 `steps.release.outputs.tag`（L110）、`.version`（L128）、
`.tag`（L129）、`.pub_date`（L130）。定义与消费漂移无人判：消费写错
键名时 `publish_r2_release.py` 拿到空 version/tag——R2 上传路径错位、
稳定清单的 pub_date 缺失；或定义改名/删除而消费没跟（死输出）。

W56 管 desktop-windows.yml 的 installer 步 outputs，W57 管 workflow
inputs，W58 把同一形态推到 replace workflow 的 **release 步 outputs**。

W58 的锚选在「双向恰等」：消费未定义（引用打错）与定义未消费
（死输出）都红——单向 ⊆ 会漏掉后者。

## 3. 实现

### 3.1 生产代码

- 零改动（输出键现同账，纯钉住）。

### 3.2 `tests/test_desktop_replace_outputs.py`（W58a / W58b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W58a | 定义恰一处 `f.write(f'…')`、恰 3 个键行 | replace-desktop-assets.yml |
| W58b | 定义键集合 == 消费键集合（双向） | 同上 |

实现要点：

- 定义提取 `f\.write\(f'([^']*)'\)`——键行按 f-string 里的**字面**
  `\n`（反斜杠 + n）切分（`chr(92) + "n"`），不是换行符；按 `=` 取
  键名。
- 消费提取 `steps\.release\.outputs\.(\w+)`——L110/128/129/130 四处
  引用全进（tag 出现两次）。
- M3（删一行定义）是天然双红：计数与集合同时断——如实登记。

## 4. 验证

- 定向：`tests/test_desktop_replace_outputs.py` 2 passed（首跑即过）；
  关联面 `test_desktop_replace_inputs.py`（W57）、
  `test_desktop_installer_outputs.py`（W56）全绿。
- 本机全量：**3287 passed / 28 skipped / 0 failed**（3315 条，
  约 9m09s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  replace-desktop-assets.yml 为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 消费 `outputs.tag` 错拼为 `outputs.tags`（首处 RELEASE_TAG） | W58b 红（消费未定义）、W58a 绿 |
| M2 `VERSION` 消费行删除 | W58b 红（定义未消费）、W58a 绿 |
| M3 `tag` 定义行删除 | W58a 红（3→2）+ W58b 红（集合不等，双红） |
| M4 `tag` 定义行复制 | W58a 红（3→4）、W58b 绿（集合不变） |

## 5. 边界与遗留

- 只判输出键名的字面同账——不判键值（version/tag/stamp 的取值由其
  他判据与脚本负责）、不判 `gh release`/`publish_r2_release` 行为
  （CI 负责）、不判其余 step 的 outputs。
- 四轮连推（二十八）续 **R234 create_manifest import 调用面同账
  （W59）**、**R235 publish_r2_release 调用面同账（W60）**、
  **R236 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_replace_outputs.py`（W58）、R233 文档、
  R232 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/批次行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R233 一条）、
  `JUDGEMENT_LEDGER.md`（§10.105）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
