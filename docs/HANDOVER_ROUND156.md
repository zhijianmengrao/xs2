# DeterminFlow (xs2) 交接报告 — Round 156（收口轮：R153–R156 四账 + R157–R160 登记）

> 单 profile。四轮连推（八）收口轮：四账审计 + 下一批主题实测登记。
> 本轮无新判据——R153–R155 的三条判据首跑即绿、生产代码零改动，
> 收口的发现是「这四轮钉住的账都没有漂移」本身：README 双语结构、
> 索引 CI 行、锁生成头在钉住之前就已经是对的，判据的价值在于让
> 它们**保持**对。

## 1. 一句话结论

- R153–R155 全部完成：R153 README 双语结构（M1–M4，英文补
  `### Contributors`）；R154 索引 §1 CI 闸门行（S6）；R155 锁生成头
  ↔ Python 下限（P5）。生产代码零改动（R153 只改 README.en）。
- 四轮变异合计 **11/11**（R153 4 + R154 3 + R155 3 + R156 0——收口轮
  无新判据，无变异面）。
- §3 登记 **R157–R160**（全部先实测后登记）：支持面展示层同账
  （P6–P7：README 徽章 ↔ Python 下限、Node 下限 ↔ engines）、
  安装文档引用面（V3：README / CONTRIBUTING / Dockerfile 的锁文件
  引用可解析）、锁生成头自名（P8：`--output-file` 与 compile 源
  文件）、收口。
- 总用例 3046 → **3048**（N3/D1 因本篇与 R155 回填 +2）。

## 2. 四账审计（R153–R156）

| 账 | 内容 | 状态 |
|---|---|---|
| handover | R153 / R154 / R155 / R156 四份，H1 副标题与索引 §4 行同账 | 齐 |
| PROJECT_INFO | R153–R156 四条专述 bullet，H2「至 R156」 | 齐 |
| 判据台账 | §10.25（M1–M4）/ §10.26（S6）/ §10.27（P5）/ §10.28（收口） | 齐 |
| 记忆 | `xs2-round-status.md` 更新到 R156（main、用例数、写回 80/80、R157–R160 登记） | 齐 |

四轮主题与数字：

| 轮 | 主题 | 用例总数 | 变异 | 写回 |
|---|---|---|---|---|
| R153 | README 双语结构（M1–M4） | 3040 | 4/4 | 第 80 条 |
| R154 | 索引 §1 CI 闸门行（S6） | 3043 | 3/3 | 第 80 条 |
| R155 | 锁生成头 ↔ Python 下限（P5） | 3046 | 3/3 | 第 80 条 |
| R156 | 收口 + R157–R160 登记 | 3048 | — | 第 80 条（本篇） |

满窗滚动后写回计数恒 80；四轮写回都落在第 80 条（追加即裁剪最旧）。

## 3. 下一轮候选（R157–R160：全部先实测后登记）

- **R157 支持面展示层同账（P6–P7）**：实测 README.md / README.en.md
  徽章行 `<img src="…/badge/Python-3.11-3776AB…" alt="Python 3.11">`
  （两份同写 3.11），`requires-python` 下限 3.11——徽章是 PyPI 元数据
  之外最显眼的 Python 支持面展示，改下限时没人会记得改徽章；
  `README` 双语各写 `Node.js 22.12+`，`web/package.json` engines 写
  `"node": ">=22.12.0"`——Node 下限此前无人对账，三个 workflow 的
  `node-version: "22"` 也只声明了 major。判据方向：P6 徽章 URL 与
  alt 的 `X.Y` == requires-python 下限；P7 README Node 下限 ==
  engines 下限（major 同账，CI `node-version` 的 major == engines
  major）。
- **R158 安装文档引用面（V 系续 V3）**：R140 的 V1/V2 只管
  `scripts/*.py` 被引用与 ci.yml 引用可解析；README.md（3 处）、
  README.en.md（3 处）、CONTRIBUTING.md（1 处）的
  `pip install -r <file>` 与 Dockerfile 的 `COPY requirements.lock`
  引用的文件此前无人判——锁文件一改名，所有安装命令同时 404。
  实测 8 处引用全部可解析。判据方向：V3 安装文档（README×2 /
  CONTRIBUTING）与 Dockerfile 引用的仓库文件必须存在。
- **R159 锁生成头自名（P 系续 P8）**：R155 的 P5 只读生成头的
  `--python-version`；生成头里还有两个自描述字段——
  `--output-file requirements.lock`（必须 == 文件自身名，拷贝重生成
  时最容易出现「dev 锁里写着 runtime 锁的名字」）与
  `uv pip compile requirements.txt`（源文件必须在磁盘）。实测两锁
  均自名一致、源文件都在。判据方向：两锁生成头的 `--output-file`
  == 文件名、compile 的源文件存在。
- **R160 收口轮（R157–R160 四账）+ 登记 R161–R164**：四账审计 +
  下一批主题实测登记。

## 4. 验证

- 无新判据，无新用例。定向回归（本轮动的全是文档）：
  `test_docs_navigation.py`（N1–N3）、`test_living_doc_round_caps.py`
  （L1–L4）、`test_index_row_self_description.py`（L5–L7）、
  `test_project_info_rounds.py`（B1–B2）、`test_index_snapshot.py`
  （S1–S6）、`test_handover_ci_backfill.py`（D1–D2）、
  `test_python_support_surface.py`（P1–P5）、
  `test_readme_parity.py`（M1–M4）全绿。
- 本机全量：**3020 passed / 28 skipped / 0 failed**（3048 条）。
- 变异：无（无新判据）。

## 5. 边界与遗留

- 收口轮无新判据是常态（R111/R123/R129/R134/R139/R148 同型）；
  R152 型收口（判据修正）只在判据自己走到边界时出现。
- R151 §7 的「README 徽章同账」候选在本批落地（R157）；「CI 真跑
  POSIX」「macOS 签名」等早期遗留已有归属，不在本批。
- 生产默认值不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R157 回填。

## 7. 提交

- 改动：R156 文档、R155 §6 回填、`HANDOVER_INDEX.md`（§1 六行 +
  H1 + §3 标题/两行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`
  （H2 + R156 一条）、`JUDGEMENT_LEDGER.md`（§10.28）。生产代码
  与测试零改动。
- `config/skills_config.json` 不纳入（C1）。
