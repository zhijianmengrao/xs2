# DeterminFlow (xs2) 交接报告 — Round 103（四条生产边界收口）

> 单 profile。把 R101 §5 / R102 §8 剩下的四条边界一次做完：永久拒绝进生产
> CI、`--fetch-api-url` 全链进 CI、replay job 上 Windows、驱动改真实 CLI
> 子进程。零产品代码改动（`src/`、`web/` 未动）。

## 1. 一句话结论

- **永久拒绝（三次全拒）进生产 replay job**：驱动新增期望失败场景，断言
  exit 1 / `push-rejected` / 远端轮数与末条不变 / `push_attempts=3`，并数
  **3 次 `simulated rejection`** 证明失败来自钩子而不是传输故障；失败沙箱
  「断言存在 → 清理 → 断言不存在」，不再在 runner 临时目录累积。
- **全链进生产**：新增独立 push-only job `replay-ci-fetch-chain`
  （`needs: backend`、`contents: read + actions: read`），用真实
  `${{ github.token }}` 从本轮 artifact 下载 `e2e-metrics` 再走同一条写回链。
  artifact API 的 run id 与历史 run id 由 `--fetch-run-id` 分开。
- **replay job 上 Windows**：`replay-ci-writeback` 改 os 矩阵
  （ubuntu-24.04/python3 + windows-latest/python），`shell: bash` +
  `PYTHONUTF8=1`；拒绝钩子改为 `newline="\n"`（Windows 文本模式会把 shebang
  写成 CRLF）。
- **驱动改真实 subprocess**：每个场景用
  `python -X utf8 scripts/replay_ci_writeback.py` 跑，捕获 UTF-8 输出；
  argparse 用法错误变成真实 returncode 2、未捕获异常变成 traceback 进
  `output`，`sys.path` 引导第一次被生产驱动覆盖。
- 本机全量 **2654 passed / 28 skipped / 0 failed（2682 条，207.54s）**；
  R102 为 2645/28（2673），**+9** 全部是本轮新增。
- 变异 **M79–M85 7/7 全咬合**；M81 / M82 / M83 各自唯一咬合。

## 2. 实现要点

### 2.1 期望失败场景（永久拒绝）

`Scenario` 扩字段：`expected_exit`、`expected_reason`、`expect_sandbox`、
`output_counts`。`last_run_id` 的期望分两种口径：

- 成功场景：等于本轮 `run_id`（R102 的身份断言）；
- 失败场景：等于**基线末条**——远端没有新轮次，末条不能变。

新增 `permanently-rejected`：`reject_pushes=3`、`rounds_delta=0`、
`push_attempts=3`、exit 1、reason `push-rejected`。除了 `::error::连续 3 次
写回均失败`，还必须出现 **3 次 `push 被拒（第`** 与 **3 次
`simulated rejection`**。后者的理由：任何 msys/传输故障也会让 `git push`
三次非零；不数钩子签名，场景会为错误的原因变绿。

失败沙箱：replay 在任何非零退出时按设计保留现场（`replay：沙箱保留在 …`）。
驱动解析路径、断言是目录、调 `_remove_sandbox`（3 次重试，覆盖 Windows 只读
pack），最后断言路径**真的不存在**；`sandbox_cleaned=False` 或清理后仍存在
都判场景失败。成功场景若留下沙箱同样判红。

### 2.2 `--fetch-api-url` 全链

- `replay_ci_writeback.py` 新增 `--fetch-run-id`（默认等于 `--run-id`）：
  artifact API 用 GitHub run id，历史条目仍用 `replay-ci-fetched-<sha>`。
  旧调用方不传时行为不变。
- 驱动新增 `--fetch-api-url / --fetch-run-id / --fetch-repo / --artifact`。
  给了 URL 就追加 `fetched` 场景（不喂本地 metrics）；URL 与 run id 必须
  同时给出，否则退出 2。
- `fetched` 的期望：exit 0、`written`、rounds +1、`push_attempts=1`、
  `last_run_id=replay-ci-fetched-<sha>`、输出含 `已下载 1 个文件`。
- CI 新 job `replay-ci-fetch-chain`：只在 main push 且 backend success 时跑；
  权限 `contents: read + actions: read`（显式 permissions 下未列出的 scope
  是 none）；`GITHUB_TOKEN: ${{ github.token }}`；上传 `replay-fetch-result`
  （`always()`）。现有 `replay-ci-writeback` 保持零 token、无 `if`、PR 照跑。

### 2.3 Windows 矩阵

`replay-ci-writeback` 改 `runs-on: ${{ matrix.os }}`，matrix include
`{ubuntu-24.04, python3}` 与 `{windows-latest, python}`；job 级
`PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`；驱动步骤 `shell: bash`（Git for
Windows 自带 bash 与 sh）；artifact 名带 `${{ matrix.os }}`；timeout 10→15。
拒绝钩子 `write_text(..., newline="\n")`。

### 2.4 驱动 subprocess 边界

`_invoke_replay(argv)` 用 `sys.executable -X utf8 <repo>/scripts/
replay_ci_writeback.py` 启动，`capture_output` + UTF-8 解码，透传环境（含
token），单场景 180s 超时。每个场景开始前删除陈旧 result JSON，避免子进程
崩溃后读到上一次的结果。`--repo` 在 `run()` 里先 `resolve()`。

失败形态随之改变：argparse 变成 returncode 2（不再捕获 `SystemExit`）、
未捕获异常变成 traceback + 非零（不再捕获 `Exception`），两者都进入
`record.output`。三个原有 fake-main 用例改为 monkeypatch
`_invoke_replay`；新增脚本模式子进程用例钉住 `sys.path` 引导。

## 3. 用例（+9）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_ci_scenarios.py` | 4 | 四场景真实子进程（含永久拒绝的 exit/reason/rounds/末条/push_attempts/沙箱清理）；`simulated rejection` 只出现 1 次必须判红；fetch 参数必须成对（退出 2）；全链 5 场景（fetch run id 命中 API、历史 run id 写回）；脚本模式子进程 |
| `tests/test_replay_ci_writeback.py` | 1 | `--fetch-run-id` 与 `--run-id` 分离：API 命中 GitHub run id，历史条目用写回 run id |
| `tests/test_ci_replay_wiring.py` | 4 | replay job 的 os 矩阵与 `PYTHONUTF8`；全链 job 的 needs/条件/权限/真实 API/token/单一调用点/always 上传 |

既有用例同步更新：四场景的表与摘要计数、窗口边界参数化（永久拒绝的期望
rounds = 基线，末条 = 基线末条，`rounds_clipped=False`）、fake seam 从
`replay.main` 换成 `_invoke_replay`。

**本机全量**：**2654 passed / 28 skipped / 0 failed**（2682 条，207.54s）。
R102 为 2645/28（2673）。

## 4. 变异验证（7/7 全咬合）

| 变异 | 结果 |
|---|---|
| M79 期望失败按成功退出码判 | **1 红**（`test_driver_runs_all_four_scenarios`） |
| M80 `_cleanup_sandbox` 直接返回 True（不删） | **1 红**（同上，沙箱仍在磁盘） |
| M81 去掉 `output_counts` 计数 | **仅** `test_driver_counts_the_simulated_rejections` 红 |
| M82 fetch 用同一个 run id | **仅** `test_replay_separates_the_fetch_run_id_from_the_history_run_id` 红 |
| M83 矩阵去掉 windows | **仅** `test_replay_job_exists_and_is_bounded` 红 |
| M84 `_invoke_replay` 吞掉 returncode | **1 红**（`test_driver_runs_all_four_scenarios`） |
| M85 失败场景的 `last_run_id` 期望成本轮 | **1 红**（同上） |

M79/M80/M84/M85 都由同一条四场景用例咬住（它同时看退出码、沙箱与身份），
不是各自唯一；M81/M82/M83 各有唯一咬合者。还原全部用 `cp` 备份并核对
sha256（**没有** `git checkout --`）。

## 5. 边界

- 全链只跑 main push 且 backend success：PR 不产生 `e2e-metrics` artifact，
  跑了也只能得到 `artifact-missing` → `metrics-missing`。
- 全链缺 artifact 时 fetch 退出 0（`artifact-missing`），replay 继续走
  metrics-missing；驱动按期望 `written` 判红。这是有意的：全链 job 的存在
  就是证明「下载→写回」通，不是「没有 artifact 也算过」。
- Windows 拒绝钩子依赖 Git for Windows 的 `sh`；矩阵若红，先看
  `simulated rejection` 是否出现，区分环境失败与真实拒绝。
- 子进程超时只杀直接子进程；Windows 孙进程由 job timeout 兜底。
- 失败沙箱的「断言后清理」只覆盖期望失败场景；意外失败的沙箱仍保留作为
  诊断现场（R95 的保留策略不变）。
- 没有改 `MAX_ROUNDS`（保持 40）；保留期策略仍未做。
- replay 矩阵与全链 job 都只跑脚本，不跑 pytest/e2e/npm/docker；写权限仍
  只属于 `e2e-history-writeback`。

## 6. 提交与 CI

- 提交 `e4df184`（`feat(R103): 四边界收口`），显式路径 add；
  `config/skills_config.json` 的外来改动保持未提交（提交后工作树仅剩该文件）。
- 本机全量：**2654 passed / 28 skipped / 0 failed**（2682 条，207.54s）。
- CI run **41384694336**：**9 个 job run**（8 个定义，replay 矩阵两平台）
  全 `success`——backend **2617/65**、windows-backend **2653/29**（均
  **2682**）；`replay-ci-writeback` ubuntu/windows 各 **4/4 PASS**
  （rounds 22/22/23；永久拒绝 exit 1、rounds 21、末条
  `ci-41379929177`、push_attempts 3，失败沙箱
  `/tmp/replay-ci-writeback-hba8etr_` 断言后清理）；`replay-ci-fetch-chain`
  **5/5 PASS**（`fetched` rounds 22、`last_run_id=replay-ci-fetched-e4df1849`、
  push_attempts 1，artifact 内 output 同时含 `已下载 1 个文件` 与 `已写回`）。
- 写回历史 **21 → 22 轮**（`ci-41384694336`、`source=ci`、10/10/0），bot 提交
  `82a6eac`（`[skip ci]`，未自触发）；本文档回填提交预计 **22 → 23**。

## 7. 本轮教训

1. **期望失败场景必须同时断言「为什么失败」**：只看 exit 1 + `push-rejected`
   无法区分「钩子拒绝」与「传输坏了三次」。数钩子签名（`simulated
   rejection`）才是判据；否则场景会为错误的原因变绿（R71 同型）。
2. **「清理了」必须由磁盘状态证明**：只记录 `sandbox_cleaned=True` 是自证。
   要断言「存在过」再断言「不存在」，并把这个字段暴露到 result JSON 供用例
   复核（M80 正是这样被咬住的）。
3. **子进程边界会改变失败形态**：argparse 的 2、未捕获异常的 traceback 都不
   再是父进程里的 `SystemExit`/`Exception`。测试 seam 必须跟着换，否则
   fake-main 用例在边界改动后仍在测试一条已经不存在的路径。
4. **Windows 文本模式会把可执行脚本写成 CRLF**：`write_text` 不传
   `newline="\n"` 时 shebang 变成 `#!/bin/sh\r`；Git for Windows 的 sh 不该
   赌运气。任何写 hook/脚本的地方都要显式 LF。
5. **artifact run id 与历史 run id 是两件事**：混用时「下载成功」会静默退化
   成「没有 metrics」（fetch 找不到 artifact 退出 0，writeback 报
   metrics-missing 也退出 0）。身份字段必须分开传、分开断言。

## 8. 下一步候选

- 全链 job 上 Windows（下载 zip 的反斜杠路径已由 `fetch_ci_artifact` 归一）。
- 永久拒绝与冲突/全链的组合场景（三次拒绝 + 冲突后仍失败）。
- 保留期策略：`MAX_ROUNDS` 40→80，或改成按天滚动（趋势样本）。
- 失败沙箱的自动 GC（当前只清理期望失败场景的现场）。
