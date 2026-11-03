# DeterminFlow (xs2) 交接报告 — Round 128

> 单 profile。五轮连推第 4 轮：**语义指纹截断边界**。`SEMANTICS_TEXT_LIMIT=160`
> 自 R112 存在至今零覆盖——「截断只影响展示，不参与任何判决」这句注释
> 没有用例担保。生产行为零改动（只加测试）。

## 1. 一句话结论

- 新增 `test_semantics_line_truncates_display_but_not_the_record`，
  两半各钉一边：
  - **展示**：`_metrics_semantics` 对 205 字符的 `first_failure` 输出
    前 160 字符 + `…`，全文不出现；
  - **入库**：同一份 metrics 走真实 replay `--keep` 写回，沙箱 history
    里 `fail_1.first_failure` 仍是 205 字符全文。
- 输出行同时断言：截断行出现在日志里、被截掉的 40 个字不在日志里。
- **+1 → 总用例 2738**。

## 2. 为什么是这一轮

截断是展示与数据之间的经典边界：没人担保时，「为了日志好看」的改动会
悄悄把入库内容截短（趋势/审计从此失真），或反过来把整段 e2e 详情塞进
一行日志。两半都要有判据。

## 3. 测试

`tests/test_replay_ci_writeback.py::test_semantics_line_truncates_display_but_not_the_record`：

- 单元半边：`history.entry_from_metrics` → `replay._metrics_semantics`，
  断 `failures == f"fail_1={text[:160]}…"`；
- 端到端半边：`replay.main(--keep)` → `_sandbox_from_output` →
  `history.load_history(sandbox/work/...)`，断全文原样落库。

## 4. 判据台账

- §6 复核表补该用例；§10.9 汇总。

## 5. 验证

- 定向：1 passed（0.63s）。
- 本机全量：**2710 passed / 28 skipped / 0 failed**（2738 条）。
- 变异 **M1–M3 3/3**：
  - M1 `_metrics_semantics` 去掉截断 → 展示半边红；
  - M2 `entry_from_metrics` 把 `first_failure` 截到 160 → 入库半边红；
  - M3 `SEMANTICS_TEXT_LIMIT` 改 10 → 展示半边红（截断点漂移）。
- 变异日志：`_r128_m1.log`、`_r128_m2.log`、`_r128_m3.log`。

## 6. CI

随五轮合并推送（run 待回填）。

## 7. 边界与遗留

- 截断长度 160 是展示参数，改它只需改本用例的期望值；语义行不参与退出码。
- `config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_replay_ci_writeback.py`、R128 文档、PROJECT_INFO、
  JUDGEMENT_LEDGER。生产代码零改动。
