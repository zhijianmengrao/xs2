# DeterminFlow (xs2) 交接报告 — Round 19（v3.3 上线验收 + 名字拼接点全面审计 → B10 附件静默丢失修复 + CI Windows 权威基线）

> 生成时间：2026-10-24
> 项目路径：`F:/DeterminFlow x2/xs2`（主仓库）；`F:/DeterminFlow x2/DeterminFlow-Plugins`（插件仓库，本轮**无代码改动**）
> 分支：main（两仓库各自）
> 上一轮：[HANDOVER_ROUND18.md](./HANDOVER_ROUND18.md)
> 接口契约：[humanware-helper-contract.md](./humanware-helper-contract.md)（维持 **v3.3**，本轮无契约面改动——B10 属会话附件 API，不在该契约范围内）
> 文档编码：UTF-8

## 1. 结论摘要

| 结论 | 依据 |
|---|---|
| **R18 P0-1 完成**：重启 8021 → v3.3（core 守卫 + 400 映射）上线；线上实测 `workflow_id=中文` → **400**（原 500）、`workspace=…/books/NUL` → **400**（原 200） | §3.1 探针 |
| **e2e 达到 R18 验收口径：15 passed / 0 skipped**（F6/F7 由诚实 skip 转 PASS） | `pytest tests/test_humanware_e2e.py` 实跑两次（重启后 + 终态） |
| **R18 P1 名字拼接点全面审计完成**：6 个面逐一给出「已守卫 / 修复 / 豁免理由」结论清单 | §3.2 审计表 |
| **新发现并修复 B10**（附件上传 `filename="NUL"` → **200 成功但内容静默丢弃**），红灯固化后修复，B4 同族 | §3.3、§4 |
| **R18 P1 CI 化完成（文件层）**：`ci.yml` 新增 `windows-backend` job（windows-latest + Python 3.14 + dev.lock），基线政策写入 PROJECT_INFO；**首次运行记录待推送后产生** | §7 O1 |
| 全量回归 **0 失败**（两种 IL 各一次）：Low-IL **1612 passed / 111 skipped**；High-IL **1697 passed / 26 skipped**；计数与 R18 逐项对账吻合 | §6 |
| 前端无改动：lint 0 problems、**406 测试全过（8 套件完整求和）**、build ✓ 6.14s | §6 |
| 两仓库仍未推送（xs2 29→30 笔 / 插件 5 笔），推送仍需用户手动完成（无缓存凭据） | §8 R19-1 |
| 本轮无并发写入者干扰（R17-10/R18-6 复查：`git status` 全程仅本轮 5 文件） | §8 R19-5 |

## 2. 测试计划（本轮）

- **范围**：执行 R18 §9 计划的 P0-1（服务重启验收）与 P1 两项（名字拼接点审计、High-IL 基线 CI 化）；P0 推送与 P0 单一写入流属用户/协作事项，本轮核实状态并记录。
- **类型**：功能（附件上传正常路径不回归）、边界（设备名/尾随点/超长截断产物）、异常（400 语义）、安全（文件名 → 文件系统名字面）、回归（双 IL 全套 + 前端 + 服务侧 e2e + 插件状态抽查）、环境（v3.3 上线指纹）。
- **环境**：Windows 本机；venv Python 3.14.8（Low-IL）与 `C:\Windows\py.exe` + venv site-packages（High-IL）；服务 `http://127.0.0.1:8021`（本轮重启 2 次：11:46 上线 v3.3、终态重启）。
- **通过标准**：e2e 15 passed / 0 skipped；双 IL 全量 0 failed；附件新旧用例全绿；前端三件套全过。
- **运行命令**：
  ```
  cd "F:\DeterminFlow x2\xs2"
  .\.venv\Scripts\python.exe -m pytest tests/test_workspace_attachments.py -v   # 4 → 6
  .\.venv\Scripts\python.exe -m pytest tests/test_humanware_e2e.py -v          # 需服务运行
  .\.venv\Scripts\python.exe -m pytest -q                                      # 全量 Low-IL（停服跑）
  # High-IL 权威基线
  sp="$(cygpath -w "$PWD/.venv/Lib/site-packages")"
  export PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
  C:/Windows/py.exe -m pytest -q
  cd web && npm.cmd run lint && npm.cmd test && npm.cmd run build
  ```

## 3. 测试用例与执行结果

### 3.1 v3.3 上线验收（真实 8021，重启前后对照）

| 场景 | 重启前（v3.2） | 重启后（v3.3） | 判定 |
|---|---|---|---|
| `GET /api/workflows/workspace-files?workflow_id=中文书` | **500** | **400** | B6 上线 ✓ |
| `GET /api/workflows/workspace-files?workspace=data/workspaces/books/NUL` | 200（旧探针记录；本轮单参请求 422 属端点必填参校验） | **400** | B7 上线 ✓ |
| `pytest tests/test_humanware_e2e.py` | 13 passed / 2 skipped（F6/F7 skip） | **15 passed / 0 skipped** | R18 验收口径达成 ✓ |
| `/api/plugins` | — | 双插件 `running`、`restart_required=False` | 服务健康 ✓ |

### 3.2 名字拼接点审计清单（R18 P1 验收物）

| # | 表面 | 用户可控名字 | 现状 | 结论 |
|---|---|---|---|---|
| 1 | `novel_routes` export/download `filename` | 是（仅进 `Content-Disposition`） | `re.sub('[<>:"/\\|?*\x00-\x1f]')` + 160 截断；实际文件路径固定 `export/manuscript.md`（经 `safe_target`） | **豁免**：不进文件系统，消毒充分 |
| 2 | `novel_reference_choices.py` / reference-candidates | 否（fingerprint/choice_id 由内容哈希生成） | 纯数据变换，0 路径操作 | **豁免**：无名字→路径 |
| 3 | `mention_routes`（@提及资源发现） | `q` 查询串 | 只读；`q` 仅 `casefold().split()` 过滤；模块 0 处 `Path(/open/mkdir` | **豁免**：只读检索，无落盘 |
| 4 | 插件 `runtime-resources/<extension_id>` | 间接（插件 manifest id） | `_PLUGIN_ID_RE = ^[a-z0-9]+(-[a-z0-9]+)*$`；小写 `nul` 理论可过 → 幻影目录 | **豁免（低风险）**：插件安装是同权限信任决策（PROJECT_INFO 已警示），且资源准备失败会以 extension degraded 大声失败，不静默；真要封堵应改 `_PLUGIN_ID_RE` 校验（影响插件接受规则），留 R20 决策 |
| 5 | 写法库 `library/publish`、`library/delete` | `payload.name` → `safe_library_id` → 目录名 | `library_path` 内已有 `unsafe_windows_component` 守卫（R17/R18 落地），删除侧另有 `[a-z0-9_-]{1,80}` 白名单 | **已守卫**（既有用例覆盖） |
| 6 | **会话附件上传 `_safe_attachment_name`** | 是（filename → 附件目录内创建文件） | 控制字符/`.`/`..`/长度已处理，**但无设备名/尾随点判定** | **B10 缺陷 → 本轮修复**（§3.3） |

**审计方法**：逐文件读源码（export 端点、attachment 全文、mention 全文、library publish/delete、extension_host manager）+ 关键行为实证（见 §3.3 探针），不凭推测下结论。

### 3.3 B10 取证与用例（`tests/test_workspace_attachments.py` 4 → 6）

**实证探针（修复前，直接调用 `_reserve_attachment_path`）**：

| 输入 filename | 行为 | 判定 |
|---|---|---|
| `NUL` | `os.open(O_CREAT\|O_EXCL)` 打开**设备本身**成功（0.1ms）；`exists()=True`、`is_file()=False`、**父目录列表无此文件**；后续 `aiofiles.open(...,"wb")` 写入全部进黑洞 | **静默数据丢失**（上传 200 + `{"name":"NUL"}`，内容无处可寻） |
| `NUL.txt` / `CON.txt` | 本机（Win11 + Py3.14）创建**真实文件**，可正常读写 | 本机无害；老版本 Windows/其他工具仍按设备解析 → 按规则源统一拒绝 |
| `notes.` | 落盘名被文件系统剥成 `notes`（目录列表为 `notes`），上报名 `notes.` | 上报名 ≠ 落盘名（Windows 别名可读回，POSIX 复制后断裂） |
| 裸 `CON/PRN/AUX/COM1` 作**文件** | 本机均创建真实文件（`is_file()=True`） | 与 R18 注意事项 12（目录语义）互补：仅 `NUL` 幻影，但跨工具一致性仍拒 |

**新增用例（红灯 → 绿灯）**：

| 编号 | 场景 | 预期 | 实际（修复前） | 状态 |
|---|---|---|---|---|
| TC-R19-01 | `_safe_attachment_name` 拒 `NUL`/`nul`/`NUL.txt`/`con.md`/`COM1`/`notes.`/`"report. "` | ValueError | 原样返回 | ✅（修后） |
| TC-R19-02 | HTTP 上传 `filename=NUL` | **400** + 附件目录零残留 | **200**（内容丢失） | ✅（修后） |

> 红灯证据：首跑 `2 failed`（含 200≠400 的 HTTP 级实拍）。两条均 `skipif(os.name != "nt")`，POSIX 行为不变（`unsafe_windows_component` 恒放行）。

### 3.4 既有回归抽测

| 项 | 结果 |
|---|---|
| `pytest tests/test_workspace_attachments.py`（修后） | **6 passed**（4 旧 + 2 新；旧用例含目录剥离、不覆盖重名、404 会话） |
| `pytest tests/test_humanware_e2e.py`（终态，服务运行中） | **15 passed / 0 skipped**（1.11s） |

## 4. Bug 报告与根因分析

### B10 — 附件上传以设备名为文件名：200「成功」+ 内容静默丢弃
- **现象**：`POST /api/workspace/{session_id}/attachments?filename=NUL` → **200** `{"name":"NUL",...}`，但附件目录中无任何文件，正文内容写入 NUL 设备被丢弃（§3.3 探针 + HTTP 级红灯双证）。
- **根因**：`_safe_attachment_name` 只处理目录剥离、控制字符、`.`/`..` 与字节长度，未接 R17/R18 建立的 Windows 名称规则源；`_reserve_attachment_path` 的 `os.open(O_CREAT|O_EXCL)` 对设备名**成功打开设备**（不抛 FileExistsError），O_EXCL 的防冲突语义同时被架空——重复上传 `NUL` 每次都"成功"。`notes.` 类尾随点则是上报名与落盘名剥离错位（Windows 可别名读回、POSIX 断裂）。
- **影响**：用户拖入名为 `NUL` 的文件（或恶意构造）会得到成功响应而丢失内容——与 R17 B4（novel-console 写 `references/NUL` 假成功）同族，但入口不同（会话附件 vs 章节文本）。
- **修复**：`_safe_attachment_name` 在**截断之后**（截断产物同样受检）调用 `src.core.win_names.unsafe_windows_component`，命中即 `ValueError("文件名无效（<拒因>）")` → 端点既有 `except ValueError` → **400**。POSIX 恒放行（平台门控在谓词内部）。
- **取舍**：
  1. *改为静默改名（`NUL`→`NUL_`）*：用户找不到自己上传的文件名，且与 novel/humanware 面的拒绝语义不一致 → 否。
  2. *在 `_reserve_attachment_path` 里拒*：太晚——设备名在 `os.open` 已经"成功"，且该函数职责是防覆盖不是命名合法性 → 否。
  3. *命名层统一拒（选定）*：与全仓单一规则源一致，HTTP 语义 400（客户端输入错误），改动最小（一处 import + 四行判定）。
- **风险**：极低。仅新增拒绝分支；正常名（含中文、`COM0`、`nultxt`、`console-NUL`）不受影响（`win_names` 既有放行矩阵守卫）；POSIX 行为零变化。

### 审计豁免记录（非缺陷，验收要求"每个危险点有测试或明确豁免理由"）
见 §3.2 表——1/2/3/5 有既有守卫或不涉及文件系统；4（runtime-resources）记录豁免理由与后续可选项。

### P0 事项状态（R18 遗留）
- **推送（R18-1）**：两仓库 `GCM_INTERACTIVE=never` 实测均 `Cannot prompt`——仍无缓存凭据，需用户手动 `git push`（弹 GCM 窗）。xs2 未推送 29 → 本轮提交后 30 笔。
- **单一写入流（R18-6）**：本轮 11:45–12:10 期间 `git status` 全程仅本轮 5 个文件，无第三主体痕迹；仍建议约定显式路径 add（本轮继续遵守）。

## 5. 修复代码要点（补丁位置）

| 文件 | 位置 | 变更 |
|---|---|---|
| `src/web/attachment_routes.py` | imports | 新增 `from src.core.win_names import unsafe_windows_component` |
| `src/web/attachment_routes.py` | `_safe_attachment_name` | 截断逻辑重构为单出口 `candidate`；**截断后**追加 `unsafe_windows_component` → `ValueError`（B10）；注释写明两类实测危害 |
| `tests/test_workspace_attachments.py` | 文件尾 | +2 条（TC-R19-01/02，nt 门控）；imports 补 `os`/`pytest` |
| `.github/workflows/ci.yml` | `backend` job 后 | 新增 `windows-backend` job（windows-latest、Python 3.14、dev.lock、`pytest -q`），注释说明与本机 High-IL 的对应关系 |
| `docs/PROJECT_INFO.md` | 测试环境 | 新增「基线政策（R19 起）」条目（Low-IL 快速跑 / High-IL + CI windows-backend 权威） |
| `.gitignore` | 临时产物段 | 补 `tmp*/`（PROJECT_INFO 注意事项 8 的遗留建议；本轮 pytest 又产生 2 个实例，已清） |

> 附件 API 不在 humanware-helper 契约范围内，契约文档无需升版（v3.3 维持）。

## 6. 回归测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| 附件（新旧） | `pytest tests/test_workspace_attachments.py` | **6 passed**（4 → 6） |
| e2e（服务运行中，两次） | `pytest tests/test_humanware_e2e.py` | **15 passed / 0 skipped**（1.05s / 1.11s） |
| **全量 Low-IL**（停服） | `.\.venv\Scripts\python.exe -m pytest -q` | **1612 passed / 111 skipped / 0 failed**（101.81s） |
| **全量 High-IL**（停服，权威） | `py.exe -m pytest -q`（PYTHONPATH 挂 venv） | **1697 passed / 26 skipped / 0 failed**（118.96s） |
| 前端（无改动） | lint / test / build | 0 problems；**406 pass / 0 fail**（8 套件 48+17+135+81+100+1+18+6 完整求和）；✓ built 6.14s |
| 服务终态 | `/api/plugins` | 双插件 `running`、`restart_required=False` |
| 工作树 | `git status` | 仅本轮 5 文件；pytest 临时目录已清并补 gitignore |

> **计数对账（与 R18 同口径）**：
> Low-IL：R18 1623/98（服务在跑，e2e 13 passed/2 skipped）→ R19 1612/111（停服，e2e 整模块 15 skipped）：
> passed −13（e2e）+2（附件新用例）= −11 ✓；skipped +13 ✓；总数 1721→1723（+2）✓。
> High-IL：R18 1708/13 → R19 1697/26：passed −13+2 = −11 ✓；skipped 13−2(F6/F7 并入整模块)+15(模块)=26 ✓。
> 两轮总数一致（1723），差异全部来自「服务是否运行」与新增 2 条，无失踪用例。

## 7. 优化清单（本轮）

| 编号 | 问题 | 方案 | 预期收益 | 风险 | 优先级 | 状态 |
|---|---|---|---|---|---|---|
| O1 | High-IL 权威基线只有本机手工命令，CI 只有 ubuntu | `ci.yml` 增 `windows-backend`（windows-latest + Py3.14 + dev.lock） | Windows 专属用例（win_names/幻影/设备名/msys git 传输）在 CI 真实执行；push 即验证 | 首跑未发生（推送受阻）；Python 3.14 轮子在 CI 的解析是首个验证点 | 高 | ✅（文件层） |
| O2 | pytest 临时目录反复出现在仓库根（注意事项 8 遗留） | `.gitignore` 补 `tmp*/` 并清理现存 2 个 | 状态噪声消除 | 无 | 低 | ✅ |
| O3 | 基线口径散落各轮交接文档 | PROJECT_INFO 写明基线政策（快速跑 vs 权威） | 后续轮次不再纠结用哪个数字 | 无 | 中 | ✅ |

## 8. 风险与遗留问题

| 编号 | 问题 | 说明 | 风险 |
|---|---|---|---|
| R19-1 | 两仓库未推送（xs2 30 笔 / 插件 5 笔） | 无缓存凭据；`GCM_INTERACTIVE=never` 实测 `Cannot prompt`。需用户手动推送；推送后 CI `windows-backend` 首跑记录才能产生 | 中（协作/备份） |
| R19-2 | CI 新 job 未实际运行 | 无法在本地验证 GitHub runner 环境（Python 3.14 轮子、dev.lock 解析）；若首跑失败属环境配置问题，非用例缺陷 | 低（待推送后首跑） |
| R19-3 | runtime-resources 设备名 id 豁免（审计面 4） | 小写 `nul` 理论可作插件 id → 幻影目录（大声失败不静默）；封堵需改 `_PLUGIN_ID_RE` 接受规则，建议 R20 决策 | 低 |
| R19-4 | `learning/candidates.json` 未接入 analyze-voice（R15-3…R18-8 延续） | 产品决策项 | 低 |
| R19-5 | 并发写入者（R17-10/R18-6 延续） | 本轮无干扰痕迹；继续显式路径 add | 低（已缓解） |
| R19-6 | 前端 `HumanwareScoreCard` 无调用方；`setup_plugins.py` 假安装（延续） | UI 接线/决策项 | 低 |
| R19-7 | 附件尾随点在 POSIX 是合法名 | 本轮修复按平台门控放行 POSIX（行为不变）；若产品要求跨平台同名同义，需产品决策 | 低 |

## 9. 下一轮迭代计划（Round 20）

| 优先级 | 任务 | 预估工作量 | 验收标准 |
|---|---|---|---|
| **P0** | 用户手动推送两仓库（xs2 30 笔 / 插件 5 笔）并回看 CI `windows-backend` 首跑；若失败按日志修 job 环境 | 0.3h（用户 + 修整） | 两仓库 `git log origin/main..main` 为空；CI windows-backend 绿或已修复 |
| P1 | R19-3 决策：`_PLUGIN_ID_RE` 是否追加设备名拒绝（含小写变体）；若做，补 manifest 校验用例 + marketplace 等价性对照 | 1h | 二选一落地；若拒绝，`nul` id 插件安装报 400 且有用例 |
| P1 | 附件上传面补 e2e（可选）：起服务后经 HTTP 上传 `NUL` 断言 400（当前覆盖在进程内 TestClient 层） | 0.5h | 用例进套件或记录豁免（TestClient 已覆盖则豁免成立） |
| P2 | 决策 R19-4（candidates 接入 analyze-voice，契约 §4 同步） | 2h（含确认） | 二选一落地 |
| P2 | R18-11 延续：非规范名策略统一（web 拒尾随点 + core 剥点）是否收敛为单一入口，写进 `win_names` 模块文档 | 1h | 决策 + 文档 + 对照用例 |
| P3 | 前端接线 `HumanwareScoreCard`；`setup_plugins.py` 决策（延续） | 2h / 1h | 组件测试 + lint/test/build 全绿 / 决策落地 |
| P3 | POSIX 真实运行验证（win_names 门控另一侧；R18 §9 P3 延续，本轮仍未做） | 0.5h | 一次非 Windows 全量跑记录 |

## 10. 命令记录（本轮）

```
# 基线核实（11:45）
git log：HEAD c71a5ac（R18 更正提交）；29 笔未推送；8021 pid 78636 = v3.2（workflow_id=中文 → 500 实证）

# P0-1 服务重启 + 验收
taskkill /T /F 78636 进程树 → port free → run.py（后台）
workflow_id=中文书 → 400；workspace=…/books/NUL → 400（v3.3 上线指纹）
pytest tests/test_humanware_e2e.py → 15 passed / 0 skipped（R18 验收口径）

# P0-2 推送尝试（两仓库）
GCM_INTERACTIVE=never git push → Cannot prompt（无凭据，转用户操作）

# P1-1 审计（读码 + 实证）
attachment 探针：NUL → os.open 打开设备成功/内容黑洞/目录无此项；NUL.txt、CON.txt → 真实文件；notes. → 落盘名剥离
裸 CON/PRN/AUX/COM1 作文件 → 真实文件（补全 R18 目录语义矩阵）
mentions：q 仅 casefold 过滤、0 路径操作；library：library_path 已有守卫；
export：仅响应头且消毒充分；runtime-resources：_PLUGIN_ID_RE 约束 + 信任决策豁免

# B10 红灯 → 修复 → 绿灯
pytest tests/test_workspace_attachments.py → 2 failed（含 HTTP 200≠400）
修 _safe_attachment_name（win_names 接入 + 截断后校验）→ 6 passed

# P1-2 CI + 文档
ci.yml 增 windows-backend（Py3.14）；PROJECT_INFO 基线政策；.gitignore 补 tmp*/

# 全量回归（停服）
Low-IL ：pytest -q → 1612 passed / 111 skipped / 0 failed
High-IL：py.exe -m pytest -q（PYTHONPATH=venv site-packages）→ 1697 passed / 26 skipped / 0 failed
前端   ：lint 0 problems / test 406 pass 0 fail（8 套件求和）/ build ✓ 6.14s

# 终态
重启 8021 → e2e 15 passed / 0 skipped；/api/plugins 双插件 running
清理 tmp*/ 两个实例；git status 仅本轮 5 文件
```
