# DeterminFlow (xs2) 交接报告 — Round 44（容器构建面补齐 + 大陆下载加速调研）

> 本轮定位：落地 R43 §9-1 / §2.3 选项 A——把 R43 调研暴露的**最大单项风险**
> 「容器镜像从未被构建验证」补上；同时按用户指定完成「大陆下载加速」的
> **方案调研**（只出结论不实施），并按用户决定**不推送**（R43 起积压提交保留）。
> 基线：`1bb2880`（R43）→ 本轮 xs2 提交 1 个（见 §6），插件仓零提交。

## 1. 为什么这一轮值得做

R43 §2.2 缺口 1 的原话是「`container-config` job 只做配置语法校验，**从未
`docker build`**」。这意味着 `Dockerfile` 里三段真实构建逻辑在 CI 上零覆盖：

1. `node:22-alpine` 阶段跑 `npm ci` + `npm run build`；
2. `python:3.12-slim` 阶段跑 `pip install -r requirements.lock`；
3. `CMD gunicorn src.web_server:app --worker-class uvicorn.workers.UvicornWorker` 能否真起。

这三段任何一段坏掉，用户 `docker compose up --build` 都直接失败，而 CI 全绿。
本轮把它变成会红的 job。

## 2. 落地内容

### 2.1 CI：新增 `container-build` job（`.github/workflows/ci.yml`）

| 步骤 | 作用 |
|---|---|
| `docker/setup-buildx-action@v3` | 起 buildx builder |
| `docker/build-push-action@v6`（`load: true`） | 真构建，tag `determinflow-core:ci`，GHA 层缓存（`type=gha,scope=container-build`） |
| `python scripts/smoke_container.py --image determinflow-core:ci --skip-build` | 起容器做行为断言 |
| `actions/upload-artifact@v4`（`if: failure()`） | 失败时上传 `container-logs/`，否则 CI 只有一行 exit 1 |

**与 `container-config` 并存而非合并**：语法校验是秒级快反馈，构建是分钟级，
合并会让「compose 拼错」也要等构建跑完。测试钉死了两者都在。

**为什么用 buildx + `load` 而不是 `docker build`**：GHA 层缓存能把 `npm ci` 与
`pip install` 这两层命中率拉到接近 100%，首次之后的增量代价主要是源码层。
`load: true` 是「构建结果能被本地 daemon 运行」的前提，漏了它会去 registry
pull 一个同名镜像（不存在则失败）。

**为什么不给冒烟步骤 `pip install`**：脚本只用标准库（`urllib`/`subprocess`），
测试里有一条静态断言禁止出现 `requests`/`httpx`/`docker` 导入——否则这一步
会因为装依赖失败而掩盖镜像问题。

### 2.2 冒烟脚本（`scripts/smoke_container.py`，新增）

判定与执行分离：**纯函数**可在无 docker 的机器上单测，**交互层**只在 CI 真跑。

纯函数（全部直接单测，含反例）：

| 函数 | 断言什么 |
|---|---|
| `evaluate_status` | `workflow_executor` 为 `process` 模式、`configured/member/ready/reachable` 全为 4、`available=true`、`degraded=false`；且 `main_session`/`main_sessions`/`total_sessions` 字段存在 |
| `evaluate_index_html` | `/` 返回的 HTML 有 `#root`、有 DeterminFlow 标题、引用 `/assets/*.js`；**且不含 `/src/main.tsx`**（后者是「构建阶段没执行，StaticFiles 回落到源码目录」的特征） |
| `find_entrypoint_evidence` | 容器日志含 `Session 启动前裁剪完成`——证明 `docker-entrypoint.sh` 先裁剪再 `exec` |
| `evaluate_layout` | 双向断言：`run.py`/`src/web_server.py`/`src/core/defaults/skills`/entrypoint/`web/dist/index.html` **应存在**；`tests/`、`pytest.ini`、`config/models_config.json` **不应存在** |
| `parse_probe_output` | 解析镜像内 `path=0/1` 探测输出；**未出现在输出里的路径不算 False**（否则「探测失败」会被误判成合规） |

交互层顺序（每一步失败都 dump 容器日志）：

```
buildx 构建 → docker run -d（固定 4 个 Executor、WEB_PORT=8020）
→ 轮询 /api/system/status 直到契约成立（不是「200 就行」，池成员可能仍在 starting）
→ GET / 验前端产物 → GET /docs 验 HEALTHCHECK 路径
→ docker inspect 等 HEALTHCHECK 报 healthy（这才是「镜像的 HEALTHCHECK 指令真能用」）
→ docker logs 验 entrypoint 证据
→ docker rm -f → 对镜像本体做一次性 --rm 布局探测
```

### 2.3 活体验证暴露并改掉的一处设计缺陷

最初的实现是**在运行中的容器里** `docker exec test -e` 逐路径探测布局。本地
用临时目录模拟镜像环境起真服务时发现：`ModelManager` 在
`config/models_config.json` 缺失时会从 `config/models_config.example.json`
**生成**该文件（`model_manager.py` 的 `_create_default_config`）。也就是说启动
后这个路径必然存在，而断言期望它「不应存在」——**这条断言恒假红**。

修法：布局探测改成对**镜像本体**跑一次性 `--rm` 容器（`--entrypoint /bin/sh`），
在容器删除之后执行。测试里有一条顺序断言钉死「布局探测必须在 teardown 之后」。

这条缺陷只有真起一次服务才会暴露，纯静态读代码发现不了——与 R43 §2 用同样
方式推翻了「POSIX 未覆盖」的表述是同一种取证方式。

### 2.4 本地验证做了什么（本机无 docker）

本机 `docker` / `wsl` 均不可用（R43 实测，本轮复核仍不可用），因此**真实构建
无法本地验证**，改为两条替代取证：

1. **模拟镜像环境起真服务**：临时目录只放 `config/*`（不含 `models_config.json`，
   模拟 `.dockerignore` 的效果）+ 空 `data/`、`logs/`，用
   `DETERMINFLOW_DATA_DIR/LOGS_DIR/CONFIG_DIR` 指向它跑 `run.py`，端口 18733。
   结果：`/api/system/status` **200**、`mode=process`、`ready 4/4`、
   `reachable 4`、`degraded=false`、`available=true`，
   `evaluate_status` **零违规**；`GET /` 200 且 `evaluate_index_html` 零违规
   （实际产物 `/assets/index-Di62suE6.js`）；`GET /docs` 200。
   → 说明 CI 首跑时这几个核心断言不会因为「干净数据目录」而失败。
2. **判据的反例与真实数据双向校准**：同一个 `evaluate_status` 在真实 8021
   （`4/4 ready`）上零违规；`evaluate_index_html` 在 `web/dist/index.html`
   上零违规、在开发态 `web/index.html` 上正确报出两条违规
   （指向 `/src/main.tsx` + 未引用 `/assets/`）。
3. **entrypoint 证据链**：`python -m src.agent.session_retention` 在干净目录
   独立跑通并输出 `Session 启动前裁剪完成: scanned=0 retained=0 pruned=0 ...`，
   退出码 0——证明 CI 里 `docker logs` 应当能捞到这行。
4. **无 docker 降级**：`python scripts/smoke_container.py --image x --skip-build`
   → 输出环境提示并 **exit 2**（不是 1）。

过程中还排除了两条伪线索：首次模拟用了 `DATA_DIR`/`LOGS_DIR`（缺
`DETERMINFLOW_` 前缀）导致环境变量被忽略、实际跑在真仓库数据目录上，与运行中
的 8021 抢 Executor 租约而失败——这属于我的验证脚本问题，不是产品缺陷。
另有一次 `provision_core_skills` 在 Windows 临时目录上抛 `PermissionError`
（`os.fsync` 打开的 `.tmp` 句柄），独立复现三次只有首次成功、后两次正常，
属本机环境偶发，Linux 容器内不复现，未做改动。

### 2.5 测试（`tests/test_container_build_contract.py`，新增 17 条）

| 分组 | 用例 | 断言 |
|---|---|---|
| CI 真的构建 | `test_ci_builds_the_image_and_smokes_it` | 存在 build-push 步骤且 `load: true`、`file: ./Dockerfile`；冒烟步骤在构建之后、消费同一 tag、带 `--skip-build` |
| | `test_container_build_job_keeps_existing_container_config_job` | 两个 job 并存，`container-config` 仍跑 `compose config -q` |
| | `test_container_build_uploads_logs_on_failure` | 上传步骤 `if: failure()`，且冒烟带 `--logs-dir container-logs` |
| 判据自身可用 | `test_status_contract_accepts_healthy_payload` | 健康载荷零违规 |
| | `test_status_contract_rejects_degraded_pool` | `ready_count=3` 被报出 |
| | `test_status_contract_rejects_inline_mode_and_unavailable_pool` | inline 模式、`available=false` 且 reason 透传 |
| | `test_status_contract_reports_missing_sections` | 类型错误 + 缺字段都报且不抛异常 |
| | `test_index_html_contract_requires_built_assets` | 构建产物通过；开发态两处违规；`find_frontend_asset` 提取正确 |
| | `test_index_html_contract_rejects_missing_mount_point` | 缺 `#root` 被报出 |
| | `test_entrypoint_evidence_requires_the_real_log_line` | 正反例 |
| | `test_layout_contract_is_two_sided` | 合规零违规；`/app/tests` 泄漏被报；漏探测被报 |
| | `test_layout_probe_output_parsing_ignores_noise` | 噪声行被忽略、未探测路径不被当成 False |
| | `test_credentials_probe_runs_against_image_not_running_container` | 布局探测在 teardown 之后（钉死 §2.3 的修法） |
| 不脱钩 | `test_smoke_contract_matches_dockerfile` | 端口 `8020`、`/docs`、`COPY` 行、entrypoint 证据行与 `session_retention.py` 源码一致 |
| | `test_smoke_layout_expects_no_credentials_baked_in` | `.dockerignore` 的真实内容支撑「不烘焙凭据」断言 |
| | `test_smoke_env_matches_compose_service_settings` | `CONTAINER_ENV` 与 compose 默认值逐项一致 |
| | `test_smoke_script_is_stdlib_only_so_ci_needs_no_pip` | 无第三方 import；`EXIT_ENV_MISSING == 2` |

「不脱钩」这一组是本轮的关键设计：冒烟判据里写死了端口、路径、日志文案，
如果哪天有人改了 `Dockerfile` 的 `CMD --bind` 或把 entrypoint 换成别的启动
方式，这些测试会先红，而不是等到 CI 真跑构建时才发现判据在空转。

## 3. 大陆下载加速方案调研（用户指定：只出结论不实施）

### 3.1 结论先行

**当前不建议做，触发条件未成立；若触发，走 R28 §6 选项 B（Cloudflare R2 +
自有域名），工作量约 1–2h，不需要改代码逻辑。**

### 3.2 现状取证（本轮读码与文档核对，未发起网络压测）

| 项 | 现状 |
|---|---|
| 更新源 | **单源 GitHub**：`tauri.conf.json` 的 `plugins.updater.endpoints` 与 `desktop/src-tauri/src/updater.rs` 的 `GITHUB_UPDATE_ENDPOINT` 都是 `https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json` |
| 为什么必须单源 | `updater.rs` 注释钉死：tauri updater 在 `check()` 阶段**不验签**（只在下载时验签），保留上游端点会让上游更高版本号（实测 1.1.1 / v1.0.10）穿透成「发现新版本」误报且下载必败。R42 已把 R2/Gitee 残留彻底移除 |
| 已备但未启用的通道 | `desktop/scripts/publish_r2_release.py`（S3 兼容上传 + `latest.json` 生成 + 缓存头策略）与 `desktop-windows.yml` 里 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'` 的发布步骤**都已就位**，缺的只是仓库 vars/secrets 与域名 |
| 孤儿残留 | `scripts/sync_gitee_release.py` + `tests/test_gitee_sync_script.py` 仍在仓库里，但**零 CI 接线、零代码引用**（只在历轮 HANDOVER 里被提到）。属可清理的技术债，不属于加速方案本身 |
| 实测速度 | 33MB 安装器**直连 ~30KB/s 且会中断一次**（R31/R32 记录，本轮未复测——用户量级与网络环境未变，无新证据） |

### 3.3 三个选项与推荐

| 选项 | 覆盖 | 代价 | 风险 |
|---|---|---|---|
| **维持现状（推荐）** | 更新器可用，只是大陆直连慢 | 0 | 低。更新失败会弹错误，但验签链完整不会装错东西 |
| **B：R2 + 自有域名** | 大陆可达性最优；`publish_r2_release.py` 现成，vars 开关即启用 | 域名（约 ¥50+/年）+ Cloudflare 账号 + DNS + 4 个 vars/secrets，1–2h | 中低。多一处运维面与密钥管理；**必须同步改两处端点**（tauri.conf + updater.rs），否则又回到多源穿透问题 |
| **A：GitHub Releases 自托管** | 已在用，无新增 | 0 | —— |

**触发条件**：真实用户报告「下载慢/下载失败」成为阻塞（而非我们推测它会）。
理由：本轮没有任何新证据表明痛点已成立；而 B 方案一旦启用就必须同时维护
「两处端点 + 4 个凭据 + 域名续费」，在用户量级未起来时是净负担。

**若决定实施，实施清单（下轮可直接执行）**：
1. 仓库 vars：`R2_DISTRIBUTION_ENABLED=true`、`R2_BUCKET`、`R2_ENDPOINT_URL`；
   secrets：`R2_ACCESS_KEY_ID`、`R2_SECRET_ACCESS_KEY`。
2. `tauri.conf.json` 的 `endpoints` 与 `updater.rs` 的 `GITHUB_UPDATE_ENDPOINT`
   **同时**改成 `https://<自有域名>/desktop/stable/latest.json`。
3. `scripts/verify_release.py` 的 manifest 端点校验地址同步参数化（现在硬编码
   GitHub `releases/latest/download/latest.json`）。
4. 发一个 tag 验证：`latest.json` 三项（version/url/signature）+ 端到端 minisign 验签。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_container_build_contract.py` | **17 passed**（新增） |
| Low-IL 全量 | **1869 passed / 96 skipped / 0 failed**（98.98s） |
| High-IL 全量（权威） | **1954 passed / 11 skipped / 0 failed**（131.71s） |
| 前端 8 组 | **463 passed / 0 fail**（与 R43 一致，零净增） |
| 前端 lint / build | 0 problems / ✓ 5.59s |
| 插件套件（双 CWD） | **98 passed ×2** |
| 存储名审计 | **[clean]** exit 0 |

对账：Low-IL 1852 + 17 = **1869** ✓；High-IL 1937 + 17 = **1954** ✓。
总用例 R43 口径 1948 → **1965**（High passed+skipped：1954+11）。

## 5. 未做与未验证的事（如实记录）

1. **真实 `docker build` 未在本地执行过**——本机无 docker/wsl。CI 的
   `container-build` job 是本轮代码的**首次真实构建**，首次推送可能暴露
   Dockerfile 层面的问题（例如 `requirements.lock` 在 python:3.12-slim 上的
   可安装性、alpine 上的前端构建）。我已做的事前核对：`web/package.json` 与
   `package-lock.json` 的 dependencies/devDependencies **完全同步**（`npm ci`
   不会因锁不同步失败）；`requirements.lock` 中无 `Requires-Python` 排除 3.12
   的包；平台相关项只有 `colorama`/`pywin32`（win32）与 `uvloop`（非 win32），
   在 Linux 侧会正确安装/跳过。
2. **`uvicorn.workers.UvicornWorker` 的弃用告警**：本机 `uvicorn 0.50.2` 导入
   `uvicorn.workers` 会发 `DeprecationWarning`（建议改用 `uvicorn-worker` 包）。
   Windows 上导入直接失败只因缺 `fcntl`（POSIX-only），Linux 容器里可用。
   **这是既有 `Dockerfile` 的选择，本轮未改**——改它属于依赖决策，应单开一轮
   评估（`--worker-class` 换成 `uvicorn_worker.UvicornWorker` 需新增依赖并刷新锁）。
3. **macOS 签名流水线未核对**（R43 §2.3 选项 C）：本轮按用户选择只做 A，
   未去读 `desktop-macos.yml` 的 CI 记录。缺口 3 仍开着。
4. **`scripts/sync_gitee_release.py` 孤儿**（§3.2）：本轮只记录，未删除。删它
   要连 `tests/test_gitee_sync_script.py` 一起处理，属独立清理项。

## 6. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | 本文档提交 | `feat(ci)` 容器构建冒烟 job + 冒烟脚本 + 17 条契约测试 + 交接文档 + PROJECT_INFO R44 条目 |

未入库：`config/skills_config.json`（社区插件运行时合法写入，B23/R36 定性，
与历轮一致）。

**未推送**（用户明确要求本轮继续攒）：R43 的 `1bb2880` 与本轮提交均积压在本地，
`origin/main` 落后 2 个提交，CI 未触发。

## 7. 遗留风险与需人工确认事项

1. **`container-build` 首次真跑可能红**：见 §5-1。~~若红，先看
   `container-logs` artifact 与构建日志分段定位（前端层 / pip 层 / 启动层）。~~
   **已由 run 40641422351 验证：首跑全绿，本项风险解除**（实测见 §9.2）。
2. **CI 时长增加**：~~GHA 层缓存命中后增量约 1–3 分钟（首次约 8–12 分钟）。
   若认为代价过高，可把 job 改成 `pull_request` 仅路径触发……建议先观察几轮
   真实耗时再决定。~~ **已实测收口**：首跑 1m56s（冷构建）、二次推送 56s
   （18 层全 `CACHED`），比预估更轻。用户已决定保持**每推必验**，不改路径
   触发——实测成本支持这个选择（§9.2.1）。
3. **`EXIT_ENV_MISSING=2` 的语义只在脚本内**：CI 步骤没有对退出码做分支处理，
   若 runner 侧 docker 异常，job 会以 exit 2 失败并上传日志。这是有意的
   （runner 缺 docker 应当修 runner，而不是静默跳过）。
4. **冒烟绑定的端口是宿主侧随机空闲端口**（`_free_port()`），容器内固定 8020。
   若 CI runner 的端口分配与 8020 冲突不会发生（容器内端口只在容器网络里）。
5. **插件仓推进必须刷新本仓锁**（R42 纪律）：本轮插件仓零提交，
   `official-plugins.lock.json` 无需刷新。
6. **High-IL 跑法必须用 Windows 反斜杠路径 + `py.exe` + PYTHONPATH**
   （PROJECT_INFO 平台注意事项 9），本轮照做得到 1954/11/0。
7. **`F:\DeterminFlow x2` 路径含空格**：本轮未碰 Rust 构建，无影响。

## 8. 下一轮候选

1. ~~**推送 + CI 全量核对**（需用户授权）：届时 `container-build` 首次真跑。~~
   **已完成**（用户授权当轮执行）：run 40641422351 五 job 全绿，详见 §9。
2. ~~**核对 `desktop-macos.yml` 历史结果**（R43 §2.3 选项 C，低成本）。~~
   **已完成**：v1.0.2 tag run 40202145251 双矩阵 success，缺口不成立，见 §9.3。
3. **`uvicorn.workers` 弃用治理**（§5-2）：评估换 `uvicorn-worker` 包，
   顺带刷新 `requirements.lock` 与 Dockerfile 的 `--worker-class`。
4. **循环节点与重试语义区分**（R41 §9-3，需后端 Core 配合）。
5. **孤儿脚本清理**（§5-4）：`sync_gitee_release.py` + 对应测试。
6. **CI 起服务跑 e2e**（R43 §2.3 选项 B）：仍需先解决「CI 无模型凭据」设计。

## 9. 补记：推送与 CI 全量核对（用户授权后当轮执行）

本轮提交与 R43 的 `1bb2880` 一并推送（`a6e4927..2b5bba6`，`origin/main` 已同步，
积压清零），触发 CI 首跑。结果如下。

### 9.1 CI 五 job 全绿

`CI` run **40641422351**（`2b5bba6`）：

| job | 结果 | 数据 |
|---|---|---|
| `backend`（ubuntu-24.04） | success | **1901 passed / 64 skipped**（76.44s） |
| `windows-backend` | success | **1936 passed / 29 skipped**（186.83s） |
| `frontend` | success | **463 passed / 0 fail**，`vite build` ✓ 5.81s |
| `container-config` | success | `docker compose config -q` |
| **`container-build`** | **success（首次真跑）** | **1m56s**，构建 + 冒烟四断言全过 |

`Desktop Windows` run **40641422247**（同 sha）success。

四口径总数**均为 1965**：ubuntu 1901+64、windows 1936+29、本机 Low-IL 1869+96、
High-IL 1954+11 —— 与 §4 双基线逐项对齐，无未解释差异。

`windows-backend` 29 条 skip 与本机 High-IL 11 条的 18 条差额已逐条核对：
humanware e2e **17**（CI 无 8021 服务，诚实 skip）+ `test_plugin_longpath` **1**
（runner 已启用 `LongPathsEnabled`，`MAX_PATH` 用例按设计 skip）。其余 11 条与
High-IL 完全一致（macOS 签名 6 + icns 1 + Unix 进程组/进程树 2 + POSIX fcntl 2）。

### 9.2 `container-build` 首次真构建的实测细节（§5-1 的风险已解除）

§5-1 记录的「首次真跑可能红」**没有发生**。日志取证：

1. **真构建，零缓存命中**：`npm ci` 实装 497 包 8.6s；`pip install -r
   requirements.lock` 15.0s，且正确忽略 win32-only 的 `colorama`/`pywin32`
   （`Ignoring ... markers 'sys_platform == "win32"' don't match`）；`exporting
   layers` 3.9s。全文无一处 `CACHED`。
2. **冒烟四断言全过**（`--skip-build` 复用刚构建的 tag）：
   - `status 契约成立: mode=process ready=4/4 degraded=False`
   - `内置前端产物可用: /assets/index-C5eX4JWL.js`
   - `镜像 HEALTHCHECK=healthy`
   - `entrypoint 先裁剪再 exec 已验证`
   - `镜像布局契约成立（不含 tests 与预先烘焙的凭据）`
3. **失败上传步骤按预期 skipped**（job 成功时不触发）。

**一处与 §2.1 预估不符需修正认知**：GHA 层缓存**首跑为空**——日志有
`importing cache manifest from gha:...` 但无任何一层命中，所以首次是完整的
冷构建（含 apt、npm、pip 全量），耗时 1m56s 而非预估的 8–12 分钟。

### 9.2.1 第二次推送的缓存命中实测（增量耗时的权威数据）

紧接着的文档提交 `5a7b38b` 触发了 `CI` run **40648992383**，这是缓存是否
真的起作用的第一次检验，结果如下：

| 项 | 首跑（40641422351） | 二次（40648992383） |
|---|---|---|
| `container-build` 耗时 | 1m56s | **56s** |
| `CACHED` 层数 | 0 | **18**（含 `npm ci` 与 `pip install` 两层） |
| 冒烟断言 | 四断言全过 | 四断言全过，产物名一致 `/assets/index-C5eX4JWL.js` |

**结论：层缓存按设计生效，且增量代价比 §2.1 预估的 1–3 分钟更低（实测 56s）。**
即源码层只重跑了 `COPY` 之后的少数步骤。这条同时说明「每推必验」的成本可接受
（§7-2 的顾虑不成立，无需改路径触发）。

### 9.3 顺带闭合 R43 缺口 3：macOS 签名流水线（§8-2）

`desktop-macos.yml` 的 workflow runs 接口返回 `total_count=0`，起初像「从未
跑过」。实际原因是它是 **`workflow_call` 型可复用工作流**（触发条件仅
`workflow_dispatch` / `workflow_call` / 碰 `desktop/**` 的 PR），结果并入调用方
run 而不单独计数——零记录是正常表现，不是故障。

真实证据在 `desktop-windows.yml` 的 `build-macos` job（`if: github.ref_type ==
'tag'`，`uses: ./.github/workflows/desktop-macos.yml`）。v1.0.2 tag run
**40202145251** 中：

| job | 结果 | 耗时 |
|---|---|---|
| `build-macos / Build Apple Silicon core candidate` | success | 7m05s |
| `build-macos / Build Apple Silicon full candidate` | success | 6m32s |
| `Build core NSIS installer` | success | 11m39s |
| `Build full NSIS installer` | success | 9m21s |
| `Publish GitHub Release` | success | 13s |

两个矩阵都真跑了 `verify_bundle.py --verify-macos-signatures
--verify-dmg-container --forbid-updater-artifacts`、装载 DMG 后
`codesign --verify --deep --strict`、以及安装副本里的 backend 冒烟。

**结论：R43 缺口 3「macOS 签名流水线未核对」不成立——它在最近一次发版上是
真机跑通的真签名产物。** 该缺口可从风险清单移除（PROJECT_INFO 已同步）。

### 9.4 本轮仍未做的事

- 真实 `docker build` 只跑到 CI，本机依旧无 docker/wsl（§5-1 不变，但已不再是
  未验证项——CI 已提供权威证据）。
- `uvicorn.workers` 弃用告警（§5-2）未处理，仍在 CI 日志中可见。
- 孤儿脚本（§5-4）未删。
- 失败率时间序列本轮仍无新 run（纯核对轮）。

