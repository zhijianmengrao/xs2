# DeterminFlow (xs2) 交接报告 — Round 176（README 命令引用面：V6）

> 单 profile。四轮连推（十三）第 4 轮（收官）：两份 README 的
> 「从源码运行 / Docker / 开发与验证」命令第一次与仓库文件对账。
> 生产代码零改动；V6 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：两份 README 的 fenced 命令各解析出 **4 处**文件引用（登记
  按 3 处/份）：`python run.py`、`.\\.venv\\Scripts\\python.exe run.py`
  （同一个 `run.py` 的 exe 变体）、`docker compose up --build`（默认
  编排文件）、`docker compose -f docker-compose.yml config -q`（显式
  编排文件）。共 8 处，`run.py` 与 `docker-compose.yml` 都在磁盘，
  默认编排文件到位。
- `tests/test_readme_commands.py` 新增 **V6a/V6b**：每份 README 至少
  3 处引用（实测 4）、合计至少 6 处（实测 8）；脚本 / 编排文件必须
  存在，不带 `-f` 的 compose 工程子命令要求默认编排文件。总用例
  3111 → **3115**（+2 钉测、+1 N3 本篇、+1 D1 因 R175 进入扫描区间）。
- 变异 **3/3**：README.md 的 `python run.py`→`main.py`、README.en.md
  的 `-f docker-compose.yml`→`-f compose.prod.yml`、删除 README.md
  两条 `run.py` 启动命令，V6b 两红、V6a 一红。
- **回填**：R175 §6（run `42180441935` / bot `9cf8ce6`）与索引 §1
  的写回 / 基线两行。

## 2. 为什么是这一轮

V3 已钉安装文档的 `pip install -r <file>` 与 Dockerfile 的 `COPY`；
V5 钉 CI / Dockerfile 的 npm 引用。README 的 `python <file>.py` 与
`docker compose [-f <file>]` 是最后一类「可复制执行、但没有判据」
的仓库文件引用：`run.py` 改名、编排文件改名后，README 的快速开始与
开发验证命令会直接失效，而 CI 只跑 pytest / npm / docker 构建，**从不
执行 README 命令**——没有任何现有闸门会咬住它。

V6 的锚选在「fenced 代码块里的命令」：正文散文与行内代码不是可复制
执行的命令，不在射程；命令只认 `python <file>.py` / `python.exe
<file>.py` 与 `docker compose` 两类，参数语义（端口、`--build` 等）
留给各自的判据与运行时。

R172 §3 登记时按每份 3 条计（`python run.py` / `docker compose up` /
`docker compose -f`），漏掉了 PowerShell 的 `python.exe` 变体；开工
实测为每份 4 条。这是候选制第四次在「开工实测」阶段修正判据自己的
覆盖面（W13 补 run.py/.env.example、M5 补 GitHub Actions badge、W18
补 Cargo.toml/Cargo.lock/插件锁、V6 补 python.exe 变体）。

## 3. 实现

### 3.1 `tests/test_readme_commands.py`（V6a / V6b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| V6a | 两份 README 的 fenced 命令各至少 3 处文件引用（实测 4），合计至少 6 处（实测 8） | fenced 块内的 `python <file>.py` / `docker compose …` |
| V6b | 脚本文件与 `-f` 编排文件必须存在；不带 `-f` 的工程子命令要求默认编排文件至少一个 | `run.py` / `docker-compose.yml` / 四个默认候选名 |

实现要点：

- 只扫 fenced 代码块（``` 围栏内的行），`#` 注释行跳过；围栏外的
  散文与行内代码不参与——这是「命令」与「叙述」的边界。
- python 引用认 `python` / `python3` / `python3.11` / `py`，可带
  `.exe` 后缀；`-m` 等旗标因不含 `.py` 自然不命中；脚本名限定 ASCII
  路径字符，反斜杠路径归一化后按仓库相对路径解析。
- compose 引用先找 `-f` / `--file`（空格或 `=` 两种写法）；没有显式
  文件时取第一个非旗标 token 作为子命令，只有工程子命令（up / down /
  config / build / start / stop / restart / ps / logs / run / exec /
  create / pull / push）才要求默认文件；`docker compose version` 之类
  不判。
- 默认编排文件按 docker 的查找顺序给四个候选：`compose.yaml`、
  `compose.yml`、`docker-compose.yaml`、`docker-compose.yml`；至少
  一个存在即通过——改文件名但保留标准名不会被误判。
- 语料下限沿用登记口径（每份 3、合计 6），实测 4/8 都高于下限：
  新增命令不需要改判据，删掉半份命令块则会显式红。新增 README 文档
  的下限默认 1，防止「只解析到 0 条」的静默空转。

## 4. 验证

- 定向：`tests/test_readme_commands.py` **2 passed**。
- 关联五文件（README 判据 / 脚本清单 / npm 引用 / 文档导航 / §6 回填）
  **201 passed**。
- 本机全量：**3087 passed / 28 skipped / 0 failed**（3115 条，约 11 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 README.md `python run.py`→`python main.py` | V6b 红，V6a 绿 |
| M2 README.en.md `-f docker-compose.yml`→`-f compose.prod.yml` | V6b 红，V6a 绿 |
| M3 删除 README.md 两条 `run.py` 启动命令 | V6a 红，V6b 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（README 工作树
是 CRLF，变异锚点带 `\r\n`）。

## 5. 边界与遗留

- 只扫两份 README 的 fenced 代码块：不判正文散文与行内代码里的命令
  提及，不判命令参数语义（端口 / `--build` / `-q` 等由各自判据与运行
  时负责）。
- 不判 `python -m <module>`（模块不是文件引用）；不判 `cp` /
  `Copy-Item` 的源文件引用——`.env.example` 由 W15 直接读取，配置
  示例文件的读取点另有测试；compose 子命令只认需要工程的集合。
- 不校验 `-f` 路径是否相对、是否落在仓库内；只做字面路径解析。
- 四轮连推（十三）R173–R176 四轮全部落地（W17 / P9 / W18 / V6）；
  R176 不是收口轮，下一批候选待登记。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`2e633a2`** 推送后 run **42189459705**：**10 job 全
  `success`**（08:41:15→08:59:30 UTC，约 18m15s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42189459705`，bot 提交 **`1730c1b`**）。R177 回填。

## 7. 提交

- 改动：`tests/test_readme_commands.py`（V6）、R176 文档、R175 §6
  回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行
  + §6.1）、`PROJECT_INFO.md`（H2 + R176 一条）、
  `JUDGEMENT_LEDGER.md`（§10.48）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
