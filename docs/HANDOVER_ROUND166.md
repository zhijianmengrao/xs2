# DeterminFlow (xs2) 交接报告 — Round 166（README 徽章序列双语同账：M5）

> 单 profile。四轮连推（十一）第 2 轮：两份 README 顶部徽章的 URL 序列
> 第一次变成机判。生产代码零改动；M5 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：两份 README 顶部各有 **4 枚**徽章——Release
  （`img.shields.io/github/v/release/...`）、CI
  （`github.com/.../actions/workflows/ci.yml/badge.svg`）、license
  （`img.shields.io/badge/license-AGPL--3.0-blue`）、Python
  （`img.shields.io/badge/Python-3.11-...`）。四枚 URL 逐项相等；
  唯一差异在 license 徽章的 alt：中文 `许可证：AGPL-3.0`、英文
  `License: AGPL-3.0`——这是语言翻译，不是账目漂移。
- `tests/test_readme_parity.py` 新增 **M5 徽章序列**（M 系续）：两份
  README 的徽章 URL 序列逐项相等、数量相等；alt 不参与。总用例
  3076 → **3079**（+1 钉测、+1 N3 本篇、+1 D1 因 R165 进入扫描区间）。
- 变异 **3/3**：删一枚 CI 徽章 / 改 Release URL / 交换前两枚顺序，
  各自独红；M1–M4 与 P6/P7、V4b 全绿互不串扰。

## 2. 为什么是这一轮

R153 的 M1–M4 只钉标题层级、代码块语言与显式锚点，明确把徽章与 HTML
块留在射程外；R157 的 P6 只钉 Python 徽章的值、P7 只钉 Node 下限；
R162 的 V4b 只钉 license 徽章里的授权名。于是四枚徽章里：

- Release / CI 两枚**完全无人对账**——改上游仓库、换 workflow 文件名，
  另一份 README 不会跟；
- 徽章的**顺序**无人对账——两枚互换仍是合法的 Markdown/HTML，但读者
  看到的展示顺序变了；
- 数量无人对账——中文加一枚、英文忘了加，两份文档的顶部看起来
  「一样高」但信息量不同。

M5 的锚选在「徽章 URL 序列」：URL 是机器可读的唯一身份，alt 是给人
读的（语言差异是设计），href 指向的仓库由 V2b 的 fork 边界负责。

## 3. 实现

### 3.1 `tests/test_readme_parity.py`（M5）

| 判据 | 内容 | 锚点 |
|---|---|---|
| M5 | 两份 README 的徽章 URL 序列逐项相等、数量相等；每份至少解析出一枚 | 徽章 `<img src>`（`img.shields.io` 与 GitHub Actions `badge.svg` 两个宿主） |

实现要点：

- 只认两种徽章宿主：`https://img.shields.io/...` 与
  `https://github.com/<owner>/<repo>/actions/workflows/<wf>/badge.svg`。
  品牌图、截图等其他 `<img>` 不进序列——它们不是双语对照的徽章。
- 先按位置逐项比较（报出第几枚、两边各是什么），再比较数量；
  数量差在共同前缀之后单独报告。
- 语料守卫：任一份 README 解析不到徽章即显式红，不让 M5 空转。

## 4. 验证

- 定向：`tests/test_readme_parity.py` 5 passed（M1–M5，0.10s）。
- 本机全量：**3051 passed / 28 skipped / 0 failed**（3079 条，约 10 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 删除 README.en 的 CI 徽章 | M5 红（数量 3 vs 4），M1–M4 绿 |
| M2 改 README.en 的 Release 徽章 URL | M5 红（第 1 枚不同），M1–M4 绿 |
| M3 交换 README.en 前两枚徽章顺序 | M5 红（第 1/2 枚错位），M1–M4 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判徽章的 URL 序列：不判 alt 文案（license 的中英差异是正常翻译）、
  不判 href 指向的仓库（fork 徽章有意指 upstream，V2b 同型）、不判
  徽章图片的内容与颜色。
- 品牌图、截图等其他 `<img>` 不在射程；它们没有双语对照的语义。
- 四轮连推（十一）下一轮 **R167 compose 环境账 ↔ config 读取点
  （W14）**：6 个 env 的读取点与静态默认值同账。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R167 回填。

## 7. 提交

- 改动：`tests/test_readme_parity.py`（M5）、R166 文档、R165 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R166 一条）、
  `JUDGEMENT_LEDGER.md`（§10.38）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
