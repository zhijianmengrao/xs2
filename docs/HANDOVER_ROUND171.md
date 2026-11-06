# DeterminFlow (xs2) 交接报告 — Round 171（compose 挂载点 ↔ config 目录：W16）

> 单 profile。四轮连推（十二）第 3 轮：compose 的三个持久化卷第一次与
> 代码的目录默认值、容器 `WORKDIR` 对账。生产代码零改动；W16 首跑即过，
> 变异 3/3。

## 1. 一句话结论

- **实测**：compose 给 app 挂 3 个卷——`./data:/app/data`、
  `./logs:/app/logs`、`./config:/app/config`；`src/config.py` 的
  `DATA_DIR` / `LOGS_DIR` / `CONFIG_DIR` 默认值分别是
  `BASE_DIR/{data,logs,config}`；容器里代码在 `/app/src`，运行时
  `WORKDIR /app`——三个目标全部同名，宿主机源 basename 也同名。
- 新增 `tests/test_compose_mounts.py` 两条 **W 系续判据**：W16a 语料
  守卫（3 个卷 / 3 个目录 / 运行时 WORKDIR）、W16b 挂载点同账（目标
  集合 == `WORKDIR/<目录名>`、源 basename == 目录名）。总用例
  3093 → **3097**（+2 钉测、+1 N3 本篇、+1 D1 因 R170 进入扫描区间）。
- 变异 **3/3**：卷目标改名 / config 目录默认值改名 / 删一个卷，
  W16b 与 W16a 各自独红。

## 2. 为什么是这一轮

compose 的三个卷把容器内的持久化目录映射到宿主机；目录默认值在
`src/config.py` 里另写一遍。三种静默漂移：

- 卷挂到 `/app/dta`：容器把数据写进镜像层，`docker compose down` 即丢；
- 宿主机源与容器目录不同名（`./mydata:/app/data`）：运维在 `./data`
  里找不到数据；
- 少挂一个卷：该目录退回容器可写层，重启即清空。

R167 的 W14 只钉 env 的读取点与默认值，不涉及卷；W16 把「目录」这条
面补齐。

## 3. 实现

### 3.1 `tests/test_compose_mounts.py`（W16a / W16b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W16a | compose 恰 3 个卷、config 恰 3 个目录默认值、Dockerfile 有运行时 `WORKDIR`（最后一个） | 三个源的语法形状 |
| W16b | 容器目标集合 == `WORKDIR/<目录名>`；每个卷的宿主机源 basename == 目录名；缺卷显式红 | `DATA_DIR/LOGS_DIR/CONFIG_DIR` 的 `BASE_DIR / "<name>"` |

实现要点：

- config 目录用正则锚定 `Path(get_determinflow_env("X", str(BASE_DIR /
  "<name>")))` 的完整形状，不是只 grep 目录名——形状变了判据显式红。
- 运行时 `WORKDIR` 取 Dockerfile 的**最后一个**（`/app`），不是前端
  构建阶段的 `/app/web`。
- 卷只接受 `src:dst` 短语法；长语法（dict）会显式红，因为当前仓库
  没有使用，且 long-form 的 `source/target` 需要另一套解析。

## 4. 验证

- 定向：`tests/test_compose_mounts.py` 2 passed（0.08s）。
- 本机全量：**3069 passed / 28 skipped / 0 failed**（3097 条，约 10 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 `./data:/app/data`→`./data:/app/dta` | W16b 红，W16a 绿 |
| M2 config `BASE_DIR / "data"`→`"data2"` | W16b 红，W16a 绿 |
| M3 删除 `./config:/app/config` 卷 | W16a 红（W16b 同时缺目标） |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 app 服务的三个持久化目录：不判读写权限、不判 bind mount 与
  named volume 的类型选择、不判 `./data` 等源目录是否存在（compose
  会自动创建，CI 检出树里通常没有）；不判其它服务的卷。
- 四轮连推（十二）下一轮 **R172 收口轮（R169–R172 四账）**：四账审计
  + 登记 R173–R176（先实测后登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R172 回填。

## 7. 提交

- 改动：`tests/test_compose_mounts.py`、R171 文档、R170 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R171 一条）、
  `JUDGEMENT_LEDGER.md`（§10.43）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
