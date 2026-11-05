# DeterminFlow (xs2) 交接报告 — Round 157（支持面展示层同账：徽章 ↔ Python 下限 / Node 下限 ↔ engines）

> 单 profile。四轮连推（九）第 1 轮（R156 §7 登记）。README 的 shields
> 徽章与「Node.js 22.12+」是支持面最显眼的展示层，此前全靠手抄：
> 改 requires-python 没人会记得改徽章；engines 升了 README 不会跟着
> 走。本轮把两条边钉成 **P6–P7**，Python 支持面家族（P 系）从解释器
> 与锁延伸到展示层与非 Python 运行时。

## 1. 一句话结论

- `tests/test_python_support_surface.py` 新增 **P6–P7**（实测 R156 §7
  登记，首跑即过）：
  - **P6 徽章 → 下限**：README.md / README.en.md 的 shields 徽章
    （URL `badge/Python-X.Y-` 与 `alt="Python X.Y"` 双锚）==
    requires-python 下限（实测两份都是 3.11 == 3.11）。
  - **P7 Node 下限 → engines**：README 双语「Node.js X.Y+」==
    `web/package.json` `engines.node`（`>=X.Y.0` 形状；实测 22.12 ==
    `>=22.12.0`）；声明 `node-version` 的 workflow，major 必须等于
    engines major（实测 3 个 workflow 都写 `"22"`）。
- 总用例 3048 → **3052**（+2 P6/P7、N3/D1 因本篇与 R156 回填 +2）；
  变异 **4/4**。生产代码零改动。

## 2. 开工复核（实测 2026-11-05/06）

| 项 | 值 |
|---|---|
| README.md 徽章（第 18 行） | `<img src="…/badge/Python-3.11-3776AB?logo=…" alt="Python 3.11">` |
| README.en.md 徽章 | 同上（双语结构同账保证同行同位） |
| requires-python 下限 | `>=3.11` → 3.11 |
| README 双语 Node 下限 | `Node.js 22.12+`（各恰好一处） |
| `web/package.json` engines | `"node": ">=22.12.0"` |
| CI `node-version` | ci.yml / desktop-windows.yml / desktop-macos.yml 各写 `"22"` |

徽章 URL 与 alt 各自解析出**恰好一个** X.Y 才判——两处写法是同一
事实的两次展示，只改其一时旧判据会放行；P6 用双锚钉住。Node 的
CI 声明是 major（`"22"`），与 engines 的 `>=22.12.0` 只做 major
同账：GHA 的 `node-version: "22"` 安装最新 22.x（≥ 22.12 由 minor
同账间接保证不了——这是声明面的颗粒度边界，见 §5）。

## 3. 实现

- P6：`BADGE_URL_RX`（URL 路径段）与 `BADGE_ALT_RX`（alt 属性）
  分别在每份 README 里各取一个集合，恰等单一值后与 requires-python
  下限比较；URL 与 alt 任一不等都逐条列红。
- P7：engines 只认 `>=X.Y.0` 形状（GHA/工具链的常见写法，其他写法
  显式红）；README 的 `Node.js X.Y+` 恰好一处；CI 伴生判扫全部
  workflow 的 `node-version`，声明 major != engines major 即红，
  全仓库无声明也红（防止判据空转）。
- 语料守卫内建于 P6/P7：徽章解析不到、engines 缺失、Node 下限
  缺失都显式红，不静默跳过。

## 4. 判据台账

- 新增 §10.29（P 系续：支持面展示层，P6–P7），接在 §10.28 之后；
  家族清单不变（仍是 P 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_python_support_surface.py` **7 passed**（P1–P7）；
  相关回归 `test_readme_parity.py`（M1–M4，README 结构被动过）同跑。
- 本机全量：**3022 passed / 28 skipped / 0 failed**（3052 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 README.md 徽章 URL `3.11` → `3.10` | P6 红（URL 3.10 vs 下限 3.11），其余 6 条绿 |
| M2 README.md 徽章 alt `3.11` → `3.10` | P6 红（alt 3.10 vs 下限 3.11），其余 6 条绿 |
| M3 README.md Node `22.12+` → `22.11+` | P7 红（README 22.11 vs engines 22.12），其余 6 条绿 |
| M4 engines `>=22.12.0` → `>=22.13.0` | P7 红（README 22.12 vs engines 22.13），其余 6 条绿 |

字节快照还原后 sha256 逐字节相同，4/4 咬合（P6 与 P7 互不串扰，
P1–P5 全绿）。

## 6. CI

- 提交 **`5f91198`** 推送后 run **42071828247**：**10 job 全
  `success`**（17:09:35→17:27:34 UTC，约 17m59s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42071828247`，bot 提交 `5d84d81`）。R158 回填。

## 7. 边界与遗留

- P7 的 CI 伴生判只做 major 同账：`node-version: "22"` 无法声明
  minor 下限，`22.12` 的保证来自 engines 本身（npm 会拒绝更旧的
  Node）；若未来某 workflow 需要钉完整版本（`"22.12.0"`），P7 的
  正则已兼容 `X.Y` 与 `X.Y.Z` 之外的 major 写法，同账判继续成立。
- 不判 npm 下限（README 提 npm 无版本声明）；不判 desktop 管线的
  Node 实际版本（tag-only 上游继承，声明面已由 major 同账覆盖）。
- 下一轮 **R158 安装文档引用面（V3）**：README×2 / CONTRIBUTING /
  Dockerfile 引用的锁文件必须存在（R156 §7 登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_python_support_surface.py`（P6–P7）、R157 文档、
  R156 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R157 一条）、
  `JUDGEMENT_LEDGER.md`（§10.29）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
