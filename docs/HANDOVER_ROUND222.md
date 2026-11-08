# DeterminFlow (xs2) 交接报告 — Round 222（核心安装包名两 workflow 同账：W50）

> 单 profile。四轮连推（二十五）第 2 轮：把核心（core）NSIS 安装包
> 名的两种占位写法（windows bash 字面 ↔ replace python 组合）钉成
> 占位归一后逐字恰等。生产代码零改动，本轮无修复——安装包名现同账。
> 变异 4/4。

## 1. 一句话结论

- `tests/test_desktop_installer_name.py` 新增 **W50a/W50b**：windows
  的 installer 赋值与 replace 的组合行各恰一处（值无关形状）（W50a）；
  占位归一（``${version}`` → ``{version}``）后两份安装包名逐字恰等
  （W50b）。总用例 3273 → **3277**（+2 钉测、+1 N3 本篇、+1 D1 因
  R221 §6 进入回填扫描区间）。
- 变异 **4/4**：windows 后缀漂移 / replace 后缀漂移（W50b 各自独红）、
  windows 赋值删除 / 复制（W50a 各自独红）。
- **回填**：R221 §6（run `42443606070` / bot `b23a0e1`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

核心（core）NSIS 安装包名有两份账：desktop-windows.yml 的 bash 字面
（`installer="release-assets/DeterminFlow_${version}_x64-setup.exe"`，
L185，喂给 create_update_manifest 的 `--installer`）与
replace-desktop-assets.yml 的 python 组合（`installer=assets /
f'DeterminFlow_{version}_x64-setup.exe'`，L93，补发版资产时的定位）。
占位写法不同（bash `${version}` vs python `{version}`），安装包名是
同一份账：一边改名/改后缀而另一边没跟——create_update_manifest 按
新名读到安装包、replace 按旧名找（或反之），发版补资产/清单生成找
不到文件。W34 管后缀**词表**，安装包名的**跨 workflow 字面**第一次
进射程。

W50 的锚选在「占位归一后恰等」：bash 的 `${version}` 归一成 python
的 `{version}` 再比——两种写法的语义差（shell 展开 vs f-string）不进
射程，账面要求归一后逐字相同。

## 3. 实现

### 3.1 生产代码

- 零改动（安装包名现同账，纯钉住）。

### 3.2 `tests/test_desktop_installer_name.py`（W50a / W50b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W50a | windows installer 赋值恰一处（值无关形状）；replace 组合行恰一处 | desktop-windows.yml + replace-desktop-assets.yml |
| W50b | 占位归一后两份安装包名逐字恰等（两侧都在才判，缺失归 W50a） | 同上 |

实现要点：

- windows 侧提取 `installer="(release-assets/[^"]+)"`（值无关），
  剥目录前缀后比文件名；`release-assets/` 目录前缀的账归 W37。
- 归一只做 `${name}` → `{name}`——两侧占位名都是 `version`，改名
  也翻红。

## 4. 验证

- 定向：`tests/test_desktop_installer_name.py` 2 passed（首跑即过）；
  关联面 `test_desktop_product_suffixes.py`（W34）、
  `test_desktop_gh_release_uploads.py`（W37）、
  `test_desktop_forbid_bundle_path.py`（W49）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3249 passed / 28 skipped / 0 failed**（3277 条，
  约 12m19s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均 `read_bytes`/`write_bytes` 还原并逐字节复核；
  两份 workflow 均为 CRLF）：

| 变异 | 结果 |
|---|---|
| M1 windows 后缀 `x64-setup.exe` → `x64-installer.exe` | W50b 红（名不等）、W50a 绿 |
| M2 replace 后缀漂移 | W50b 红（名不等）、W50a 绿 |
| M3 windows 赋值删除 | W50a 红（1→0）、W50b 绿（缺失归 W50a） |
| M4 windows 赋值复制一份 | W50a 红（1→2）、W50b 绿 |

## 5. 边界与遗留

- 只判核心安装包名的字面同账——不判 full 安装包名（windows 的 full
  走 `${suffix}` 变量，W34 的词表已管）、不判 `.sig`/`.sha256` 派生名
  （由安装包名推出）、不判 `release-assets/` 目录前缀（W37 已管）、
  不判执行行为（CI 负责）。
- 四轮连推（二十五）续 **R223 产物名前缀多源同账（W51）**、
  **R224 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_desktop_installer_name.py`（W50）、R222 文档、
  R221 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题 + §4
  H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R222 一条）、
  `JUDGEMENT_LEDGER.md`（§10.94）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
