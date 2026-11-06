# DeterminFlow (xs2) 交接报告 — Round 185（macOS bundle identifier 同账：W22）

> 单 profile。四轮连推（十六）第 1 轮：桌面应用的 bundle identifier
> 第一次做成六处同账。生产代码与配置零改动；W22 首跑即过，变异 3/3。

## 1. 一句话结论

- **实测**：`io.determinflow.desktop` 共 **6 处 / 3 个文件**——
  `desktop/src-tauri/tauri.conf.json` 的 `identifier` 1 处、
  `desktop/scripts/verify_bundle.py` 2 处（`CFBundleIdentifier` 比较 +
  失败错误消息）、`desktop/README.md` 3 处（`%LOCALAPPDATA%` 与
  `Application Support` 两条数据路径 + 数据目录树根）。
- `tests/test_macos_bundle_identifier.py` 新增 **W22a/W22b**：三源条数
  守卫（1 / 2 / 3，合计 6）+ README 三种上下文锚 + 反向域名形状 +
  六值逐字相等。总用例 3143 → **3147**（+2 钉测、+1 N3 本篇、+1 D1
  因 R184 进入扫描区间）。
- 变异 **3/3**：tauri identifier 改 `io.determinflow.probe`（W22b 红）、
  README 目录树根改 `io.determinflow.probe/`（W22a+W22b 红）、
  verify_bundle 比较值改 `io.determinflow.probe`（W22b 红）。
- **回填**：R184 §6（run `42240337924` / bot `f49958c`）与索引 §1 的
  写回 / 基线两行。

## 2. 为什么是这一轮

bundle identifier 同时决定三件事：Tauri 写进 `Info.plist` 的
`CFBundleIdentifier`（`verify_bundle.py` 对它做逐字校验）、两个平台的
数据目录名（Windows `%LOCALAPPDATA%\<id>`、macOS
`~/Library/Application Support/<id>`）、以及 README 教用户去哪找数据。
四处手抄（tauri / verify 比较值 / verify 消息 / README ×3）没有一处由
另一处推导：

- 漏改 `verify_bundle` 的比较值：产物和配置都对，验证脚本把正确 bundle
  判失败；漏改错误消息：报错文本与实际要求分叉。
- 漏改 README：用户照文档找数据目录，目录名已经变了。
- tests 里的 `CFBundleIdentifier` 是 fixture 取值（跟产品走），不是
  声明面，不进同账。

W22 的锚选在「同一个 identifier 的所有声明点」：三源条数 1 / 2 / 3、
README 三处各落在登记上下文（Windows 路径 / macOS 路径 / 目录树根）、
全部反向域名形状、六值逐字相等。不判 productName、不判数据目录的实际
创建行为。

## 3. 实现

### 3.1 `tests/test_macos_bundle_identifier.py`（W22a / W22b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W22a | 三源条数 1 / 2 / 3、合计恰 6；README 的 Windows 路径 / macOS 路径 / 目录树根三种上下文各恰一处；全部反向域名形状（≥2 段小写标签） | JSON 键 / 源码两条正则 / README 三条正则 |
| W22b | 六个值逐字相等 | 同上 |

实现要点：

- verify_bundle 的两处分开锚定（比较 `!= "…"` 与错误消息
  `必须是 <id>:`），改其一即红，不会互相遮蔽。
- README 用 `io.` 前缀的反向域名 token 扫描（与 tauri 值无关的独立
  口径）：改 identifier 全家时判据仍能对账；删掉任一处时条数守卫先红。
- 目录树根按整行 `<id>/` 锚定，必须与 token 口径取到同一个值。

### 3.2 生产代码与配置

- 零改动：`tauri.conf.json`、`verify_bundle.py`、`desktop/README.md`
  都不动。

## 4. 验证

- 定向：`tests/test_macos_bundle_identifier.py` 2 passed。
- 关联面：`test_desktop_packaging.py`、`test_macos_minimum_version.py`、
  `test_desktop_pipeline_commands.py`、`test_desktop_defaults.py` 全绿。
- 本机全量：**3119 passed / 28 skipped / 0 failed**（3147 条，约 10m56s）。
- 变异 **3/3**：

| 变异 | 结果 |
|---|---|
| M1 tauri `identifier` → `io.determinflow.probe` | W22b 红、W22a 绿 |
| M2 README 目录树根 → `io.determinflow.probe/` | W22a 红、W22b 红 |
| M3 verify_bundle 比较值 → `io.determinflow.probe` | W22b 红、W22a 绿 |

三次变异均 `read_bytes`/`write_bytes` 还原并逐字节复核（三个文件均为
CRLF）。

## 5. 边界与遗留

- 只判 identifier 声明：不判 productName、不判数据目录落盘行为、不判
  updater URL；tests fixture 与其它文档不在射程。
- 不判「identifier 是否该改」——反向域名形状只守字面账，业务取值是
  产品决定。
- 四轮连推（十六）下一轮 **R186 desktop README DMG 产物路径同账
  （W23）**：`desktop/README.md` 硬编码的
  `DeterminFlow_1.0.2_aarch64.dmg` ↔ `build_macos.py` 产物模板 ↔
  tauri 版本。
- 生产代码与配置零改动；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 **`ed750cd`** 推送后 run **42246512628**：**10 job 全
  `success`**（15:48:44→16:05:26 UTC，约 16m42s）；写回 **第 80 条**
  （满窗滚动：追加后裁剪最旧一条，history 仍 80 条；
  `ci-42246512628`，bot 提交 **`74aa21d`**）。R186 回填。

## 7. 提交

- 改动：`tests/test_macos_bundle_identifier.py`（W22）、R185 文档、
  R184 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/一行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R185 一条）、
  `JUDGEMENT_LEDGER.md`（§10.57）。生产代码与配置零改动。
- `config/skills_config.json` 不纳入（C1）。
