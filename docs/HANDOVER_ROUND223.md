# DeterminFlow (xs2) 交接报告 — Round 223（产物名前缀多源同账：W51）

> 单 profile。四轮连推（二十五）第 3 轮：把 `DeterminFlow_<version>_`
> 产物名前缀的 7 处出现（三份文件）钉成占位归一后逐字同账。生产代码
> 零改动，本轮无修复——前缀现同账。变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_product_prefix.py` 新增 **W51a/W51b**：前缀出现
  数逐份恰等（replace 3〔L77/L93/L94，含 .sig 派生名〕/ build_macos 1 /
  windows 3，合计 7）（W51a）；占位归一（``${version}`` →
  ``{version}``）后前缀集合 == {``DeterminFlow_{version}_``}——连接符
  ``_`` 也在账面（W51b）。总用例 3277 → **3281**（+2 钉测、+1 N3
  本篇、+1 D1 因 R222 §6 进入回填扫描区间）。
- 变异 **4/4**：replace 连接符 ``_`` → ``-`` / build_macos 连接符
  漂移（W51b 各自独红）、windows L185 删除 / 复制（W51a 各自独红）。
- **回填**：R222 §6（run `42446020006` / bot `db27258`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

桌面产物名的前缀 `DeterminFlow_<version>_` 在 7 处出现、三份文件：
replace-desktop-assets.yml 3（L77 `f'DeterminFlow_{version}_{suffix}'`
name 组合、L93 installer、L94 signature——后两处含 .sig 派生名）、
build_macos.py 1（L37 dmg 文件名）、desktop-windows.yml 3（L175/L176
bash `DeterminFlow_${version}_${suffix}`（含 .sha256）、L185
`DeterminFlow_${version}_x64-setup.exe`）。占位写法两种（bash
`${version}` / python `{version}`）。前缀漂移无人判：改产品名前缀
（改名/加品牌段）只改一处，其余产物名仍旧——发版资产命名分叉，W34
的后缀词表、W50 的安装包名都对不上。W34 管后缀、W50 管单个安装包
名，前缀的**多源账**第一次进射程。

W51 的锚选在「连接符进账」：首版只捕占位符（连接符在形状里但不在
账里），连接符漂移变异双绿——捕获组改成（占位符, 连接符）双组后，
`_` → `-` 的漂移才翻红（W43「变异全绿要查原因」教训的同型再现）。

## 3. 实现

### 3.1 生产代码

- 零改动（前缀现同账，纯钉住）。

### 3.2 `tests/test_desktop_product_prefix.py`（W51a / W51b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W51a | 前缀出现数逐份恰等（3/1/3，合计 7；形状容忍 `_`/`-` 连接符） | replace-desktop-assets.yml + build_macos.py + desktop-windows.yml |
| W51b | 占位归一后前缀集合 == {`DeterminFlow_{version}_`}（含连接符） | 同上 |

实现要点：

- 形状 `DeterminFlow_(\$\{version\}|\{version\})([_-])` 双捕获组：
  占位符与连接符都进账；变体（连接符改 `-`）进形状归 W51b 判值。
- 归一只做 `${name}` → `{name}`——两侧占位名都是 `version`。
- windows L114 的 `DeterminFlow_${version}${suffix}`（PS 重命名步，
  连接下划线在 $suffix 内）是另一种组合，不进本账（边界）。

## 4. 验证

- 定向：`tests/test_desktop_product_prefix.py` 2 passed（首跑修正
  replace 计数（漏 L94 派生名）与连接符入账后即过）；关联面
  `test_desktop_installer_name.py`（W50）、
  `test_desktop_product_suffixes.py`（W34）、
  `test_desktop_product_paths.py`（W44）全绿；S2/S3/S5 在本提交前的
  红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3253 passed / 28 skipped / 0 failed**（3281 条，
  约 11m40s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 与 build_macos.py 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 replace L77 连接符 `_` → `-` | W51b 红（前缀集合多一员）、W51a 绿 |
| M2 build_macos 连接符漂移 | W51b 红（前缀集合多一员）、W51a 绿 |
| M3 windows L185 删除 | W51a 红（3→2）、W51b 绿（剩余同前缀） |
| M4 windows L185 复制 | W51a 红（3→4）、W51b 绿 |

## 5. 边界与遗留

- 只判 `DeterminFlow_<version>_` 前缀的字面同账——不判后缀（W34
  词表已管）、不判 windows L114 的 `DeterminFlow_${version}${suffix}`
  变体（其连接下划线在 $suffix 内，是 PS 重命名步的另一种组合）、
  不判 `.sig`/`.sha256` 派生名的存在性（其前缀在本账内）、不判执行
  行为（CI 负责）。
- 四轮连推（二十五）收官 **R224 收口轮（R221–R224 四账）+ 登记
  R225–R228**（登记时先实测）。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_product_prefix.py`（W51）、R223 文档、
  R222 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R223 一条）、
  `JUDGEMENT_LEDGER.md`（§10.95）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
