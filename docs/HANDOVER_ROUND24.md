# DeterminFlow (xs2) 交接报告 — Round 24（维护态第二轮：e2e 宕机语义 + supervisor 竞态兜底 + installation_state 真实证据收口）

> 本轮定位：R23 之后的**维护态第二轮**，候选起点=R23 §9。修复 2 个编号缺陷
> （B15：e2e 中途宕机语义；B16：supervisor stop/spawn 竞态孤儿）+ 收口 1 个
> P3 复查项（installation_state 真实设备名证据）+ 关闭 pool 级语义复查。
> 基线：`a6c2515`（R23 提交），**工作树存在外来未暂存改动**（15 个
> HANDOVER_ROUND*.md 全部被删除，非本轮所为、未提交未恢复，见 §8）。

## 1. 基线终验（改动前，全部通过）

| 验证项 | 结果 | 与 R23 基线对比 |
|---|---|---|
| Low-IL 全量 | **1735 passed / 96 skipped / 0 failed**（107.09s） | 一致 |
| 服务健康 | 8021 `HTTP 200` | 一致（活体） |
| git 状态 | main 领先 origin 1 commit（a6c2515 未推送，R23 遗留） | 与 R23 §8 一致 |
| 工作树 | 15 个 HANDOVER 文档删除（未暂存，外来） | 新发现，见 §8 |

## 2. B15：e2e「服务不可达 → 诚实 skip」路径是死代码

- **现象**：`tests/test_humanware_e2e.py` 的 `_rule_enforced` 依赖
  `status == -1 → None → skip("服务不可达")` 语义，但 `_get` 只捕获
  `HTTPError`——服务**中途**宕机时 `URLError` 直接穿透成未捕获异常，
  表现为一串 traceback 而非设计的诚实 skip。`status == -1` 分支从未可达。
- **复现**：服务运行中手动停服后跑 F5–F7（改动前）→ `URLError` 报错而非 skip。
  （本轮以逻辑单测钉住：`test_b15_get_and_post_report_unreachable_as_minus_one`
  用 monkeypatch 模拟连接拒绝，修复前该用例会以 URLError 失败。）
- **影响范围**：仅测试基建（活体 e2e 套件健壮性）；服务端行为无影响。
  模块级 `_probe()` 在收集期已挡住「服务一开始就不可达」的情形，本缺陷只影响
  「探测通过之后、用例执行中途」宕机的窗口。
- **根因**：`_get`/`_post` 的异常捕获面比 `_probe` 窄（缺
  `except (urllib.error.URLError, OSError)` 分支），而下游探测逻辑按
  「`-1` = 不可达」协议设计，两端约定脱节。
- **修复**：`_get`/`_post` 各补一条与 `_probe` 同款的
  `except (urllib.error.URLError, OSError)` 分支，返回 `(-1, "…服务不可达（类型名）")`。
  语义分工明确：**F5–F7 探测**收到 -1 → None → 诚实 skip；**E1–E7b 功能用例**
  收到 -1 → 断言失败（失败信息含「服务不可达」）——服务中途死了，功能用例
  失败是诚实结果，不伪装成通过。
- **回归测试**（2 条，跟随模块级 pytestmark：服务不可达时与其余 e2e 一起 skip）：
  - `test_b15_get_and_post_report_unreachable_as_minus_one`
  - `test_b15_unreachable_probe_yields_honest_skip`
- **风险点**：无服务端改动；探测缓存/去重语义不变。

## 3. B16：supervisor `stop()` 与 monitor 重启的竞态可遗留孤儿 worker

- **现象**（代码审读发现，窗口极窄但真实）：monitor 的重启循环
  `while not self._closing: await self._spawn()` 在 `_closing` 置位**前**已进入
  `_spawn` 时，`stop()` 先读到旧的死进程引用（跳过 shutdown）、把
  `_process` 清空并 gather monitor；而 `_spawn` 在 gather 期间完成
  `self._process = process`（新一代 worker）——该 worker 从此无人收割：
  runtime 目录被 stop() 顺手删除、租约（`workflow-executor-N.lock`）被它持有
  到控制器进程退出（worker 的 parent-watch 只在父进程死亡时触发）。
  后果：`status=stopped` 与「worker 实际在跑」不符；同进程内再 start 该成员
  会因租约被占而超时。
- **触发条件**：worker 意外死亡后的重启窗口 ∩ stop() 被调用（实践中=应用关闭
  恰逢 worker 崩溃重启），且 stop() 的 `self._process` 读取落在
  `create_subprocess_exec` 与赋值之间——概率极低，但属状态机诚实性缺陷。
- **修复（最小，+7 行）**：`stop()` 在 gather monitor 之后增加兜底分支——
  若 `_process` 又被赋值且存活，复用 `_abort_process()`（terminate→wait→
  kill 兜底→记录退出码→收割进程树）收割之。runtime 目录清理由原有
  `if self._runtime_dir is not None` 分支覆盖（竞态 spawn 建了新目录时同样生效）。
- **伴随诚实性收口**：`start()` 的 except 分支此前不清 `self.client`——
  失败重启后 `identity` 仍报旧世代身份而 `status=stopped`（谎报）。补一行
  `self.client = None`，此后 `identity` 如实抛 `ExecutorUnavailable("not started")`。
- **回归测试**（2 条，`tests/test_executor_runtime_dir.py`，`_FakeProcess` 桩
  确定性复现，无真实子进程）：
  - `test_stop_reaps_worker_spawned_by_racing_monitor`：monitor 任务在
    stop() gather 期间把 `_process` 从死进程换成存活进程 → 断言兜底分支
    terminate 生效、`_process` 复位、status=stopped。
  - `test_start_failure_clears_stale_client`：预置 stale client + mkdtemp 失败
    → 断言 client 复位 None、`identity` 抛 ExecutorUnavailable。
- **R21「改动需动 pool 语义」备注复核**：**可关闭**。B14 修复始终在 supervisor
  内部（准备步骤移入 try），pool 侧 `start()` 的部分失败处理
  （`gather(return_exceptions=True)` + `finally: if not self._started: stop()`）
  经本轮逐行复核无缺陷——所有已创建成员都会被 stop() 收割，retired 租约
  fail-closed 释放。本轮 B16 也未触碰 pool 语义。

## 4. P3 收口：`installation_state()` 真实设备名目录证据（无代码改动）

R23 §9 P3 要求把「`\\?\` 真目录下 `installation_state()` 的 exists()→conflict
路径复核」钉成回归。新增
`tests/test_real_device_name_dirs.py::test_installation_state_conflict_with_real_nul_dir_on_disk`：

- 真实 nul 目录（`\\?\` 前缀创建）躺在 `marketplace-skills/` 下时，
  `installation_state` 对 slug `nul` 报 **conflict**——名字守卫
  （`skill_id_is_safe`）先于 exists()；即便守卫被绕过，真实目录也让
  exists() 恒真 → conflict，两条路径结论一致，无「可安装」谎报（R20 修复面
  在真实文件系统上的直接证据）。
- 对照组：真实存在的 `demo-skill` 目录 → 同报 conflict，钉住 exists() 分支
  本身在真实文件系统上的行为（本地同名不同源 → conflict）。
- 文件桩 `_StubManager` 补 `get_skill() -> None`（installation_state 对合法 id
  会查注册表；对既有 `_trusted_marketplace_skill_path` 用法无影响）。

## 5. 测试用例对账

| 基线 | 改动前 | 净增 | 改动后 |
|---|---|---|---|
| Low-IL | 1735 / 96 / 0 | +5 | **1740 passed / 96 skipped / 0 failed**（109.75s，实测） |
| High-IL | 1820 / 11 / 0 | +5 | **1825 passed / 11 skipped / 0 failed**（实测，权威） |
| 总用例 | 1831（R23 口径） | +5 | **1836** |

净增 5 = B15 逻辑回归 2 + B16 回归 2 + installation_state 真实证据 1。
对账：Low-IL 1735+5=1740；High-IL 1820+5=1825。新增 e2e 逻辑回归依赖服务在跑，
CI（服务不在跑）随模块诚实 skip——与既有 e2e 语义一致。

## 6. 其他验证（改动后全绿）

| 验证项 | 结果 |
|---|---|
| 存储名审计 | `scripts/audit_storage_names.py` → `[clean]`，exit 0 |
| 活体 e2e | 目标文件复跑 17 passed（15 条 E/F 全执行 + 2 条 B15 逻辑），0 skip |
| 前端三连 | lint 0 problems；npm test 6/6（fail 0）；build ✓ 7.62s |
| 目标文件单跑 | `test_executor_runtime_dir.py` + `test_real_device_name_dirs.py` + `test_humanware_e2e.py` → 25 passed |

## 7. 修改文件清单

```
src/workflow/executor_supervisor.py      # B16：stop() 竞态兜底收割（+7）+ start() except 清 client（+1）
tests/test_humanware_e2e.py              # B15：_get/_post 不可达分支 + 2 条逻辑回归（+45）
tests/test_executor_runtime_dir.py       # B16：_FakeProcess 桩 + 2 条回归（+76）
tests/test_real_device_name_dirs.py      # P3：installation_state 真实证据 +1 条（+48/-1）
docs/HANDOVER_ROUND24.md                 # 本文件
docs/PROJECT_INFO.md                     # 项目状态追加 R24 条目 + 测试环境基线行
```

## 8. 风险与遗留问题

1. **外来工作树改动（需维护者决策）**：本轮开工时发现 15 个
   `docs/HANDOVER*.md`（含 HANDOVER_ROUND23.md）在工作树中**被删除**且未暂存，
   非本轮所为。按「并发写入者纪律」（记忆 xs2-parallel-writers）本轮**未提交、
   未恢复**这些删除，仅按显式路径提交自己的文件。删除者意图不明（归档？
   误删？另一会话所为？）——请维护者核查后决定 `git restore` 或提交删除。
   R23 及更早各轮细节仍可从 git 历史读取（`git show a6c2515:docs/HANDOVER_ROUND23.md`）。
2. **R23 提交仍未推送**（`origin/main..main` = 1，本轮再 +1 = 2）：推送需先处理
   git 代理问题（见记忆 xs2-git-push-proxy），且属外发动作，与 R23 §8 同理
   留待维护者确认。推送后核对 CI 四 job（含 windows-backend 的 Storage name
   audit 步骤——R23 O-a 的实跑验证仍悬置）。
3. **HumanwareScoreCard 前端组件**（R19 遗留 P3，连续第五轮顺延）：纯新增 UI，
   与本轮测试/修复主线无关，维持下一轮候选。
4. **POSIX 真跑**（环境依赖，连续遗留）：docker/WSL 均未安装，维持 CI ubuntu
   backend 作为 POSIX 单元级信号。
5. B16 竞态窗口的真实复现（非桩模拟）不可行（需在 create_subprocess_exec 与
   赋值之间注入），桩级确定性回归已覆盖逻辑分支。

## 9. 下一轮迭代计划（Round 25 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | 核查 §8-1 外来删除的意图，恢复或提交；推送 R23+R24 并核对 CI（含 audit 步骤实跑） | 低 | 30min |
| P2 | HumanwareScoreCard 前端组件（契约 §3.3 字段已定，纯新增 UI） | 低 | 2h |
| P3 | supervisor `_spawn` 重启窗口内 `stop()` 的真实并发测试（需可注入 spawn 钩子，评估是否值得） | 中 | 1h |
| P3 | POSIX 真跑（需先装 docker/WSL，环境决策归维护者） | 低 | 环境依赖 |
| P3 | e2e `_post` 中途宕机时 E 系用例的失败信息人因复核（现返回 -1+原因字符串，确认断言输出可读性） | 低 | 15min |

## 10. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest -q                                   # 1735/96/0（改动前基线）
./.venv/Scripts/python.exe -m pytest tests/test_executor_runtime_dir.py \
  tests/test_real_device_name_dirs.py tests/test_humanware_e2e.py -v      # 25 passed（改动后目标面）
./.venv/Scripts/python.exe -m pytest -q                                   # 1740/96/0（Low-IL，改动后）
sp='F:\DeterminFlow x2\xs2\.venv\Lib\site-packages'
MSYS2_ENV_CONV_EXCL=PYTHONPATH PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32" \
  C:/Windows/py.exe -X utf8 -m pytest -q -p no:cacheprovider              # 1825/11/0（High-IL 权威）
./.venv/Scripts/python.exe scripts/audit_storage_names.py                 # [clean] exit 0
cd web && npm run lint && npm test && npm run build                       # 三连全绿
```
