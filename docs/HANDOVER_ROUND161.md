# DeterminFlow (xs2) 交接报告 — Round 161（版本双源同账：pyproject ↔ web/package.json）

> 单 profile。四轮连推（十）第 1 轮（R160 §7 登记）。发版要同时改
> 两处 `version`——`pyproject.toml` 的 `[project].version` 与
> `web/package.json` 的 `version`（前端产物打进桌面包与容器镜像）。
> 此前无人对账：`test_branding` 只钉名字与资产来源，不钉版本；漏改
> 一边时「打包元数据的版本」与「前端清单的版本」悄悄分叉。本轮钉成
> **W12**（W 系从依赖四源延伸到版本双源）。

## 1. 一句话结论

- 新增 `tests/test_version_sources.py` **W12**（实测 R160 §7 登记，
  首跑即过）：`pyproject.toml [project].version` ==
  `web/package.json version`，两处都必须是 `X.Y.Z` 形状（语料守卫）
  且逐字相等。实测两处都是 `0.1.0`。
- 总用例 3060 → **3063**（+1 W12、N3/D1 因本篇与 R160 回填 +2）；
  变异 **2/2**。生产代码零改动。

## 2. 开工复核（实测 2026-11-06）

| 源 | 值 |
|---|---|
| `pyproject.toml` `[project].version` | `0.1.0` |
| `web/package.json` `version` | `0.1.0` |

## 3. 实现

- `_pyproject_version()`：tomllib 读 `[project].version`；
  `_web_version()`：json 读 `version`。两者各自先过 `X.Y.Z` 形状
  守卫（解析不到或形状不对显式红），再逐字比较。
- 判据单条（W12）：不等即红，错误信息列两个值并提示「发版时两处
  必须同改」。

## 4. 判据台账

- 新增 §10.33（W 系续：版本双源，W12），接在 §10.32 之后；家族
  清单不变（仍是 W 系）；编号表仍 18 条。

## 5. 验证

- 定向：`tests/test_version_sources.py` **1 passed**。
- 本机全量：**3035 passed / 28 skipped / 0 failed**（3063 条）。
- 变异：

| 变异 | 结果 |
|---|---|
| M1 pyproject `0.1.0` → `0.1.1` | W12 红（pyproject==0.1.1 vs web==0.1.0），语料守卫绿 |
| M2 web/package.json `0.1.0` → `0.0.9` | W12 红（双源漂移），语料守卫绿 |

字节快照还原后 sha256 逐字节相同，2/2 咬合。

## 6. CI

- 提交 `<code-sha>` 推送后 run `<run1>`：10 job 预计全 `success`；
  写回 **第 80 条**（满窗滚动：追加后裁剪最旧一条，history 仍 80 条）。
  R162 回填。

## 7. 边界与遗留

- 不判 `web/package-lock.json`（npm ci 自带 package.json↔lock 一致性
  闸门）；不判 `[tool.*]` 的其他版本字段；不判 git tag（发版流程的
  账，RELEASE_SOP 自己管）。
- 下一轮 **R162 许可证面（V4）**：license-files 引用可解析 + 双语
  徽章授权名同账（R160 §7 登记）。
- 生产代码零改动；`config/skills_config.json` 保持未提交（C1）。

## 8. 提交

- 改动：`tests/test_version_sources.py`（新文件，W12）、R161 文档、
  R160 §6 回填、`HANDOVER_INDEX.md`（§1 六行 + H1 + §3 阶段行 +
  §4 H2/一行 + §6.1）、`PROJECT_INFO.md`（H2 + R161 一条）、
  `JUDGEMENT_LEDGER.md`（§10.33）。生产代码零改动。
- `config/skills_config.json` 不纳入（C1）。
