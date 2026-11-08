# DeterminFlow (xs2) 交接报告 — Round 225（community-updates 当前正式版同账：W52）

> 单 profile。四轮连推（二十六）第 1 轮：把 docs/community-updates.md
> 的「当前正式版」与 desktop/release-notes/ 目录的最高版本文件钉成
> 同账（按数字段比较）。生产代码零改动，本轮无修复——最高版本现同账。
> 变异 4/4。

## 1. 一句话结论

- `tests/test_community_current_version.py` 新增 **W52a/W52b**：
  release-notes 目录有版本文件（形状 `v<数字段>.md`）+ community 至少
  一处引用（W52a）；引用的最高版本 == 目录的最高版本文件（W52b）。
  总用例 3283 → **3287**（+2 钉测、+1 N3 本篇、+1 D1 因 R224 §6 进入
  回填扫描区间）。
- 变异 **4/4**（均 W52b 独红）：引用降级 v1.1.1 → v1.0.9 / 目录新增
  v1.2.0.md / community 删 v1.1.1 引用 / 目录删 v1.1.1.md。
- **回填**：R224 §6（run `42450653843` / bot `4f6657e`）与索引 §1 的
  写回 / 基线两行（S2/S5 按约定在 bot 之后先红，本轮翻正）。

## 2. 为什么是这一轮

docs/community-updates.md 的「当前正式版」叙述引用 v1.1.1（另有
v1.1.0 的历史链接，W36 已钉两处可解析），desktop/release-notes/ 目录
现有 13 个版本文件、最高 v1.1.1.md。「当前正式版」是发版叙事的门面
账：新日志入库（如 v1.2.0.md）而叙述没跟——读者看到的还是旧版；
或叙述写到尚未入库的版本——W36 只判「引用的都在盘」，不判「最高
引用 == 目录最高」。这层账第一次进射程。

W52 的锚选在「最高版本按数字段比较」：字符串比较会把 v1.0.10 排在
v1.0.9 之前（10 < 9 的字符串陷阱），按 `(1,0,10)` 数字段元组比较才
是版本序。

## 3. 实现

### 3.1 生产代码

- 零改动（最高版本现同账：引用 v1.1.1 == 目录最高 v1.1.1.md，纯
  钉住）。

### 3.2 `tests/test_community_current_version.py`（W52a / W52b）

| 判据 | 内容 | 锚点 |
|---|---|---|
| W52a | release-notes 目录有版本文件（`v<数字段>.md` 形状）；community 至少一处引用 | docs/community-updates.md + desktop/release-notes/ |
| W52b | 引用的最高版本 == 目录的最高版本文件（数字段元组比较） | 同上 |

实现要点：

- 版本键 `v1.1.1 → (1, 1, 1)`——数字段元组，`v1.0.10` 正确排在
  `v1.0.9` 之后。
- W36 的可解析账（两处链接）继续由其本人管；W52 只对最高版本。

## 4. 验证

- 定向：`tests/test_community_current_version.py` 2 passed（首跑修正
  缺失的 `_text` 辅助后即过）；关联面
  `test_desktop_release_notes_refs.py`（W36）、
  `test_desktop_tag_version_strip.py`（W46）全绿；S2/S3/S5 在本提交
  前的红是约定（bot 之后、索引翻正之前），本提交翻正后全绿。
- 本机全量：**3259 passed / 28 skipped / 0 failed**（3287 条，
  约 11m32s；S4 体量行在全量树上是约定的最后一步翻正，重算后复跑绿）。
- 变异 **4/4**（均还原并逐字节/存在性复核；community-updates.md 为
  CRLF）：

| 变异 | 结果 |
|---|---|
| M1 引用降级 v1.1.1 → v1.0.9 | W52b 红（引用最高 (1,1,0) ≠ 目录 (1,1,1)）、W52a 绿 |
| M2 目录新增 v1.2.0.md | W52b 红（目录最高 (1,2,0)）、W52a 绿 |
| M3 community 删 v1.1.1 引用行 | W52b 红（引用最高 (1,1,0)）、W52a 绿 |
| M4 目录删 v1.1.1.md | W52b 红（目录最高 (1,1,0)）、W52a 绿 |

## 5. 边界与遗留

- 只判最高版本的同账——不判目录里的历史文件是否都被引用（旧日志
  无需叙述）、不判日志内容、不判 tag 与日志的对应（发版流程负责）、
  不判 v1.0.10 这类字符串排序陷阱本身（按数字段比较正是为了它）。
- 四轮连推（二十六）续 **R226 应用显示名两脚本同账（W53）**、
  **R227 安装数据目录标识同账（W54）**、**R228 收口**。
- 生产代码不变；`config/skills_config.json` 保持未提交（C1）。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  下一轮回填。

## 7. 提交

- 改动：`tests/test_community_current_version.py`（W52）、R225 文档、
  R224 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 标题/阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R225 一条）、
  `JUDGEMENT_LEDGER.md`（§10.97）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
