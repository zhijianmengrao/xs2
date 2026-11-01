# DeterminFlow (xs2) 交接报告 — Round 94（`--dry-run` + 本地回放）

> 第 5 轮。形态：写回脚本增加 `--dry-run`；新增 `scripts/replay_ci_writeback.py`，
> 把整条「写回 → 提交 → 推送」在临时沙箱里走一遍。

## 1. 一句话结论

R89 §7-2 的「未在本地复现整个 writeback job」缩到只剩**artifact 传输本身**：

- `--dry-run`：在历史**副本**上真算一遍，报告将写入的轮次，不写文件、不提交、不推送；
- `replay_ci_writeback.py`：从源仓库克隆一个裸沙箱作为 origin，再克隆工作区，
  用真实的 `writeback()` 提交并推送——**源仓库一个字节都不动**（工具自己复核 HEAD）。

## 2. 实现要点

1. `_rehearse()`：`TemporaryDirectory` 里的历史副本 → `record()` → 比较前后字节：
   - 相同 → `no-change`；
   - 不同 → `dry-run` 类别，打印 `历史 N/40 轮（+k，未写入）`；
   - metrics/历史坏 → 与正常路径相同的退出码（4）。
2. `replay`：
   - `git clone --bare <repo> sandbox/origin.git` → `git clone -b <branch> origin work`；
   - 在 work 里跑真实 `writeback()`（提交、推送、重试全是真的，只是推到沙箱）；
   - 打印 `历史 before → after 轮；退出码；沙箱 HEAD`，并复核源仓库 HEAD 未变；
   - 默认删除沙箱，`--keep` 保留。
3. `--dry-run` 与 replay 的 `--dry-run` 可组合：沙箱里也只算不写。

## 3. 用例（7 条）

| 用例 | 断言 |
|---|---|
| `test_dry_run_does_not_touch_the_repo` | HEAD、`git status`、历史文件都不动；打印 `dry-run` 与 `1/40` |
| `test_dry_run_reports_no_change_for_a_recorded_run` | 已记录的 run 再 dry-run → `no-change` |
| `test_dry_run_rejects_bad_metrics_without_writing` | 坏 metrics → 4，历史不变 |
| `test_cli_wires_dry_run` | CLI 的 `--dry-run` 不产生提交 |
| `test_replay_leaves_the_source_repo_untouched` | 源仓库 HEAD/status/历史字节都不变；输出 `0 → 1` |
| `test_replay_reports_the_writeback_commit` | 沙箱 HEAD 是 `chore(e2e): record CI run replay-1` |
| `test_replay_dry_run_does_not_commit` | 回放 + dry-run → `0 → 0` |

## 4. 变异验证（3/3 全咬合）

| 变异 | 结果 |
|---|---|
| M28 dry-run 直接写真实历史文件 | 1 红 |
| M29 dry-run 走真实写回（提交+推送） | 1 红 |
| M30 回放把源仓库当 origin（会写源仓库） | 1 红 |

## 5. 边界

- **artifact 传输仍是唯一不能本地复现的一段**（`actions/download-artifact`）；
  replay 用 `--metrics` 直接喂文件，覆盖的是它下游的全部逻辑。
- replay 只回放**已提交**的状态：源仓库工作树里的未提交改动不会进沙箱。
- 沙箱默认删除；需要检查时 `--keep`。

## 6. 提交与 CI

- 提交 `4786abf`（原 `1ba6915`，推送前 rebase 到 bot 提交 `905bd58`）。
- CI run **（待回填）**。
- 本机全量 **2578 passed / 28 skipped / 0 failed**（R93 2571/28，+7）。
