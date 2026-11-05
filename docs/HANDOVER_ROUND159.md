# DeterminFlow (xs2) 交接报告 — Round 159（锁生成头自名：--output-file 与 compile 源文件）

> 单 profile。四轮连推（九）第 3 轮（R156 §7 登记）。P5 只读生成头的
> `--python-version`；生成头里还有两个自描述字段——`--output-file`
> （必须 == 文件自身名）与 `uv pip compile <src>`（源文件必须在磁盘）。
> 拷贝重生成时最容易出现「dev 锁里写着 runtime 锁的名字」；源文件
> 改名则重生成命令直接失效。本轮钉成 **P8**，锁头三要素
> （版本 / 输出名 / 源文件）全部有判据。

## 1. 一句话结论

- `tests/test_python_support_surface.py` 新增 **P8**（实测 R156 §7
  登记，首跑即过）：两份锁生成头的 `--output-file X` == 文件自身名；
  `uv pip compile <src>` 的 `<src>` 在磁盘。实测 runtime 锁头
  `compile requirements.txt … --output-file requirements.lock`、dev
  锁头 `compile requirements-dev.txt … --output-file
  requirements-dev.lock`，全部自名一致、源文件都在。
- 总用例 3055 → **3058**（+1 P8、N3/D1 因本篇与 R158 回填 +2）；
  变异 **3/3**。生产代码零改动。

## 2. 开工复核（实测 2026-11-06）

| 锁 | 生成头源 | 生成头输出 |
|---|---|---|
| requirements.lock | `requirements.txt`（在磁盘） | `requirements.lock`（== 自名） |
| requirements-dev.lock | `requirements-dev.txt`（在磁盘） | `requirements-dev.lock`（== 自名） |

自名不一致是「拷贝重生成」的指纹：把 runtime 锁复制成 dev 锁而不
重跑 uv，`--output-file` 仍写着 runtime 锁的名字——W10/W11 会判
闭包交集，但读不出这份锁**是谁生成的、按哪个源生成的**。

## 3. 实现

- `LOCK_SOURCE_RX`：`^#\s{2,}uv pip compile\s+(\S+)\s` 取命令的源
  文件；`LOCK_OUTPUT_RX`：`…--output-file\s+(\S+)\s*$` 取输出名。
  解析不到显式红（锁头三要素每个都是唯一锚）。
- 判决：输出名 != 文件自身名逐锁列红；源文件 `is_file()` 不存在
  逐锁列红——两类违例合并在一条消息里，双向发声音。

## 4. 判据台账

- 新增 §10.31（P 系续：锁生成头自名，P8），接在 §10.30 之后；
  家族清单不变（仍是 P 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_python_support_surface.py` **8 passed**
  （P1–P8）；相关回归 `test_dependency_sources.py`（W3–W11）、
  `test_requirements_lock_sync.py`（W1–W2）同跑。
- 本机全量：**3030 passed / 28 skipped / 0 failed**（3058 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 runtime 锁头 `--output-file requirements.lock` → `requirements-renamed.lock` | P8 红（输出名 != 自名），P1–P7 绿 |
| M2 dev 锁头 `compile requirements-dev.txt` → `requirements-dev-renamed.txt` | P8 红（源文件不在磁盘），P1–P7 绿 |
| M3 runtime 锁头删掉 ` --output-file …` | P8 红（锚丢失，显式红），P1–P7 绿 |

字节快照还原后 sha256 逐字节相同，3/3 咬合。

## 6. CI

- 提交 **`3d722e3`** 推送后 run **42081644639**：**10 job 全
  `success`**（18:10:17→18:26:35 UTC，约 16m18s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42081644639`，bot 提交 `943caba`）。R160 回填。

## 7. 边界与遗留

- P8 只判生成头的自描述一致性，不重放 uv（闭包内容由 W 系）、不判
  源文件与 pyproject 的同账（W3–W7 已覆盖四源）；`--universal` /
  `--no-annotate` 等旗标不判。
- 四轮连推（九）下一轮 **R160 收口轮（R157–R160 四账）**：四账审计
  + 登记 R161–R164（先实测后登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_python_support_surface.py`（P8）、R159 文档、
  R158 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R159 一条）、
  `JUDGEMENT_LEDGER.md`（§10.31）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
