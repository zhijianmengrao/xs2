"""R173：开发代理端口 ↔ 后端端口（W 系续 W17）。

背景（实测，R172 §3 登记）：``web/vite.config.ts`` 的开发代理把 ``/api``
与 ``/ws`` 转发到后端：

- ``target: "http://localhost:8020"``（HTTP）
- ``target: "ws://localhost:8020"``（WebSocket）

R165 的 W13 已钉生产容器面的八个端口写入点，但明确把 Vite 开发代理留在
射程外（它是本地开发链路，不是生产声明面）。这条边仍然是第二份账：
后端改 ``WEB_PORT`` 而代理没改，``npm run dev`` 下所有 API 调用都会
连接拒绝，且报错只出现在浏览器控制台。

W17 把这条边钉住：

- **W17a 语料守卫**：``web/vite.config.ts`` 恰好解析出 2 个代理目标
  （HTTP + WS），``src/config.py`` 的 ``WEB_PORT`` 默认值恰一处。
- **W17b 代理端口同账**：两个 target 的端口都 == config 默认值；
  协议（``http`` / ``ws``）不参与——它们是代理类型，不是端口账。

边界：只判 Vite 代理的端口——不判代理路径（``/api`` / ``/ws`` 的路由
语义）、不判 ``server.port: 5173``（前端开发服务器自己的端口）、不判
``web/dist`` 产物（构建面由 CI 的 ``npm run build`` 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PY = REPO_ROOT / "src" / "config.py"
VITE_CONFIG = REPO_ROOT / "web" / "vite.config.ts"

CONFIG_PORT_RX = re.compile(
    r'^WEB_PORT\s*=\s*_get_int_config\(\s*"WEB_PORT"\s*,\s*(\d+)\s*\)',
    re.M,
)
PROXY_TARGET_RX = re.compile(
    r'target:\s*"(?:https?|wss?)://localhost:(\d+)"'
)


def _canonical_port() -> int:
    ports = CONFIG_PORT_RX.findall(CONFIG_PY.read_text(encoding="utf-8"))
    assert len(ports) == 1, (
        f"src/config.py 的 WEB_PORT 默认值应恰好一处，实际 {ports}"
        "——W17 无锚"
    )
    return int(ports[0])


def _proxy_ports() -> list[int]:
    ports = [
        int(port)
        for port in PROXY_TARGET_RX.findall(
            VITE_CONFIG.read_text(encoding="utf-8")
        )
    ]
    return ports


def test_dev_proxy_targets_are_parseable() -> None:
    """W17a：Vite 配置恰好两个代理目标，config 端口锚唯一。"""
    ports = _proxy_ports()
    assert len(ports) == 2, (
        f"web/vite.config.ts 解析到 {len(ports)} 个代理目标：{ports}"
        "——W17 的覆盖面缩水了（预期 HTTP + WS 各一）"
    )
    _canonical_port()


def test_dev_proxy_ports_agree_with_config() -> None:
    """W17b：两个代理目标的端口都 == config 的 WEB_PORT 默认值。"""
    canonical = _canonical_port()
    violations = [
        f"第 {position} 个代理目标写 {port}，config 默认值是 {canonical}"
        for position, port in enumerate(_proxy_ports(), 1)
        if port != canonical
    ]
    assert not violations, (
        "Vite 开发代理端口与后端不同账：\n" + "\n".join(violations)
    )
