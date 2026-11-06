# DeterminFlow (xs2) 交接报告 — Round 186（desktop README DMG 产物路径同账：W23）

> 单 profile。四轮连推（十六）第 2 轮：发布文档里硬编码的 DMG 产物名
> 第一次与构建模板 / 版本源对账。生产代码与文档零改动；W23 首跑即过，
> 变异 3/3。

## 1. 一句话结论

- **实测**：`desktop/README.md` 的 macOS 验证命令硬编码
  `DeterminFlow_1.0.2_aarch64.dmg`（恰 1 处）；`desktop/scripts/build_macos.py`
  的产物模板是 `DeterminFlow_{version}_aarch64{suffix}.dmg`（恰 1 处），
  `version` 读自 `tauri.conf.json`（W18 五源之一，当前 `1.0.2`）。三处
  当前同账，但 README 的硬编码不在 W18 的五源清单里。
- `tests/test_desktop_dmg_reference.py` 新增 **W23a/W23b**：语料守卫
  （README 引用与模板各恰一处、形状完整、README 是 Core 后缀）+ 三处
  同账（版本 == tauri 版本、架构 == 模板架构）。总用例 3147 → **3151**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R185 进入扫描区间）。
- 变异 **3/3**：README DMG 版本改 `1.0.3`（W23b 红）、模板架构改
  `x86_64`（W23a+W23b 红）、tauri 版本改 `1.0.3`（W23b 红）。
- **回填**：R185 §6（run `42246512628` / bot `74aa21d`）与索引 §1 的
  写回 / 基线两行。

## 2. 为什么是这一轮

桌面版本升级时 W18 会要求五源同步（tauri / package / Cargo.toml /
Cargo.lock / official-plugins.lock + 发版钉值测试），但
`desktop/README.md` 的 macOS 验证命令里还有第六处版本——硬编码的
DMG 产物名。它不在五源清单里，W18 管不到；照文档执行本地验证的人会
拿到「文件不存在」，而 CI 从不执行 README 命令（与 V8 同一条边）。

产物名的三个自由度都要对账：**版本**（README == tauri）、**架构**
（README == 模板；改 universal / Intel 时模板先行）、**后缀**（README
引用的是 Core 产物，无 `-full`）。W23 把三处钉成同账。

## 3. 实现

### 3.1 `tests/test_desktop_dmg_reference.py`（W23a / W23b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W23a | README 恰 1 处 DMG 产物名引用、模板恰 1 处；版本 `X.Y.Z` 形状；README 架构 == 模板架构；README 无 `-full` 后缀 | README 正则 / 模板正则 |
| W23b | README 版本 == `tauri.conf.json` 的 `version`（W18 锚）；README 架构 == 模板架构 | 同上 + tauri JSON |

实现要点：

- README 的引用按完整产物名正则锚定
  （`DeterminFlow_<X.Y.Z>_<arch><-full?>.dmg`），改路径前缀不红、改
  文件名任一段才红。
- 模板按带引号的字面量锚定（`"DeterminFlow_{version}_<arch>{suffix}.dmg"`），
  改生成逻辑不误伤。
- 后缀守卫放在 W23a：README 的验证命令对应 `--flavor core`，引用
  `-full` 产物即红。

### 3.2 生产代码与文档

- 零改动：`desktop/README.md`、`build_macos.py`、`tauri.conf.json`
  都不动。

## 4. 验证

- 定向：`tests/test_desktop_dmg_reference.py` 2 passed。
- 关联面：`test_version_sources.py`（W18 五源）、
  `test_desktop_packaging.py`、`test_macos_minimum_version.py`、
  `test_macos_bundle_identifier.py` 全绿。
- 本机全量：**3123 passed / 28 skipped / 0 failed**（3151 条，约 10m33s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 README DMG 版本 `1.0.2`→`1.0.3` | W23b 红、W23a 绿 |
| M2 模板架构 `aarch64`→`x86_64` | W23a 红、W23b 红 |
| M3 tauri `version` `1.0.2`→`1.0.3` | W23b 红、W23a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（README /
tauri.conf 为 CRLF，build_macos.py 为 LF）。

## 5. 边界与遗留

- 只判 `desktop/README.md` 的 macOS 验证命令与 `build_macos.py` 模板：
  不判根 README / release-notes 的历史发版产物名（各版本史料）、不判
  Windows 安装包名、不判 DMG 是否真的构建出来。
- 四轮连推（十六）下一轮 **R187 desktop README macOS 候选范围 ↔
  workflow 矩阵（W24，含真实修复）**：表行「只构建 Core，不构建 Full」
  与 matrix `[core, full]` 已分叉，R187 先修文档再钉同账。
- 生产代码与文档零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_dmg_reference.py`（W23）、R186 文档、
  R185 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R186 一条）、
  `JUDGEMENT_LEDGER.md`（§10.58）。生产代码与文档零改动。
- `config/skills_config.json` 不纳入（C1）。
