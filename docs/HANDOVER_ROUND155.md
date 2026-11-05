# DeterminFlow (xs2) 交接报告 — Round 155（锁生成头 ↔ Python 下限同账：--python-version / requires-python）

> 单 profile。四轮连推（八）第 3 轮（R152 §7 登记）。两份锁的 uv 生成头
> 各写一行 `--python-version 3.11`，`requires-python` 的下限也是 3.11，
> P4 已把 README 的下限钉到同一锚——但锁头这条边此前无人对账：改
> requires-python 而不重生成锁时，锁仍按旧解释器解析，闭包可能悄悄
> 漂移。本轮把这条边钉成 **P5**。

## 1. 一句话结论

- `tests/test_python_support_surface.py` 新增 **P5**：两份锁
  （`requirements.lock` / `requirements-dev.lock`）生成头的
  `--python-version X.Y` == `requires-python` 下限。实测两处都是
  3.11，**首跑即过**（这条边此前成立、只是没人判）。
- 生成头是 P5 唯一的锚：丢失或写法改变必须显式红，不静默跳过。
- 总用例 3043 → **3046**（+1 P5、N3/D1 因本篇与 R154 回填 +2）；
  变异 **3/3**。生产代码零改动。

## 2. 开工复核（实测 2026-11-05）

| 项 | 值 |
|---|---|
| `requirements.lock` 生成头（第 2 行） | `uv pip compile requirements.txt --python-version 3.11 --universal --no-annotate --output-file requirements.lock` |
| `requirements-dev.lock` 生成头（第 2 行） | `uv pip compile requirements-dev.txt --python-version 3.11 …` |
| `pyproject.toml` requires-python | `>=3.11` → 下限 `3.11` |
| README 双语下限（P4） | `Python 3.11+`（已由 P4 钉住，同源） |

生成头是 `uv` 写锁文件时回显的**实际命令**，`--python-version` 记录
解析这份闭包用的解释器版本。W8/W9（R145）只对账「顶层声明 ↔ 锁内
钉版」，W10/W11（R150）只对账两锁闭包的交集——没有一条判据读过
生成头。缺的正是这条边：requires-python 改成 `>=3.12` 而锁头仍是
3.11 时，四源判据全绿，而锁解析出的闭包已经不是新下限的闭包。

## 3. 实现

- `LOCK_HEADER_RX`：生成头行形状 `#\s{2,}uv pip compile …
  --python-version[ =]X.Y\s`（行首注释 + 命令回显 + 版本后随空白，
  防止把别的旗标吃进来）。两份锁共用一个正则，各自解析。
- P5 判决：两份锁的版本各自与 `requires-python` 下限比较，全部
  相等才绿；错误信息逐锁列出「生成头 X.Y vs 下限 X.Y」，并提示
  「改下限后需重生成锁」。
- 语料守卫：任一锁的生成头匹配不到即红（消息点名该锁），P5 不会在
  「读不到锚」时静默放行。

## 4. 判据台账

- 新增 §10.27（P 系续：锁生成头 ↔ Python 下限，P5），接在 §10.26
  之后；家族清单不变（仍是 P 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_python_support_surface.py` **5 passed**（P1–P5）；
  相关回归 `test_dependency_sources.py`（W3–W11）13 passed 同跑。
- 本机全量：**3018 passed / 28 skipped / 0 failed**（3046 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 runtime 锁生成头 `3.11` → `3.10` | P5 红（生成头 3.10 vs 下限 3.11），P1–P4 绿 |
| M2 dev 锁生成头 `3.11` → `3.12` | P5 红（生成头 3.12 vs 下限 3.11），P1–P4 绿 |
| M3 runtime 锁生成头删掉 ` --python-version 3.11` | P5 红（锚丢失，显式红），P1–P4 绿 |

字节快照还原后 sha256 逐字节相同，3/3 咬合（三条变异只打锁头或
锁内旗标，P1–P4 全绿——P5 与其余四条互不串扰）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R156 回填。

## 7. 边界与遗留

- P5 只读生成头，不重放 uv 解析（闭包内容对账由 W 系负责）；不判
  `--universal` / `--no-annotate` 等其余旗标；不判 `uv.lock`
  （R148 已决定维持排除）。
- README 徽章 `Python-3.11` 的展示值与正文下限的同账仍是候选
  （R151 §7 提过），本轮未收。
- 下一轮 **R156 收口轮（R153–R156 四账）**：四账审计 + 登记
  R157–R160（先实测后登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_python_support_surface.py`（P5）、R155 文档、
  R154 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R155 一条）、
  `JUDGEMENT_LEDGER.md`（§10.27）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
