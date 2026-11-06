# DeterminFlow (xs2) 交接报告 — Round 181（macOS 最低版本同账：W20）

> 单 profile。四轮连推（十五）第 1 轮：Apple Silicon 候选包的最低系统
> 版本第一次做成六处同账。生产代码与配置零改动；W20 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：macOS 最低版本声明共 **6 处 / 4 个文件**，当前全部是
  `11.0`——`desktop/src-tauri/tauri.macos.conf.json` 的
  `minimumSystemVersion`、`desktop/scripts/verify_bundle.py` 的
  `MINIMUM_MACOS_VERSION`、`.github/workflows/desktop-macos.yml` 的
  `MACOSX_DEPLOYMENT_TARGET`、`desktop/README.md` 3 处（架构行
  `macOS 11.0+` 与两条构建命令的 `MACOSX_DEPLOYMENT_TARGET=11.0`）。
- `tests/test_macos_minimum_version.py` 新增 **W20a/W20b**：四源条数
  守卫（1/1/1/3，合计 6）+ 六值逐字相等。总用例 3129 → **3133**
  （+2 钉测、+1 N3 本篇、+1 D1 因 R180 进入扫描区间）。
- 变异 **3/3**：tauri 改 `12.0` / README 架构行改 `12.0+`（W20b 红、
  W20a 绿）、workflow 删 `MACOSX_DEPLOYMENT_TARGET` 行（W20a 红、
  W20b 绿）。
- **回填**：R180 §6（run `42213726312` / bot `032db07`）与索引 §1 的
  写回 / 基线两行。

## 2. 为什么是这一轮

macOS 候选包的「最低系统版本」是四处手抄的同一个数字，但没有一处由
另一处推导：

- `tauri.macos.conf.json` 的 `minimumSystemVersion` 决定 Tauri 写进
  `Info.plist` 的 `LSMinimumSystemVersion`；
- `verify_bundle.py` 的 `MINIMUM_MACOS_VERSION` 用它**逐字**校验
  `LSMinimumSystemVersion`，并拒绝 deployment target 高于它的 Mach-O；
- `desktop-macos.yml` 的 `MACOSX_DEPLOYMENT_TARGET` 决定编译期目标的
  下限，也就是二进制实际能跑在哪；
- `desktop/README.md` 把架构行和两条构建命令写给本地复现的人。

漏改 `verify_bundle` 时，产物和配置都对，验证脚本却会把正确 bundle
判失败；漏改 workflow 时，产物声明的下限与实际 Mach-O 目标分叉；漏改
README 时，文档失真。`desktop-macos` workflow 只在 `desktop/**` 变更时
触发，纯文档/测试改动不会让它运行——这条边没有任何现有闸门会咬住。

W20 的锚选在「同一个最低版本的所有声明点」：四源必须齐全，六值必须
逐字相等。不判最低版本的业务取值（是否该升到 12/13 是产品决定），也不
判 macOS SDK / runner 版本。

## 3. 实现

### 3.1 `tests/test_macos_minimum_version.py`（W20a / W20b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W20a | 四源各解析出登记条数（tauri / verify_bundle / workflow 各 1，README 恰 3），合计恰 6；全部是 `X.Y` 形状 | JSON 键 / 源码常量 / workflow env / README 3 处 |
| W20b | 六个值逐字相等 | 同上 |

实现要点：

- README 的 3 处分开解析：架构行 `macOS 11.0+` 恰一处、两条构建命令的
  `MACOSX_DEPLOYMENT_TARGET=11.0` 恰两处。任一条命令被删都会让 W20a
  红，而不是让同账判据静默少看一处。
- `tauri.macos.conf.json` 走 `json.loads` 取嵌套键，不按整文件正则——
  其它键的改动不会误伤；`verify_bundle.py` 的常量按行锚定，避免命中
  字符串里的同名文本。
- 逐字相等而不是数值比较：`11.0` 与 `11.00` 在字符串面上就是两份账，
  形状守卫先要求 `X.Y`，再要求完全相同。

### 3.2 生产代码与配置

- 零改动：`tauri.macos.conf.json`、`verify_bundle.py`、
  `desktop-macos.yml`、`desktop/README.md` 都不动。
- `desktop/scripts/install_macos_build_dependencies.py` 的
  `macosx_11_0_arm64` 是 wheel 平台标签（低版本 wheel 可装在高版本
  系统上），不属于最低版本声明面，本轮显式留在射程外。

## 4. 验证

- 定向：`tests/test_macos_minimum_version.py` 2 passed。
- 关联桌面面：`tests/test_desktop_packaging.py`、`test_desktop_macos_signing.py`、
  `test_desktop_defaults.py`、`test_scripts_inventory.py` 全绿。
- 本机全量：**3105 passed / 28 skipped / 0 failed**（3133 条，约 10m35s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 tauri `minimumSystemVersion` `11.0`→`12.0` | W20b 红、W20a 绿 |
| M2 README 架构行 `macOS 11.0+`→`macOS 12.0+` | W20b 红、W20a 绿 |
| M3 workflow 删除 `MACOSX_DEPLOYMENT_TARGET` 行 | W20a 红、W20b 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（
`tauri.macos.conf.json`、`desktop/README.md`、`desktop-macos.yml` 均为
CRLF）。

## 5. 边界与遗留

- 只判「最低版本声明」：不判取值该是多少、不判 `tauri.conf.json` 的
  其它键、不判 macOS SDK / runner 版本。
- 不判 `install_macos_build_dependencies.py` 的 wheel 平台标签与说明
  文字（二进制兼容标签，不需要随应用下限同步）。
- 四轮连推（十五）下一轮 **R182 desktop 管线命令引用面（V8）**：
  `desktop/README.md` 的 fenced 命令块里的 python 脚本、npm script 与
  锁文件必须可解析。
- 生产代码与配置零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_macos_minimum_version.py`（W20）、R181 文档、
  R180 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R181 一条）、
  `JUDGEMENT_LEDGER.md`（§10.53）。生产代码与配置零改动。
- `config/skills_config.json` 不纳入（C1）。
