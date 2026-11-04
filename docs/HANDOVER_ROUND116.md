# DeterminFlow (xs2) 交接报告 — Round 116（失败形状 × 拒绝/注入：内容不被重算）

> 单 profile。五轮连续推进的第 3 轮：把「失败形状 artifact」与「拒绝/冲突
> 重试」组合起来——重试只应改变 push 次数与远端轮数，不能把 artifact 里的
> failed/retried/attempts 或逐场景 `first_failure` 重算掉。
> 生产行为零改动（只加测试），`src/`、`web/` 零改动。

## 1. 一句话结论

- 新增参数化用例 `test_failure_shape_survives_retries` 两格：
  - 被拒一次后成功：`push_attempts=2`、rounds +1；
  - 第一次拒绝时注入冲突、第三次成功：`push_attempts=3`、rounds +2。
- 两格都断言：历史条目的 `(total, passed, failed, retried, attempts) ==
  (4, 3, 1, 1, 5)`，`retry_1.first_failure` 与 `fail_2.first_failure`
  原样保留，`reason=written`、末条是本轮 run_id。
- 本机全量 **2694 passed / 28 skipped / 0 failed**（2722 条，363.74s），
  比 R115 净增 **+2**。
- 定向 **2 passed**（3.09s）；变异 **M1–M2 全咬合**、sha256 还原一致。

## 2. 为什么组合

R112 证明失败/重试形状能走完 fetch → writeback；R113 证明拒绝/注入能走完
重试循环。但两条路径此前从未在同一用例里相遇：

- 重试循环有 `prepared`/`reset --hard`/`record` 的重算逻辑，任何一处把
  metrics 重新读错或丢掉场景明细，单看「写回成功」发现不了；
- 失败形状的 `failed > 0` 恰好让「计数被清零/场景被重算」立刻显形——
  全过形状的 `failed=0` 会让这类缺陷完全隐形。

## 3. 测试

`tests/test_replay_ci_writeback.py::test_failure_shape_survives_retries`
（`pytest.mark.parametrize` 两格）：

| 参数 | 观测 |
|---|---|
| `--reject-pushes 1` | exit 0、push 2、rounds 1、输出「第 2 次尝试」 |
| `--reject-pushes 2 --conflict-on-reject 1` | exit 0、push 3、rounds 2、输出「rebase 冲突（第 1 次）」「第 3 次尝试」 |

两格共用同一份 4 场景 artifact（2 过、1 重跑后过、1 失败，
`total=4 passed=3 failed=1 retried=1 attempts=5`），并读沙箱 history
核对逐场景 `first_failure`。

## 4. 判据台账

- #15「全链 metrics 内容指纹与语义」补组合场景：失败形状 × 拒绝后成功 /
  × 注入冲突后成功。
- §6 复核表补该用例。
- §10.6 补一句：重试路径不得重算内容；全过形状会让「failed 被清零」隐形。

## 5. 验证

- 定向：**2 passed**（`-k failure_shape_survives_retries`，3.09s）。
- 本机全量：**2694 passed / 28 skipped / 0 failed**（2722 条，363.74s）。
- 变异 **M1–M2 全咬合**（`cp` 备份、sha256 逐字节相同）：
  - M1 `entry_from_metrics` 把 `failed` 清零 → 两格都红（计数矛盾）；
  - M2 丢掉 `first_failure` → 两格都红（逐场景内容丢失）。
- 变异日志：`_r116_mutate.log`；备份 `_r116_backup/`（未提交）。

## 6. CI

- run **41493684591**（17:47:14→约 17:58 UTC）：**10 个 job 全 `success`**。
  - backend **2657/65**、windows-backend **2693/29**（均 **2722**）；
  - `replay-ci-writeback` 两平台各 **15/15 PASS**；
  - `replay-ci-fetch-chain` 两平台各 **18/18 PASS**；
  - 前端 **490 / 0**。
- 写回历史 **45 → 46**（`ci-41493684591`、`source=ci`），bot 提交
  `61d1d87`（`[skip ci]`，未自触发）。

## 7. 边界与下一步

- 组合只覆盖「最终成功」的重试路径；永久失败时本轮不入库，失败指标不会
  落库——这是写回语义，不是本轮缺口。
- 生产 artifact 仍是真实全过形状；失败形状只在测试夹具里。
- `config/skills_config.json` 保持未提交。

## 8. 提交与 CI

- 代码+文档提交 **ac3ae43**（`test(R116): 失败形状经拒绝/注入后内容不丢
  （含 R115 CI 回填）`），显式路径 add；`config/skills_config.json` 未纳入。
- CI run **41493684591**（见 §6）；写回 bot `61d1d87`。
- 下一轮 CI 预计写回 **46 → 47**。
