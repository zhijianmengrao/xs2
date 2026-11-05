# 交接文档总索引（R24–R152）

> 生成：2026-11-04（R131 之后、R132 之前）。用途：一份文件回答四件事——
> **有哪些轮次、每轮做了什么、文档在哪、还有哪些缺口**。
> 本文件是索引，不替代 `HANDOVER_ROUNDn.md`；数字有冲突时以单轮文档与
> `JUDGEMENT_LEDGER.md` 为准。

## 1. 现状快照

| 项 | 值 |
|---|---|
| 交接文档 | **127 份**（`docs/HANDOVER_ROUND24..152.md`；R34/R35 从未有文档） |
| 文档体量 | 20,097 行 / 1.1 MB |
| 当前用例 | **3,034**（R152 收口：N3/D1 因本篇 +2；R152 树 3006 passed / 28 skipped / 0 failed；本行由 S3 机判） |
| CI 写回历史 | **80 / 80 轮**（`tests/fixtures/e2e_retry_history/history.json`，末条 `ci-42025942392`；R152 跑执行第 80 条） |
| 代码基线 | `main` = `2c5e3a0`（R151 提交 + CI 回写；docs 回填见 R151 §6） |
| 判据登记 | `docs/JUDGEMENT_LEDGER.md`：18 条编号判据（§2 编号表）+ 退出码表 0/1/3/4/5/6/7/8 |
| CI 闸门 | 10 个 job（backend / windows-backend / frontend / container-config / container-build / replay-ci-writeback ×2 / replay-ci-fetch-chain ×2 / e2e-history-writeback） |

## 2. 三层读法

不必一上来读 2 MB。按问题选层：

| 想回答 | 读什么 |
|---|---|
| 项目是什么、现在到哪 | `docs/PROJECT_INFO.md`（每轮一段，最摘要） |
| 某一轮的结论 / 实现 / 变异 / CI / 边界 | `docs/HANDOVER_ROUNDn.md`（单轮细节） |
| 某个数字（阈值、退出码、容忍量）凭什么 | `docs/JUDGEMENT_LEDGER.md`（判据登记 + 翻转点） |
| 有哪些轮次、文档在哪、缺什么 | 本文件 §4 / §5 / §6 |

每轮固定产出四件（收口轮称「四账审计」）：handover、PROJECT_INFO 一段、
判据台账（涉及判据时）、会话记忆。**记忆不在仓库内**
（`~/.zcode/.../memory/xs2-round-status.md`），外部接手者只能依赖前三者——
见 §6.4。

## 3. 阶段划分（127 份文档的骨架）

| 阶段 | 轮次 | 份数 | 主线 |
|---|---|---|---|
| 维护态与发版 | R24–R33 | 10 | Humanware 前端接线、归档首发、updater 自托管、v1.0.0/v1.0.1/v1.0.2 |
| 收编与防复发 | R36–R40 | 5 | R34/R35 收编（B20–B23）、静态防复发钉测、供应商失败率画像 |
| 画像与 CI 闸门 | R41–R53 | 13 | 画像三面、首次全量 CI 核对、容器构建、快照保鲜、桩 provider + 故障注入 |
| 判据边界 | R54–R69 | 16 | 样本量 / per-workflow / 留一法 / 翻转点 / 形状判据 / 两个 flake 家族 |
| 归因与元数据 | R70–R80 | 11 | msys skip 归因、元数据形状与退出码 3/4、重跑率趋势 |
| 回写与快照收口 | R81–R100 | 20 | ACL 归因、`totals.runs`、CI 回写 e2e、replay 本地化、收口 |
| 生产边界 | R101–R113 | 13 | replay 进生产 CI、Windows 全链、预算 / 窗口 / GC、失败形状 |
| 五轮连推（一） | R114–R118 | 5 | 注入矩阵 N=6/7、失败形状的下游消费 |
| 五轮连推（二） | R119–R123 | 5 | 失败 / 0 场景 / 全失败进生产全链、趋势表消费 |
| 单轮 | R124 | 1 | 注入矩阵 N=7/8、attempts=9 |
| 五轮连推（三） | R125–R129 | 5 | 满窗 80、大预算、写回幂等、语义指纹截断 |
| 五轮连推（四） | R130–R134 | 5 | 展示层坏数据边界、CI 报告层降级、发版验收判决、交接文档引用完整性、收口 |
| 五轮连推（五） | R135–R139 | 5 | 流程资产自描述：CI job 清单恰等、history↔git 双账、索引快照机械化、SOP↔判决脚本同账、收口 |
| 四轮连推 | R140–R143 | 4 | scripts/ 引用面（孤儿清零）、skip 分类自述、PROJECT_INFO 叙事账、requirements 双源 |
| 五轮连推（六） | R144–R148 | 5 | 文档与依赖的「第二份账」收口：§6 回填时限机判、依赖四源同账、活文档轮次盖子、索引 §4 行自描述、收口 |
| 四轮连推（七） | R149–R152 | 4 | 索引 §1 余下两行、双锁闭包、Python 支持面、收口；R153–R156 已登记（R152 §7） |

## 4. 全量索引（R24–R152）

日期取文档首次入库的提交日期；主题取标题副标题（R112 起 18 份无副标题，
按引言首句补；R133 已补齐 19 份含 R129/R132，钉测 `test_docs_navigation.py`
N3 防复发）。

| 轮次 | 日期 | 主题 | 文档 |
|---|---|---|---|
| R24 | 2026-10-24 | 维护态第二轮：e2e 宕机语义 + supervisor 竞态兜底 + installation_state 真实证据收口 | [md](HANDOVER_ROUND24.md) |
| R25 | 2026-10-25 | 维护态第三轮：HumanwareScoreCard 前端接线——score-content 链路接入 UI | [md](HANDOVER_ROUND25.md) |
| R26 | 2026-10-25 | 维护态第四轮：score-chapter 接入读者评估页 + B17 错误包络修复 | [md](HANDOVER_ROUND26.md) |
| R27 | 2026-10-25 | 维护态第五轮：check-dialogue 接线收官 + api 层 4xx 错误人因化 | [md](HANDOVER_ROUND27.md) |
| R28 | 2026-10-25 | 维护者任务执行轮：删除归档 + 首次推送 + CI 核对 + B18 | [md](HANDOVER_ROUND28.md) |
| R29 | 2026-10-25 | updater 分发自托管：方案 A 落地 | [md](HANDOVER_ROUND29.md) |
| R30 | 2026-10-25 | 角色声音页共享输入子组件抽取 | [md](HANDOVER_ROUND30.md) |
| R31 | 2026-10-25 | 首个 fork 发版演练：v1.0.0 落地 | [md](HANDOVER_ROUND31.md) |
| R32 | 2026-10-25 | 收官轮：R31 建议落地 + 小说全流程测试 + v1.0.1 最终版 | [md](HANDOVER_ROUND32.md) |
| R33 | 2026-10-26 | 小说创作全流程测试轮 | [md](HANDOVER_ROUND33.md) |
| R36 | 2026-10-26 | 收编轮：R34/R35 未提交工作落地 + 基线修复 | [md](HANDOVER_ROUND36.md) |
| R37 | 2026-10-27 | 维护轮：R36 §6 候选落地 | [md](HANDOVER_ROUND37.md) |
| R38 | 2026-10-27 | 维护轮：R37 §8 候选落地 | [md](HANDOVER_ROUND38.md) |
| R39 | 2026-10-28 | 维护轮：B26 家族 workflow 面收口 + B27 教训机械化 | [md](HANDOVER_ROUND39.md) |
| R40 | 2026-10-28 | 维护轮：B26 家族机械化终局 + 供应商失败率画像 | [md](HANDOVER_ROUND40.md) |
| R41 | 2026-10-28 | 维护轮：画像三面闭环——导出/可视化/周期化 | [md](HANDOVER_ROUND41.md) |
| R42 | 2026-10-28 | 维护轮：首次推送 CI 全量核对收口 + 失败率硬闸门 + 死通道依赖收尾 | [md](HANDOVER_ROUND42.md) |
| R43 | 2026-10-28 | 维护轮：画像跨 run 对比视图 + POSIX 真跑调研收口 | [md](HANDOVER_ROUND43.md) |
| R44 | 2026-10-28 | 容器构建面补齐 + 大陆下载加速调研 | [md](HANDOVER_ROUND44.md) |
| R45 | 2026-10-28 | 三笔技术债收口：worker 弃用 / 孤儿脚本 / 闸门空转 | [md](HANDOVER_ROUND45.md) |
| R46 | 2026-10-28 | 闸门真正接进 CI / R2 应急通道补门控 | [md](HANDOVER_ROUND46.md) |
| R47 | 2026-10-28 | 四项技术债并行收口 | [md](HANDOVER_ROUND47.md) |
| R48 | 2026-10-28 | 快照保鲜自动化 | [md](HANDOVER_ROUND48.md) |
| R49 | 2026-10-29 | CI e2e 桩 provider + 快照覆盖度 | [md](HANDOVER_ROUND49.md) |
| R50 | 2026-10-29 | 桩故障注入 + 画像多 run 基线 + macOS 缺口收口 | [md](HANDOVER_ROUND50.md) |
| R51 | 2026-10-29 | 样本量闸门进 CI + 退避可观察 + 趋势接入列表 | [md](HANDOVER_ROUND51.md) |
| R52 | 2026-10-29 | 退避形状验证 + Windows 侧闸门 + 全失败信号 + 快照重导 | [md](HANDOVER_ROUND52.md) |
| R53 | 2026-10-29 | 三段退避形状 + 半宽预算 + 全失败退化点 | [md](HANDOVER_ROUND53.md) |
| R54 | 2026-10-30 | workflow 级全失败聚合 + per-workflow 样本量 | [md](HANDOVER_ROUND54.md) |
| R55 | 2026-10-30 | workflow 级趋势 + 样本量精确界 + 四段退避形状 | [md](HANDOVER_ROUND55.md) |
| R56 | 2026-10-30 | per-workflow 失败率判据：留一法基线 + 三分法 + 报告模式 | [md](HANDOVER_ROUND56.md) |
| R57 | 2026-10-30 | 主闸门 `evaluate` 永不失败修复：外部政策上限 + 区间下界三分法 | [md](HANDOVER_ROUND57.md) |
| R58 | 2026-10-30 | per-workflow 硬门槛 + 连续 3 轮 undetermined 的次级信号 | [md](HANDOVER_ROUND58.md) |
| R59 | 2026-10-30 | 主闸门历史基线回归 + 载荷扫描扩到所有快照 fixture | [md](HANDOVER_ROUND59.md) |
| R60 | 2026-10-30 | 快照重导：回归判据从 `undetermined` 转为真判 | [md](HANDOVER_ROUND60.md) |
| R61 | 2026-10-30 | 8% 政策上限首次校准：维持 8%，它是突破线不是健康线 | [md](HANDOVER_ROUND61.md) |
| R62 | 2026-10-30 | 逐 workflow 历史基线：只有 2/9 说得出话，提前量 2/5 次失败 | [md](HANDOVER_ROUND62.md) |
| R63 | 2026-10-30 | min_ratio 判别力边界：失明点是 c==a，实测余量 25–67 倍 | [md](HANDOVER_ROUND63.md) |
| R64 | 2026-10-30 | CP 溢出：边界是一条曲线，最小值 1030，出现在失败率最高的一端 | [md](HANDOVER_ROUND64.md) |
| R65 | 2026-10-31 | 形状判据：从「相邻比值」换成「逐段非对称容差」 | [md](HANDOVER_ROUND65.md) |
| R66 | 2026-10-31 | executor pool 的 `node_control_conflict`：闸门在「终态落盘」与「收尾」之间误报 | [md](HANDOVER_ROUND66.md) |
| R67 | 2026-10-31 | 提前量命令化：R62 的「同一把尺」是错的，两层阈值差 7 个百分点是必需的 | [md](HANDOVER_ROUND67.md) |
| R68 | 2026-10-31 | 形状场景判红后重跑一次：机制的第一步先把「重跑会撞同名工作流」修掉 | [md](HANDOVER_ROUND68.md) |
| R69 | 2026-10-31 | 判据容忍量的翻转点：把「数字等于常量」升级成「数字是判决的边界」 | [md](HANDOVER_ROUND69.md) |
| R70 | 2026-10-31 | 判据边界的两种「不是常量」 | [md](HANDOVER_ROUND70.md) |
| R71 | 2026-10-31 | msys skip 的归因：判据先被判据自己吞掉 | [md](HANDOVER_ROUND71.md) |
| R72 | 2026-10-31 | #4 的退出路径：门与翻转点用同一组计数 | [md](HANDOVER_ROUND72.md) |
| R73 | 2026-10-31 | #3 的退出路径：回归判据的门也要用边界计数 | [md](HANDOVER_ROUND73.md) |
| R74 | 2026-11-01 | 重跑频率：从 grep 日志到机读指标 + step summary | [md](HANDOVER_ROUND74.md) |
| R75 | 2026-11-01 | 畸形 per_workflow：退出码 4 不是 1，也不是 8 | [md](HANDOVER_ROUND75.md) |
| R76 | 2026-11-01 | 样本量诊断：报告也要排在退出 3/4 之后 | [md](HANDOVER_ROUND76.md) |
| R77 | 2026-11-01 | 元数据不是 JSON：4 不是 1/3/8 | [md](HANDOVER_ROUND77.md) |
| R78 | 2026-11-01 | 重跑率跨 run 趋势：只判数据有效 | [md](HANDOVER_ROUND78.md) |
| R79 | 2026-11-01 | 元数据路径读不开：退出 4 不是 3 | [md](HANDOVER_ROUND79.md) |
| R80 | 2026-11-01 | 元数据形状收尾：`totals` → 4、`history` 只报告且逐条 | [md](HANDOVER_ROUND80.md) |
| R81 | 2026-11-01 | msys 对象 ACL：根因是「对象带着创建者的完整性级别」 | [md](HANDOVER_ROUND81.md) |
| R82 | 2026-11-01 | 两块元数据：任何读计数的入口都校验整份工件 | [md](HANDOVER_ROUND82.md) |
| R83 | 2026-11-01 | `totals.runs` 收口：写了没人看的字段并入内容复算 | [md](HANDOVER_ROUND83.md) |
| R84 | 2026-11-01 | failure_rate 登记 / p=1.0 真实数据 / F:→Low 根因 | [md](HANDOVER_ROUND84.md) |
| R85 | 2026-11-01 | 清除 Low 强制标签 / 本机基线收口为 2486/28 | [md](HANDOVER_ROUND85.md) |
| R86 | 2026-11-01 | 顶层 `source_root` 登记为只读展示字段 | [md](HANDOVER_ROUND86.md) |
| R87 | 2026-11-01 | n≥29 全失败样本：主动制造 / 翻转点 n=29 | [md](HANDOVER_ROUND87.md) |
| R88 | 2026-11-01 | CI 回写 e2e 重跑历史 | [md](HANDOVER_ROUND88.md) |
| R89 | 2026-11-01 | 写回链路可执行化 + 历史窗口 20→40 | [md](HANDOVER_ROUND89.md) |
| R90 | 2026-11-01 | 写回冲突可恢复 | [md](HANDOVER_ROUND90.md) |
| R91 | 2026-11-01 | 写回失败分类 + step summary | [md](HANDOVER_ROUND91.md) |
| R92 | 2026-11-01 | PR 预检 `record --check-only` | [md](HANDOVER_ROUND92.md) |
| R93 | 2026-11-01 | 历史条目来源标注 | [md](HANDOVER_ROUND93.md) |
| R94 | 2026-11-01 | `--dry-run` + 本地回放 | [md](HANDOVER_ROUND94.md) |
| R95 | 2026-11-01 | artifact 拉取脚本 + replay 未提交态 | [md](HANDOVER_ROUND95.md) |
| R96 | 2026-11-02 | replay 全链 fetch→writeback | [md](HANDOVER_ROUND96.md) |
| R97 | 2026-11-02 | 写回机读结果工件 | [md](HANDOVER_ROUND97.md) |
| R98 | 2026-11-02 | fetch 重试/分类 + 结果工件 | [md](HANDOVER_ROUND98.md) |
| R99 | 2026-11-02 | 回放内制造 push 拒绝/冲突 | [md](HANDOVER_ROUND99.md) |
| R100 | 2026-11-02 | 收口：现场清理 + 轮次编号 + 写回 15 轮核对 | [md](HANDOVER_ROUND100.md) |
| R101 | 2026-11-02 | replay 拒绝/冲突进生产 CI | [md](HANDOVER_ROUND101.md) |
| R102 | 2026-11-02 | MAX_ROUNDS 耗尽防护 | [md](HANDOVER_ROUND102.md) |
| R103 | 2026-11-02 | 四条生产边界收口 | [md](HANDOVER_ROUND103.md) |
| R104 | 2026-11-02 | 全链 job 上 Windows | [md](HANDOVER_ROUND104.md) |
| R105 | 2026-11-02 | 永久拒绝 × 冲突组合场景 | [md](HANDOVER_ROUND105.md) |
| R106 | 2026-11-02 | fetch × 永久拒绝 × 冲突三重叠加 | [md](HANDOVER_ROUND106.md) |
| R107 | 2026-11-02 | 全链 metrics 内容指纹 | [md](HANDOVER_ROUND107.md) |
| R108 | 2026-11-02 | 拒绝预算成为行为边界 | [md](HANDOVER_ROUND108.md) |
| R109 | 2026-11-02 | MAX_ROUNDS 可配置 | [md](HANDOVER_ROUND109.md) |
| R110 | 2026-11-02 | 失败沙箱 GC | [md](HANDOVER_ROUND110.md) |
| R111 | 2026-11-02 | 收口轮 | [md](HANDOVER_ROUND111.md) |
| R112 | 2026-11-02 | 保留期 40→80 + 第 N 次拒绝注入 + 全链语义指纹 | [md](HANDOVER_ROUND112.md) |
| R113 | 2026-11-03 | 注入矩阵 N=4/5 + 全链失败形状 | [md](HANDOVER_ROUND113.md) |
| R114 | 2026-11-03 | 注入矩阵 N=6/7 + 场景表不变量 | [md](HANDOVER_ROUND114.md) |
| R115 | 2026-11-03 | 趋势表显示失败列 + 0 场景文案拆分 | [md](HANDOVER_ROUND115.md) |
| R116 | 2026-11-03 | 失败形状 × 拒绝/注入：内容不被重算 | [md](HANDOVER_ROUND116.md) |
| R117 | 2026-11-03 | 全链注入 N=6（fetch-chain） | [md](HANDOVER_ROUND117.md) |
| R118 | 2026-11-03 | 收口轮（R114–R118 四账） | [md](HANDOVER_ROUND118.md) |
| R119 | 2026-11-03 | 失败形状 × 拒绝/注入进生产全链 + R118 CI 回填 | [md](HANDOVER_ROUND119.md) |
| R120 | 2026-11-03 | 全链 0 场景形状 + 拒绝重试 | [md](HANDOVER_ROUND120.md) |
| R121 | 2026-11-03 | 全链全失败形状 + 拒绝重试 | [md](HANDOVER_ROUND121.md) |
| R122 | 2026-11-03 | 失败形状的下游趋势消费 | [md](HANDOVER_ROUND122.md) |
| R123 | 2026-11-03 | 收口轮（R119–R123 四账） | [md](HANDOVER_ROUND123.md) |
| R124 | 2026-11-03 | 注入矩阵 N=7/8、attempts=9 | [md](HANDOVER_ROUND124.md) |
| R125 | 2026-11-04 | 满窗实战（默认窗口 80） | [md](HANDOVER_ROUND125.md) |
| R126 | 2026-11-04 | 失败形状 × 大预算（attempts=9） | [md](HANDOVER_ROUND126.md) |
| R127 | 2026-11-04 | 写回幂等 replay 层 | [md](HANDOVER_ROUND127.md) |
| R128 | 2026-11-04 | 语义指纹截断边界 | [md](HANDOVER_ROUND128.md) |
| R129 | 2026-11-04 | 收口轮（R125–R129 四账） | [md](HANDOVER_ROUND129.md) |
| R130 | 2026-11-04 | e2e step summary 的坏数据边界 | [md](HANDOVER_ROUND130.md) |
| R131 | 2026-11-04 | CI 报告层单行与降级边界 | [md](HANDOVER_ROUND131.md) |
| R132 | 2026-11-04 | 发版验收：判决不得是 `assert` | [md](HANDOVER_ROUND132.md) |
| R133 | 2026-11-04 | 交接文档引用完整性：导航层防复发 | [md](HANDOVER_ROUND133.md) |
| R134 | 2026-11-05 | 收口轮：R130–R134 五轮连推四账 | [md](HANDOVER_ROUND134.md) |
| R135 | 2026-11-05 | CI 闸门形状：job 清单恰等 | [md](HANDOVER_ROUND135.md) |
| R136 | 2026-11-05 | history.json ↔ git 双账核对 | [md](HANDOVER_ROUND136.md) |
| R137 | 2026-11-05 | 索引 §1 快照数字机械化 | [md](HANDOVER_ROUND137.md) |
| R138 | 2026-11-05 | RELEASE_SOP ↔ verify_release 退出码契约 | [md](HANDOVER_ROUND138.md) |
| R139 | 2026-11-05 | 收口轮：R135–R139 四账 + R140–R143 登记 | [md](HANDOVER_ROUND139.md) |
| R140 | 2026-11-05 | scripts/ 引用面：孤儿清零 + CI 引用可解析 | [md](HANDOVER_ROUND140.md) |
| R141 | 2026-11-05 | skip 分类：每条 skip 必须自述 | [md](HANDOVER_ROUND141.md) |
| R142 | 2026-11-05 | PROJECT_INFO 专述 bullet 覆盖与顺序单调 | [md](HANDOVER_ROUND142.md) |
| R143 | 2026-11-05 | requirements 双源一致性 | [md](HANDOVER_ROUND143.md) |
| R144 | 2026-11-05 | 交接文档 §6 回填时限机判 | [md](HANDOVER_ROUND144.md) |
| R145 | 2026-11-05 | 依赖四源同账：pyproject / requirements-dev / 双锁 | [md](HANDOVER_ROUND145.md) |
| R146 | 2026-11-05 | 活文档轮次盖子：当前时态数字机判 | [md](HANDOVER_ROUND146.md) |
| R147 | 2026-11-05 | 索引 §4 行自描述同账：日期与主题机判 | [md](HANDOVER_ROUND147.md) |
| R148 | 2026-11-05 | 收口轮：R144–R148 四账 + R149–R152 登记 | [md](HANDOVER_ROUND148.md) |
| R149 | 2026-11-05 | 索引 §1 余下两行机械化：文档体量与代码基线 | [md](HANDOVER_ROUND149.md) |
| R150 | 2026-11-05 | 双锁闭包同账：runtime lock ⊆ dev lock | [md](HANDOVER_ROUND150.md) |
| R151 | 2026-11-05 | Python 支持面同账：CI / Dockerfile / classifiers / README | [md](HANDOVER_ROUND151.md) |
| R152 | 2026-11-05 | 收口轮：R149–R152 四账 + 满窗滚动账本修正 + R153–R156 登记 | [md](HANDOVER_ROUND152.md) |

## 5. 历史轮次处置（R1–R23、R34、R35）

| 轮次 | 现状 | 证据 / 取回方式 |
|---|---|---|
| R1–R2 | 无独立文档 | 早期三次会话合并记在 `docs/HANDOVER.md`（R28 已删） |
| R3 | 有：`DELIVERY_REPORT_ROUND3.md`（仍在库） | — |
| R4–R9 | **无任何记录** | git 全历史的文档树与提交信息均无 |
| R10–R23 | **曾有文档，R28 归档删除** | 提交 `a249e17`（15 文件，−2934 行）；取回：`git show a249e17^:docs/HANDOVER_ROUND18.md` |
| R34、R35 | **从未有文档** | R36 §0 用未提交 diff + 轮次记忆重建溯源表（B20/B21/B22）；回归文件 `tests/test_novel_full_flow_round34.py` |
| R35 的插件修复 | 只有提交号 | 插件仓 `6804876`（0.1.15）、`a101515`（0.1.16）、`1504a88` 等不在本仓 |

R10–R12 的副本含 BOM 与「〔待补〕」乱码占位符；若从 git 恢复，需先清洗。

## 6. 缺口清单

### 6.1 覆盖缺口（历史，已知悉即可）

按 §5：**R4–R9 完全无记录；R1–R3 仅合并记录；R10–R23 只剩 git 历史；
R34/R35 从未有文档**。现行维护入口从 R24 起，R36 已把 R34/R35 的可溯源部分
补进正文。除此之外，R24–R152 每轮恰好一份，无缺号、无重号。

### 6.2 回填缺口（CI 写回 run 未记账）——**已在本轮补正文的 4 处**

每轮的 CI 写回会自增历史计数。文档普遍只写到「本篇回填提交预计 N→N+1」，
之后不回改。核对 `history.json` 与 `git log` 后发现：

| 文档 | 文档只写到 | 实际回填 run | 结果 |
|---|---|---|---|
| R124 | 51→52「预计」 | `41674132029`（`f1a6775`） | success，16:25:56→16:41:59，写回第 52 条 |
| R125–R129 | 53→54「预计」 | `41690012416`（`72bab38`） | success，18:02:46→18:21:35，写回第 54 条 |
| R130 | 55→56「预计」 | `41793979222`（`313315a`） | success，10 job 全绿，07:41:06→07:59:21，写回第 56 条 |
| R131 | 57→58「预计」 | `41805112750`（`a9bb275`） | success，10 job 全绿，09:09:21→09:26:13，写回第 58 条 |

R130 / R131 / PROJECT_INFO 的这四行已按上表补成实测值（与历史文件逐条对齐）。

另有一批**更早的写回 run 在任何文档里都没有 run id**（计数逐轮有记，
run id 无记）：2026-11-01～11-02 共 12 个（`41297578263`、`41300432743`、
`41304923837`、`41367942634`、`41374544793`、`41435198806`、`41439726639`、
`41444765661`、`41448315894`、`41453307854`、`41470550560`、`41482603567`）。
权威来源是 `tests/fixtures/e2e_retry_history/history.json` 与
`git log --grep "CI run"`，不必回改旧文档。

### 6.3 失效引用（指向已删除文档）

R28 删除 R10–R23 后，以下位置仍在引用它们：

| 位置 | 引用 | 处置建议 |
|---|---|---|
| `docs/PROJECT_INFO.md` §项目状态 | 「逐轮记录见 `docs/HANDOVER_ROUND15..22.md`」、`HANDOVER_ROUND21 §9`、`HANDOVER_ROUND23.md` | ✅ R133 已修（死链改指 §5 / 补归档取回标注） |
| `docs/PROJECT_INFO.md` 平台注意事项 | `HANDOVER_ROUND18 §4` | ✅ R133 已修（R18 引用即 §5 取回指引，带标记） |
| `docs/HANDOVER_ROUND32.md` §6 | `docs/HANDOVER_ROUND15..32.md` | 历史文档，不改 |
| `docs/humanware-helper-contract.md` | `docs/HANDOVER_ROUND20.md`（B11–B13）、`HANDOVER_ROUND21.md` | ✅ R133 已加归档取回标注（原建议「不改」，因它是 v3.4 活契约而推翻，见 R133 §3.1） |
| `src/core/win_names.py`、`src/workflow/executor_supervisor.py`、`scripts/audit_storage_names.py`、`tests/test_executor_runtime_dir.py` 等注释 | R18/R20/R21 文档 | 不改（注释性散文，历史轮次号仍可经索引 §5 取回） |

R28 当时在 handover 里写过取回方式，但 R28 已不是入口；本索引 §5 提供统一口径。
R133 起失效引用有钉测把守（`tests/test_docs_navigation.py` N1：可解析或带
归档标记；台账 §10.13）。

### 6.4 结构与编号

1. **`PROJECT_INFO.md` 标题陈旧**：仍写「项目状态（2026-10-24 完结）」，
   内容已续写到 R131（完结后又跑了 108 轮）。建议改为「R22 完结 → R24 起
   维护迭代（至 R131）」。✅ R133 已改为「至 R133」并逐轮跟进。
2. **`PROJECT_INFO.md` 轮次顺序错位**：`R39` 排在 `R40` 之后，`R32` 排在
   `R39/R40` 之后（§项目状态的 bullet 顺序）。只影响阅读，不影响事实。
   R112 起 20 条 bullet 此前直接挂在 §平台注意事项 末尾，R132 已补
   「§迭代记录续记（R112 起）」分节，内容未改。✅ R133 已重排为单调
   （R32→R31 之后；R39→R40 之前）。
3. **R132 审计：38 / 107 份没有「下一轮候选 / 后续」章节**：R28、R32、R33、R88–R101、R132、
   R112–R131。规划只能从下一轮的引言倒推；R130/R131 只写了「R130–R134
   五轮连推」，**R132–R134 的主题未登记**。✅ 主题部分 R133 已登记；
   R134 §9 重启候选制（R135–R139 已登记）；R134 审计：按标题实测仍有 42/109 份无候选/后续章节。
4. **18 份 R112 起的文档标题没有主题副标题**，需读引言才知道本轮做什么
   （本索引 §4 已补主题列）。✅ R133 已补齐 19 份（含 R129/R132），
   N3 钉测防复发。
5. **记忆不在仓库内**：收口轮的「四账」含会话记忆
   （`~/.zcode/.../memory/xs2-round-status.md`），外部接手者读不到；
   §1 的数字已按仓库内可核对的口径重述。
6. **文档无日期字段**：日期只在 git 提交里（本索引 §4 的日期取自
   `git log --diff-filter=A`）。

## 7. 跨轮遗留项（今天仍然有效）

| 项 | 出处 | 状态 |
|---|---|---|
| 展示层不判定：趋势表、step summary、CI 报告只展示，不判趋势好坏 / 业务有效性 | R78 / R115 / R130 / R131 | 设计边界，勿当缺口修 |
| 历史按天滚动、失败沙箱「保留最近 N 个」 | R112 拍板 | 明确不做 |
| 注入矩阵 N>8、attempts>9 未建场景 | R124 / R126 / R129 | 量变，矩阵形状已钉住 |
| 生产 `DEFAULT_ATTEMPTS=3`、`MAX_ROUNDS=80`、GC 默认 dry-run/7 天 | R108–R110 / R112 | 现行默认值 |
| `config/skills_config.json` 保持未提交（C1） | 多轮 | 外来改动，勿提交 |
| 两个 flake 家族：e2e 形状判据（R65 已修）、executor pool `node_control_conflict`（R66 已结构化修复） | R65 / R66 | 已闭环，保留为回归 |
| POSIX 真跑、macOS 签名、HumanwareScoreCard 三笔早期遗留 | R21 §9 | 分别由 CI ubuntu、R44 核对、R25–R27 接线闭环 |
| R133–R134 主题未定 | R130/R131 引言 | ✅ R133 已登记（R133=交接文档引用完整性；R134=收口轮 R130–R134 四账） |

## 8. 建议动作（按优先级）

1. ✅ **R133 已办**（原「R133 开工前」）：R133–R134 主题已写进
   `PROJECT_INFO.md` 尾段与 R133 引言。
2. **回填已完成**：R130/R131 的 CI 实测已写回正文；R132 代码 run
   `41832975143` 十 job 全绿、写回 59→60，docs 回填后到 61；R133 代码 run
   `41861139324` 十 job 全绿、写回 61→62。
3. ✅ **R133 已办**（原「补索引入口」）：索引指针 R132 已加；失效引用
   R133 已修清并有钉测把守（N1）。
4. **可选**：给 R112–R131 的 18 份文档补标题副标题（纯展示，风险为零）。
5. **不要做**：回改 R101–R111 的 12 个写回 run id（权威在 `history.json`，
   回改只会制造第二份账）。
