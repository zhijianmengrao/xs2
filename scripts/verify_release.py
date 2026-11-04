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

R132：这是发版前的**判决脚本**，但此前十处判断全是裸 ``assert``——``python -O``
会把它们整段删掉，脚本仍打印 ``ALL CHECKS PASSED`` 并退 0；坏输入（空
``.sha256``、坏 base64、manifest 缺键、网络失败）则各有各的 traceback。
现在判断改成显式抛出、按类别收口：

- ``0`` 通过；
- ``1`` 判了，且不合格（摘要不符、key id 不符、验签失败、版本/URL/signature 不符）；
- ``2`` 用法或环境问题（参数错、缺文件、读不开、网络不可达）——没作判定；
- ``4`` 资产形状无效（不是合法 base64、blob 长度不对、sha256 行不是 64 位十六进制、
  tauri.conf / latest.json 结构不对）——同样没作判定。

``-O`` 下仍然按上面的语义退出：判决不依赖 ``assert``。

用法（在已下载资产的目录里执行）：
  python scripts/verify_release.py --tag v1.0.1 --assets-dir <dir> [--full]
资产下载（大陆网络建议 curl -C - 断点续传）：
  curl -sLO https://github.com/<repo>/releases/download/<tag>/DeterminFlow_<ver>_x64-setup.exe{,.sig,.sha256}
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SHAPE = 4

_SHA256_LINE = re.compile(r"^[0-9a-fA-F]{64}$")


class VerificationFailure(Exception):
    """判了，且不合格（退出 1）。"""


class AssetShapeError(Exception):
    """资产能读到，但结构不是预期形状（退出 4）。"""


class EnvironmentProblem(Exception):
    """缺输入 / 读不开 / 网络不可达——没作判定（退出 2）。"""


def _read_text(path: Path, what: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvironmentProblem(f"无法读取{what} {path}：{exc}") from exc


def _b64decode(text: str, what: str) -> bytes:
    try:
        return base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AssetShapeError(f"{what} 不是合法 base64：{exc}") from exc


def _minisign_blob(path: Path, what: str, expected: int) -> bytes:
    """外层 base64 → 内层文本 → 第二行 base64 → 定长 blob。"""
    inner = _b64decode(_read_text(path, what), what).decode("utf-8", "replace")
    lines = [line for line in inner.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("untrusted comment"):
        first = lines[0] if lines else ""
        raise AssetShapeError(f"{what} 首行不是 minisign 注释：{first!r}")
    if len(lines) < 2:
        raise AssetShapeError(f"{what} 只有注释行，没有签名/公钥数据")
    blob = _b64decode(lines[1], f"{what} 的数据行")
    if len(blob) != expected:
        raise AssetShapeError(
            f"{what} blob 长度 {len(blob)}，期望 {expected}")
    return blob


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def _sha256_expected(path: Path) -> str:
    text = _read_text(path, "sha256 资产")
    tokens = text.split()
    if not tokens:
        raise AssetShapeError(f"sha256 资产为空：{path}")
    expected = tokens[0].strip()
    if not _SHA256_LINE.match(expected):
        raise AssetShapeError(
            f"sha256 资产首列不是 64 位十六进制：{expected!r}")
    return expected.lower()


def _load_manifest(options: argparse.Namespace) -> dict:
    url = f"https://github.com/{options.repo}/releases/latest/download/latest.json"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, UnicodeError) as exc:
        raise EnvironmentProblem(f"无法读取 latest.json（{url}）：{exc}") from exc
    try:
        manifest = json.loads(raw)
    except ValueError as exc:
        raise AssetShapeError(f"latest.json 无法解析：{exc}") from exc
    if not isinstance(manifest, dict):
        raise AssetShapeError("latest.json 顶层不是对象")
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        raise AssetShapeError("latest.json 缺 platforms 对象")
    platform = platforms.get("windows-x86_64")
    if not isinstance(platform, dict):
        raise AssetShapeError("latest.json 缺 platforms.windows-x86_64")
    for field in ("url", "signature"):
        if not isinstance(platform.get(field), str):
            raise AssetShapeError(f"latest.json 的 windows-x86_64.{field} 不是字符串")
    if not isinstance(manifest.get("version"), str):
        raise AssetShapeError("latest.json 的 version 不是字符串")
    return manifest


def _verify(options: argparse.Namespace) -> int:
    version = options.tag[1:] if options.tag.startswith("v") else options.tag
    if not version:
        raise EnvironmentProblem("--tag 不能为空")
    suffix = "_x64-full-setup.exe" if options.full else "_x64-setup.exe"
    installer_name = f"DeterminFlow_{version}{suffix}"
    exe = options.assets_dir / installer_name
    sig_asset = options.assets_dir / f"{installer_name}.sig"
    sha_asset = options.assets_dir / f"{installer_name}.sha256"

    for path in (exe, sig_asset, sha_asset):
        if not path.is_file():
            raise EnvironmentProblem(f"缺少资产文件：{path}")

    # 1) sha256
    try:
        data = exe.read_bytes()
    except OSError as exc:
        raise EnvironmentProblem(f"无法读取安装器 {exe}：{exc}") from exc
    digest = hashlib.sha256(data).hexdigest()
    expected = _sha256_expected(sha_asset)
    print(f"[sha256] computed={digest}")
    print(f"[sha256] asset  ={expected}")
    _require(digest == expected, "sha256 不符")
    print("[sha256] OK")

    # 2) minisign 验签
    sig_blob = _minisign_blob(sig_asset, "签名资产", 74)
    sig_keynum, signature = sig_blob[2:10], sig_blob[10:74]

    pub_blob = _minisign_blob(options.pubkey, "公钥文件", 42)
    pub_keynum, pub_key = pub_blob[2:10], pub_blob[10:42]
    _require(pub_keynum == sig_keynum, "key id 不符：签名不是这把公钥签的")
    print(f"[sig] key_id={sig_keynum.hex()}（两端一致）")

    message = hashlib.blake2b(data, digest_size=64).digest()
    try:
        Ed25519PublicKey.from_public_bytes(pub_key).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise VerificationFailure(
            f"ed25519 验签失败：blake2b-512(installer) 与 .sig 不匹配（{exc}）") from exc
    print("[ed25519] signature VALID over blake2b-512(installer) — 与 tauri updater 同链")

    # 3) tauri.conf 版本一致性 + pubkey 与本地公钥逐字一致
    tauri_path = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
    try:
        tauri = json.loads(_read_text(tauri_path, "tauri.conf"))
    except ValueError as exc:
        raise AssetShapeError(f"tauri.conf 无法解析：{exc}") from exc
    if not isinstance(tauri, dict):
        raise AssetShapeError("tauri.conf 顶层不是对象")

    def find_pubkey(obj):
        if isinstance(obj, dict):
            if "pubkey" in obj:
                return obj["pubkey"]
            for value in obj.values():
                found = find_pubkey(value)
                if found:
                    return found
        return None

    _require(tauri.get("version") == version,
             f"tauri.conf version {tauri.get('version')} != tag {version}")
    _require(find_pubkey(tauri) == _read_text(options.pubkey, "公钥文件").strip(),
             "tauri.conf updater pubkey 与本地公钥文件不一致")
    print("[config] tauri.conf version 与 tag 一致；updater pubkey 与本地公钥逐字一致")

    # 4) latest.json 端点
    if not options.skip_manifest:
        manifest = _load_manifest(options)
        platform = manifest["platforms"]["windows-x86_64"]
        _require(manifest["version"] == version,
                 f"latest.json version {manifest['version']} != {version}")
        _require(platform["url"] == (
            f"https://github.com/{options.repo}/releases/download/"
            f"{options.tag}/{installer_name}"),
            f"latest.json url 指向异常: {platform['url']}")
        _require(platform["signature"].strip()
                 == _read_text(sig_asset, "签名资产").strip(),
                 "latest.json signature 与 .sig 资产不一致")
        print("[manifest] latest.json 端点校验通过（version/url/signature 三项一致）")

    print("ALL CHECKS PASSED")
    return EXIT_PASS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="例如 v1.0.1")
    parser.add_argument("--assets-dir", type=Path, required=True,
                        help="存放已下载 exe/.sig/.sha256 的目录")
    parser.add_argument("--full", action="store_true", help="验收 Full 安装器（默认 Core）")
    parser.add_argument("--repo", default="zhijianmengrao/xs2")
    parser.add_argument("--pubkey", type=Path,
                        default=REPO_ROOT / "determinflow-updater.key.pub")
    parser.add_argument("--skip-manifest", action="store_true",
                        help="跳过 latest.json 端点校验（离线环境）")
    options = parser.parse_args(argv)

    try:
        return _verify(options)
    except EnvironmentProblem as exc:
        print(f"[error] {exc}")
        return EXIT_USAGE
    except AssetShapeError as exc:
        print(f"[shape] {exc}")
        return EXIT_SHAPE
    except VerificationFailure as exc:
        print(f"[fail] {exc}")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
