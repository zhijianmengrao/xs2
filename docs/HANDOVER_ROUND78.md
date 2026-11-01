# DeterminFlow (xs2) 交接报告 — Round 78（重跑率跨 run 趋势：只判数据有效）

> 本轮定位：R77 §8-1 / R74 §8-3 的挂账。落地形态：**新增脚本 + 18 条用例 +
> CI 只读接线 + 入库一轮真实历史**；`src/` 与前端零改动，快照闸门 md5 不变。
> 用户拍定的四项：只做趋势 / 本机显式追加 / 有效性硬闸门 / 每次入库运行算一轮。

## 1. 一句话结论

R74 让**单次** e2e 的重跑频率可机读（`--metrics-json` + step summary），但每次
run 都是孤立的：没有历史就说不出「这轮比上轮差」。本轮把每次入库的运行追加成
一轮（快照式、随被判数据入库），本机显式 `record` 后随提交进仓库，CI 只读
`check`——`permissions: contents: read` 不变。

判据边界是**只判数据有效，不判趋势变差**。这不是保守，是判据自己的算术：
e2e 只有 10 个场景，`retried/total` 的取值只能是 0/10/…/100 个百分点。

## 2. 为什么趋势不判红

趋势判决若存在，只能长成「重跑率比上一轮高 X 个百分点 → 判变差」。在 10 个
场景上：

| 想判的差 | 阈值（pp） | 实际能分辨的 | 结果 |
|---|---|---|---|
| 小幅变差 | <10 | 0 次 → 1 次重跑 | 阈值被**一次**重跑越过，等于「≥1 次重跑」 |
| 中等变差 | 10–19 | 1 → 2 次重跑 | 同样只剩「第 k 次重跑」的格点 |
| 更保守 | ≥20 | 2 次以上 | 样本量 10，2 次重跑本身就是小概率事件，趋势没有统计意义 |

任何阈值都落在这个格点上：**「小幅变差」在 10 个场景的分辨率里不存在**——这正是
R63 §3「小量级被判据自己的量级压成单点窗口」的同一条算术。所以本轮的 `check`
**没有 1，也没有 8**：0 退出只表示历史可读，输出必须逐字写出「不判趋势好坏」
与当前分辨率（`100 / 最近一轮 total`，是算出来的量；20 个场景时用例要求它变成
5 个百分点）。

将来场景数上去了，要重新回答「多少轮、多少场景才够」——那是新一轮的判据设计，
不是把本轮的 0 改成 1。

## 3. 设计

### 3.1 存储与轮次

- 历史文件：`tests/fixtures/e2e_retry_history/history.json`（`data/` 被
  `.gitignore` 忽略，随被判数据入库只能放 fixtures）。
- 条目 = metrics payload + `run_id` + `exported_at`；`attempts` 由 scenarios
  求和后入库，读的时候不必重算。
- 同一 `run_id` 重复 `record` 是**覆盖**而不是追加（默认 `run_id` 取入库时间
  戳）——否则修一次数据就会在趋势里凭空多出一轮。
- 窗口 **20 轮**（`MAX_ROUNDS`）：不是快照 `history` 的 5 轮，那个只需要相邻
  两次当基线；趋势要看得见走向。第 21 轮写入时最早一轮掉出。

### 3.2 有效性闸门与退出码

| 情形 | 码 | 处置 | 钉住它的用例 |
|---|---|---|---|
| 历史可读 | 0（**不是**「趋势合格」） | 继续攒轮次 | `test_check_says_it_has_no_judgement_power` |
| 没有历史 / 历史为空 | 3 | 先跑一轮 e2e 并 record | `test_check_exits_three_without_a_history_file`、`..._for_an_empty_history` |
| JSON 读不懂 | 4 | 重录/修文件 | `test_check_exits_four_on_unparseable_history_not_eight` |
| 形状无效 / 计数矛盾 / `run_id` 重复 / 路径不是文件 | 4 | 同上 | `..._contradictory_counts`、`..._duplicate_run_ids`、`..._path_is_a_directory` |
| 判据算术失败 | **不适用** | — | 没有可失败的算术，刻意不设 8 |

**最隐蔽的改法是「跳过坏条目继续渲染」**：剩下的好条目会让趋势表看起来完整，
「0 次重跑」与真实数据一模一样（R74 对 summary 的同一条批评）。因此
`validate_history` 对整份文件校验，不做逐条过滤；
`test_check_rejects_bad_json_even_when_one_entry_would_render` 专门咬这一口。

### 3.3 入口

```
# 本机：跑完 e2e 后显式入库（不会自动发生）
python scripts/e2e_retry_history.py record "$TMP/e2e-metrics.json" \
    --history tests/fixtures/e2e_retry_history/history.json

# CI：只读校验 + 渲染趋势
python scripts/e2e_retry_history.py check \
    --history tests/fixtures/e2e_retry_history/history.json >> "$GITHUB_STEP_SUMMARY"
```

写盘用「临时文件 + `os.replace`」：中途失败不会留下半份历史。`record` 在写入
前先整份校验旧历史——坏历史不能被静默覆盖，那会把「数据坏了」改写成「刚记了
一轮」。

### 3.4 CI 接线与权限

`backend` job 在 e2e summary 之后新增一步 `e2e retry trend (history,
read-only)`，`if: always()`。CI **不写**历史：每 push 都跑 e2e，但入库是本机
显式动作；CI 的职责只有「入库的那份历史仍然可读」。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `scripts/e2e_retry_history.py` | 新增 379 行 | `record` / `check` + 有效性校验 |
| `tests/test_e2e_retry_history.py` | 新增 285 行 / **18 条** | 用例（含 CI 接线） |
| `tests/fixtures/e2e_retry_history/history.json` | 新增，1 轮 | **真实**本机 e2e 数据 |
| `.github/workflows/ci.yml` | +12 行 | 只读校验步骤 |
| `docs/JUDGEMENT_LEDGER.md` | §5 表补模式、§6 +7 行、新增 §7.6 | 登记 |
| `docs/PROJECT_INFO.md` | +1 行 | R78 轮次条目 |
| `docs/HANDOVER_ROUND78.md` | 新增 | 本文 |

**快照闸门 md5 未变**：`1d0e0ac027f3732fad7586cf81ac05fa`。`src/` 与前端零改动。

## 5. 变异验证（十次，`cp` 备份还原）

相关集基线 **94 passed**（新文件 18 + `test_ci_e2e_stub.py` 71 + 台账 5）。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | `check` 把坏历史当通过（0） | **4 failed** | 坏 JSON / 计数矛盾 / 重复 id / 坏条目渲染 四条用例 |
| 2 | `check` 把坏历史当无样本（3） | **4 failed** | 同上四条 |
| 3 | 空历史当通过（0） | **1 failed** | 空历史用例 |
| 4 | 同一 `run_id` 也追加 | **1 failed** | 覆盖用例 |
| 5 | 窗口多留一轮（21） | **1 failed** | 窗口用例 |
| 6 | 去掉 `passed+failed==total` | **1 failed** | 计数矛盾用例（record 层） |
| 7 | 输出不写「不判趋势」 | **1 failed** | 无判定力文案用例 |
| 8 | `bool` 冒充计数（去掉 `_is_int` 的 bool 检查） | **1 failed** | bool 用例（`total=False` + 0/0/0 + 空 scenarios） |
| 9 | CI 去掉 `always()` | **1 failed** | 接线用例 |
| 10 | 跳过坏条目继续渲染 | **4 failed** | 坏 JSON / 计数矛盾 / 重复 id / 坏条目渲染 四条用例 |

每次还原后 `md5sum` 与备份逐字节相同（脚本 `aa71901c…`、`ci.yml` `a3e8136c…`）。

**如实记录**：M1/M2/M10 各有 4 条用例同时判红，**没有唯一咬合者**——这三类
改法破坏的是同一个前提（「历史先整份校验，再渲染」），所以多条用例一起响；
唯一咬合的是 M3–M9，各由一条针对性用例钉住。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`tests/test_e2e_retry_history.py` | **18 passed**（0.43s） |
| 相关集：新文件 + ci stub + 台账 | **94 passed**（3.74s） |
| 本机 e2e（生成第一轮 metrics） | **10/10 场景通过**、0 重跑、19.06s |
| 全量（本机，Low `S-1-16-4096`） | **2237 passed / 113 skipped / 0 failed**（142.66s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| docker build / npm run build | 未跑（无生产与前端改动；CI 会跑 container-build） |

**对账**：总用例 **2332 → 2350**（+18；R77 的 2332 口径）。
Low `2237 + 113` = **2350**。

**入库的第一轮是真实的**，不是构造数据：
`run_id=2026-11-01T01:51:48+00:00`，10/10 通过、`retried=0`、总尝试 10。

## 7. 未做与未验证的事（如实记录）

1. **CI 不回写仓库**（拍定）：每 push 的 e2e 不入库，趋势的轮次密度取决于
   「本机跑 e2e 并提交」的频率；CI 只验证入库那份历史可读。
2. **趋势永不判红**（拍定）：将来场景数增加后要重新做判据设计（见 §2）。
3. **历史校验是严格模式**：`schema` 必须是 1、条目字段必须齐全；将来 schema
   演进要同时改 `validate_history` 与 `entry_from_metrics`，旧文件需要迁移。
4. **未重导快照**：`data/` 下 `run-*.json` 仍 **40 个**，最新
   `2026-10-28 08:34`（本轮实查）。
5. **本会话仍只有 Low profile**：113 skips，28-skip 未复现。
6. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。

## 8. 下一轮候选

1. **`snapshot-meta.json` 的 `OSError` 分支**（R77 §8-5）：把 meta 写成目录 /
   权限拒绝，钉住退出 4 而不是 1/3/8。成本低，是上轮 §7-1 的同型缺口。
2. **`history` 畸形条目纳入判决**（R58 起的缺口）：需先定处置（只报告 / 计入
   退出 4 / 连续畸形轮提示重导），会动 `scripts/`。
3. **重导快照 / `p=1.0` 真实数据**：继续挂账，每轮查一次 run 数。
4. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile 的
   路径，风险最高（可能动 shell 正在用的命名对象）。
5. **趋势判红的前置研究**（不实现）：要回答「场景数到多少、多少轮历史，才能
   让 1 次重跑的台阶不再吞掉判据」；本轮拍定不做。
6. **CI 回写历史**：明确不推荐——要 `contents: write`、会触发二次 CI、PR 分支
   会被写提交；只有在本机追加实在跟不上时才值得重开。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 提交、推送与 CI 核对

（推送后补记）
