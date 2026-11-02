# DeterminFlow (xs2) 交接报告 — Round 104（全链 job 上 Windows）

> 单 profile。把 R103 §8 的第一条边界做完：`replay-ci-fetch-chain` 与 replay
> 主 job 同平台矩阵。顺带把 R103 声称「反斜杠已归一」的 zip 路径规则补上
> 用例，并堵住 Windows 驱动器相对路径。零 `src/`、`web/` 改动；
> `MAX_ROUNDS`、失败沙箱策略、写权限归属都不动。

## 1. 一句话结论

- **全链 job 双平台**：`replay-ci-fetch-chain` 改 os 矩阵
  （ubuntu-24.04/python3 + windows-latest/python），与
  `replay-ci-writeback` 同一组 include；`fail-fast: false`、timeout 10→15、
  `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`、两个 step 都显式 `shell: bash`、
  驱动用 `"$PYTHON"`、artifact 名带 `${{ matrix.os }}`。
- **路径规则硬化**：`fetch_ci_artifact._extract` 在「绝对路径 / `..`」之外
  增加「任一 path part 含 `:`」拒绝——Windows 把 `Z:foo` / `Z:\foo` 当
  驱动器相对路径，`Path.joinpath` 会重置盘符把文件写出目标目录。
- **R103 的「反斜杠已归一」没有用例**：补测试时发现最初的嵌套反斜杠用例
  在 Windows 上即使删掉 `replace` 也会通过（`WindowsPath.joinpath` 本来
  就把 `\` 当分隔符）；改用 fake archive + `..\evil.txt` 才钉住
  「不归一 → `..` 判定被绕过」。
- 用例 **+6 → 2688**；本机 **2660 passed / 28 skipped / 0 failed**
  （221.24s）。R103 为 2654/28（2682）。
- **变异 M86–M92 7/7 全咬合**；M92 首测 MISSED，换用例后才咬住（§7）。

## 2. 实现要点

### 2.1 全链 job 双平台

`replay-ci-fetch-chain` 与 `replay-ci-writeback` 用同一组矩阵：

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - os: ubuntu-24.04
        python: python3
      - os: windows-latest
        python: python
runs-on: ${{ matrix.os }}
timeout-minutes: 15
env:
  PYTHONUTF8: "1"
  PYTHONIOENCODING: utf-8
```

Windows runner 默认 shell 是 pwsh，`code=0` / `|| code=$?` / `if [ ... ]` /
`exit $code` 都不认，所以驱动步骤与 `git checkout -B main` 都显式
`shell: bash`（Git for Windows 自带 bash/sh）。解释器名由矩阵给：
`PYTHON: ${{ matrix.python }}`，run 里用 `"$PYTHON"`——windows-latest 没有
`python3` 这个命令名。上传 artifact 名改为
`replay-fetch-result-${{ matrix.os }}`，否则两条矩阵腿会在同一个 run 里
撞名（upload-artifact v4 同名上传失败）。

### 2.2 路径规则硬化

`_extract` 的判定变成三条：

```python
relative = PurePosixPath(info.filename.replace("\\", "/"))
if (relative.is_absolute() or ".." in relative.parts
        or any(":" in part for part in relative.parts)):
    raise ArtifactInvalid(...)
```

冒号规则的理由不是洁癖：Windows 把 `Z:foo` / `Z:\foo` 当**驱动器相对
路径**，`Path.joinpath` 会在中途重置盘符（`destination / "Z:" / "evil.txt"`
→ `Z:evil.txt`），文件写出目标目录；artifact 是外部输入，必须能在两个
平台安全解压，而冒号在 Windows 文件名里本来就非法。

一个平台事实：**Windows 的 `zipfile` 在读取时已经把 `\` 归一成 `/`**
（`ZipInfo._sanitize_filename` 把 `os.sep` 换掉），POSIX 不会。因此：

- e2e 夹具在 Windows 上造不出带反斜杠的 zip 条目；
- 生产代码的 `replace("\\", "/")` 在 POSIX 上仍然是真实分支；
- 要跨平台钉住 `_extract` 自己的规则，只能用 fake archive 直接驱动
  （`tests/test_fetch_ci_artifact.py` 的 `_FakeZip` / `_FakeZipEntry`）。

### 2.3 用例

- `tests/test_ci_replay_wiring.py`：
  - `test_fetch_chain_job_runs_on_the_same_platforms_as_replay`：runs-on
    矩阵、include 与 replay job 完全一致、`fail-fast: false`、
    `PYTHONUTF8`/`PYTHONIOENCODING`、timeout 边界；
  - `test_fetch_chain_job_uses_bash_and_the_matrix_python`：`shell: bash`、
    `PYTHON` 环境变量、`"$PYTHON"`、且不含 `python3 scripts/...`；
  - 既有上传用例改为钉 `replay-fetch-result-${{ matrix.os }}`。
- `tests/test_fetch_ci_artifact.py`：
  - `test_extract_rejects_backslash_traversal`：fake archive 的
    `..\evil.txt` 必须按「非法路径」拒绝（两个平台同一条规则）；
  - `test_zip_windows_drive_paths_are_rejected`：参数化
    `Z:\evil.txt`、`Z:evil.txt`、`dir/Z:\evil.txt`，退出 1、reason
    `artifact-invalid`、stderr 含「非法路径」、目标目录外无文件。

## 3. 用例（+6）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_ci_replay_wiring.py` | 2 | 全链矩阵与 replay 完全一致；驱动步骤 `shell: bash` + `$PYTHON` |
| `tests/test_fetch_ci_artifact.py` | 4 | 反斜杠穿越拒绝 1 条；驱动器相对路径 3 个参数格 |

**本机全量**：**2660 passed / 28 skipped / 0 failed**（2688 条，221.24s）。
R103 为 2654 passed / 28 skipped（2682）。

## 4. 变异验证（7/7 全咬合）

| 变异 | 结果 |
|---|---|
| M86 fetch matrix 去掉 windows | **1 红**（矩阵与 replay 一致性用例） |
| M87 `"$PYTHON"` 改回 `python3` | **1 红**（bash + matrix python 用例） |
| M88 去掉驱动步骤 `shell: bash` | **1 红**（同上） |
| M89 去掉 job 级 `PYTHONUTF8` | **1 红**（矩阵用例） |
| M90 上传名去掉 `-${{ matrix.os }}` | **1 红**（上传用例） |
| M91 `_extract` 去掉冒号校验 | **3 红**（驱动器路径三个参数全红） |
| M92 `_extract` 去掉反斜杠归一 | **1 红**（`..\evil.txt` 穿越用例） |

M92 第一次跑是 **MISSED**：当时的用例用 `nested\e2e-metrics.json`，在
Windows 上即使删掉 `replace` 也能通过，因为 `WindowsPath.joinpath` 本来
就把 `\` 当分隔符。换成 `..\evil.txt` 后，没有归一就会让 `PurePosixPath`
把整段当成一个普通 part，`..` 判定被绕过、文件写出目标目录，用例才真正
咬住。还原全部用 `cp` 备份并核对 sha256：ci.yml `f90ff13e…`、
fetch_ci_artifact.py `1b826dd5…`，逐字节相同（**没有** `git checkout --`）。

## 5. 边界

- 全链仍只在 main push 且 backend success 时跑；PR 不产生
  `e2e-metrics` artifact，跑了也只会得到 `artifact-missing`。
- Windows 腿依赖 Git for Windows 的 bash/sh；拒绝钩子 `pre-receive` 也走
  同一套（`newline="\n"`，R103 已修）。
- `zipfile` 的平台归一化意味着「e2e 下载带反斜杠 zip」在 Windows 上无法
  构造；fake archive 只验证 `_extract` 自己的规则，不替代真实下载路径。
  驱动器路径用例走的是真实 `fetch.main` + 假 HTTP 服务。
- 测试里的 `Z:` 是刻意的：驱动器相对路径在 `C:` 上会在变异演练时写系统盘；
  `Z:` 与 `C:` 走同一条 `windows.drive` 逻辑。
- 没有改 `MAX_ROUNDS`（保持 40）；失败沙箱自动 GC、拒绝×冲突组合、保留期
  策略仍未做。
- 写权限仍只属于 `e2e-history-writeback`；全链 job 仍 `contents: read` +
  `actions: read`，不跑 pytest/e2e/npm/docker。

## 6. 提交与 CI

- 提交 `ff29973`（`feat(R104): 全链 job 上 Windows`），显式路径 add，
  4 文件 +136/−7；`config/skills_config.json` 的外来改动保持未提交。
- 本机全量：**2660 passed / 28 skipped / 0 failed**（2688 条，221.24s）。
- CI run **41399731230**：**10 个 job run**（8 个定义；replay 与
  fetch-chain 各两平台）全 `success`（06:24:44→06:31:57，约 7m13s）——
  backend **2623/65**、windows-backend **2659/29**（均 **2688**）；
  `replay-ci-writeback` ubuntu/windows 各 **4/4 PASS**（rounds
  24/24/25；永久拒绝 exit 1、rounds 23、末条 `ci-41386175114`、
  push_attempts 3）；`replay-ci-fetch-chain` ubuntu/windows 各
  **5/5 PASS**（`fetched` rounds 24、
  `last_run_id=replay-ci-fetched-ff299738`、push_attempts 1；Windows
  路径 `D:\a\xs2\xs2` 与
  `C:\Users\RUNNER~1\AppData\Local\Temp\replay-ci-writeback-*`，
  artifact 输出含「已下载 1 个文件」）。
- 写回历史 **23 → 24 轮**（`ci-41399731230`、`source=ci`、10/10/0），bot
  提交 `5c786ab`（`[skip ci]`，未自触发）；本文档回填提交预计 **24 → 25**。

## 7. 本轮教训

1. **「已归一」没有用例就只是注释**：R103 §8 这么写，但 `_extract` 的反斜杠
   分支没有任何测试；本轮补测试时才发现驱动器相对路径的缺口。声称一个
   安全规则前，先找到咬住它的用例。
2. **测试可能为错误的理由通过**：嵌套反斜杠在 Windows 上不依赖
   `replace` 也能落成目录（`WindowsPath.joinpath` 把 `\` 当分隔符）。只有
   `..\evil.txt` 能暴露「`..` 判定被绕过」——M92 首测 MISSED 就是直接证据。
3. **平台会替你归一，夹具要先自检**：Windows 的 `zipfile` 读取时已把 `\`
   换成 `/`（`_sanitize_filename`），e2e 在 Windows 上造不出反斜杠条目。
   最初写的 `namelist()` 夹具自检立刻变红，避免了「用例看起来在测、其实
   没测」；改用 fake archive 直接驱动 `_extract`，两个平台钉同一条规则。
4. **矩阵 job 的三件套**：`shell: bash`（Windows 默认 pwsh）、
   `${{ matrix.python }}`（windows 没有 `python3`）、artifact 名带
   `${{ matrix.os }}`（v4 同名上传会失败）。

## 8. 下一步候选

- 永久拒绝与冲突/全链的组合场景（三次拒绝 + 冲突后仍失败）。
- 保留期策略：`MAX_ROUNDS` 40→80，或改成按天滚动（趋势样本）。
- 失败沙箱的自动 GC（当前只清理期望失败场景的现场）。
- （已完成）全链 job 上 Windows。
