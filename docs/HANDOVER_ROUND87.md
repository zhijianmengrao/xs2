# DeterminFlow (xs2) 交接报告 — Round 87（n≥29 全失败样本：主动制造 / 翻转点 n=29）

> 本轮定位：用户拍定 R84 §3.3 的改判——原结论是「n≥29 的自然全失败样本不存在，
> 不主动制造」，本轮改为**主动制造**。
> 形态：零生产代码改动；新增两份真实导出的 fixture + 10 条测试 + 文档。
> 关键约束：**隔离 `DETERMINFLOW_DATA_DIR`，不碰仓库 `data/workflows`**。

## 1. 一句话结论

1. 用 e2e 的桩 provider + 真实 `Runtime` 编排，在隔离数据目录里真跑 **29 次**
   首节点带 `[stub:fail]` 的工作流：29/29 `task=failed`，每次落一份真实
   `run-*.json`（不是手写 JSON）。
2. 导出成两份 fixture：`live_snapshot_all_failed_29`（29/29/100%）与
   `live_snapshot_all_failed_28`（28/28/100%，与前者只差一个 run）。
3. **n=29 是 margin 10 的翻转点**：29 → `--check-sample-size` 退 **0**
   （闭式 9.81pp ≤ 10）；28 → 退 **7**（10.15pp > 10，「约 29 次尝试」）。
   两份 `evaluate --fail-if-above 8` 均退 **1**（政策超阈），
   `--check-coverage` 均退 **6**（单 workflow，设计内）。

## 2. 制造方式（为什么不是手写 JSON）

R84 §3.3 拒绝制造的理由是「为一条判据故意跑坏 29 次真实工作流，代价与污染都
不值得」。本轮按用户拍定改判，但把两个代价都消掉了：

- **不污染仓库数据**：`DETERMINFLOW_DATA_DIR` 指到
  `F:\DeterminFlow x2\_r87_sample_data`（仓库外），`data/workflows` 只读。
- **不依赖真实供应商/凭据**：复用 `scripts/e2e_workflow_stub.py` 的桩 provider
  （真实 HTTP + SSE，走 ChatOpenAI SDK / LangGraph / 引擎回调全链路），
  失败由桩按协议返回（`stub induced failure`），不是伪造 run 记录。
- **失败是真实终态**：每次 `Runtime.run_workflow` 都等到 task 终态；
  29 次全部 `task=failed`、节点 `status=failed`、`attempt_count=1`、
  没有自动重试（`max_retries=0`）。

生成器 `_r87_generate.py` 按 R81/R84 的约定留在工作区根，**不入库**；它的全部
依赖（`Runtime` / `_isolate_environment` / `_write_models_config` /
`_write_agents_config`）都来自已入库的 e2e 脚本。

## 3. 导出与判决

导出走真实链路（只读隔离目录）：

```
python scripts/export_run_samples.py \
  --source "F:\DeterminFlow x2\_r87_sample_data\data\workflows" \
  --dest tests/fixtures/live_snapshot_all_failed_29 --limit 40
python scripts/export_run_samples.py \
  --source "F:\DeterminFlow x2\_r87_sample_data\data\workflows" \
  --dest tests/fixtures/live_snapshot_all_failed_28 --limit 28
```

`_iter_source_runs` 按 run 文件名倒序取前 `limit` 个（不看 mtime），所以 28 份
fixture 是 29 份去掉一个确定性的 run——`test_manufactured_fixtures_differ_by_exactly_one_run`
把「只差一个」钉死，翻转就只能归因于样本量。

| fixture | 文件 | 大小 | `--check-sample-size`（margin 10） | `evaluate --fail-if-above 8` | `--check-coverage` |
|---|---|---|---|---|---|
| `live_snapshot_all_failed_29` | 29 run + meta | 129 KB | **0**：9.81pp ≤ 10.0（n=29） | **1**：区间 [90.19%, 100.00%] | 6 |
| `live_snapshot_all_failed_28` | 28 run + meta | 125 KB | **7**：10.15pp > 10.0（n=28），「约 29 次尝试」 | **1**：区间 [89.85%, 100.00%] | 6 |

导出时裁剪把 4416 B/run 压到 **1024 B/run**；两份 fixture 都不含
`summary` / `input_snapshot` / `outputs` / `token_usage_calls` 等载荷字段
（两条自动发现的 fixture 扫描各多 2 个参数）。

## 4. 新增测试（10 条）

| 用例 | 钉什么 |
|---|---|
| `test_manufactured_all_failed_fixture_is_a_real_export[n29/n28]` | 每个 run `status=failed`；`runs/attempts/failed` 与 meta 自洽 |
| `test_n29_all_failed_sample_passes_the_margin` | 29 → 0，文案含 `9.81` 与 `n=29` |
| `test_n28_all_failed_sample_is_the_flip_point` | 28 → 7，文案含 `10.15` 与「约 29 次尝试」 |
| `test_manufactured_fixtures_differ_by_exactly_one_run` | 28 份是 29 份的真子集，差集恰 1 |
| `test_n29_all_failed_snapshot_still_exceeds_the_policy_ceiling` | 29 → 1，区间 `[90.19%, 100.00%]` |
| 两条既有扫描（载荷 / 裁剪恒等） | 自动发现新 fixture，各 +2 参数 |

**总用例 2550 → 2560（+10）**；本机全量 **2532 passed / 28 skipped / 0 failed**
（152.39s），`2522 + 10 = 2532`。

## 5. 变异验证（两次）

还原源是当前文件快照（`_r86_gate_snapshot.py`，gate 未变，md5 `5e0a070e…`）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| M1 | 全失败闭式改成返回常量 `9.0` | **2 failed** | `test_n29_...passes_the_margin` + `test_n28_...is_the_flip_point` |
| M2 | 从 29 fixture 移走一个 run 文件（meta 不动） | **2 failed** | `test_manufactured_all_failed_fixture_is_a_real_export[n29]` + `test_n29_...passes_the_margin` |

M1 还原后 gate md5 逐字节相同；M2 还原后 fixture 计数回到 29。

## 6. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/fixtures/live_snapshot_all_failed_29/` | 新增 30 文件（129 KB） | 真实导出快照 |
| `tests/fixtures/live_snapshot_all_failed_28/` | 新增 29 文件（125 KB） | 同上，少一个 run |
| `tests/test_live_snapshot_gate.py` | +10 条用例 + 扫描名单同步 | 测试 |
| `docs/JUDGEMENT_LEDGER.md` | +22 行（§6 一行 + §7.13） | 文档 |
| `docs/PROJECT_INFO.md` | +1 行（R87 条目） | 文档 |
| `docs/HANDOVER_ROUND87.md` | 新增 | 本文 |

**生产代码零改动**：`scripts/check_live_snapshot_gate.py` 的 md5 仍
`5e0a070e…`；`scripts/export_run_samples.py`、`src/`、CI YAML 均未动。

## 7. 未做与未验证

1. **没有改 `data/workflows`**：仓库真实数据仍 40 个 run；制造全程在
   `F:\DeterminFlow x2\_r87_sample_data`（仓库外）。
2. **没有改导出脚本/闸门**：本轮只消费它们的既有能力。
3. **没有跑前端 / e2e / docker build**：零服务路径改动。
4. **没有验证真实供应商的失败分布**：这批样本验证的是**样本量判据的边界算术**，
   不是供应商质量；n=29 的合格路径由桩诱导的全失败走通，不代表真实世界会出现
   29 次连续全失败。
5. **没有把生成器入库**：按 R81/R84 的约定留在工作区根；重生成步骤见 §2/§3。

## 8. 下一轮

**R88：CI 回写历史**（用户已拍定「做」）。先出设计与代价表：R81 §7 的原始结论
是「不做」，本轮改判为「做」；必须处理 `contents: write`、并发/竞态、失败回滚、
避免提交自我触发的循环，且不能影响现有 `permissions: contents: read` 的 job。

## 9. 提交、推送与 CI 核对

- 提交 `5a3f958`（test + 两份 fixture）与 `4413aa2`（docs），推送 `4ca3c31..4413aa2`。
- CI run **41296193079**（push，10:09:05 → 10:14:23，约 5m18s）五个 job 全 `success`：
  ubuntu `2495 passed, 65 skipped` = **2560**；windows `2531 passed, 29 skipped`
  = **2560**（各 +10，与本轮新增用例数一致）；e2e 10/10、前端与容器 job 均
  `success`。
