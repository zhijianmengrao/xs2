# DeterminFlow (xs2) 交接报告 — Round 143（requirements 双源一致性）

> 单 profile。R140–R143 四轮第 4 轮（收官）：**本地依赖源与 CI 锁文件
> 同账**。零生产代码改动。

## 1. 一句话结论

- **实测缺口（R142 §7 预告）**：CI 从 `requirements-dev.lock`（84 包闭包）
  安装，本地从 `requirements.txt`（19 顶层依赖）安装，两源之间无判据——
  一边升版另一边忘跟，本地与 CI 就跑在不同版本上。实测 2026-11-05：
  按名覆盖成立（`uvicorn[standard]` → lock 裸名，extras 归一）、19 个
  `==` 钉版全部一致——对，但没判据。
- 新增 `tests/test_requirements_lock_sync.py`（2 函数 / 2 条，**W 系**）：
  **W1** requirements.txt 每个包（extras 剥离）必须出现在 lock；
  **W2** 每个 `==V` 与 lock 同包 `==V` 逐字相等。总用例 2981 → **2984**
  （+2 钉测、+1 N3 本篇）。
- 变异 **M1–M3 3/3** 咬合：lock 删包（双红：覆盖+同账）、req 升版（W2）、
  lock 升版（W2）；还原 sha256 一致。

## 2. 为什么是这一轮

「两个 runner 给出互相矛盾的结论」是 R57 注释里点过名的最难排查形态，
而依赖分叉是它的最廉价入口。R140–R143 的最后一块：闸门清单（R135）、
账本（R136）、索引（R137）、手册（R138）、脚本（R140）、skip（R141）、
叙事账（R142），最后是**依赖双源**。十轮全部遵循同一形制：实测 → 定界
→ 钉测 → 变异咬合。

## 3. 实现

### 3.1 `tests/test_requirements_lock_sync.py`

- 解析器跳过注释与 `-r`/`-e` 行；extras 剥离归一（`uvicorn[standard]`
  → `uvicorn`）；`==` 全匹配才算钉版（范围规格记 None，W2 跳过）。
- **W1 名字覆盖**：req ⊆ lock（按名）；**W2 版本同账**：钉版逐字相等。
- lock ⊉ req 的反方向不判（闭包超集是常态）；环境标记整行接受；
  lock 内部传递依赖不钉（锁文件自己的职责）。

### 3.2 刻意不做的

- 不把 requirements.txt 改成 `-r requirements-dev.lock`（双源各有受众：
  本地快速装顶层、CI 装闭包——判据保证它们不漂移即可）；
- 不钉 uvloop 等传递依赖的平台标记内容。

## 4. 判据台账

- §10.13 同族补一段（W 系：依赖双源同账）。

## 5. 验证

- 定向：`tests/test_requirements_lock_sync.py` **2 passed**（0.05s）。
- 本机全量：**2955 passed / 1 S2 延后红 / 28 skipped**（2984 条，473.97s）
  ——S2 按流程等 R142 bot 落地后随本提交改行；R143 收官树 +2 钉测
  +1 N3 本篇。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 lock 删 `uvicorn==0.50.2` 行 | W1+W2 双红 |
| M2 req `uvicorn[standard]==0.50.2→0.50.3` | W2 红 |
| M3 lock `uvicorn==0.50.2→0.50.9` | W2 红 |

内存快照还原后 sha256 逐字节相同，3/3 咬合。

## 6. CI

- 提交推送后 run `<run1>`：10 job 预计全绿；写回历史 **72→73**。
- 本篇 docs 回填提交预计 **73→74**。

## 7. 边界与遗留

- W2 只钉 `==` 钉版：requirements.txt 若引入范围规格（`>=`），W2 对该包
  降级为只查 W1 覆盖——引入范围规格是显式动作，届时应连动本判据。
- extras 归一是单向的：req 声明 extras 而 lock 无对应传递闭包时不红
  （实测 uvloop/httptools/websockets 均在 lock 闭包内，属现状钉死）。
- R140–R143 四轮收官：五轮连推（六）的候选制从 R144 起，由下一轮开工
  实测登记。

## 8. 提交

- 改动：`tests/test_requirements_lock_sync.py`、R143 文档、PROJECT_INFO、
  HANDOVER_INDEX。生产代码零改动。
