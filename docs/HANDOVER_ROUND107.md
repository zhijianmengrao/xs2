# DeterminFlow (xs2) 交接报告 — Round 107（全链 metrics 内容指纹）

> 单 profile。把 R106 §8 的第四条候选做完：证明全链写回的结果确实来自
> **下载到的 artifact 内容**，而不是驱动自己的本地夹具。零 `web/` 改动；
> `MAX_ROUNDS`、失败沙箱策略、写权限归属都不动。

## 1. 一句话结论

- `replay_ci_writeback` 在写回前打印**实际 metrics** 的计数指纹：
  `replay：metrics 内容 total=… passed=… failed=… retried=… attempts=…`。
- 驱动的本地夹具改成**故意与生产不同**的形状（3 场景、1 次重跑、总尝试
  4），生产 artifact 是 10 场景；全链场景断言指纹
  `metrics 内容 total=10`，误用本地夹具会变成 `total=3` 立刻露馅。
- 用例 **+3 → 2693**；本机 **2665 passed / 28 skipped / 0 failed**
  （229.47s）。R106 为 2662/28（2690）。
- **变异 M109–M112 4/4 咬合**；M110（写死 total=10）只能由**变体形状**的
  单测发现——生产形状的断言挡不住「来源错了但形状碰巧一样」（§4）。
- CI run **41433682082**：**10 个 job run 全 `success`**，
  fetch-chain 两平台 **7/7 PASS**；写回历史 **29 → 30**（`02863d4`）。

## 2. 实现要点

### 2.1 计数指纹

`scripts/replay_ci_writeback.py` 新增 `_metrics_content()`（解析失败返回
`None`，正式错误仍由 `record` 给出），并在 `writeback()` 之前打印：

```python
content = _metrics_content(metrics_path)
if content is not None:
    print(f"replay：metrics 内容 total={content['total']} "
          f"passed={content['passed']} failed={content['failed']} "
          f"retried={content['retried']} "
          f"attempts={content['attempts']}")
```

指纹来自 `metrics_path`——fetch 时就是下载解压后的
`e2e-metrics.json`，本地时就是 `--metrics` 文件。

### 2.2 本地夹具故意与生产不同

`replay_ci_scenarios._metrics()` 从「10 场景、0 重跑」改成「3 场景、
其中 1 个重跑一次」：

```json
{"schema": 1, "total": 3, "passed": 3, "failed": 0, "retried": 1,
 "scenarios": [{"name": "local_0", "attempts": 2, ...}, ...]}
```

非 fetch 的本地场景仍能写回（record 只校验形状），但它们的指纹是
`total=3`。全链场景断言 `metrics 内容 total=10`，因此：

- fetch 成功 → 指纹 total=10，通过；
- fetch 成功但错误地回退到本地夹具 → 指纹 total=3，判红；
- 完全不打印指纹 → 判红（M109）。

### 2.3 只钉 total，不钉 retried/attempts

生产 e2e metrics 的形状是 10 场景，但**重跑次数**取决于当轮 e2e 是否
发生重试。如果把 `retried=0 attempts=10` 写进断言，某天一个场景重试就会
让全链 job 变红——那是 e2e 的 flake，不是写回回归。因此只钉
`total=10`（生产契约：e2e 有 10 个场景），其余计数只出现在日志里供诊断。

### 2.4 用例

- `tests/test_replay_ci_writeback.py`：
  - `test_replay_reports_the_metrics_content`：本地 2 场景 metrics →
    指纹 `total=2`；
  - `test_replay_reports_the_fetched_metrics_content`：artifact 4 场景 →
    指纹 `total=4`，证明指纹跟着**下载内容**走。
- `tests/test_replay_ci_scenarios.py`：
  - `test_local_metrics_shape_is_deliberately_different`：本地夹具
    total=3/retried=1/尝试和=4，并钉两个全链场景都含
    `metrics 内容 total=10`；
  - 全链 e2e 的 `fetched` / `fetched-rejected-conflict` 记录里断言输出
    含该指纹。
- 既有 fetch e2e 的测试 artifact 从 1 场景改成 10 场景，与生产同形。

## 3. 用例（+3）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_writeback.py` | +2 | 本地 2 场景 / artifact 4 场景的指纹分别正确 |
| `tests/test_replay_ci_scenarios.py` | +1 | 本地夹具形状 + 两个全链场景的 total=10 钉 |

**本机全量**：**2665 passed / 28 skipped / 0 failed**（2693 条，229.47s）。

## 4. 变异验证（4/4 咬合）

| 变异 | 结果 |
|---|---|
| M109 不打印计数指纹 | **2 红**（本地指纹用例 + 全链行为用例） |
| M110 指纹写死 `total=10` | **2 红**（本地 2 场景 / artifact 4 场景用例）；全链行为用例仍绿 |
| M111 全链场景不钉 `total=10` | **1 红**（形状钉用例） |
| M112 本地夹具改成 10 场景 | **1 红**（五场景行为用例：record 校验失败） |

**M110 是重点**：生产 artifact 本来就是 total=10，写死 10 的全链行为用例
照样通过；只有「换一个形状再断言」的单测能发现。**生产形状的判据只能
证明「没缺」，不能证明「来源对」**（R70 的同一教训：用例看起来在测，
和只有它能发现，是两件事）。

全部用 `cp` 备份还原并核对 sha256（备份在 `_r107_backup/`）。

## 5. 边界

- `total=10` 是生产 e2e 的契约（10 个场景）；若 backend 增删场景，全链
  场景的断言要同步改。这是有意的显式契约，不是隐式耦合。
- 指纹只覆盖计数，不覆盖场景名/`passed` 逐项内容；内容语义仍由
  backend 的 e2e 用例与 `record` 的形状校验覆盖。
- `MAX_ROUNDS` 保持 40；失败沙箱仍由驱动断言存在后清理；写权限仍只属于
  `e2e-history-writeback`；replay / fetch 两个 job 仍只读。

## 6. 提交与 CI

- 提交 **27653a0**（`feat(R107): 全链 metrics 内容指纹`），显式路径 add，
  4 文件 +125/−11；`config/skills_config.json` 外来改动保持未提交。
- 本机全量：**2665 passed / 28 skipped / 0 failed**（2693 条，229.47s）。
- CI run **41433682082**：**10 个 job run** 全 `success`
  （11:03:22→11:11:38，约 8m16s）——backend **2628/65**、
  windows-backend **2664/29**（均 **2693**）；
  `replay-ci-writeback` 两平台各 **5/5 PASS**
  （rounds 30/30/31/29/30；永久拒绝末条 `ci-41430862316`）；
  `replay-ci-fetch-chain` 两平台各 **7/7 PASS**（`fetched` rounds 30、
  末条 `replay-ci-fetched-27653a00`；三重叠加 exit=1、rounds=30、
  末条 `replay-conflict`、push 3）。
- 写回历史 **29 → 30 轮**（`ci-41433682082`、`source=ci`、10/10/0），
  bot 提交 `02863d4`（`[skip ci]`，未自触发）；本文档回填提交预计
  **30 → 31**。

## 7. 本轮教训

1. **生产形状的断言证明不了来源**：写死 `total=10` 的变异全链照样绿，
   因为生产 artifact 就是 10。要证明来源，必须让「错误来源」的形状与
   正确来源**不同**，再用变体形状单测咬住。
2. **夹具的形状是判据的一部分**：把本地夹具从 10 改成 3 不是「随便造
   数据」，而是让「回退到本地」从不可见变成可见。夹具与生产同形时，
   很多来源错误天然隐形。
3. **只钉稳定字段**：`total` 是契约，`retried/attempts` 是当轮运行结果；
   把运行结果写进判据会把 e2e flake 变成 replay 回归。
4. **打印实际输入**：`metrics 内容 …` 这一行让日志自己说出「写的是哪份
   数据」，比在断言里猜更直接，也让失败现场可诊断。

## 8. 下一步候选

- R108：拒绝预算行为边界——把冲突注入挪到第一次 push 之后，让
  `reject_pushes` 2/3 可区分。
- R109：保留期策略——`MAX_ROUNDS` 可配置（默认仍 40）。
- R110：失败沙箱自动 GC（默认 dry-run、只认约定前缀与过期年龄）。
- artifact 内容语义：让全链 artifact 用失败/重试形状（需要 e2e 或 fixture
  能产出非全绿 metrics），而不只是计数指纹。
