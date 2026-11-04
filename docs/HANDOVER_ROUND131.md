# DeterminFlow (xs2) 交接报告 — Round 131

> 单 profile。新五轮连推（R130–R134）第 2 轮：**CI 报告层的单行与降级边
> 界**。`ci_reporting.py` 自 R98 起是「一行 summary + 一份机读 JSON，且写
> 失败只告警、不改判决」的唯一实现，三个 CI 脚本都依赖它，但此前零用例。
> 生产判决逻辑零改动；三轮以外的调用方零改动。

## 1. 一句话结论

- 两条真实缺口都会把展示层变成判决层：
  - git stderr / HTTP body 组成的 `detail` 常带换行，直接拼进 step summary
    会伪造出新的列表项（`summary` 的契约是**一行**）；
  - payload 里混入 `Path` 等不可序列化对象时，`json.dumps` 的 `TypeError`
    会逃出 `emit_result`，让整个 job 以 traceback 结束——与「写失败只告警」
    相反；
  - 另外，孤立代理字符会让 `write_text` 抛 `UnicodeEncodeError`，两条写
    路径此前都没有接住。
- 新增 `_one_line`：`run_id` / `reason` / `detail` 的 CR/LF 压成空格再输出
  summary；机读 JSON 里的 `detail` 保持原文（压平只影响展示）。
- `emit_result` 的序列化移进 `try`，`TypeError` / `ValueError` 转成一条
  `结果工件序列化失败（path）：…` 并返回；两条写路径都补上 `UnicodeError`
  降级。临时文件清理行为不变。
- 新增 `tests/test_ci_reporting.py`（11 个函数 / 12 条）。

## 2. 为什么是这一轮

R98 把摘要与机读工件的写出集中到一个模块，R80 又钉住「同一份事实不能写
两处」。但集中后的模块没有直接用例：现有覆盖都从 `writeback()` /
`fetch()` / `replay` 间接经过，只验证单行 detail 的 happy path。

R130 刚刚把「可观测性不得被坏数据判死」补到 `e2e_retry_summary` 的内层；
报告层是同一类边界的另一面：**坏的不是 metrics，而是报告自己的输入**。
`_git_checked` 把 git stderr 整段塞进 `WritebackError`，`fetch_ci_artifact`
把 HTTP body 截 300 字符塞进 detail——它们都可能是多行。summary 是 GitHub
Step Summary 的 Markdown，多行文本会变成新的段落/列表项，读者分不清哪条
是脚本写的结论。

序列化缺口更直接：`emit_result` 只捕 `OSError`，一个 `Path` 就足以让写回
job 在主判决已经成功之后判红。展示层的失败没有资格改判决，也不该用
traceback 淹没真正的结论。

## 3. 实现

### 3.1 契约点

- `_one_line(text)`：`re.sub(r"[\r\n]+", " ", str(text)).strip()`；summary
  的三个字段都先过它。连续换行压成一个空格，首尾空白去掉。
- `emit_summary`：写出前拼行；`except (OSError, UnicodeError)` 只告警
  （`step summary 写入失败（path）：…`）。
- `emit_result`：先序列化再开临时文件——序列化失败不产生半成品；`except
  (TypeError, ValueError)` 打印 `结果工件序列化失败（path）：…` 后返回。
  写块 `except (OSError, UnicodeError)`，仍然 `unlink` 临时文件。
- `default_summary_path` 行为不变：未设置或空串都返回 `None`（空串不是
  当前目录）。

### 3.2 刻意不做的

- **不改机读工件的 `detail`**：压平只发生在人读的 summary；JSON 仍是原文
  （多行保留为 `\n`）。R80 的「reason/detail 两处一致」指同一份事实，
  单行 detail 的逐字一致由现有集成用例继续担保。
- **不转义 Markdown 元字符**：summary 的 `run_id`/`reason` 是固定类别与
  数字 run id；本轮只处理会破坏「一行」结构的换行。
- **不改三个调用方**：`writeback()` / `fetch()` / `replay` 的判决与退出码
  零改动。

## 4. 判据台账

- §6 复核表补一行（R131 的十一条用例）；
- §10.11 新增「报告层：单行与写失败不得判死」一段。

## 5. 验证

- 定向：`tests/test_ci_reporting.py` + `test_ci_writeback_history.py` +
  `test_fetch_ci_artifact.py` + `test_e2e_retry_summary.py` **83 passed**
  （39.32s；新文件 12 条）。
- 本机全量（`core.symlinks=true`，同 R124/R129/R130 口径）：
  **2739 passed / 28 skipped / 0 failed**（2767 条，489.75s）。
- 变异 **M1–M8 8/8**：

  | 变异 | 改动 | 红 |
  |---|---|---|
  | M1 | summary 不压平换行 | 1 |
  | M2 | 序列化失败不降级（`TypeError`/`ValueError` 逃逸） | 2 |
  | M3 | 写失败后不清理临时文件 | 2 |
  | M4 | 机读 JSON 缩进漂移 | 1 |
  | M5 | summary 覆盖而不是追加 | 1 |
  | M6 | 空 `GITHUB_STEP_SUMMARY` 当成当前目录 | 1 |
  | M7 | summary 编码失败不降级 | 1 |
  | M8 | 工件编码失败不降级 | 1 |

  每次 `cp` 还原后 sha256 与备份逐字节相同
  （`8dc94d6750fd277c9bf097d6a2eba52c2ac6c896683ecb1c8927922edc3ad0e0`）。
  日志：`_r131_m1.log` … `_r131_m8.log`。

## 6. CI

- 提交 **`eba19e3`** 推送后 run **41800285110**：**10 个 job 全 `success`**
  （08:32:27→08:49:34 UTC，约 17m07s）。
- backend **2702/65**、windows-backend **2738/29**（均 2767）；
  `replay-ci-writeback` 两平台 **17/17 PASS**（`inject-at-7` exit=1/push=7、
  `budget-8-at-8` exit=0/push=9）；`replay-ci-fetch-chain` 两平台
  **29/29 PASS**。
- 写回历史 **56→57**（`ci-41800285110`，bot 提交 `59f6281`）；本文档回填
  提交预计 **57→58**。

## 7. 边界与遗留

- summary 仍是「只展示」：不判趋势、不判 metrics 业务有效性；业务闸门仍在
  `record` / `check`（退出 4）与各脚本自己的退出码。
- 本轮只动 `scripts/ci_reporting.py` 与测试；`src/`、`web/`、CI YAML 零改动。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`scripts/ci_reporting.py`、`tests/test_ci_reporting.py`、
  R131 文档、PROJECT_INFO、JUDGEMENT_LEDGER。生产判决逻辑零改动。
