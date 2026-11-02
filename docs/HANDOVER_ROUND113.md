# DeterminFlow (xs2) 交接报告 — Round 113

> 单 profile。用户拍板 **1C+2A**：注入矩阵与全链失败形状两条边界合并成一轮；
> `config/skills_config.json` 外来改动保持未提交。生产行为改动只涉及
> **回放工具的 `--attempts`**（测试面），`src/`、`web/` 零改动。

## 1. 一句话结论

- `--conflict-on-reject` 扩到 **N=4/5**：新增 `--attempts`，并补上
  **注入点 ≤ 重试次数** 的可达性校验（R112 只查了预算，漏了一半）。
- 本地新增 3 条时间线（N=4 全失败 / N=4 第五次成功 / N=5 全失败），
  全链新增 `fetched-rejected-hook-at-4`；本地场景 10 → **13**，全链 2 → **3**。
- 全链失败形状新增 **全失败 / 0 场景 / 重试多次仍失败** 三种，真实
  `fetch → writeback` 后读沙箱历史核对计数与逐场景 `first_failure`。
- 本机全量 **2689 passed / 28 skipped / 0 failed**（2717 条，349.80s），
  比 R112 净增 **+6**。
- 定向 **49 passed**（165.56s）；变异 **M1–M6 全咬合**、`cp` 还原后
  sha256 逐字节相同。

## 2. 用户拍板

| 项 | 决定 | 落地 |
|---|---|---|
| R113 主线 | **1C：注入矩阵 + 全链失败形状** | 本轮完成 |
| `config/skills_config.json` | **2A：保持未提交** | 未纳入提交 |

R112 §8 没有新的编号待定项；本轮处理的是它留下的两条可执行边界。

## 3. 注入矩阵：N=4/5 与两个可达性变量

### 3.1 先补闸门

R112 的校验是 `--reject-pushes >= N`，但写回循环最多 push
`attempts` 次（默认 3）。`--reject-pushes 4 --conflict-on-reject 4`
能通过校验却永远到不了第 4 次 push——注入不会发生，失败只表现为普通的
三次拒绝。R113：

- `--attempts`（默认 `writeback.DEFAULT_ATTEMPTS` = 3）透传到
  `writeback.writeback(..., attempts=...)`；
- CLI 新增 `N <= attempts` 校验，不满足退 2，消息带当前 attempts；
- 原有 `N <= reject_pushes`、`N >= 1`、`attempts >= 1` 校验保留。

**一条「配置生效」的判据必须覆盖配置里每一个决定可达性的变量。**
只查预算不查重试次数，等于给了「看起来生效」一个合法出口。

### 3.2 新增场景（本地 10 → 13）

| 场景 | 预算/注入/重试 | 观测 |
|---|---|---|
| `rejected-hook-conflict-at-4` | 4 / 4 / 4 | exit 1、`reason=rebase-conflict`、rounds 基线+1、末条 `replay-conflict`、push 4、`simulated rejection` 4 |
| `rejected-hook-budget-4-at-4` | 4 / 4 / 5 | exit 0、净 +2、第 4 次拒绝时注入、第 5 次成功 |
| `rejected-hook-inject-at-5` | 5 / 5 / 5 | exit 1、`reason=rebase-conflict`、rounds 基线+1、push 5、`simulated rejection` 5 |

全链新增 `fetched-rejected-hook-at-4`（预算 4/注入 4/attempts 5，成功净 +2）：
artifact 仍按 `total=10` 断来源，额外断「第 4 次拒绝时注入冲突」「rebase
冲突（第 4 次）」「第 5 次尝试」——证明 `--attempts` 在真实 CLI 子进程里
透传到了重试循环。

## 4. 全链失败形状（fetch → writeback）

三种形状都由本地 HTTP artifact 夹具提供，走真实
`fetch_ci_artifact.fetch()` → `writeback()`，再读沙箱 history：

| 形状 | 计数 | 断言 |
|---|---|---|
| 全失败 | total 3 / passed 0 / failed 3 / retried 0 / attempts 3 | 写回照常入库；每个场景 `passed=False` 与 `first_failure` 原样落库；语义行 `fail_*=fail/1` |
| 0 场景 | total 0 / passed 0 / failed 0 / retried 0 / attempts 0 | 合法形状，照常入库；语义行显式打印 `（无场景）`，不留空行 |
| 重试多次仍失败 | total 2 / passed 1 / failed 1 / retried 2 / attempts 5 | `never_passes` 试 3 次仍 `passed=False`；`ok_after_retry` 试 2 次通过；`first_failure` 逐项保留 |

**写回记录的是数据，不是结论**：本轮 e2e 全红不等于写回失败；失败数据必
须进历史，否则趋势永远看不到质量事故。生产 artifact 仍是真实全过形状，
失败形状只在测试夹具里（§5 的「不污染趋势」边界不变）。

0 场景的语义行原本是空字符串，看起来与「指纹没打」完全一样；本轮改为
`（无场景）`，让「缺少内容」也显式说出来。

## 5. 判据台账

- #15 扩为「全链 metrics 内容指纹与语义（R107/R112/R113）」：补三种失败
  形状与 `（无场景）` 的盲区。
- #16 扩为「拒绝预算、注入时机与重试上限（R108/R112/R113）」：补 N=4/5
  结局与「可达性是两个变量」。
- §6 复核表补两条用例清单；§10 标题扩到 R113，新增 §10.5（可达性）与
  §10.6（失败形状）。

## 6. 验证

- 定向：**49 passed**（`test_replay_ci_writeback.py` +
  `test_replay_ci_scenarios.py`，165.56s）。
- 本机全量：**2689 passed / 28 skipped / 0 failed**（2717 条，349.80s）。
- 变异 **M1–M6 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 钩子固定第一次注入 → 3 条（N=2/4/5）红；
  - M2 反转 attempts 可达性校验 → 不可达注入点用例红；
  - M3 驱动忽略场景 attempts → 13 场景里 10/13，3 条新场景红；
  - M4 写回忽略 `--attempts` → 2 条（N=4 全失败/第五次成功）红；
  - M5 语义把失败标成 ok → 全失败形状红；
  - M6 去掉 `（无场景）` → 0 场景形状红。
- 变异日志：`_r113_mutate.log`；备份在 `_r113_backup/`（未提交）。

## 7. CI

- run **41479138215**（16:12:14→16:28:38 UTC，含一次失败 job 重跑，约
  16m24s）：**10 个 job 全 `success`**。
  - backend **2652/65**、windows-backend **2688/29**（均 **2717**）；
  - `replay-ci-writeback` 两平台各 **13/13 PASS**；
  - `replay-ci-fetch-chain` 两平台各 **16/16 PASS**（13 本地 + 3 全链）；
    `fetched-rejected-hook-at-4` 实测 `exit=0 rounds=43 push_attempts=5`；
  - 前端 **490 / 0**。
- **首次运行时 `e2e-history-writeback` 失败**：三次 push 都收到 GitHub
  `Internal Server Error`（远端历史仍是 41/80，没有半写回）。这是服务端
  瞬时错误，不是代码/判据问题；`rerun-failed-jobs` 后该 job success，
  整轮 conclusion 变为 success。
- 写回历史 **41 → 42**（`ci-41479138215`、`source=ci`），bot 提交
  `7420a6c`（`[skip ci]`，未自触发）；本文档回填提交预计 **42 → 43**。

## 8. 边界与下一步

- 生产 artifact 仍是真实全过形状；失败形状只在全链测试夹具里。
- 覆盖到 N=5 / attempts=5；N>5、attempts>5 与更多预算组合未单独建场景。
- `--attempts` 只影响回放沙箱；生产 `ci_writeback_history.py` 的
  `DEFAULT_ATTEMPTS=3` 未变，CI 写回重试上限仍是 3。
- 按天滚动、失败沙箱「保留最近 N 个」按 R112 拍板**不做**；GC 默认仍
  dry-run、7 天。
- `config/skills_config.json` 外来改动保持未提交（2A）。

## 9. 提交与 CI

- 代码+文档提交 **8c3e727**（`feat(R113): 注入矩阵扩到 N=4/5 + 全链失败
  形状`），显式路径 add，6 文件 +658/−119；`config/skills_config.json`
  未纳入。
- CI run **41479138215**（见 §7）；写回 bot `7420a6c`。
- 本文档与 PROJECT_INFO/记忆回填后推送，预计触发最后一轮 CI 并写回
  **42 → 43**。
