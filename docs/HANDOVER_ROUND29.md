# DeterminFlow (xs2) 交接报告 — Round 29（updater 分发自托管：方案 A 落地）

> 本轮定位：R28 §6 P3 决策的执行轮——用户选定**方案 A（GitHub Releases
> 自托管）**。改动面经核实比预估多一处关键文件：`desktop/src-tauri/src/updater.rs`
>（桌面端 `check_update_sources` 的运行时端点在 Rust 常量里，而非只读
> tauri.conf.json）。后端 Python 侧零行为变化（仅钉值测试同步）。
> 基线：`b0716fc`（R28 提交）→ 本轮 `2938a82`。

## 1. 改动清单（4 文件，+10/-4）

| 文件 | 改动 |
|---|---|
| `desktop/src-tauri/tauri.conf.json` | updater `endpoints` → `https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json` |
| `desktop/src-tauri/src/updater.rs` | `GITHUB_UPDATE_ENDPOINT` → 同上（fork Releases）；附注释说明上游 R2/Gitee 源的去留理由 |
| `.github/workflows/desktop-windows.yml` | release job 的 `--base-url` 从 `alikon-art/DeterminFlow` 改为 `${{ github.repository }}`（Actions 模板展开为本仓库，修掉 latest.json 内安装器下载链接指向上游的潜伏错误） |
| `tests/test_desktop_packaging.py` | endpoints 钉值断言同步（+方案注记） |

## 2. 设计说明

- **运行时三源机制**（`check_update_sources`）：R2（上游 downloads 域）、GitHub、
  Gitee（上游 alikon 镜像）并发探测，`plan_update_sources` 按「版本权威性 +
  签名一致性」选优。本 fork 的验签公钥是自有密钥（R22 `25282d4`），上游
  manifest 验签**必败** → R2/Gitee 两源是 **fail-closed 死通道**（错误结果
  被 `choose_update` 忽略，仅当三源全败才报错）。因此：
  - 唯一可用通道 = GitHub 源 → 指向本 fork Releases（本轮改动核心）；
  - R2/Gitee 常量**保留原地址**：并发探测、永不入选、无安全风险（上游签名
    无法通过本 fork 公钥验证），仅多两次 15s 超时的并发请求（join3 并行，
    墙钟不叠加）。彻底移除需同步精简 `plan_update_sources` 与其 8 条 Rust
    单测，留作后续可选清理（见 §5）。
- **latest.json 生成侧**：release job（tag-only）用 `create_update_manifest.py`
  的 `--base-url` 拼安装器下载链接——改用 `${{ github.repository }}` 运行时
  变量后，manifest 里的下载 URL 指向**本仓库** release 资产，与 endpoints
  自洽。签名链不变：NSIS 产物签名用仓库 secret 的 `TAURI_SIGNING_PRIVATE_KEY`
  （R22 已配置），与 tauri.conf.json 的 fork 公钥配对。
- **发版流程**（用户操作）：`git tag v<X.Y.Z> && git push origin v<X.Y.Z>` →
  release job 自动构建 NSIS + .sig + latest.json 并 `gh release create` 到本
  仓库 → 桌面端更新检查即可发现并验签通过。注意 `desktop/release-notes/
  v<X.Y.Z>.md` 需先备好（workflow 引用）。

## 3. 验证

| 项 | 结果 |
|---|---|
| YAML `safe_load`（PROJECT_INFO 注意事项：改 workflow 必先本地验证） | ✓ jobs: build / build-macos / release |
| tauri.conf.json JSON 解析 + endpoints 值 | ✓ |
| `tests/test_desktop_packaging.py` + `test_desktop_plugin_lock.py` | 36 passed / 1 skipped（macOS） |
| Low-IL 全量 | **1741 / 96 / 0**（101.88s，与 R28 一致——无新增用例） |
| High-IL 权威 | **1826 / 11 / 0**（117.78s） |
| updater.rs Rust 单测 | 不涉及 URL 常量（仅测 plan 逻辑），CI desktop 编译即验证 |
| CI（`2938a82`） | 四 job + Desktop Windows NSIS 编译（见 §4 填记） |

## 4. CI 结果（已核对）

- **CI（run 40150677528，`2938a82`）：completed / success**——四 job
  （backend / windows-backend / frontend / container-config）全绿。
- **Desktop Windows（run 40150677429，`2938a82`）：completed / success**——
  core/full NSIS 双构建 job 通过（**updater.rs 新端点常量编译验证**），
  macOS 与 Publish GitHub Release 按 tag-only 规则正确 skip。

## 5. 风险与遗留

1. **死通道清理（可选后续）**：彻底移除 R2/Gitee 源需重构 `plan_update_sources`
   + 8 条 Rust 单测 + `join3`→`join2`，收益是省两次注定失败的探测请求。
   本轮按最小改动原则未做。
2. **大陆可达性**：GitHub Releases 直连下载在大陆网络可能缓慢——若成为真实
   痛点按 R28 §6 选项 B 迁移（Cloudflare R2 + 自有域名，endpoints 平滑切换）。
3. **`sync_gitee_release.py` / `replace-desktop-assets.yml` / 插件源 URL**
   （`config/plugin-sources.json` 等）仍指上游——它们是插件生态/资产同步面，
   不属于 updater 分发，本轮未动。
4. 未打 tag 前无 latest.json 资产——`releases/latest/download/latest.json` 404，
   更新检查诚实失败（桌面端显示无更新/源不可用），属预期空态。

## 6. 下一轮迭代计划（Round 30 候选）

| 优先级 | 事项 | 风险 | 工作量 |
|---|---|---|---|
| P2 | 首个 fork tag 发版演练（v1.1.2 或沿用版本号决策 + release-notes 模板） | 低 | 1h |
| P2 | 角色声音页三区块共享「角色下拉+内容输入」子组件抽取（R28 §7 遗留） | 低 | 1.5h |
| P2 | 评分/检查历史记录持久化 | 低-中 | 2h |
| P3 | updater 死通道清理（R2/Gitee 源移除 + Rust 测试精简） | 中 | 1h |
| P3 | spawn 真实并发测试；POSIX 真跑 | 中/低 | 1h/环境 |

## 7. 命令记录（本轮）

```bash
cd "F:\DeterminFlow x2\xs2"
./.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('.github/workflows/desktop-windows.yml', encoding='utf-8'))"
./.venv/Scripts/python.exe -m pytest tests/test_desktop_packaging.py tests/test_desktop_plugin_lock.py -q   # 36/1
./.venv/Scripts/python.exe -m pytest -q                                  # 1741/96/0
High-IL（py.exe + PYTHONPATH 挂载）                                       # 1826/11/0
git push origin main                                                      # 2938a82
```

## 8. 修改文件清单

```
desktop/src-tauri/tauri.conf.json            # endpoints → fork Releases
desktop/src-tauri/src/updater.rs             # GITHUB_UPDATE_ENDPOINT → fork（+死通道注释）
.github/workflows/desktop-windows.yml        # --base-url → ${{ github.repository }}
tests/test_desktop_packaging.py              # 钉值断言同步
docs/HANDOVER_ROUND29.md                     # 本文件
docs/PROJECT_INFO.md                         # R29 条目
```
