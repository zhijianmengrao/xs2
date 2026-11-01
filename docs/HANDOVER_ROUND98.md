# DeterminFlow (xs2) 交接报告 — Round 98（fetch 重试/分类 + 结果工件）

> 第 4 轮。形态：`fetch_ci_artifact.py` 增加传输重试与固定类别；
> `--result-json` / `--summary`；summary/result 写入抽成 `scripts/ci_reporting.py`。

## 1. 一句话结论

- **只重试瞬时错误**：429 / 500 / 502 / 503 / 504 与网络/超时，最多
  `DEFAULT_ATTEMPTS = 3` 次，退避 0.5s / 1s（可注入）；401/403 等 4xx
  **不重试**——重试没有意义，还会把「凭证坏了」拖成三次。
- **固定类别**：`artifact-fetched` / `artifact-missing` / `artifact-expired` /
  `artifact-fetch-failed` / `artifact-invalid` / `usage`；与 summary 共用同一组
  字符串。
- **结果工件**：`--result-json` 写 `schema/run_id/repo/artifact/reason/detail/
  exit_code/attempts/files/path`；`attempts` 是**列表 + 下载两次调用的总请求数**。
- summary/result 的写入实现从写回脚本抽到 `scripts/ci_reporting.py`，两边共用
  （R80：同一事实写两处会分裂）。

## 2. 实现要点

1. `_read_with_retries(url, …, attempts, sleep)`：HTTPError 先读 body 再决定；
   可重试且还有次数 → 打印、`sleep(min(0.5*2^(n-1), 5))`、继续；否则抛
   `FetchError(msg, used)`。网络/超时同理。
2. `FetchError.attempts`：**失败也要带上已发起的次数**；否则结果里的
   `attempts` 在失败路径永远是 0（本轮实测踩到，见 §7）。
3. `ArtifactInvalid(FetchError)`：坏 zip / 路径穿越 / 缺 archive_url / 空 zip
   → `artifact-invalid`；传输失败 → `artifact-fetch-failed`。
4. 假 API 的 `routes` 支持 callable，测试可以用计数器让第一次 500、第二次 200，
   并记录 `sleep` 调用（不真睡）。
5. CI：fetch 步骤加 `--summary` / `--result-json`；新增 `Upload fetch result`
   （`if: always()`、缺失 warn）。

## 3. 用例（+8）

| 文件 | 新增 | 断言 |
|---|---|---|
| `tests/test_fetch_ci_artifact.py` | +7 | 500 后重试成功（2 次列表 + 1 次下载 = attempts 3）；持续 500 → 3 次、退避 [0.5,1.0]；401 不重试（1 次、无 sleep）；result 与 summary 的 reason/detail 一致；missing/expired 分类；坏 zip → invalid；结果写失败只告警 |
| `tests/test_ci_history_writeback.py` | +1 | fetch 步骤带 `--summary`/`--result-json`；`Upload fetch result` 是 `always()` 且名称/路径/缺失行为正确 |

**本机全量**：**2618 passed / 28 skipped / 0 failed（2646 条）**，R97 的 2638 + 8。

## 4. 变异验证（7/7 全咬合）

| 变异 | 结果 |
|---|---|
| M50 401 也重试 | 1 红 |
| M51 不重试（`attempt < 1`） | 1 红 |
| M52 缺 artifact 归为失败 | 1 红 |
| M53 summary 写失败改判决 | 1 红 |
| M54 失败路径不写结果 | 1 红 |
| M55 YAML 丢 `--result-json` | 1 红 |
| M56 上传不是 `always()` | 1 红 |

## 5. 边界

- 真实 GitHub API 的重试从未发生（生产两次 fetch 都是首次成功）；重试语义由
  假 HTTP 服务驱动，真实网络层仍只有 CI 生产运行。
- `attempts` 是两次调用（列表 + 下载）的**总请求数**；不是「重试了几轮」。
- 上传侧仍是 `actions/upload-artifact`。

## 6. 提交与 CI

- 首次 run **41327072519**：backend / frontend / 容器 job `success`；
  - **windows-backend 失败**：`test_fetch_classifies_missing_and_expired` 用
    `Path.read_text()` 的默认编码读 UTF-8 结果 JSON（中文 `detail`），Windows
    runner 的 cp1252 抛 `UnicodeDecodeError`；已改为显式 `encoding="utf-8"`。
  - **写回 job 失败**：`ModuleNotFoundError: No module named 'scripts'`——
    CI 以 `python3 scripts/fetch_ci_artifact.py` 直接执行，此时 `sys.path[0]`
    是 `scripts/`，不是仓库根；pytest 会加根目录，所以本机 73 条全绿也漏了。
    已补 `REPO_ROOT` bootstrap，并新增**子进程直跑脚本**的用例
    `test_fetch_runs_as_a_script_not_just_as_an_import`。
- 修复后的 CI run：（待推送后回填）

## 7. 本轮教训

1. **失败路径的计数器必须由异常携带**：`_read_with_retries` 成功才 return，
   失败直接抛；`attempts_used += used` 写在 return 之后，于是失败结果的
   `attempts` 恒为 0（M54/实测都咬住）。把 `used` 挂到 `FetchError.attempts`
   上，外层再累加，才算得出来。
2. **「重试次数」要先定义口径**：列表 2 次 + 下载 1 次，是总请求数 3，不是
   「重试 2 次」也不是「每个 URL 各 2 次」；result 字段必须把口径写进文档，
   否则读的人会按另一种口径核对。
3. **重试的排除项与包含项一样重要**：401/403 重试只会把「凭证坏了」延迟三次
   并放大日志；只列 `RETRY_STATUS` 白名单，不写「5xx 以外都重试」。
