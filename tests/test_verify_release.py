"""R132：发版验收脚本（``scripts/verify_release.py``）的判决与降级边界。

R31 用这个脚本验收过 v1.0.0，R32 把它参数化；但它此前**零用例**，且十处判断
全是裸 ``assert``——``python -O`` 会把判断整段删掉，脚本仍打印
``ALL CHECKS PASSED`` 并退 0。本文件钉住三件事：

- 判决不依赖 ``assert``：``-O`` 下同样的坏产物仍然退出 1；
- 三类失败互不冒充：判了不合格 1 / 没作判定 2 / 形状无效 4；
- 坏输入是可读拒因，不是 traceback（空 sha256、坏 base64、manifest 缺键、断网）。

全部用本地夹具，不联网、不读真实发布产物。
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import verify_release

KEYNUM = bytes.fromhex("0123456789abcdef")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py"


# ----------------------------------------------------------------------- 夹具
def _minisign_text(blob: bytes) -> str:
    """外层 base64 → 内层「注释行 + base64 数据行」（R31 取证的实测结构）。"""
    inner = ("untrusted comment: fixture\n"
             + base64.b64encode(blob).decode() + "\n")
    return base64.b64encode(inner.encode()).decode() + "\n"


class _Release:
    def __init__(self, tmp_path: Path) -> None:
        self.assets = tmp_path / "assets"
        self.assets.mkdir()
        self.root = tmp_path / "repo"
        (self.root / "desktop" / "src-tauri").mkdir(parents=True)
        self.version = "1.0.1"
        self.name = f"DeterminFlow_{self.version}_x64-setup.exe"
        self.exe = self.assets / self.name
        self.sig = self.assets / f"{self.name}.sig"
        self.sha = self.assets / f"{self.name}.sha256"
        self.pubkey = tmp_path / "updater.key.pub"
        self.tauri = self.root / "desktop" / "src-tauri" / "tauri.conf.json"
        self.private = Ed25519PrivateKey.generate()
        self._exe_bytes = b"fake installer bytes"
        self.exe.write_bytes(self._exe_bytes)
        self.sha.write_text(
            f"{hashlib.sha256(self._exe_bytes).hexdigest()}  {self.name}\n",
            encoding="utf-8")
        self.public_text = self._pub_text()
        self.pubkey.write_text(self.public_text, encoding="utf-8")
        self.sig.write_text(self._sig_text(), encoding="utf-8")
        self._write_tauri()

    # --- 组成部件
    def _pub_blob(self, keynum: bytes = KEYNUM) -> bytes:
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return b"Ed" + keynum + raw

    def _pub_text(self, keynum: bytes = KEYNUM) -> str:
        return _minisign_text(self._pub_blob(keynum))

    def _sig_text(self, payload: bytes | None = None,
                  keynum: bytes = KEYNUM) -> str:
        payload = self._exe_bytes if payload is None else payload
        signature = self.private.sign(
            hashlib.blake2b(payload, digest_size=64).digest())
        return _minisign_text(b"ED" + keynum + signature)

    def _write_tauri(self, *, version: str | None = None,
                     pubkey: str | None = None) -> None:
        self.tauri.write_text(json.dumps({
            "version": self.version if version is None else version,
            "plugins": {"updater": {
                "pubkey": self.public_text.strip() if pubkey is None else pubkey,
            }},
        }), encoding="utf-8")

    # --- 调用
    def run(self, monkeypatch: pytest.MonkeyPatch,
            *extra: str) -> int:
        monkeypatch.setattr(verify_release, "REPO_ROOT", self.root)
        return verify_release.main([
            "--tag", f"v{self.version}",
            "--assets-dir", str(self.assets),
            "--pubkey", str(self.pubkey),
            *extra,
        ])

    def manifest(self, *, version: str | None = None,
                 url: str | None = None,
                 signature: str | None = None) -> dict:
        return {
            "version": self.version if version is None else version,
            "platforms": {"windows-x86_64": {
                "url": url if url is not None else (
                    "https://github.com/zhijianmengrao/xs2/releases/download/"
                    f"v{self.version}/{self.name}"),
                "signature": (self.sig.read_text(encoding="utf-8").strip()
                              if signature is None else signature),
            }},
        }


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _serve(monkeypatch: pytest.MonkeyPatch, payload: dict | bytes) -> None:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    monkeypatch.setattr(
        verify_release.urllib.request, "urlopen",
        lambda *_a, **_k: _Response(body))


def _offline(release: _Release, monkeypatch: pytest.MonkeyPatch,
             *extra: str) -> int:
    return release.run(monkeypatch, "--skip-manifest", *extra)


# ------------------------------------------------------------------ 通过路径
def test_happy_path_passes_offline(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)

    assert _offline(release, monkeypatch) == 0

    out = capsys.readouterr().out
    assert "[sha256] OK" in out
    assert "[ed25519] signature VALID" in out
    assert "[config] tauri.conf version 与 tag 一致" in out
    assert "ALL CHECKS PASSED" in out


def test_manifest_happy_path_passes(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, release.manifest())

    assert release.run(monkeypatch) == 0


# ------------------------------------------------------------- 2：用法与环境
def test_missing_asset_is_environment(tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    release.sig.unlink()

    assert _offline(release, monkeypatch) == verify_release.EXIT_USAGE
    assert "缺少资产文件" in capsys.readouterr().out


def test_missing_pubkey_is_environment(tmp_path: Path,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.pubkey.unlink()

    assert _offline(release, monkeypatch) == verify_release.EXIT_USAGE


def test_empty_tag_is_environment(tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    monkeypatch.setattr(verify_release, "REPO_ROOT", release.root)

    assert verify_release.main([
        "--tag", "", "--assets-dir", str(release.assets),
        "--pubkey", str(release.pubkey), "--skip-manifest",
    ]) == verify_release.EXIT_USAGE


def test_network_failure_is_environment(tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch,
                                        capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)

    def boom(*_a, **_k):
        raise verify_release.urllib.error.URLError("connection reset")

    monkeypatch.setattr(verify_release.urllib.request, "urlopen", boom)

    assert release.run(monkeypatch) == verify_release.EXIT_USAGE
    assert "无法读取 latest.json" in capsys.readouterr().out


# ----------------------------------------------------------------- 4：形状无效
def test_empty_sha256_asset_is_shape(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.sha.write_text("", encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE


def test_sha256_not_hex_is_shape(tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.sha.write_text(f"{'z' * 64}  {release.name}\n", encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE


def test_bad_outer_base64_is_shape(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    release.sig.write_text("not base64 !!", encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE
    assert "base64" in capsys.readouterr().out


def test_comment_line_is_required(tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    # 两行齐全、blob 长度也对：只有「首行必须是 minisign 注释」能拦住它。
    inner = ("not a comment\n"
             + base64.b64encode(b"ED" + KEYNUM + b"\x00" * 64).decode() + "\n")
    release.sig.write_text(base64.b64encode(inner.encode()).decode(),
                           encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE
    assert "minisign 注释" in capsys.readouterr().out


def test_sig_blob_length_is_shape(tmp_path: Path,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.sig.write_text(_minisign_text(b"ED" + KEYNUM + b"\x00" * 63),
                           encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE


def test_pubkey_blob_length_is_shape(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.pubkey.write_text(_minisign_text(b"Ed" + KEYNUM + b"\x00" * 31),
                              encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE


def test_tauri_conf_not_json_is_shape(tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.tauri.write_text("{not json", encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_SHAPE


def test_manifest_not_json_is_shape(tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, b"<html>502</html>")

    assert release.run(monkeypatch) == verify_release.EXIT_SHAPE


def test_manifest_missing_platform_is_shape(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, {"version": release.version, "platforms": {}})

    assert release.run(monkeypatch) == verify_release.EXIT_SHAPE
    assert "windows-x86_64" in capsys.readouterr().out


# --------------------------------------------------------------- 1：判了不合格
def test_sha256_mismatch_fails(tmp_path: Path,
                               monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    release.sha.write_text(f"{'0' * 64}  {release.name}\n", encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_FAIL
    assert "sha256 不符" in capsys.readouterr().out


def test_keynum_mismatch_fails(tmp_path: Path,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release.pubkey.write_text(
        release._pub_text(bytes.fromhex("fedcba9876543210")),
        encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_FAIL


def test_invalid_signature_fails(tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch,
                                 capsys: pytest.CaptureFixture) -> None:
    release = _Release(tmp_path)
    release.sig.write_text(release._sig_text(payload=b"other bytes"),
                           encoding="utf-8")

    assert _offline(release, monkeypatch) == verify_release.EXIT_FAIL
    assert "ed25519 验签失败" in capsys.readouterr().out


def test_tauri_version_mismatch_fails(tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release._write_tauri(version="9.9.9")

    assert _offline(release, monkeypatch) == verify_release.EXIT_FAIL


def test_tauri_pubkey_mismatch_fails(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    release._write_tauri(pubkey="another-key")

    assert _offline(release, monkeypatch) == verify_release.EXIT_FAIL


def test_manifest_version_mismatch_fails(tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, release.manifest(version="9.9.9"))

    assert release.run(monkeypatch) == verify_release.EXIT_FAIL


def test_manifest_url_mismatch_fails(tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, release.manifest(url="https://evil.example/x.exe"))

    assert release.run(monkeypatch) == verify_release.EXIT_FAIL


def test_manifest_signature_mismatch_fails(tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    release = _Release(tmp_path)
    _serve(monkeypatch, release.manifest(signature="different-signature"))

    assert release.run(monkeypatch) == verify_release.EXIT_FAIL


# ------------------------------------------------------- 判决不依赖 assert（-O）
def test_optimized_mode_still_rejects_a_bad_sha256(tmp_path: Path) -> None:
    release = _Release(tmp_path)
    release.sha.write_text(f"{'0' * 64}  {release.name}\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-O", str(SCRIPT),
         "--tag", f"v{release.version}",
         "--assets-dir", str(release.assets),
         "--pubkey", str(release.pubkey), "--skip-manifest"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")

    assert completed.returncode == verify_release.EXIT_FAIL, completed.stdout
    assert "ALL CHECKS PASSED" not in completed.stdout


def test_usage_requires_tag_and_assets_dir() -> None:
    with pytest.raises(SystemExit) as excinfo:
        verify_release.main([])

    assert excinfo.value.code == verify_release.EXIT_USAGE
