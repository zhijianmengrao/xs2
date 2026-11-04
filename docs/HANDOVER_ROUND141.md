# DeterminFlow (xs2) 交接报告 — Round 141（skip 分类：每条 skip 必须自述）

> 单 profile。R140–R143 四轮第 2 轮：**「skip 必须带 reason」从纪律变
> 判据**。零生产代码改动。

## 1. 一句话结论

- **实测缺口（R140 §7 预告）**：静态提取 46 个 skip 标记/调用（不含
  本测试自身），全部带 reason——R71（msys skip 归因）以来逐轮积累的
  纪律，但「带 reason」本身没有判据：新加的裸 `@pytest.mark.skip()` 会
  静默让 skipped 计数 +1。
- 新增 `tests/test_skip_reasons.py`（2 函数 / **49 条**：1 语料守卫 +
  48 参数化逐条）：**R1** 每个 `@pytest.mark.skip[if](...)` 必须带非空
  `reason=`；**R2** 每个 `pytest.skip()/fail()` 调用必须带非空消息或
  `reason=` 实参。总用例 2926 → **2975**（+49）。
- 变异 **M1–M3 3/3** 咬合，判红 id 精确到 `文件:行:种类`。

## 2. 为什么是这一轮

R71 的教训是「skipped 计数 +1 而无人知道为什么」——判据被自己的跳过
吞掉。此后每个 skip 都写了理由，但那只是纪律：一条裸 skip 不会让任何
测试红，skipped 的分母悄悄变化。R140–R143 的候选制把它登记为本轮：
skip 的自述从约定变成机判。

## 3. 实现

### 3.1 `tests/test_skip_reasons.py`

- 静态扫描 `tests/*.py`（**排除自身**——首跑正则把本文件 docstring 里的
  示例当代码，自扫自咬，见 §5）；标记（marker）与运行时调用（call）
  两类四元组参数化，ids 精确到 `文件:行:marker/call`。
- **R1**：marker 必须有非空 `reason="…"`；**R2**：call 的平衡括号实参里
  必须有非空首字符串或 `reason=`（无参调用不再逃过——首版正则只匹配
  带引号消息的调用，无参 `pytest.skip()` 漏网，M2 变异暴露后重写为
  平衡括号提取）。
- **语料守卫**：扫描结果为空时显式红（防正则失配后判据空转）。

### 3.2 刻意不做的

- 不钉 reason 的内容（平台归因措辞由 R71 家族测试担保）；
- 不钉 skip 数量（本机 28 / CI ubuntu 65，平台差异大）；
- `pytest.xfail` 不在范围（语义不同）。

## 4. 判据台账

- §10.13 同族补一段（skip 自述判据；扫描器排除自身）。

## 5. 验证

- 定向：`tests/test_skip_reasons.py` **51 passed**（0.52s）。
- 本机全量：与 R140 合并验证（R141 文件入树时机晚于 R140 全量的收集点，
  R140 §5 已如实记录；R141 树的干净全量并入 R142 提交前复跑）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 裸 `@pytest.mark.skip()`（临时文件） | R1 红，id=`_r141_mutate_tmp.py:3:marker` |
| M2 无参 `pytest.skip()` | R2 红，id=`…:4:call`（首版漏网，重写后咬合） |
| M3 `reason=""` 空串 | R1 红，id=`…:3:marker` |

临时文件变异后即删，sha256 还原核对一致。

## 6. CI

- 提交推送后 run `<run1>`：10 job 预计全绿；写回历史 **70→71**。
- 本篇 docs 回填提交预计 **71→72**。

## 7. 边界与遗留

- 扫描是静态正则：字符串拼接出的动态 skip（`getattr` 式）不在射程；
  仓库无此形态（实测）。
- 扫描器排除自身文件的口子写死在 `SCAN_FILES`：未来在测试里写「关于
  skip 的元测试」需同样排除。
- R142 预告（已实测）：PROJECT_INFO 专述 bullet 覆盖 R23–R140 连续
  （R33/34/35 豁免），顺序单调（R133 修的错位防复发）。

## 8. 提交

- 改动：`tests/test_skip_reasons.py`、R141 文档、PROJECT_INFO、
  HANDOVER_INDEX。生产代码零改动。
