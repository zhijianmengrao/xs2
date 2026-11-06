# DeterminFlow (xs2) 交接报告 — Round 165（端口五源同账：Dockerfile / compose / config / README）

> 单 profile。四轮连推（十一）第 1 轮：Web 端口 ``8020`` 的八处写入点第一次
> 变成机判。生产代码零改动；W13 首跑即过，变异 7/7——与前三批同型，钉住的
> 是本来就对的账。

## 1. 一句话结论

- **实测**：端口在八个位置各写一次——`src/config.py` 的
  `_get_int_config("WEB_PORT", 8020)`（运行时默认值）、`run.py` 的
  `os.getenv("WEB_PORT", "8020")`（开发入口兜底值）、`.env.example` 的
  `WEB_PORT=8020`（环境模板）、`Dockerfile` 的 `EXPOSE 8020` /
  healthcheck `localhost:8020` / `CMD --bind 0.0.0.0:8020`、
  `docker-compose.yml` 的 `ports: "8020:8020"` 与 `WEB_PORT: "8020"`、
  两份 README 各两处 `localhost:8020`。八处当前全部等于 8020，但没有任何
  一条命令会把它们放在一起看。登记时只数到六处，本轮开工实测补上
  `run.py` 与 `.env.example` 两个直接运行时输入。
- 新增 `tests/test_port_sources.py` 两条 **W 系续判据**：W13a 语料守卫
  （八个写入点都能解析且形状唯一）、W13b 端口同账（以 config 默认值为唯一
  锚，其余每个端口字面量逐项相等，含 compose 的宿主机与容器两端）。
  总用例 3072 → **3076**（+2 钉测、+1 N3 本篇、+1 D1 因 R164 进入扫描区间）。
- 变异 **7/7**：config 默认值 / Dockerfile EXPOSE / compose WEB_PORT /
  README.en 端口 / Dockerfile CMD bind / run.py 兜底值 / .env.example，
  各自独红。

## 2. 为什么是这一轮

R44 的容器契约测试只钉 `CMD` 字符串本身（`--bind` 的形参名与 worker
class），不比较端口值与其他写入点；R153 的 M 系明确把徽章与 HTML 块留在
射程外；R157 的 P6/P7 只钉 Python / Node 展示面。于是「改端口」这件在
部署时最常发生的事，落在八个各写各的账上：

- 只改 compose 映射而不改 `EXPOSE`：`docker inspect` 的端口声明与
  实际监听不一致；
- 只改 config 默认值：容器内 `WEB_PORT` 环境变量仍把旧值钉回去；
- 只改 README：读者照着文档访问会得到连接拒绝；
- 只改 config 而漏了 `run.py` 的兜底值 / `.env.example`：开发入口与新
  环境模板仍起在旧端口。

W13 的锚选在「运行时真正执行出来的那个数」——config 的
`_get_int_config("WEB_PORT", 8020)`。其余五处都是围绕它的声明面，
逐项对账即可，不需要引入容器或起服务。

## 3. 实现

### 3.1 `tests/test_port_sources.py`（W13a / W13b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W13a | 八个写入点都能解析出端口且形状唯一：`EXPOSE` 恰一行、`--bind` 恰一处、healthcheck 恰一处、compose `ports` 恰一条 `H:C`、compose `WEB_PORT` 是纯数字串、config 默认值恰一处、`run.py` 兜底值恰一处、`.env.example` 恰一处、两份 README 各至少一处 `localhost:<port>` | 各源的语法形状 |
| W13b | W13a 解析出的每个端口（含 compose 宿主机端与容器端）== config 的 `WEB_PORT` 默认值；违规逐源报告 | `_get_int_config("WEB_PORT", N)` |

实现要点：

- compose 走 `yaml.safe_load` 读 `services.app`，不靠正则猜缩进；
  `ports` 必须恰一条 `"H:C"`，两端分别入账——`"8020:8021"` 这种
  「宿主机对、容器错」的映射两头都会报。
- Dockerfile 的 healthcheck 与 README 共用 `localhost:<port>` 正则，
  但分源计数：Dockerfile 要求恰一处（多一个检查 URL 会让锚不唯一），
  README 只要求至少一处（两份文档各有 Web UI / API 两行）。
- W13a 解析出的源数下限设为 11（config 1 + run.py 1 + .env.example 1 +
  Dockerfile 3 + compose 3 + README 2），任一面消失都会先在这里红，而不是
  让 W13b 静默少判。

## 4. 验证

- 定向：`tests/test_port_sources.py` 2 passed（0.09s）。
- 本机全量：**3048 passed / 28 skipped / 0 failed**（3076 条，约 10 分钟）。
- 变异 **7/7**：

| 变异 | 结果 |
|---|---|
| M1 config 默认值 8020→8021 | W13b 红，W13a 绿 |
| M2 Dockerfile `EXPOSE 8020`→8021 | W13b 红 |
| M3 compose `WEB_PORT "8020"`→"8021" | W13b 红 |
| M4 README.en 一处 `localhost:8020`→8021 | W13b 红 |
| M5 Dockerfile `CMD --bind 0.0.0.0:8020`→8021 | W13b 红 |
| M6 `run.py` 兜底值 `"8020"`→`"8021"` | W13b 红 |
| M7 `.env.example` `WEB_PORT=8020`→8021 | W13b 红 |

七次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判 Web 端口这一个数：不判编排设计是否合理、不判 README 的协议与
  主机名、不判 `web/` 前端的 Vite 开发代理端口（开发链路不在生产容器面）。
- 不判 `start_determinflow.sh` 的展示/诊断文案（启动器自带固定文案，不是
  服务端声明面）；healthcheck 仍只认 `localhost` 形式。
- 四轮连推（十一）下一轮 **R166 README 徽章序列双语同账（M5）**：
  两份 README 各 4 枚徽章，URL 序列逐项相等，alt 语言差异豁免。
- 生产默认值不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R166 回填。

## 7. 提交

- 改动：`tests/test_port_sources.py`、R165 文档、R164 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 + §6.1）、
  `PROJECT_INFO.md`（H2 + R165 一条）、`JUDGEMENT_LEDGER.md`（§10.37）。
  生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
