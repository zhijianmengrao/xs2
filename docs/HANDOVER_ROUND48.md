# DeterminFlow (xs2) 交接报告 — Round 48（快照保鲜自动化）

> 本轮定位：R47 §8-2 候选「快照保鲜自动化」，按用户选定方向做。
> 基线：`81b3fbf`（R47 收尾，CI 全绿，详见 HANDOVER_ROUND47 §10）。
> 用户同时确认：R47 立即推送（已执行并盯完 CI）；闸门余量保持 **+10 个百分点**；
> 后续 CI e2e 走**桩 provider** 路线（记录在案，本轮未开工）。

## 1. 为什么这一轮值得做

R47 把真实快照闸门接进了 CI，但它在 §5-3 与 §7-2 都写下了同一个缺口：

> 闸门判的是「这批样本的失败率没有恶化」，不是「供应商今天健康」。
> 快照不会自动更新 …… 它**无法察觉「整体数据都旧了」**（旧数据自身仍自洽）。

这是一个**结构性**的失效，不是疏漏：`check_live_snapshot_gate` 现有的退出码
全部基于「元数据与内容是否一致」这一对内部关系。旧快照的元数据与内容**完全
一致**，失败率也没恶化，所以它一路绿灯——而闸门实际在判 2026-10-28 那批 run 的
故事，跟今天的供应商健康状况已经没有关系。

这类「内部自洽所以永远绿」的防护，与 R45 §2.4 引入退出码 3、R47 引入退出码 4
要治的是同一种病。本轮补的是第三种：**判据与被判对象的时间脱节**。

## 2. 落地内容

### 2.1 `--check-stale`：唯一能让「数据旧了」显形的手段

实现放在 `scripts/check_live_snapshot_gate.py`，作为同一脚本的另一种模式，
而不是新脚本。理由：它和失败率闸门共用同一份 `snapshot-meta.json` 与同一个
`--data-dir` 口径，拆成两个文件会让「读哪份元数据」有两处真相。

```
python scripts/check_live_snapshot_gate.py --check-stale
python scripts/check_live_snapshot_gate.py --check-stale --max-lag-days 3
```

判定链：快照的 `exported_at` 与真实 `data/workflows` 里最新一次 run 的时间比，
滞后超过容忍天数（默认 7）即报过期。

**新增退出码 5（快照过期）**，与既有的 0/1/3/4 并列：

| 码 | 含义 | 处置 |
|---|---|---|
| 0 | 尚新（或失败率未超阈） | 无 |
| 1 | 失败率超阈 | 查供应商 / 看哪个 workflow 在涨 |
| 3 | 判不到（元数据缺、真实数据缺、无可用时间戳） | 补数据，**不是故障** |
| 4 | 元数据与内容不一致 | 重导快照 |
| 5 | **快照过期** | 重导快照（`export_run_samples.py`） |

**为什么 5 不能挤进 1**：1 的意思是「判过了，这批数据的失败率不合格」，5 的
意思是「判了，但判的是过期数字」。前者要查供应商，后者只需重导一次——处置
完全不同，混在一个退出码里会让人对着旧快照去追供应商问题。这与 R47 §2.3
引入 4 时的理由（「第三种失效不能挤进 0 也不能挤进 1」）是同一个思路的延伸。

### 2.2 时间戳取「最大值」，而不是只读 `completed_at`

`latest_real_run_time()` 同时看 `started_at` 与 `completed_at`，取两者中更晚的。
两个理由，都是实数据逼出来的：

1. **只看 `completed_at` 会对进行中的 run 失明**。一个 5 分钟前启动、还在跑的
   run，恰恰是「快照已经没覆盖到」的最直接证据，但它的 `completed_at` 是 `None`。
2. **B31 修复前 `completed_at` 恒空**（R40 §2 记录）。历史数据里大量为 `None`，
   只读它等于对旧数据整体失明——而那正是最需要判过期的那批数据。

本机实测：`data/workflows` 里最新的时间戳来自 `run-48c2bfb2` 的
`started_at=2026-10-26T18:11:54+08:00`，其 `completed_at` 为 `None`。
只读 `completed_at` 的话，这个证据会被完全跳过。

### 2.3 明确不接进 CI（这是一个决定，不是遗漏）

`--check-stale` 需要 `data/workflows`（真实 run 记录），而 **CI 检出里没有这个
目录**——它是个不入库的运行时数据目录。接进 CI 的结果只有两种：

- 在 CI 上永远返回退出码 3（判不到），成为一个永远「无法判定」的步骤；
- 或者为了让它在 CI 上「有用」而伪造数据，那么它判的又是别的东西了。

R47 §2.3 已经把「永远绿的防护」列为要避免的东西，本轮照着这条纪律办：**它是
轮次收官动作，不是 CI step**。并加了一条测试反向钉死这件事——
`test_stale_check_is_not_wired_into_ci` 断言 backend job 里没有任何 step 调用
`--check-stale`。这样将来有人「顺手加一步」时，测试会问一句「CI 里没有
data/workflows，你打算让它判什么」。

### 2.4 接进轮次收官清单（`docs/PROJECT_INFO.md`）

R41 起每轮收官固定跑 `provider_failure_profile.py --summary`，R42 追加了
`--fail-if-above` 硬闸门。本轮在同一处追加第三步：

```
python scripts/export_run_samples.py --dest tests/fixtures/live_snapshot --limit 2
python scripts/check_live_snapshot_gate.py --check-stale
```

写进 PROJECT_INFO 而不是只写在交接文档里，因为交接文档会归档、PROJECT_INFO
是常驻的作业指引——「只有人记得」正是 R47 §1 批评手工 fixture 的那条问题。

**顺带形成闭环**：`--check-stale` 与重导动作绑在一起放在收官清单里，形成
「重导 → 判新鲜度 → 判失败率」的三步链。原来只有重导与判失败率两步，
「快照是否覆盖到最新数据」这一问从来没人问。

## 3. 测试（6 条新增，两个变异咬合）

新增在 `tests/test_live_snapshot_gate.py`，总数 11 → **17**：

| 测试 | 钉什么 |
|---|---|
| `test_stale_check_flags_snapshot_older_than_real_data` | 滞后超容忍 → 码 5，且 **5 ≠ 1** |
| `test_stale_check_passes_when_snapshot_is_current` | 快照够新 → 码 0 |
| `test_stale_check_reads_in_flight_runs_not_just_completed` | `completed_at=None` 时靠 `started_at` 仍能判出过期 |
| `test_stale_check_reports_no_sample_when_real_data_absent` | 真实数据缺 → 码 3，**不是 0** |
| `test_stale_check_requires_exported_at` | 元数据无 `exported_at` → 码 3，不默认「够新」 |
| `test_stale_check_is_not_wired_into_ci` | 反向钉：CI 里不得出现 `--check-stale` |

**两个变异，都咬合**（照 R47 §2.3 的纪律做，不只看「测试通过」）：

| 变异 | 预期 | 实测 |
|---|---|---|
| `latest_real_run_time` 只读 `completed_at` | 红 | ✓ 3 条红（含 in-flight 那条） |
| `EXIT_STALE = 1`（过期码混进超阈码） | 红 | ✓ `test_stale_check_flags_...` 红 |

第二个变异能咬合是有意的结果：`test_stale_check_flags_snapshot_older_than_real_data`
里显式断言 `EXIT_STALE != EXIT_GATE_TRIGGERED`。没有这一行，「过期」混进
「超阈」在行为上几乎看不出来（都是非零退出），但在 CI 日志与处置流程里后果
完全不同。

## 4. 本机实跑（全部实际执行）

```
$ python scripts/check_live_snapshot_gate.py --check-stale
[live-gate] 快照尚新：导出 2026-10-28T12:30:35+00:00，真实数据最新
2026-10-28T00:34:30.966378+00:00，滞后 -0.5 天 ≤ 容忍 7.0 天      → exit 0

$ python scripts/check_live_snapshot_gate.py --check-stale --max-lag-days 0
[live-gate] 快照尚新：…… 滞后 -0.5 天 ≤ 容忍 0.0 天                → exit 0

$ # 把 exported_at 改成 2026-09-01 后
(5, '快照已过期：…… 滞后 57.0 天 > 容忍 7.0 天。重导：python scripts/…')  → exit 5

$ # 真实数据目录不存在
(3, '真实数据里没有可用时间戳（…\\nope），无法判新鲜度。本机无 run 记录时
     这是预期结果，不是故障')                                        → exit 3

$ # 元数据删掉 exported_at
(3, '快照元数据缺 exported_at 或无法解析（None）……')                  → exit 3

$ # 失败率模式未受影响
[live-gate] 失败率 3.74% 未超出阈值 13.7%（187 次尝试，余量 10.0 个百分点） → exit 0
```

**滞后为负是正确结果**，不是 bug：快照导出于 2026-10-28T12:30Z，比本机最新 run
（2026-10-28T00:34Z）还新——本机数据自导出后没再产生新 run。这种情况必须判
「尚新」而不是「过期」，否则导出完立刻检查就会误报。

## 5. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_live_snapshot_gate.py` | **17 passed**（11 + 6 新增） |
| Low-IL 全量 | **1905 passed / 96 skipped / 0 failed**（118.74s） |
| High-IL 全量（权威） | **1990 passed / 11 skipped / 0 failed**（134.85s） |
| 变异 1（只读 completed_at） | 3 failed → 咬合 ✓ |
| 变异 2（`EXIT_STALE=1`） | 1 failed → 咬合 ✓ |
| 真实快照闸门（失败率模式） | 3.74% < 13.7% → exit 0 |
| `--check-stale` 四种路径 | 0 / 5 / 3 / 3 全部实跑确认 |

**对账**：

- Low-IL：R47 1899 **+ 6** = **1905** ✓
- High-IL：R47 1984 **+ 6** = **1990** ✓
- 总用例 R47 口径 1995 → **2001**（High passed+skipped：1990 + 11）

本轮零删除，新增 6 条。前端零改动（本轮不碰前端，R47 的 471 条不变）。

## 6. 本轮改动一览（3 改 2 增，含 2 文档）

| 文件 | 变更 |
|---|---|
| `scripts/check_live_snapshot_gate.py` | +114 行：`EXIT_STALE`、`_parse_ts`、`latest_real_run_time`、`check_stale`、`--check-stale` / `--source` / `--max-lag-days` |
| `tests/test_live_snapshot_gate.py` | +82 行：6 条保鲜契约测试 |
| `docs/PROJECT_INFO.md` | 收官固定动作追加「R48 起追加快照保鲜」一节 |
| `docs/HANDOVER_ROUND47.md` | 补 §10 推送后 CI 核对（R47 的两处未验证全部关闭） |
| `docs/HANDOVER_ROUND48.md` | **新增**（本文） |

## 7. R47 的 CI 结果（本轮一并关闭，详见 HANDOVER_ROUND47 §10）

`81b3fbf` 推送后：CI 五 job 全绿；Desktop Windows 的 core 与 full NSIS **都
success**。这意味着：

1. **`backend.rs` 的端口协议重写在真实 Windows runner 上编译通过且冒烟通过**
   ——R47 唯一的编译期风险面关闭。本机 `cargo check` 卡在 `ring` 的 C 编译这件事
   从此不再是该改动的未验证项。
2. **真实快照闸门 step 在 GHA 上判出与本地逐数字相同的结论**（3.74% / 187 次
   尝试 / 阈值 13.7%），`${{ github.workspace }}` 展开与 yml 解析一并验证。

## 8. 未做与未验证的事（如实记录）

1. **`--check-stale` 的 7 天容忍值是一个判断值**，不是统计结论。它假设「每轮
   收官都会重导」。若某段时间不跑轮次（例如停更），快照会自然过期并报 5——那
   是正确行为（快照确实旧了），但需要人知道「这不代表供应商变差」。收紧用
   `--max-lag-days 3`。
2. **仍不判「快照内容是否还代表性」**：`--check-stale` 只看时间，不看快照覆盖
   的 workflow 集合是否还完整。若新增了 workflow 而快照里没有，时间上可能仍
   「尚新」。这需要另一条判据（比对 `data/workflows` 与快照的 workflow 名集合），
   本轮未做——它属于「覆盖度」而非「新鲜度」，混在一起会让退出码语义变糊。
3. **未接进 CI**（§2.3 的决定）。因此 CI 仍然不会发现「快照旧了」。这是有意的
   取舍：CI 无真实数据，接了只能假判。真正的防线是收官清单 + 人的纪律。
4. **未重导快照**：本机快照滞后 -0.5 天（比真实数据还新），无需重导。§2.4 的
   重导动作是给下一轮及以后的收官用的。
5. **未做 macOS 面**：`desktop-macos.yml` 是 tag-only，本次 push 未触发。
   R47 的 `--port 0` 在 macOS 的 `process_group(0)` 路径仍未复核（R47 §8-4 挂着）。
6. **未跑 `docker build`**：本机仍无 docker/wsl（与历轮一致，CI 的
   `container-build` job 已 success）。
7. **`config/skills_config.json` 仍是未入库的运行时写入**（B23/R36 定性，与历轮一致）。

## 9. 下一轮候选

1. **CI e2e（桩 provider）**：用户已选定这条路线（不依赖 secrets、fork PR 可跑、
   验编排不验模型质量）。这是连续三轮（R45/R46/R47）挂着的最有价值缺口，且 blocker
   （凭据设计）已由用户拍定，现在只剩实现。
2. **快照覆盖度判据**：见 §8-2。名字集合差比对，判据与新鲜度分开（可能是退出码 6，
   或并入 5 的说明文字——需要先想清楚它该不该单独成码）。
3. **macOS 的 `--port 0` 面验证**（R47 §8-4）：`desktop-macos.yml` 用同一份
   `entrypoint.py`，但 `process_group(0)` 路径未复核。需要触发一次 tag 或改 workflow
   支持手动触发。
4. **画像对比的多 run 基线**（R47 §8-5）：当前只与「上一次 run」比，看不出「连续
   三次都在退步」。需后端提供多点对比，工作量中等。
5. **循环节点与重试语义区分**（R41 §9-3）：需后端 Core 配合，用户已确认继续挂着。

其余：POSIX 真跑已由 CI 覆盖（R43 结论），大陆下载加速维持现状（R44 结论）。

## 10. 本轮未实际运行

- **未触发 macOS CI**（tag-only，需要打 tag 或改触发条件）。
- **未在 CI 上跑 `--check-stale`**（§2.3 的有意决定，且有测试反向钉死）。
- **未重导快照**（本机快照比真实数据还新，无必要）。
- **未跑 `docker build`**（本机无 docker）。
- **未重启 8021 服务**：改动面纯脚本与文档，不涉及运行时代码。
