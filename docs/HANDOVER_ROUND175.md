# DeterminFlow (xs2) 交接报告 — Round 175（desktop 版本五源同账：W18）

> 单 profile。四轮连推（十三）第 3 轮：桌面发布版本线第一次做多源
> 同账。登记时只数到两处，开工实测按 `RELEASE_SOP` §1 补齐到五份
> 真实清单；生产代码零改动。W18 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：桌面版本线是独立的 1.0.x（核心是 0.1.0）。按
  `docs/RELEASE_SOP.md` §1 的六处清单，真实版本文件有 **五份**——
  `desktop/src-tauri/tauri.conf.json`、`desktop/src-tauri/Cargo.toml`、
  `desktop/src-tauri/Cargo.lock`、`desktop/package.json`、
  `desktop/official-plugins.lock.json`（`desktop_version`），当前全为
  **1.0.2**；第六处是发版钉值测试。
- `tests/test_version_sources.py` 新增 **W18a/W18b**：五源形状守卫 +
  逐字同账；`RELEASE_SOP` §1 清单与五源集合恰等。总用例
  3107 → **3111**（+2 钉测、+1 N3 本篇、+1 D1 因 R174 进入扫描区间）。
- 变异 **3/3**：tauri 形状 1.0 / Cargo.lock 1.0.1 / SOP 删
  Cargo.lock 行，W18a 与 W18b 各自独红。
- **收编**：`test_desktop_versions_are_consistent` 原来的三源裸断言
  由 W18 接管，原测试只保留 SOP 第六处的「当前发布版本 = 1.0.2」
  钉值，并改名为 `test_desktop_release_version_is_pinned`。

## 2. 为什么是这一轮

R161 的 W12 只钉核心版本线（`pyproject.toml` == `web/package.json`，
0.1.0）；桌面是**独立的发布版本线**（1.0.x）。Tauri 打包读
`tauri.conf.json`、Rust 构建读 `Cargo.toml`/`Cargo.lock`、npm 清单读
`desktop/package.json`、full 构建的插件锁读 `official-plugins.lock.json`
的 `desktop_version`（`load_official_plugin_lock` 硬校验）。任一处
漏改，安装器、关于页与插件锁会各说各话：Updater 按 tauri 版本判新旧，
Rust 二进制按 Cargo 版本自述，full 包按插件锁决定捆绑快照。

R172 §3 登记时只数到 `desktop/package.json` 与 `tauri.conf.json` 两处，
且没注意到 `test_desktop_packaging.py` 已有一组裸断言（含硬编码
1.0.2）。开工实测按 SOP §1 补齐到五份真实清单，并把裸断言收编进
W18——这是候选制第三次在「开工实测」阶段修正判据自己的覆盖面
（W13 补 run.py/.env.example、M5 补 GitHub Actions badge、W18 补
Cargo.toml/Cargo.lock/插件锁）。

## 3. 实现

### 3.1 `tests/test_version_sources.py`（W18a / W18b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W18a | 五份清单都能解析出 `X.Y.Z` 形状的版本；`RELEASE_SOP` §1 表格恰好列出五份清单 + 发版钉值测试 | 五个 `version`/`desktop_version` 字段 + SOP 表首列路径 |
| W18b | 五份清单的版本逐字相等（锚 = `tauri.conf.json`） | 同上 |

实现要点：

- `Cargo.lock` 用 `tomllib` 找 `[[package]] name = "determinflow-desktop"`
  条目，要求恰一处；不扫传递依赖的版本。
- `official-plugins.lock.json` 的键是 `desktop_version`，不是
  `version`——读取时显式传 key。
- SOP 表首列用 `^\|\s*`([^`]+)`\s*\|` 提取，集合相等而不是包含：
  新增/删除版本文件时表与判据必须同改，否则 W18a 显式红。
- 桌面版本与核心版本**不比较**：1.0.x 与 0.1.0 是两条独立版本线。

### 3.2 收编现有裸断言

`tests/test_desktop_packaging.py` 的
`test_desktop_versions_are_consistent` 原来同时断言
`tauri == "1.0.2"`、`package == tauri`、`Cargo.toml` 含同一版本。
三源同账交给 W18b 后，该测试改名为
`test_desktop_release_version_is_pinned`，只保留 SOP 第六处的发布
钉值（`tauri["version"] == "1.0.2"`）——避免同一条账被两个测试
各钉一次。`RELEASE_SOP` §1 的第六行同步改名，并注明前五处由 W18
机判。

## 4. 验证

- 定向：`tests/test_version_sources.py` **3 passed**（W12 + W18a/W18b）；
  关联四文件（版本 / 桌面打包 / 插件锁 / SOP 契约）45 passed / 1 skipped
  （macOS icon 生成按平台跳过）。
- 本机全量：**3083 passed / 28 skipped / 0 failed**（3111 条，约 10 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 tauri `"version": "1.0.2"`→`"1.0"` | W18a 红（形状），W18b 红（锚漂移） |
| M2 Cargo.lock 根包 `1.0.2`→`1.0.1` | W18b 独红，W18a 绿 |
| M3 `RELEASE_SOP` §1 删除 Cargo.lock 行 | W18a 独红，W18b 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判版本字段：不判版本递增语义（发版 tag 与 `RELEASE_SOP` §3
  负责）、不判 release-notes 文件名与历史文档里的旧版本字面、不判
  `tauri.macos.conf.json`（overlay 不含 `version`，继承主配置）。
- 不判 `Cargo.lock` 的传递依赖钉版（`Cargo.lock` 由 cargo 维护，
  W18 只钉根包自述版本）。
- 四轮连推（十三）下一轮 **R176 README 命令引用面（V6）**。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_version_sources.py`（W18）、
  `tests/test_desktop_packaging.py`（收编为发布钉值）、
  `docs/RELEASE_SOP.md`（§1 第六行改名 + W18 注记）、R175 文档、
  R174 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R175 一条）、
  `JUDGEMENT_LEDGER.md`（§10.47）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
