# DeterminFlow (xs2) 交接报告 — Round 110（失败沙箱 GC）

> 单 profile。把 R106 §8 的第二个候选做完：失败沙箱清理从「手工」变成
> 可重复执行的工具，默认 **dry-run**，只认约定前缀、直接子目录、过期年龄
> 与非链接。零 `src/`、`web/` 改动；`MAX_ROUNDS`、失败沙箱保留策略、
> 写权限归属都不动。

## 1. 一句话结论

- 新增 `scripts/replay_sandbox_gc.py`：扫描临时目录里的
  `replay-ci-writeback-*`，按 `--min-age-days`（默认 7）选候选；
  **默认只打印**，`--apply` 才删除。
- 四道独立守卫：**直接子目录** + **名字前缀** + **非符号链接/junction** +
  **mtime 超龄**；删除复用 `replay._remove_sandbox`（Windows 只读 pack）。
- 用例 **+6 → 2705**；本机 **2677 passed / 28 skipped / 0 failed**
  （265.52s）。R109 为 2671/28（2699）。
- **变异 M127–M131 5/5 咬合**（每道守卫至少一条用例独立咬住）。
- CI run **41446771172**：**10 个 job run 全 `success`**，writeback 7/7、
  fetch-chain 9/9；写回历史 **35 → 36**（`f8134c1`）。

## 2. 实现要点

### 2.1 候选判定

```python
for entry in sorted(root.iterdir()):          # 只看直接子目录
    if not entry.name.startswith(SANDBOX_PREFIX):
        continue
    if _is_symlink_or_junction(entry) or not entry.is_dir():
        continue
    mtime = entry.stat().st_mtime
    if mtime <= now - min_age_days * 86400:
        found.append((entry, now - mtime))
```

- `SANDBOX_PREFIX = "replay-ci-writeback-"` 与
  `replay_ci_writeback.replay` 的 `mkdtemp(prefix=...)` 硬一致；
- `is_junction()` 在 Python 3.12+ 可用，旧版本按「不是 junction」处理；
- 年龄用 **mtime**，不读目录内容；只影响是否候选，不影响删除方式。

### 2.2 默认 dry-run

```text
$ python scripts/replay_sandbox_gc.py
[dry-run] 将删除 /tmp/replay-ci-writeback-abc（10.2 天）
dry-run：候选 1 个（加 --apply 才会删除）
$ python scripts/replay_sandbox_gc.py --apply
已删除 /tmp/replay-ci-writeback-abc（10.2 天）
完成：删除 1/1 个候选
```

- 退出码：`0` 成功；`1` 有删除失败；`2` 用法错误（负年龄、root 不存在）。
- 删除后 `path.exists()` 复核；`_remove_sandbox` 已处理只读 pack 的
  `shutil.rmtree(ignore_errors=True)` 静默失败（R95 的坑），GC 直接复用，
  不复制一份删除逻辑。

### 2.3 为什么不是「自动在 CI 里跑」

`replay` 的失败沙箱在 **runner 的临时目录**里；GHA 的 runner 是一次性的，
job 结束就没了。生产 CI 里没有「上几轮的沙箱」可清。真正会累积的是本机
开发环境，所以本轮交付的是**手工可执行、默认不删**的工具；没有加定时器
或 CI step，避免为了「自动化」造一个永远空转的步骤。

### 2.4 用例

- `tests/test_replay_sandbox_gc.py`：
  - dry-run 只列超龄匹配目录（新目录、异名前缀、同名文件都不列）；
  - `--apply` 只删候选，其余原样；
  - `--min-age-days 0` 允许；
  - 负年龄 / root 不存在退 2；
  - 同名符号链接被跳过，目标不被删除。

## 3. 用例（+6）

| 文件 | 条数 | 断言 |
|---|---|---|
| `tests/test_replay_sandbox_gc.py` | +6 | dry-run 候选集 / apply 删除集 / 年龄 0 / 负年龄 / root 缺失 / 符号链接 |

**本机全量**：**2677 passed / 28 skipped / 0 failed**（2705 条，265.52s）。

## 4. 变异验证（5/5 咬合）

| 变异 | 结果 |
|---|---|
| M127 不检查前缀 | **1 红**（dry-run：`other-old` 被列入） |
| M128 忽略年龄 | **1 红**（dry-run：新目录被列入） |
| M129 不跳过符号链接 | **1 红**（链接用例：删除失败/目标风险） |
| M130 默认改成直接删除 | **1 红**（dry-run 用例：旧目录被删） |
| M131 负年龄不拒绝 | **1 红**（用法用例：返回 0 而不是 2） |

每道守卫都有独立变异，说明它们不是「写在一起但只有一条在起作用」。
全部用 `cp` 备份还原并核对 sha256（备份在 `_r110_backup/`）。

## 5. 边界

- GC **不进入 CI**：runner 临时目录随 job 消失，没有可清的历史现场；
  工具定位是本机/长期环境的维护命令。
- 只处理**直接子目录**；不递归、不跟随链接；不会碰前缀之外的任何东西。
- 默认 7 天；`--min-age-days` 可调，`0` 只用于测试/明确要求。
- 失败沙箱的**保留策略**没变：replay 失败仍保留现场，GC 只是事后处置。
- 写权限仍只属于 `e2e-history-writeback`；GC 不需要仓库写权限。

## 6. 提交与 CI

- 提交 **1b24a1d**（`feat(R110): 失败沙箱 GC（默认 dry-run）`；
  rebase 后 **9c2de9b**），显式路径 add，2 文件 +204；
  `config/skills_config.json` 外来改动保持未提交。
- 本机全量：**2677 passed / 28 skipped / 0 failed**（2705 条，265.52s）。
- CI run **41446771172**：**10 个 job run** 全 `success`
  （12:41:36→12:50:46，约 9m10s）——backend **2640/65**、
  windows-backend **2676/29**（均 **2705**）；
  `replay-ci-writeback` 两平台各 **7/7 PASS**；
  `replay-ci-fetch-chain` 两平台各 **9/9 PASS**。
- 写回历史 **35 → 36 轮**（`ci-41446771172`、`source=ci`、10/10/0），
  bot 提交 `f8134c1`（`[skip ci]`，未自触发）；本文档回填提交预计
  **36 → 37**。

## 7. 本轮教训

1. **删除类工具默认必须不删**：dry-run 是默认值，`--apply` 是显式动作；
   M130 证明「默认改了」会被用例立刻咬住。
2. **守卫要各自可被咬住**：前缀、年龄、直接子目录、链接，四条独立变异
   各红一次；如果只测「删了一个」，分不清哪条守卫真的在工作。
3. **复用已修过的删除逻辑**：`_remove_sandbox` 在 R95 修过 Windows 只读
   pack 的静默失败；GC 直接调用，不复制第二份 `rmtree`。
4. **不要为自动化而自动化**：CI runner 的临时目录不需要 GC；工具面向
   本机累积，硬塞进 CI 只会是一个永远空转的步骤。

## 8. 下一步候选

- R111：收口轮——五轮审计、文档一致性、全量回归。
- 若将来要自动清理：用 `--apply --min-age-days N` 的手工命令或本机定时
  任务，不要让 CI job 承担。
- 失败沙箱保留策略本身（例如保留最近 N 个）仍未定义；GC 的年龄阈值
  可以承担这个策略，但需要用户拍板数值。
