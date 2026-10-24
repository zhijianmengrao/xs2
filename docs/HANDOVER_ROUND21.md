# DeterminFlow (xs2) 交接报告 — Round 21（O2 executor 临时目录钉位 + B13 纵深只读审计 + 市场安装 e2e 补缺 + updates exists() 语义锚定）

> 本轮定位：HANDOVER_ROUND20 §9 计划的落地轮。开局核查发现两仓库均已推送干净
> （`origin/main..main` = 0，xs2 与 DeterminFlow-Plugins 皆是），R20 遗留 P0
> 「用户推送」**已完成**，CI 已首绿（`e925dda` 四 job 全绿）——故本轮无 P0 项，
> 直接做 P1/P2 四件事。
> 基线：`449578f`（R20 的 CI 复盘提交），工作树干净。

## 1. 结论摘要

| 项 | 结果 |
|---|---|
| O2（P1） | executor runtime 目录显式 `dir=DATA_DIR/system/executor-runtimes`；真实 spawn 验证通过；**仓库根 52 个残留清理 48 个**（余 4 个为在跑服务的活跃目录，重启后已可删） |
| B13 纵深（P1） | 存储名只读审计：`src/core/storage_name_audit.py` + `scripts/audit_storage_names.py`（退出码 0/1）；真实仓库扫描 **clean** |
| P2a | 市场 Skill 安装 e2e（真实 portal 客户端 + MockTransport + 真实多文件包 + 路由层）3 条 |
| P2b | `updates.py:166` exists() 语义锚定 2 条（设备名 → 400 先于任何查询；真实残留目录 → 409 保持） |
| 新增测试 | 12 条（5+2+3+2） |
| Low-IL 全量 | **1732 passed / 96 skipped / 0 failed**（105.1s；对账 1720+12） |
| High-IL 全量 | **1817 passed / 11 skipped / 0 failed**（124.1s；对账 1805+12） |
| 前端 | lint 0 problems、test 48/48、build ✓ 7.04s（本轮未改前端） |
| Bug | 0 个新发现（本轮为加固/补测/运维轮，无红灯缺陷） |

一句话：**executor 临时目录不再散落仓库根（含历史残留清理），设备名历史遗留有了
只读诊断工具（当前 clean），市场安装面补上真实包全链 e2e，update 面的 exists()
语义被测试钉死。**

## 2. 测试计划（本轮）

| 优先级 | 目标 | 手段 | 结果 |
|---|---|---|---|
| P0 | 基线可复现 | 服务在跑时 Low-IL 全量 | 1720/96/0，与 R20 精确一致 |
| P1 | O2 红灯取证 | `tempfile.gettempdir()` 探针 | 返回**进程 CWD**（`F:\DeterminFlow x2\xs2`），证实回落链 |
| P1 | O2 绿灯（单测） | monkeypatch DATA_DIR + 失败 spawn | 2 条通过；失败路径零残留、CWD 零新增 |
| P1 | O2 绿灯（真实 spawn） | pool/protocol/readiness/observability 四套件 | 79 条全过；`data/system/executor-runtimes/` 用后即清（0 残留） |
| P1 | B13 纵深 | 扫描器单测 + 真实仓库 CLI | 5 条通过；真实仓库 clean（exit 0） |
| P2 | 安装 e2e 真实包 | TestClient + ResourceMarketplaceClient + MockTransport | 3 条通过（含出站请求序列取证） |
| P2 | update exists() 锚定 | RecordingMarketplace + 残留目录现场 | 2 条通过 |
| P3 | 双基线 + 前端三连 | 全量 ×2 + lint/test/build | 1732/96/0、1817/11/0、前端全过 |

## 3. 测试用例与执行结果

### 3.1 O2 红灯取证（真实环境）

```
TEMP env: C:\Users\wenbo\AppData\Local\Temp
tempdir:  F:\DeterminFlow x2\xs2          ← gettempdir() 已回落到 CWD
mkdtemp landed: F:\DeterminFlow x2\xs2\determinflow-executor-cn0emowi
```

即 PROJECT_INFO 注意事项 8 的机制实证：mkdtemp 无 `dir=` 时按
`TEMP → TMP → CWD` 回落，仓库根 52 个残留即此因（进程硬杀时 `start()` 的
except 清理与 `stop()` 均不执行）。

### 3.2 残留目录活跃性判定（清理前的安全核查）

不能用 mtime 猜（R20 记服务「11:58:43 启动」实为 10-23T19:58 的时间戳格式
误读——4 个 19:58:12 的目录才是活跃的）。改用**权威判定**：读每个目录
`rpc.endpoint` 的 JSON 端口 → 对 `netstat -ano` 的 LISTENING 集合求交：

```
ACTIVE: 4 个（端口 51928/51932/51935/51938 监听中 = 在跑服务的 4 执行器）
DEAD:   48 个（4 个无 endpoint 文件 + 44 个端口已死）
清理：   removed=48, kept=4 → 仓库根仅剩活跃目录
```

### 3.3 新增用例清单（12 条，全绿）

| 文件 | 条数 | 锚定内容 |
|---|---|---|
| `tests/test_storage_name_audit.py` | 5 | 配置键/目录项命中报告；合法名（nul-2/com0/nullable）不误报；缺面/坏 JSON 安静跳过；**真实仓库树零命中**（R20 零误伤结论的常驻锚） |
| `tests/test_executor_runtime_dir.py` | 2 | runtime 根钉在 `DATA_DIR/system/executor-runtimes`；spawn 失败时清理生效、零残留、CWD 零新增 |
| `tests/test_marketplace_install_e2e.py` | 3 | 真实包经路由→服务→真实 portal 客户端→pin→download→verify→原子落盘→provenance→启用配置全链（含出站请求序列断言 `GET 详情 + GET 下载` 各一次）；重复安装 409 already_exists 且不二次下载；设备名 slug HTTP 面 400 invalid_slug 且**零出站请求** |
| `tests/test_marketplace_update.py`（追加） | 2 | 设备名 slug update → 400 invalid_slug 且 `get_skill` 零调用（先于 `updates.py:166` 的 exists()）；真实残留目录（非设备名）→ 409 conflict（exists() 分支正当语义保持，防止 R20 修复被误扩大） |

### 3.4 e2e 实现要点（供后续维护）

- 既有 e2e（`test_humanware_e2e.py`）走活体 8021 服务；市场安装面无法依赖真实
  远端 registry，故用 **httpx `MockTransport`**：真实 `ResourceMarketplaceClient`
  的请求序列化/响应解析路径全走真，仅不出网卡。客户端必填 `app_version`；
  TestClient 需 `client=("127.0.0.1", 50000)` 过路由的本机来源校验 +
  `DETERMINFLOW_DESKTOP=1`（与既有路由测试同款）。
- High-IL 全量必须按 PROJECT_INFO 注意事项 9 的 **PowerShell 原文命令**跑；
  在 Git Bash 里 `export PYTHONPATH=$PWD/...` 会注入 MSYS 风格路径
  （`/f/...`），Windows Python 读不了 → 125 collection errors（本轮实测踩坑）。

## 4. Bug 报告与根因分析

本轮**无新发现缺陷**（无红灯项）。四项交付均为加固/补测/运维：

| 项 | 性质 | 说明 |
|---|---|---|
| O2 | 既有已记录问题的修复 | HANDOVER_ROUND20 §7 O2；风险实评低于交接预估（endpoint 是 JSON 文件非 socket，子进程不继承该目录为 cwd） |
| B13 纵深 | 防御性诊断工具 | R20 §8.3 遗留；只读，不改行为 |
| P2a/P2b | 测试补缺/锚定 | R20 §9 P2 两项 |

附带修正一处**文档错误**：R20 记 8021 服务「pid 81092，11:58:43 启动」；
本轮按端口活跃性判定，服务实际启动于 **2026-10-23 19:58**（11:58 系时间戳
格式误读），R20 全量期间加载的确实是不含 R20 提交的代码（与 R20 的 e2e
诚实 skip 处置一致，无实质影响）。

## 5. 修复代码要点（O2）

`src/workflow/executor_supervisor.py`：

```python
def _runtime_dir_root() -> Path:
    """Executor runtime 目录的固定落点（data/ 下，PROJECT_INFO 注意事项 8）。…"""
    root = DATA_DIR / "system" / "executor-runtimes"
    root.mkdir(parents=True, exist_ok=True)
    return root

# start() 内：
self._runtime_dir = Path(
    tempfile.mkdtemp(prefix="determinflow-executor-", dir=_runtime_dir_root())
)
```

接口兼容性：无签名变更；`DATA_DIR` 可被 env `DETERMINFLOW_DATA_DIR` 覆盖
（既有语义）；失败清理路径（`start()` except / `stop()`）未动。
`data/**` 已整体 gitignore，新目录无需 ignore 规则。

## 6. 回归测试结果

| 套件 | 结果 | 对账 |
|---|---|---|
| Low-IL 全量（服务在跑） | **1732 passed / 96 skipped / 0 failed**，105.1s | 1720 + 12 = 1732，skip 不变 |
| High-IL 全量（权威） | **1817 passed / 11 skipped / 0 failed**，124.1s | 1805 + 12 = 1817 |
| 邻域定向 | 239 passed / 0 failed（plugin/marketplace/skill/executor 家族） | — |
| 真实 spawn 套件 | 79 passed（pool_start/protocol/readiness/observability） | 全量后新位置 0 残留、仓库根零新增 |
| 前端 | lint 0 problems；test 48/48；build ✓ 7.04s | 本轮未改前端 |

skip：Low-IL 96（symlink 40 + msys 传输类 + macOS/POSIX 平台类）；High-IL 11
（全为 macOS 签名/打包与 POSIX fcntl/进程树，环境类）。

## 7. 优化清单（本轮）

- **O2（已做，见 §5）**：含运维收尾——48 个死残留已删；4 个活跃目录在服务
  重启后失效可删（见 §10 收尾记录）。
- **O3（已做，微小）**：`scripts/audit_storage_names.py` 退出码语义
  （0 clean / 1 findings / 2 usage），可直接进 CI 或手工巡检。
- **记录未做**：`start()` 里 `mkdtemp` 失败时 supervisor 状态停留在
  `starting`（调用方 pool 会丢弃该实例，无实际泄漏；属既有行为，非本轮引入，
  改动需动 pool 语义，留待有真实需求时处理）。

## 8. 风险与遗留问题

1. **POSIX 真跑仍未验证**（环境依赖，R20 起遗留）：本轮所有平台无关判定仍
   只有单元级证据。
2. **HumanwareScoreCard 前端组件**（R19 遗留 P3，连续第三轮顺延）：纯新增
   UI 功能，无缺陷压力，优先级维持 P3。
3. `conftest.py` 的 msys 探测钩子与 symlink skip 逻辑未动；Low-IL 96 skip
   的构成与 R20 完全一致。
4. 服务重启后 `data/system/executor-runtimes/` 会随服务生命周期增删；若服务
   被硬杀，残留集中该处（可用 `win_names` 无关的普通 rmtree 清理），不再
   污染仓库根。

## 9. 下一轮迭代计划（Round 22）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | `updates.py` 的 `_trusted_marketplace_skill_path` 与 installs 的 `target.exists()` 判定路径做一次「幻影目录免疫」复查（R20 修复后理论不可达，但无 `monkeypatch _on_windows` 之外的证据） | 低 | 1h |
| P2 | 把 `scripts/audit_storage_names.py` 挂进 CI（windows job 之后跑一次，防新数据回归） | 低 | 30min |
| P2 | `test_humanware_e2e.py` 的 F5/F6/F7 探测函数去重（三个近似 `_service_enforces_*` 探测可收敛成一个版本探测） | 低 | 30min |
| P3 | HumanwareScoreCard 前端组件（R19 遗留） | 低 | 2h |
| P3 | POSIX 真跑（需容器/WSL 环境） | 低 | 环境依赖 |
| P3 | `start()` 失败时 supervisor 状态机 `starting` 悬挂（§7 O3 记录项） | 中 | 1h |

## 10. 命令记录（本轮）

```powershell
# 基线核实与红灯取证
cd "F:\DeterminFlow x2\xs2"; git --no-pager log --oneline -3        # 449578f
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider  # 1720/96/0
.\.venv\Scripts\python.exe -X utf8 -c "import tempfile; print(tempfile.gettempdir())"
#   → F:\DeterminFlow x2\xs2  （O2 红灯：回落 CWD 实证）

# B13 纵深：真实仓库审计
.\.venv\Scripts\python.exe -X utf8 scripts/audit_storage_names.py   # [clean]，exit 0

# 残留清理（活跃性判定内嵌：rpc.endpoint 端口 ∩ netstat LISTENING）
#   removed=48, kept=4（活跃）

# 全量回归
.\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider  # 1732/96/0
$sp = "$PWD\.venv\Lib\site-packages"
$env:PYTHONPATH = "$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32"
C:\Windows\py.exe -X utf8 -m pytest -q -p no:cacheprovider           # 1817/11/0

# 前端三连
cd web; npm.cmd run lint; npm.cmd test; npm.cmd run build             # 0 problems / 48/48 / ✓
```
