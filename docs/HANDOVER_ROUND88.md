# DeterminFlow (xs2) 交接报告 — Round 88（CI 回写 e2e 重跑历史）

> 本轮定位：用户拍定「做」CI 回写历史。R81 §7 曾给出代价表并结论「不做」，
> 本轮改判；落点是**独立 write job**，写权限与仓库测试的执行面分离。
> 形态：`ci.yml` 加一个 job + 一个 artifact 上传步骤；`scripts/e2e_retry_history.py`
> 只改模块 docstring；新增 9 条接线测试；判定语义（趋势不判好坏）不变。

## 1. 一句话结论

1. **backend** 在 e2e 之后上传 `e2e-metrics` artifact（仅 main 的 push；
   环境起不来时缺失只告警）。
2. **新 job `e2e-history-writeback`**：`needs: backend`、只在 main push 上跑、
   `permissions: contents: write`、`concurrency` 串行化；它**不跑任何仓库测试**，
   只执行 `scripts/e2e_retry_history.py record` 与 git 提交/推送。
3. **幂等**：`run_id = ci-<github.run_id>`（不是 `run_attempt`），同一 run 重跑
   覆盖同一轮，不会把一次运行记成两轮（R78 的「同 id 覆盖」契约）。
4. 语义变更：一次 main push 可以产生一轮；20 轮窗口在密集提交下滚动更快
   （R81 §7 的告警，已登记台账 §7.14）。**趋势仍不判好坏**（R78 不变）。

## 2. 为什么是独立 job，不是 backend 加一步

写回需要 `contents: write`。如果把它加在 backend 里，backend 的 **PR 运行**
（以及所有跑仓库测试的步骤）都会拿到写权限——测试代码与非可信输入在同一个
token 下执行，写入面和执行面重叠。拆成独立 job 后：

| job | 权限 | 执行什么 |
|---|---|---|
| `backend`（push / PR） | 顶层 `contents: read` | pytest、e2e、快照判据 |
| `e2e-history-writeback`（仅 main push） | `contents: write` | checkout、下载 artifact、record、commit/push |

`tests/test_ci_history_writeback.py::test_writeback_job_runs_no_repository_tests`
把「写回 job 不得出现 pytest / e2e_workflow_stub / npm / docker」钉死；
`test_write_permission_belongs_only_to_the_writeback_job` 钉住写权限的唯一归属。

## 3. 数据流与幂等

```
backend: e2e → $RUNNER_TEMP/e2e-metrics.json
         → upload-artifact (name=e2e-metrics, 仅 push/main, 缺失 warn)
e2e-history-writeback: download-artifact (continue-on-error)
         → record --run-id "ci-${{ github.run_id }}"
         → 有 diff 才 commit（[skip ci]）
         → push origin HEAD:main，每次被拒先 pull --rebase，最多 3 次
```

- **同一 run 重跑**：`run_id` 相同 → `record` 覆盖同一轮（R78 已钉住）；
  内容不变时 `git diff --quiet` 直接退出，不产生空提交。
- **backend 失败**：断言失败时 metrics 仍会被写出（脚本在返回 1 之前写），
  写回 job 仍然执行——失败的轮次对趋势有价值。环境起不来（退出码 3）没有
  metrics，job 打印「本轮不入库」并退出 0。
- **并发**：`concurrency.group = e2e-history-writeback` +
  `cancel-in-progress: false` 串行化；push 竞态由 3 次 rebase 重试兜底。
- **自触发**：GITHUB_TOKEN 的 push 本就不触发 workflow；提交信息里仍写
  `[skip ci]`，防止将来换 PAT 后产生循环。

## 4. 接线测试（9 条，新增文件）

| 用例 | 钉什么 |
|---|---|
| `test_write_permission_belongs_only_to_the_writeback_job` | 顶层 read；写权限只在写回 job |
| `test_writeback_only_runs_on_main_pushes` | `push` + `refs/heads/main` + `needs.backend.result` |
| `test_writeback_job_runs_no_repository_tests` | 写回 job 不含 pytest/e2e/npm/docker |
| `test_backend_uploads_the_metrics_artifact_only_on_main_pushes` | artifact 名与上传条件 |
| `test_writeback_downloads_the_same_artifact_name` | 下载同名 artifact |
| `test_writeback_uses_run_id_not_run_attempt` | `ci-${{ github.run_id }}`，无重试次数变量 |
| `test_writeback_retries_and_skips_self_trigger` | `pull --rebase`、3 次循环、`[skip ci]` |
| `test_writeback_serializes_concurrent_runs` | concurrency 组与 `cancel-in-progress: false` |
| `test_committed_history_is_still_valid_for_the_writer` | 入库历史仍能通过 `validate_history` |

**总用例 2560 → 2569（+9）**；本机全量 **2541 passed / 28 skipped / 0 failed**
（151.42s）。

## 5. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `.github/workflows/ci.yml` | +上传步骤、+写回 job（+66 行） | CI |
| `scripts/e2e_retry_history.py` | 模块 docstring +5 行 | 文档性 |
| `tests/test_ci_history_writeback.py` | 新增 9 条 | 测试 |
| `docs/JUDGEMENT_LEDGER.md` | §6 一行 + §7.14 | 文档 |
| `docs/PROJECT_INFO.md` | R88 条目（+R87 CI 回填） | 文档 |
| `docs/HANDOVER_ROUND88.md` | 新增 | 本文 |

**生产 Python 代码零改动**：`scripts/check_live_snapshot_gate.py`、
`scripts/e2e_retry_history.py` 的逻辑、`src/` 均未动。

## 6. 未做与未验证

1. **没有在 PR 上写回**：按设计只在 main push；PR 的历史由下一次 main push
   补齐（`check` 读到的是检出时的历史）。
2. **没有处理分支保护**：main 当前无保护；若将来加保护，bot 直推会三次失败
   并以 `::error::` 显式报错，不会静默丢历史。
3. **没有改趋势判据**：仍不判好坏（10 场景 = 10pp，R78 §2）。
4. **没有在本地复现整个 writeback job**：本地只验证了 `record` 幂等（R78 已有）
   与 YAML 接线；真正的 artifact→commit→push 链由本轮 CI 首次执行（见 §7）。
5. **没有清理旧的本机入库轮次**：历史里 R78 那一轮保留。

## 7. 提交、推送与 CI 核对

（待补记）
