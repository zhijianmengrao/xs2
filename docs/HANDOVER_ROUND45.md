# DeterminFlow (xs2) 交接报告 — Round 45（三笔技术债收口：worker 弃用 / 孤儿脚本 / 闸门空转）

> 本轮定位：按用户选定的三项（R44 §8 候选 3、5 + R42 §8-1）做维护轮。
> 基线：`f73433d`（R44 收尾）→ 本轮 xs2 提交 1 个（见 §6），插件仓零提交。
> 用户同时确认：大陆下载加速**维持现状**（R44 §3.3 结论继续有效）、
> 循环节点与重试语义**继续挂着**（需后端 Core 配合）、收尾**做完就推并核对 CI**。

## 1. 为什么这一轮值得做

三项各自对应一个「已经知道、但一直在流血」的位置：

1. **`uvicorn.workers` 弃用告警**（R44 §5-2）：CI 的 `container-build` 每跑一次，
   gunicorn 导入 worker class 就打一条 `DeprecationWarning`。它不影响功能，但
   意味着生产启动路径挂在别人明确宣布要移除的入口上。
2. **孤儿脚本**（R44 §5-4）：`scripts/sync_gitee_release.py` 455 行 + 50 行测试，
   **零 CI 接线、零代码引用**，只在历轮 HANDOVER 里被提到。它存在的唯一效果是
   让后来者以为 Gitee 分发还是活的能力。
3. **闸门空转**（R42 §8-1）：`--fail-if-above` 在 R42 就已落地且测得很细，但
   R42 §8 自己也写了——CI 克隆不含 `data/workflows`（该目录被 gitignore），
   挂进 CI 只会得到「无 run 样本 → 诚实放行」，**每一步都绿，一个样本都没判**。

第 3 项是本轮唯一有设计含量的：把一条「诚实」的语义（无数据不等于 0% 也不等于
100%）放进自动化语境后，它会变成**静默失效**。修法不是取消诚实，而是让「没判到
东西」这个事实自己发出声音。

## 2. 落地内容

### 2.1 uvicorn-worker 迁移（`Dockerfile` + 两份锁 + `tests/test_dependency_locks.py`）

**取证先行**：迁移前先证明了「换包不改行为」这件事本身有证据，而不是靠印象。

| 取证 | 结论 |
|---|---|
| `uvicorn_worker/_workers.py` 与 `uvicorn/workers.py` 逐行 diff | **仅两处差异**：删掉了模块级 `warnings.warn(..., DeprecationWarning)`，两个 URL 注释从 `Kludex/uvicorn` 改成 `encode/uvicorn`，外加一个 `# pragma: no cover` |
| `uvicorn-worker` 0.4.0 的依赖声明 | `gunicorn>=21.0.0, uvicorn>=0.36.0`——本项目 `gunicorn==26.0.0` / `uvicorn==0.50.2` 都满足 |
| gunicorn 26.0.0 `util.load_class` 实现 | 对 `--worker-class` 字符串做 `importlib.import_module(点前段)` + `getattr(点后段)`，`uvicorn_worker.UvicornWorker` 完全符合该形式 |
| 本机 `import uvicorn_worker` | 失败于 `ModuleNotFoundError: No module named 'fcntl'` / `'pwd'` / `socket.AF_UNIX`——**与旧路径同一原因**（gunicorn 是 POSIX-only），不是迁移引入的问题 |

**改动**：`--worker-class`, `"uvicorn.workers.UvicornWorker"` → `"uvicorn_worker.UvicornWorker"`，
`requirements.txt` 追加 `uvicorn-worker==0.4.0`。

**锁文件用约束式重编译，避免整树漂移**：直接 `uv pip compile requirements.txt`
会把所有传递依赖升到当时最新（实测 starlette 1.3.1→1.10.0、pydantic 2.13.4→2.14.1、
jiter、orjson、httptools 等 40+ 项全变），那是另一件事，不该混进弃用治理。做法是
先用当前锁生成约束文件再编译：

```
uv pip compile requirements.txt -c <当前锁的 pin 列表> --python-version 3.11 \
  --universal --no-annotate --output-file requirements.lock
```

实测结果：**两份锁都只多一行 `uvicorn-worker==0.4.0`**（插在 `uvicorn` 之后），
传递依赖零变化。约束式编译复现性也验证过——用不加新包的 pin 列表重编译，与
现有锁**逐字节内容相同**（仅行尾差异）。

> 需要提醒的一点：约束式编译的头部注释会写成临时文件路径。本轮已手工把两处
> 头部恢复成规范命令（`uv pip compile requirements.txt ... --output-file requirements.lock`），
> 否则下一个人按注释复现会去读一个不存在的 Temp 路径。

**3 条新钉测**（`test_dependency_locks.py` 1 → 4）：

| 用例 | 钉什么 | 变异验证 |
|---|---|---|
| `test_dockerfile_uses_the_packaged_uvicorn_worker` | Dockerfile 用新路径，且**不再出现**旧路径 | 改回 `uvicorn.workers.UvicornWorker` → 红 ✓ |
| `test_every_worker_class_in_dockerfile_is_provided_by_the_lock` | 从 Dockerfile 正则取出 `--worker-class`，把模块名折算成分布包名（`uvicorn_worker`→`uvicorn-worker`），要求它在 `requirements.lock` 里；**这是「改了 Dockerfile 却漏刷锁」的直接闸门** | 从锁里删掉 `uvicorn-worker` → 红 ✓ |
| `test_uvicorn_worker_pin_is_identical_in_txt_and_both_locks` | `.txt` 与两份锁版本一致，且锁里的 `uvicorn` 主次版本 ≥ 0.36（uvicorn-worker 的硬要求） | 同上一并红 ✓ |

第 2 条值得单说：它不检查任何具体字符串，而是「Dockerfile 里声明要用的 worker
class，必须能被锁文件里的某个包提供」。以后谁换成第三个 worker 实现，这条会
自动跟着要新依赖，不需要改测试。

### 2.2 孤儿脚本清理（删 2 个文件）

删前复核引用面（含 `config/`、`.github/`、`src/`、`web/`、`desktop/`）：

- `scripts/sync_gitee_release.py`（455 行）：仅 `tests/test_gitee_sync_script.py` 导入；
- `tests/test_gitee_sync_script.py`（50 行）：2 条用例，测的是 Gitee manifest 改写与附件大小比较；
- 其余全部提及都在 `docs/HANDOVER_ROUND{29,31,32,44}.md` 与 `PROJECT_INFO.md` 的历史记录里。

`.github/workflows/` 里与 Gitee 相关的零命中（R42 已把 updater 的 Gitee 通道彻底移除，
这个脚本是那轮遗留的孤儿）。

**测试数影响**：−2（两条 Gitee 用例）。这是本轮唯一的净减，如实计入 §4 对账。

### 2.3 闸门空转防护 `--require-sample`（`scripts/provider_failure_profile.py` + 5 条测试）

R42 已有的 `--fail-if-above` 语义保持不变，新增一个**退出码维度**：

| 场景 | 退出码 | stderr 首行 |
|---|---|---|
| 有样本，未超阈 | **0** | `[gate] 总失败率 2.88% 未超出阈值 5.0%（243 次尝试）` |
| 有样本，超阈 | **1** | `[gate] 总失败率 2.88% 超出阈值 0.1%（243 次尝试）` |
| **无样本 + `--require-sample`** | **3** | `[gate] --require-sample: 一个 run 样本都没有，闸门未生效（退出码 3，检查 data/workflows 是否存在）` |
| 无样本，不加开关 | **0** | `[gate] 无 run 样本（attempts=0），跳过失败率闸门（阈值 5.0%）` |

设计取舍：

1. **3 与 1 分开**，因为它们是两件事。1 = 闸门判了，不合格；3 = **闸门根本没生效**。
   CI 日志里一眼能分开，不用读文案。沿用 `smoke_container.py` 的 `EXIT_ENV_MISSING=2`
   同一套「环境/配置问题不冒充产品缺陷」的思路。
2. **不加开关时行为完全不变**（R42 的「诚实放行」保持）。这条有独立测试
   `test_without_require_sample_empty_data_still_passes` 守着，防止有人把默认值改成严格模式
   而打破本机时间序列的既有用法。
3. **`--require-sample` 必须与 `--fail-if-above` 同用**，否则 argparse 直接拒（退出码 2）。
   单独用它对任何判定都没有影响，留着只会让人误以为它做了什么。
4. **超阈优先于空转**：`if triggered … elif require_sample and attempts==0`，所以真有
   不合格样本时得到的是 1（硬结论），不会被 3（软结论）顶替。有测试
   `test_require_sample_does_not_mask_a_real_breach` 钉死。

**5 条新测试**（`test_provider_failure_profile.py` 10 → 15）全部走注入的临时
`WORKFLOWS_DIR` + `monkeypatch sys.argv/stdout/stderr`，不碰真实 `data/workflows`（B27 纪律）。
变异验证：把 `elif args.require_sample and verdict["attempts"] == 0:` 改成 `elif False:`
（模拟「只加了参数没加行为」）→ `test_require_sample_fails_when_no_runs_exist` 红 ✓。

**四态真实数据实跑**（不是合成）：见上表，243 次尝试 / 7 失败 / 2.88%。

### 2.4 本轮**没有**做的事：把闸门挂进 CI

R42 §8-1 留的难题是「CI 无数据 → 空转」，本轮把「空转」变成**能被发现**（退出码 3），
但**没有**把闸门加进 `ci.yml` 的步骤里。理由如下，供下一轮决策：

- CI 克隆里 `data/workflows` 不存在（`data/**` 被 gitignore），挂上去必然是全红（一挂
  就 3），或者为了让它是绿而**不**加 `--require-sample`——那就回到静默空转。
- 真正生效需要「run 记录可得」。两条路：① 把 run 记录作为 artifact 从有数据的机器
  上传后聚合；② 在 `data/workflows` 下提交一份小的真实形状 fixture 并在 CI 上指向它
  （`DETERMINFLOW_DATA_DIR` 可覆盖，`src/config.py:21` 支持）。
- 两条路都涉及「往仓库里放运行数据」这个决策，超出本轮维护范围（本轮用户选的是
  「把闸门做成能用的」，不是「让闸门在 CI 上判真实数据」）。**退出码 3 已就位，接
  下来无论走哪条路都只需要加一步即可。**

## 3. 对 R44 记录的两处认知修正

如实记录，避免后人沿错的说法往下做：

1. **「`--fail-if-above` 待做」不成立**：R44 §8 把 R41 §9-1 列为候选，但 R42 已经把它
   实现完（含 10 条测试与真实数据四态实测）。本轮真正做的是它的**空转面**。
2. **「本机 `import uvicorn.workers` 直接失败只因缺 `fcntl`」不完整**：实测还缺
   `pwd` 与 `socket.AF_UNIX`，是 gunicorn 整体 POSIX-only 导致，与具体哪个 worker 模块无关。
   这条同时说明：**本机永远无法验证 worker class 能否真起**，只有 Linux 容器能——
   而 `container-build` job 正好提供这个面（它跑的是同一个 Dockerfile）。

## 4. 测试执行汇总（全部实际运行）

| 项 | 结果 |
|---|---|
| 定向：`test_dependency_locks.py` | **4 passed**（1 旧 + 3 新） |
| 定向：`test_provider_failure_profile.py` | **15 passed**（10 旧 + 5 新） |
| Low-IL 全量 | **1875 passed / 96 skipped / 0 failed**（103.11s） |
| High-IL 全量（权威） | **1960 passed / 11 skipped / 0 failed**（137.23s） |
| 前端 8 组 | **463 passed / 0 fail**（与 R44 一致，本轮零前端改动） |
| 前端 lint / build | 0 problems / ✓ 6.37s |
| 插件套件（双 CWD） | **98 passed ×2** |
| 插件相关（High-IL，`-k plugin`） | **308 passed / 0 skipped** |
| 插件相关（Low-IL，`-k plugin`） | 236 passed / 72 skipped（msys git 传输在 Low-IL 不可用，属已知平台面） |
| 存储名审计 | **[clean]** exit 0 |
| 失败率时间序列（第 4 点） | 23 runs / 243 尝试 / 7 失败 / **2.9%** |

**对账**：

- Low-IL：R44 1869 **− 2**（删 Gitee 用例）**+ 3**（锁钉测）**+ 5**（闸门测试）= **1875** ✓
- High-IL：R44 1954 **− 2 + 3 + 5** = **1960** ✓
- 总用例 R44 口径 1965 → **1971**（High passed+skipped：1960 + 11）

净增 +6 而不是 +8，正是因为 B 项删掉了 2 条。这条如实写出来，避免下一轮对账时
以为丢了用例。

## 5. 未做与未验证的事（如实记录）

1. **worker class 能否真起，本机测不了**：gunicorn 在 Windows 上因 `fcntl`/`pwd`/
   `socket.AF_UNIX` 无法导入（新旧路径同样失败）。权威证据只能来自 `container-build`
   job——它跑同一份 Dockerfile 并起容器打 `/api/system/status`。若本轮的 worker 类
   换错，该 job 会红在冒烟的第一步。
2. **GHA 层缓存会让首次验证打折**：`requirements.lock` 变了，`pip install` 那一层必然
   重建；但若只有 `Dockerfile` 的 CMD 变，`pip` 层会命中缓存。本轮两者都变，所以
   **这一推的 `container-build` 是真实冷/半冷构建**，缓存命中情况以 CI 日志为准。
3. **闸门仍未在 CI 上判真实数据**：见 §2.4，退出码 3 已就绪但未接线。
4. **`config/skills_config.json` 仍是未入库的运行时写入**（B23/R36 定性，与历轮一致）。
5. **循环节点与重试语义**（R41 §9-3）：用户本轮确认继续挂着，未动。
6. **大陆下载加速**：用户本轮确认维持现状，未动。

## 6. 本轮提交一览

| 仓库 | 提交 | 说明 |
|---|---|---|
| xs2 | 本文档提交 | `chore(deps)` uvicorn-worker 迁移 + 孤儿脚本清理 + `feat(scripts)` 闸门空转防护 + 交接文档 + PROJECT_INFO R45 条目 |

改动面（8 改 2 删）：

| 文件 | 变更 |
|---|---|
| `Dockerfile` | `--worker-class` 换 `uvicorn_worker.UvicornWorker` + 说明注释 |
| `requirements.txt` | `+ uvicorn-worker==0.4.0` |
| `requirements.lock` / `requirements-dev.lock` | 各 +1 行（约束式重编译，传递依赖零漂移） |
| `tests/test_dependency_locks.py` | +68 行 / 3 条钉测 |
| `scripts/provider_failure_profile.py` | +31 行（`--require-sample` + 退出码 3） |
| `tests/test_provider_failure_profile.py` | +67 行 / 5 条测试 |
| `scripts/sync_gitee_release.py` | **删除**（455 行） |
| `tests/test_gitee_sync_script.py` | **删除**（50 行） |

## 7. 遗留风险与需人工确认事项

1. **`--require-sample` 是给 CI 预留的口子，当前无自动使用者**：退出码 3 只有在有人
   把它挂上 CI（或本地脚本）时才生效。这不是缺陷，但下一轮若做 §2.4 的接线，需先决定
   「run 记录怎么进 CI」。
2. **uvicorn-worker 的下游演进**：0.4.0 依赖 `uvicorn>=0.36.0` 无上界。若将来 uvicorn
   主版本破坏 `uvicorn._compat.asyncio_run`（该包私有 API），worker 包会坏。锁定了
   uvicorn==0.50.2，所以暂时安全；升级 uvicorn 时需一并验证容器冒烟。
3. **删除 Gitee 脚本后若有外部脚本引用**：本仓库内零引用已复核，但仓库外的自动化
   （个人机器上的 cron 等）无法核实。若有人依赖过它，从 git 历史 `scripts/sync_gitee_release.py`
   可取回。
4. **High-IL 跑法必须用 Windows 反斜杠路径 + `py.exe` + PYTHONPATH**（PROJECT_INFO
   平台注意事项 9），本轮照做得到 1960/11/0。
5. **`F:\DeterminFlow x2` 路径含空格**：本轮未碰 Rust 构建，无影响。
6. **插件仓推进必须刷新本仓锁**（R42 纪律）：本轮插件仓零提交，`official-plugins.lock.json`
   无需刷新。

## 8. 下一轮候选

1. **闸门接进 CI**（中低工作量，R42 §8-1 / 本轮 §2.4）：两条路选一——artifact 聚合
   或提交真实形状 fixture + `DETERMINFLOW_DATA_DIR` 指向。退出码 3 已就位。
2. **`replace-desktop-assets.yml` 的 R2 发布步骤无门控**（R44 §3.2 的遗留面）：常规发版
   路径（`desktop-windows.yml`）的 R2 步骤有 `if: vars.R2_DISTRIBUTION_ENABLED == 'true'`
   门控，漏掉的是**手动触发**的 `replace-desktop-assets.yml`——它在第 114 行
   `Publish rebuild to R2 and switch stable manifest` 无条件执行，且 `--public-base-url`
   硬编码 `https://downloads.determinflow.com`。与 R44「大陆加速维持现状」并存会有歧义：
   只要有人手动跑这个 workflow，R2 就会被写入并切换 stable manifest。建议下轮二选一——
   给它补同样的门控，或在文档里明确它属于应急通道、不属于常规发版路径。
3. **CI 起服务跑 e2e**（R43 §2.3 选项 B）：仍需先解决「CI 无模型凭据」设计。
4. **循环节点与重试语义区分**（R41 §9-3）：需后端 Core 配合，用户已确认继续挂着。
5. **画像跨 run 对比视图的进一步演进**（R43 已落地基础版）。

其余：POSIX 真跑已由 CI 覆盖（R43 结论），大陆下载加速待真实痛点（R44 结论）。

## 9. 本轮未实际运行

- **未重启 8021 服务**：本轮后端改动只有脚本与测试（`provider_failure_profile.py` 是
  只读工具，Dockerfile 只影响镜像构建），服务进程不受影响，故未做活体走查。
- **未跑 `docker build`**：本机无 docker/wsl（R43/R44 复核仍不可用），真实构建证据
  交给 CI 的 `container-build`。
