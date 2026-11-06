# DeterminFlow (xs2) 交接报告 — Round 170（.env.example 环境模板：W15）

> 单 profile。四轮连推（十二）第 2 轮：用户复制成 `.env` 的环境模板
> 第一次与 `src/` 的读取点、代码兜底值对账。生产代码零改动；W15 首跑
> 即过，变异 3/3。

## 1. 一句话结论

- **实测**：`.env.example` 有 **9 个 active 键**——`WEB_HOST` /
  `WEB_PORT` / `LOG_LEVEL` / `SESSION_HISTORY_MAX_ENTRIES` /
  `DEEPSEEK_API_KEY`（空凭证）/ `MARKETPLACE_SKILL_FILE_TYPE_CHECK` /
  `MARKETPLACE_SKILL_ALLOWED_EXTENSIONS` /
  `DETERMINFLOW_WORKFLOW_EXECUTOR_MODE` / `..._COUNT`。9 个键在 `src/`
  全部有读取点；8 个非空默认值与代码兜底值相等（`0.0.0.0` / `8020` /
  `INFO` / `1000` / `true` / `.md` / `process` / `4`）。
- 新增 `tests/test_env_template.py` 两条 **W 系续判据**：W15a 读取点
  存在 + 键不重复；W15b 非空默认值同账，空值凭证只判读取点。总用例
  3089 → **3093**（+2 钉测、+1 N3 本篇、+1 D1 因 R169 进入扫描区间）。
- 变异 **3/3**：改 `WEB_HOST` 默认值 / 改 `LOG_LEVEL` 默认值 / 新增
  无人消费的键，W15a 与 W15b 各自独红。

## 2. 为什么是这一轮

R167 的 W14 已钉 compose 的 6 个 env，但 `.env.example` 是另一份独立
写入点：9 个键里有 4 个不在 compose 出现
（`SESSION_HISTORY_MAX_ENTRIES` / `DEEPSEEK_API_KEY` /
`MARKETPLACE_SKILL_FILE_TYPE_CHECK` / `MARKETPLACE_SKILL_ALLOWED_EXTENSIONS`）。
模板的两种静默漂移：

- 模板写了 `FOO=1` 但代码从不读 `FOO`：用户以为调了参数，实际什么都没
  发生；
- 模板默认值与代码兜底值不同：复制模板后行为与默认部署不一致。

W15 的锚选在「模板的 active 行」：注释掉的
`# DETERMINFLOW_DATA_DIR=…` 是文档示例，不参与；空值（
`DEEPSEEK_API_KEY=`）是凭证，语义是「由部署者填」，只判读取点。

## 3. 实现

### 3.1 `tests/test_env_template.py`（W15a / W15b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W15a | 每个 active 键在 `src/` 有读取点：裸名命中 `os.getenv` / `os.environ.get` / `_get_config_value` / `_get_int_config` / `_get_bool_config`；带 `DETERMINFLOW_` 前缀的键，后缀命中 `get_determinflow_env`。至少 9 个键，键不得重复 | 各读取函数的调用点 |
| W15b | 非空模板值 == 代码兜底值（布尔与大小写归一）；空值只判读取点。至少 8 个非空值的语料守卫 | 读取点第二个实参 |

实现要点：

- 模板按 `KEY=VALUE` 逐行解析，跳过空行与 `#` 注释；重复键显式红
  ——后写覆盖先写，模板本身就歧义。
- 兜底值从 `src/**/*.py` 静态提取，同一键必须恰好一处候选；带前缀的
  键先剥前缀再找读取点。
- `.env.example` 的 `DEEPSEEK_API_KEY=` 是唯一空值：读取点存在
  （`os.getenv("DEEPSEEK_API_KEY", "")`），默认值不比较。

## 4. 验证

- 定向：`tests/test_env_template.py` 2 passed（0.35s）。
- 本机全量：**3065 passed / 28 skipped / 0 failed**（3093 条，约 10 分钟）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 `.env.example` `WEB_HOST=0.0.0.0`→`127.0.0.1` | W15b 红，W15a 绿 |
| M2 `.env.example` `LOG_LEVEL=INFO`→`DEBUG` | W15b 红，W15a 绿 |
| M3 新增 `UNKNOWN_FLAG=1` | W15a 红（W15b 同时无锚） |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 active 行：注释掉的示例键不在射程；不判 `.env` 本身（不入库）、
  不判 `load_dotenv` 的运行时优先级（运维面）。
- W15a 的「至少 9 个键」是语料守卫，不是 allowlist：新增键只要有读取
  点且默认值同账即可通过。
- 四轮连推（十二）下一轮 **R171 compose 挂载点 ↔ config 目录（W16）**。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R171 回填。

## 7. 提交

- 改动：`tests/test_env_template.py`、R170 文档、R169 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R170 一条）、
  `JUDGEMENT_LEDGER.md`（§10.42）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
