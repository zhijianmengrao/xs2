# 桌面发版 SOP（fork：zhijianmengrao/xs2）

> 依据 R31 v1.0.0 全链路实战整理；后续发版按本流程执行即可。
> 版本线自 1.0.0 起自有递增（1.0.1、1.0.2 …），与上游 alikon-art 版本号无关。

## 1. 版本号统一（六处，缺一不可）

| 文件 | 字段 |
|---|---|
| `desktop/src-tauri/tauri.conf.json` | `version`（workflow 有 tag↔版本一致性校验） |
| `desktop/src-tauri/Cargo.toml` | `[package] version` |
| `desktop/src-tauri/Cargo.lock` | `determinflow-desktop` 条目的 `version`（避免锁漂移） |
| `desktop/package.json` | `version` |
| `desktop/official-plugins.lock.json` | `desktop_version`（`load_official_plugin_lock` 硬校验，**漏改 full 构建必炸**） |
| `tests/test_desktop_packaging.py` | `test_desktop_versions_are_consistent` 的钉值断言 |

## 2. Release Notes

新建 `desktop/release-notes/v<X.Y.Z>.md`（同时用作 release 正文与
latest.json 的 notes 字段）。要点：本版变更、安装升级表（Win core/full +
macOS core/full 文件名）、Core/Full 差异、macOS ad-hoc 签名提示。

## 3. 本地验证 → 提交 → 打 tag

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -m pytest tests/test_desktop_packaging.py tests/test_desktop_plugin_lock.py tests/test_desktop_public_model_smoke.py tests/test_core_default_resources.py -q
git add <六处版本文件 + release-notes> && git commit && git push origin main
git tag -a v<X.Y.Z> -m "DeterminFlow v<X.Y.Z>" && git push origin v<X.Y.Z>
```

## 4. 流水线（全自动，~12 分钟）

tag 推送触发 `Desktop Windows`：Win core/full NSIS + macOS core/full DMG
（ad-hoc 签名）并行构建 → release job 校验四安装器 + sha256 → 生成
latest.json（下载 URL 指向本仓库，R29 base-url 修复）→ `gh release create`。
未打 tag 时 macOS/release job 按 tag-only 规则跳过，属预期。

## 5. 发版后验收（scripts/verify_release.py）

```bash
mkdir -p rel && cd rel
V=<X.Y.Z>
# 大陆网络建议 curl -C - 断点续传（直连 ~30KB/s 且可能中断）
curl -sLO "https://github.com/zhijianmengrao/xs2/releases/download/v$V/DeterminFlow_${V}_x64-setup.exe"
curl -sLO "https://github.com/zhijianmengrao/xs2/releases/download/v$V/DeterminFlow_${V}_x64-setup.exe.sig"
curl -sLO "https://github.com/zhijianmengrao/xs2/releases/download/v$V/DeterminFlow_${V}_x64-setup.exe.sha256"
cd .. && ./.venv/Scripts/python.exe scripts/verify_release.py --tag "v$V" --assets-dir rel
```

验收覆盖：sha256 / minisign ed25519 验签（与桌面更新器同链，需公钥即
`determinflow-updater.key.pub` 与私钥 `determinflow-updater.key` 配对，私钥
已 gitignore 且 GitHub secret `TAURI_SIGNING_PRIVATE_KEY` 已配置）/
tauri.conf 版本与公钥一致性 / latest.json 端点三项（version、URL 指向、
signature 与 .sig 一致）/ tauri.conf endpoints 与 updater.rs
GITHUB_UPDATE_ENDPOINT 单源一致。

## 6. 注意事项

- 更新通道 = **Core 安装器**（上游既有决策）；Full 用户检查更新会被引到 Core。
- 大陆直连下载慢是已知痛点；若需加速按 R28 §6 选项 B（Cloudflare R2 +
  自有域名）迁移，endpoints 平滑切换即可。
- 上游 R2/Gitee 源已彻底移除（2026-10 修复）：tauri updater 在 check() 阶段
  不验签（仅下载时验签），上游残留的更高版本号（实测 1.1.1 / v1.0.10）会
  穿透成“发现新版本”误报且下载必败。更新源现仅 GitHub 本仓库 Releases，
  两处端点（tauri.conf endpoints 与 updater.rs）须保持一致。
- 回滚：Release 可在 GitHub 页面删除/编辑；已装客户端无影响（更新按
  版本比较拉取）。
