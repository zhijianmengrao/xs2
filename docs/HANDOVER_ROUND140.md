# DeterminFlow (xs2) 交接报告 — Round 140（scripts/ 引用面：孤儿清零 + CI 引用可解析）

> 单 profile。R140–R143 四轮（候选制）第 1 轮：**scripts/ 目录的守门人**。
> 删除 5 个 R16 时代孤儿探针脚本，引用面钉成三条判据。生产代码零改动。

## 1. 一句话结论

- **实测缺口（R139 §7 登记）**：23 个 `scripts/*.py` 里 **5 个三面零引用**
  （tests/CI/docs）：`_hw_analyze_smoke.py`、`_hw_bench_r16.py`、
  `_hw_frontend_sim.py`、`_hw_score_matrix.py`、`_hw_setup_welcome.py`，
  全部是 R16 时代（2026-10-23/24）对着本地开发服务器跑的一次性活体探针，
  已被 R49 桩 provider + R50 故障注入取代。R45 清过孤儿，此后 105 轮
  无人守门。
- **删除 5 个孤儿**（git 历史可取回；无任何引用面受影响）。
- 新增 `tests/test_scripts_inventory.py`（3 函数 / 3 条）：
  **V1** 每个 `scripts/*.py` 必须 tests/CI/docs 三面之一可引用，或在
  `ALLOWED_ORPHANS` 豁免清单登记理由（R140 起为空）；**V2a** ci.yml
  （常开闸门）引用的 10 个脚本必须全部在库；**V2b** 桌面管线（上游继承、
  tag-only）的 8 个「已知缺失脚本」引用冻结成清单，新增缺失/补齐脚本都
  要显式改清单。总用例 2922 → **2926**。
- 变异 **M1–M4 4/4** 咬合（M4 双红正确，见 §5）。

## 2. 为什么是这一轮

孤儿脚本是「第二份账」在文件系统里的形态：存在、无引用、无人敢删。
R45 清过一次，但清完没有守门人——5 个 R16 探针就是这 105 轮里重新积累
的。R139 候选制实测后登记为本轮。另一个实测发现顺带入判据：桌面管线
（desktop-macos/desktop-windows/replace-desktop-assets，上游继承）引用
8 个本 fork 没有的脚本——它们按 tag-only 规则不跑就不会碎，但这个
「已知缺失」此前只是部落记忆，现在冻结成清单。

## 3. 实现

### 3.1 删除面

- `git rm` 5 个 `_hw_*` 探针；每个都能在 git 历史（`792be87`、`5da9224`、
  `914fbb0`、`b099f95`、`71acf5b`）取回。它们依赖本地 8021 服务与真实
  供应商密钥，与 R49 之后的桩化 e2e 相比无保留价值。

### 3.2 `tests/test_scripts_inventory.py`

- **V1**：引用面语料 = tests/*.py ∪ .github/workflows/*.yml ∪ docs/*.md
  的全文；`ALLOWED_ORPHANS` 空清单 + 豁免必须带理由；豁免过期也红。
- **V2a**：ci.yml 引用的脚本全部在库——常开闸门引用缺失 = job 当场碎。
- **V2b**：三条桌面管线的缺失引用集合逐文件冻结（macOS 6 / Windows 6 /
  replace 1，去重 8 个）——补齐脚本或新增缺失引用都判红，显式改清单。

### 3.3 刻意不做的

- **不把 verify_release 接进 CI**：ci.yml 本就不引用它（R132 有意保持
  手工闸门）——首轮变异 M2/M4 误拿它当靶子没咬，实测后才纠正靶标。
- **不钉桌面管线引用的存在脚本**（桌面 yml 里在库的引用由 V2b 的
  集合等式间接覆盖缺失面，存在面交由各自 job 的 tag-only 运行时自证）。
- **不动 .sh/.ps1**（docker-entrypoint.sh、humanware_banner.ps1 由
  Dockerfile/文档自然约束）。

## 4. 判据台账

- §10.13 同族补一段（文件系统引用面：孤儿 V1 + CI 引用 V2a + 桌面冻结
  V2b）。

## 5. 验证

- 定向：`tests/test_scripts_inventory.py` **3 passed**（0.08s）。
- 本机全量：**2897 passed / 1 S3 红 / 28 skipped**（2926 条）——S3 的
  `pytest --collect-only` 子进程采到**实时磁盘**，而 R141 的测试文件在
  全量运行中途入树，行值（2926）与子进程收集数（2977）错位。CI 上
  R140 提交树无 R141 文件，S3 应恰等。**教训：全量运行期间不得增删
  测试文件**（S3 的口径是活磁盘，这是特性也是纪律）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 新增孤儿脚本 | V1 红 |
| M2 改名 ci 引用的 `smoke_container.py` | V2a 红 |
| M3 desktop-windows 新增缺失引用 | V2b 红 |
| M4 补齐冻结清单里的 `create_update_manifest.py` | V1+V2b 双红（孤儿 + 清单失真，两判据各司其职） |

内存快照还原后 sha256 逐字节相同（M2 的还原曾把名字写错成
`smoke_container2.py`，被下一轮变异的红当场暴露——还原本身也要核对，
教训同 R133 §5 一族）。

## 6. CI

- 提交 **`e80d78b`** 推送后 run **41902407692**：写回历史 **69→70**
  （bot `450e414`）。R141 回填。
- 本篇 docs 回填并入 R141 提交；其 run 执行 **70→71**。

## 7. 边界与遗留

- V1 的语料含 handover 历史文档：脚本被历史文档提及即算「有出处」，
  不要求活文档——历史是合法出处，孤儿判定只针对零记载。
- V2b 清单是快照：上游管线改造（把脚本带进 fork）时须显式改清单，
  那正是要人来做的决定。
- R141 预告（已实测）：本机 28 条 skip 的 reason 分布未成清单，
  `pytest -rs` 机读化在 R141 落地。

## 8. 提交

- 改动：删除 5 个 `scripts/_hw_*.py`、新增
  `tests/test_scripts_inventory.py`、R140 文档、PROJECT_INFO、
  HANDOVER_INDEX。生产代码零改动。
