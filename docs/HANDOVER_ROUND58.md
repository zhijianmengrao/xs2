# DeterminFlow (xs2) 交接报告 — Round 58（per-workflow 硬门槛 + 连续 3 轮 undetermined 的次级信号）

> 本轮定位：R57 §11-1 / §10-4 挂账的 per-workflow 硬门槛（R56 两步走的第二步）。
> 基线：`6fa5c2a`（R57 收尾，Low 2085/96/0、High 2170/11/0（权威）、总用例 2181、
> 前端 490/0）。落地形态由用户拍定四项：**硬门槛接两个 runner**；**连续 3 轮
> undetermined → 提示重导**；**ubuntu + windows 同口径**；**8% 政策上限维持**。

## 1. 本轮最重要的一件事：连续轮数的历史必须随快照入库

硬门槛本身是接线——机制 R56 已实现、已测试（`--fail-on-exceeds`）。本轮真正的
设计问题是**次级信号的历史放在哪**。

先在 CI 里写状态是最自然的想法，但它不成立：CI 检出是临时的，任何在 job 里写
下的文件都会在 job 结束时消失。于是「连续 3 轮」在 CI 里永远等于「1 轮」——
一个写着「在看趋势」的恒绿防护，正是历轮反复批评的形状。

历史因此放进**被评判的那份数据**里：`snapshot-meta.json` 的 `history` 块，由
导出脚本在每次导出时追加（旧→新，封顶 5 轮），闸门只读。它满足三条性质：

1. **当前轮不会数两次**：导出脚本写历史时已经把本轮写进去，闸门只在「最后一条
   与当前计数不一致」时才把当前补成新的一轮（`snapshot_rounds`）。
2. **历史缺失/不匹配时当前轮必须补上**：不能因为「历史里没有这一轮」就少算，
   那会让提示晚一轮出现，而且让「当前是不是判不了」取决于历史是否完整。
3. **历史不参与漂移校验**：历史条目描述的是过去几轮**各自的**快照，拿它们跟
   当前内容比是拿错了尺——每次重导后都会判 4，处置却指向「再重导一次」。

历史条目只记原始计数 `attempts/failed`，**不记判决**：判决依赖 `margin`，而
`margin` 是调用方的参数；把判决焊进数据，重导后就没法用今天的尺子回看历史。

## 2. 硬门槛：什么会红、什么不会

| 情形 | 退出码 |
|---|---|
| 有 workflow 判 `exceeds`，且给了 `--fail-on-exceeds` | 1 |
| `undetermined`（含连续 3 轮以上） | **0**（永远） |
| `per_workflow` 元数据与内容漂移 | 4 |
| 无样本 | 3 |
| `exceeds` 但没给 `--fail-on-exceeds`（报告模式） | 0 |

`undetermined` 不判失败是 R56 §2 定下的纪律，本轮没有改：把它做成失败，红的
是「样本太薄」而冒充「有 workflow 在变坏」，是一个会把处置指向供应商的假红。
次级信号只出现在报告文字里，不改变任何退出码。

真实入库快照在硬门槛下实测（margin=10）：**0 个超出 / 1 个正常 / 8 个样本不足**，
退出 0。全挂合成快照 `tests/fixtures/live_snapshot_exceeds`（两个 40/0 的健康
workflow + 一个 40/40 的全挂者）：1 个超出 / 2 个正常，加开关判 1，不加判 0。

## 3. 反向验证：全挂快照为什么必须是**入库 fixture**

硬门槛在真实快照上恒绿（0 个超出），所以 CI 必须有办法证明它能红。做法是
提交一份**合成快照 fixture**，而不是在 CI 里用 `python -c` 现场造一个：

- 它是可审阅的：三份 run 文件与元数据都在 diff 里，判 `exceeds` 的原因一眼可见；
- 它是**测试与 CI 共用的一份**：`test_the_exceeds_fixture_really_exceeds` 先钉住
  它的判决，CI 那一步才断言「它是 1」——两处用的是同一份数据，不会漂开；
- fixture 被钉住的数字变了（基线算术、margin 默认值、精确界改动），测试先红，
  CI 不会把一个「其实已经判不出来」的数据继续当反向验证用。

`live_snapshot_exceeds` 的判决全部落在区间判据上：全挂者 95% 下界 92.78% 远高于
阈值（留一法基线 0% + margin 10），健康者上界 7.22% 远低于阈值（基线 50% + 10）。

## 4. 次级信号的措辞：只提示，不判失败，也不假装能修好一切

报告里出现的形式（真实快照历史满 3 轮后）：

```
连续 3 轮以上样本不足：<workflow>（连续 N 轮）。**这不是失败**（退出码不受影响），
处置是重导更多 run：python scripts/export_run_samples.py --dest tests/fixtures/live_snapshot --limit 5；
若重导后仍连续不足，说明这些 workflow 的真实数据量本身支撑不了逐 workflow 判决，
需要在文档里接受该限制
```

最后一句是 R56 §10-3 挂账的那件事的正面回答：`export` 这类 workflow 总共只有
10 个 run，物理上补不到 margin=10 所需的样本量。提示不能假装「再导一次就好」，
否则它会变成一条永远无法满足的告示——那与「永远绿的防护」是同一种错误，只是
换成了「永远在喊」。

## 5. 历史覆盖也必须可见（不许用沉默表达「没有趋势」）

- 历史不足 3 轮时报告明说：`快照历史 1 轮（含当前）——「连续 3 轮样本不足」的
  提示需要 ≥3 轮历史，当前未生效`。
- 形状无效的历史条目跳过并计数：`另有 N 条历史形状无效已跳过（连续轮数可能被
  低估…）`。低估比编造一个「看起来连续」的序列诚实。
- 某个 workflow 在历史轮里缺席（覆盖变化）时中断计数，而不是跳过——缺席说明
  那一轮的样本集合不同，「连续」的前提不成立。

入库快照本轮**回填了一条历史**（就是它自己的那次导出，`exported_at` 与计数都
从同一份文件里取），所以下一轮重导后即有两轮，第三轮重导后提示开始生效。回填
命令记录在 §12，可复现。

## 6. 导出侧：追加、封顶、丢弃坏条目

- `HISTORY_MAX_ROUNDS = 5`：提示需要 3 轮，5 轮留两轮余量；每轮只记
  `attempts/failed`，9 个 workflow 约 600 字节，封顶后不到 3KB（快照的职责是
  「一份可读的样本」，不是日志）。
- `carry_forward_history(dest_root)` 在写盘前读目的快照的旧 `history`，形状无效
  的条目丢弃——猜一个形状比丢掉更糟（会让连续性数在一段编造出来的序列上）。
- `--dry-run` 同样读（为的是「先看会写什么」时结论与现实一致），但不写。

## 7. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| Low-IL 全量 | **2082 passed / 113 skipped / 0 failed**（126.33s） |
| High-IL 全量（权威） | **2167 passed / 28 skipped / 0 failed**（140.09s） |
| 前端 `npm test` | **490 passed / 0 fail**（不变，零前端改动） |
| 本机 e2e | 未重跑（本轮零 e2e 相关改动；R56 记录 10/10） |

**对账**：

- 总用例 R57 口径 2181 **+14** = **2195** ✓（Low 2082+113=2195、High 2167+28=2195）
- 新增 14 条 = `test_live_snapshot_gate.py` 85 → **96**（+11，含 1 条替换为 2 条）
  + `test_export_run_samples.py` 14 → **17**（+3）。
- Low-IL 的 passed/skipped 分布与 R57 不同（2085/96 → 2082/113）：17 条用例
  转成 skip（8021 服务本轮未运行等环境前置），总用例数不受影响；High-IL 同因。

### 7.1 推送与 CI 核对（已闭环）

推送 `477eb68`（代码 + 夹具）+ `d024d78`（文档）+ `88aaafd`（本节的 CI 实证）。
直连通道当时不稳（配的 socks5 代理未运行，且 DNS 把 github.com 解析到一个
不可达的 IP），改用「本地 CONNECT 隧道指向可达 IP」推送成功，临时脚本用完即删，
不改任何远端或系统代理配置。

| run | 结果 |
|---|---|
| `CI` **41018667020**（d024d78） | **五 job 全绿**（backend / windows-backend / frontend / container-config / container-build） |
| `CI` **41019944805**（88aaafd） | **五 job 全绿**（同口径；本条是 CI 实证的文档提交，代码未变） |

CI 日志实证（下载日志解码后逐字比对，不是推断）：

- **新步骤在两个 runner 上都真跑了**：ubuntu `backend` 第 11 步与 windows
  `windows-backend` 第 9 步 `Snapshot per-workflow failure-rate gate`，均 success
  （步骤名已从 R56 的 `…report` 改为 `…gate`）。
- **两个 runner 的判决逐字一致**：

  ```
  [live-gate] per-workflow 失败率（留一法基线，margin=10）：0 个超出 / 1 个正常 /
  8 个样本不足无法判定。…快照历史 1 轮（含当前）——「连续 3 轮样本不足」的提示
  需要 ≥3 轮历史，当前未生效
  ```

  windows 日志里中文是 `\uXXXX` 转义，解码后比对；gate 输出逐字相同，
  `OK` 行只多一个平台后缀 `（Windows/Python 3.14）`。
- **硬门槛双向生效真跑**：两个 runner 都打印
  `OK  per-workflow 失败率硬门槛双向生效：真实快照通过，全挂快照触发 1，注入漂移触发 4`。
  这句话只有在「真实快照退出 0 + 全挂 fixture 退出 1 + 漂移注入退出 4」三条
  同时成立时才会打印；全挂那次调用的输出被 `$null =` 收走（预期），由
  `$LASTEXITCODE` 断言。
- **四面用例总数一致**：ubuntu `2131 passed / 64 skipped` = **2195**、
  windows `2166 / 29` = **2195**、本机 Low-IL `2082 / 113` = **2195**、
  High-IL `2167 / 28` = **2195**。

## 8. 变异验证（6 个，全部咬合）

| 变异 | 预期 | 实测 |
|---|---|---|
| 连续轮数不含当前轮（`verdicts[:-1]`） | 红 | ✓ 2 红（连续计数 / 重导提示） |
| 历史条目纳入漂移校验 | 红 | ✓ 2 红（历史不参与校验 / 坏历史报告） |
| 导出不携带旧历史 | 红 | ✓ 1 红（携带与封顶） |
| `undetermined` 触发硬门槛 | 红 | ✓ 2 红（真实快照通过 / undetermined 永不失败） |
| ubuntu 真实判定那次调用丢掉 `--fail-on-exceeds` | 红 | ✓ 1 红（逐次调用检查） |
| 历史封顶失效 | 红 | ✓ 1 红（携带与封顶） |

**还原方式**：`cp` 备份覆盖回去，**不是 `git checkout --`**（R55 的教训：
`git checkout --` 会抹掉整份未提交改动）。还原后三个文件 `diff` 与备份逐字节
相同，受影响的 113 条测试全绿。

第 5 个变异值得说：只删掉**一次**调用里的开关，`_has_flag(run, ...)` 那种「这
一段里出现过开关」的断言照样通过——所以本轮把它改成逐次调用检查
（`_rate_invocations`，先把 `\` 续行拼回一行）。这与 R57 对
`--fail-if-above` 的纪律一致：同一判据在脚本与 CI 两处各写一份时，要测「每一次
调用都带了必要开关」，而不是「这一段里出现过某开关」。

## 9. 本轮改动一览（3 处代码 + 2 处测试 + 1 处 CI + 2 份快照 + 文档）

| 文件 | 变更 |
|---|---|
| `scripts/check_live_snapshot_gate.py` | +170：`UNDETERMINED_ROUND_STREAK`、`snapshot_rounds`、`undetermined_streaks`、`_history_entry_counts`、`_verdicts_of_round`；`check_per_workflow_rate` 的报告里加历史覆盖与重导提示 |
| `scripts/export_run_samples.py` | +52：`HISTORY_MAX_ROUNDS`、`carry_forward_history`、`build_snapshot_meta(prior_history=)` 写入 `history` 块 |
| `.github/workflows/ci.yml` | 两 runner 的失败率步骤改名 `…failure-rate gate`、加 `--fail-on-exceeds`、加全挂快照反向验证（断言 1），漂移验证保留（断言 4） |
| `tests/test_live_snapshot_gate.py` | 85 → 96：连续轮数/历史覆盖/坏历史/历史不参与漂移/回填钉住/全挂 fixture 判决/CI 逐次调用开关/全挂反向验证 |
| `tests/test_export_run_samples.py` | 14 → 17：历史写入、携带与封顶、坏条目丢弃 |
| `tests/fixtures/live_snapshot/snapshot-meta.json` | +43：`history` 块（回填 1 轮） |
| `tests/fixtures/live_snapshot_exceeds/` | 新增：3 个 workflow / 120 次尝试 / 40 次失败（全挂合成快照） |
| `docs/PROJECT_INFO.md` | R58 基线条目追加 |

`config/skills_config.json` 仍是未入库的运行时写入（B23/R36 定性），**不在本轮
改动内**。提交时照例显式按路径 add，排除它。

## 10. 未做与未验证的事（如实记录）

1. **「轮」是导出轮，不是 CI 轮**：同一份快照在 CI 里跑多少次都只算一轮（历史
   不随 CI 运行推进）。这是刻意的——CI 无法写回仓库；若要「每次 CI 都算一轮」，
   需要一个能写回仓库的动作（例如轮次收官时导出），那是另一个设计。
2. **提示对物理上补不到的 workflow 也会发**：R56 §10-3 挂账的同一件事，文案里
   写明处置（重导→仍不足则接受限制），但没有做「理论上限」推断——真实 run 总数
   不在快照里，推断会变成猜。
3. **per-workflow 判据仍只有 `baseline + margin` 一种阈值形态**：没有绝对上限。
   主闸门有 8% 政策上限，per-workflow 没有对应的政策值（每个 workflow 的合理
   失败率不同），本轮不发明一个。
4. **8% 政策上限维持**（用户拍定），未校准；首次校准仍需等真实失败率逼近。
5. **Desktop Windows 未被触发**：paths 过滤只认 `desktop/`、`src/`、`web/`、
   `config/`、`requirements.lock` 与 workflow 自身，本轮改的是 `scripts/`、
   `tests/`、`.github/` 其它文件——预期行为。
6. **未跑 `docker build`**：本机仍无 docker/wsl；`container-build` 在 GHA 上真构建。
7. **前端未跑 `npm run build`**：零前端改动（`npm test` 已跑）。
8. **未重启 8021 服务**：本轮只改脚本与 CI 接线，不涉运行时装配。
9. **新增 fixture 未纳入 `test_snapshot_has_no_content_payload` 的扫描范围**：
   那条测试只扫 `live_snapshot`。新 fixture 由构造脚本生成，只含
   `node_id/status/attempt_history`，但要防它以后被手工扩写——见 §11-1。

## 11. 下一轮候选

1. **把载荷扫描扩到所有 fixture 快照**（§10-9）：一条参数化测试即可，属清理。
2. **8% 上限首次校准**（R57 §10-2）与**主闸门历史基线模式**（R57 §11-2）：
   后者要与绝对上限并存时写清退出码 1 的两种来源。
3. **`min_ratio` 判别力边界的精确定量**（R53 §11-2 / R55 §11-2）。
4. **`p=1.0` 的真实数据验证**（R53 §11-4）。
5. **`workflow_trend` 与 `workflow_health` 合并成一次画像扫描**（R55 §11-3）。
6. **历史轮与 CI 轮的对齐**（§10-1）：若希望每轮都有推进，需要设计一个可写回
   仓库的轮次收官动作；否则接受「导出轮」这个口径。

其余：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；快照保鲜
容忍 7 天维持（R49 确认）。

## 12. 附录：历史块回填命令（可复现）

入库快照的 `history` 块是 R58 回填的，内容就是它自己那次导出（`exported_at`
与计数都取自同一份文件）：

```bash
python - <<'PY'
import json, pathlib
p = pathlib.Path("tests/fixtures/live_snapshot/snapshot-meta.json")
meta = json.loads(p.read_text(encoding="utf-8"))
entry = {
    "exported_at": meta["exported_at"],
    "per_workflow": {name: {"attempts": b["attempts"], "failed": b["failed"]}
                     for name, b in meta["per_workflow"].items()},
}
rebuilt = {}
for key, value in meta.items():
    rebuilt[key] = value
    if key == "per_workflow":
        rebuilt["history"] = [entry]
p.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
```

回填不是必需的：没有 `history` 块的旧快照照样能判，只是报告里会写「当前未生效」，
并在下一次导出时从 1 轮重新积累（`snapshot_rounds` 会把当前轮补成第一条）。
