# DeterminFlow (xs2) 交接报告 — Round 76（样本量诊断：报告也要排在退出 3/4 之后）

> 本轮定位：R72 §7.2 / R73 §7.3 同一形状的最后一格——`check_per_workflow`
> （逐 workflow 样本量**诊断**）的退出 3/4 前提。落地形态：**测试 + 文档**；
> `scripts/` 与 `src/` 一行未动（闸门 md5 不变）。

## 1. 一句话结论

`check_per_workflow` 在出报告之前有两道门：元数据漂移（退出 4）与无样本
（退出 3）。R54 的用例各测过这两个退出码，但它们与报告**用的不是同一组计数**：

- 漂移用例用 10/1 + 10/1，两条都需 **29.42 个百分点** > `margin=10`，报告
  说不出「达标」；
- 无样本用例只看退出码，没有任何一条检查消息里有没有报告词。

于是「**只有发现薄样本时才查漂移**」这种改法在既有 2326 条用例上**全绿**：
一份全厚（30/0 ×2）的快照配上说谎的元数据会静默通过——而全厚恰恰是日常
快照的形状。本轮补 2 条用例，用同一组计数把门与报告绑在一起。

## 2. 为什么这一条没有翻转点

它不是判据，是诊断（R54 定下）：薄只进报告、**恒退出 0**；能红的只有漂移与
无样本。所以本轮钉的不是「判决翻转」，而是**报告词「达标」不得出现在退出
4/3 的消息里**（「不达标」含「达标」，一条断言覆盖两个词）。

登记页 §2 没有它的行，`_FLIP_POINT_TESTS` 不新增编号；本轮只在 §7.4 登记，
并在 §6 加一行复核指针。

## 3. 设计

1. 复用 R72 的 `_write_rate_snapshot` 造落盘快照，走 `check_per_workflow`
   真实入口（读盘 → 形状校验 → 漂移 → 报告 → 退出码）。
2. `test_metadata_drift_preempts_the_per_workflow_sample_report` 三格：
   - **混合厚度基线**：wf-thin 5/0（需 45.07）+ wf-thick 30/0（需 9.50）→
     退出 0，报告同时说「达标」与「不达标」；
   - **漂移**：同一份内容，元数据把 wf-thick 写成失败 1 次 → 退出 4、消息
     不含「达标」；**全厚快照**（30/0 ×2）同样退出 4——这一格咬住「只在报告
     有话说时才查漂移」；
   - **坏 JSON**：同一份内容 + `{not json` → 退出 4（不是 3，也不是带着报告
     出来的 0）。这一分支此前**全仓库无用例**。
3. `test_no_sample_preempts_the_per_workflow_sample_report`：
   缺元数据文件 / 缺 `per_workflow` 块 / 元数据说有但内容为空 → 三条分支都
   退出 3 且不含「达标」。
4. 模块 docstring 补 R76 一段；登记页新增 §7.4。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/test_judgement_flip_points.py` | **+93 / −1** | 2 条用例 + docstring |
| `docs/JUDGEMENT_LEDGER.md` | **+23 / −0** | §6 一行 + 新增 §7.4 |
| `docs/PROJECT_INFO.md` | **+1 行** | R76 轮次条目 |
| `docs/HANDOVER_ROUND76.md` | 新增 | 本文 |

**闸门脚本 md5 未变**：`1d0e0ac027f3732fad7586cf81ac05fa`（R75 之后的值）。
`src/` 与前端零改动——本轮是**纯测试 + 登记**轮，CI 仍跑全量五 job。

## 5. 变异验证（六次，`cp` 备份还原）

跑的是全部相关用例（基线 **199**）：

| # | 变异 | 实测 | 唯一咬合 |
|---|---|---|---|
| 1 | 只在有薄样本时才查漂移 | **2 failed**：新用例 A（全厚格）+ 既有 `test_three_per_workflow_judges_share_one_drift_message` | A 的全厚格（既有那条是同文案测试，因只改了其中一条判据而红） |
| 2 | 缺元数据文件返回 `EXIT_OK` | **1 failed**：新用例 B | **B（唯一）** |
| 3 | 内容为空时按元数据报告 | **2 failed**：B + R54 `test_per_workflow_reports_no_sample_when_snapshot_has_no_workflows` | 共享 |
| 4 | 缺 `per_workflow` 块当空块继续 | **2 failed**：B + R54 `test_per_workflow_requires_the_per_workflow_block` | 共享 |
| 5 | 漂移消息里先写出报告摘要 | **2 failed**：A 的顺序断言 + 既有同文案测试 | A 的「不含达标」断言 |
| 6 | 坏 JSON 当空元数据继续 | **1 failed**：新用例 A（坏 JSON 格） | **A（唯一）** |

每次还原后 `md5sum` 与备份逐字节相同（`1d0e0ac027f3732fad7586cf81ac05fa`），
还原后相关集 **199 passed**。

**如实记录**：M2 与 M6 是新用例唯一咬合；M1/M5 的增量是**顺序断言**（既有
那条同文案测试会因三条判据不再逐字相同而红，但它一句话都没说「达标」），
M3/M4 与 R54 共用同一批分支——不声称唯一覆盖。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`-k "sample_report"` | **2 passed** |
| 相关集：msys + ledger + flip points + live snapshot gate | **199 passed**（5.73s） |
| 全量（本机，Low `S-1-16-4096`） | **2215 passed / 113 skipped / 0 failed**（131.15s，最终代码复跑） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm run build | 未跑（闸门不在 e2e 链路；CI 会跑 container-build） |

**对账**：总用例 **2326 → 2328**（+2）。Low `2215+113` = **2328**。

## 7. 未做与未验证的事（如实记录）

1. **只对齐了 `check_per_workflow`**：`history` 的畸形条目仍由
   `_history_entry_counts` 跳过并计数（R58 起），不参与判决。
2. **没有形状用例**：字符串 bucket / 布尔 / 负值的拒绝属于 R75 的 §9，
   本轮不重复（`_per_workflow_shape_error` 的三条判据共用）。
3. **坏 JSON 只钉了 `check_per_workflow`**：`check_per_workflow_rate` /
   `check_per_workflow_regression` 的同一分支仍无用例（同型缺口，挂账）。
4. **本会话仍只有 Low profile**：28-skip 未复现。
5. **未重导**：`run-*.json` 仍 **40 个**，最新 `2026-10-28 08:34`（本轮实查）。
6. **未跑 docker build / npm run build / 未重启 8021**：`src/` 与前端零改动。

## 8. 下一轮候选（含本轮拍定的两条）

1. **重跑率的跨 run 趋势**（R74 §8-3）：**存储位置已拍定——随被判数据入库
   （快照式）**，不走 CI artifact（检出临时，等于永远只有 1 轮）。仍不是
   纯测试改动。
2. **重导快照 / `p=1.0` 真实数据**：**拍定继续挂账**，每轮查一次 run 数
   （当前 40 个 / 最新 2026-10-28 08:34）。
3. **msys 对象 ACL 的跨会话对照实验**（R70 §7-1）：唯一能复现稳定 profile
   的路径，可能动正在被 shell 使用的命名对象，风险最高。
4. **`check_per_workflow_rate` / `_regression` 的坏 JSON 分支**：本轮新发现
   的同型缺口（§7-3），成本低。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 9. 推送与 CI 核对

（待推送后补记）
