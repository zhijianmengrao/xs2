# DeterminFlow (xs2) 交接报告 — Round 109（MAX_ROUNDS 可配置）

> 单 profile。把 R106 §8 的第一条候选做成**可配置但不改政策**：历史保留期
> 由 `XS2_MAX_ROUNDS` 覆盖，默认仍是 40。零 `src/`、`web/` 改动；失败沙箱
> 策略、写权限归属都不动。

## 1. 一句话结论

- 新增 `e2e_retry_history.max_rounds()`：读 `XS2_MAX_ROUNDS`，默认 **40**，
  范围 `[3, 1000]`；非整数/越界**告警并退回默认**，不静默生效。
- 所有运行期入口统一走这一个读取点：`record` 裁剪与文案、
  `ci_writeback_history` 的窗口文案/`window_full`、replay 驱动期望、
  冲突夹具裁剪、钩子注入的 `MAX_ROUNDS`。
- 没设环境变量时行为与 R108 完全一致（CI 也未设）。
- 用例 **+4 → 2699**；本机 **2671 passed / 28 skipped / 0 failed**
  （251.02s）。R108 为 2667/28（2695）。
- **变异 M120–M126 7/7 咬合**；M123 首测 MISSED——只改文案的缺陷没有
  断言看见，补 `detail` 后咬住（§4/§7）。
- CI run **41443367040**：**10 个 job run 全 `success`**，writeback 7/7、
  fetch-chain 9/9；写回历史 **33 → 34**（`9b8caba`）。

## 2. 实现要点

### 2.1 单一读取点

```python
MAX_ROUNDS = 40
MAX_ROUNDS_ENV = "XS2_MAX_ROUNDS"
MAX_ROUNDS_FLOOR = 3
MAX_ROUNDS_CEILING = 1000


def max_rounds() -> int:
    raw = os.environ.get(MAX_ROUNDS_ENV, "").strip()
    if not raw:
        return MAX_ROUNDS
    try:
        value = int(raw)
    except ValueError:
        print(f"::warning::...不是整数，保留期退回 {MAX_ROUNDS}", file=sys.stderr)
        return MAX_ROUNDS
    if value < MAX_ROUNDS_FLOOR or value > MAX_ROUNDS_CEILING:
        print(f"::warning::...超出范围，保留期退回 {MAX_ROUNDS}", file=sys.stderr)
        return MAX_ROUNDS
    return value
```

范围下限 3：相邻两轮趋势至少需要 3 轮；上限 1000：超出趋势样本的合理
规模。非法值不静默生效——写错的环境变量让策略悄悄回到默认，正是
「配置看起来生效了」的典型坑。

### 2.2 所有调用点

| 位置 | 用途 |
|---|---|
| `e2e_retry_history.record` | `history[-window:]` 裁剪 + `check-only`/写入文案 |
| `e2e_retry_history` CLI help | 打印当前窗口 |
| `ci_writeback_history._writeback_steps` | no-change / written 的 `历史 n/window 轮` |
| `ci_writeback_history._rehearse` | dry-run 的满窗/净增量文案 |
| `ci_writeback_history.writeback` | result JSON 的 `window_full` |
| `replay_ci_scenarios._run_scenario` | 期望轮数 `min(before+delta, window)`、`rounds_clipped` |
| `replay_ci_scenarios.run` | 启动日志、`window_full`、result 的 `max_rounds` |
| `replay_ci_writeback._create_conflicting_round` | 冲突注入的窗口裁剪 |
| `replay_ci_writeback._conflict_hook_source` | R108 钩子注入脚本里的 `MAX_ROUNDS` |

只要有一处回退到常量，就会立刻出现「裁剪按 80、期望按 40」这类两个事实
两种说法；R109 的驱动用例用「窗口 8、基线 8」把这种分裂判红。

### 2.3 用例

- `tests/test_e2e_retry_history.py`：
  - `test_max_rounds_env_override_and_invalid`：默认 40 / 80 生效 /
    `abc`、`2`、`1001` 告警并退回 40；
  - `test_record_uses_the_configured_window`：窗口 4 时写 5 轮只留 4，
    首条 `r1`、末条 `r4`，文案是 `/4 轮`。
- `tests/test_ci_writeback_history.py`：
  - `test_writeback_window_follows_env`：窗口 5、基线 5，`rounds=5`、
    `window_full=true`、`detail` 含 `5/5 轮`。
- `tests/test_replay_ci_scenarios.py`：
  - `test_driver_uses_the_configured_window`：窗口 8、基线 8，冲突的 +2
    被裁剪、失败场景的注入也裁到 8；驱动全场景通过。

## 3. 用例（+4）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_e2e_retry_history.py` | +2 | 环境变量/非法值；record 窗口裁剪与文案 |
| `tests/test_ci_writeback_history.py` | +1 | 写回窗口、`window_full`、`detail` 文案 |
| `tests/test_replay_ci_scenarios.py` | +1 | 驱动 + 夹具共用窗口（基线=窗口=8） |

**本机全量**：**2671 passed / 28 skipped / 0 failed**（2699 条，251.02s）。

## 4. 变异验证（7/7 咬合）

| 变异 | 结果 |
|---|---|
| M120 `max_rounds()` 忽略环境变量 | **1 红**（环境变量用例） |
| M121 record 裁剪回退常量 | **1 红**（record 窗口用例） |
| M122 驱动期望回退常量 | **1 红**（驱动窗口用例） |
| M123 `_writeback_steps` 的窗口回退常量 | **首测 MISSED**；补 `detail` 断言后 **1 红** |
| M124 非法值不告警 | **1 红**（环境变量用例） |
| M125 范围检查失效 | **1 红**（环境变量用例） |
| M126 冲突夹具回退常量 | **1 红**（驱动窗口用例：满窗注入造出第 9 轮） |

**M123 是本轮真正的发现**：`_writeback_steps` 的 `window` 只影响文案，
裁剪实际由 `record` 完成；如果只断言 `rounds/window_full`，文案说
`5/40` 也全绿。补上 `detail` 含 `5/5 轮` 后，这个「同一事实两种说法」
的缺陷才被看见。全部用 `cp` 备份还原并核对 sha256（备份在
`_r109_backup/`）。

## 5. 边界

- **默认政策没变**：不设 `XS2_MAX_ROUNDS` 时窗口仍是 40；CI 也没有设。
  本轮只把「改成 80 / 按天滚动」从改代码变成改部署配置，选择权留给
  后续；按天滚动仍未实现。
- `export_run_samples.HISTORY_MAX_ROUNDS = 5` 是快照的**相邻基线**材料，
  不是保留期，未动。
- 环境变量是部署策略，不是判据；判据（窗口边界用例）仍按默认 40 钉住。
- 失败沙箱仍由驱动断言存在后清理；写权限仍只属于
  `e2e-history-writeback`。
- 范围 `[3, 1000]` 是安全护栏，不是政策值；真要用 80 只需设环境变量。

## 6. 提交与 CI

- 提交 **c70d6db**（`feat(R109): MAX_ROUNDS 可配置（默认 40）`；
  rebase 后 **e9a90f8**），显式路径 add，7 文件 +145/−23；
  `config/skills_config.json` 外来改动保持未提交。
- 本机全量：**2671 passed / 28 skipped / 0 failed**（2699 条，251.02s）。
- CI run **41443367040**：**10 个 job run** 全 `success`
  （12:16:41→12:24:10，约 7m29s）——backend **2634/65**、
  windows-backend **2670/29**（均 **2699**）；
  `replay-ci-writeback` 两平台各 **7/7 PASS**；
  `replay-ci-fetch-chain` 两平台各 **9/9 PASS**（默认 40 口径，
  与 R108 相同）。
- 写回历史 **33 → 34 轮**（`ci-41443367040`、`source=ci`、10/10/0），
  bot 提交 `9b8caba`（`[skip ci]`，未自触发）；本文档回填提交预计
  **34 → 35**。

## 7. 本轮教训

1. **一个配置项只能有一个读取点**：`max_rounds()` 本身很简单，难的是
   把 record、写回文案、驱动期望、夹具、钩子五处全部换过去。任何一处
   留在常量上，都会产生「裁剪按 A、期望按 B」的分裂。
2. **非法配置必须出声**：静默退回默认会让「我设了 80」与「实际 40」
   长期共存。告警 + 显式范围比「尽量容错」更安全。
3. **只改文案的缺陷需要文案断言**：M123 在 rounds/window_full 全对时
   完全隐形；`detail` 是判据的一部分，不是装饰。
4. **默认值不变也是一种交付**：R109 没有替用户拍板 40→80，而是把选择
   变成部署配置；政策问题留给真正要拍板的人。

## 8. 下一步候选

- R110：失败沙箱自动 GC（默认 dry-run、只认约定前缀与过期年龄）。
- R111：收口轮——五轮审计、文档一致性、全量回归。
- 按天滚动保留期（需要新的时间戳裁剪规则与趋势样本定义）。
- 在 CI 里用 `XS2_MAX_ROUNDS=80` 跑一次全链，验证配置在真实 job 上生效
  （需要单独 job 或矩阵参数）。
