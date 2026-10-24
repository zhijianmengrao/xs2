# DeterminFlow (xs2) 交接报告 — Round 20（名字面第四轮审计 → B11/B12/B13 三个设备名缺陷修复 + 零误伤核查）

> 本轮定位：R19 §9 的 P1「R19-3 决策 `_PLUGIN_ID_RE` 是否拒设备名」落地，并把同一类
> 缺陷在**其余未审计的名字面**一次扫清。上一轮修的是 B10（附件文件名），本轮修的是
> **插件 id / 资源 id / 市场 Skill id** 三个「名字 → 目录名」拼接面。
> 基线：`df21c5d`（R19 提交），未推送 30 笔。

## 1. 结论摘要

| 项 | 结果 |
|---|---|
| 本轮缺陷 | 3 个（B11 插件 id / B12 资源 id / B13 市场 Skill id），同一根因族 |
| 新增测试 | 93 条（`test_plugin_name_guard.py` 60 + `test_marketplace_skill_id_guard.py` 33） |
| Low-IL 全量 | **1720 passed / 96 skipped / 0 failed**（基线 1627/96，净增 = 93） |
| High-IL 全量 | **1805 passed / 11 skipped / 0 failed**（R19 1697/26；净增 93 + e2e 15 由 skip 转 pass） |
| 前端 | lint 0 problems、test 6 pass / 0 fail、build 6.30s（本轮未改前端） |
| 零误伤 | 真实配置/锁文件/21 个插件清单/16 个资源目录/6 个已装 Skill **0 拒绝** |
| 优化 | `.gitignore` 补 `/tmp*`（实测发现 `tmp*/` 漏掉 mkstemp **文件**） |
| 遗留 | 52 个 `determinflow-executor-*` 残留目录（gitignore 内，未修）；POSIX 真跑无法本地验证 |

一句话：**Windows 保留设备名（`nul`/`con`/`com1`…）在三个「名字变目录」的面上会变成幻影目录，
本轮把三处入口统一拒绝，判定放在 `src/core/win_names.py` 单一规则源，且平台无关。**

## 2. 测试计划（本轮）

| 优先级 | 目标 | 手段 | 结果 |
|---|---|---|---|
| P0 | 确认基线可复现（不虚报） | 服务在跑时跑全量，与 R19 停服数对账 | 1627/96，与 R19 1612/111 精确对账（e2e 15 由 skip→pass） |
| P1 | R19-3：插件 id 是否拒设备名 | 读码定位所有「id→路径」拼接点 + 逐点实证 | 形成 B11/B12 两个缺陷 |
| P1 | 未审计名字面普查 | grep 全部 `/<name>` 拼接与 `exists()` 判定 | 发现 B13（市场 Skill id） |
| P1 | 三个缺陷红灯→修复→绿灯 | 先写复现脚本取证，再写 pytest 断言 | 93 条新测试全绿 |
| P2 | 零误伤 | 扫描真实数据与全部仓库清单 | 0 拒绝 |
| P2 | 独立复核审计结论 | 对子代理给出的每条「缺陷」逐一验伪 | **全部证伪**（见 §8） |
| P3 | 前端与文档 | 三连 + 交接 | 通过 |

## 3. 测试用例与执行结果

### 3.1 基线核实（真实环境，非推断）

- 8021 服务为 **v3.3**（pid 81092，11:58:43 启动），用 `urllib` 直连（**不用** `Invoke-WebRequest`，
  因 .NET `System.Uri` 会剥尾随点，R18 已证此坑）：`workflow_id=中文书` → 400、
  `workspace=…/books/NUL` → 400、对照组 → 200。说明 R18 的 B6/B7 已在线上生效。
- 服务在跑时全量：**1627 passed / 96 skipped / 0 failed（111s）**。与 R19 停服 1612/111 的
  差值恰好是 e2e 15 条（服务在跑则执行）。

### 3.2 名字拼接点普查（本轮验收物）

对 `src/` 全量检索「变量参与路径拼接」与「以 `exists()` 判定存在性」两类点位，得到下表。
**判定原则**：名字若会成为文件系统路径段 → 必须拒设备名；若只是 JSON 文档内的键 → 不拒。

| 名字面 | 是否落盘为路径 | 处置 | 依据 |
|---|---|---|---|
| 插件 id（`checkouts/<id>`、`runtime-resources/<id>`、锁文件键） | 是 | **修（B11）** | 见 3.3 |
| 资源前缀 / effective 资源 id（`copytree` 目标目录名） | 是（4 类） | **修（B12）** | 见 3.4 |
| 市场 Skill id / 包内 `name`（`marketplace-skills/<id>`） | 是 | **修（B13）** | 见 3.5 |
| `process_id`（`log_root/<owner>/<id>.log`） | 是 | **修（B11 附带）** | 与 B10 同族 |
| agent / prompt / preset_phrase 资源 id | 否（JSON 键） | 豁免 | 拒了会误伤正文里恰好叫 `nul` 的键 |
| `validate_plugin_subdirectory` 的中间段 | 是 | 豁免（已足够） | 幻影段使 `is_dir()` 为假 → 清单查找失败 → `InvalidPluginPackageError`，**响亮失败无假成功** |
| `humanware_routes.py:106` 的 runtime-resources 路径 | 是 | 豁免 | 插件 id 为硬编码常量，非外部输入 |
| `mention_routes` | 否 | 豁免 | 只读查询 |
| 小说导出 `filename` | 仅响应头 | 豁免 | 只进 `Content-Disposition`，不落盘 |

### 3.3 B11 取证：插件 id = `nul` → **HTTP 500**（不是 400）

复现脚本（一次性，已删除）逐步实测：

```
P2  os.replace(prepared → checkouts/nul/<rev>)
    mkdir(parents=True) 后 dest.parent.exists(): True   is_dir(): False   ← 幻影
    os.replace → RAISED FileNotFoundError winerror=3
    isinstance OSError: True | isinstance ValueError: False
    => OSError 不被 _raise_http_error 转换 → HTTP 500
P3  prepare_plugin_resources(extension_id='nul')  → RAISED OSError winerror=87
```

根因链：`_PLUGIN_ID_RE = ^[a-z0-9]+(?:-[a-z0-9]+)*$` 与设备名同型 → 小写 `nul` 通过校验 →
`prepare_plugin_resources` 在 `runtime_root/<id>` 上 `_atomic_replace_directory` 报 **WinError 87** →
`store._place_checkout` 的 `os.replace` 报 **WinError 3** → 两者都是 `OSError`，
而 `plugin_routes._raise_http_error` 只映射 `SourceTrustError`/`PluginStoreError`/`ValueError`，
故直接 500。修复后同一路径在**建目录之前**就抛 `ResourceIdError`（`ValueError` 子类）→ **400**，零残留。

### 3.4 B12 取证：资源 effective id = `nul` → 幻影目录吞资源

```
build_resource_id_plan("p1","",{"workflows":["nul"]})   → 接受（修复前）
copytree(src/nul → dst/nul)                             → RAISED OSError winerror=1
(dst/nul).exists(): True  is_dir(): False  dst 列表: []   definition.json 不可读
```

即：插件安装「看起来成功」，但 workflow/script_library/skill/rule 的目录是幻影，
内容不可达、`rmtree` 也删不掉（`ignore_errors=True` 静默）。修复后在建目录前拒绝。

### 3.5 B13 取证：市场 Skill id = `nul` → **谎报 409「已存在」**

```
validate_skill_content(包内 name: nul)                  → 返回 'nul'（接受，修复前）
Path('marketplace-skills/nul').exists()                 → True   ← 什么都没创建就恒真
install_skill_atomically(target=nul, 合法包)             → FileExistsError winerror=183
resolve_openable_skill('nul')                           → 409「本地存在同名但来源不同的 Skill」
```

关键点：**`exists()` 为真是 NUL 设备本身的语义，不是我方创建了什么**。后果是该名字被永久占用：
列表页显示「已存在」、安装报 409、而 `get_skill()` 永远读不到、也没有任何实体可删除/可卸载。
修复后 `_validate_slug`/`require_skill_id`/`validate_skill_content`/`skill_identity`/
`normalize_skill_id`/`resolve_openable_skill` 一律 400「…格式无效（为 Windows 保留设备名）」，
`install_skill_atomically` 另有纵深防御（在 `mkdir` 之前拦，零残留）。

### 3.6 零误伤核查（必须保留的证据）

逐一扫描真实数据，设备名命中数 **全为 0**：

- `config/plugin-sources.json`、`plugins.lock.json`（仅 `bishu-novel`、`xs2-novel-flywheel`）
- 21 个插件仓库的 `definition.json` 目录名、16 个资源目录名、全部 `resource_prefix` 值
- `config/skills_config.json` 6 个 id（`agent-definition-guide`、`automation-guide`、
  `prompt-template-guide`、`script-library-guide`、`skill-rule-authoring-guide`、`workflow-guide`）
- `data/skills`（`builtin`/`local`/`marketplace`）下全部目录
- 测试与配置里出现的任何 `process_id` / `extension_id` / `plugin_id` 字面量

合法名回归样本（新测试内固化）：`nul-2`、`null`、`nullable`、`console`、`com0`、`com10`、
`lpt0`、`auxiliary`、`bishu-novel`、`xs2-novel-flywheel` 全部放行。

## 4. Bug 报告与根因分析

### B11 — 插件 id / 资源前缀 / process_id 接受 Windows 保留设备名

- **严重度**：高（HTTP 500 而非 400；插件安装半途失败；幻影目录残留且不可删）
- **根因**：`_PLUGIN_ID_RE`、`_RESOURCE_PREFIX_RE`、`_PROCESS_ID_RE` 都是 `[a-z0-9._-]` 族，
  与小写设备名同型；R18 把设备名规则下沉到 `win_names.py` 后，**只接了 web 面的路径守卫**，
  插件系统这条链路没接。
- **为何必须平台无关**：插件 id 写进 `plugins.lock.json` 与 registry 清单，是跨平台共享键；
  `_parse_registry_plugin` 对任一非法 id 会使**整份清单失效**——若只在 nt 上拒绝，
  同一份 registry 在 Linux 与 Windows 上会得到不同的「清单是否有效」结论。

### B12 — 路径型资源 effective id 接受设备名

- **严重度**：中高（资源静默不可达；`rmtree(ignore_errors=True)` 使清理静默失效）
- **根因**：`effective_resource_id(prefix, local_id)` 的产物被 `resource_preparation` 直接当
  `copytree` 目标目录名，但该函数只做「拼接 + 去重」，从不校验文件系统命名约束。
- **边界（刻意）**：只拒 `workflow`/`script_library`/`skill`/`rule` 四类**路径型**资源；
  `agent`/`prompt`/`preset_phrase` 是 JSON 文档内的键，不落盘为路径，不在此拒绝面内。
  也**不**改 `_normalize_local_id`——它与查找逻辑共用，且 `_maybe_resolve` 只捕 `KeyError`，
  在归一化处抛错会改变既有查找语义。

### B13 — 市场 Skill id 接受设备名：永久占用命名空间 + 谎报 409

- **严重度**：中（用户看到「已存在」而实际不存在；该名字永久不可安装、不可卸载）
- **根因**：`SKILL_ID_PATTERN = ^[a-z0-9]+(?:-[a-z0-9]+)*$` 同型；且存在性判定依赖
  `Path.exists()`，而 `marketplace-skills/nul` 的 `exists()` 恒真。
- **特别说明**：`bundle.py` 早在 R17 就按**路径段**拒了设备名，但只覆盖**包内文件路径**，
  没覆盖**Skill id 自身**——本轮补上的是这个缺口。

## 5. 修复代码要点（补丁位置）

单一规则源新增平台无关谓词（`src/core/win_names.py`）：

```python
def unsafe_device_name(name: str) -> Optional[str]:
    """平台无关：仅判设备名，不判尾随点/空格（后者仍按平台门控）。"""
    return REASON_DEVICE_NAME if is_reserved_device_name(name) else None
```

| 文件 | 改动 |
|---|---|
| `src/plugin_system/models.py` | `validate_plugin_id`、`validate_resource_prefix`、`ProcessSpec.__post_init__` 追加设备名判定；**保留**原有 `invalid plugin id:` / `invalid resource prefix:` 前缀（消息兼容），只在尾部追加 `（原因）` |
| `src/extension_host/resource_ids.py` | 新增 `_PATH_BEARING_RESOURCE_KINDS`；`build_resource_id_plan` 对路径型资源在拼出 `effective_id` 后拒绝设备名（`ResourceIdError` ⊂ `ValueError` → 400） |
| `src/skill_marketplace/ownership.py` | 新增 `skill_id_is_safe`（谓词）与 `assert_safe_skill_id`（抛 `LocalSkillError`，默认 400）；`installation_state` 改用谓词；`resolve_openable_skill` 在 `exists()` **之前**拒绝 |
| `src/skill_marketplace/service.py` | `_validate_slug` 追加守卫（覆盖 install/update/community/draft 全部 ~15 个调用点） |
| `src/skill_marketplace/local_skills.py` | `require_skill_id`、`validate_skill_content`、`skill_identity` 追加守卫；`install_skill_atomically` 加纵深防御（`target.name`，在 `mkdir` 之前） |
| `src/skill_marketplace/drafts.py` | `normalize_skill_id` 追加守卫 |

**接口兼容性**：无签名变更；错误码沿用既有 `invalid_slug`/`invalid_name`/`invalid_plugin_id` 族，
仅消息尾部追加原因；`LocalSkillError` 默认 `status_code=400` 未动。

## 6. 回归测试结果

| 套件 | 结果 | 对账 |
|---|---|---|
| Low-IL 全量（服务在跑） | **1720 passed / 96 skipped / 0 failed**，112.6s | 1627 + 93 = 1720，skip 不变 |
| High-IL 全量（权威） | **1805 passed / 11 skipped / 0 failed**，133.5s | 1697 + 93 + e2e 15(skip→pass) = 1805 |
| 邻域定向 | 704 passed / 83 skipped / 0 failed | plugin/extension/resource/marketplace/manifest/memory/settings |
| 前端 | lint 0 problems；test 6 pass / 0 fail；build 6.30s | 本轮未改前端，确认无连带影响 |

skip 的 11 项（High-IL）全为 macOS 签名/打包与 POSIX fcntl/进程组断言，属环境类。

## 7. 优化清单（本轮）

- **O1（已做）`.gitignore` 漏掉 mkstemp 文件**：R19 只加了 `tmp*/`，它**只匹配目录**；
  实测 `tempfile.mkstemp()` 在 `%TEMP%` ACL 受限时回落到 CWD，产出的是**文件** `tmpXXXXXXXX`，
  因此照样污染工作区。补 `/tmp*`（仓库根锚定，已确认无任何被跟踪文件以 `tmp` 开头）。
- **O2（记录，未修）`determinflow-executor-*` 残留 52 个**：`executor_supervisor.py:211`
  用 `mkdtemp(prefix=...)` 且无 `dir=`，同样回落到 CWD；清理只在 232-234 与 423-428，
  进程被硬杀时跳过。**建议**改为显式 `dir=` 指向工作区内隔离目录（PROJECT_INFO 注意事项 8 的
  既有结论），属行为变更，留给下一轮。

## 8. 风险与遗留问题

1. **子代理审计结论全部证伪**（重要教训）：一次并行审计返回了
   `src/skill_marketplace/install.py`、`resolver.py`、`resolve_target_dir`、
   `tests/test_agent_persistent_session_runtime.py`、`data/projects/NUL` 等**不存在**的引用，
   并声称「小说导出 zip 解包到 NUL」。逐条验伪：这些文件均不存在；全 `src/` 内
   **无任何 `extractall`**（只有 `registry_release.py:208` 写 zip、`registry.py:655` 读 zip）。
   → 结论：**审计类结论必须逐条落到可执行证据上，不能直接采信。**
2. **POSIX 真跑未验证**：本机无 WSL/Docker，平台无关判定只有单元级（monkeypatch `_on_windows`）
   证据，没有真实 Linux 运行记录。
3. **B13 的卸载面未单独验证**：修复后设备名无法进入命名空间，故「卸载幻影」路径不可达；
   但若历史数据里已存在幻影目录，仍无自动清理逻辑（需手工 `\\?\` 前缀删除）。
4. **未推送**：xs2 30 笔 + `DeterminFlow-Plugins` 5 笔；推送需要用户凭据（GCM 弹窗），
   本轮**未执行**（R19 P0 亦未完成，属用户侧动作）。
5. 插件仓库侧若已有设备名 id，本轮修复会让其清单整体失效——零误伤扫描显示当前不存在此类 id。

## 9. 下一轮迭代计划（Round 21）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P0（用户） | 推送两仓库（需凭据） | 低 | 5min |
| P1 | O2：executor 临时目录改显式 `dir=`，并清理 52 个残留 | 中（涉及子进程工作目录语义） | 1-2h |
| P1 | B13 纵深：为「历史幻影目录」提供一次性诊断/清理命令（只读诊断优先） | 中 | 1h |
| P2 | 补 `install_marketplace_skill` 端到端测试（当前该 HTTP 面缺真实包用例） | 低 | 1h |
| P2 | `updates.py:166` 的 `exists()` 语义统一（现由 `_validate_slug` 上游覆盖，但无测试锚定） | 低 | 30min |
| P3 | POSIX 真跑（需容器/WSL 环境） | 低 | 环境依赖 |
| P3 | 前端 HumanwareScoreCard 组件（R19 遗留） | 低 | 2h |

## 10. 命令记录（本轮）

```powershell
# 基线核实
cd "F:\DeterminFlow x2\xs2"; git --no-pager log --oneline -3   # df21c5d
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider   # 1627/96/0

# 红灯取证（一次性脚本，跑完即删）
.\.venv\Scripts\python.exe -X utf8 data\_r20_probe4.py   # B13: exists() 恒真 + WinError 183

# 绿灯验证（修复后同脚本复跑）
.\.venv\Scripts\python.exe -X utf8 data\_r20_probe4.py
#   validate_skill_content → LocalSkillError「…（为 Windows 保留设备名）」
#   install_skill_atomically → LocalSkillError，且父目录未被创建（零残留）
#   demo-skill 对照组仍安装成功、可读回

# 全量回归（Low-IL）
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider   # 1720/96/0

# 全量回归（High-IL 权威）
$sp = "$PWD\.venv\Lib\site-packages"
$env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
C:\Windows\py.exe -X utf8 -m pytest -q -p no:cacheprovider            # 1805/11/0

# 前端三连
cd web; npm.cmd run lint; npm.cmd test; npm.cmd run build
```
