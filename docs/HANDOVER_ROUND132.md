# DeterminFlow (xs2) 交接报告 — Round 132（发版验收：判决不得是 assert）

> 单 profile。新五轮连推（R130–R134）第 3 轮：**发版验收脚本的判决与降级
> 边界**。`scripts/verify_release.py` 是发版前的判决脚本，此前零用例，且十处
> 判断全是裸 `assert`——`python -O` 会把判断整段删掉，脚本仍打印
> `ALL CHECKS PASSED` 并退 0。发行产物与生产代码零改动。

## 1. 一句话结论

- **判决不能是 `assert`**：`assert` 是调试断言，解释器有权在 `-O` 下移除。
  改前实测：把 `.sha256` 换成全 `0`，`python -O scripts/verify_release.py …`
  仍输出 `ALL CHECKS PASSED` 并退 **0**。
- 坏输入此前各有各的 traceback：空 `.sha256` → `IndexError`、坏 base64 →
  `binascii.Error`、`latest.json` 缺 `platforms` → `KeyError`、断网 →
  `URLError`。traceback 的退出码也是 1，与「判了不合格」无法区分。
- 现在四类退出码互不冒充：**0** 通过 / **1** 判了不合格 / **2** 环境或用法
  （没作判定）/ **4** 资产形状无效（没作判定），全部是可读拒因。
- 新增 `tests/test_verify_release.py`（**25 个函数 / 25 条**）。总用例
  2767 → **2792**。
- 变异 **M1–M6 6/6** 咬合，`cp` 还原后 sha256 逐字节相同。

## 2. 为什么是这一轮

R130 治的是 e2e 摘要层（坏 metrics 不得 traceback 判红），R131 治的是 CI
报告层（summary 单行、写失败只告警）。两者都是「展示层不得被坏数据判死」。
发版验收是同一家族的最后一处：它不是展示层，而是**判决脚本**——结论直接
决定「这个安装包能不能发」。

它比前两轮更危险，因为它同时踩中三件事：

1. **零用例**：R31 用它验收过 v1.0.0，R32 把它参数化，此后没有任何直接用例；
2. **裸 `assert` ×10**：`-O` 下 sha256、key id、版本、公钥、manifest 三项
   校验全部消失，脚本照样宣布通过；
3. **失败原因被错误类型淹没**：坏输入是 traceback，退出码同样是 1——读日志
   的人分不清「验签失败」和「你少下载了一个文件」。

R130/R131 的教训是「展示层没有判决权，也不该有把 job 判死的能力」；这一轮
是它的反面：**判决层不该有被解释器开关静默删除的能力**。

## 3. 实现

### 3.1 契约点

- 三个异常类别：`VerificationFailure`（判了不合格）、`AssetShapeError`
  （结构不对，没能比较）、`EnvironmentProblem`（缺输入/读不开/网络）。
  `main` 一处收口成 1 / 4 / 2。
- `_require(condition, message)` 取代全部 `assert`：判决为假时显式抛出，
  与解释器优化模式无关。
- `_read_text` / `_b64decode(validate=True)` / `_minisign_blob` 把
  OSError、`binascii.Error`、长度不符分别转成 2 与 4；minisign 首行必须是
  `untrusted comment`，sig blob 必须 74B、pubkey blob 必须 42B。
- `_sha256_expected` 先判「是不是 64 位十六进制」再比较：空文件与非十六进制
  是**形状无效 4**，十六进制但不相等才是**不合格 1**。这两件事此前都表现为
  `IndexError` / `AssertionError`。
- `_load_manifest` 把网络失败归 2、JSON/结构问题归 4，并显式校验
  `platforms.windows-x86_64` 的 `url` / `signature` / `version` 是字符串。
- 行为保持不变：四阶段输出行、`ALL CHECKS PASSED`、`--full` / `--repo` /
  `--pubkey` / `--skip-manifest` 语义、外层 base64 → 内层 minisign 文本的
  解析方式（R31 取证的结构）。

### 3.2 刻意不做的

- **不改验什么**：sha256、key id、ed25519（blake2b-512 预哈希）、
  `tauri.conf` 版本/公钥、`latest.json` 三项，一个都没有增删。
- **不接进 CI**：验收需要真实发行产物与网络 manifest，CI 检出里没有；
  接进去只会永远退 2。它仍是发版前的手工闸门。
- **不把 key id 不符降级成形状错误**：长度对、结构对，只是「签名不是这把
  公钥签的」——这是判决（1），不是没验成。
- **不捕获所有异常**：没预料到的异常仍以 traceback 退出，不会被误分类成
  2/4（与 #10「判据算术失败」的分界一致）。
- **没有 8，也没有 3**：这里没有判据算术，算不下去的形态都归 4；发版验收
  不存在「样本不足」。

## 4. 判据台账

- §6 复核表补一行（R132）：`-O` 回归、四类退出码各有锚点用例。
- §10.12 新增一段：判决不得是 `assert`；4/2/1 的分界；为什么没有 8/3。

## 5. 验证

- 定向：`tests/test_verify_release.py` **25 passed**（0.71s）。
- 本机全量：**2764 passed / 28 skipped / 0 failed**（2792 条，561.93s）。
- 变异（对 `scripts/verify_release.py` 逐个破坏后跑同一份用例）：

| 变异 | 结果 |
|---|---|
| M1 所有判决恒通过（`_require` 变 no-op） | 8 红 |
| M2 sha256 十六进制校验失效 | 1 红 |
| M3 blob 长度校验失效 | 2 红 |
| M4 minisign 注释行校验失效 | 1 红 |
| M5 验签失败被吞掉 | 1 红 |
| M6 判决退回 `assert`（`-O` 回归） | 8 红 |

`cp` 还原后 sha256 **`00c38677…f65cdf9b`** 逐字节相同，6/6 咬合。

> 首跑 M4 未咬合：原用例只有一行内层文本，禁掉注释行检查后仍被
> 「至少两行」拦住，测试通过得**理由不对**。改成「两行齐全、blob 长度也对」
> 后只有注释行检查能拦住它，M4 才真咬。这是本轮唯一一次用例自身被变异
> 抓出问题，记在此处。

## 6. CI

- 提交 **`2668236`** 推送后 run **41832975143**：**10 个 job 全 `success`**
  （12:52:03→13:09:04 UTC，约 17m01s）。
- 写回历史 **59→60**（`ci-41832975143`，bot 提交 `096ff16`）；本篇 docs
  回填提交预计 **60→61**。

## 7. 边界与遗留

- 验收仍是「产物完整性 + 与本仓库配置一致」：不验证上传者身份、不验
  `latest.json` 的传输来源（HTTPS 之外没有第二证据源），也不判产物行为。
- 手工闸门：不在 CI 里，发版时由人执行；忘记执行不会自动发现。
- `--skip-manifest` 会跳过第 4 阶段——离线验收的已知盲区，输出里仍有前三段
  证据可查。
- 本轮只动 `scripts/verify_release.py` 与测试；`src/`、`web/`、CI YAML 零改动。

## 8. 提交

- 改动：`scripts/verify_release.py`、`tests/test_verify_release.py`、
  R132 文档、PROJECT_INFO、JUDGEMENT_LEDGER、HANDOVER_INDEX。
  发行产物与生产代码零改动。
