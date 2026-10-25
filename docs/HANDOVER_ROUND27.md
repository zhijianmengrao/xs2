# DeterminFlow (xs2) 交接报告 — Round 27（维护态第五轮：check-dialogue 接线收官 + api 层 4xx 错误人因化）

> 本轮定位：R26 之后的**维护态第五轮**，候选起点=R26 §7 P2 两项：
> ①契约 §3.5 `check-dialogue`（HTTP `/api/humanware/check-dialogue`）接入
> 「角色声音」页——**humanware 五端点接线就此收官**（status / voice-file /
> generate-voice-file / score-content / score-chapter / check-dialogue 全部有
> UI 消费方）；②api 层 4xx 错误信息人因化（R26 §5 观察，B17 同族收口）：
> `web/src/lib/http-client.ts` 抛错 message 不再内嵌原始 JSON。**后端零改动**。
> 基线：`0f131be`（R26 提交）。工作树 15 个 HANDOVER 外来删除仍在
> （未提交未恢复，连续第五轮，见 §6）。

## 1. 基线终验（改动前）

| 验证项 | 结果 | 与 R26 基线对比 |
|---|---|---|
| 8021 服务健康 | `HTTP 200`（R26 dist，重启前） | 一致 |
| git 状态 | main 领先 origin **4** commits | R26 遗留，未变 |
| 工作树 | 15 个 HANDOVER 文档删除（未暂存，外来） | 未变 |

## 2. 实现 A：check-dialogue 接入角色声音页（纯前端）

- `web/src/components/CharacterVoiceEditor.tsx`（+~110 行）：
  - 新区块「检查一段对话（声音符合性）」：复用编辑器 `## 角色名` 解析的
    characterNames（独立下拉 `aria-label="选择检查角色"`）+ 对话 textarea
    （rows=4）+「检查对话」按钮；
  - `runCheck()`：POST `/api/humanware/check-dialogue`，body
    `{workspace_id: workspaceKey（末段归一化）, character, dialogue}`；
  - 结果渲染（契约 §3.5）：`matches=true` → 绿色「符合「角色」的声音定义」
    徽章；`matches=false` → 黄色「偏离」徽章 + violations 列表
    （rule + detail 逐条）+「修改建议」框；violations/suggestion 为空时对应
    区块不渲染（响应字段做了类型收窄过滤）；
  - 守卫：未选角色或对话为空按钮禁用 + `runCheck` 内早退（双层，与试评区
    同规）；业务失败 409 → B17 同源 `detail` 优先透传；网络失败 →
    「服务不可达」。

## 3. 实现 B：api 层 4xx 错误人因化（B17 同族收口）

- **问题（R26 §5 观察）**：`request()` 抛错 message 为
  `API Error 409: {"detail":"还没有读者评估…"}` —— 原始 JSON 直达用户
  （读者评估页 alert 实测）。
- **修复**：`web/src/lib/http-client.ts` 新增 `describeErrorBody()`：
  响应体能解析为 JSON 且 `detail` 为非空字符串 → message 用该人话拒因；
  其余形状（非 JSON / detail 非字符串）保留原文以便排查。
- **配套兼容**：`getRoundtableErrorDescription`（`web/src/lib/roundtableFeedback.ts`，
  唯一解析该 message 格式的消费方）扩展：旧 JSON 格式优先（不变），无 `{`
  或 JSON 损坏时按 `^API Error (\d{3}): (.+)$` 提取，**仅 4xx** 展示纯文本
  负载，5xx 保持隐藏（不外泄内部信息）。矩阵：
  - `API Error 400: {"detail":"至少需要保留 2 个席位"}` → detail（旧行为，不变）
  - `API Error 409: 还没有读者评估…`（新格式）→ 直接展示（新增）
  - `API Error 500: internal traceback` / `500: {"detail":{…}}` /
    `500: 服务器内部错误文本` → 兜底文案（不变）
- **影响面**：全站经 `request()` 的错误提示更可读；圆桌错误语义经矩阵验证
  无回归；console.error 仍记录原始 body（排障信息不丢）。

## 4. 测试用例与验证

### 4.1 前端单测（净增 12 条；npm test 8 组 422 → **434**）

| 文件 | 用例 | 断言要点 |
|---|---|---|
| CharacterVoiceEditor.test.ts +5 | check section lists the same parsed characters | 检查下拉含林晚/沈砚 |
| | check button stays disabled until both character and dialogue are provided | 双输入守卫 + 空输入零请求 |
| | check flow posts check-dialogue with normalized id and renders violations | POST body 三字段；偏离徽章 + rule/detail + 修改建议 |
| | check result shows the match state and hides the violations list | 符合徽章；无偏离徽章、无违规列表 |
| | check 409 surfaces the FastAPI detail message and keeps the result hidden | `{detail}` 透传；结果区隐藏（B17 形状锚） |
| http-client.test.ts（新文件，5 条） | 4xx FastAPI string detail is surfaced as the human message | message=`API Error 409: <人话>`（无花括号） |
| | non-JSON error bodies keep their raw text | 500 原文保留 |
| | non-string detail keeps the raw JSON | `{"detail":{…}}` 原样（排障） |
| | 4xx non-JSON body is kept as-is | 原文保留 |
| | successful responses parse JSON and empty bodies resolve to undefined | 成功路径不回归 |
| roundtableStream.test.ts +2 | shows humanized 4xx payloads | 新格式 4xx 直显 |
| | keeps humanized 5xx payloads hidden | 新格式 5xx 仍兜底 |

`test:desktop` 116 → **121**（+http-client 5）；`test:conversation` 135 → **137**（+roundtable 2）。

### 4.2 活体验证（8021，重启加载新 dist；后端代码未变）

1. HTTP 探活 check-dialogue（demo-voice，林晚）：
   - 长句「结论已经给出，方案可以执行，我们按既定步骤推进即可。」→
     **matches=false**，violation `句法指纹: 平均句长 26.0 字，锚点为 9.7 字`，
     suggestion「对照锚点调整句长或用词后复检」；
   - 短爆发句「什么？！怎么会这样？？…」→ **matches=true**，violations=[]。
2. 真实浏览器（demo-voice）：角色声音页 → 检查区选林晚 → 填偏离句 →
   「检查对话」→ **偏离「林晚」的声音定义 + 句法指纹违规 + 修改建议**渲染；
   换符合句复检 → **符合「林晚」的声音定义**（无违规列表）。截图存档
   （会话 artifacts）。—— UI → check-dialogue → CLI → violations/suggestion
   链路首次打通，humanware 五端点全部有 UI 消费方。
3. 错误人因化活体：读者评估页（demo-voice，无读者报告）alert 从
   `API Error 409: {"detail":"还没有读者评估，请先运行模拟读者。"}`（R26 实测）
   变为 **`API Error 409: 还没有读者评估，请先运行模拟读者。`**。

### 4.3 套件对账

| 基线 | 改动前 | 改动后 |
|---|---|---|
| 后端 Low-IL | 1740 / 96 / 0 | **1740 / 96 / 0**（105.55s；后端零改动） |
| 后端 High-IL | 1825 / 11 / 0 | **1825 / 11 / 0**（124.83s，权威） |
| 后端总用例 | 1836 | **1836**（不变） |
| 前端 npm test | 8 组 422 条 | **8 组 434 条 0 fail**（净增 12） |
| 前端 lint / build | 0 problems / ✓ | **0 problems / ✓ 6.34s** |
| 活体 e2e | 17 passed | **17 passed**（重启后复跑，0 skip） |
| 存储名审计 | [clean] | **[clean] exit 0** |

## 5. 风险与遗留问题

1. **外来工作树改动（连续第五轮，需维护者决策）**：15 个 `docs/HANDOVER*.md`
   删除仍未暂存。本轮继续**未提交、未恢复**，仅显式路径提交本轮文件。
2. **R23–R27 五个提交未推送**（`origin/main..main` = 5）：推送需维护者先处理
   git 代理/PAT（记忆 xs2-git-push-proxy），并核对 CI 四 job。
3. humanware 接线已收官；「小说创作全流程」前端的下一批候选见 §7。
4. check-dialogue 的 `matches` 判定依赖 CLI 的锚点规则（句长/问叹密度等），
   语义以插件仓库 `humanware_helper.py` 为准；本轮仅接线未改算法。
5. POSIX 真跑（环境依赖）与 B16 真实并发复现（不可行）维持 R24 结论。

## 6. 下一轮迭代计划（Round 28 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | 维护者处理：外来删除核查（restore 或提交）+ 推送 5 提交 + CI 四 job 实跑核对 | 低 | 30min |
| P2 | 角色声音页三区块（试评/检查/编辑器）共享「角色下拉 + 内容输入」子组件抽取（可维护性：三处同构逻辑收敛） | 低 | 1.5h |
| P2 | 章节人味评分/对话检查结果持久化展示（评分历史记录，localStorage 或工作区文件） | 低-中 | 2h |
| P3 | desktop updater endpoints 切自有 latest.json 的分发地址决策（R22 遗留安全失效态） | 中 | 决策+1h |
| P3 | supervisor `_spawn` 真实并发测试；POSIX 真跑 | 中/低 | 1h/环境 |

## 7. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest -q                                   # 1740/96/0（105.55s）
./.venv/Scripts/python.exe -m pytest tests/test_humanware_e2e.py -q       # 17 passed（重启服务后）
./.venv/Scripts/python.exe scripts/audit_storage_names.py                 # [clean] exit 0
sp='F:\DeterminFlow x2\xs2\.venv\Lib\site-packages'
MSYS2_ENV_CONV_EXCL=PYTHONPATH PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32" \
  C:/Windows/py.exe -X utf8 -m pytest -q -p no:cacheprovider              # 1825/11/0（High-IL 权威）
cd web
npm.cmd run test:desktop     # 121 passed（+5 http-client）
npm.cmd run test:conversation# 137 passed（+2 roundtable）
npm.cmd run lint             # 0 problems
npm.cmd test                 # 8 组 434 条 0 fail
npm.cmd run build            # ✓ 6.34s
# 服务重启（加载新 dist）：taskkill 旧 PID → ./.venv/Scripts/python.exe run.py
# HTTP 探活：check-dialogue demo-voice 林晚 偏离/符合两态 → matches false/true
# 浏览器 e2e：角色声音页检查区偏离+符合两态渲染（截图存档）；
#            读者评估页 alert 人因化（无原始 JSON）
```

## 8. 修改文件清单

```
web/src/components/CharacterVoiceEditor.tsx        # 检查区块 + runCheck（+~110）
web/src/components/CharacterVoiceEditor.test.ts    # +5 用例 + mock 扩展
web/src/lib/http-client.ts                         # describeErrorBody 人因化（+15/-2）
web/src/lib/http-client.test.ts                    # 新文件，5 用例
web/src/lib/roundtableFeedback.ts                  # 兼容纯文本 4xx 负载（+9/-1）
web/src/lib/roundtableStream.test.ts               # +2 用例
web/package.json                                   # test:desktop 追加 http-client.test.ts
docs/HANDOVER_ROUND27.md                           # 本文件
docs/PROJECT_INFO.md                               # 项目状态追加 R27 条目
```
