# DeterminFlow（yuyang0702/xs2）项目信息

## 项目名称
DeterminFlow（`yuyang0702/xs2` 二次开发版）——面向生产的确定性 AI 工作流运行框架。把 LLM、脚本、API、数据库操作和人工审批组织成有版本、可校验、可重试、可恢复、可审计的工作流。

- 仓库：https://github.com/yuyang0702/xs2
- 上游：https://github.com/alikon-art/DeterminFlow
- 本地安装路径：`F:\DeterminFlow x2\xs2`

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
- 2026-10-22 运行状态抽查：`/api/plugins` 双插件 `runtime_status=running`（bishu-novel 0.2.2 / xs2-novel-flywheel 0.1.13）；`/api/system/status` 四执行器 `ready`（pid 为**真实 worker 解释器**，非启动桩）；`cd web && npm.cmd run build` 成功。

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

7. **symlink 相关用例在本机必然失败**
   会话令牌中 `SeCreateSymbolicLinkPrivilege` 为 Disabled 且进程内启用无效，`os.symlink` 报 WinError 1314。需管理员令牌或重新登录后再跑。

8. **`%TEMP%` 有 ACL 限制**，`tempfile.mkdtemp()` 会落到当前工作目录，导致仓库根出现 `determinflow-executor-*/`、`pytest-of-wenbo/` 等临时目录；建议加入 `.gitignore`。