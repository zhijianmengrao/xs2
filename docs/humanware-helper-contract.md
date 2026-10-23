# Humanware Helper CLI 接口契约（P0 前置物）

> 版本：v1（2026-10-23，对应 `src/web/humanware_routes.py` 的调用约定）
> 目的：为在 `F:\DeterminFlow x2\DeterminFlow-Plugins`（xs2-novel-flywheel 插件）补发
> `humanware_helper` 脚本库提供实现与验收依据。CLI 未部署时后端按设计返回 501。

## 1. 部署位置与发现方式

后端 `_get_humanware_cli_path()` 在当前插件版本查找的路径：

```
data/plugins/runtime-resources/xs2-novel-flywheel/script-libraries/0/xs2-novel-flywheel-xs2/humanware_helper/humanware_cli.py
```

对应插件源仓库（`DeterminFlow-Plugins/plugins/xs2-novel-flywheel/resources/script-library/xs2/`）中的
`humanware_helper/humanware_cli.py`。发布新插件版本并完成 resources prepare 后，
该路径由 runtime-resources 生成。**验收时以 `runtime-resources/.../humanware_helper/humanware_cli.py`
存在且可执行 `python humanware_cli.py --version` 为准。**

CLI 用 `sys.executable`（后端 venv 解释器）执行，参数经 `subprocess.run([...], text=False, timeout=120)`
以列表形式传递（无 shell 注入面）；stdout 为 UTF-8 JSON（单行或格式化均可）。

## 2. 通用输出契约

所有命令必须向 **stdout** 打印一个 JSON 对象，**成功时进程退出码为 0**，失败时退出码非 0。

### 2.1 成功（HTTP 透传）

```json
{ "status": "success", "message": "人话描述", ...命令特定字段 }
```

### 2.2 失败（业务失败 / 状态码透传）

```json
{ "status": "error", "message": "人话错误原因", "code": 409 }
```

- `code` 取值范围：400（输入错误）、409（工作区状态不满足）、500（内部失败）、501（功能未实现）。
- 后端将 `code` 直接作为 HTTP 状态码返回给前端（见 `_generate_voice_file` / `score_content` / `score_chapter`）。

### 2.3 硬性规则

1. **必须输出合法 JSON**，否则后端返回 500「无法解析命令输出」（原始 stdout 回传）。
2. 严禁输出多余的非 JSON 前缀（日志打到 stderr）。
3. 中文输出使用 UTF-8；`errors="ignore"` 兜底，但契约要求 UTF-8。
4. 单命令执行不得超过 120 秒（后端 timeout=120，超时转 500）。

## 3. 命令定义

### 3.1 `generate-voice <workspace_root>`

从 `meta/character_profiles.md` 生成 `meta/character_voice.md` 模板。

- 输入：`workspace_root` 为 `data/workspaces/books/<id>` 的**绝对路径**。
- 前置：`<workspace_root>/meta/character_profiles.md` 必须存在且包含 `## 角色名` 条目。
- 输出（成功）：
```json
{ "status": "success", "message": "已生成 N 个角色声音模板", "character_count": 3 }
```
- 行为要求：将生成内容写入 `<workspace_root>/meta/character_voice.md`（UTF-8）。
- 失败：profiles 缺失 → `code: 409, message: "character_profiles.md 不存在，请先创建角色档案"`。

### 3.2 `analyze-voice <workspace_root>`

从参考资料（`learning/` 目录或 `references/`）分析提炼各角色声音特征并写入 `meta/character_voice.md`。

- 输出（成功）：同 3.1（`status/ message / character_count`）。
- 失败：无可用参考 → `code: 409`。

### 3.3 `score-text <workspace_root> <character> <content>`

对一段文本按角色声音定义评分。

- 输入：`character` 角色名（UTF-8），`content` 待评文本（最多 10M 字符，后端已限）。
- 输出（成功）——**字段与前端 `HumanwareScoreCard` 一一对应**：
```json
{
  "status": "success",
  "total_score": 88,
  "grade": "B",
  "summary": "总体评价",
  "detailed_scores": { "声音一致性": 85, "对话自然度": 90, "情感真实度": 80, "行为一致性": 95 },
  "issues": [ { "dimension": "声音一致性", "type": "voice_break", "severity": "medium", "message": "..." } ],
  "recommendation": "改进建议"
}
```
- `total_score`：0–100；`grade`：A/B/C/D/F；`detailed_scores` 键名固定为上述四个维度（前端硬编码渲染）。
- `issues` 可为空数组；`recommendation` 可为空字符串。
- 失败：`character` 不在角色声音定义中 → `code: 409, message: "角色 X 未在 character_voice.md 中定义"`。

### 3.4 `score-chapter <workspace_root> <chapter_file>`

对章节文件（相对于工作区的路径，如 `manuscript/chapters/0001.md`）内所有对话批量评分。

- 输出（成功）——聚合结构（前端消费方按字段名取值）：
```json
{
  "status": "success",
  "total_score": 82,
  "grade": "B",
  "summary": "本章对话评分汇总",
  "detailed_scores": { "声音一致性": 80, "对话自然度": 85, "情感真实度": 78, "行为一致性": 85 },
  "issues": [ ... ],
  "recommendation": "..." ,
  "dialogues_scored": 12
}
```
- 失败：章节文件不存在 → `code: 404, message: "章节文件不存在: <chapter_file>"`。

### 3.5 `check-dialogue <workspace_root> <character> <dialogue>`

检查一段对话是否符合角色声音定义（返回是否符合与偏离点）。

- 输出（成功）：
```json
{
  "status": "success",
  "matches": true,
  "character": "张三",
  "violations": [ { "rule": "句法指纹", "detail": "句长超出平均 2.5 倍" } ],
  "suggestion": "缩短句式，保持 15 字以内"
}
```
- `matches=false` 时 `violations` 非空并给出 `suggestion`。

## 4. 工作区目录契约（CLI 可读写的路径）

```
<workspace_root>/
├── meta/
│   ├── character_profiles.md    # 角色档案（generate-voice 输入，可不存在 → 409）
│   ├── character_voice.md       # 角色声音定义（score-text/chapter 输入，CLI 写入）
│   └── console-*.md             # 已确认的创作计划（只读，可不存在）
├── learning/candidates.json     # 参考写法候选（analyze-voice 输入，可不存在）
├── references/                  # 作者提供的参考资料（analyze-voice 输入）
└── manuscript/...               # 章节原稿（score-chapter 输入）
```

CLI **不得**读写工作区之外的文件；所有路径解析须以 `workspace_root` 为根并拒绝 `..` 逃逸。

## 5. 实现注意事项（Windows）

1. 脚本以 `python humanware_cli.py <cmd> ...` 运行，`sys.executable` 为 venv 桩解释器；
   脚本内如需 import 第三方库，须使用运行解释器已安装的依赖（与 xs2 主进程同 venv）。
2. `print(json.dumps(...))` 前应 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，
   避免 Windows 控制台 GBK 重定向破坏 JSON。
3. 所有文件读写显式 `encoding="utf-8"`；`Path.write_text(..., newline="\n")` 保证确定性字节。

## 6. 验收标准（对应用户侧测试）

| 命令 | 后端端点 | 现有测试 | 验收 |
|---|---|---|---|
| generate-voice | POST /api/humanware/generate-voice-file | tests/test_humanware_routes.py::HumanwareCliAvailableTests::test_generate_voice_file_success | 200 + character_count=3 |
| analyze-voice | 同上（from_references=true） | 同上（可加一条） | 200 |
| score-text | POST /api/humanware/score-content | ::test_score_content_propagates_business_result | 200 + total_score=88 透传 |
| score-chapter | POST /api/humanware/score-chapter | 新增 | 200 + dialogues_scored |
| check-dialogue | POST /api/humanware/check-dialogue | 新增 | 200 + matches |

端到端验收（发布插件 + 重新 prepare 后）：
```
python .\run.py                          # 8021
GET  /api/humanware/status/welcome       # 200
PUT  /api/humanware/voice-file/welcome   # 200（写入）
POST /api/humanware/generate-voice-file  # 200（不再 501）
POST /api/humanware/score-content        # 200（评分透传）
```