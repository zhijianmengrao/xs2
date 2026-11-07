# DeterminFlow (xs2) 交接报告 — Round 192（收口轮：R189–R192 四账 + R193–R196 登记）

> 单 profile。四轮连推（十七）收口轮：四账审计 + 下一批主题实测登记。
> 本轮无新判据。R189–R191 三条判据全部落地（W25 / W26 / W27），
> 生产代码零改动。

## 1. 一句话结论

- R189–R191 全部完成：R189 desktop README 架构表路径同账（W25，四源
  含 main.rs 注入点）；R190 Windows 表 runner ↔ desktop-windows.yml
  首个 job（W26）；R191 README 表 ↔ tauri conf 打包三键（W27）。
- 三轮变异合计 **9/9**（R189 3 + R190 3 + R191 3；R192 收口轮无新
  判据，无变异面）。
- §3 登记 **R193–R196**（全部先实测后登记）：desktop README 工作流名
  同账（W28，**实测发现真实不一致**：README 写 `Desktop macOS
  candidate` 而 workflow `name:` 是 `Desktop macOS`）、flavor 词表
  四源闭包（W29）、README R2 分发凭据同账（W30，**实测发现真实不
  一致**：README 的「只通过…注入」清单漏 `R2_PUBLIC_BASE_URL`
  Variable）、收口。
- 总用例 3157 → 3161 → 3165 → 3169 → **3171**（N3/D1 因本篇与 R191
  回填 +2）。
- **回填**：R191 §6（run `42350304034` / bot `6a1a0f4`）与索引 §1 的
  写回 / 基线两行。

## 2. 四账审计（R189–R192）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R189 / R190 / R191 / R192 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R189–R192 四条专述 bullet，H2「至 R192」 | 齐 |
| 判据台账 | §10.61（W25）/ §10.62（W26）/ §10.63（W27）/ §10.64（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R192（main、用例数、写回 80/80、R193–R196 登记） | 齐 |

三轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R189 | desktop README 架构表路径同账（W25） | 3161 | 3/3 | 第 80 条 |
| R190 | Windows 表 ↔ desktop-windows.yml runner（W26） | 3165 | 3/3 | 第 80 条 |
| R191 | README 表 ↔ tauri conf 打包三键（W27） | 3169 | 3/3 | 第 80 条 |
| R192 | 收口 + R193–R196 登记 | 3171 | — | 第 80 条（本篇） |

## 3. 下一轮候选（R193–R196：全部先实测后登记）

- **R193 desktop README 工作流名同账（W28）**：实测 desktop/README.md
  「桌面更新发布」节写「macOS 候选由 `Desktop macOS candidate` 工作流
  生成」，而 `.github/workflows/desktop-macos.yml` 的 `name:` 是
  `Desktop macOS`——候选制第三次在登记阶段抓到真实不一致（前两次
  R177 P10、R187 W24），修复为 `Desktop macOS`。判据方向：README 中
  反引号引用的 desktop 工作流名必须 ∈ `.github/workflows/desktop-*.yml`
  的 `name:` 集合（现集合 {`Desktop macOS`, `Desktop Windows`}）；
  workflow 改名而 README 没跟、或 README 写出集合外的名，双向显式红。
  本仓桌面工作流只有这两个，词表守卫让新增/删除 desktop 工作流时先红
  在词表。
- **R194 flavor 词表四源闭包（W29）**：实测 flavor 词表共四处——
  `desktop/scripts/build_macos.py` 的 `choices=("core","full")` 与运行
  时集合、`desktop/scripts/build_backend.py` 的 `choices`、
  `desktop-macos.yml` 的 `matrix.flavor: [core, full]`、
  `desktop-windows.yml` 的 `matrix.flavor` 列表——四处现均为
  {core, full}。W24 只钉了 macOS 范围行与 macos 矩阵；Windows 矩阵与
  两个构建脚本的词表没有锚，加第三个 flavor 时四处会各自漂移。判据
  方向：四源解析出的词表集合恰等（任一处加减值显式红），解析不到
  显式红。
- **R195 README R2 分发凭据同账（W30）**：实测 README「桌面更新发布」
  节写「R2 凭据只通过 `R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY` Secret
  和 `R2_BUCKET`、`R2_ENDPOINT_URL` Variable 注入」，另有
  `R2_DISTRIBUTION_ENABLED=true` 与 `TAURI_SIGNING_PRIVATE_KEY` 两处
  提名；而 desktop 工作流实际消费 `secrets.R2_ACCESS_KEY_ID` /
  `secrets.R2_SECRET_ACCESS_KEY` / `secrets.TAURI_SIGNING_PRIVATE_KEY` /
  `vars.R2_BUCKET` / `vars.R2_ENDPOINT_URL` /
  `vars.R2_PUBLIC_BASE_URL` / `vars.R2_DISTRIBUTION_ENABLED` 七个名字
  ——README 的「只」清单漏 `R2_PUBLIC_BASE_URL`（带公网缺省值
  `https://downloads.determinflow.com`），这是候选制第四次实测抓到
  真实不一致，修复为把该 Variable 补进清单。判据方向：README 提名的
  R2/签名凭据名集合 == 三个 desktop 工作流（desktop-windows /
  desktop-macos / replace-desktop-assets）的 `secrets.*`/`vars.*` 引用
  名集合，双向恰等；`ci.yml` 无 `secrets.*`/`vars.*` 引用（实测）。
- **R196 收口轮（R193–R196 四账）+ 登记 R197–R200**：四账审计 +
  下一批主题实测登记。

## 4. 验证

- 无新判据，无新用例。定向回归（S1–S6、L1–L8、N1–N3、B1–B2、D1–D2、
  P1–P10、V1–V8、W1–W27、M1–M5）全绿。
- 本机全量：**3143 passed / 28 skipped / 0 failed**（3171 条，
  约 13m29s）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148/R156/R160/
  R164/R168/R172/R180/R184/R188 同型）。
- R189–R191 三条判据全部「钉住本来就对的账」，四轮变异合计 9/9；
  但收口登记阶段实测又抓到两处真实不一致（工作流名、R2 清单），
  都在 R193/R195 落地修复——候选制的实测先行连续第三批在登记阶段
  抓到真问题。
- W25 登记三锚、开工补 main.rs 注入点成四源（W18/W13/R175 同型）；
  W26 锚定 YAML 首个 job（`release` 的 `ubuntu-latest` 不进射程）；
  W27 的「安装包」行用 NSIS 前缀消歧（Windows 小节有两处
  `| 安装包 |` 形状）。
- 四轮连推（十七）R189–R192 全部落地；下一批 R193–R196 已登记。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`8793cf3`** 推送后 run **42352629011**：**10 job 全
  `success`**（07:45:56→08:01:23 UTC，约 15m27s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42352629011`，bot 提交 **`9429ee1`**）。R193 回填。

## 7. 提交

- 改动：R192 文档、R191 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题/批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R192
  一条）、`JUDGEMENT_LEDGER.md`（§10.64）。生产代码与测试零改动。
- `config/skills_config.json` 不纳入（C1）。
