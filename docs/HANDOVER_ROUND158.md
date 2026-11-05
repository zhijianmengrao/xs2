# DeterminFlow (xs2) 交接报告 — Round 158（安装文档引用面：README / CONTRIBUTING / Dockerfile 的锁文件引用可解析）

> 单 profile。四轮连推（九）第 2 轮（R156 §7 登记）。README 双语的
> 安装命令、CONTRIBUTING 的开发安装、Dockerfile 的镜像构建都按文件名
> 引用两份锁——R140 的 V1/V2 把 scripts/ 的引用面钉住了，这一面此前
> 无人判：锁文件一改名，所有安装命令同时失效。本轮钉成 **V3**。

## 1. 一句话结论

- `tests/test_scripts_inventory.py` 新增 **V3**（实测 R156 §7 登记）：
  安装文档（README.md / README.en.md / CONTRIBUTING.md）的
  `pip install -r <file>` 引用与 Dockerfile 的**单文件 COPY** 引用的
  仓库文件必须存在。实测 7 处 `-r` 引用 + 4 处单文件 COPY 全部可解析，
  **首跑即过**（首跑抓出的 `COPY --from=frontend-builder` 是旗标形
  COPY，判据改为跳过旗标/目录/通配后再判）。
- 总用例 3052 → **3055**（+1 V3、N3/D1 因本篇与 R157 回填 +2）；
  变异 **3/3**。生产代码零改动。

## 2. 开工复核（实测 2026-11-06）

| 引用面 | 处数 | 明细 |
|---|---|---|
| README.md `-r` | 3 | requirements.lock ×2、requirements-dev.lock ×1 |
| README.en.md `-r` | 3 | 同上（双语结构同账保证成对） |
| CONTRIBUTING.md `-r` | 1 | requirements-dev.lock |
| Dockerfile 单文件 COPY | 4 | web/package.json、requirements.lock、scripts/docker-entrypoint.sh、run.py |

Dockerfile 其余 COPY 是目录（`web/`、`src/`、`config/`）、通配
（`web/package-lock.json*`）与 `--from=frontend-builder` 旗标形——
不在文件判据射程：目录存在性由 container-build 真构建判、空通配是
合法形态、旗标的第二源在构建器阶段里。

## 3. 实现

- `INSTALL_REF_RX`：`-r\s+<path>`，路径字符集
  `[A-Za-z0-9_.-/]`；逐引用 `is_file()` 判存在。
- `_dockerfile_file_copies()`：`^COPY\s+(\S+)` 取首 token，跳过
  `--` 旗标、目录（尾 `/` 或 `.`/`./`）与通配（含 `*`），剩下的
  单文件逐个判存在。
- 语料守卫：每个安装文档的引用数有下限（README ≥2、CONTRIBUTING
  ≥1，Dockerfile 单文件 COPY ≥1）——引用面被整体删光时显式红，
  判据不静默空转。

## 4. 判据台账

- 新增 §10.30（V 系续：安装文档引用面，V3），接在 §10.29 之后；
  家族清单不变（仍是 V 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_scripts_inventory.py` **4 passed**（V1/V2a/V2b/V3）；
  相关回归 `test_readme_parity.py`（M1–M4，README 结构被动过）、
  `test_python_support_surface.py`（P1–P7）同跑。
- 本机全量：**3027 passed / 28 skipped / 0 failed**（3055 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 README.md `install -r requirements.lock` → `requirements-renamed.lock` | V3 红（文件不存在），V1/V2 绿 |
| M2 Dockerfile `COPY requirements.lock` → `requirements-core.lock` | V3 红（文件不存在），V1/V2 绿 |
| M3 CONTRIBUTING `install -r requirements-dev.lock` → `requirements-dev-renamed.lock` | V3 红（文件不存在），V1/V2 绿 |

字节快照还原后 sha256 逐字节相同，3/3 咬合。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R159 回填。

## 7. 边界与遗留

- V3 只判「引用的文件存在」，不判引用内容的正确性（版本对账由
  W 系、下限对账由 P 系负责）；README 代码块的其他文件路径
  （`git clone` 的 URL、`.venv` 的写法等）不在射程——它们不是
  「安装源」引用。
- 通配 COPY（`web/package-lock.json*`）在 npm ci 场景是合法空匹配，
  保持射程外；若未来出现第二个单文件 COPY，判据自动纳入。
- 下一轮 **R159 锁生成头自名（P8）**：生成头 `--output-file` ==
  文件自身名、`uv pip compile` 源文件存在（R156 §7 登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_scripts_inventory.py`（V3）、R158 文档、
  R157 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R158 一条）、
  `JUDGEMENT_LEDGER.md`（§10.30）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
