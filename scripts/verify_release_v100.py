"""R31 发版演练：本地端到端 minisign 验签（tauri updater 签名链自证）。

对已发布的 DeterminFlow_1.0.0_x64-setup.exe：
1. sha256 与 release 资产 .sha256 一致；
2. .sig（外层 base64 解包后的 minisign 签名）能用本仓库公钥
   （determinflow-updater.key.pub，与 tauri.conf.json 的 updater pubkey 一致）
   通过 ed25519 验签——与桌面端更新器同算法（blake2b-512 预哈希）。

实测结构（R31 取证）：pubkey blob 42B = algo("Ed") + keynum(8) + key(32)；
sig blob 74B = algo("ED") + keynum(8) + signature(64)；keynum 两端一致。
全局签名（trusted comment 认证）为可选强化项，更新器不强制，本脚本不校验。
"""
import base64
import hashlib
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO = Path(r"F:\DeterminFlow x2\xs2")
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

exe = WORK / "df_100_setup.exe"
sig_asset = WORK / "df_100_setup.exe.sig"
sha_asset = WORK / "df_100_setup.exe.sha256"

# 1) sha256 校验
data = exe.read_bytes()
digest = hashlib.sha256(data).hexdigest()
expected = sha_asset.read_text(encoding="utf-8").split()[0].strip()
print(f"[sha256] computed={digest}")
print(f"[sha256] asset  ={expected}")
assert digest == expected, "sha256 mismatch"
print("[sha256] OK")

# 2) 解包 .sig（外层 base64 → minisign 签名文本）
sig_text = base64.b64decode(sig_asset.read_text(encoding="utf-8").strip()).decode("utf-8")
lines = [ln for ln in sig_text.splitlines() if ln.strip()]
assert lines[0].startswith("untrusted comment"), lines[0]
sig_blob = base64.b64decode(lines[1])
assert len(sig_blob) == 74, f"unexpected sig blob length {len(sig_blob)}"
sig_keynum, signature = sig_blob[2:10], sig_blob[10:74]
print(f"[sig] key_id={sig_keynum.hex()}")

# 3) 公钥（本地 .pub 文件是「base64(minisign 公钥文件文本)」）
pub_text = base64.b64decode(
    (REPO / "determinflow-updater.key.pub").read_text(encoding="utf-8").strip()
).decode("utf-8")
pub_lines = [ln for ln in pub_text.splitlines() if ln.strip()]
pub_blob = base64.b64decode(pub_lines[1])
assert len(pub_blob) == 42, f"unexpected pub blob length {len(pub_blob)}"
pub_keynum, pub_key = pub_blob[2:10], pub_blob[10:42]
print(f"[key] key_id={pub_keynum.hex()}")
assert pub_keynum == sig_keynum, "key id mismatch"

# 4) ed25519 验签（minisign Ed 方案：对消息的 blake2b-512 摘要签名）
message = hashlib.blake2b(data, digest_size=64).digest()
Ed25519PublicKey.from_public_bytes(pub_key).verify(signature, message)
print("[ed25519] signature VALID over blake2b-512(exe) — 与 tauri updater 验签链一致")
print("ALL CHECKS PASSED")
