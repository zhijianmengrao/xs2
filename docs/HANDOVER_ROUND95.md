# DeterminFlow (xs2) 交接报告 — Round 95（artifact 拉取脚本 + replay 未提交态）

> 第 6 轮。形态：下载侧 `actions/download-artifact` → `scripts/fetch_ci_artifact.py`；
> replay 增加 `--from-worktree`；沙箱失败自动保留。
> 已拍定（用户四选四）：artifact 走脚本拉取、replay 带未提交改动、失败保留现场。

## 1. 一句话结论

R94 §5 的三条边界全部收口：

1. **artifact 下载变成可执行代码**：列表（按 name 精确匹配）→ 下载 zip →
   安全解压，语义由假 HTTP 服务驱动；YAML 只剩一次调用。
2. **replay 能带未提交改动**：`--from-worktree` 把已跟踪文件的暂存/未暂存
   改动打成 binary patch，应用到沙箱；未跟踪文件不进入并提示。
3. **失败自动保留现场**：成功删除、失败/`--keep` 保留。
4. 顺带修掉 R94 的一个真缺陷：**`shutil.rmtree(ignore_errors=True)` 在 Windows
   上删不掉 git 的只读 pack/object，R94 的「默认删除沙箱」其实一直没删掉**——
   R95 的「成功必须不存在」用例第一次把它咬出来；本机 temp 里实测积了 **12 个**
   旧沙箱（最早 19:48），已用修好的 `_remove_sandbox()` 清空。

**语义变更（重要）**：旧接线给 `actions/download-artifact` 加了
`continue-on-error: true`，于是 401/403/5xx/坏 zip 都会被吞成「没有 metrics」，
写回 job 以 0 退出、**静默丢掉一轮历史**。R95 改为：缺 artifact/已过期 → 退出 0；
真实传输错误 → `::error::` + 退出 1（R64：同一退出码的不同来源不得互相冒充）。

## 2. 实现要点

1. `scripts/fetch_ci_artifact.py`：
   - `GET /repos/{repo}/actions/runs/{run_id}/artifacts?name=…` → 按 `name`
     精确匹配（服务端过滤之外再客户端过滤）；
   - `archive_download_url` 下载 zip → 解压到 `--path`；
   - **认证头用 `add_unredirected_header`**：GitHub 的 artifact 下载会 302 到
     blob 主机，把 `Authorization` 带过去会 401（R71 实测）；
   - 解压拒绝绝对路径与 `..`（artifact 是外部输入，不能写出目标目录）；
   - 退出码：0 = 成功/缺 artifact/已过期；1 = 传输/内容错误；2 = 用法。
2. `ci.yml` 写回 job：
   - 新增 `actions: read`——一旦显式声明 `permissions`，未列出的 scope 就是
     none；API 列 artifacts 需要它；
   - 删除 `continue-on-error: true`；fetch 步骤失败就是 job 失败，不再静默。
3. `replay_ci_writeback.py`：
   - `--from-worktree`：`git diff HEAD --binary`（暂存 + 未暂存）→
     `git apply --binary` 到沙箱；
   - 未跟踪文件不进入（工作区的日志/临时脚本不该冒充被测状态），只打印数量；
   - `_remove_sandbox()`：先 `os.chmod(..., S_IWRITE)` 清只读位再删。
4. 沙箱保留：`success && !--keep` 删除；失败或 `--keep` 保留并打印路径
   （失败时标「失败现场」）。

## 3. 用例（+15）

| 文件 | 新增/改动 | 断言 |
|---|---|---|
| `tests/test_fetch_ci_artifact.py` | +9 | 成功解压并带 token；缺 artifact → 0；过期 → 0；列表 5xx → 1；下载 403 → 1；302 到别的主机不带 token；zip `..` 被拒；别的 artifact 不能顶替；缺 repo → 2 |
| `tests/test_replay_ci_writeback.py` | +4 | `--from-worktree` 后 `1 → 2` 且源仓库逐字节不动；未跟踪文件只提示不进入；成功删沙箱；失败（坏 metrics → 4）保留现场 |
| `tests/test_ci_history_writeback.py` | +2（替换 1 条） | YAML 只调用 `fetch_ci_artifact.py`、不再有 `download-artifact`；写回 job 有 `actions: read`；fetch 步骤无 `continue-on-error` 且开关齐全 |

**本机全量**：**2593 passed / 28 skipped / 0 failed（2621 条）**，R94 的 2606 + 15。
首次全量遇到一个既有 flake（`test_plugin_processes.py::test_plain_braces_are_not_treated_as_placeholders`，
单跑与整文件均绿，随后两次全量全绿）；不影响本轮新增用例。

**真实仓库探针**（不是纸面）：`replay --repo . --from-worktree --dry-run` 输出
`已把工作树未提交改动带入沙箱（23078 字节补丁）`、`118 个未跟踪文件不进入回放`、
`历史 10 → 10 轮；退出码 0`，源仓库 HEAD/工作树未变，成功路径的沙箱目录随后不存在。

## 4. 变异验证（9/9 全咬合）

还原源是当前文件快照（`cp` 备份），不用 `git checkout`（R55 教训）。

| 变异 | 结果 |
|---|---|
| M31 不按 artifact 名称过滤 | 1 红 |
| M32 缺 artifact 当失败 | 2 红（缺 + 过期） |
| M33 认证头用 `add_header`（随跳转） | 1 红 |
| M34 允许 zip 路径穿越 | 1 红 |
| M35 replay 忽略 `--from-worktree` | 1 红 |
| M36 失败也删沙箱 | 1 红 |
| M37 成功也留沙箱 | 1 红 |
| M38 YAML 恢复 `continue-on-error` | 1 红 |
| M39 去掉 `actions: read` | 1 红 |

## 5. 边界

- 假 HTTP 服务只证明**脚本的 API 契约**；真实 GitHub API 的 token 权限、artifact
  zip 的实际目录布局、以及 `upload-artifact`（上传侧仍是官方 action）仍只能由
  下一次 CI 生产运行验证。
- `--from-worktree` 只带**已跟踪文件**的改动；未跟踪文件明确不进入。
- 失败保留的沙箱需手动清理（路径会打印出来）。
- 趋势判据仍未改（R78：只判历史有效，不判好坏）。

## 6. 提交与 CI

- 提交 `ea6e962` 推送后，CI run **41323628155**：backend / windows-backend /
  frontend / container-config / container-build 五个 job `success`；
  **`e2e-history-writeback` 失败**，fetch 步骤报：

  ```text
  ::error::GitHub API 415（…/artifacts?name=e2e-metrics）：
  {"message":"Unsupported 'Accept' header: 'application/octet-stream'.
   Must accept 'application/json'."}
  ```

  - 根因：artifact 下载端点只接受 JSON Accept，真正的 zip 由 302 后的 blob
    主机返回；`octet-stream` 直接被 415。
  - 假服务器不校验 Accept，R95 的 9 条用例全绿也漏了它——已补
    「列表与下载两个请求都必须是 `application/vnd.github+json`」的断言。
  - **这是 R95 语义改动的第一次生产证明**：旧接线的
    `continue-on-error: true` 会把 415 吞成「没有 metrics」并以 0 退出，
    静默丢掉这一轮；现在 fetch 步骤直接红，job 失败。
- 修复：下载请求改回 `application/vnd.github+json`；本机用真实 GitHub API 对
  run 41323628155 重跑 fetch，成功解出 1 个文件（`e2e-metrics.json`，1365 B）。
- 修复提交 `a91fb42`；CI run **41324392700** 六 job 全 `success`：
  - backend **2556 passed / 65 skipped** = **2621**；
  - windows-backend **2592 / 29** = **2621**；
  - 写回 job：fetch 成功、写回成功，历史 **10 → 11 轮**（新增
    `ci-41324392700`，`source=ci`），main 头 bot 提交 `6314310`。
  - 首次失败的 run 41323628155 没有写回（那一轮不计入历史）——失败轮次
    不入库是既有契约；修复只影响后续 run。

## 7. 本轮教训

1. **「默认删除」必须由「目录不存在」的断言来证明**：R94 的用例只断言输出，
   `shutil.rmtree(ignore_errors=True)` 在 Windows 上遇到 git 的只读对象会静默
   失败——本机 temp 里积了 12 个旧沙箱。一个防护（删除）把失败转换成了成功
   （ignore_errors），它就不是防护（R71 同类教训）。
2. **`continue-on-error` 会把「传输坏了」变成「没有数据」**：两者在写回 job
   眼里都是「本轮不入库」，但处置完全不同——一个该修 CI，一个正常跳过。
   这条与 R64「同一退出码不同来源」是同一个错误的两种外观。
3. **302 去认证头要用机制保证，不要靠调用方记得**：`add_unredirected_header`
   让「跳转后不带 token」成为默认行为，而不是在 redirect handler 里手工删。
