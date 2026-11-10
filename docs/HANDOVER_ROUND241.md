# DeterminFlow (xs2) 交接报告 — Round 241（冻结收口：W64/W65/W66 落地 + R242–R244 并入）

> 单 profile。四轮连推（三十）的合并收口轮：维护者拍板 R242–R244 不再
> 单独成轮，三条判据与冻结决策一并落地。三条判据全部「钉住本来就对的
> 账」（无修复），生产代码零改动，变异合计 12/12。本轮之后维护迭代
> 冻结：不再新增「同账」判据，只在回归红时修复。

## 1. 一句话结论

- **W64**：三份 desktop workflow 对 `.github/workflows/*.yml` 的字面引用
  恰 **5 处**——两个 `paths` 自引用、一个本地 `uses:`、replace 元组的
  两条 `run['path']` 期望。判据钉住：自引用 == 自身文件名、逐处可解析、
  元组路径 ↔ 平台 ↔ 该 producer 恰 1 个非诊断 artifact 模板。
- **W65**：desktop-windows 的 job 键恰 3 个（`build` / `build-macos` /
  `release`）；`release.needs` ⊆ jobs 且 == `{build, build-macos}`；
  `build-macos` 的 `uses` 目标可解析、声明 `workflow_call`、job 键恰 1 个
  且调用方 job 名 == 目标 job 键 + 平台 token；uses-job 与
  `runs-on`/`steps` 互斥。
- **W66**：`build-runs.json` 的写读两处字面逐字恰等；平台集合 ==
  `{windows, macos}`；release 步的 `build_runs` 消费表达式逐字匹配。
- 变异 **12/12**（W64 4 + W65 4 + W66 4）；总用例 3,339 → **3,347**
  （三条判据 +6、N3/D1 因本篇与 R240 回填 +2）。
- **冻结决策**（维护者拍板）：本批为维护迭代最后一轮；R242–R244 并入
  本轮（§5），此后不再造新判据。

## 2. 三条判据

### 2.1 W64 workflow 路径字面多源同账

`tests/test_desktop_workflow_path_refs.py`。实测 5 处引用的分布：

| 文件 | 位置 | 形态 |
|---|---|---|
| desktop-windows.yml | L12 | `on.push.paths` 自引用 |
| desktop-windows.yml | L150 | `uses: ./.github/workflows/desktop-macos.yml` |
| desktop-macos.yml | L9 | `on.pull_request.paths` 自引用 |
| replace-desktop-assets.yml | L43 | provenance 元组 windows 路径 |
| replace-desktop-assets.yml | L45 | provenance 元组 macos 路径 |

- **W64a 语料守卫**：三份文件引用总数恰 5；路径条目恰 2、本地 `uses:`
  恰 1、元组路径恰 2。
- **W64b 多源同账**：自引用 == 自身文件名；全部引用逐处可解析；被引用
  集合 == 两个 producer；元组的两条路径 ↔ 平台（`desktop-<platform>.yml`）
  ↔ 该 producer 恰 1 个非诊断 artifact 模板（模板小写含平台名）。

W32 只钉 `desktop/scripts/*` 引用面（17 处），workflow 路径这一族此前
无锚：文件改名而 `run['path']` 校验没跟 → 应急通道当场
`build must be successful and match exact source/workflow`；可复用
workflow 改名 → 调用起不来。

### 2.2 W65 needs/uses ↔ job 键同账

`tests/test_desktop_windows_needs.py`。desktop-windows.yml 的编排面：
jobs = `{build, build-macos, release}`；`release.needs = [build,
build-macos]`；`build-macos.uses = ./.github/workflows/desktop-macos.yml`，
后者声明 `workflow_dispatch` / `workflow_call` / `pull_request`，job 键
恰 `{build}`。

- **W65a 语料守卫**：job 键恰 3、`needs` 恰 2 项、本地 `uses` 恰 1 处。
- **W65b 编排同账**：needs 名字集合 ⊆ job 键集合且不自指、且与登记的
  `{build, build-macos}` 恰等；uses 目标可解析、声明 `workflow_call`、
  目标 job 键恰 1 个；调用方 job 名 == 目标 job 键 + `-` + 平台 token
  （`build` + `-macos`）；uses-job 不得同时声明 `runs-on`/`steps`，普通
  job 两者都必须有。

needs 写错 job 名 / uses 指向不存在的文件 / 被调 workflow 没声明
`workflow_call`——三种漂移都会让 GitHub 在**解析期**拒绝整个 workflow，
推 tag 时常规发版全断，而此前仓库里没有任何判据把编排面与 job 键对账。

### 2.3 W66 build-runs.json 写读同账

`tests/test_desktop_build_runs_io.py`。provenance 步
`Path('build-runs.json').write_text(json.dumps(records))`（L60）与
release 步 `'build_runs': json.loads(Path('build-runs.json').read_text())`
（L100）两处字面同账；`records` 由元组的 `platform` 变量填充，最终落进
`build-source.json` 的审计面。

- **W66a 语料守卫**：两个 heredoc；`write_text` 恰 1 处；release 步读回
  **本次写入的那个名字**恰 1 处（该步还读 `tauri.conf.json` /
  `official-plugins.lock.json`，不数进来）；`records` 的初始化 / 平台
  赋值 / 序列化各恰 1 处；`'build_runs'` 键字面恰 1 处。
- **W66b 写读同账**：写侧路径 == `build-runs.json`；读侧必须读回写入的
  同名文件（双向：谁改名都会表现为「没有一处读回这个名字」）；平台字面
  集合 == `{windows, macos}`；消费表达式逐字匹配。

写读改名而对面没跟 → release 步 `FileNotFoundError`（发版第 2 步中断）；
平台集合漂移 → 审计面少平台；`build_runs` 键改名 → 下游读者拿不到构建
run 账。

## 3. 变异（12/12）

| # | 变异 | 被咬的测试 |
|---|---|---|
| 1 | desktop-windows 自引用改名 | W64b |
| 2 | `uses` 目标改名 | W64b |
| 3 | 元组 windows 路径指向 macOS producer | W64b |
| 4 | 自引用条目复制 | W64a |
| 5 | `needs` 错拼 `build-x` | W65b |
| 6 | `uses` 指向不存在文件 | W65b |
| 7 | 被调 workflow 的 job 键 `build` → `compile` | W65b |
| 8 | uses-job 混入 `runs-on` | W65b |
| 9 | 写侧 `build-runs.json` → `build-runs2.json` | W66a + W66b（双红） |
| 10 | 读侧改名 | W66a + W66b（双红） |
| 11 | `build_runs` 键改名 | W66a + W66b（双红） |
| 12 | 平台字面 `windows` → `win` | W66b |

双红是同一份语料的两条断言（形状守卫按写入名过滤读取侧，写读对账也
按写入名判），不是判据串扰。

## 4. 验证

- 定向回归：三个新文件 6 条全绿；文档门禁（N1–N3、L1–L8、S1–S6、
  D1–D2、B1–B2）全绿。
- 本机全量（初跑）：**3316 passed / 28 skipped / 3 failed**（3,347 条，约
  8m41s）。三条失败逐条归因：
  - `test_judgement_ledger.py::test_ledger_has_no_placeholder_rows`——本轮
    台账初稿把「待办标记」写成字母缩写，撞上该判据的占位符黑名单；已改写
    措辞，定向复跑绿。
  - `test_memory_extract.py::test_format_correction_shares_one_timeout_budget`
    ——时间敏感：0.05s 预算对每次 0.03s 的桩 LLM，全量树负载下超时；单跑
    必绿，与本轮改动无关（memory 抽取路径零改动）。
  - `test_plugin_store.py::test_symlink_cannot_escape_checked_out_package`
    ——本机 `core.symlinks=false`（见 §5）：git 检出把符号链接写成普通
    文件，store 自然判不到 symlink；CI 两个 runner 上为绿。
- 修复后全量复跑：**3318 passed / 28 skipped / 1 failed**（3,347 条，
  8m32s），仅剩本机 `core.symlinks` 那条。
- 变异：12/12（§3）。

## 5. 边界与遗留

- **冻结**：维护者拍板——本批为维护迭代最后一轮。此后不再新增
  「同账」判据；只在回归红时修复。理由见本轮判断：应用代码（`src/`、
  `web/src`、`desktop/src-tauri/src`）自 R66 起零改动（`scripts/` 的最后
  改动在 R155）、`src/` 的待办标记计数为 0、原始缺陷债（B1–B27）清空，
  边际收益已接近零。
- **R242–R244 并入本轮**：三条判据原登记为 R242（W65）/ R243（W66），
  与 R241（W64）同批；R244 原为收口轮。合并后一次落地、一次回填，避免
  三轮纯文档 CI。台账 §10.116 记录这次合并。
- **写回行的终态**：CI 的 `e2e-history-writeback` 在每次 main push 上都
  追加一条历史；冻结后没有「下一轮」来翻正索引 §1 的写回/基线两行。
  本轮因此以一次**纯文档回填提交**收尾，提交信息带 `[skip ci]`——回填
  提交自己不再触发写回，S2/S5 才能停在一致态。
- **仍未闭合的产品项**：R241 §8 已由维护者拍板并落地（R2 公网域
  fail-closed、发行线归位、macOS 自动更新明确不做）；剩下的是需要外部
  账号/预算的两项——Apple Developer ID 签名与公证、macOS 自动更新的
  更新产物链路（后者已拍板不做）。
- `config/skills_config.json` 保持未提交（C1）。
- 生产代码零改动；测试只新增三个文件（§8 另改了一条既有判据的语义）。

## 6. CI

- 提交 **`345da0a`** 推送后 run **42753616716**：**10 job 全
  `success`**（04:05:41→04:23:50 UTC，约 18m09s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42753616716`，bot 提交 **`d9a0181`**）。
- 终态回填：本篇 §6 与索引 §1 的写回/基线两行由一次纯文档回填提交
  补齐，提交信息带 `[skip ci]`——冻结后没有下一轮，回填提交自己不能再
  触发写回，否则账目永远追不上自己。

## 7. 提交

- 改动：`tests/test_desktop_workflow_path_refs.py`、
  `tests/test_desktop_windows_needs.py`、
  `tests/test_desktop_build_runs_io.py`、本篇、`PROJECT_INFO.md`
  （H2 + 一条专述）、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 + §4 一行
  + §6.1）、`JUDGEMENT_LEDGER.md`（§10.113–§10.116）、R240 §6 回填。
- 生产代码零改动；`config/skills_config.json` 不纳入（C1）。

## 8. 拍板落地（冻结后补丁，同轮记录）

冻结声明之后，维护者对「待拍板产品项」逐项给了结论并授权落地。本节
记录**决定与改动**，不再开新轮次、不新增判据号（W31 是同号改判）。

### 8.1 R2 公网域：改为未设即失败

**决定**：禁止任何内置回落域名，`R2_PUBLIC_BASE_URL` 未设置时发布
步骤直接失败。

**依据（实测）**：`https://downloads.determinflow.com/desktop/stable/
latest.json` 返回 **200 且 version=1.1.1**——那是**上游**的稳定清单，
本 fork 是 1.0.2。旧写法 `${{ vars.R2_PUBLIC_BASE_URL ||
'https://downloads.determinflow.com' }}` 会在「启用 R2 但漏配变量」时
把清单 URL 发到上游域名上，客户端用本 fork 公钥验签必败。

**改动**：`desktop-windows.yml` / `replace-desktop-assets.yml` 去掉
回落缺省、加 `-z "$R2_PUBLIC_BASE_URL"` 显式守卫；`desktop/README.md`
改为「必须显式设置」；`tests/test_desktop_r2_fallback_domain.py` 的
**W31 同号改判**（原「三源回落同值」→ 现「无缺省 + fail-closed +
发布面不得出现上游域名」）。脚本侧 `--public-base-url` 本来就是
`required=True`，未改。

### 8.2 发行线归位：上游日志归档

**决定**：`desktop/release-notes/` 只保留本 fork 发行线
（v1.0.0–v1.0.2）；上游 v1.0.3–v1.1.1 归档到
`desktop/release-notes/upstream/`（附 `README.md` 说明不属于本 fork
发行线）。

**依据（实测）**：代码五源全 1.0.2、GitHub 只有 v1.0.0/1/2 三个
release；上游 10 份日志的入库日期是 2026-08-04～09-11，早于本 fork
首版（2026-10-24）。`docs/community-updates.md` 却写「当前正式版
v1.1.1」，并被 W52 钉成「== release-notes 目录最高版」——文档因此
长期指向本 fork 不存在的版本。

**改动**：10 个文件 `git mv` 到 `upstream/`；`community-updates` 的
「当前正式版」改 **v1.0.2**（历史链接改 v1.0.1），并加一段「以下为
上游社区版记录」的边界说明；`test_community_public_boundary.py` 的
`v1.0.9.md` 路径随迁。W52/W36 的判据语义不变（目录最高版与引用最高
版现在都落在 1.0.x，自动同账）。

### 8.3 macOS：明确不做自动更新

**决定**：macOS 维持 ad-hoc 签名 + 手动 DMG 升级；自动更新列为明确
不做项，直到有 Developer ID 签名与公证链路。

**依据（实测）**：`latest.json` 只有 `windows-x86_64` 一个平台；
`desktop-macos.yml` 用 `createUpdaterArtifacts=false` 且
`verify_bundle.py --forbid-updater-artifacts` 显式禁止 updater 产物。
现状与决定一致，差的是文档把「怎么做」写清。

**改动**：`desktop/README.md` 的 macOS 节补一句「不提供自动更新，
升级即手动下载新 DMG 覆盖安装；R241 拍板列为明确不做项」。

### 8.4 记录纠错

`PROJECT_INFO.md` 开头「上游桌面发布管线」一段的「`endpoints` 仍指向
上游 latest.json、自动更新安全失效」是 2026-10-24 的旧结论；R29
（`2938a82`）已切回本 fork，实测 200 且清单 1.0.2。本次按实测更正，
并在 §5 撤掉同一错误表述。

**验证**：R2 四判据（W30/W31/W35/W43）与发行线三判据（W36/W52/公共边界）全绿；
全量 **3319 passed / 28 skipped / 0 failed**（3,347 条，8m59s，按 CI 口径 `core.symlinks=true` 跑）。

**补丁 CI**：提交 **`2aecea6`** 推送后 run **42788139632**：**10 job 全
`success`**（09:08:07→09:26:06 UTC，约 17m59s），写回第 80 条
（`ci-42788139632`，bot **`ec029b1`**）；同次推送触发的
**Desktop Windows** run **42788139922** 亦 success（core/full 两条 NSIS，
非 tag 故 release job 跳过）。

## 9. 发版 v1.0.3（同轮记录）

维护者拍板「发布最新版本」后按 `docs/RELEASE_SOP.md` 落地。自 v1.0.2
（2026-10-25）起有 **22 个应用代码提交**（R43–R66：运行画像、失败率
画像、幻影目录与 404/422 修复等），因此按补丁版递增为 **v1.0.3**。

- **升版本六处**：`tauri.conf.json` / `desktop/package.json` /
  `Cargo.toml` / `Cargo.lock`（`determinflow-desktop` 条目）/
  `official-plugins.lock.json` 的 `desktop_version` /
  `tests/test_desktop_packaging.py` 的发版钉值。另同步
  `desktop/README.md` 的 DMG 示例名（W23 型钉值会在升版时先红，实测
  抓到 1 处）。
- **发行说明**：新增 `desktop/release-notes/v1.0.3.md`；
  `docs/community-updates.md` 的「当前正式版」改为 v1.0.3、
  历史链接改 v1.0.2（W52/W36 随目录最高版自动同账）。
- **提交**：`74e8a96` → push main，CI run **42803089035**：10 job 全
  `success`（10:54:39→11:12:35 UTC，约 17m56s），bot **`56fd925`**。
- **tag**：`v1.0.3` → Desktop Windows run **42803095432**：core/full
  NSIS + macOS core/full DMG 全 `success`，release job 于
  **2026-11-10T11:07:52Z** 创建并发布 GitHub Release。
- **资产（11 个）**：`DeterminFlow_1.0.3_{x64,x64-full}-setup.exe`
  及 `.sig`/`.sha256`、`DeterminFlow_1.0.3_{aarch64,aarch64-full}.dmg`
  及 `.sha256`、`latest.json`。
- **清单复核**：`latest.json` 的 `version=1.0.3`、
  `windows-x86_64` 的 URL 指向 v1.0.3 资产、`signature` 424 字符
  （与 `.sig` 同长）。
- **R2 步骤 skipped**（`R2_DISTRIBUTION_ENABLED` 未开）：本轮新增的
  fail-closed 守卫未触发，发布未受影响；这也再次印证第 8.1 节的
  判断——R2 通道当前是休眠路径。
