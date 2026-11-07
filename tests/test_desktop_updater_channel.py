"""R202：更新通道清单端到端同账（W 系续 W35）。

背景（实测，R200 §3 登记）：桌面更新通道的清单有两份账——

- 消费端：``desktop/src-tauri/tauri.conf.json`` 的
  ``plugins.updater.endpoints`` 恰一处
  ``https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json``
  （updater 启动时拉它判断有无新版本）；
- 生产端：``desktop-windows.yml`` 的 create_update_manifest 用
  ``--base-url "https://github.com/${{ github.repository }}/releases/
  download/$RELEASE_TAG"`` 生成 ``--output release-assets/latest.json``，
  再 ``gh release upload`` 传到 release（``releases/latest/download/``
  是 GitHub 对最新 release 下载地址的别名，与
  ``releases/download/<tag>`` 同键族）。

两段任何一段单侧漂移：清单改名而端点没跟 → updater 拉 404，更新
通道静默断；仓库改名而端点的**硬编码** owner/repo 没跟（workflow
侧 ``${{ github.repository }}`` 永远跟走）→ 同样 404。updater 的
失败只发生在用户机器上，CI 看不见。

W35 把这条边钉成两半：

- **W35a 语料守卫**：tauri 端点数组恰一个条目且形状是
  ``github.com/<owner>/<repo>/releases/latest/download/<file>.json``；
  desktop-windows 的 ``--base-url``（``github.repository`` 表达式 +
  ``/releases/download/``）与 ``--output release-assets/<file>`` 各
  恰一处。
- **W35b 端到端同账**：端点文件名 == ``--output`` 文件名（清单改名
  两端必须同改）；端点的 owner/repo == git ``origin`` 的 owner/repo
  （仓库身份同账——仓库改名/搬移时端点显式红，不再静默 404）。

边界：只判端点/清单的字面同账——不判 updater 的运行行为与签名校验
（tauri 运行时负责）、不判 ``latest.json`` 内容结构（create_update_
manifest 的输出形状有自己的判据面）、不判 ``gh release upload`` 的
执行（CI 负责）；git 不可用显式红不 skip（R136 纪律）。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_CONF = REPO_ROOT / "desktop" / "src-tauri" / "tauri.conf.json"
WINDOWS_WF = REPO_ROOT / ".github" / "workflows" / "desktop-windows.yml"

ENDPOINTS_BLOCK_RX = re.compile(r'"endpoints"\s*:\s*\[([^\]]*)\]')
ENDPOINT_URL_RX = re.compile(
    r'"(https://github\.com/([^/"\s]+)/([^/"\s]+)'
    r"/releases/latest/download/([^/\"\s]+\.json))\""
)
BASE_URL_RX = re.compile(
    r'--base-url "https://github\.com/\$\{\{ github\.repository \}\}'
    r'/releases/download/([^"\s]+)"'
)
OUTPUT_RX = re.compile(r'--output (release-assets/[^"\s]+)')


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _origin_owner_repo() -> str:
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert proc.returncode == 0, (
        f"git remote get-url origin 失败（退出码 {proc.returncode}）："
        f"{proc.stderr.strip()[:200]}——git 不可用显式红，不 skip（R136 纪律）"
    )
    url = proc.stdout.strip()
    match = re.search(r"github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", url)
    assert match, f"origin URL 解析不出 owner/repo：{url!r}——W35b 无锚"
    return match.group(1)


def _endpoint() -> tuple[str, str, str]:
    """返回 (完整 URL, owner/repo, 文件名)；恰一条由 W35a 守。"""
    block = ENDPOINTS_BLOCK_RX.search(_text(TAURI_CONF))
    assert block, "tauri.conf.json 没有 plugins.updater.endpoints 数组"
    urls = ENDPOINT_URL_RX.findall(block.group(1))
    assert urls, "updater 端点数组没有 github.com/<owner>/<repo>/… 条目"
    return urls[0][0], f"{urls[0][1]}/{urls[0][2]}", urls[0][3]


def test_updater_channel_anchors() -> None:
    """W35a：端点恰一条 + --base-url/--output 各恰一处（形状守卫）。"""
    block = ENDPOINTS_BLOCK_RX.search(_text(TAURI_CONF))
    assert block, "tauri.conf.json 没有 endpoints 数组——W35a 无锚"
    urls = ENDPOINT_URL_RX.findall(block.group(1))
    assert len(urls) == 1, (
        f"updater 端点数组应恰一条 github.com/…/latest/download/<file>.json，"
        f"实测 {len(urls)} 条——W35a 语料守卫"
    )
    text = _text(WINDOWS_WF)
    bases = BASE_URL_RX.findall(text)
    assert len(bases) == 1, (
        f"desktop-windows.yml 的 --base-url（github.repository + "
        f"releases/download）应恰一处，实测 {len(bases)} 处——W35a 语料守卫"
    )
    outputs = OUTPUT_RX.findall(text)
    assert len(outputs) == 1, (
        f"desktop-windows.yml 的 --output release-assets/<file> 应恰一处，"
        f"实测 {len(outputs)} 处——W35a 语料守卫"
    )


def test_updater_manifest_file_and_repo_agree() -> None:
    """W35b：端点文件名 == --output 文件名；端点 owner/repo == git origin。"""
    _url, endpoint_repo, endpoint_file = _endpoint()
    outputs = OUTPUT_RX.findall(_text(WINDOWS_WF))
    output_file = outputs[0].rsplit("/", 1)[-1]
    assert endpoint_file == output_file, (
        f"更新清单文件名不同账：tauri 端点拉 {endpoint_file!r}，workflow "
        f"产出 {output_file!r}——清单改名两端必须同改，否则 updater 404"
    )
    origin_repo = _origin_owner_repo()
    assert endpoint_repo == origin_repo, (
        f"更新通道仓库身份不同账：tauri 端点硬编码 {endpoint_repo!r}，"
        f"git origin 是 {origin_repo!r}——仓库改名/搬移时端点必须同改"
        "（workflow 侧 github.repository 自动跟走，端点不会）"
    )
