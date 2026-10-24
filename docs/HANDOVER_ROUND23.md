# DeterminFlow (xs2) 交接报告 — Round 23（维护态首轮：P1 幻影免疫真实证据收口 + B14 修复 + P2 两项落地）

> 本轮定位：R22 完结后重启迭代的**维护态首轮**（迭代候选起点=HANDOVER_ROUND21 §9）。
> 全量终验无回归；P1 项以**真实文件系统证据**（非 monkeypatch）收口；修复 1 个
> 编号缺陷 B14（supervisor 状态悬挂）；落地两项 P2（审计脚本挂 CI、e2e 探测去重）。
> 基线：`321a2f0`（R22 终提交），工作树干净、`origin/main..main` = 0。

## 1. 基线终验（改动前，全部通过）

| 验证项 | 结果 | 与 R21/R22 基线对比 |
|---|---|---|
| Low-IL 全量 | **1732 passed / 96 skipped / 0 failed**（110.19s） | 一致 |
| 前端三连 | lint 0 problems；npm test 0 fail（tail 所见套件 6/6）；build ✓ 7.22s | 一致 |
| 存储名审计 | `scripts/audit_storage_names.py` → `[clean]`，exit 0 | 一致 |
| 活体 e2e（8021 服务） | **15 passed / 0 skipped**（F5/F6/F7 探测全执行） | 一致 |
| 服务健康抽查 | `/api/system/status`、`/api/plugins` 均 200，双插件 `running` | 一致 |
| git 状态 | 工作树干净，main == origin/main（`321a2f0`） | 一致 |

## 2. P1 复查收口：幻影目录免疫的**真实证据**（无代码改动）

R21 §9 P1 要求对 `updates.py` 的 `_trusted_marketplace_skill_path` 与 installs 的
`target.exists()` 判定路径做「幻影目录免疫」复查，且明确指出当时**只有
monkeypatch `_on_windows` 之外的间接证据**。本轮以真实 NTFS 实验补齐：

**实验方法**：用扩展路径前缀 `\\?\` 绕过 Win32 设备名解析，在临时目录下创建一个
**真实存在**的 `nul` 目录（`os.mkdir("\\\\?\\...\\nul")` 成功），然后用不打任何
补丁的常规 `Path` 与生产代码路径去触碰它。

**实测结论（三条，全部真实环境取证）**：

1. **真实 nul 目录对常规 `Path` 仍呈幻影属性语义**：`exists()=True`、
   `is_dir()=False`、`is_symlink()=False`，但 `iterdir()` 能列出它、其下
   `SKILL.md` 可正常写入并读回——比 PROJECT_INFO 注意事项 12 的「幻影 NUL」
   更微妙：目录真实存在、可读写，唯独**属性查询**被设备名解析劫持。
2. **`_trusted_marketplace_skill_path` 在真实文件系统上正确拒绝**：
   `candidate.is_dir()=False → LocalSkillError(conflict, 409)`，防纵深成立，
   不依赖入口校验的假设。
3. **入口面守卫链闭合**（代码审读）：installs 的 `target.exists()`（installs.py:57）
   上游为 `verify_downloaded_skill → validate_skill_content → assert_safe_skill_id`，
   包内 `name: nul` 在拼路径之前即被拒绝；service 入口 `_validate_slug` 同样含
   `assert_safe_skill_id`。设备名 id **到不了** `target.exists()`。

**处置**：无需改代码；把上述真实语义钉成常驻回归 `tests/test_real_device_name_dirs.py`
（2 条：路径守卫真实拒绝 + 审计扫描器发现真实 nul 遗留；POSIX/不支持环境诚实 skip）。
顺带确认 `scan_storage_names` 经 `iterdir()` 枚举，**能**发现 `\\?\` 创建的真实
设备名目录（真实证据：findings 命中 `data/skills/marketplace :: 'nul'`）。
P1 项就此关闭。

## 3. B14：`start()` 准备步骤失败时 supervisor 状态悬挂 `starting`

- **现象**：`_set_status(STATUS_STARTING)` 之后、`_spawn()` 之前的准备步骤
  （`tempfile.mkdtemp` / `restrict_private_path`）位于 `try` 块**之前**
  （原 executor_supervisor.py:224-227）。这两步抛异常时直接穿透 `start()`，
  无人把状态复位为 `stopped`——健康面板看到该 executor 永远 `starting`
  （HANDOVER_ROUND21 §7「记录未做」项）。
- **影响范围**：仅状态可观测性；pool 会丢弃失败实例，无进程/目录泄漏
  （R21 已定性）。风险等级：低；但属状态机诚实性问题，修复成本极小。
- **根因**：异常防线（try/except → STATUS_STOPPED）的覆盖范围漏掉了 try 之前
  的两行准备代码。
- **修复（最小改动，11 行）**：把 `mkdtemp` + `restrict_private_path` 移入
  `try` 块首部；except 分支原有清理逻辑（`_runtime_dir` rmtree + 置 None +
  STATUS_STOPPED）原样覆盖新移入的两步。`stop()` 收尾已把 `_runtime_dir`
  置 None（executor_supervisor.py:441-446），重启场景下 except 不会误删旧目录。
- **回归测试**：`tests/test_executor_runtime_dir.py::test_start_failure_before_spawn_resets_status_to_stopped`
  ——注入 mkdtemp 失败 / restrict_private_path 失败两种场景，断言
  `status == "stopped"`、`_runtime_dir is None`、runtime 根目录零残留。
- **风险点**：无接口变化；except 分支行为对原有 spawn 失败路径完全不变。

## 4. P2 两项落地

| 项 | 内容 | 验证 |
|---|---|---|
| O-a 审计脚本挂 CI | `.github/workflows/ci.yml` windows-backend job 在 pytest 后追加 `python scripts/audit_storage_names.py`（只读巡检防新数据回归）。**已本地 `yaml.safe_load` 校验**（R18 教训）：4 job 结构完整，windows-backend 6 步 | 脚本本机 exit 0；CI 实跑待推送后观察 |
| O-b e2e 探测去重 | `tests/test_humanware_e2e.py`：F5/F6/F7 三个近似探测的公共管线收敛为 `_rule_enforced` + `_require_service_rule`；R18 探测 `@lru_cache` 消除 F6/F7 重复请求。**保留两条规则级探测**（断言不同端点/契约版本），不收敛成单一「版本探测」——那会让一条规则的结论推断另一条，失去逐规则诚实 skip 语义 | 活体 e2e 15 passed |

## 5. 测试用例对账

| 基线 | 改动前 | 净增 | 改动后 |
|---|---|---|---|
| Low-IL | 1732 / 96 / 0 | +3（B14 回归 1 + 真实设备名 2） | **1735 passed / 96 skipped / 0 failed**（105.49s，实测） |
| High-IL | 1817 / 11 / 0 | +3（同上） | **1820 passed / 11 skipped / 0 failed**（实测） |
| 总用例 | 1828（R21 口径） | +3 | **1831** |

新增真实设备名 2 条在 Windows（Low/High-IL 均可，`\\?\` 前缀不需要特权）真实执行；
ubuntu CI 上 skip（`sys.platform != "win32"` 诚实跳过）。

## 6. 修改文件清单

```
src/workflow/executor_supervisor.py      # B14：mkdtemp/restrict_private_path 移入 try（+4/-4 行 + 注释）
tests/test_executor_runtime_dir.py       # +38 行：B14 回归（两种准备步骤失败场景）
tests/test_real_device_name_dirs.py      # 新文件：P1 真实证据常驻回归（2 条）
tests/test_humanware_e2e.py              # O-b：探测公共管线收敛 + lru_cache（净 -20 行左右）
.github/workflows/ci.yml                 # O-a：windows-backend 追加存储名审计步骤
docs/HANDOVER_ROUND23.md                 # 本文件
docs/PROJECT_INFO.md                     # 项目状态追加 R23 条目 + 测试环境基线行
```

## 7. 风险与遗留问题

1. **POSIX 真跑**（环境依赖，连续遗留）：本机实测 **docker 未安装、WSL 未安装**
   （`wsl --status` 返回未安装提示），本地容器验证不可行；CI ubuntu backend
   （绿）仍是 POSIX 单元级信号。新加的真实设备名用例在 POSIX 上 skip，不阻塞。
2. **HumanwareScoreCard 前端组件**（R19 遗留 P3，连续第四轮顺延）：纯新增 UI，
   与本轮测试/修复主线无关，维持下一轮候选。
3. **CI audit 步骤实跑验证**：O-a 已本地 YAML 校验 + 脚本 exit 0，但该步骤的
   CI 实跑需推送后观察（本轮按纪律**只 commit 不 push**，见 §8）。
4. 前端 `npm test` 输出经 `tail` 截断，本轮仅确认整体 0 fail（退出码 0）；
   完整逐套件计数未复核（R22 记录为 8 套件 406 断言，本轮构建产物哈希未见异常）。

## 8. 提交与推送状态

- 本轮结束：本地 1 个 commit（fix+test+ci+docs）；**未推送**——推送需处理
  git 代理问题（全局 socks5 破坏 GCM 授权，见记忆 xs2-git-push-proxy：
  PAT 种库或换 http 代理），且属外发动作，留待维护者确认后执行。
- 推送后验证清单：`origin/main..main` = 0；CI 四 job 全绿（重点 windows-backend
  的第 6 步 Storage name audit）；桌面管线不受影响（未触碰 tauri/release 面）。

## 9. 下一轮迭代计划（Round 24 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P1 | 推送 R23 提交并核对 CI 四 job（含新 audit 步骤实跑） | 低 | 15min |
| P2 | HumanwareScoreCard 前端组件（R19 遗留，契约 §3.3 字段已定，纯新增 UI） | 低 | 2h |
| P2 | `test_humanware_e2e.py` 顶部 `_probe` 与 F5–F7 探测统一服务可达性处理（URLError 中途宕机时 `_get` 会抛未捕获异常，可转为诚实 skip） | 低 | 30min |
| P3 | 真实设备名回归扩展：`\\?\` 真目录下 `installation_state()` 的 `exists()→conflict` 谎报路径复核（R20 修复面） | 低 | 30min |
| P3 | POSIX 真跑（需先装 docker/WSL，环境决策归维护者） | 低 | 环境依赖 |
| P3 | `start()` 失败路径之外的 pool 级语义复查（R21 曾记「改动需动 pool 语义」，本轮最小修复后该备注可复核是否已消除） | 中 | 1h |

## 10. 命令记录（本轮）

```bash
# 基线终验
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest -q                                   # 1732/96/0（改动前）
./.venv/Scripts/python.exe scripts/audit_storage_names.py                 # [clean] exit 0
./.venv/Scripts/python.exe -m pytest tests/test_humanware_e2e.py -q       # 15 passed（改动前后各一次）

# P1 真实证据实验（一次性脚本，证据已钉入常驻回归后删除）
os.mkdir("\\\\?\\" + str(market / "nul"))                                  # 成功创建真实 nul 目录

# 修复后全量回归
./.venv/Scripts/python.exe -m pytest -q                                   # 1735/96/0（Low-IL）
sp='F:\DeterminFlow x2\xs2\.venv\Lib\site-packages'
MSYS2_ENV_CONV_EXCL=PYTHONPATH PYTHONPATH="$sp;$sp\win32;$sp\win32\lib;$sp\pythonwin;$sp\pywin32_system32" \
  C:/Windows/py.exe -X utf8 -m pytest -q -p no:cacheprovider              # 1820/11/0（High-IL 权威）

# CI YAML 本地校验（R18 教训）
./.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))"
```
