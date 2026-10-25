# DeterminFlow (xs2) 交接报告 — Round 28（维护者任务执行轮：删除归档 + 首次推送 + CI 核对 + B18）

> 本轮定位：R27 §6 P1 的三项维护者任务由用户明确授权执行——①提交 15 个
> HANDOVER 外来删除（连续五轮在场的「疑似用户归档」正式确认为有意删除）；
> ②推送 R23–R27 全部积压提交；③CI 四 job 实跑核对。核对过程发现并修复
> **B18**（R23 挂 CI 的审计步骤在 cp1252 stdout 下崩溃——此前从未推送导致
> 从未真实执行）。另附 P3「desktop updater 分发地址」决策选项分析（§6）。
> 基线：`dcd91a9`（R27 提交）→ 本轮产出 `a249e17`（删除）、`d3d75d5`（B18）。

## 1. 任务一：HANDOVER 删除归档（a249e17）

- 15 个文件：`docs/HANDOVER.md` + `docs/HANDOVER_ROUND10..23.md`（-2934 行），
  显式路径提交；`HANDOVER_ROUND24..27.md` 与 `PROJECT_INFO.md` 保留为现行
  维护入口。**连续五轮在场的外来删除至此闭环。**

## 2. 任务二：推送（首次成功确认）

- 排障结论修正（记忆 xs2-git-push-proxy 已更新）：GCM 已存账号
  **zhijianmengrao**（`git credential-manager github list`），此前「socks5
  破坏 GCM 授权」的障碍因已存凭据不再触发；git 传输继续走全局
  `socks5://127.0.0.1:10808`（verge-mihomo，同进程另有 HTTP 口 **10509**，
  curl 实测可用；本机亦可直连 GitHub）。
- `git push origin main`：`321a2f0..a249e17`（6 提交）→ 后续 `d3d75d5`。
  验证 `git rev-list origin/main..main --count` = **0**。
- 本机 SSH key（id_ed25519）未注册 GitHub（publickey 拒绝），备用通道留档。

## 3. 任务三：CI 四 job 核对 + B18

### 3.1 首轮核对（a249e17，run 40148872231）

| job | 结果 |
|---|---|
| backend（ubuntu） | success |
| frontend | success |
| container-config | success |
| **windows-backend** | **failure**（失败步骤：Storage name audit；测试本体 **1808 passed / 28 skipped / 0 failed**——28 含 e2e 17 条诚实 skip，服务不在 CI 跑） |

### 3.2 B18：审计脚本 cp1252 stdout 崩溃（R23 潜伏缺陷）

- **现象**：CI 审计步骤 `python scripts/audit_storage_names.py` 报
  `UnicodeEncodeError: 'charmap' codec can't encode characters`（cp1252.py），
  exit 1。**实际审计结果是 clean**（崩溃点在打印 `[clean]` 结论的 line 31）。
- **根因**：CI（windows-latest / Windows Server 2025 PowerShell）stdout 编码
  为 **cp1252**，脚本 print 中文结论无法编码；本机 cp936 可编码中文故从未
  暴露。R23（`a6c2515`）把审计挂进 CI，但 R23 起提交从未推送——**这是该
  步骤在 CI 的首次真实执行**，属「挂了 CI 但没验证过 CI」的流程失误。
  与 R18 修过的「cp1252 炸 write_text」同族（PROJECT_INFO 注意事项 5），
  方向相反：这次是 **print** 面。
- **修复（d3d75d5）**：`scripts/audit_storage_names.py` 入口把 stdout/stderr
  `reconfigure(encoding="utf-8", errors="replace")`（与 humanware CLI 契约
  §5 的既有约定一致）。
- **回归锚**：`tests/test_storage_name_audit.py` 新增
  `test_script_survives_non_utf8_stdout`——以 `PYTHONIOENCODING=cp1252`
  子进程跑脚本，断言 exit 0 且 stdout 含 `[clean]`（无修复时必复现崩溃）。
- **同族排查**：CI 会执行的其他脚本（desktop/scripts/*）无中文 print；
  `scripts/check_environment.py` 有中文 print 但不在 CI 路径（本地工具，
  不改，最小修复原则）。

### 3.3 修复后核对（d3d75d5，run 40149647827）

**四 job 全绿**：backend ✓ / windows-backend ✓（含修复后的 Storage name audit
步骤）/ frontend ✓ / container-config ✓。另 Desktop Windows（a249e17，
run 40148872233）**success**：core/full NSIS 构建通过，macOS 按 tag-only
规则正确 skip。至此 origin/main（`d3d75d5`）CI 状态与本地双基线一致。

## 4. 本地回归（B18 修复前后）

| 基线 | R27 | 本轮（d3d75d5） |
|---|---|---|
| Low-IL | 1740 / 96 / 0 | **1741 / 96 / 0**（+1 = B18 回归锚） |
| High-IL | 1825 / 11 / 0 | **1826 / 11 / 0**（权威） |
| 总用例 | 1836 | **1837** |
| 审计（本机） | [clean] | **[clean] exit 0** |

## 5. 风险与遗留

1. CI 审计步骤今后随每次 push 真实执行（B18 后才真正可用）——它是防新数据
   回归的闸门，若未来误报需先看输出是 findings 还是崩溃。
2. desktop-windows.yml 的 release job `--base-url` 仍指向上游
   `alikon-art/DeterminFlow` 的 release 下载地址（fork 尚未打 tag，潜伏未触发），
   属 P3 分发地址决策的伴生修复项（§6）。
3. 推送通道依赖 GCM 已存账号 + socks5 git 传输；若换机器/清凭据需按更新后
   的记忆 xs2-git-push-proxy 路径恢复。

## 6. P3 决策分析：desktop updater 分发地址（选项供维护者定夺）

现状：`desktop/src-tauri/tauri.conf.json` updater endpoints 指向上游
`https://downloads.determinflow.com/desktop/stable/latest.json`，而 pubkey 已换
成本 fork 自有密钥（R22/`25282d4`）→ 上游 manifest 验签必败 = **安全失效态**
（自动更新恒拒绝，用户只能手动下载）。要启用自动更新需把 endpoints 与
release 流水线的 `--base-url` 一并切到自有分发地址。

| 选项 | 方案 | 优点 | 缺点 | 工作量 |
|---|---|---|---|---|
| **A（推荐）** | **GitHub Releases 自托管**：endpoints=`https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json`；同步把 desktop-windows.yml 的 `--base-url` 从 alikon-art 改为 `$GITHUB_REPOSITORY` | 零新基础设施；工件已由 release job 自动发布到自有 release（`gh release create` 步骤现成）；仓库公开（API 无 token 可读已验证）→ latest/download 永久稳定 URL；HTTPS 由 GitHub 提供 | 中国大陆直连 GitHub 下载速度不稳定（本机有代理，终端用户未必有）；release 资产必须公开可读 | **2 行改动**（tauri.conf.json + workflow），风险极低 |
| B | **Cloudflare R2 + 自有域名**（复刻上游架构）：注册 R2 bucket + 域名，配置 vars `R2_DISTRIBUTION_ENABLED/R2_BUCKET/R2_ENDPOINT_URL` + secrets `R2_ACCESS_KEY_ID/SECRET`；endpoints 指向 `https://<自有域名>/desktop/stable/latest.json` | 上游 `publish_r2_release.py` 脚本现成（vars 开关即启用）；R2 免出口流量费、10GB 内免费；自定义域名可挂 CDN，大陆可达性最优 | 需域名（约 ¥50+/年）+ Cloudflare 账号 + DNS 配置；多一处运维面；密钥管理 | 账号+域名+4 个仓库变量/密钥，约 1-2h |
| C | GitHub Pages 静态托管 manifest | 稳定 URL、可自定义域 | 二进制放 Pages 受 100MB/文件与 1GB 仓库限制（NSIS full 安装器超限风险）；仅托管 manifest 则相对选项 A 纯属多余一跳 | 不推荐 |
| D | 维持现状（安全失效态） | 零工作；更新器恒拒绝上游签名，无降级风险 | 无自动更新 UX；每次发版用户手动下载；更新失败弹错误 | 0 |

**推荐路径**：先 A（2 行，立刻可用）→ 若大陆用户下载速度成为真实痛点再迁 B
（endpoints 是列表，可平滑切换；A→B 只需再改 1 行 + 配 R2）。无论选哪个，
`--base-url` 指向上游这一潜伏错误都应一并修正（否则生成的 latest.json 里
安装器下载链接指向上游仓库，tag 对不上或验签必败）。

## 7. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
git add docs/HANDOVER.md docs/HANDOVER_ROUND10..23.md && git commit   # a249e17
git push origin main                                                    # 321a2f0..a249e17
# CI 核对（无 gh CLI，走 REST API）：
#   GET api.github.com/repos/zhijianmengrao/xs2/actions/runs?per_page=N + /runs/{id}/jobs
#   job 日志：GCM 凭据（git credential fill）→ logs 端点 302 → 裸取签名 URL
./.venv/Scripts/python.exe -m pytest tests/test_storage_name_audit.py -q # 6 passed
./.venv/Scripts/python.exe -m pytest -q                                  # 1741/96/0
High-IL（py.exe + PYTHONPATH 挂载）                                       # 1826/11/0
git push origin main                                                     # d3d75d5（B18）
```

## 8. 修改文件清单

```
docs/HANDOVER.md + HANDOVER_ROUND10..23.md   # 删除 15 个（a249e17）
scripts/audit_storage_names.py               # B18：stdout 重配 UTF-8（d3d75d5）
tests/test_storage_name_audit.py             # B18 回归锚 +1 用例（d3d75d5）
docs/HANDOVER_ROUND28.md                     # 本文件
docs/PROJECT_INFO.md                         # R28 条目与基线更新
```
