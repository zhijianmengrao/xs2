# DeterminFlow (xs2) 交接报告 — Round 68（形状场景判红后重跑一次：机制的第一步先把「重跑会撞同名工作流」修掉）

> 本轮定位：R65 §8-9 / R66 §9-4（挂账 2 轮）——「计时型场景判红后重跑一次」。
> 基线 `18dcd84`（R67 收尾：Low 2166/113/0、High 2251/28/0（权威）、
> 总用例 2279、前端 490/0）。落地形态：**主线 = 重跑机制**；
> **范围 = 重跑 + 它暴露的同名工作流复用**；**收尾 = 照常推送 + 五 job 逐字核对**。

## 1. 一句话结论

形状/退避场景判红时**再跑一次**，判定口径是**任一次通过即通过**，容差一个都不动。
本轮真正的产出不是这个策略，而是**机制的第一步就撞到的坑**：`Runtime.run_workflow`
对同名 `workflow_id` 会走 `create_workflow` → `workflow_already_exists` → 抛断言，
于是「重试」会把**一次假红**升级成「两次都判红」——比不修更糟。

## 2. 最重要的一件事：本机 e2e 10/10 证明不了重试能用

`run_with_retries` 的第一版只用**假 callable** 测过（第 1 次返回失败、第 2 次返回
通过），全绿。但真实 Runtime 的每一次场景执行都是

```python
self.workflow_manager.create_workflow({"workflow_id": workflow_id, **definition})
if created.get("success") is False:
    raise AssertionError(f"创建工作流失败: {created}")
```

而 `create_workflow` 在工作流目录已存在时返回
`{"success": False, "error": "workflow_already_exists"}`。**重跑同一场景 → 目录还在
→ 第 2 次尝试直接抛异常**，被 `_attempt` 捕获成「场景抛异常」，最终结果是
「共跑 2 次都判红」。也就是说：**这个机制在它唯一需要发挥作用的路径上是坏的**，
而「本机 e2e 10/10」完全看不出来——没有重试时每个场景的 workflow id 都是新的。

修法：`create` 返回 `workflow_already_exists` 时改用 `update_workflow` 覆盖同一份
定义（定义是常量），只有 `update` 返回 `None`（真写不进去）才算环境坏；其它
创建错误照常抛，不顺手吞掉。

**真机探针**（仓库外脚本 `_r68_retry_probe.py`，把 `retry_backoff_shape_is_honoured`
包一层「第 1 次强制判红」，走的是 `_run` 的完整入口）：

```
[e2e] PASS retry_backoff_shape_is_honoured: 退避形状符合配置 [0.4, 0.8]：实测 [0.414, 0.817]；超睡容差 0.30s/段，本次最大超睡 0.017s（第 2 段，余量 17.6 倍）；参考：相邻比值 [1.97]（诊断用，不参与判定）；第 2 次尝试通过（共跑 2 次；第 1 次判红：注入的第一次假红（probe））
[e2e] 1/1 场景通过
[e2e] 其中 1 个场景发生过重跑（判定口径：任一次通过即通过）：retry_backoff_shape_is_honoured
[probe] exit=0 calls=2
```

第 2 次尝试能跑通，本身就证明 `workflow_already_exists` 那条路径被真实走到了。

## 3. 判定口径（写成代码常量，不藏在注释里）

| 项 | 取值 | 依据 |
|---|---|---|
| 哪些场景重跑 | `RETRY_ON_FAILURE` = 四个 `retry_backoff_*` | 计时型判据才有一类与代码无关的失效（调度/JIT/日志的停顿，R64 实测 0.16s）；语义型失败是确定性的，重跑只把同一缺陷展示两遍 |
| 最多几次 | `MAX_SCENARIO_ATTEMPTS = 2` | 真回归两次都失败（判据要求**每一段**落容差内，不靠运气）；单次停顿的假红从 p 降到约 p²；第 3 次只换 ~p³ |
| 通过条件 | **任一次通过即通过** | 不是「两次都要过」（那是把容差内的正常抖动当失败），也不是「取平均」（那是换判据） |
| 容差 | **一律不动** | 重跑是为了让「偶尔慢一次」不冒充「退避没被等过」，不是为了放松阈值 |
| 第一次失败 | 保留在 `ScenarioResult.first_failure`，并写进 PASS 详情 | 重跑后通过 ≠ 没红过；藏掉它，「重跑了几次」在日志里就看不见了 |
| 汇总 | 有重跑就打印「其中 N 个场景发生过重跑」 | 只写单行详情时，快速浏览的人会把「10/10」读成「一次没红」 |

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/e2e_workflow_stub.py` | **+136 / −11** | `ScenarioResult` 加 `attempts` / `first_failure`；`RETRY_ON_FAILURE`、`MAX_SCENARIO_ATTEMPTS`、`combine_attempts`、`run_with_retries`；`_run` 的每场景循环改成注入式 `_attempt`；**`run_workflow` 复用已存在的工作流**；汇总行报重跑 |
| `tests/test_ci_e2e_stub.py` | **+224 / −0** | 64 条（原 53）：9 条重跑策略 + 2 条 `run_workflow` 复用/不吞错 |
| `docs/JUDGEMENT_LEDGER.md` | **+3 / −2** | #8/#9 行的容忍量写明「每次尝试」与重跑口径；§6 加钉住行 |

## 5. 变异验证（四次全部咬合，`cp` 备份还原）

| 变异 | 期望 | 实测 |
|---|---|---|
| `combine_attempts` 只允许**第 1 次**通过（`index > 0` 也 skip） | 「任一次通过」的两条用例必须掉 | **2 failed**（`combine_attempts_passes_when_any_attempt_passes`、`run_with_retries_retries_a_failing_timing_scenario_once`） |
| `run_with_retries` 对**所有**失败场景重跑（去掉 `name not in RETRY_ON_FAILURE` 条件） | 语义型不重跑的用例必须掉 | **1 failed**（`never_retries_a_semantic_scenario`） |
| `combine_attempts` 不再保留 `first_failure` | 首次失败被保留的断言必须掉 | **1 failed**（`combine_attempts_passes_when_any_attempt_passes`） |
| `run_workflow` 退回「任何 create 失败都抛」 | 同名复用用例必须掉 | **1 failed**（`run_workflow_reuses_an_existing_workflow_instead_of_raising`，报错点 `e2e_workflow_stub.py:297`） |
| 还原后 | 全绿 | **64 passed**；两个 md5 与备份逐字节相同（`1222f4a2…` / `210f062c…`） |

还原用 `cp` 备份覆写，不用 `git checkout --`（R55 教训）。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2177 passed / 113 skipped / 0 failed**（132.20s） |
| High-IL 全量（权威） | **2262 passed / 28 skipped / 0 failed**（147.68s） |
| 定向：`test_ci_e2e_stub.py` | **64 passed** |
| e2e 全量（本机，无重跑） | **10/10 场景通过**（未打印「发生过重跑」行——本机没有场景判红） |
| e2e 真机探针（强制第 1 次判红） | **1/1 通过，calls=2**，见 §2 原文 |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |

**对账**：总用例 **2279 → 2290**（+11：`test_ci_e2e_stub.py` 53 → 64）。
Low `2177+113` = 2290、High `2262+28` = 2290。

## 7. 未做与未验证的事（如实记录）

1. **没有在 CI 上再观测到形状判红**：R64 那次是 0.16s 的单段离群，本轮没有新的
   触发。重跑正确性的证据是**结构性的**（§2 的真机探针把窗口强制打开）＋单测，
   不是统计性的。
2. **p → p² 是独立假设**：两次尝试共用同一个进程、同一个 JIT 预热状态，第二次
   通常更快更稳，所以实际收益**不低于** p² 而不是恰好 p²。这一点没有实测数据，
   写在这里是为了不把「约 p²」当成测出来的数。
3. **重跑会把场景时长翻倍（只在判红时）**：最贵的四段场景约 6.2s，最坏 +6.2s；
   全量 e2e 的 10 个场景里最多 4 个计时场景可能重跑，上界约 +18s。CI 里这一步
   没有超时压力（实测整步约 18s）。
4. **`attempts` / `first_failure` 只写进日志与用例**：没有上报到任何指标系统，
   「重跑频率」目前只能靠 grep 日志（与 R62 对「判定力」的处理同一级别）。
5. **未跑 `docker build` / `npm run build` / 未重启 8021 服务**：改动是 e2e 脚本
   与测试，不涉运行时装配。
6. **Desktop Windows 预期不触发**：paths 过滤不含 `scripts/`、`tests/`、`docs/`。
7. **R60~R63 的重导仍被数据卡住**：`run-*.json` 仍是 40 个，最新
   `run-dfe789fd.json` 仍是 `2026-10-28 08:34`。

## 8. 下一轮候选

1. **判据容忍量的「翻转点」验证**（R65 §9-5 的另一半）：登记页上的每个容忍量都
   应该能用「输入在边界两侧各挪一点，判决翻转」钉住，而不只是「与代码常量相等」。
   R68 的重跑属于「对同一输入多测一次」，与翻转点正交——两者可以一起测。
2. **有新 run 后再重导一次**（R60 §7-1 起的直接后续）：仍被数据卡住。
3. **`p=1.0` 的真实数据验证**（R53 §11-4）：仍缺真实全失败快照。
4. **重跑频率的可观测性**（本轮 §7-4 的直接后续）：如果 CI 上重跑开始频繁出现，
   说明容差（0.30s）已经贴着环境抖动的边界，那时要回头改的是容差或场景预算，
   不是继续加重试。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜容忍
7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定，CI 不写回仓库）。

## 9. 推送与 CI 核对

（待推送后补记）
