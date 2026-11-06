# DeterminFlow (xs2) 交接报告 — Round 173（Vite 开发代理端口：W17）

> 单 profile。四轮连推（十三）第 1 轮：`web/vite.config.ts` 的开发代理
> 端口第一次与后端 `WEB_PORT` 对账。生产代码零改动；W17 首跑即过，
> 变异 2/2。

## 1. 一句话结论

- **实测**：Vite 代理有两个目标——`/api` → `http://localhost:8020`、
  `/ws` → `ws://localhost:8020`；`src/config.py` 的 `WEB_PORT` 默认值
  是 8020。两个 target 同账。
- `tests/test_dev_proxy_port.py` 新增 **W17a/W17b**：代理目标恰 2 个、
  端口都 == config 默认值。总用例 3099 → **3103**（+2 钉测、+1 N3
  本篇、+1 D1 因 R172 进入扫描区间）。
- 变异 **2/2**：HTTP target 端口改 8021 / WS target 端口改 8021，
  W17b 独红。

## 2. 为什么是这一轮

R165 的 W13 把生产容器面的八个端口写入点钉住，但明确把 Vite 开发
代理留在射程外（本地开发链路，不是生产声明面）。这条边仍是第二份账：
后端改端口而代理没改，`npm run dev` 下所有 API 调用连接拒绝，且报错
只出现在浏览器控制台——CI 的 frontend job 只跑 lint/test/build，不会
起 dev server，所以没有任何现有闸门会咬住它。

W17 的锚选在「代理目标的 URL」：`/api` 与 `/ws` 是两条独立的代理链路，
端口必须与后端 config 默认值一致；协议（`http` / `ws`）是代理类型，
不参与端口账。

## 3. 实现

### 3.1 `tests/test_dev_proxy_port.py`（W17a / W17b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W17a | `web/vite.config.ts` 恰好解析出 2 个代理 target（HTTP + WS），config 的 `WEB_PORT` 默认值恰一处 | 代理 `target:` 行 + `_get_int_config("WEB_PORT", N)` |
| W17b | 两个 target 的端口都 == config 默认值；逐条报告第几个目标、写了什么 | 同上 |

实现要点：

- target 正则只认 `target: "<http|https|ws|wss>://localhost:<port>"`；
  `server.port: 5173`（前端开发服务器自己的端口）不匹配——它不是
  localhost 后端代理。
- 代理数量恰 2 是语料守卫，不是 allowlist：新增第三个代理需要同步
  改判据的计数，否则显式红。

## 4. 验证

- 定向：`tests/test_dev_proxy_port.py` 2 passed。
- 本机全量：**3075 passed / 28 skipped / 0 failed**（3103 条，约 10 分钟）。
- 变异 **2/2**：

| 变异 | 结果 |
|---|---|
| M1 `/api` target `http://localhost:8020`→8021 | W17b 红，W17a 绿 |
| M2 `/ws` target `ws://localhost:8020`→8021 | W17b 红，W17a 绿 |

两次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核。

## 5. 边界与遗留

- 只判代理端口：不判代理路径的路由语义、不判 `server.port` 5173、
  不判 `web/dist` 产物（构建面由 CI 的 `npm run build` 负责）。
- 四轮连推（十三）下一轮 **R174 Dockerfile node 基础镜像 ↔ engines
  （P9）**。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`7421281`** 推送后 run **42169319840**：**10 job 全
  `success`**（05:35:27→05:52:42 UTC，约 17m15s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42169319840`，bot 提交 `ca0793f`）。R174 回填。

## 7. 提交

- 改动：`tests/test_dev_proxy_port.py`、R173 文档、R172 §6 回填、
  `HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 + §4 H2/一行 +
  §6.1）、`PROJECT_INFO.md`（H2 + R173 一条）、
  `JUDGEMENT_LEDGER.md`（§10.45）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
