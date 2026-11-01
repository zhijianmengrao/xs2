# DeterminFlow (xs2) 交接报告 — Round 81（msys 对象 ACL：根因是「对象带着创建者的完整性级别」）

> 本轮定位：R80 §8-1 / R70 §7-1 挂账的「msys 对象 ACL 跨会话对照实验」（用户拍定
> 主线）；另按拍定交付 R80 §8-5「CI 回写历史」的**方案与代价评估**（**不落地**）。
> 落地形态：**测试基建的一处归因文案（恢复处方）+ 1 条用例重写 + 文档**。
> 生产代码（`src/`、`scripts/`）与前端零改动，闸门脚本 md5 未变。

## 1. 一句话结论

R17 只记到「DACL 明细未能可靠读出」，R70/R71 把 113 vs 28 skips 归成「会话状态」。
本轮把安全描述符读出来了：对象 DACL 只有**一条** `Everyone → 0x2000F`
（`READ_CONTROL` + `DIRECTORY_QUERY/TRAVERSE/CREATE_OBJECT/CREATE_SUBDIRECTORY`），
**没有 SACL**。可 Low 打开者拿到的那 `0x2000F` 里，写权限**全部**被拒
（`0xC0000022`），High 打开者全部通过。用**同一 DACL** 的合成对象做
「创建者 × 打开者」交叉对照后，判别变量锁定为：**对象隐式带着创建者的完整性级别
（IL）**——DACL 写着允许并不够。于是 113/28 的分野第一次有了确定机制和可执行处方：
**从 High 的 shell、用 C: 上的启动器跑 pytest**。

## 2. 实测（本机，2026-11-01；全程只读，未改任何既有对象）

### 2.1 对象与它的安全描述符

`\BaseNamedObjects` 共 740 个条目，其中 msys 对象**只有一个**：

| 项 | 实测值 |
|---|---|
| 名字 | `\BaseNamedObjects\msys-2.0S5-1888ae32e00d56aa` |
| 类型 | Directory |
| owner | `S-1-5-21-2150300333-113044971-1653767673-1001`（当前用户） |
| group | `S-1-5-21-2150300333-113044971-1653767673-513` |
| DACL | 1 条 ACE：`ACCESS_ALLOWED`，SID `S-1-1-0`（Everyone），mask `0x2000F` |
| SACL | **不存在**（High 下以 `READ_CONTROL\|ACCESS_SYSTEM_SECURITY` 打开后查询，`control=0x8800`，无 `SE_SACL_PRESENT`） |

`0x2000F` = `READ_CONTROL(0x20000)` | `DIRECTORY_QUERY(0x1)` | `TRAVERSE(0x2)` |
`CREATE_OBJECT(0x4)` | `CREATE_SUBDIRECTORY(0x8)`。**字面上 Low 应该能写。**

### 2.2 同一对象、两种令牌的访问掩码

| 访问 | Low（`S-1-16-4096`） | High（`S-1-16-12288`） |
|---|---|---|
| `DIRECTORY_QUERY` | OK | OK |
| `DIRECTORY_TRAVERSE` | OK | OK |
| `READ_CONTROL` | OK | OK |
| `MAXIMUM_ALLOWED` | OK | OK |
| `DIRECTORY_CREATE_OBJECT` | **0xC0000022** | OK |
| `DIRECTORY_CREATE_SUBDIRECTORY` | **0xC0000022** | OK |
| `DIRECTORY_ALL_SPECIFIC`（0xF） | **0xC0000022** | OK |
| `WRITE_DAC` | **0xC0000022** | OK |
| `ACCESS_SYSTEM_SECURITY` | **0xC0000022** | OK |
| `DELETE` / `WRITE_OWNER` / `SYNCHRONIZE` / `DIRECTORY_ALL_ACCESS` | 0xC0000022 | 0xC0000022 |

Low 令牌**不是受限令牌**（`TokenRestrictedSids` 为空）；它持有 `SeSecurityPrivilege`
并在本进程内 `AdjustTokenPrivileges` 成功（无 `ERROR_NOT_ALL_ASSIGNED`），但以
`ACCESS_SYSTEM_SECURITY` 打开句柄仍然 `0xC0000061`（`STATUS_PRIVILEGE_NOT_HELD`）——
Low 下该特权不生效。High 同一操作成功。

### 2.3 交叉对照：同一 DACL 的合成对象（创建者 × 打开者）

在 `\BaseNamedObjects` 里自建**临时**目录对象（名字带 pid，句柄关闭即删除），用
`SetSecurityInfo` 把 DACL 换成与 msys 对象**逐字相同**的一条 Everyone `0x2000F`：

| 创建者 | 打开者 | `CREATE_OBJECT` / `CREATE_SUBDIRECTORY` / `WRITE_DAC` |
|---|---|---|
| High | Low | **全部 0xC0000022**（与 msys 对象**逐项相同**） |
| Low | Low | 全部 OK |
| Low | High | 全部 OK |

High 创建的合成对象上，Low 拿到的矩阵与 msys 对象完全一致——**DACL 相同、SACL 都
为空，差异只在创建者**。

### 2.4 启动器矩阵（`sh.exe -c 'echo ok'`）

| 启动器 | 自身 IL | 结果 |
|---|---|---|
| Git Bash（`C:\Program Files\Git\usr\bin\bash.exe`） | High | **rc=0** |
| PowerShell（C:） | High | **rc=0** |
| `C:\Windows\py.exe` | High | **rc=0** |
| `F:\...\.venv\Scripts\python.exe`（venv） | **Low** | **rc=3221225794**，`NtCreateDirectoryObject(...): 0xC0000022` |
| C: 的 `python.exe` 原样复制到 `F:\` | **Low** | 同上 |

IL 的来源（实测，两次互为对照）：

- 父 shell 是 **High**：C: 上的 `py.exe`/`python.exe` → High；F: 上的 venv python → **Low**。
- 父进程是 **Low**：子进程继承 Low——从 Low 的 python 里再起 `C:\Windows\py.exe`，
  **仍然是 Low**（`sh.exe` 照样失败）。
- 同一份 `C:\Program Files\Python314\python.exe` 复制到 F: → Low。

即：**IL 由父令牌继承，但 F: 上的可执行文件被强制降到 Low**。

## 3. 归因与对 R70 的更正

- R17 的「Low 被拒、High 可用」在**字面上**是对的（本机今天复现）；R70 的
  「High 也会失败」在本机**不成立**：本机三种 C: 启动器（Git Bash / PowerShell /
  py.exe）下 `sh.exe` 全部 rc=0，High 全量 **2373 passed / 28 skipped**。
- 本轮不重跑 R70 那次的具体命令，因此**不断言当时哪一步错了**；只记录今天可复现的
  事实与解释：「113 vs 28」的判别变量是**启动器的 IL**，而 IL 由「父令牌 + 可执行文件
  所在盘符」决定，不是随机会话状态。R70 观察到的「High 也失败」最可能是那次所谓
  「High」的进程其实是 Low（例如从 Low 解释器里派生的 shell，本机实测这种派生**不会**
  把子进程升回 High）。
- `\BaseNamedObjects\msys-2.0S5-…` 的**创建者 IL 至少是 Medium**（High 打开者可写、
  Low 不可写；合成对象复现同一矩阵），本机**无法区分 Medium 与 High**（只能拿到
  Low/High 两极，见 §8-2）。因此「启动器是 High 就能挂接」在本机成立；若某台机器上
  对象由更高 IL 的进程创建，处方要相应抬高。

## 4. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `tests/conftest.py` | +33 / −22（311 行） | 归因注释改写；`_msys_skip_reason` **恢复处置处方**（High shell + C: 启动器 + `PYTHONPATH`）；`_msys_skip_applies` 注释更正（判据本身不变） |
| `tests/test_msys_attribution.py` | +31 / −18（200 行） | 模块说明按 R81 实测重写；1 条用例重写（`test_skip_reason_names_the_mechanism_and_never_an_integrity_level` → `..._and_the_actionable_fix`） |
| `docs/PROJECT_INFO.md` | 平台注意 9 更正 + R81 轮次条目 | 文档 |
| `docs/JUDGEMENT_LEDGER.md` | §6 用例名、§8 R81 一节 | 文档 |
| `docs/HANDOVER_ROUND81.md` | 新增 | 本文 |

**判据行为零变更**：`_msys_skip_applies` 仍然是「签名 ∨（6 个传输模块 ∧ 探针）」，
IL 不是第三个自变量；变的只有**归因文案**（恢复 R71 删掉的处方）与文档。

md5：`tests/conftest.py` `0ba5b473…` → `a9f294b5…`；
`tests/test_msys_attribution.py` `722425ba…` → `ea1befc3…`（提交前再核一次）。

## 5. 变异验证（五次，`cp` 备份还原）

相关用例集 = `tests/test_msys_attribution.py`（5 条，整模块 `no_msys_skip`）。R71 的教训
是「判红会被钩子吞成 skip」——这里每条都确认输出是 **failed**，不是 skipped。

| # | 变异 | 实测 | 咬合者 |
|---|---|---|---|
| 1 | 处方里去掉 `PYTHONPATH` | **1 failed** | 文案用例 |
| 2 | 处方里去掉 `py.exe` | **1 failed** | 文案用例 |
| 3 | 文案退回「under this Low-integrity token」 | **1 failed** | 文案用例（禁止把责任钉在令牌上） |
| 4 | 文案里写死 `S-1-16-4096` | **1 failed** | 文案用例 |
| 5 | 判据丢掉模块白名单（`signature_hit or transport_blocked`） | **1 failed** | 真值表用例 |

每次还原后 md5 与备份逐字节相同（`a9f294b5…`）。如实记录：五条变异咬合的都是同一个
文件里的两条用例，增量集中在「文案的两半（机制 / 处方）」与「判据不带 IL」——不是五条
互不相干的新判据。

## 6. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：msys 归因 | **5 passed**（0.11s） |
| 全量（Low，venv `S-1-16-4096`） | **2288 passed / 113 skipped / 0 failed**（144.91s） |
| 全量（High，`C:\Windows\py.exe` + 绝对 `PYTHONPATH`） | **2373 passed / 28 skipped / 0 failed**（150.48s） |
| 前端 | 未跑（零前端改动，R63 的 490/0 仍适用） |
| e2e / docker build / npm build | 未跑（生产与前端零改动；CI 会跑 e2e 与 container-build） |

**总用例不变**：2401（Low `2288 + 113` = 2401；High `2373 + 28` = 2401）。

## 7. ⑤ CI 回写历史：方案与代价评估（按拍定不落地）

现状（R78）：历史随本机 e2e 入库（`tests/fixtures/e2e_retry_history/history.json`），
CI 只读 `check`，`permissions: contents: read`，趋势本身不判红。

要改成「CI 把每 push 的 e2e 结果写回仓库」，需要的组件与代价：

| 组件 | 说明 | 代价/风险 |
|---|---|---|
| 权限 | 写入 job 需要 `permissions: contents: write`（job 级最小化） | 仓库写入面变大；审计要多看一处 |
| 写回方式 A：直接 push 当前分支 | `git commit && git push` | SHA 变化会改变现有核对方式（「同一 SHA 只有 CI 一个 run」不再成立）；`[skip ci]` 会连带跳过其它 workflow；GITHUB_TOKEN 的 push 通常不触发新 workflow，但仓库会多出 bot commit |
| 写回方式 B：专用分支 + 聚合 | 推到 `e2e-history`，再由定时任务合到 main | 多一个合并/冲突面与一个定时 job；但 main 不被污染 |
| 写回方式 C：artifact + 本机聚合 | 不写仓库 | 回到现状，无需权限 |
| 幂等 | 同一 SHA 重跑（re-run）会重复 record | R78 已有「同一 `run_id` 覆盖」，但需要 CI 侧生成稳定的 `run_id`（`github.run_id`/`attempt`） |
| 并发 | backend / windows 两个 job 都可能产出 | 需要 `concurrency:` 或去重键 |
| 分支保护 | main 若禁止 bot 直推 | 必须走 PR，等于再触发一轮 CI |
| 语义 | 「轮」按导出轮推进（R59 拍定） | 改成「每 push 一轮」后，20 轮窗口在密集提交下几小时就滚完，趋势失去跨天含义 |

**结论：维持挂账、不实施。** 若将来要做，先满足三个前提：①「轮」的定义改为「每次 CI
运行」并登记台账；②历史放独立分支/独立仓库，不写 main；③趋势判据有可判阈值（当前
10 场景分辨率 10pp、不存在可判阈值，R78 §2）。

## 8. 未做与未验证的事（如实记录）

1. **没有改动既有 msys 对象的 ACL**：全程只读（open 读 SD / 试掩码）。合成对象是自建、
   自命名、关句柄即删的临时对象。
2. **没有实测 Medium 令牌**：本机只拿得到 Low / High 两极（`F:` → Low，`C:` → High）。
   Medium 预期可写（no-write-up 允许同级），但**未实测**。
3. **没有追查「F: 上的可执行文件为什么被降到 Low」**：是组策略 / 安全软件 / 沙箱驱动
   还是别的层，本轮只测现象。**这是下一轮真正的问题**——处方在别的机器是否成立取决于它。
4. **没有重跑 R70 那次的具体命令**，所以对「当时为什么判成 High 也失败」只给出最可能
   的解释（Low 解释器派生的 shell 不会升回 High），不作为结论。
5. **未重导快照**：`data/workflows/*/runs` 仍 **40 个** run，最新 `2026-10-28 08:34`，
   入库快照 `exported_at=2026-10-30T09:26:54`，未到期。
6. **未跑 e2e / docker build / npm run build**：生产与前端零改动（CI 会跑 e2e 与
   container-build）。
7. **本轮新增的两个临时探针脚本未入库**（`_r81_probe_acl.py` / `_r81_cross.py`，
   在仓库外的 `F:\DeterminFlow x2\`）：它们是 Windows 特有的 ctypes 取证脚本，
   要不要入库属于另一件事，本轮按「最小改动」没有提交。

## 9. 下一轮候选

1. **`F:` → Low 的策略来源**：`CreateProcess` 之后是谁把令牌降下去的（组策略 /
   安全软件 / 沙箱驱动）。决定本轮处方在别的机器上是否成立。
2. **Medium 令牌边界实测**：用 `CreateRestrictedToken` + `SetTokenInformation` 造
   Medium，验证「同级可写、低级不可写」这一层。
3. **CI 回写历史**：仍不推荐（见 §7）。
4. **重导快照 / `p=1.0` 真实数据**：继续挂账，每轮查一次 run 数（本轮仍 40 个）。
5. **探针脚本入库评估**：把 `_r81_probe_acl.py` 收进 `scripts/` 是否值得（Windows-only，
   无 CI 覆盖）。

其余维持现状：快照三条判据与保鲜全绿；大陆下载加速维持现状（R44 结论）；
快照保鲜容忍 7 天维持（R49 确认）；「轮」按导出轮推进（R59 拍定）。

## 10. 提交、推送与 CI 核对

两次提交（`fd75b6b` fix + `ec81ef7` docs，显式路径 add）后推送
`bff1f7d..ec81ef7`（一次成功；本轮 socks5 与直连同时可用，推的是全局
socks5 配置）。CI run **41271573395**（push，04:03:36 → 04:08:06，约 4m30s）
五 job 全 `success`：

| 项 | 实证（下载日志解码后逐字比对） |
|---|---|
| 五个 job | backend（04:03:39–04:06:13）/ windows-backend（04:03:39–04:08:06）/ frontend（04:03:38–04:04:51）/ container-config（04:03:38–04:03:43）/ container-build（04:03:39–04:04:16）全部 `success` |
| ubuntu | `2336 passed, 65 skipped, 1 warning in 109.09s` = **2401** |
| windows | `2372 passed, 29 skipped, 1 warning in 207.11s` = **2401** |
| 计数与 R80 逐字相同 | 本轮零新增用例（只改 1 条用例的名称与断言），`65` 与 `29` 的 skip 数也没变——文案改动不影响判据行为 |
| 快照判据 | backend 第 7–14 步（自检 + 真实快照七步：闸门 / 回归 / 逐 workflow 回归 / 提前量 / 样本量 / per-workflow 报告 / 失败率门槛）全 `success`；windows 第 7–11 步同 |
| e2e / metrics | `[e2e] 10/10 场景通过`；`[e2e-metrics] total=10 passed=10 failed=0 retried=0` |
| e2e 趋势（R78 步骤） | backend 第 **17** 步 `e2e retry trend (history, read-only)` `success` |
| 前端 / 容器 | 前端 8 块 TAP `# pass` 求和 **490 / fail 0**；`容器镜像冒烟全部通过: determinflow-core:ci`；`docker compose config -q` 成功 |
| Desktop Windows / macOS | 未触发（该 SHA 下只有 CI 一个 run） |

`$GITHUB_STEP_SUMMARY` 正文 API 不提供，与 R74 §7-2 / R80 §9 同一条限制；CI 上能核到的
是「这一批步骤都以 0 退出」。

