# DeterminFlow (xs2) 交接报告 — Round 25（维护态第三轮：HumanwareScoreCard 前端接线——score-content 链路接入 UI）

> 本轮定位：R24 之后的**维护态第三轮**，候选起点=R24 §9。主线为顺延五轮的
> P2「HumanwareScoreCard 前端组件」——本轮核实发现该组件**早已存在但从未接线**
> （`4854d47` 已提交组件文件，全仓零 import），故实际工作是把契约 §3.3 的
> `score-text`（HTTP 端点 `/api/humanware/score-content`）接入「角色声音」页并
> 挂载该卡片。**后端零改动**。附带复核关闭 R24 §9 P3 的 e2e 失败信息可读性项。
> 基线：`f6df2db`（R24 提交）。工作树 15 个 HANDOVER 外来删除仍在（未提交未恢复，
> 与 R23/R24 相同，见 §6）。

## 1. 基线终验（改动前，全部通过）

| 验证项 | 结果 | 与 R24 基线对比 |
|---|---|---|
| Low-IL 全量 | **1740 passed / 96 skipped / 0 failed**（105.54s） | 一致 |
| 服务健康 | 8021 `HTTP 200`（重启前后各验一次） | 一致 |
| git 状态 | main 领先 origin **2** commits（a6c2515 + f6df2db 未推送） | R24 遗留，未变 |
| 工作树 | 15 个 HANDOVER 文档删除（未暂存，外来） | R24 §8-1，未变 |

## 2. 本轮核实：HumanwareScoreCard「组件存在但零接线」（认知修正）

R19–R24 交接将该候选表述为「HumanwareScoreCard 前端组件（纯新增 UI）」，隐含
前提是组件不存在。本轮核实（`git log --all -- web/src/components/HumanwareScoreCard.tsx`
+ 全仓 grep）：

- 组件文件在早期提交 `4854d47`（添加角色声音功能前端组件和后端路由）中已存在，
  含 `HumanwareScoreCard`（卡片）与 `HumanwareScoreBadge`（徽章）两个导出；
- **全仓（web/src）没有任何 import**——两导出均为死代码；前端也从未调用
  `/api/humanware/score-content`、`score-chapter`、`check-dialogue` 三个端点
  （唯二被调用的 humanware 端点是 status/voice-file/generate-voice-file）；
- 组件字段与契约 §3.3 一一对应（total_score/grade/summary/detailed_scores 四维/
  issues/recommendation），样式 token 与现主题一致（`bg-card`/`text-success` 等）。

因此 R25 的工作从「新建组件」修正为「**接线**」：让用户能在 UI 里对一段内容按
角色评分并看到结果卡片。

## 3. 实现：角色声音页接入 score-content（纯前端，最小增量）

- `web/src/components/CharacterVoiceEditor.tsx`（+~100 行）：
  - 新增「试评一段内容（人味评分）」区块：角色下拉（从当前编辑器内容的
    `^## (.+)$` 小节解析，`useMemo`）+ 内容 textarea + 「开始评分」按钮；
  - `runScore()`：POST `/api/humanware/score-content`，body
    `{workspace_id: workspaceKey（末段归一化，与既有端点一致）, character, content}`；
    成功 → `setScoreResult` 并渲染 `<HumanwareScoreCard score={...}/>`（含
    「{角色} 的评分结果」说明行）；业务失败（409 等）→ 透传 CLI `message`；
  - 守卫：未选角色或内容为空时按钮禁用（`!scoreCharacter || !scoreText.trim() || scoring`），
    `runScore` 内同样早退——双层防护；
  - 诚实性提示：区块文案明示「评分按**已保存**的 character_voice.md 执行——
    编辑器改动后请先保存再评分」（下拉解析自编辑器缓冲区，评分来自磁盘文件，
    两者可能短暂不一致，409 会诚实报「角色未定义」）。
- `web/src/components/HumanwareScoreCard.tsx`：仅把 `HumanwareScore` 接口
  `export`（调用方与卡片共用契约 §3.3 的单一结构源），渲染逻辑零改动。
- `web/package.json`：`test:desktop` 脚本追加 `HumanwareScoreCard.test.ts`。

## 4. 测试用例与验证

### 4.1 前端（净增 9 条，test:desktop 100 → 109）

| 用例（CharacterVoiceEditor.test.ts +5） | 断言要点 |
|---|---|
| score section lists characters parsed from the voice content | 下拉含 `## 林晚`/`## 沈砚` 解析结果 |
| score button stays disabled until both character and text are provided | 缺任一输入即禁用；齐备后解锁；空输入不发出请求 |
| score flow posts score-content with normalized id and renders the score card | POST body 的 workspace_id 为末段归一化 id；卡片渲染（总分/`/ 100`/四维/改进建议） |
| score 409 surfaces the CLI message and keeps the card hidden | 409 message 透传展示；卡片不渲染 |
| score section explains when no character sections exist yet | 无 `## 小节` 时空态提示 + 按钮禁用 |

| 用例（HumanwareScoreCard.test.ts，新文件 +4） | 断言要点 |
|---|---|
| renders contract §3.3 payload | 总分 88、`/ 100`、等级 B、四维、summary、issue、recommendation 全渲染 |
| shows at most five issues and notes the overflow count | 7 条 issue 只显 5 条 + 「还有 2 个问题未显示」 |
| hides the issues and recommendation sections when both are empty | 空数组/空串时对应区块不渲染 |
| badge shows the score and fires its click handler | 「人味 92」+ onClick 触发 |

### 4.2 真实浏览器端到端（8021 活体，本轮新代码）

重启 8021 加载新 dist（后端代码未变，仍为 R24）后，浏览器全流程实测：

1. `?tab=novel-workbench`（工作区 welcome）→ 侧栏「角色声音」→ 页面渲染；
2. 试评区下拉自动列出 **林晚/阿柴**（解析自已保存 voice 文件）；「开始评分」初始
   **禁用**（DOM `[disabled]` 证据）；
3. 选林晚 + 填入对话 → 按钮解锁 → 点击 → **真实评分卡渲染**：
   林晚 的评分结果 · 人味评分 · **90 / 100 · A** · 四维 声音一致性 90 / 对话自然度 90 /
   情感真实度 91 / 行为一致性 88 · summary「角色声音表现优秀，与定义高度一致」·
   改进建议「优先提升「行为一致性」…」。截图已存档（会话 artifacts）。
   —— 浏览器 UI → score-content → CLI → 卡片渲染 的完整链路首次在 UI 层打通。

### 4.3 套件对账

| 基线 | 改动前 | 改动后 |
|---|---|---|
| 后端 Low-IL | 1740 / 96 / 0 | **1740 / 96 / 0**（后端零改动，数字不变） |
| 后端 High-IL | 1825 / 11 / 0 | **1825 / 11 / 0**（同上） |
| 后端总用例 | 1836 | **1836**（不变） |
| 前端 npm test | 8 组全过 | **8 组 415 条 0 fail**（净增 9） |
| 前端 lint / build | 0 problems / ✓ | **0 problems / ✓ 6.78s** |
| 活体 e2e | 17 passed | **17 passed**（重启后复跑，0 skip） |
| 存储名审计 | [clean] | **[clean]** exit 0 |

## 5. R24 §9 P3 复核关闭：e2e `_post` 中途宕机失败信息可读性

E1–E7b 断言形如 `assert status == 200, body`；服务中途宕机时实际输出为
`AssertionError: 服务不可达（URLError）` + `assert -1 == 200`——失败信息明确
指出「服务不可达」及异常类型，`-1` 语义在 B15 注释与 `_probe` 协议中均有文档。
**结论：可读性足够，无需改动，该项关闭。**

## 6. 风险与遗留问题

1. **外来工作树改动（连续第三轮，需维护者决策）**：15 个 `docs/HANDOVER*.md`
   删除仍在工作树未暂存。本轮继续按并发写入者纪律**未提交、未恢复**，仅显式路径
   提交本轮文件。历史可 `git show` 读取。
2. **R23+R24+R25 三个提交未推送**（`origin/main..main` 将 = 3）：推送仍需维护者
   先处理 git 代理/PAT（见记忆 xs2-git-push-proxy），并核对 CI 四 job。
3. **check-dialogue / score-chapter 仍未接入 UI**：本轮按 R24 §9 P2 最小范围只接
   score-text；§3.4/§3.5 端点仍仅 e2e 覆盖。若需要「按章节批量评分」入口，
   可复用 HumanwareScoreCard（聚合结构同构），列为下轮候选。
4. 角色下拉解析自**编辑器缓冲区**（用户所见），评分按**磁盘文件**执行；两者不一致
   时 409 诚实报错，UI 已有文案提示先保存。已知边界语义，非缺陷。
5. POSIX 真跑（环境依赖）与 B16 真实并发复现（不可行）维持 R24 结论。

## 7. 下一轮迭代计划（Round 26 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | 维护者处理：外来删除核查（restore 或提交）+ 推送 3 提交 + CI 四 job 实跑核对（含 audit 步骤） | 低 | 30min |
| P2 | check-dialogue 接入角色声音页（violations/suggestion UI，契约 §3.5）；或 score-chapter 挂到章节目录/读者评估页（§3.4，含 dialogues_scored） | 低 | 1.5h |
| P3 | 试评区交互增强（可选）：评分后高亮命中口头禅位置、历史试评记录 | 低 | 1h |
| P3 | supervisor `_spawn` 真实并发测试（R24 遗留，需评估注入钩子是否值得） | 中 | 1h |
| P3 | POSIX 真跑（环境决策归维护者） | 低 | 环境依赖 |

## 8. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest -q                                   # 1740/96/0（改动前后各一次）
./.venv/Scripts/python.exe -m pytest tests/test_humanware_e2e.py -q       # 17 passed（重启服务后）
./.venv/Scripts/python.exe scripts/audit_storage_names.py                 # [clean] exit 0
sp='F:\DeterminFlow x2\xs2\.venv\Lib\site-packages'
MSYS2_ENV_CONV_EXCL=PYTHONPATH PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32" \
  C:/Windows/py.exe -X utf8 -m pytest -q -p no:cacheprovider              # 1825/11/0（High-IL 权威）
cd web
npm.cmd run test:desktop     # 109 passed（+9）
npm.cmd run lint             # 0 problems
npm.cmd test                 # 8 组 415 条 0 fail
npm.cmd run build            # ✓ 6.78s
# 服务重启（加载新 dist）：taskkill 旧 PID → ./.venv/Scripts/python.exe run.py
# 浏览器 e2e：?tab=novel-workbench → 角色声音 → 林晚 → 开始评分 → 卡片渲染（截图存档）
```

## 9. 修改文件清单

```
web/src/components/CharacterVoiceEditor.tsx      # 试评区块 + runScore（+~100）
web/src/components/HumanwareScoreCard.tsx        # export HumanwareScore 接口（+3/-1）
web/src/components/CharacterVoiceEditor.test.ts  # +5 用例 + mock 扩展（+~110）
web/src/components/HumanwareScoreCard.test.ts    # 新文件，+4 用例
web/package.json                                 # test:desktop 追加新测试文件
docs/HANDOVER_ROUND25.md                         # 本文件
docs/PROJECT_INFO.md                             # 项目状态追加 R25 条目
```
