# DeterminFlow (xs2) 交接报告 — Round 14（P0 humanware CLI 落地）

> 生成时间：2026-10-23
> 项目路径：F:/DeterminFlow x2/xs2（主仓库）；F:/DeterminFlow x2/DeterminFlow-Plugins（插件仓库）
> 分支：main（两个仓库各自）
> 本轮提交：xs2 `9614d03`、`d2f1e2b`、`dbaae08`；插件 `fea68e5`、`91c4914`
> 文档编码：UTF-8

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| **P0 端到端达成**：humanware 从"全部 501"变为可用 | generate-voice/score-content/check-dialogue 经 8021 API 实测 200；score-chapter 404/409 语义正确 |
| humanware_helper 脚本库已实现 | 插件仓库 `resources/script-library/xs2/humanware_helper/humanware_helper.py`（同名入口，纯规则引擎，5 命令） |
| 插件更新链路打通 | `POST /api/plugins/xs2-novel-flywheel/update` → commit 4eed8cb → **91c4914** → 重启 → runtime-resources 重建出 CLI |
| 回归无破坏 | humanware/extension/plugin 路由 63 passed；插件侧 13 条 pytest 通过 |
| uv.lock 决策执行 | 已加入 .gitignore（commit 9614d03），不纳入版本管理 |
| 工作区状态 | xs2 主仓库已干净（仅剩 .bak 未跟踪）；插件仓库已干净 |

## 2. 交付内容

### 2.1 插件仓库（DeterminFlow-Plugins）

`plugins/xs2-novel-flywheel/resources/script-library/xs2/humanware_helper/`：
- **humanware_helper.py**（同名入口，约 500 行）：5 个命令 `generate-voice` / `analyze-voice` / `score-text` / `score-chapter` / `check-dialogue`；纯规则确定性（无模型调用）；句法指纹启发式评分（句长/问叹比例/口头禅/禁用词），输出前端 HumanwareScoreCard 四维字段
- **SCRIPT.md**：frontmatter + 命令用法 + 退出码/流契约
- `tests/test_humanware_helper.py`：13 条 pytest（生成/分析/评分/章节聚合/穿越/404/禁用词）

插件提交：`fea68e5`（实现）+ `91c4914`（入口改名，满足 Script Library 预检的"同名入口"要求）。

### 2.2 xs2 主仓库

- `src/web/humanware_routes.py`：CLI 查找路径 `humanware_cli.py` → **`humanware_helper.py`**（commit d2f1e2b）
- `tests/test_humanware_routes.py`：两个 501 用例改为显式 mock CLI 缺失（环境无关，commit dbaae08）——因 CLI 现已真实存在，原依赖环境状态的断言会误报
- `docs/humanware-helper-contract.md`：**v2**（同名入口、章节路径 `story/{n}/chapter.md`、业务失败 **exit 0** + stdout error JSON 的退出码语义澄清、端到端验收已达成）
- `.gitignore`：`uv.lock` 排除（用户决策，commit 9614d03）

## 3. 实现要点与关键决策

1. **纯规则引擎而非 LLM**：确定性、零外部依赖、可测试——符合插件 file-only/deterministic 设计。评分是启发式基线（如冷静角色叹句比例高会扣"情感真实度"），后续可由模型版本增强，接口不变。
2. **退出码语义澄清（契约 v2）**：后端只在 `returncode != 0` 时返回 500，故业务失败（缺文件/未知角色）必须 **exit 0 + stdout error JSON**（code 透传）；仅进程级失败才 exit 非 0。
3. **同名入口约束**：插件预检要求 `humanware_helper/` 目录内入口与目录同名（`humanware_helper.py`），首版 `humanware_cli.py` 被预检拦截后改名并同步后端路径。
4. **激活链路**：插件源 commit → `POST /api/plugins/{id}/update`（checkout 同步 + content_sha256 变化）→ 重启服务 → runtime-resources 重建（revision 不匹配触发）。

## 4. 测试与验证

| 项 | 结果 |
|---|---|
| 插件侧 pytest（test_humanware_helper.py） | **13 passed** |
| xs2 侧 humanware/extension/plugin 路由 | **63 passed**（501 用例已环境无关化） |
| CLI 自测（mock 工作区） | 5 命令 + 409/400/404/banned 全符合契约 |
| 端到端（8021 API） | generate→200(character_count=2)；voice-file 读回完整；score-content→200(86/B)；check-dialogue→200(matches)；无 profiles→409；缺失章节→404 |
| 服务状态 | 8021 running；插件 `runtime_status=running`、`restart_required=false`、resolved_commit=91c4914 |

## 5. 遗留与下一轮建议

| 编号 | 问题 | 建议 |
|---|---|---|
| R14-1 | 评分模型为启发式基线，对冷静角色"情感真实度"偏严 | 若需要可迭代调参或引入模型增强（接口不变） |
| R14-2 | `analyze-voice` 未走独立 API 冒烟（与 generate 同链路，CLI 已验证） | 按需补一条 from_references 端到端 |
| R14-3 | ~~docs/HANDOVER_ROUND10.md.bak-20261022~~ | **已核实不存在**（磁盘无 *.bak*，git 状态干净） |
| R14-4 | 前端 7 处 react-refresh 结构告警（R13 保留项） | context/hook 拆分专项（可选） |
| R14-5 | 36 条环境限制 skipped | 管理员/WSL/macOS 复跑 |
| R14-6 | conftest 文本匹配跳过机制（R11-2） | 收敛为统一装饰器 |

**插件仓库后续**：`fea68e5`/`91c4914` 尚未推送远端（本地 main 领先）；如需共享，`git push origin main`。

## 6A. 前端「角色声音」链路联调验收（追加，2026-10-23）

| 项 | 结果 |
|---|---|
| API 全链路模拟（scripts/_hw_frontend_sim.py，13 步幂等） | **13/13 PASS × 2 次**（projects→workflows→files→status→voice-file→generate→status→read→PUT save→verify→score-content→score-chapter→check-dialogue） |
| 静态资源 | index HTML + JS/CSS entry + NovelWorkbenchPage 懒加载 chunk 全部 200 |
| CharacterVoiceEditor 组件测试（7 条，happy-dom+mock fetch） | **7/7 PASS**（归一化/生成门控/PUT 保存/失败提示/内容加载），纳入 npm test:desktop |
| 前端全套 | npm test 全过（含新用例）、lint 0 errors、build 成功 |
| demo 工作区 | `data/workspaces/books/demo-voice`（含 profiles/story/.novel-project.json），可用于浏览器人工验收后删除 |

浏览器人工验收步骤：
1. 打开 `http://localhost:8021/?tab=novel-workbench`，左侧「角色声音」进入页面；
2. 应显示「状态: 未创建」+「角色数量 0」，profiles 存在时「从角色档案生成」可点击；
3. 点击生成 → 提示成功、状态变「已创建」、角色数量 2、编辑器载入两个角色锚点；
4. 编辑任意内容 → 点「保存」→ 提示「保存成功」；
5. 保存后可刷新页面，内容仍在（PUT/GET 已验证）。


## 6. 命令记录（本轮）

```
git add/commit（.gitignore: uv.lock 决策）
写 humanware_helper.py + SCRIPT.md + tests/test_humanware_helper.py（13 条通过）
插件预检拦截（入口需同名）→ git mv humanware_cli.py humanware_helper.py + 后端路径同步
POST /api/plugins/xs2-novel-flywheel/update（200, resolved_commit=91c4914, restart_required=true）
重启 8021 → runtime-resources 重建（humanware_helper.py 存在）
Python urllib 端到端：generate 200 / score 200 / check 200 / 409 / 404
清理临时工作区 hw-test-ws、hw-e2e
xs2 回归 63 passed → 提交（d2f1e2b / dbaae08）
```