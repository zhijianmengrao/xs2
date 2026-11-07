# DeterminFlow (xs2) 交接报告 — Round 194（desktop flavor 词表五源闭包：W29）

> 单 profile。四轮连推（十八）第 2 轮：把 flavor 词表的五份文件钉成
> 恰等；生产代码零改动。变异 3/3。

## 1. 一句话结论

- **实测补面**：R192 §3 登记 flavor 词表四处（build_macos.py 的
  `choices` 与运行时集合、build_backend.py 的 `choices`、两份 workflow
  的 `matrix.flavor`）；开工实测补上第五处——
  `desktop/scripts/verify_bundle.py` 的 `--expected-flavor` choices
  （同 W18/W13/W25/R193 登记口径外实测补面先例）。五份文件六个解析点
  现均为 `{core, full}`。
- `tests/test_desktop_flavor_vocabulary.py` 新增 **W29a/W29b**：五处各
  恰一处、非空、值都在登记词表 `{core, full}` 内 + 两份 workflow 恰一个
  job 带 `flavor` 矩阵（W29a）、五源集合两两恰等（W29b，任一处加减值
  显式红）。总用例 3175 → **3179**（+2 钉测、+1 N3 本篇、+1 D1 因 R193
  §6 进入回填扫描区间）。
- 变异 **3/3**：build_backend.py choices 删 `full`（W29b 独红）、
  desktop-windows.yml 矩阵删 `full`（W29b 独红）、build_macos.py 删
  运行时集合守卫（W29a+W29b 双红：语料守卫 + 解析不到）。
- **回填**：R193 §6（run `42369789774` / bot `2d0b58b`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

flavor 是桌面构建的组合轴：两个构建脚本用它选捆绑面、两份 workflow 矩阵
用它展开 job、verify_bundle 用它核对候选包。五份文件里的词表今天都是
`{core, full}`，但这条边此前只有半个人判——W24 钉了 macOS 范围行与
macos 矩阵的词表（`⊆ {core, full}`），Windows 矩阵与三个构建脚本的
`choices`/运行时集合没有锚。加第三个 flavor（比如 `lite`）时五处会各自
漂移：脚本 `choices` 拒绝新值、Windows 矩阵不展开新组合、
`verify_bundle --expected-flavor` 对不上候选包——每一处都是「单边改了、
其余四源不知道」的静默分叉。

W29 的锚选在「词表 + 恰等」双层：先钉登记词表 `{core, full}`（扩充
flavor 先红词表，强制显式扩表并同步五源与 README 范围行，W24 同型），
再钉五源集合两两恰等（同批加减值时词表不动、恰等层显式红）。

## 3. 实现

### 3.1 生产代码

- 零改动（五源本来就同账，纯钉住）。

### 3.2 `tests/test_desktop_flavor_vocabulary.py`（W29a / W29b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W29a | 五处（build_macos choices / build_macos 运行时集合 / build_backend choices / verify_bundle choices / 两 workflow matrix）各恰一处、非空、值都在词表 {core, full}；两份 workflow 恰一个 job 带 flavor 矩阵 | 三个构建脚本 + 两份 desktop workflow |
| W29b | 五源集合两两恰等（以 build_macos choices 为参照） | 同上 |

实现要点：

- 脚本侧 `choices` 用 `` --(?:expected-)?flavor",\s*choices=\(([^)]*)\) ``
  提取（verify_bundle 的参数名是 `--expected-flavor`，与 `--flavor` 共用
  一条正则）；运行时集合用 `if flavor not in \{([^}]*)\}`。
- workflow 侧 `yaml.safe_load` 后扫 jobs：恰一个 job 的
  `strategy.matrix` 带 `flavor` 键（不写死 job 名，W26 同型）。
- 解析统一走「字符串集合」：`choices=("core", "full")`、
  `{"core", "full"}`、YAML 列表都拆成 `{core, full}` 再比，天然双向。

## 4. 验证

- 定向：`tests/test_desktop_flavor_vocabulary.py` 2 passed。
- 关联面：`test_desktop_macos_scope.py`（W24）、
  `test_desktop_workflow_name.py`（W28）、
  `test_desktop_windows_runner.py`（W26）、
  `test_desktop_readme_packaging.py`（W27）全绿；S2/S3/S5 在本提交前的
  红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3151 passed / 28 skipped / 0 failed**（3179 条，
  约 20m41s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **3/3**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  build_macos.py / build_backend.py / desktop-windows.yml 实测均为
  CRLF——交接记忆里「build_macos.py 是 LF」已过时，本轮实测翻正）：

| 变异 | 结果 |
|---|---|
| M1 build_backend.py `choices=("core", "full")` → `("core",)` | W29b 红（四源有 full、backend 没有）、W29a 绿（可解析、词表内） |
| M2 desktop-windows.yml 矩阵删 `- full` | W29b 红（macOS 有 full、Windows 没有）、W29a 绿 |
| M3 build_macos.py 删 `if flavor not in …` 两行 | W29a 红（运行时集合恰一处→0）、W29b 红（解析不到） |

## 5. 边界与遗留

- 只判五处词表——不判 README 范围行与叙述段（W24 射程：范围行点名矩阵
  全部 flavor + 否定式禁用）、不判矩阵展开行为与 job 数（CI 负责）、
  不判 flavor 语义（full 多捆绑官方插件快照）、不判 verify_bundle 其余
  参数与校验逻辑。
- 四轮连推（十八）第 3 轮 **R195 README R2 分发凭据同账（W30）**（已
  登记，R192 §3；真实不一致：README「只通过…注入」清单漏
  `R2_PUBLIC_BASE_URL`，R195 补清单并钉双向恰等）。
- `config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_flavor_vocabulary.py`（W29）、R194 文档、
  R193 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 批次行 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R194 一条）、
  `JUDGEMENT_LEDGER.md`（§10.66）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
