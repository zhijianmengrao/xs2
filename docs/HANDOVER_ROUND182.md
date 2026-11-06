# DeterminFlow (xs2) 交接报告 — Round 182（desktop 管线命令引用面：V8）

> 单 profile。四轮连推（十五）第 2 轮：`desktop/README.md` 的构建命令
> 第一次进入 V 系判据。生产代码与文档命令零改动；V8 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：`desktop/README.md` 的 fenced 命令块解析出 **9 处**
  `python desktop/scripts/*.py`（R180 §3 按逐行口径登记 8 处；macOS 的
  `build_backend` 脚本名在 `\` 续行上，V8 合并续行后多看到 1 处）、
  **3 处** `npm run` / `npm test`（`build` / `test` / `build:macos`）、
  **2 处** `npm ci`（web / desktop）。全部可解析。
- `tests/test_desktop_pipeline_commands.py` 新增 **V8a/V8b**：语料下限
  （≥8 / ≥3 / ≥2）+ 脚本、npm script、锁文件逐项可解析。总用例
  3133 → **3137**（+2 钉测、+1 N3 本篇、+1 D1 因 R181 进入扫描区间）。
- 变异 **3/3**：README 的 `npm run build:macos`→`build:macosx` / 移走
  `desktop/scripts/generate_macos_icon.py` / 移走 `web/package-lock.json`，
  V8b 三红、V8a 绿。
- **回填**：R181 §6（run `42226610076` / bot `d34c177`）与索引 §1 的
  写回 / 基线两行。

## 2. 为什么是这一轮

`desktop/README.md` 是桌面 full 包唯一的人读构建说明——本地验证块和
macOS 额外验证块里的命令，是复现候选包的人唯一能照抄的入口。但：

- CI 只跑脚本本身（`desktop-macos.yml` 直接调用
  `install_macos_build_dependencies.py` / `build_backend.py` / …），
  从不执行 README 里的命令；
- V6 只扫 `README.md` / `README.en.md` 的 `python run.py` 与 compose；
- V7 只扫三份开发者文档的 npm 命令，并明确把 `desktop/README.md`
  留在射程外。

于是文档里的 9 处脚本引用、3 处 npm script、2 处锁文件是彻底的
「第二份账」：脚本改名、`package.json` 删 script、锁文件移动，读者
照文档执行才会失败。V8 把这条边钉住。

## 3. 实现

### 3.1 `tests/test_desktop_pipeline_commands.py`（V8a / V8b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| V8a | fenced 块至少 8 处 `python desktop/scripts/*.py`、至少 3 处 `npm run`/`npm test`、至少 2 处 `npm ci` | `desktop/README.md` |
| V8b | 脚本文件存在；npm script 命中该目录 `package.json` 的 `scripts`；`npm ci` 的工作目录有 `package-lock.json` | 磁盘 + `web/package.json` / `desktop/package.json` |

实现要点：

- **续行合并**：`\` 结尾的行并入下一条逻辑命令。macOS 的
  `build_backend.py` 与 `verify_bundle.py` 都是跨行命令；不合并时
  前者会漏掉 `python` 前缀，后者会只剩一个碎片。合并后脚本引用为
  9 处，V8a 仍用登记下限 8——口径修正不改变判据的失败面。
- **子壳 cd 语义**：`(cd web && …)` 与 `(cd desktop && …)` 的 `cd`
  只作用于本行子壳，不改变块的基准目录。第一版按 V7 的「块内顺序
  推进」写，会把 `(cd desktop …)` 解析成 `web/desktop`；实测抓到后
  改为子壳局部推进，`run.py` 之外的两处 npm 工作目录才落对。
- **npm script 解析**：`npm run build:macos` 的冒号是 script 名的一
  部分，正则按 `[A-Za-z0-9:_.-]+` 取值，不按空白截断。

### 3.2 生产代码与文档

- 零改动：`desktop/README.md`、`desktop/package.json`、
  `desktop/scripts/*.py`、两份 `package-lock.json` 都不动。

## 4. 验证

- 定向：`tests/test_desktop_pipeline_commands.py` 2 passed。
- 关联面：`test_scripts_inventory.py`、`test_doc_npm_commands.py`、
  `test_readme_commands.py`、`test_desktop_packaging.py` 全绿
  （46 passed / 1 skipped，icon 生成按平台跳过）。
- 本机全量：**3109 passed / 28 skipped / 0 failed**（3137 条，约 10m48s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 README `npm run build:macos`→`build:macosx` | V8b 红、V8a 绿 |
| M2 移走 `desktop/scripts/generate_macos_icon.py` | V8b 红、V8a 绿 |
| M3 移走 `web/package-lock.json` | V8b 红、V8a 绿 |

三次变异均用改名/`read_bytes` 还原并逐字节或存在性复核
（`desktop/README.md` 为 CRLF，替换按整行字节锚定）。

## 5. 边界与遗留

- 只扫 `desktop/README.md` 的 fenced 代码块：正文散文与行内代码不是
  可复制执行的命令；不判 `python -m <module>`、`cargo test` 与命令
  参数语义；不判其它 docs / README（V6/V7 已覆盖各自的面）。
- 不判 script 内部命令与参数（那是 script 自己的事）。
- 四轮连推（十五）下一轮 **R183 前端构建输出目录同账（W21）**：
  Vite 有效 `outDir` ↔ `run.py` 的 `dist_dir` ↔ `web_server` 的
  `web_dist`。
- 生产代码与文档命令零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_pipeline_commands.py`（V8）、R182 文档、
  R181 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R182 一条）、
  `JUDGEMENT_LEDGER.md`（§10.54）。生产代码与文档命令零改动。
- `config/skills_config.json` 不纳入（C1）。
