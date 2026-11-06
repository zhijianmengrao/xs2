# DeterminFlow (xs2) 交接报告 — Round 167（compose 环境账 ↔ config 读取点：W14）

> 单 profile。四轮连推（十一）第 3 轮：`docker-compose.yml` 的 6 个环境
> 变量第一次与 `src/` 的读取点、代码兜底值放在一起对账。生产代码零改动；
> W14 首跑即过，变异 4/4。

## 1. 一句话结论

- **实测**：compose 给 app 设 6 个 env——裸名 `WEB_HOST` / `WEB_PORT` /
  `LOG_LEVEL` / `CODING_WORKSPACE_COPY_ON_CREATE`，带
  `DETERMINFLOW_` 前缀的 `WORKFLOW_EXECUTOR_MODE` /
  `WORKFLOW_EXECUTOR_COUNT`。6 个键在 `src/` 全部有读取点，4 个
  `${KEY:-default}` 的插值变量名都与键名一致，8 个静态默认值全部与代码
  兜底值相等（`0.0.0.0` / `8020` / `INFO` / `true` / `process` / `4`）。
- 新增 `tests/test_compose_environment.py` 两条 **W 系续判据**：W14a
  读取点存在（带前缀的键用后缀命中 `get_determinflow_env`）、W14b
  静态默认值同账（含插值变量名 == 键名）。总用例 3079 → **3083**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R166 进入扫描区间）。
- 变异 **4/4**：LOG_LEVEL 默认值 / executor count 默认值 / config mode
  兜底值 / 新增无读取点的 prefixed key，W14a 与 W14b 各自独红。

## 2. 为什么是这一轮

compose 是「部署时的第二份 config」：它把 6 个环境变量的静态默认值抄了
一遍，但没有任何命令验证这些键真的被代码读取、默认值真的与代码一致。
两类静默漂移：

- compose 写 `WEB_HOST: "127.0.0.1"` 而 config 兜底 `0.0.0.0`：容器只在
  回环上监听，宿主机映射的端口永远连不上；
- compose 设一个没人读的 `DETERMINFLOW_*`：用户以为调了参数，实际什么
  都没发生。

R165 的 W13 只钉端口值本身；`.env.example` 的模板面留给后续轮次。W14
的锚选在「代码里真正消费该键的那一行」——裸名走
`os.getenv` / `_get_config_value` 系列，带前缀走
`get_determinflow_env("<suffix>")`，默认值从同一行取。

## 3. 实现

### 3.1 `tests/test_compose_environment.py`（W14a / W14b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W14a | compose 的每个 env 都能在 `src/` 找到读取点：裸名命中 `os.getenv` / `os.environ.get` / `_get_config_value` / `_get_int_config` / `_get_bool_config`；带前缀的键，后缀命中 `get_determinflow_env("<suffix>")`。至少 6 个键的语料守卫 | 各读取函数的调用点 |
| W14b | `${KEY:-default}` 的插值变量名 == 键名；default / 字面量 == 代码兜底值（布尔与大小写归一） | 读取点第二个实参 |

实现要点：

- compose 走 `yaml.safe_load` 读 `services.app.environment`，值必须是
  字符串；当前 6 个全是字符串。
- 兜底值从 `src/**/*.py` 的调用实参静态提取，同一键必须恰好一处候选
  ——同一键多兜底值本身就是不同账，不猜哪一个是对的。
- 带前缀的键只认后缀命中：`DETERMINFLOW_WORKFLOW_EXECUTOR_MODE` 必须
  命中 `get_determinflow_env("WORKFLOW_EXECUTOR_MODE")`，而不是某个
  恰好同名的裸名读取点。
- 归一化只处理引号与布尔大小写；`INFO` 与 `info` 视为同一个值。

## 4. 验证

- 定向：`tests/test_compose_environment.py` 2 passed（0.28s）。
- 本机全量：**3055 passed / 28 skipped / 0 failed**（3083 条，约 10 分钟）。
- 变异 **4/4**：

| 变异 | 结果 |
|---|---|
| M1 compose `LOG_LEVEL` 默认 INFO→DEBUG | W14b 红，W14a 绿 |
| M2 compose executor count 默认 4→8 | W14b 红，W14a 绿 |
| M3 config mode 兜底 `process`→`inline` | W14b 红，W14a 绿 |
| M4 新增无读取点的 `DETERMINFLOW_NO_SUCH_READER` | W14a 红（W14b 同时无锚） |

四次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 compose 的 `services.app.environment` 静态账：不判
  `docker compose` 的运行时插值优先级（shell / `.env` 会覆盖默认值，
  那是运维面）、不判未在 compose 出现的其它 env、不判非字符串值。
- W14a 的「至少 6 个键」是语料守卫，不是 allowlist：新增 env 只要
  有读取点且默认值同账即可通过。
- 四轮连推（十一）下一轮 **R168 收口轮（R165–R168 四账）**：四账审计
  + 登记 R169–R172（先实测后登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R168 回填。

## 7. 提交

- 改动：`tests/test_compose_environment.py`、R167 文档、R166 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R167 一条）、
  `JUDGEMENT_LEDGER.md`（§10.39）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
