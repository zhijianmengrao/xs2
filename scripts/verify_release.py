"""桌面发版验收脚本（R32 自 verify_release_v100.py 参数化）。

对指定 tag 的已发布 GitHub Release 做本地端到端验收：
1. 下载产物 sha256 与 release 资产 .sha256 一致；
2. .sig（外层 base64 解包后的 minisign 签名）能用本仓库公钥
   （默认 determinflow-updater.key.pub，须与 tauri.conf.json updater pubkey
   一致——脚本会做逐字比对）通过 ed25519 验签，算法与桌面更新器相同
   （blake2b-512 预哈希）；
3. tauri.conf.json 版本与 tag 一致（workflow 构建时也校验，双保险）；
4. updater 端点 latest.json：version 匹配、安装器 URL 指向本仓库本 tag、
   signature 字段与本地 .sig 逐字一致。

实测签名结构（R31 取证）：pubkey blob 42B = algo("Ed") + keynum(8) + key(32)；
sig blob 74B = algo("ED") + keynum(8) + signature(64)；keynum 两端一致。

用法（在已下载资产的目录里执行）：
  python scripts/verify_release.py --tag v1.0.1 --assets-dir <dir> [--full]
资产下载（大陆网络建议 curl -C - 断点续传）：
  curl -sLO https://github.com/<repo>/releases/download/<tag>/DeterminFlow_<ver>_x64-setup.exe{,.sig,.sha256}
"""
import argparse
import base64
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="例如 v1.0.1")
    parser.add_argument("--assets-dir", type=Path, required=True,
                        help="存放已下载 exe/.sig/.sha256 的目录")
    parser.add_argument("--full", action="store_true", help="验收 Full 安装器（默认 Core）")
    parser.add_argument("--repo", default="zhijianmengrao/xs2")
    parser.add_argument("--pubkey", type=Path, default=REPO_ROOT / "determinflow-updater.key.pub")
    parser.add_argument("--skip-manifest", action="store_true",
                        help="跳过 latest.json 端点校验（离线环境）")
    options = parser.parse_args()

    version = options.tag[1:] if options.tag.startswith("v") else options.tag
    suffix = "_x64-full-setup.exe" if options.full else "_x64-setup.exe"
    installer_name = f"DeterminFlow_{version}{suffix}"
    exe = options.assets_dir / installer_name
    sig_asset = options.assets_dir / f"{installer_name}.sig"
    sha_asset = options.assets_dir / f"{installer_name}.sha256"

    for path in (exe, sig_asset, sha_asset):
        if not path.is_file():
            print(f"[error] 缺少资产文件: {path}")
            return 1

    # 1) sha256
    data = exe.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    expected = sha_asset.read_text(encoding="utf-8").split()[0].strip()
    print(f"[sha256] computed={digest}")
    print(f"[sha256] asset  ={expected}")
    assert digest == expected, "sha256 mismatch"
    print("[sha256] OK")

    # 2) minisign 验签
    sig_text = base64.b64decode(sig_asset.read_text(encoding="utf-8").strip()).decode("utf-8")
    lines = [ln for ln in sig_text.splitlines() if ln.strip()]
    assert lines[0].startswith("untrusted comment"), lines[0]
    sig_blob = base64.b64decode(lines[1])
    assert len(sig_blob) == 74, f"unexpected sig blob length {len(sig_blob)}"
    sig_keynum, signature = sig_blob[2:10], sig_blob[10:74]

    pub_text = base64.b64decode(options.pubkey.read_text(encoding="utf-8").strip()).decode("utf-8")
    pub_lines = [ln for ln in pub_text.splitlines() if ln.strip()]
    pub_blob = base64.b64decode(pub_lines[1])
    assert len(pub_blob) == 42, f"unexpected pub blob length {len(pub_blob)}"
    pub_keynum, pub_key = pub_blob[2:10], pub_blob[10:42]
    assert pub_keynum == sig_keynum, "key id mismatch"
    print(f"[sig] key_id={sig_keynum.hex()}（两端一致）")

    message = hashlib.blake2b(data, digest_size=64).digest()
    Ed25519PublicKey.from_public_bytes(pub_key).verify(signature, message)
    print("[ed25519] signature VALID over blake2b-512(installer) — 与 tauri updater 同链")

    # 3) tauri.conf 版本一致性 + pubkey 与本地公钥逐字一致
    tauri = json.loads((REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))

    def find_pubkey(obj):
        if isinstance(obj, dict):
            if "pubkey" in obj:
                return obj["pubkey"]
            for value in obj.values():
                found = find_pubkey(value)
                if found:
                    return found
        return None

    assert tauri.get("version") == version, f"tauri.conf version {tauri.get('version')} != tag {version}"
    assert find_pubkey(tauri) == options.pubkey.read_text(encoding="utf-8").strip(), \
        "tauri.conf updater pubkey 与本地公钥文件不一致"
    print("[config] tauri.conf version 与 tag 一致；updater pubkey 与本地公钥逐字一致")

    # 4) latest.json 端点
    if not options.skip_manifest:
        manifest_url = f"https://github.com/{options.repo}/releases/latest/download/latest.json"
        with urllib.request.urlopen(manifest_url, timeout=60) as response:
            manifest = json.loads(response.read().decode("utf-8"))
        platform = manifest["platforms"]["windows-x86_64"]
        assert manifest["version"] == version, f"latest.json version {manifest['version']} != {version}"
        assert platform["url"] == (
            f"https://github.com/{options.repo}/releases/download/{options.tag}/{installer_name}"
        ), f"latest.json url 指向异常: {platform['url']}"
        assert platform["signature"].strip() == sig_asset.read_text(encoding="utf-8").strip(), \
            "latest.json signature 与 .sig 资产不一致"
        print(f"[manifest] latest.json 端点校验通过（version/url/signature 三项一致）")

    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
