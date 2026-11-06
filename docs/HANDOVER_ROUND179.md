# DeterminFlow (xs2) 交接报告 — Round 179（desktop 默认配置覆盖：W19）

> 单 profile。四轮连推（十四）第 3 轮：`config/*.json` 与桌面打包的
> staging 清单第一次做集合恰等。生产代码零改动；W19 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：`config/` 有 **15 个** JSON——`stage_defaults.py` 的
  `SOURCE_CONFIG_FILES` 10 个、`DESKTOP_OVERRIDES` 3 个
  （extensions / mcp_servers / plugin-sources）、models 派生对 2 个
  （`models_config.example.json` / `models_config.json`），三组互不重叠，
  并集恰好 15。`build_payloads` 与 `stage_defaults` 实际落盘的键/文件
  集合也都是这 15 个。
- `tests/test_desktop_defaults.py` 新增 **W19a/W19b**：集合恰等 + 三组
  不重叠 + 语料守卫；真实 `build_payloads` / `stage_defaults` 的落盘集合
  == `config/`。总用例 3123 → **3127**（+2 钉测、+1 N3 本篇、+1 D1 因
  R178 进入扫描区间）。
- 变异 **3/3**：新增未登记 `config/w19_probe.json` / 从源清单删
  `preset_phrases.json` / 改覆盖键名，W19a/W19b 各自红。
- **回填**：R178 §6（run `42203675809` / bot `BOT_SHA`）与索引 §1
  的写回 / 基线两行。

## 2. 为什么是这一轮

桌面 full 包的默认配置由 `desktop/scripts/stage_defaults.py` 生成：
源文件从 `git show HEAD:config/<name>` 原样读取，三个覆盖文件用代码里的
字面量，models 由 example 派生。**新增一个 `config/new.json` 而忘记加进
清单时，桌面 full 包会静默缺文件**，后端回落到代码默认值；删除/改名
配置时也要等构建期 `git show` 才失败。现有
`test_stage_defaults_uses_sanitized_overrides` 把 `_read_git_json`
monkeypatch 掉，只钉覆盖值与脱敏，**不钉真实 config 集合**——这条边
此前无人判。

W19 的锚选在「`config/*.json` 的集合」：三组清单必须铺满且不重叠。
不判每个 JSON 的内容（各自测试负责），也不判覆盖值的业务正确性。

## 3. 实现

### 3.1 `tests/test_desktop_defaults.py`（W19a / W19b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W19a | `config/*.json` == 源清单 ∪ 覆盖清单 ∪ models 派生对；三组两两不重叠；源 ≥10、覆盖 ≥3 | `SOURCE_CONFIG_FILES` / `DESKTOP_OVERRIDES` |
| W19b | `build_payloads` 的键集合 == `config/`；`models_config.json` == example；`stage_defaults` 返回与落盘集合 == `config/` | 真实 `git show HEAD:config/…` |

实现要点：

- 集合恰等而不是包含：新增/删除任一配置文件都必须同步改清单，否则
  W19a 显式红；清单里留一个不存在的文件同样红。
- W19b 走真实 `build_payloads` / `stage_defaults`（不 monkeypatch），
  证明的不只是常量表，而是**实际会写进桌面包的文件集合**。
- `models_config.json` 必须逐字等于 example，防止派生逻辑被改成读
  用户本机的 `config/models_config.json`（那会把个人配置打进安装包）。

### 3.2 生产代码与配置

- 零改动：`stage_defaults.py`、`config/`、桌面构建脚本都不动。

## 4. 验证

- 定向：`tests/test_desktop_defaults.py` 2 passed；关联桌面打包文件
  38 passed / 1 skipped（macOS icon 生成按平台跳过）。
- 本机全量：**3099 passed / 28 skipped / 0 failed**（3127 条，约
  10m36s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 新增未登记 `config/w19_probe.json` | W19a/W19b 红 |
| M2 从 `SOURCE_CONFIG_FILES` 删 `preset_phrases.json` | W19a/W19b 红 |
| M3 覆盖键 `extensions.json`→`extensions.probe.json` | W19a/W19b 红 |

三次变异均 `read_bytes`/`write_bytes`（或创建后删除）还原并逐字节复核。

## 5. 边界与遗留

- 只判「文件集合」：不判 JSON 内容、不判覆盖值的业务正确性（脱敏与
  覆盖已由 `test_stage_defaults_uses_sanitized_overrides` 负责）。
- 不判 `config/extension-overrides/` 目录（不是 `config/*.json` 集合的
  一部分）；不判桌面安装后 `seed_user_config` 的落盘行为（已有测试）。
- 四轮连推（十四）下一轮 **R180 收口轮（R177–R179 四账）**：四账审计
  + 登记下一批（R181–R184）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`f0c78d4`** 推送后 run **42207692893**：**10 job 全
  `success`**（11:06:09→11:24:38 UTC，约 18m29s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42207692893`，bot 提交 **`d53530b`**）。R180 回填。

## 7. 提交

- 改动：`tests/test_desktop_defaults.py`（W19）、R179 文档、R178 §6
  回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行
  + §6.1）、`PROJECT_INFO.md`（H2 + R179 一条）、
  `JUDGEMENT_LEDGER.md`（§10.51）。生产代码与配置零改动。
- `config/skills_config.json` 不纳入（C1）。
