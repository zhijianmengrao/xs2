# DeterminFlow (xs2) 交接报告 — Round 99（回放内制造 push 拒绝/冲突）

> 第 5 轮。形态：`replay --reject-pushes N` / `--conflict` / `--result-json`；
> 在沙箱 origin 上真实制造服务端拒绝与 history.json 冲突。

## 1. 一句话结论

前四轮把「下载 → 写回 → 结果」搬进可执行代码；R99 把**失败路径**也搬进回放：

- `--reject-pushes N`：沙箱 origin 装 `pre-receive` 钩子，前 N 次 push 被拒
  （计数器在 `$GIT_DIR/replay-reject-count`）——重试/rebase 分支在完整
  fetch → writeback 链路里第一次被本地走过；
- `--conflict`：先在 origin 上推一轮**合法**的 `history.json`，写回 push 必被
  拒、`pull --rebase` 冲突，R90 的「丢弃本地提交→reset→重算」路径被真实触发；
- `--result-json`：把写回的机读工件透传出来，`push_attempts` 在端到端演练里
  可断言（被拒一次 = 2）。

## 2. 实现要点

1. `_install_rejection_hook(origin, N)`：`#!/bin/sh` 钩子读计数器，`n < N` 时
   `n+1` 写回并 `exit 1`；钩子消息写 stderr。
2. `_create_conflicting_round`：从 origin 克隆 `other`，读 `work` 的合法历史，
   追加一条 `replay-conflict`（1 场景、全通过），`validate_history` 通过后
   commit + push 回 origin。
3. 顺序：worktree patch → conflict（先推冲突轮）→ reject hook（避免把冲突
   那一推也拒掉）→ writeback。
4. `replay` 新增 `result_path` 透传给 `writeback.writeback`。
5. `main` 拒绝负的 `--reject-pushes`（退出 2）。

## 3. 用例（+5）

| 用例 | 断言 |
|---|---|
| `test_replay_simulates_a_rejected_push_once` | 前 1 次被拒 → 第 2 次成功；result `push_attempts=2`、`reason=written`、`rounds=1` |
| `test_replay_simulates_permanent_rejection` | 3 次全拒 → 退出 1、`push_attempts=3`、`rounds=0`、沙箱保留 |
| `test_replay_simulates_a_conflicting_history` | 输出 `rebase 冲突（第 1 次）`、第 2 次写回成功；`rounds=2`（冲突轮 + 本轮） |
| `test_replay_fetch_and_rejection_work_together` | fetch → writeback → 被拒一次 → 成功，全链 `push_attempts=2` |
| `test_replay_rejects_a_negative_rejection_count` | `--reject-pushes=-1` → 2 |

**本机全量**：**2624 passed / 28 skipped / 0 failed（2652 条）**，R98 的 2647 + 5。

## 4. 变异验证（6/6 全咬合）

| 变异 | 结果 |
|---|---|
| M57 不装拒绝钩子 | 1 红 |
| M58 钩子永久拒绝 | 1 红 |
| M59 不制造冲突 | 1 红 |
| M60 result 不透传 | 1 红 |
| M61 忽略拒绝次数 | 1 红 |
| M62 负值不拦 | 1 红 |

## 5. 边界

- 钩子是 `#!/bin/sh`：Git for Windows 自带 sh 可执行；没有 sh 的环境会装不上
  （CI 不跑 replay，本机已验证）。
- 拒绝/冲突模拟的是**沙箱 origin 的行为**，不是 GitHub 服务端或网络层。
- 持续被拒时沙箱按失败保留；需手动清理。

## 6. 提交与 CI

- 提交 `79ec4cc`；CI run **41328702470** 六 job 全 `success`：
  - backend **2587 / 65**、windows **2623 / 29**，均 **2652**（本地 2652）；
  - 写回 job：历史 **13 → 14 轮**（`ci-41328702470`，`source=ci`），main 头
    bot 提交 `2464c2a`。
- 本文档回填提交本身还会触发一轮 CI/写回（R89 同类语义），预计
  **14 → 15 轮**；这是「一轮 = 一次 main push」的直接后果，不是缺陷。

## 7. 本轮教训

1. **回放的失败路径也要有服务端**：用沙箱 origin 的 `pre-receive` 就能真实
   制造「被拒」，比在 YAML 里写 `for attempt in 1 2 3` 强得多（R89 同一理念）。
2. **冲突必须是一轮合法历史**：直接写坏 `history.json` 会让 R90 的「reset 后
   重算」也产不出合法历史；追加一条通过 `validate_history` 的轮次，最终历史
   才能同时保留冲突轮和本轮。
3. **断言计数词要带边界**：`out.count("push 被拒")` 会把钩子安装提示里的
   「前 1 次 push 被拒」也算进去；改成 `push 被拒（第` 才只数真正的尝试。
