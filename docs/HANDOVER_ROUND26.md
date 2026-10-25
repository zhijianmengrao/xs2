# DeterminFlow (xs2) 交接报告 — Round 26（维护态第四轮：score-chapter 接入读者评估页 + B17 错误包络修复）

> 本轮定位：R24 之后的**维护态第四轮**，候选起点=R25 §7 P2。两件事：
> ① 把契约 §3.4 `score-chapter`（HTTP `/api/humanware/score-chapter`）接入
> 「读者评估」页（ReviewView），复用 HumanwareScoreCard——小说创作主流程的
> **章节级**对话人味评分闭环；② 修复 **B17**：R25 接线 score-content 时前端
> 读错业务失败包络（读 `message`，真实是 FastAPI `{detail}`），409 拒因被
> 兜底文案吞掉。**后端零改动**。基线：`366494b`（R25 提交）。工作树 15 个
> HANDOVER 外来删除仍在（未提交未恢复，连续第四轮，见 §6）。

## 1. 基线终验（改动前）

| 验证项 | 结果 | 与 R25 基线对比 |
|---|---|---|
| 8021 服务健康 | `HTTP 200`（R25 dist，重启前） | 一致 |
| git 状态 | main 领先 origin **3** commits | R25 遗留，未变 |
| 工作树 | 15 个 HANDOVER 文档删除（未暂存，外来） | 未变 |

## 2. B17：score-content 业务失败拒因被吞（R25 引入）

- **现象**：角色声音页试评一个未在 voice 文件定义的角色，UI 只显示兜底
  「评分失败，请重试」，CLI 透传的 409 拒因（如「角色 X 未在
  character_voice.md 中定义」）不显示。R25 交接声称「409 透传 CLI message」
  与活体行为不符。
- **复现（活体 8021）**：`POST /api/humanware/score-content`，body
  `{workspace_id:"welcome", character:"不存在的角色", content:"「测试」"}` →
  实际响应 `409 {"detail":"角色「不存在的角色」未在 character_voice.md 中定义"}`
  （Python urllib 直连，避免 .NET URI 假象，注意事项 11）。
- **根因**：后端业务失败走 `raise HTTPException(status_code=code, detail=message)`
  （`src/web/humanware_routes.py:418-420`），FastAPI 默认错误包络是
  `{"detail": ...}`；R25 前端 `runScore` 读取 `data?.message`（undefined）→
  落入兜底文案。R25 单测 mock 了 CLI 直出形状 `{status:'error', message}`
  （该形状在 HTTP 错误路径上**不会出现**），mock 与活体不符导致假通过。
- **修复**：`web/src/components/CharacterVoiceEditor.tsx` 错误文案提取改为
  `data?.detail || data?.message || '评分失败，请重试'`（detail 优先=真实包络，
  message 兜底=防御 CLI 直出形状）。最小改动 1 行。
- **回归锚**：`CharacterVoiceEditor.test.ts` 的 409 用例 mock 改为真实形状
  `{detail: ...}` 并注释「mock 形状必须与活体一致」。
- **活体验证（本轮浏览器）**：编辑器缓冲区追加未保存角色「临时测试角色」→
  下拉选中 → 试评 → UI 显示「角色「临时测试角色」未在 character_voice.md 中定义」
  （修复前此处为兜底文案）。
- **影响面**：仅 score-content 试评的错误分支；成功路径与守卫不受影响。
  score-chapter 新组件（§3）自出生即用正确形状。

## 3. 实现：读者评估页接入 score-chapter（纯前端，最小增量）

- `web/src/components/ChapterHumanwareScore.tsx`（新组件，~100 行）：
  - props `{workspaceId, chapter}`；workspaceKey 末段归一化（与
    CharacterVoiceEditor 同规）；`chapter_file = story/<四位章节号>/chapter.md`
    （`padStart(4,"0")` 防非四位输入）；
  - 「评估本章对话」按钮 → POST `/api/humanware/score-chapter`，body
    `{workspace_id, chapter_file}`；成功 → 「共评分 N 段对话」引导行 +
    `<HumanwareScoreCard score={...}/>`（§3.4 聚合结构与卡片同构）；
    业务失败（404 章节不存在 / 409 缺 voice 文件或无对白）→ B17 同源
    `detail` 优先透传；网络失败 → 「服务不可达」；
  - 评分中按钮禁用 + 文案「评分中…」；成功后按钮变「重新评分」。
- `web/src/pages/NovelWorkbenchPage.tsx`：ReviewView 右侧栏「模拟读者评估」
  区块下方挂载 `<ChapterHumanwareScore key={workspace:chapter} .../>`
  （键控：切章/切工作区即重挂载，丢弃过期结果）。
- `web/package.json`：`test:desktop` 追加 `ChapterHumanwareScore.test.ts`。

## 4. 测试用例与验证

### 4.1 前端单测（净增 7 条，test:desktop 109 → 116；npm test 415 → 422）

| 用例（ChapterHumanwareScore.test.ts） | 断言要点 |
|---|---|
| renders the section without issuing any request on mount | 标题/依赖说明渲染；挂载即零请求 |
| click posts score-chapter with normalized workspace id and zero-padded chapter file | POST body `workspace_id=demo-voice`（完整路径归一化）、`chapter_file=story/0001/chapter.md`（"1"→补零） |
| success renders dialogue count and the score card | 「共评分 12 段对话」+ 卡片（82 / 100、四维、summary）+ 按钮变「重新评分」 |
| 404 surfaces the FastAPI detail message and keeps the card hidden | 真实包络 `{detail}` 透传；结果区隐藏（B17 同源锚） |
| 409 without quotable dialogue surfaces the CLI message | 「没有可评分的对话内容」透传 |
| button stays disabled while a score request is in flight | 在途禁用 + 「评分中…」；放行后恢复 |
| network failure surfaces a readable message without the card | 「服务不可达」；无过期结果残留 |

另有 CharacterVoiceEditor.test.ts 409 用例改用真实 `{detail}` 形状（B17 回归锚，数目不变）。

### 4.2 活体验证（8021，重启加载新 dist；后端代码未变）

1. HTTP 直连：`score-chapter {demo-voice, story/0001/chapter.md}` →
   **200，total 81 / B，dialogues_scored 2**，四维 88/100/48/88。
2. 真实浏览器（demo-voice 工作区「角色声音联调演示」）：
   `?tab=novel-workbench` → 章节目录 → 第 1 章「阅读与评估」→ 新区块
   「对话人味评分」渲染 → 点「评估本章对话」→ **评分卡渲染**：
   共评分 2 段对话 · 人味评分 **81 / 100 · B** · 四维
   声音一致性 88 / 对话自然度 100 / 情感真实度 48 / 行为一致性 88 ·
   2 条问题（句长偏差、问句/叹句密度）· 改进建议。截图已存档（会话 artifacts）。
   —— 浏览器 UI → score-chapter → CLI → 聚合卡片链路首次打通。
3. B17 活体：角色声音页缓冲区追加未保存「临时测试角色」→ 试评 →
   UI 显示 CLI 拒因全文（见 §2）。

### 4.3 套件对账

| 基线 | 改动前 | 改动后 |
|---|---|---|
| 后端 Low-IL | 1740 / 96 / 0 | **1740 / 96 / 0**（104.88s；后端零改动） |
| 后端 High-IL | 1825 / 11 / 0 | **1825 / 11 / 0**（121.42s，权威） |
| 后端总用例 | 1836 | **1836**（不变） |
| 前端 npm test | 8 组 415 条 | **8 组 422 条 0 fail**（净增 7） |
| 前端 lint / build | 0 problems / ✓ | **0 problems / ✓ 6.30s** |
| 活体 e2e | 17 passed | **17 passed**（重启后复跑，0 skip） |
| 存储名审计 | [clean] | **[clean] exit 0** |

## 5. 本轮观察（未修，候选）

ReviewView 读取读者报告失败时，页面 alert 显示
`API Error 409: {"detail":"还没有读者评估，请先运行模拟读者。"}`
——`web/src/lib/api` 抛错的 message 内嵌原始 JSON，用户直读不友好。
属 B17 同族（错误信息面向机器而非人），建议 api 层对 4xx 解出 `detail`
拼进 message。列为 R27 候选 P2。

## 6. 风险与遗留问题

1. **外来工作树改动（连续第四轮，需维护者决策）**：15 个 `docs/HANDOVER*.md`
   （HANDOVER.md + ROUND10–23）删除仍未暂存。本轮继续按并发写入者纪律
   **未提交、未恢复**，仅显式路径提交本轮文件。历史可 `git show` 读取。
2. **R23+R24+R25+R26 四个提交未推送**（`origin/main..main` = 4）：推送需
   维护者先处理 git 代理/PAT（记忆 xs2-git-push-proxy），并核对 CI 四 job。
3. check-dialogue（契约 §3.5）仍未接入 UI：humanware 五端点已接其四
   （status/voice-file/generate/score-content/score-chapter），仅剩该端点。
4. 章节人味评分按**磁盘** chapter.md 与 character_voice.md 执行；与页面
   预览可能短暂不一致（预览读的是工作流文件端点同一磁盘文件，实际一致；
   voice 文件编辑后需先保存——组件文案已明示）。
5. POSIX 真跑（环境依赖）与 B16 真实并发复现（不可行）维持 R24 结论。

## 7. 下一轮迭代计划（Round 27 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | 维护者处理：外来删除核查（restore 或提交）+ 推送 4 提交 + CI 四 job 实跑核对 | 低 | 30min |
| P2 | check-dialogue 接入角色声音页（契约 §3.5，violations/suggestion UI）——humanware 接线收官 | 低 | 1.5h |
| P2 | api 层 4xx 错误信息人性化（解出 `detail`，§5 观察；B17 同族收口） | 低 | 1h |
| P3 | 试评/章节评分增强：评分后高亮命中口头禅位置、历史评分记录 | 低 | 1-2h |
| P3 | supervisor `_spawn` 真实并发测试（R24 遗留） | 中 | 1h |
| P3 | POSIX 真跑（环境决策归维护者） | 低 | 环境依赖 |

## 8. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest -q                                   # 1740/96/0（104.88s）
./.venv/Scripts/python.exe -m pytest tests/test_humanware_e2e.py -q       # 17 passed（重启服务后）
./.venv/Scripts/python.exe scripts/audit_storage_names.py                 # [clean] exit 0
sp='F:\DeterminFlow x2\xs2\.venv\Lib\site-packages'
MSYS2_ENV_CONV_EXCL=PYTHONPATH PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32" \
  C:/Windows/py.exe -X utf8 -m pytest -q -p no:cacheprovider              # 1825/11/0（High-IL 权威）
cd web
npm.cmd run test:desktop     # 116 passed（+7）
npm.cmd run lint             # 0 problems
npm.cmd test                 # 8 组 422 条 0 fail
npm.cmd run build            # ✓ 6.30s
# 服务重启（加载新 dist）：taskkill 旧 PID → ./.venv/Scripts/python.exe run.py
# HTTP 探活：score-chapter demo-voice 第 1 章 → 200 81/B/2 段
# 浏览器 e2e：demo-voice → 章节目录 → 阅读与评估 → 评估本章对话 → 卡片渲染（截图存档）
#            角色声音页缓冲区加未保存角色 → 试评 → CLI 409 拒因透传（B17）
```

## 9. 修改文件清单

```
web/src/components/ChapterHumanwareScore.tsx       # 新组件：score-chapter 接线（~100 行）
web/src/components/ChapterHumanwareScore.test.ts   # 新文件，7 用例
web/src/components/CharacterVoiceEditor.tsx        # B17：错误提取 detail 优先（1 行）
web/src/components/CharacterVoiceEditor.test.ts    # 409 mock 改真实 {detail} 形状（B17 锚）
web/src/pages/NovelWorkbenchPage.tsx               # ReviewView 挂载（import + 1 行）
web/package.json                                   # test:desktop 追加新测试文件
docs/HANDOVER_ROUND26.md                           # 本文件
docs/PROJECT_INFO.md                               # 项目状态追加 R26 条目
```
