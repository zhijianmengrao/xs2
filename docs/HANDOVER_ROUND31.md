# DeterminFlow (xs2) 交接报告 — Round 31（首个 fork 发版演练：v1.0.0 落地）

> 本轮定位：R30 §6 P2 执行轮——**用户决策版本号 v1.0.0**，完成 fork 首个
> tag 发版全链路演练（版本号统一 → release-notes → tag → 流水线 → 发布 →
> 端到端验签）。基线：`b6f120f`（R30 收尾）→ 本轮 `0d9d23f` + tag `v1.0.0`。

## 1. 改动清单（8 文件）

| 文件 | 改动 |
|---|---|
| `desktop/src-tauri/tauri.conf.json` / `Cargo.toml` / `Cargo.lock`（应用包条目）/ `desktop/package.json` | 版本 `1.1.1` → `1.0.0`（四处一致；Cargo.lock 同步应用包条目避免 CI 锁漂移） |
| `desktop/official-plugins.lock.json` | `desktop_version` → `1.0.0`（**必须同步**：`load_official_plugin_lock` 对 tauri 版本硬校验，full flavor 构建会加载真实锁） |
| `tests/test_desktop_packaging.py` | 版本钉值断言 `1.1.1` → `1.0.0` |
| `desktop/release-notes/v1.0.0.md` | **新增**：fork 首版说明（要点/安装升级表/版本线说明），同时作为 release 正文与 latest.json 的 notes 字段 |
| `scripts/verify_release_v100.py` | **新增**：发版后本地端到端验签脚本（sha256 + minisign ed25519 验签，本轮验收工具留档复用） |

## 2. 发版执行记录

1. **前置事实核对**：release job 强制要求**四个安装包**（Win core/full NSIS +
   macOS core/full DMG）→ `build-macos` 在本 fork **首次真实执行**（此前全部
   tag-only skip）；ad-hoc 签名无 Apple 证书依赖，fork 可跑。workflow 有
   tag↔版本一致性校验（`v$version`）。
2. **本地验证**：desktop 契约测试
   `test_desktop_packaging + test_desktop_plugin_lock + test_desktop_public_model_smoke + test_core_default_resources`
   → **49 passed / 2 skipped**（macOS icon + symlink 平台 skip）。
3. **提交推送**：`0d9d23f` → main；**打 annotated tag `v1.0.0` 推送**。
4. **流水线**（commit `0d9d23f` 共 4 个 run，全部 **completed/success**）：
   - CI[v1.0.0] 与 CI[main]：四 job 全绿（版本升级无回归）；
   - Desktop Windows[main]：分支构建（不发布）；
   - **Desktop Windows[v1.0.0]**：Win core/full NSIS + **macOS core/full（fork
     首跑通过）** + release job → `gh release create` 发布。

## 3. 发布验收（全部实测）

| 项 | 结果 |
|---|---|
| Release 存在性 | https://github.com/zhijianmengrao/xs2/releases/tag/v1.0.0（非 draft/prerelease） |
| 资产清单（11 个） | Win core/full setup.exe（各含 .sha256/.sig）+ macOS core/full dmg（各含 .sha256）+ latest.json |
| updater 端点 `releases/latest/download/latest.json` | **HTTP 200**（R29 §5.4 的 404 预期空态就此终结）；`version=1.0.0` |
| latest.json 下载 URL | 指向**本仓库** `.../zhijianmengrao/xs2/releases/download/v1.0.0/DeterminFlow_1.0.0_x64-setup.exe`——R29 `--base-url` 修复实测生效 |
| latest.json signature ↔ release .sig 资产 | 逐字一致 |
| tauri.conf pubkey ↔ 本地 `determinflow-updater.key.pub` | 逐字一致 |
| **端到端 minisign 验签**（下载 33MB 安装器 + `scripts/verify_release_v100.py`） | sha256 ✓；sig blob 74B（algo+keynum(8)+sig(64)）与 pubkey blob 42B 的 keynum 一致（`c7ebb04df17244ed`）；**ed25519 签名对 blake2b-512(安装器) 验证通过**——与桌面更新器同算法同链，分发完整性自证 |
| CI 内部校验（流水线自带） | tag↔版本一致性 throw 检查、sha256sum --check 全资产、verify_bundle（安装器冒烟 + 卸载冒烟） |

## 4. 风险与遗留

1. **大陆下载 GitHub Releases 慢**：33MB 安装器实测 ~30KB/s 且中断一次需
   断点续传。若成真实痛点按 R28 §6 选项 B（Cloudflare R2 + 自有域名）迁移，
   endpoints 平滑切换。
2. **全局签名（trusted comment 认证）未取证**：minisign 规范中可选强化项，
   更新器不强制；本轮主签名链已完整证明。脚本注释已说明。
3. **版本线说明**：1.0.0 低于上游 1.1.1——fork 自有版本线起点；上游原版
   客户端不会发现本版本（分发/签名体系不同），release-notes 已写明需全新
   安装。后续 fork 版本从 1.0.1 递增即可。
4. `sync_gitee_release.py` / `replace-desktop-assets.yml` 仍指上游（资产同步
   面，非 updater 分发），维持 R29 §5.3 结论不动。
5. 更新通道 = Core 安装器（上游既有决策）：Full 用户检查更新会被引到 Core
   安装器。本轮未改；若需双通道属后续产品决策。

## 5. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest tests/test_desktop_packaging.py tests/test_desktop_plugin_lock.py tests/test_desktop_public_model_smoke.py tests/test_core_default_resources.py -q   # 49/2
git push origin main && git tag -a v1.0.0 -m "..." && git push origin v1.0.0
# 验收：
curl -sL https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json   # 200
./.venv/Scripts/python.exe scripts/verify_release_v100.py "$TEMP"                     # ALL CHECKS PASSED
```

## 6. 下一轮迭代计划（Round 32 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P2 | 评分/检查历史记录持久化（先定存储位置：localStorage 最小 vs 后端端点） | 低-中 | 2h |
| P2 | 发版体验固化：verify_release 脚本参数化（去 v1.0.0 硬编码）+ 发版 SOP 文档 | 低 | 1h |
| P3 | updater 死通道清理（R2/Gitee 源移除 + Rust 测试精简） | 中 | 1h |
| P3 | 大陆下载加速评估（R2 选项 B 调研，视痛点决定） | 低 | 0.5h |
| P3 | spawn 真实并发测试；POSIX 真跑 | 中/低 | 1h/环境 |
