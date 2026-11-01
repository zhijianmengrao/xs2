# DeterminFlow (xs2) 交接报告 — Round 96（replay 全链 fetch→writeback）

> 第 2 轮。形态：`replay --fetch-api-url`；假 artifact API 抽成共享夹具；
> 上传文件名 / fetch artifact 名 / 写回文件名三方契约用例。

## 1. 一句话结论

R95 把「下载」变成代码，R96 把**下载 → 写回**在本地一次走完：

- `replay --fetch-api-url` 先调用真实的 `fetch_ci_artifact.fetch()`（列表 →
  下载 zip → 解压），再把解出来的 `e2e-metrics.json` 交给真实 `writeback()`；
- 拉取失败（5xx/网络）→ 不进入写回、保留沙箱、退出码沿用 fetch 的 1；
- 缺 artifact → fetch 退出 0，写回按「没有 metrics」退出 0（与 CI 同语义）；
- 上传侧仍是 `actions/upload-artifact`，但它产出的文件名、fetch 的 artifact
  名、写回读取的文件名现在由一条接线用例钉成同一份事实。

## 2. 实现要点

1. `replay_ci_writeback.py`：
   - `--metrics` 与 `--fetch-api-url` 互斥且必选其一（argparse group）；
   - fetch 解压到 `sandbox/e2e/`，写回读 `sandbox/e2e/e2e-metrics.json`；
   - fetch 非 0 → `can_write = False`，不进入写回，沙箱按失败保留。
2. 共享假 API：`tests/artifact_api_fixture.py`（`zip_bytes` / `api_path` /
   `listing` / `server`），`test_fetch_ci_artifact` 与 `test_replay_ci_writeback`
   共用——避免 R80 的「同一事实写两处」。
3. 接线契约（`test_upload_fetch_and_writeback_agree_on_the_metrics_filename`）：
   - backend 上传 `path` 的 basename == `e2e-metrics.json`；
   - fetch 的 `--artifact e2e-metrics`、`--path $RUNNER_TEMP/e2e`；
   - 写回读 `$RUNNER_TEMP/e2e/e2e-metrics.json`。

## 3. 用例（+5）

| 文件 | 新增 | 断言 |
|---|---|---|
| `tests/test_replay_ci_writeback.py` | +4 | fetch 成功后 `0 → 1` 且提交信息正确；缺 artifact `0 → 0`；fetch 5xx 不进入写回、退 1、沙箱保留；`--metrics`/`--fetch-api-url` 都没给 → 2 |
| `tests/test_ci_history_writeback.py` | +1 | 上传 basename、artifact 名、写回文件名三方一致 |
| `tests/test_fetch_ci_artifact.py` | 0（重构） | 改用共享夹具，9 条断言不变 |

**本机全量**：**2598 passed / 28 skipped / 0 failed（2626 条）**，R95 的 2621 + 5。

## 4. 变异验证（4/4 全咬合）

| 变异 | 结果 |
|---|---|
| M40 replay 忽略 `--fetch-api-url` | 1 红 |
| M41 拉取失败仍进入写回 | 1 红 |
| M42 沙箱内文件名接错 | 1 红 |
| M43 上传文件名与写回不一致 | 1 红 |

## 5. 边界

- 上传侧 `actions/upload-artifact` 仍无法本地执行；R96 只把它的**文件名契约**
  钉住，zip 的实际布局仍由 CI 生产运行验证。
- fetch 的假 API 只证明客户端契约（R95 §5 同）。
- 真实 GitHub API + token 权限仍只在 CI 走到。

## 6. 提交与 CI

- 与 R97 同一提交 `aa62a29`（R91/R92 有同提交先例）。
- CI run **41325738034** 六 job 全 `success`：
  - backend **2573 / 65**、windows **2609 / 29**，均 **2638**（本地 2638）；
  - 写回 job：历史 **11 → 12 轮**（`ci-41325738034`，`source=ci`），main 头
    bot 提交 `f3f26fb`。

## 7. 本轮教训

1. **跨三个步骤的同一个文件名必须由一条用例串起来**：上传路径的 basename、
   fetch 的 artifact 名、写回的 metrics 路径原本是三处独立字符串；任何一处
   改名都只表现为「本轮不入库」（退出 0），不是失败。R80 的「同一事实两处
   会分裂」在这里是三处。
2. **共享夹具要抽成非 `test_*` 模块**：两个测试文件各自维护一份假 HTTP 服务，
   协议一旦补一条分支就会漂移；抽到 `tests/artifact_api_fixture.py` 后，
   fetch 与 replay 的假服务永远同源。
