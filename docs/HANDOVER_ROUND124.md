# DeterminFlow (xs2) 交接报告 — Round 124

> 单 profile。注入矩阵补到 **N=7/8、attempts=9**：本地两条时间线 + 全链
> 一条，把 R114/R117 留下的「N>6 / attempts>7 未建场景」闭合。生产行为
> 零改动（只加场景与断言）。

## 1. 一句话结论

- 本地场景 **15→17**：`rejected-hook-inject-at-7`（预算/注入 7、
  attempts=7，七次全拒、末次注入）与 `rejected-hook-budget-8-at-8`
  （预算/注入 8、attempts=9，第 9 次成功、净 +2）。
- 全链场景 **10→11**：`fetched-rejected-hook-at-8`（同 N=8/attempts=9），
  `replay-ci-fetch-chain` 记录数 25→**28**（17 本地 + 11 全链）。
- 场景表/窗口边界/全链端到端/公式测试全部同步；用例总数仍 **2733**
  （新增的是场景行，不是新的 pytest 函数）。
- 本机定向 **40 passed**（重放+接线，230.30s）；全量
  **2705 passed / 28 skipped / 0 failed**（446.18s）。

## 2. 为什么是这一轮

R114 把本地矩阵抬到预算 6 / N=6，R117 把 N=6/attempts=7 搬进全链，此后
两轮交接都把 **N>6 / attempts>7** 列为未建场景。此前的「可达性」只由场景
表不变量与 `N <= attempts` 校验保证；没有任何一条真实回放能证明：

1. 拒绝钩子的计数器在第 7、8 次仍然工作；
2. 写回重试循环没有隐含的 7 次上限（`--attempts 9` 真的会 push 第 9 次）；
3. 全链子进程同样透传 `--attempts 9`。

R124 用三条时间线分别钉住这三点，代数关系与旧场景完全一致。

## 3. 场景与测试

| 场景 | 预算 | 注入点 | attempts | 期望观测 |
|---|---|---|---|---|
| `rejected-hook-inject-at-7` | 7 | 7 | 7 | exit=1、`rebase-conflict`、rounds=基线+1、push=7 |
| `rejected-hook-budget-8-at-8` | 8 | 8 | 9 | exit=0、`written`、净 +2、push=9 |
| `fetched-rejected-hook-at-8` | 8 | 8 | 9 | 全链同型；额外断 `metrics 内容 total=10` 与 `metrics 语义` |

同步点：

- `tests/test_replay_ci_scenarios.py`：本地/全链期望列表、逐场景 actual、
  失败沙箱清单、窗口边界三组（38/39/40）、全链 API 调用数（10→11）、
  脚本模式场景数（15→17）、全链公式测试；
- `.github/workflows/ci.yml`：job 注释从「十五个场景各 1–7 次」改为
  「十七个场景各 1–9 次」；
- `scripts/replay_ci_scenarios.py`：模块/`Scenario` 文档补 R124。

## 4. 判据台账

- #16 标题扩到 R124；描述补 N=7/attempts=7、N=8/attempts=9 与全链
  `fetched-rejected-hook-at-8`。
- §10.5 补 R124 段：矩阵抬过 6/7 上限，不改代数关系，只证明没有隐含上限；
  场景表不变量仍是唯一守卫。

## 5. 验证

- 定向：
  - 静态场景表 **3 passed**（0.16s）；
  - 本地真实回放 `test_driver_runs_all_local_scenarios` **1 passed**
    （29.90s）；
  - 全链端到端 + 脚本模式 **2 passed**（75.21s）；
  - 窗口边界 38/39/40 **3 passed**（91.80s）；
  - 场景 + 接线两文件 **40 passed**（230.30s）。
- 本机全量：**2705 passed / 28 skipped / 0 failed**（2733 条，446.18s）。
  环境说明：本机无系统 git，使用项目外便携 MinGit
  `F:\DeterminFlow x2\_tools\mingit-2.56.0.4`；`GIT_CONFIG_COUNT=1` /
  `GIT_CONFIG_KEY_0=core.symlinks` / `GIT_CONFIG_VALUE_0=true` 让 symlink
  用例走真实路径（否则 `test_symlink_cannot_escape_checked_out_package`
  因链接被还原成普通文件而失败，首跑已复现该环境差异，加环境后通过）。
- 变异 **M1–M3 3/3 全咬合**（`cp` 还原后 sha256 逐字节相同）：
  - M1 `_install_rejection_hook` 把拒绝次数封顶 6 → N=7/8 两条新场景红
    （15/17 通过），旧 15 条不受影响；
  - M2 `_writeback_steps` 的重试循环封顶 7 → `rejected-hook-budget-8-at-8`
    红（exit=1、push=7，期望第 9 次成功）；
  - M3 `run()` 的全链元组漏掉 `fetched-rejected-hook-at-8` → 全链端到端
    列表断言红（少一项）。
- 变异日志：`_r124_m1.log`、`_r124_m2.log`、`_r124_m3.log`；备份
  `_r124_backup/`（未提交）。
- 还原后 sha256：
  `replay_ci_writeback.py` `AFD56A32…ADFE332A`、
  `ci_writeback_history.py` `4D494946…B95056A5`、
  `replay_ci_scenarios.py` `04277F9C…0AAE7A3`，与备份一致。

## 6. CI

- 本轮**未推送**：本机没有系统 git 与 GitHub 凭据，只有项目外的便携
  MinGit（`F:\DeterminFlow x2\_tools\mingit-2.56.0.4`）用于本地跑测试。
- 因此 CI 未触发、写回历史未变化（仍 **50/80**）。推送后预计
  `replay-ci-writeback` 两平台 **17/17**、`replay-ci-fetch-chain`
  两平台 **28/28**，写回 **50→51**（bot 提交）。

## 7. 边界与遗留

- 生产 `DEFAULT_ATTEMPTS=3`、`MAX_ROUNDS=80`、GC dry-run/7 天不变。
- 趋势表仍只展示、不判趋势好坏（R78/R115）。
- 按天滚动、失败沙箱「保留最近 N 个」按 R112 拍板不做。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`scripts/replay_ci_scenarios.py`、`tests/test_replay_ci_scenarios.py`、
  `.github/workflows/ci.yml`、R124 文档、PROJECT_INFO、JUDGEMENT_LEDGER。
- **未提交、未推送**：本会话没有收到提交/推送指令；改动保留在工作区，
  `config/skills_config.json` 不纳入。
- 本机验证用的 MinGit 与 `_r124_*` 日志/备份均在仓库外或未跟踪，不进入改动。
