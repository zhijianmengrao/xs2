# DeterminFlow (xs2) 交接报告 — Round 177（环境检查脚本 ↔ 支持面下限：P10）

> 单 profile。四轮连推（十四）第 1 轮：`scripts/check_environment.py`
> 的支持面下限第一次与 requires-python / engines.node 对账。候选制第一次
> 在「开工实测」阶段抓到一处**真实不一致**（Node 18+ vs 22.12+），修后
> P10 2/2、变异 3/3。

## 1. 一句话结论

- **实测**：`pyproject.toml` 的 `requires-python = ">=3.11"`、
  `web/package.json` 的 `engines.node = ">=22.12.0"`；README 双语已是
  `22.12+`（P7），但 `CONTRIBUTING.md` 写 `Node.js 22+`，
  `scripts/check_environment.py` 的 Node 下限写 **`18+`**——Node 18/20
  会被判绿，随后 `npm run build` 才失败。Python 侧 3.11 已对齐。
- `tests/test_environment_check.py` 新增 **P10a/P10b**：四个下限源
  （requires-python / engines / CONTRIBUTING 两处 / 脚本两常量）可解析且
  形状唯一；两个常量 == 锚点；脚本对 22.11 告警、22.12 判绿、3.10 报错、
  3.11 判绿。总用例 3115 → **3119**（+2 钉测、+1 N3 本篇、+1 D1 因 R176
  进入扫描区间）。
- **修复**：`check_environment.py` 收敛为 `MIN_PYTHON = (3, 11)` /
  `MIN_NODE = (22, 12)`，Node 18+ → 22.12+；`CONTRIBUTING.md` 的
  `Node.js 22+` → `22.12+`。这是 P 系第一条带生产代码改动的判据。
- 变异 **3/3**：`MIN_NODE`→(18,0)、`MIN_PYTHON`→(3,10)、
  CONTRIBUTING→22.13+，P10b 各自红、P10a 保持绿。
- **回填**：R176 §6（run `42189459705` / bot `1730c1b`）与索引 §1
  的写回 / 基线两行。

## 2. 为什么是这一轮

R151 的 P3 把 Dockerfile / CI / classifiers / README 钉住；R155 补锁生成
头；R157 补徽章与 README 的 Node 下限。剩下的两处「用户读到的支持面」
仍是手抄：`CONTRIBUTING.md` 与 `scripts/check_environment.py`——后者被
`start_determinflow.sh` / `start_determinflow_v2.ps1` 直接调用，是用户
装环境时第一眼看到的判定。Node 18 已低于 Vite 构建要求，但脚本只给
「✅ Node.js v18」，把问题推迟到 `npm run build`；CONTRIBUTING 的
`22+` 也低于 engines 的 `22.12`。这两处不是「钉住本来就对的账」，而是
候选制第一次在实测阶段发现账本身错了。

P10 的锚选在「声明面的最小值」：requires-python 与 engines.node 的下限。
不引入运行时探测（那是探针，不是声明），也不重复 P4/P7 的 README 面。

## 3. 实现

### 3.1 `tests/test_environment_check.py`（P10a / P10b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| P10a | requires-python / engines.node / CONTRIBUTING 的 Python 与 Node 下限、脚本两个常量都能解析且形状唯一 | 四个下限源 |
| P10b | 两个常量 == 锚点；CONTRIBUTING 两处 == 锚点；22.11 告警 / 22.12 判绿 / 3.10 报错 / 3.11 判绿 | `MIN_PYTHON` / `MIN_NODE` |

实现要点：

- CONTRIBUTING 用 `Python X.Y+` 与 `Node.js X.Y+` 两把正则各取恰一处；
  少一处或写成 `22+`（无 minor）都会显式红。
- 行为边界用 `EnvironmentChecker` 的公开方法 + `subprocess.run` 桩，
  不启动真实 node；Python 侧替换模块的 `sys.version_info`，不碰解释器。
- 常量定义数 == 1：防止有人再写回一个裸 `18` 而测试只读常量。

### 3.2 `scripts/check_environment.py`

- 新增 `MIN_PYTHON = (3, 11)`、`MIN_NODE = (22, 12)`；
  `check_python_version` 用元组比较，`check_nodejs` 解析 major/minor 后
  与 `MIN_NODE` 比较，消息里的下限从常量生成。
- 旧的 `major < 18` 与 `推荐 18+` 一并删除。

### 3.3 `CONTRIBUTING.md`

- `Node.js 22+` → `Node.js 22.12+`，与 engines / README 同一下限。

## 4. 验证

- 定向：`tests/test_environment_check.py` 2 passed；关联三文件（环境检查
  / Python 支持面 / scripts 清单）16 passed。
- 本机全量：**3091 passed / 28 skipped / 0 failed**（3119 条，约
  10m22s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 `MIN_NODE` (22,12)→(18,0) | P10b 红，P10a 绿（Node 22.11 不再告警） |
| M2 `MIN_PYTHON` (3,11)→(3,10) | P10b 红，P10a 绿 |
| M3 CONTRIBUTING `22.12+`→`22.13+` | P10b 红，P10a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（脚本与
CONTRIBUTING 工作树都是 CRLF）。

## 5. 边界与遗留

- 只判「下限声明」：不判 Node/Python 的实际安装版本、不判 npm 下限、
  不判 `run.py` 的 Node 存在性检查（它是启动期提示，不是声明面）。
- 不重复 README 面（P4/P7）与 Dockerfile 的 python/node 基础镜像
  （P3/P9）；不判 CONTRIBUTING 的其它版本叙述。
- 本轮是 P 系首次带生产脚本改动：`check_environment.py` 是用户入口，
  不是核心运行时；核心默认值与退出码语义不变。
- 四轮连推（十四）下一轮 **R178 文档 npm 命令引用面（V7）**：
  README×2 + CONTRIBUTING 共 10 处 `npm run` / `npm test` 引用；
  R179 desktop 默认配置覆盖（W19）；R180 收口 + 登记。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`843b60b`** 推送后 run **42199142142**：**10 job 全
  `success`**（09:59:14→10:11:58 UTC，约 12m44s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42199142142`，bot 提交 **`ccd81a3`**）。R178 回填。

## 7. 提交

- 改动：`scripts/check_environment.py`（P10 常量 + Node 下限）、
  `CONTRIBUTING.md`（22.12+）、`tests/test_environment_check.py`（P10）、
  R177 文档、R176 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 +
  §3 标题/一行 + §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R177 一条）、
  `JUDGEMENT_LEDGER.md`（§10.49）。
- `config/skills_config.json` 不纳入（C1）。
