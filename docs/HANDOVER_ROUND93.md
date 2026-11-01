# DeterminFlow (xs2) 交接报告 — Round 93（历史条目来源标注）

> 第 4 轮。形态：`record` 写 `source`（`ci`/`local`）；`validate_history` 校验
> 已知值；`check` 增加一行来源分布（只读展示）。

## 1. 一句话结论

R88 之后历史里同时有两种来源：本机显式导出与 CI 写回。此前只能靠 `run_id`
的形状（`ci-*` vs 时间戳）**猜**。R93 让条目自己说：

```json
{"run_id": "ci-41303273571", "exported_at": "...", "source": "ci", ...}
```

- 旧条目没有这个字段：**合法**，按「未标注」统计，不根据 run_id 反推；
- 新条目：本机默认 `local`，CI 写回显式传 `ci`；
- `check` 打印 `来源：CI n / 本机 m / 未标注 k（共 N 轮）`——**只展示，不判判决**。

## 2. 实现要点

1. `SOURCES = ("ci", "local")`；`record(source="local")`，非法值返回 **2**（用法）。
2. `validate_history`：`source` 缺失合法；出现但不在 `SOURCES` 里 → `HistoryError`
   （退出 4）。未知值不是「未标注」，是**数据坏了**。
3. `render_sources(history)` + `check()` 多打印一行；不改变退出码。
4. 写回脚本 `history.record(..., source="ci")`——来源由入口决定，不由使用者记得传。

## 3. 生产证据（不是纸面）

R93 的 CI 写回（run 41303273571，checkout `35e6ce0`）第一次写出带来源的轮次：

```
rounds= 8
  2026-11-01T01:51:48+00:00 <未标注>
  ci-41297112074 <未标注>
  …
  ci-41302777624 <未标注>
  ci-41303273571 ci          ← R93 起的写回条目
```

## 4. 用例（7 条）

| 用例 | 断言 |
|---|---|
| `test_record_writes_the_source` | 显式 `ci` 与默认 `local` 都落到条目上 |
| `test_record_rejects_unknown_source` | 非法来源 → 2，文件不创建 |
| `test_validate_history_accepts_legacy_entries_without_source` | 旧条目仍合法 |
| `test_validate_history_rejects_unknown_source` | 未知来源 → `HistoryError`（4） |
| `test_check_reports_the_source_mix` | `CI 2 / 本机 1 / 未标注 1` |
| `test_source_report_does_not_change_the_verdict` | 有/无 source 都退出 0 |
| `test_cli_wires_source` | CLI 传 `ci` 生效、传非法值退 2 |

`test_push_succeeds_on_the_first_attempt` 增加断言：写回条目 `source == "ci"`。

## 5. 变异验证（5/5 全咬合）

| 变异 | 结果 |
|---|---|
| M23 record 接受任意 source | 1 红 |
| M24 条目不写 source | 2 红（函数级 + 写回链路） |
| M25 校验器不查 source | 1 红 |
| M26 未标注的被猜成本机 | 1 红 |
| M27 写回入口标成 local | 1 红 |

## 6. 边界

- 旧 8 轮保持「未标注」：不批量回填、不猜来源（回填等于伪造历史）。
- `source` 不是判决输入：坏值在**校验层**拦（4），分布行只展示。

## 7. 提交与 CI

- 提交 `35e6ce0`（原 `cba319a`，因 bot 写回提交 fast-forward 失败后 rebase）。
- CI run **41303273571** 六 job 全 `success`：
  - backend **2534 / 65**（118.12s）= **2599**；
  - windows-backend **2570 / 29**（224.36s）= **2599**；
  - 写回 job：`已记录 run_id=ci-41303273571 … 历史 8/40 轮`。
- 本机全量 **2571 passed / 28 skipped / 0 failed**。
