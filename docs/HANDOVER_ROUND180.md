# DeterminFlow (xs2) 交接报告 — Round 180（收口轮：R177–R180 四账 + R181–R184 登记）

> 单 profile。四轮连推（十四）收口轮：四账审计 + 下一批主题实测登记。
> 本轮无新判据。R177–R179 三条判据全部落地（P10 / V7 / W19），其中
> P10 第一次在实测阶段抓到真实不一致并修复；生产代码仅
> `scripts/check_environment.py` 一处。

## 1. 一句话结论

- R177–R179 全部完成：R177 环境检查脚本 ↔ 支持面下限（P10，含 Node
  18→22.12 修复）；R178 文档 npm 命令引用面（V7）；R179 desktop 默认
  配置覆盖（W19）。
- 三轮变异合计 **9/9**（R177 3 + R178 3 + R179 3 + R180 0——收口轮无
  新判据，无变异面）。
- §3 登记 **R181–R184**（全部先实测后登记）：macOS 最低版本同账
  （W20）、desktop 管线命令引用面（V8）、前端构建输出目录同账
  （W21）、收口。
- 总用例 3115 → 3119 → 3123 → 3127 → **3129**（N3/D1 因本篇与 R179
  回填 +2）。

## 2. 四账审计（R177–R180）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R177 / R178 / R179 / R180 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R177–R180 四条专述 bullet，H2「至 R180」 | 齐 |
| 判据台账 | §10.49（P10）/ §10.50（V7）/ §10.51（W19）/ §10.52（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R180（main、用例数、写回 80/80、R181–R184 登记） | 齐 |

三轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R177 | 环境检查脚本 ↔ 支持面下限（P10） | 3119 | 3/3 | 第 80 条 |
| R178 | 文档 npm 命令引用面（V7） | 3123 | 3/3 | 第 80 条 |
| R179 | desktop 默认配置覆盖（W19） | 3127 | 3/3 | 第 80 条 |
| R180 | 收口 + R181–R184 登记 | 3129 | — | 第 80 条（本篇） |

## 3. 下一轮候选（R181–R184：全部先实测后登记）

- **R181 macOS 最低版本同账（W20）**：实测 `11.0` 共 **6 处 / 4 个
  文件**——`desktop/src-tauri/tauri.macos.conf.json` 的
  `minimumSystemVersion`、`desktop/scripts/verify_bundle.py` 的
  `MINIMUM_MACOS_VERSION`、`.github/workflows/desktop-macos.yml` 的
  `MACOSX_DEPLOYMENT_TARGET`、`desktop/README.md` 3 处（架构行
  `macOS 11.0+` 与两条构建命令的 `MACOSX_DEPLOYMENT_TARGET=11.0`）。
  改最低版本要动四处源码/文档；漏改 `verify_bundle` 会让正确的 bundle
  被判失败，漏改 workflow 会让构建目标仍是旧系统，漏改 README 则文档
  失真。desktop-macos workflow 只在 `desktop/**` PR 触发，纯文档改动
  不会被它咬住。判据方向：六处逐字相等 + 形状守卫 + 每个源至少一处。
- **R182 desktop 管线命令引用面（V8）**：实测 `desktop/README.md` 的
  fenced 代码块有 **8 处** `python desktop/scripts/*.py` 引用
  （stage_defaults / build_backend / smoke_backend ×2 / verify_bundle ×2
  / install_macos_build_dependencies / generate_macos_icon）与 **3 处**
  `npm run` / `npm test`（build / test / build:macos）+ **2 处**
  `npm ci`，全部可解析；`desktop/package.json` 的 `test` →
  `ui/desktop-adapter.test.mjs`、`build:macos` →
  `scripts/build_macos.py` 也都在磁盘。发布文档是 full 包唯一的人读
  构建说明，CI 从不执行它。判据方向：V8a 语料守卫（≥8 脚本引用 /
  ≥3 npm run/test / ≥2 npm ci）+ V8b 脚本、npm script 与锁文件逐项
  可解析。
- **R183 前端构建输出目录同账（W21）**：实测 `web/vite.config.ts` 没有
  `build.outDir`（Vite 默认 `dist`），`run.py` 的
  `dist_dir = web_dir / "dist"` 与 `src/web_server.py` 的
  `BASE_DIR / "web" / "dist"` 都指向 `dist`。三处当前同账但无人判：给
  Vite 加 `build.outDir: "public"` 后，`run.py` 每次启动都会重新构建、
  `web_server` 挂载不到产物——frontend job 只跑 `npm run build`，不会
  走 `run.py`。判据方向：从 Vite 配置取有效 `outDir`（显式或默认），
  与两处后端路径逐字相等；每侧恰一处。
- **R184 收口轮（R181–R184 四账）+ 登记 R185–R188**：四账审计 +
  下一批主题实测登记。

## 4. 验证

- 无新判据，无新用例。定向回归（S1–S6、L1–L8、N1–N3、B1–B2、D1–D2、
  P1–P10、V1–V7、W1–W19、M1–M5）全绿。
- 本机全量：**3101 passed / 28 skipped / 0 failed**（3129 条，约
  10m40s）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148/R156/R160/
  R164/R168/R172 同型）。
- R177–R179 三条判据：P10 是候选制第一次「钉出真实不一致」并带生产
  脚本修复；V7/W19 仍是「钉住本来就对的账」。四轮变异合计 9/9。
- 四轮连推（十四）R177–R180 全部落地；下一批 R181–R184 已登记。
- 生产默认值不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：R180 文档、R179 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1
  + §3 标题/一行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R180
  一条）、`JUDGEMENT_LEDGER.md`（§10.52）。生产代码与测试零改动。
- `config/skills_config.json` 不纳入（C1）。
