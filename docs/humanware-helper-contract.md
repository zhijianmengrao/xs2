# Humanware Helper CLI 接口契约（P0 前置物）

> 版本：v3.2（2026-10-24；v3.2 新增：`workspace_id` 尾随点/空白别名一律 400，Windows 名称约束
> 统一收敛到 `src/web/path_guard.py`（humanware 与 novel-console 两个路由面共用）。
> v3.1（2026-10-23）：stdin 阈值可经环境变量覆盖、后端输入预校验语义
> （NUL 字符 / Windows 保留设备名 → HTTP 400，见 §2.2）。
> v3（2026-10-23）：超长内容 `-` stdin 约定、check-dialogue 业务错误码透传。
> v2 依据实现回写：CLI 文件名为同名入口 humanware_helper.py、
> 章节路径为 story/{n}/chapter.md、业务失败 exit 0）
> 对应 `src/web/humanware_routes.py` 的调用约定。
> 状态：**已实现并端到端验证**（插件 commit 91c4914 → e4ba419 → 本轮，xs2 commit d2f1e2b → 本轮）。

## 1. 部署位置与发现方式

后端 `_get_humanware_cli_path()` 查找的路径：

```
data/plugins/runtime-resources/xs2-novel-flywheel/script-libraries/0/xs2-novel-flywheel-xs2/humanware_helper/humanware_helper.py
```

对应插件源仓库（`DeterminFlow-Plugins/plugins/xs2-novel-flywheel/resources/script-library/xs2/`）中的
`humanware_helper/humanware_helper.py`（**入口文件名必须与目录同名**，满足插件
Script Library 预检要求）。发布新插件版本并完成 resources prepare 后，
该路径由 runtime-resources 生成。**验收以 `runtime-resources/.../humanware_helper/humanware_helper.py`
存在且可执行 `python humanware_helper.py --version` 为准。**

CLI 用 `sys.executable`（后端 venv 解释器）执行，参数经 `subprocess.run([...], text=False, timeout=120)`
以列表形式传递（无 shell 注入面）；stdout 为 UTF-8 JSON（单行或格式化均可）。

**超长内容 stdin 约定（v3）**：`score-text` 的 `content` 与 `check-dialogue` 的 `dialogue`
超过 **8,192 字符** 时，后端将该参数替换为 `-` 并把真实内容（UTF-8）经 **stdin** 传入；
CLI 侧参数值为 `-` 即读 stdin（`humanware_helper._arg_or_stdin`）。
原因：Windows `CreateProcess` 命令行上限约 32,767 UTF-16 单元（超限报
`WinError 206`，实测 33,000 字符触发）、POSIX 受 `ARG_MAX` 约束，
而 HTTP 层 `score-content` 允许至 10M 字符。短内容仍走 argv（行为不变）。
阈值可经环境变量 `DETERMINFLOW_HUMANWARE_STDIN_ARG_THRESHOLD` 覆盖
（正整数字符数；缺失或非法值回退默认 8,192——v3.1）。
注意：内容恰为字面量 `"-"` 时会被 stdin 通道吞掉（stdin 空则按无内容评分），
属可接受的边界语义。

## 2. 通用输出契约

所有命令必须向 **stdout** 打印一个 JSON 对象。

> **退出码语义（v2 澄清，务必遵守）**：后端 `_run_humanware_command_blocking` 只在
> `returncode != 0` 时返回 500（不解析 stdout）。因此：
> - **业务失败**（缺文件/未知角色/空参考等）必须 **exit 0** 并输出
>   `{"status":"error","message":...,"code":<int>}`，后端才会透传 `code` 为 HTTP 状态码；
> - **仅进程级失败**（参数错误、IO 崩溃等）才 exit 非 0，后端将其映射为 HTTP 500。

### 2.1 成功（HTTP 透传）

```json
{ "status": "success", "message": "人话描述", ...命令特定字段 }
```

### 2.2 业务失败（状态码透传，exit 0）

```json
{ "status": "error", "message": "人话错误原因", "code": 409 }
```

- `code` 取值范围：400（输入错误）、404（文件不存在）、409（工作区状态不满足）、500（内部失败）。
- 后端将 `code` 直接作为 HTTP 状态码返回给前端（见 `_generate_voice_file` / `score_content` /
  `score_chapter` / `check_dialogue`——v3 起 check-dialogue 与其余端点一致透传，此前误为固定 500）。
- **后端输入预校验（v3.1，v3.2 扩展）**：以下输入在后端即被拒绝（HTTP 400），不会启动 CLI 进程：
  - `character` / `dialogue` / `chapter_file` 含 NUL 等无法进入 argv 的字符
    （此前 500「embedded null character」）；
  - `workspace_id` 为 Windows 保留设备名（`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`/`CONIN$`/
    `CONOUT$`，含大小写与带扩展名变体，如 `NUL.txt`——此前 `NUL` 因 `Path.exists()` 恒真可返回 200）；
  - **（v3.2）`workspace_id` 尾随点或空格**（`welcome`、`welcome..`）：Windows 解析路径段时
    会剥离尾随点/空白，使 `welcome.` 成为真实工作区 `welcome` 的**别名**（实测 v3.1 服务返回 200
    并可读写真实工作区内容），而 POSIX 上两者是不同名字。为保证「按给定名字定位工作区」在
    两个平台语义一致，此类名字一律 400；名字**中间**的点（`alpha.md`）仍然合法（→ 404）。
    判定规则集中在 `src/web/path_guard.py`，与 novel-console 的 `safe_target`/`library_path` 共用。

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

- 输入：`character` 角色名（UTF-8），`content` 待评文本（最多 10M 字符，后端已限；
  超过 8,192 字符时后端以 `-` 占位、真实内容走 stdin——见 §1 v3 约定）。
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

对章节文件（相对于工作区的路径，如 `story/0001/chapter.md`）内所有对话批量评分。
对话归属其前最近的 `## 角色名` 段落；无归属时按默认锚点评分。

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
- 失败：章节文件不存在 → `code: 404, message: "章节文件不存在: <chapter_file>"`；
  路径越出工作区 → `code: 400`。

### 3.5 `check-dialogue <workspace_root> <character> <dialogue>`

检查一段对话是否符合角色声音定义（返回是否符合与偏离点）。

- 输入：`dialogue` 最多 200K 字符（HTTP 层限制）；超过 8,192 字符时后端以 `-` 占位、
  真实内容走 stdin（v3，同 §1）。业务失败（未知角色/缺 voice 文件）透传 409（v3）。

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
├── learning/candidates.json     # 预留：参考写法候选（当前实现未读取，analyze-voice 仅扫描 references/）
├── references/                  # 作者提供的参考资料（analyze-voice 输入）
└── story/                       # 章节原稿（score-chapter 输入）
    └── 0001/chapter.md
```

CLI **不得**读写工作区之外的文件；所有路径解析须以 `workspace_root` 为根并拒绝 `..` 逃逸。

## 5. 实现注意事项（Windows）

1. 脚本以 `python humanware_helper.py <cmd> ...` 运行，`sys.executable` 为 venv 桩解释器；
   脚本内如需 import 第三方库，须使用运行解释器已安装的依赖（与 xs2 主进程同 venv）。
2. `print(json.dumps(...))` 前应 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，
   避免 Windows 控制台 GBK 重定向破坏 JSON。
3. 所有文件读写显式 `encoding="utf-8"`；`Path.write_text(..., newline="\n")` 保证确定性字节。

## 6. 验收标准（已达成，2026-10-23 实测）

| 命令 | 后端端点 | 测试 | 实测 |
|---|---|---|---|
| generate-voice | POST /api/humanware/generate-voice-file | tests/test_humanware_routes.py + 插件 tests/test_humanware_helper.py | **200 + character_count=2** |
| analyze-voice | 同上（from_references=true） | 插件 13 条 pytest | CLI 200（API 侧与 generate 同链路） |
| score-text | POST /api/humanware/score-content | 同上 | **200 + total_score 透传** |
| score-chapter | POST /api/humanware/score-chapter | 同上 | CLI 200 + dialogues_scored；API 404/409 语义 |
| check-dialogue | POST /api/humanware/check-dialogue | 同上 | **200 + matches/violations** |

端到端链路（已验证）：
```
插件源提交 fea68e5 + 91c4914 → POST /api/plugins/xs2-novel-flywheel/update
  → 重启 8021 → runtime-resources 重建出 humanware_helper/humanware_helper.py
GET  /api/humanware/status/welcome       → 200（voice_file_exists=false）
PUT  /api/humanware/voice-file/{id}      → 200（写入）
POST /api/humanware/generate-voice-file  → 200（character_count=2，不再 501）
POST /api/humanware/score-content        → 200（四维评分透传）
POST /api/humanware/check-dialogue       → 200（matches 判定）
```