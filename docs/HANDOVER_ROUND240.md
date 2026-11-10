# DeterminFlow (xs2) 交接报告 — Round 240（收口轮：R237–R240 四账 + R241–R244 登记）

> 单 profile。四轮连推（二十九）收口轮：四账审计 + 下一批主题实测
> 登记。本轮无新判据。R237–R239 三条判据全部落地（W61 / W62 / W63），
> 全部「钉住本来就对的账」（无修复），生产代码零改动，变异合计 12/12。

## 1. 一句话结论

- R237–R239 全部完成：R237 replace workflow provenance 步 env 定义 ==
  os.environ 消费（W61，{WINDOWS_RUN,MACOS_RUN} 双向恰等）；R238
  replace workflow 资产目录名四源同账（W62，mkdir/--dir/Path/--assets-dir
  逐字恰等）；R239 replace 下载清单 ↔ 两 producer artifact 名同账
  （W63，模板按 matrix 展开后双向恰等）。
- 三轮变异合计 **12/12**（R237 4 + R238 4 + R239 4；R240 收口轮无新
  判据，无变异面）。
- §3 登记 **R241–R244**（全部先实测后登记）：workflow 路径字面多源同账
  （W64）、desktop-windows 编排 needs/uses ↔ job 键同账（W65）、
  build-runs.json 写读同账（W66）、收口。
- 总用例 3325 → 3329 → 3333 → 3337 → **3339**（N3/D1 因本篇与 R239
  回填 +2）。
- **回填**：R239 §6（run `42739513195` / bot `0e4f434`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 四账审计（R237–R240）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R237 / R238 / R239 / R240 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R237–R240 四条专述 bullet，H2「至 R240」 | 齐 |
| 判据台账 | §10.109（W61）/ §10.110（W62）/ §10.111（W63）/ §10.112（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R240（main、用例数、写回 80/80、R241–R244 登记） | 齐 |

三轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R237 | replace workflow provenance 步 env 定义 == os.environ 消费（W61） | 3329 | 4/4 | 第 80 条 |
| R238 | replace workflow 资产目录名四源同账（W62） | 3333 | 4/4 | 第 80 条 |
| R239 | replace 下载清单 ↔ 两 producer artifact 名同账（W63） | 3337 | 4/4 | 第 80 条 |
| R240 | 收口 + R241–R244 登记 | 3339 | — | 第 80 条（本篇） |

## 3. 下一轮候选（R241–R244：全部先实测后登记）

- **R241 workflow 路径字面多源同账（W64）**：实测三份 desktop workflow
  对 `.github/workflows/*.yml` 的字面引用恰 **5 处**——desktop-windows.yml
  的 paths 自引用（L12 `- ".github/workflows/desktop-windows.yml"`）与
  可复用调用（L150 `uses: ./.github/workflows/desktop-macos.yml`）、
  desktop-macos.yml 的 paths 自引用（L9）、replace-desktop-assets.yml
  provenance 元组的两个 `run['path']` 期望值（L43/L45）。W32 只钉
  `desktop/scripts/*` 引用面（17 处），workflow 路径这一族无锚：
  文件改名 / 引用改名而对面没跟 → `run['path']` 校验在应急通道当场
  失败、可复用 workflow 起不来。判据方向：自引用 == 自身文件名；
  全部引用逐处可解析；replace 元组两路径 ↔ 平台 ↔ 该文件恰 1 个
  artifact 模板（与 W63 的模板互锚）。
- **R242 desktop-windows 编排 needs/uses ↔ job 键同账（W65）**：实测
  jobs = {push, build, build-macos, release}，release 的
  `needs: [build, build-macos]`（L155），build-macos 的
  `uses: ./.github/workflows/desktop-macos.yml`（L150），后者 job 集
  = {build}。needs/uses 写错 job 名或文件而没人判：GitHub 解析期
  就拒绝**整个** workflow（推 tag 时常规发版全断）。判据方向：
  needs 名字集合 ⊆ jobs 键集合、uses 目标可解析、被调 workflow 的
  job 键 == 调用方引用的 job 名（build-macos ↔ build）。
- **R243 build-runs.json 写读同账（W66）**：实测 provenance 步
  `Path('build-runs.json').write_text(...)`（L60）与 release 步
  `json.loads(Path('build-runs.json').read_text())`（L100）两处字面
  同账；provenance dict 的 `'build_runs'` 键（L100）消费该文件。
  写读改名而对面没跟 → release 步 FileNotFoundError（发版第 2 步
  中断）；平台键集合（records 的键 = 元组第一元素 {windows,macos}）
  漂移则审计面少平台。判据方向：写读两处恰各 1、路径逐字恰等、
  平台字面集合 == 元组平台集合、'build_runs' 键恰 1。
- **R244 收口轮（R241–R244 四账）+ 登记 R245–R248**：四账审计 +
  下一批主题实测登记（登记时先实测）。

## 4. 验证

- 无新判据，无新用例。定向回归（S1–S6、L1–L8、N1–N3、B1–B2、D1–D2、
  P1–P10、V1–V8、W1–W63、M1–M5）全绿。
- 本机全量：**3310 passed / 28 skipped / 0 failed**（3339 条，
  约 10m06s；S4 体量行在全量树上是约定的最后一步翻正，重算后
  复跑绿）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148/R156/R160/
  R164/R168/R172/R180/R184/R188/R192/R196/R200/R204/R208/R212/R216/
  R220/R224/R228/R232/R236 同型）。
- R237–R239 三条判据全部「钉住本来就对的账」，三轮变异合计 12/12；
  W63 的「M1 模板改名天然双红」（模板形状守卫与展开恰等同时断）是
  本批的形状校准。
- 实测观察（不当缺口修，沿 R216/R220/R224/R228/R232/R236 §5，仍
  成立）：desktop 代码版本五源 1.0.2 而 release-notes 最新 v1.1.1——
  tag 驱动发版的设计语义，需维护者拍板。
- 四轮连推（二十九）R237–R240 全部落地；下一批 R241–R244 已登记。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：R240 文档、R239 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R240 一条）、
  `JUDGEMENT_LEDGER.md`（§10.112）。生产代码与测试零改动。
- `config/skills_config.json` 不纳入（C1）。
