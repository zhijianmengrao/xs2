# DeterminFlow (xs2) 交接报告 — Round 162（许可证面同账：pyproject license ↔ LICENSE ↔ README 徽章）

> 单 profile。四轮连推（十）第 2 轮（R160 §7 登记）。授权声明有四个
> 写入点——pyproject 的 `license` / `license-files`、仓库根的
> `LICENSE`、两份 README 的徽章——此前无人对账：改 license 而不换
> LICENSE 文件、或不改徽章时，PyPI 元数据、仓库根文件与 README 展示
> 各说各话。本轮钉成 **V4**（V 系从「引用可解析」延伸到授权面）。

## 1. 一句话结论

- 新增 `tests/test_license_surface.py` **V4a/V4b**（实测 R160 §7
  登记，首跑即过）：
  - **V4a license-files 可解析**：`license-files = ["LICENSE"]` 里的
    每个文件必须在磁盘（缺文件 = 打包分发清单指空）。
  - **V4b 授权名同账**：pyproject `license = "AGPL-3.0-only"` 的
    核心段 `AGPL-3.0` == 两份 README 徽章 alt（`许可证：AGPL-3.0` /
    `License: AGPL-3.0`）与 URL（`badge/license-AGPL--3.0-blue`，
    `--` 归一为 `-`）中的 `AGPL-3.0`；`-only` 后缀不进徽章是正常
    写法，不参与对账。
- 总用例 3063 → **3067**（+2 V4、N3/D1 因本篇与 R161 回填 +2）；
  变异 **3/3**。生产代码零改动。

## 2. 开工复核（实测 2026-11-06）

| 写入点 | 值 |
|---|---|
| pyproject `license` | `AGPL-3.0-only` |
| pyproject `license-files` | `["LICENSE"]`（在磁盘） |
| README.md 徽章 | URL `badge/license-AGPL--3.0-blue` + alt `许可证：AGPL-3.0` |
| README.en.md 徽章 | 同 URL + alt `License: AGPL-3.0` |

## 3. 实现

- V4a：tomllib 读 `[project].license-files`（缺失/空显式红），逐项
  `is_file()`。
- V4b：SPDX 标识符正则取核心段（`AGPL-3.0-only` → `AGPL-3.0`，
  连字符进入名字）；每份 README 的 license 徽章 URL 与 alt 各解析出
  **恰好一个**授权名（URL 的 `--` 归一为 `-`），与核心段比较；URL
  与 alt 任一不等逐条列红。语料守卫内建：徽章解析不到显式红。

## 4. 判据台账

- 新增 §10.34（V 系续：许可证面，V4），接在 §10.33 之后；家族清单
  不变（仍是 V 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_license_surface.py` **2 passed**。
- 本机全量：**3039 passed / 28 skipped / 0 failed**（3067 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 pyproject `license-files` → `["LICENSE-renamed"]` | V4a 红（文件不存在），V4b 绿 |
| M2 README.en 徽章 alt `AGPL-3.0` → `MPL-2.0` | V4b 红（alt MPL-2.0 vs pyproject AGPL-3.0），V4a 绿 |
| M3 pyproject `AGPL-3.0-only` → `AGPL-3.1-only` | V4b 红（核心段 3.1 vs 徽章 3.0），V4a 绿 |

字节快照还原后 sha256 逐字节相同，3/3 咬合。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R163 回填。

## 7. 边界与遗留

- 只判声明面：不读 LICENSE 文件内容、不校验 SPDX 合法性、不判徽章
  href 指向的上游仓库（fork 的徽章有意指 upstream，V2b 同型边界）。
- 下一轮 **R163 PROJECT_INFO 支持面行（L8）**：活文档里的 Python /
  Node 下限行 == requires-python / engines 下限（R160 §7 登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_license_surface.py`（新文件，V4）、R162 文档、
  R161 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R162 一条）、
  `JUDGEMENT_LEDGER.md`（§10.34）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
