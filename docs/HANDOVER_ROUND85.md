# DeterminFlow (xs2) 交接报告 — Round 85（清除 Low 强制标签 / 本机基线收口为 2486/28）

> 本轮定位：用户拍定 R84 §9-2（**清标签 + 单独一轮重定基线**）。
> 形态：**零代码改动**——只改环境（用户目录的完整性标签）+ 文档 + 记忆。
> `src/`、`tests/`、`scripts/`、CI YAML 全部未动；`data/workflows` 只读。

## 1. 一句话结论

1. `F:\DeterminFlow x2` 的显式 Low 强制标签已清除：根目录改为 **Medium**
   （`Medium:(OI)(CI)(NW)`），子项继承同步变为 Medium。
2. **清成 Medium ≠ 恢复 High**：venv 里的 `python.exe` 现在回读
   **`S-1-16-8192`（Medium）**，不是 `S-1-16-12288`。Windows 用镜像的强制标签
   给令牌封顶，镜像带 Medium 标签时不会继承 High 父进程——R84 §8-2 的
   「清标签后 venv 继承父进程 IL」只对**完全没有标签**的镜像成立。
3. 本机基线由此收口为**单一 profile**：venv 全量 **2486 passed / 28 skipped /
   0 failed**（180.64s），与 R84 的 High 基线逐项相同；Low 的 2401/113 消失。
   用例总数不变（2514），CI 的 ubuntu/windows 计数不变。

## 2. 前置审计（清标签之前）

只读探针 `_r85_audit_labels.py`（工作区根，**未入库**，按 R81/R84 拍定）遍历
整棵树，用 `GetNamedSecurityInfoW` + `LABEL_SECURITY_INFORMATION` 读每个对象的
SACL，判定标签 ACE 是否为**显式**（`AceFlags & INHERITED_ACE == 0`）。
必须在 High 下跑（读 SACL 要 `SeSecurityPrivilege`）。

| 项 | 结果 |
|---|---|
| 扫描范围 | **17290 个目录 + 169 个 `.exe`/`.dll`**，`errors=0`、`skipped_links=0` |
| 显式标签对象 | **仅 `F:\DeterminFlow x2` 一条**：`Low S-1-16-4096` |
| 其余对象 | 全部为继承 ACE（`(I)`） |

**为什么改根就够**：标签 ACE 带 `(OI)(CI)`，子项没有自己的显式标签时靠继承；
父目录的标签 ACE 被替换后，系统会把继承 ACE 一起更新——这一点在一次性探测
目录 `F:\_r85_label_probe`（父 + 子）上实测过：父从 Low 改 Medium 后，子项的
`(I)(OI)(CI)(NW)` 从 Low 同步变成 Medium。

## 3. 执行与验证

```
icacls "F:\DeterminFlow x2" /setintegritylevel (OI)(CI)Medium
```

| 验证点 | 清标签前 | 清标签后 |
|---|---|---|
| 根目录 | `Mandatory Label\Low Mandatory Level:(OI)(CI)(NW)` | **`Medium:(OI)(CI)(NW)`** |
| `.venv\Scripts\python.exe` | `Low:(I)(NW)` | **`Medium:(I)(NW)`** |
| venv python 进程令牌 | `S-1-16-4096`（Low） | **`S-1-16-8192`（Medium）** |
| 全树显式 Low 残留（复审计） | 1（根） | **0**（显式标签只剩根的一条 Medium） |

进程令牌的读法是让 venv python 派生 `whoami /groups` 并取 `S-1-16-*` 行
（子进程继承父令牌的 IL，不受当前 shell 影响），清标签前后各跑一次。

**只改成显式 Medium，没有删除标签 ACE**：`icacls /setintegritylevel` 只能设置
级别，不能移除。要真正「无标签」需用 `SetNamedSecurityInfo` 写一份不含
`SYSTEM_MANDATORY_LABEL_ACE` 的 SACL——本轮未做，因为没有需求，且显式 Medium
对 High/Medium 进程的行为等价于默认。

## 4. 重定基线（venv 解释器，Medium）

```
./.venv/Scripts/python.exe -m pytest tests -q
→ 2486 passed, 28 skipped, 1 warning in 180.64s
```

**分解核对**：R84 的 Low 基线是 2401 passed / 113 skipped，High 基线是
2486 / 28。`2401 + 85 = 2486`、`113 − 85 = 28`——多出来的 85 条正是此前被
msys 签名转 skip 的那批；它们在 Medium 下正常执行且全过。这不是「跳过的用例
被删了」，skip 总数从 113 降到 28，剩 28 条全是平台类（macOS 签名 / fcntl /
Unix 进程树 / 需要运行中的 8021 服务）。

**Medium 与 High 的测试结果相同**（2486/28），所以「启动器 IL 只影响 msys
能否挂接对象、不影响其余断言」这一 R81/R84 的结论继续成立；但**不能**据此把
Medium 写进文档当作 High 的替代——要真正的 High 仍走
`C:\Program Files\Python314\python.exe` + 绝对 `PYTHONPATH`（R82/R83 处方）。

## 5. 记账方式变更

- 本机不再维护「Low/High 双基线」：`Low 2401/113` 这一行停止新增，历史轮次
  记录保留不动（它们记录的是当时的环境）。
- 新的本地基线固定为 **2486 passed / 28 skipped / 0 failed**。
- 用例总数 **2514 不变**（本轮零新增、零删除）；CI 的 ubuntu/windows 计数
  也不变（R84 的 2449/65、2485/29）。
- 别的机器/无标签目录不受影响：它们的 venv 继承父进程 IL，原本就没有 113-skip
  的 Low profile。

## 6. 改动范围

| 文件 | 变更 | 性质 |
|---|---|---|
| `docs/PROJECT_INFO.md` | +4 / −1（747 行） | R85 轮次条目 + 平台注意 9 的 R85 执行段 |
| `docs/JUDGEMENT_LEDGER.md` | +2 / −1（716 行） | §8 增 R85 执行段 + 旧句改为「R84 时未执行」 |
| `docs/HANDOVER_ROUND85.md` | 新增 | 本文 |
| `F:\DeterminFlow x2` 目录 ACL | 显式 Low → 显式 Medium | 环境（不属仓库） |

**代码与测试零改动**：`src/`、`tests/`、`scripts/`、`.github/workflows/` 均未动，
因此**不做变异验证**（没有可变的实现）；也没有新增用例。

## 7. 未做与未验证

1. **没有删除 SACL 里的标签 ACE**：只把 Low 改成 Medium（见 §3）。
2. **没有跑前端 / e2e / docker build**：零代码与前端改动，R63 的 490/0 与 R84
   的 e2e 10/10 仍适用。
3. **没有重导快照**：`data/workflows` 仍 40 个 run，`tests/fixtures/live_snapshot`
   仍是 28/255；本轮只读。
4. **没有回查标签是何时/被谁设置**：与 R84 §8-7 相同，SACL 没有时间戳，仓库内
   没有任何 `setintegritylevel` 调用。
5. **没有跑 High 基线复核**：Medium 与 R84 的 High 基线逐项相同，未再用 C:
   解释器重跑一遍（避免把一次环境变更放大成两轮全量）。
6. **没有验证其他机器**：结论只针对本机这棵树；可移植性的论证仍按 R84
   §4.3（skip 判据与 IL 无关）。

## 8. 下一轮（用户已拍定）

按 2026-11-01 的选择，依次：

1. **R86：`source_root` 登记为只读展示字段**（与 R83 `runs`、R84 `failure_rate`
   同一处置），守卫用例钉住六个读计数入口的 `(退出码, 文案)` 逐字不变。
2. **R87：制造 n≥29 全失败样本**（用户选择「主动制造」）。原 R84 §3.3 的理由
   是不值得为一条判据跑坏 29 次真实工作流；既然拍定要做，设计约束是
   **在隔离的数据目录里跑，不污染 `data/workflows`**，并且样本必须是真实执行
   记录（不是手写 JSON）。n=29 正是 margin 10 的翻转点：闭式
   `1 − 0.05^(1/29) = 9.82pp < 10`，n=28 是 `10.15pp > 10`——两个方向都要有
   用例/实测。
3. **R88：CI 回写历史**。先出设计与代价表（R81 §7 的结论是「不做」，本轮用户
   改判为「做」）：需要 `contents: write`、并发/竞态处置、失败回滚、避免
   自我触发的提交循环；不能影响现有 `permissions: contents: read` 的 job。

## 9. 提交、推送与 CI 核对

（待补记）
