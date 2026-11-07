# DeterminFlow (xs2) 交接报告 — Round 196（收口轮：R193–R196 四账 + R197–R200 登记）

> 单 profile。四轮连推（十八）收口轮：四账审计 + 下一批主题实测登记。
> 本轮无新判据。R193–R195 三条判据全部落地（W28 / W29 / W30），两处
> 真实不一致修复（README 工作流名、README R2 凭据清单），生产代码
> 零改动。

## 1. 一句话结论

- R193–R195 全部完成：R193 desktop README 工作流名同账（W28，README
  `Desktop macOS candidate` 修为 `Desktop macOS`）；R194 flavor 词表
  五源闭包（W29，开工实测补 verify_bundle 第五源）；R195 README R2
  分发凭据同账（W30，「只通过」清单补 `R2_PUBLIC_BASE_URL`）。
- 三轮变异合计 **9/9**（R193 3 + R194 3 + R195 3；R196 收口轮无新
  判据，无变异面）。
- §3 登记 **R197–R200**（全部先实测后登记）：R2 公网回落域名三源同账
  （W31）、desktop workflow 脚本引用路径逐处可解析（W32，17 处 /
  9 脚本）、README R2 发行路径 ↔ publish_r2_release.py 两段同账（W33）、
  收口。
- 总用例 3175 → 3179 → 3183 → **3185**（N3/D1 因本篇与 R195 回填 +2）。
- **回填**：R195 §6（run `42375361386` / bot `f6dab64`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 四账审计（R193–R196）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R193 / R194 / R195 / R196 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R193–R196 四条专述 bullet，H2「至 R196」 | 齐 |
| 判据台账 | §10.65（W28）/ §10.66（W29）/ §10.67（W30）/ §10.68（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R196（main、用例数、写回 80/80、R197–R200 登记） | 齐 |

三轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R193 | desktop README 工作流名同账（W28，含一行修复） | 3175 | 3/3 | 第 80 条 |
| R194 | desktop flavor 词表五源闭包（W29） | 3179 | 3/3 | 第 80 条 |
| R195 | README R2 分发凭据同账（W30，含清单修复） | 3183 | 3/3 | 第 80 条 |
| R196 | 收口 + R197–R200 登记 | 3185 | — | 第 80 条（本篇） |

## 3. 下一轮候选（R197–R200：全部先实测后登记）

- **R197 R2 公网回落域名三源同账（W31）**：实测 `${{ vars.R2_PUBLIC_BASE_URL
  || 'https://downloads.determinflow.com' }}` 回落缺省在
  `desktop-windows.yml` 与 `replace-desktop-assets.yml` 各恰一处（R46
  注释自declared「与 replace-desktop-assets.yml 同款，便于改域名时不改
  代码」，但两处漂移无人判）；R195 修复后 README 也带回落说明
  （`未设置时回落 https://downloads.determinflow.com`，恰一处）——三源
  现同值。判据方向：三源回落域名字面值逐字恰等 + `--public-base-url`
  消费点存在（两 workflow 各恰一处）；任一处改域名而其余未跟显式红。
  未设变量时的行为不变由 CI 负责（不判回落触发逻辑）。
- **R198 desktop workflow 脚本引用路径逐处可解析（W32）**：实测三份
  desktop workflow 共 **17 处** `desktop/scripts/*` 引用 / **9 个不同
  脚本**（desktop-windows.yml 8：refresh_official_plugin_lock /
  build_backend / smoke_backend / verify_bundle ×2 / smoke_installer.ps1 /
  create_update_manifest / publish_r2_release；desktop-macos.yml 8：
  install_macos_build_dependencies / refresh_official_plugin_lock /
  build_backend / smoke_backend ×3 / generate_macos_icon /
  verify_bundle；replace-desktop-assets.yml 1：publish_r2_release）
  ——全部在磁盘。V8 管的是 README 侧命令引用面，workflow 侧没有锚：
  脚本改名/挪走时 CI 在 run 时才炸。判据方向：17 处逐处按仓库根解析后
  在磁盘 + 每份 workflow 引用数语料守卫（8/8/1），解析不到显式红。
- **R199 README R2 发行路径 ↔ publish_r2_release.py（W33）**：实测
  README「桌面更新发布」节写「先上传并公开校验 `desktop/releases/vX/`
  下的不可变资产，最后更新 `desktop/stable/latest.json`」，脚本
  `publish_r2_release.py` 的 `version_prefix = f"desktop/releases/v{version}"`
  （L159）与 `publish_latest(manifest_path, "desktop/stable/latest.json")`
  （L191）是同一份账的实现侧——README 的 `vX` 形状对脚本的
  `v{version}` 前缀、稳定清单键逐字同账。判据方向：两段路径前缀
  （`desktop/releases/` / `desktop/stable/latest.json`）双向同账，
  改键名/改目录而 README 没跟显式红。
- **R200 收口轮（R197–R200 四账）+ 登记 R201–R204**：四账审计 +
  下一批主题实测登记（候选面已见 `replace-desktop-assets.yml` 期望资产
  词表 ↔ desktop-windows NSIS 后缀对 / build_macos DMG 后缀对的三源
  产物名词表，登记时先实测）。

## 4. 验证

- 无新判据，无新用例。定向回归（S1–S6、L1–L8、N1–N3、B1–B2、D1–D2、
  P1–P10、V1–V8、W1–W30、M1–M5）全绿。
- 本机全量：**3157 passed / 28 skipped / 0 failed**（3185 条，
  约 10m40s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148/R156/R160/
  R164/R168/R172/R180/R184/R188/R192 同型）。
- R193–R195 三条判据全部「钉住本来就对的账」（修复后），四轮变异合计
  9/9；R192 登记阶段抓到的两处真实不一致（工作流名、R2 清单）分别在
  R193/R195 落地修复——候选制实测先行连续第三批收口闭环。
- R194 登记四处、开工实测补 verify_bundle.py 第五源（W18/W13/W25
  同型的实测补面）；W30 的清单句形状守卫是「集合同账抓不到的复制/
  改写」的显式红。
- 四轮连推（十八）R193–R196 全部落地；下一批 R197–R200 已登记。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：R196 文档、R195 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题/批次行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R196
  一条）、`JUDGEMENT_LEDGER.md`（§10.68）。生产代码与测试零改动。
- `config/skills_config.json` 不纳入（C1）。
