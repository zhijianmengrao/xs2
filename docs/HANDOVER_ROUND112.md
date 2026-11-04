# DeterminFlow (xs2) 交接报告 — Round 112（保留期 40→80 + 第 N 次拒绝注入 + 全链语义指纹）

> 单 profile。用户拍板四项政策后落地：保留期 40→80、GC 年龄保持 7 天、
> 失败沙箱仅按年龄清理；并完成 §8 的两项候选（第 N 次拒绝注入、全链
> artifact 失败/重试形状与语义指纹）。生产行为改动只涉及**保留期默认值**
> 与回放工具（测试面），`src/`、`web/` 零改动。

## 1. 一句话结论

- `MAX_ROUNDS` 40→80（用户拍板）；生产写回日志实测 `历史 40/80 轮`。
- `--conflict-on-reject N`（N≥1，落在预算外退 2）；新增 N=2 耗尽 /
  N=2 成功 / N=3 末次注入三条时间线。
- metrics 指纹扩成**逐场景语义**（`name=ok/retry/fail/尝试次数` +
  `first_failure`），并用失败/重试形状的 artifact 走完整 fetch→writeback。
- 本机全量 **2683 passed / 28 skipped / 0 failed**（2711 条，304.54s）。
- CI run **41467904922**：**10 个 job 全 `success`**；写回 **39 → 40**
  （bot `470625d`）；本文档回填提交预计 **40 → 41**。

## 2. 用户拍板（R111 §5/§8 待定项）

| 项 | 决定 | 落地 |
|---|---|---|
| 写回历史保留期 | **40→80** | `MAX_ROUNDS = 80` |
| 失败沙箱 GC 年龄 | **保持 7 天** | 未改代码 |
| 沙箱保留策略 | **仅按年龄**（不加「保留最近 N 个」） | 未改代码 |
| 下一轮工作 | CI 实跑 80 轮 + artifact 失败/重试形状 + 第 N 次拒绝注入 | 本轮完成 |

## 3. 保留期 40→80

- 依据：R111 时已用到 **39/40**，而 39 条只覆盖 2026-11-01 01:51 ～
  11-02 13:32（约 **1.5 天**）；每个工作轮约 3 次 push（实现/CI/文档），
  40 格 ≈ 13 个工作轮。80 格 ≈ 26 个。
- 只改 `MAX_ROUNDS`；`XS2_MAX_ROUNDS` 与 `[3, 1000]` 校验不变，非法值
  告警后退回**新默认值** 80。旧历史条目保留原值、不改写。
- 驱动的窗口边界用例（38/39/40）改为**显式配置 40**，不跟默认政策走；
  同时修掉一个真问题：原断言写的是 `payload["max_rounds"] == MAX_ROUNDS`
  （常量），已改为 `max_rounds()`（生效窗口）——这正是台账反复警告的
  「一个配置两处读取」。
- 生产证据：`e2e-history-writeback` 日志
  `已记录 run_id=ci-41467904922：0/10 个场景重跑（总尝试 10 次），历史 40/80 轮`。

## 4. 第 N 次拒绝注入

- CLI：`--conflict-on-reject [N]`（`nargs="?"`、`const=1`）；裸开关仍是
  「第 1 次」，R108/CI 的调用不变。
- 钩子判据 `$n -eq N-1`（`$n` 是此前已被拒次数）；安装日志明说第 N 次。
- **校验**：`N < 1` 或 `--reject-pushes < N` 退 2。注入点落在预算之外时
  注入永远不会发生，静默退化成普通拒绝会让「第 N 次注入」看起来被测过。
- 新场景（本地 7→10，含 fetch 9→12）：

| 场景 | 预算/注入点 | 观测 |
|---|---|---|
| `rejected-hook-conflict-at-2` | 3 / 2 | exit 1、`push-rejected`、rounds 基线+1、末条 `replay-conflict`、push 3、`simulated rejection` 3、冲突在第 2 次尝试 |
| `rejected-hook-budget-2-at-2` | 2 / 2 | exit 0、净 +2、冲突在第 2 次尝试、第三次成功 |
| `rejected-hook-inject-at-3` | 3 / 3 | exit 1、**reason=`rebase-conflict`**、rounds 基线+1、末条 `replay-conflict`、push 3 |

- **实测发现**：注入在**最后一次**拒绝时，冲突轮进了 origin，但已经没有
  下一次重试去重算；重试循环看到的最后一次失败是 rebase 冲突，不是 push
  被拒。`rejected-hook-inject-at-3` 把这条 reason 来源单独钉住。

## 5. 全链语义指纹与失败/重试形状

- 写回前除计数行外新增：
  `replay：metrics 语义 ok_0=ok/1 retry_1=retry/2 fail_2=fail/1 …` 与
  `replay：metrics 首次失败 retry_1=…；fail_2=…`（首次失败文本截 160
  字符，只影响展示，不参与判决）。
- 全链用例使用**失败/重试形状**的 artifact（4 场景：2 过、1 重跑后过、
  1 失败；`total=4 passed=3 failed=1 retried=1 attempts=5`），走真实
  `fetch_ci_artifact.fetch()` → `writeback()`，再读沙箱 history 断言
  `failed/retried/attempts` 与逐场景 `first_failure` 原样落库。
- **不伪造生产 artifact**：生产 e2e 保持真实全过形状，全链场景只断
  `metrics 语义` 出现、取值不钉死（e2e 偶发重跑不应让 job 变红，也不应
  被强制造进历史污染重跑趋势）。失败/重试形状由全链测试夹具提供。
- 生产 artifact 实测（`replay-fetch-result-ubuntu-24.04`）：
  `metrics 内容 total=10 passed=10 failed=0 retried=0 attempts=10`，语义行
  逐项列出 10 个真实 e2e 场景名（`happy_path=ok/1 …`）。

## 6. 判据台账

- #15 扩为「内容指纹与语义（R107/R112）」：#15 的边界写明失败/重试形状
  来自测试夹具、不伪造生产 artifact。
- #16 扩为「拒绝预算与注入时机（R108/R112）」：N=1/2/3 的结局、N 超预算
  退 2。
- §6 复核表补两条用例清单；§10.1/§10.2 补 R112 小结；覆盖守卫全绿。

## 7. 验证

- 定向：**67 passed**（replay + scenarios + 翻转点守卫）。
- 本机全量：**2683 passed / 28 skipped / 0 failed**（2711 条，304.54s）。
- 变异 **M1–M5 全咬合**（`cp` 还原、sha256 逐字节相同）：
  - M1 钩子固定第一次注入 → 第 2 次注入用例红；
  - M2 删预算校验 → 不可达注入点用例红；
  - M3 语义状态全标 ok → 2 条红；
  - M4 删首次失败行 → 2 条红；
  - M5 驱动忽略 N → 驱动 7/10 通过判红。
- CI run **41467904922**（15:03:55→15:14:11 UTC，约 10m16s），**10 job 全绿**：
  - backend **2646/65**、windows-backend **2682/29**（均 **2711**）；
  - `replay-ci-writeback` 两平台各 **10/10 PASS**；
  - `replay-ci-fetch-chain` 两平台各 **12/12 PASS**；
  - `e2e-history-writeback`：`历史 40/80 轮`、第 1 次 push 成功。
- 写回历史 **39 → 40**（`ci-41467904922`、`source=ci`），bot 提交
  `470625d`（`[skip ci]`，未自触发）；本文档回填提交预计 **40 → 41**。

## 8. 边界与下一步

- 生产 artifact 仍是真实全过形状；失败/重试形状只在全链测试夹具里，理由
  见 §5（不污染趋势）。
- 「第 N 次注入」覆盖到 N=1/2/3，N>3 与更多重试预算组合未单独建场景。
- 按天滚动、失败沙箱「保留最近 N 个」按拍板**不做**；GC 默认仍 dry-run、
  7 天。
- `config/skills_config.json` 外来改动保持未提交。

## 9. 提交与 CI

- 代码+文档提交 **7cfcd7d**（`feat(R112): 保留期默认 80 + 第 N 次拒绝注入 +
  全链语义指纹`），显式路径 add，10 文件 +518/−81；`config/skills_config.json`
  未纳入。
- CI run **41467904922**（见 §7）；写回 bot `470625d`。
- 本文档与 PROJECT_INFO/记忆回填后推送，预计触发最后一轮 CI 并写回
  **40 → 41**。
