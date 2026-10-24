# DeterminFlow（yuyang0702/xs2）项目信息

## 项目名称
DeterminFlow（`yuyang0702/xs2` 二次开发版）——面向生产的确定性 AI 工作流运行框架。把 LLM、脚本、API、数据库操作和人工审批组织成有版本、可校验、可重试、可恢复、可审计的工作流。

- 仓库：https://github.com/zhijianmengrao/xs2（**origin**，2026-10-24 迁移；原 `yuyang0702/xs2` 保留为 upstream 远程，真正上游为 `alikon-art/DeterminFlow`）
- 本地安装路径：`F:\DeterminFlow x2\xs2`

## 项目状态（2026-10-24 完结）

- **迭代完结于 Round 22（完结轮，纯终验+文档定稿）**（R15–R22 共 8 轮「审计→修复→
  回归→交接」循环，逐轮记录见 docs/HANDOVER_ROUND15..22.md）；全部提交已推送
  （`origin/main..main` = 0）。
- **交付摘要**：修复 13 个编号缺陷（B1–B13，涵盖 HTTP 500 逃逸、幻影目录数据损坏、
  内容静默丢失、409 谎报占用等类别）；「名字面」安全治理全线闭环（路径面 +
  标识符面，单一规则源 `src/core/win_names.py` + 历史数据只读体检
  `scripts/audit_storage_names.py`）；executor 临时目录治理（钉位
  `data/system/executor-runtimes`，仓库根残留清零）；总用例 1597（R17 口径）→
  **1828**（R21：High-IL **1817 passed / 11 skipped / 0 failed** 权威、Low-IL
  1732/96/0 快速）；CI 四 job 全绿（backend / windows-backend / frontend /
  container-config）。
- **有意遗留**（详见 HANDOVER_ROUND21 §9）：POSIX 真跑验证（需容器/WSL 环境）、
  HumanwareScoreCard 前端组件（纯新增 UI，无缺陷压力）、`start()` 失败时
  supervisor 状态悬挂（无实际泄漏）。
- **上游桌面发布管线（2026-10-24 已转绿）**：`.github/workflows/desktop-windows.yml`
  为上游继承的 Tauri/NSIS 发布流水线（发布清单指向 alikon-art 上游 release 与
  downloads.determinflow.com）。曾因缺 `TAURI_SIGNING_PRIVATE_KEY` 密钥在本 fork
  预期红；完结后已补齐：本地 minisign 密钥对（空密码，密钥文件已 gitignore）+
  GitHub secret 配置 + `tauri.conf.json` 的 updater `pubkey` 替换为本 fork 公钥
  （`25282d4`：core/full 两条 NSIS job **success**，管线史上首绿；macOS/release
  job 按 tag-only 规则正确跳过）。注意：`endpoints` 仍指向上游 latest.json，
  在自有分发地址落地前自动更新呈**安全失效态**（新公钥验上游签名不过即拒绝）；
  若要启用自动更新需替换 endpoints 为自己的 latest.json 地址。
- **维护入口**：接口契约 docs/humanware-helper-contract.md（**v3.4 完结版**，
  含 §6.1 常驻回归基线）；数据巡检 `python scripts/audit_storage_names.py`
  （exit 0 clean / 1 有发现）；回归命令与权威基线定义见下文「测试环境」。

## 技术栈与运行方式

| 项目 | 内容 |
|---|---|
| 后端语言 | Python ≥3.11（要求）；**本机 venv 实际为 Python 3.14.8**（`.venv\pyvenv.cfg` 的 `home = C:\Program Files\Python314`；早期文档误记 3.12.14） |
| 后端框架 | FastAPI 0.139.0 + uvicorn 0.50.2、LangGraph 1.2.8、MCP 1.28.1、LangChain、gunicorn |
| 前端 | React 18 + TypeScript + Vite 7.3.6 + Tailwind CSS + React Flow（node ≥22.12） |
| 核心依赖 | openai 2.44.0、fastapi、uvicorn[standard]、langgraph、langchain-core/openai/anthropic、mcp、httpx、cryptography、websockets、croniter、aiofiles |
| 数据 | 文件型（`data/` 工作区、JSON/SQLite 检查点），无独立数据库服务 |
| 启动命令（Windows） | `git clone` → `python -m venv .venv` → `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` → 复制 `.env`、`config\models_config.json` → `.\.venv\Scripts\python.exe run.py` |
| 前端构建 | `cd web && npm install && npm run build`（产出 `web/dist/`；`run.py` 启动时自动检测构建） |
| 环境变量 | `.env`：`WEB_HOST`、`WEB_PORT`（默认 8020）、`DEEPSEEK_API_KEY` 等，统一 `DETERMINFLOW_*` 前缀 |
| 模型配置 | `config/models_config.json`（供应商需在设置页或配置填写） |
| Docker 方式 | `docker compose up --build` |
| 启动后访问 | Web UI `http://localhost:8020` · API `/docs` · 插件 `/api/plugins` |

## 仓库结构

```
xs2/
├── run.py                  # 后端入口，负责前端构建/插件检查/启动 uvicorn
├── pyproject.toml          # 项目元数据与依赖（Python ≥3.11）
├── requirements.txt        # 运行时依赖锁定
├── requirements.lock / requirements-dev.lock
├── setup_plugins.py        # 自动检测并安装必需插件（xs2-novel-flywheel）
├── .env.example            # 环境变量模板
├── docker-compose.yml / Dockerfile
├── src/                    # Python 后端（web_server、agent、core、mcp、tools、skills、rules、prompts）
├── web/                    # React 前端（src/、dist/、vite.config.ts、package.json）
├── config/                 # 运行配置（models_config、extensions、plugin-sources、agents_config）
├── data/                   # 运行数据（workspaces、plugins checkouts、检查点）
├── scripts/                # 环境检查、启动辅助脚本
├── desktop/                # 桌面客户端（Tauri）
├── tests/ · docs/ · examples/
└── 启动脚本：start_determinflow.bat / start_determinflow_v2.ps1 / rebuild_now.ps1
```

- `config/extensions.json` — 启用 `xs2-novel-flywheel` 插件（`strict_startup: false`）
- `config/plugin-sources.json` — 官方/社区源 + 自定义本地源 `file:///F:/DeterminFlow%20x2/DeterminFlow-Plugins`（早期文档误记 `file:///C:/xs2/DeterminFlow-Plugins`，该路径不存在）及 `github.com/yuyang0702/xs2-plugins.git`

## 约束条件

- Python ≥3.11；Node.js ≥22.12（`web/package.json` 的 `engines`）
- 默认端口 8020；本机 8020 已被 `F:\DeterminFlow` 上既有 DeterminFlow 实例占用，新实例运行在 **8021**（`.env` 设 `WEB_PORT=8021`）
- 许可证 **GNU AGPL-3.0**
- 模型/凭据未配置时仅 Core 服务可启动；Agent 调用前需在 `models_config.json` 或设置页配置
- 第三方/社区插件与主进程同权限运行、无沙箱，安装前需确认风险
- 默认 4 个本机 Workflow Executor；单进程回退 `DETERMINFLOW_WORKFLOW_EXECUTOR_MODE=inline` + `DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT=1`
- 并发限制：`UVICORN_LIMIT_CONCURRENCY` 默认 200、`UVICORN_BACKLOG` 默认 2048

## 测试环境

- 本地沙箱/开发环境（Windows 本机 `F:\DeterminFlow x2\xs2`），非生产
- 已安装完成并可访问：Web UI `http://localhost:8021`、API `/docs`、插件 `/api/plugins`
- **禁止直接操作生产环境**；`F:\DeterminFlow`（端口 8020）为既有运行环境，未改动其数据
- 验证方式：`python -m pytest -q`；`cd web && npm run lint && npm run test:* && npm run build`；`docker compose -f docker-compose.yml config -q`
- 2026-10-22 最终本地回归（`.\.venv\Scripts\python.exe -m pytest -q`）：**1514 passed / 0 failed / 36 skipped**；所有剩余 skip 均为平台环境限制（Windows symlink 特权 / macOS 签名 / POSIX fcntl），不再有失败项；前端 `npm run lint` 0 errors、`npm test` 全过、`npm run build` 成功。
- 2026-10-24 R17 双基线（同一提交，Windows）：Low-IL（venv）`pytest -q` → **1501 passed / 96 skipped / 0 failed**；High-IL（`C:\Windows\py.exe` + venv site-packages 经 `PYTHONPATH`，见平台注意事项 9）→ **1586 passed / 11 skipped / 0 failed**。High-IL 是权威基线（symlink 与 msys git 用例都真实执行）；Low-IL 下这些用例转为 skip。
- 2026-10-24 R18 双基线（core 层 Windows 名称守卫 + 错误映射 + 测试健壮性修复）：Low-IL → **1623 passed / 98 skipped / 0 failed**；High-IL → **1708 passed / 13 skipped / 0 failed**（13 = 11 平台 skip + 2 条 `test_humanware_e2e` F6/F7，服务未重启加载 R18 代码时诚实 skip）。净增 **124** 条用例（core 名称守卫 20 + marketplace 规则等价性 99 + web 端到端 3 + 服务侧 e2e F6/F7 2；其中 F6/F7 在 Low/High 两种 IL 下各计 1 条 skip，故 passed 增 122、skip 增 2）。总用例数 R17 1597 → R18 1721。
  > R18 B9 已让 `test_workflow_executor_protocol` / `test_workflow_recovery_timeout` 与系统 locale
  > 解耦（子进程 env 内显式 `PYTHONIOENCODING=utf-8` + 父进程按 UTF-8 解码），因此下面两条命令
  > **无论会话是否预设 `PYTHONIOENCODING` 都会通过**（实测四种组合各 39 passed）。
- **基线政策（R19 起）**：本地 Low-IL（`.venv`）仅作**快速跑**；**权威基线**为 ① 本机 High-IL 命令
  （见平台注意事项 9）与 ② CI `windows-backend` job（`.github/workflows/ci.yml`：windows-latest +
  Python 3.14 + `requirements-dev.lock`，与本机 High-IL 平台一致，Windows 专属用例在 CI 真实执行）。
  ubuntu `backend` job 保留作跨平台快速信号。
- 2026-10-24 R20 双基线（插件 id / 资源 id / 市场 Skill id 设备名拒绝）：Low-IL → **1720 passed / 96 skipped / 0 failed**（服务在跑，故 e2e 15 条执行而非 skip）；High-IL → **1805 passed / 11 skipped / 0 failed**。净增 **93** 条用例（`test_plugin_name_guard.py` 60 + `test_marketplace_skill_id_guard.py` 33）。对账：Low-IL 1627+93=1720；High-IL 1697+93+15(e2e skip→pass)=1805。
- 2026-10-24 R21 双基线（executor runtime 目录钉位 + 存储名只读审计 + 市场安装真实包 e2e + update exists() 语义锚定）：Low-IL → **1732 passed / 96 skipped / 0 failed**；High-IL → **1817 passed / 11 skipped / 0 failed**。净增 **12** 条用例（`test_storage_name_audit.py` 5 + `test_executor_runtime_dir.py` 2 + `test_marketplace_install_e2e.py` 3 + update 锚定 2）。对账：Low-IL 1720+12=1732；High-IL 1805+12=1817。
- **2026-10-24 CI 首绿（仓库已迁移：origin → `zhijianmengrao/xs2` 与 `zhijianmengrao/xs2-plugins`，原
  `yuyang0702/*` 保留为 upstream 远程）**：commit `e925dda`，run 40088073223，四 job 全绿（backend /
  windows-backend / frontend / container-config），CI 全量 **1790 passed / 26 skipped**。首跑过程修复三个
  CI 环境缺陷：① backend/windows 缺兄弟目录 `../DeterminFlow-Plugins`（7 个测试文件按 `parents[2]` 读取
  本地开发布局，现 CI 显式 depth-1 克隆插件仓库）；② workflow 步骤名含冒号+空格致 YAML 解析失败（0 job，
  教训：改 workflow 须先 `yaml.safe_load` 本地验证）；③ `test_novel_progress` 两处 `write_text('正文')`
  未传 encoding——本机 cp936 掩盖、CI cp1252 必炸（注意事项 5 的实证；其余 1788 条在 cp1252 下全过 =
  全仓唯此两处残留）。
- 2026-10-22 运行状态抽查：`/api/plugins` 双插件 `runtime_status=running`（bishu-novel 0.2.2 / xs2-novel-flywheel 0.1.13）；`/api/system/status` 四执行器 `ready`（pid 为**真实 worker 解释器**，非启动桩）；`cd web && npm.cmd run build` 成功。
- 2026-10-24 R21 完结态抽查：8021 服务运行 R21 代码（重启加载 `29b8eb8`，4/4 执行器
  `ready`、`degraded=false`）；活体 e2e `tests/test_humanware_e2e.py` **15 passed /
  0 skipped**（F5/F6/F7 版本探测全部执行，确认新代码在线）；存储名审计
  `scripts/audit_storage_names.py` → `[clean]`；仓库根 `determinflow-executor-*`
  残留**清零**（runtime 目录已在 `data/system/executor-runtimes/`）；`29b8eb8`
  的 CI（ubuntu backend）success。

## 平台注意事项（Windows，2026-10-22 实测确认）

这些是**实测结论**，不是推测；修改相关代码前务必先读。

1. **venv 的 `python.exe` 是启动桩（stub launcher）**
   `.venv\Scripts\python.exe`（约 255 KB）会 fork 真正的解释器作为**子进程**。因此：
   - `subprocess.Popen().pid` / `asyncio.create_subprocess_exec().pid` **不等于**子进程的 `os.getpid()`；
   - 任何"用 spawn 返回的 pid 代表工作进程"的逻辑在 Windows 上都错位；
   - Python 3.12 与 3.14 的 stdlib venv **都是**该行为（与 `uv` 无关）。
   - 已有正确做法：`WorkflowExecutorSupervisor.pid` 采用 worker 在 `ping` 握手中自报的 pid。

2. **脚本（Script 节点）的 `os.getppid()` 不等于执行器 pid**
   进程链为：执行器解释器 → `sys.executable`（桩）→ 真正解释器（跑脚本）。脚本的直接父进程是桩。
   不要再以 `ppid == member_pid` 断言"任务跑在哪个执行器"；应使用下节的执行器身份环境变量。

3. **执行器身份环境变量（可用于脚本自证世代）**
   Workflow Executor 为子进程注入 `DETERMINFLOW_EXECUTOR_ID` 与 `DETERMINFLOW_EXECUTOR_EPOCH`，脚本可读取以确认自己由哪个执行器世代运行（脚本经 `os.environ` 继承）。

4. **POSIX 权限位在 NTFS 上不可用**
   `os.chmod(path, 0o600)` 会静默"成功"，但 `st_mode` 仍为 `0o666`。凡断言权限位的用例须 `if os.name == "posix":` 守卫。

5. **`Path.read_text()` 不传 `encoding` 会用系统 locale（本机 cp936）**
   读取 UTF-8 文件将得到乱码。本项目所有文件读写**应显式传 `encoding="utf-8"`**。

6. **`Path.write_text()` 默认把 `\n` 翻译为 `\r\n`**
   若后续对**原始字节**做哈希（如 marketplace 的 `source_sha256`），跨平台结果会不同；需要确定性字节时传 `newline="\n"`。

7. **symlink 相关用例仅在 Low-IL 解释器下不可用（R17 修正，见平台注意事项 9）**
   会话令牌中 `SeCreateSymbolicLinkPrivilege` 为 Disabled 且进程内启用无效，`os.symlink` 报 WinError 1314。根因与本机解释器被降为 **Low 完整性级别**有关，不必然需要管理员令牌或重新登录：以 High-IL 解释器（`C:\Windows\py.exe` + venv site-packages 经 `PYTHONPATH` 挂载）跑同一套件时，symlink 用例可正常创建链接并通过。

8. **`%TEMP%` 有 ACL 限制**，`tempfile.mkdtemp()` 会落到当前工作目录（实测
   `gettempdir()` 返回进程 CWD），导致仓库根出现 `determinflow-executor-*/`、
   `pytest-of-wenbo/`、`tmpXXXX` 等临时目录；建议加入 `.gitignore`。
   **R21 处置**：executor supervisor 已改显式 `dir=DATA_DIR/system/executor-runtimes`
   （`executor_supervisor._runtime_dir_root`），不再依赖 %TEMP%；仓库根 52 个历史残留
   已清理 48 个（余 4 个为当时在跑服务的活跃目录，重启服务后失效）。其余调用点
   （如 pytest 自身）仍可能回落 CWD，gitignore 规则保留。

9. **（2026-10-23 R16 发现 / R17 定位根因并给出处置）msys 引导被拒——影响所有需要 git 传输的测试**
   症状：由 python `subprocess` 派生的 Git for Windows msys 程序（`usr/bin/sh.exe`、`bash.exe`）
   启动即崩：`*** fatal error - NtCreateDirectoryObject(\BaseNamedObjects\msys-2.0S5-<hash>): 0xC0000022`。
   **R17 根因（实测，非推测）**：
   - 令牌的强制完整性级别（IL）随**可执行文件所在位置**变化：任何 `python.exe`（含改名副本）
     从 **F: 盘**启动即为 **Low IL（S-1-16-4096）**，同一二进制复制到 **C:** 启动为 **High IL**；
     `cmd.exe`/`node.exe`/`C:\Windows\py.exe` 在本会话均为 High IL。
   - 机器上已存在由更早的 msys 进程创建的共享对象 `\BaseNamedObjects\msys-2.0S5-<hash>`。
     实测（本会话，ctypes 直调 ntdll）：该对象**确实存在**——自建同名目录对象返回
     `0xC0000035`（OBJECT_NAME_COLLISION），说明先前某进程已创建它；
     Low-IL 进程 `NtOpenDirectoryObject` 时 `DIRECTORY_QUERY`/`LIST_DIRECTORY`/`MAXIMUM_ALLOWED`
     成功，而 `SYNCHRONIZE`/`WRITE_DAC`/`DIRECTORY_ALL_ACCESS` 一律 `0xC0000022`
     （STATUS_ACCESS_DENIED），`MAXIMUM_ALLOWED` 实际只授予 `SYNCHRONIZE|READ_CONTROL` 级别；
     msys 需要被拒绝的那部分访问，故引导失败。对象属主 SID 为本地用户 RID 1001。
     （DACL 明细未能可靠读出，因此此处只陈述可达/被拒的实测结果，不断言具体 ACE。）
     对照实验：`cmd.exe`(High IL) 直接 exec `sh.exe` → rc=0 正常；`cmd.exe` → `python.exe`(Low IL)
     → `sh.exe` → 崩溃。因此 R16 记为「疑似安全软件 / 重启可解」的结论**不成立**——判别变量是
     解释器令牌的 IL，而非机器状态；**无需重启机器**。
     （R16 当日 R15 全量绿、R16 全量红的差异，同样由该 IL 差异解释。）
   - 影响面：git 的 clone/fetch/push/ls-remote 传输（本地路径与 `file://` 也算）都要 exec msys `sh`；
     `init/add/commit/config/rev-parse/branch/tag/log/diff` 等原生动词**不受影响**。
     同理，Windows 建 symlink 需 `SeCreateSymbolicLinkPrivilege`，Low-IL 进程也拿不到——
     此前记录为「需管理员/重新登录」，R17 证据：High-IL 全量运行的 11 个 skip 恰为 macOS 签名(6)+icon.icns(1)+fcntl(2)+Unix进程树(2)，symlink 类 skip 消失且用例通过，故同样由令牌 IL 决定。
   - **处置（两者均已在仓库固化）**：
     1) `tests/conftest.py` 新增 msys 探测钩子：失败信息含 `NtCreateDirectoryObject` 签名，
        或失败发生在已知依赖 git 传输的 6 个插件测试模块内**且**探测确认本机传输不可用时，
        转成 skip（附原因）。探测通过（传输可用）时钩子完全不介入，真实缺陷照常失败。
     2) 需要真正执行这些用例时，改用 **High-IL 解释器**跑 pytest：
        ```powershell
        cd "F:\DeterminFlow x2\xs2"
        $sp = "$PWD\.venv\Lib\site-packages"
        $env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
        C:\Windows\py.exe -m pytest -q
        ```
        （`py.exe` 是 C: 上的原生启动器，它启动的 venv 包路径解释器仍为 Low IL，
        因此需把 venv 的 site-packages 经 PYTHONPATH 挂到 C: 侧解释器上。）
   - 实测基线：Low-IL（venv）`pytest -q` → **1497 passed / 96 skipped / 0 failed**；
     High-IL（py.exe + PYTHONPATH）同一提交 → **1582 passed / 11 skipped / 0 failed**
     （11 项为 macOS/POSIX 类平台 skip）。

11. **（2026-10-24 R18 实测）PowerShell / .NET `System.Uri` 会剥掉 URL 路径段的尾随点**
    `[System.Uri]"http://host/api/status/welcome."` 的 `AbsolutePath` 是 `/api/status/welcome`
    （`welcome...` 同样被剥成 `welcome`），因此 `Invoke-WebRequest` / `curl`（经 PowerShell
    参数绑定）发出的请求**根本不含尾随点**。后果：对「尾随点别名」这类缺陷做服务侧取证时，
    用 `Invoke-WebRequest` 会得到 **200**，误判成「服务端守卫失效」；实测同一 URL 用 Python
    `urllib` 直连则正确返回 **400**（`%2E` 编码形式亦 400）。
    **验证名字规范化类缺陷必须用不经 .NET URI 解析的客户端**（`urllib.request`、`httpx`，
    或本项目 `tests/test_humanware_e2e.py`）。R17 §3.4「实时取证」表中 3 行以
    `Invoke-WebRequest` 记录的 `welcome.`→200 属该客户端假象，而非服务端行为；R18 予以更正
    （服务端当时已正确 400，见 HANDOVER_ROUND18 §4 R18-ENV-2）。

12. **（2026-10-24 R18 实测）Windows 设备名作为「目录」与作为「文件」语义不同**
    R17 把 `CON`/`PRN`/`AUX`/`COM1`/`LPT1`/`CONIN$` 与 `NUL` 同等对待，实测有偏差：
    - 若已存在真实目录 `<x>\CON`，则 `CON\data.md` 的读写**完全正常**（`is_dir()=True`、
      `iterdir()` 可列出、`\\?\` 前缀读回一致），`mkdir` 亦成功。
    - `NUL` 是唯一「幻影目录」：`mkdir` 静默成功、`exists()` 恒真但 `is_dir()=False`，
      其下任何写入 → `FileNotFoundError(WinError 3)`，`shutil.rmtree` 删不掉。
    - 处置结论不变：一律**拒绝**（保持 R17 已上线的 web 面行为与跨工具一致性——资源管理器
      拒绝创建这些名字），但根因表述以此条为准，不再写作「CON 写入也会静默丢弃」。

13. **（2026-10-24 R20 实测）设备名不只是「路径段」问题，也是「标识符」问题**
    第 12 条讲的是设备名当**路径段**；R20 发现同一族缺陷也出现在**标识符**上——插件 id、
    资源 effective id、市场 Skill id 的合法字符集（kebab-case `^[a-z0-9]+(?:-[a-z0-9]+)*$`）
    与小写设备名同型，`nul`/`con`/`com1` 全部合法，而这些 id 会被直接拼成目录名：
    - **插件 id** → `checkouts/<id>`、`runtime-resources/<id>`、锁文件键。实测
      `prepare_plugin_resources(extension_id="nul")` 报 **WinError 87**、
      `os.replace(... → checkouts/nul/<rev>)` 报 **WinError 3**；两者都是 `OSError`，
      而 `_raise_http_error` 只映射 `ValueError`/`PluginStoreError`/`SourceTrustError`，
      故**逃逸成 HTTP 500 而非 400**。
    - **路径型资源 id**（workflow/script_library/skill/rule）→ `copytree` 目标目录名。
      实测 `copytree(src/nul → dst/nul)` 报 **WinError 1**，留下 `exists()=True` 的幻影，
      内容不可达且 `rmtree(ignore_errors=True)` 静默无效。
    - **市场 Skill id** → `marketplace-skills/<id>`。最隐蔽的一处：**`exists()` 恒真发生在
      任何创建动作之前**（NUL 设备本身），于是 `resolve_openable_skill("nul")` 会返回
      **409「本地存在同名但来源不同的 Skill」**——纯属谎报；该名字被永久占用，既装不上
      也卸不掉。
    - **处置**：三处入口统一拒绝，判定谓词为 `win_names.unsafe_device_name()`，
      **平台无关**（不按 `os.name` 门控）——因为这些 id 是跨平台共享键（写进
      `plugins.lock.json`、registry 清单、`skills_config.json`），条件式校验会让同一份配置
      在 POSIX 有效、在 Windows 永久损坏。仅**路径型**资源才拒；`agent`/`prompt`/
      `preset_phrase` 等纯 JSON 键不拒（否则误伤正文里恰好叫 `nul` 的键）。
