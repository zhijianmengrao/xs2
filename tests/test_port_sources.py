"""R165：端口五源同账——Dockerfile / compose / config / README（W 系续 W13）。

背景（实测，R164 §7 登记、R165 开工复核）：Web 端口 ``8020`` 在仓库里有
六处独立写入点，此前只有容器契约测试钉 ``CMD`` 字符串本身，没有任何一处
跨源对账：

- ``src/config.py``：``WEB_PORT = _get_int_config("WEB_PORT", 8020)``
  （运行时默认值，是唯一能执行出结果的锚）；
- ``run.py``：``port = int(os.getenv("WEB_PORT", "8020"))``（开发入口的
  兜底值）；``.env.example``：``WEB_PORT=8020``（用户复制的环境模板）；
- ``Dockerfile``：``EXPOSE 8020``、``HEALTHCHECK`` 的
  ``http://localhost:8020/docs``、``CMD`` 的 ``--bind 0.0.0.0:8020``；
- ``docker-compose.yml``：``ports: "8020:8020"``（宿主机与容器两端）与
  ``environment.WEB_PORT: "8020"``；
- ``README.md`` / ``README.en.md``：各两处 ``localhost:8020``
  （Web UI 与 API 文档）。

改端口要动八处：只改 compose 的映射而不改 ``EXPOSE``，容器构建的元数据
与端口声明就会分叉；只改 README 而不改 config，读者照着文档访问会得到
连接拒绝；只改 config 而漏了 ``run.py`` 的兜底值，开发入口仍起在旧端口。
本文件把这条面钉住：

- **W13a 语料守卫**：八个写入点都必须能解析出端口，且形状唯一
  （``EXPOSE`` / ``--bind`` / healthcheck / compose ports / compose
  ``WEB_PORT`` / config 默认值 / ``run.py`` 兜底值 / ``.env.example``
  各恰一处；两份 README 各至少一处）。任一锚点消失显式红，
  防止 W13b 静默少判一个源。
- **W13b 端口同账**：``config`` 默认值是唯一锚，其余写入点的每个端口
  字面量（含 compose 的宿主机与容器两端）必须逐项相等。任一处漏改
  都红，且报告里指出是哪个源、写了什么。

边界：只判 Web 端口这一个数——不判 ``EXPOSE`` 与 ``ports`` 语义是否
合理（那是编排设计）、不判 README 的协议/主机名（``http://`` 与
``localhost`` 是文档惯例）、不判 ``web/`` 前端的开发代理端口
（``vite.config`` 是另一条开发链路，不在生产容器面）、不判
``start_determinflow.sh`` 的展示/诊断文案（启动器自带固定文案，不是
服务端声明面）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PY = REPO_ROOT / "src" / "config.py"
RUN_PY = REPO_ROOT / "run.py"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE = REPO_ROOT / "docker-compose.yml"
READMES = (REPO_ROOT / "README.md", REPO_ROOT / "README.en.md")

CONFIG_PORT_RX = re.compile(
    r'^WEB_PORT\s*=\s*_get_int_config\(\s*"WEB_PORT"\s*,\s*(\d+)\s*\)',
    re.M,
)
RUN_PORT_RX = re.compile(
    r'os\.getenv\(\s*"WEB_PORT"\s*,\s*"(\d+)"\s*\)'
)
ENV_EXAMPLE_PORT_RX = re.compile(r"^WEB_PORT\s*=\s*(\d+)\s*$", re.M)
EXPOSE_RX = re.compile(r"^EXPOSE\s+(\d+)\s*$", re.M)
BIND_RX = re.compile(r'"--bind"\s*,\s*"([0-9.]+):(\d+)"')
LOCALHOST_PORT_RX = re.compile(r"localhost:(\d+)")


def _canonical_port() -> int:
    """从 config 的 ``_get_int_config("WEB_PORT", N)`` 取唯一端口锚。"""
    text = CONFIG_PY.read_text(encoding="utf-8")
    ports = CONFIG_PORT_RX.findall(text)
    assert len(ports) == 1, (
        f"src/config.py 的 WEB_PORT 默认值应恰好解析出一处，实际 {ports}"
        "——W13 无锚或锚不唯一"
    )
    return int(ports[0])


def _entry_point_ports() -> dict[str, list[int]]:
    run_text = RUN_PY.read_text(encoding="utf-8")
    run_ports = [int(p) for p in RUN_PORT_RX.findall(run_text)]
    assert len(run_ports) == 1, (
        f"run.py 的 WEB_PORT 兜底值应恰好一处，实际 {run_ports}"
    )
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8-sig")
    env_ports = [int(p) for p in ENV_EXAMPLE_PORT_RX.findall(env_text)]
    assert len(env_ports) == 1, (
        f".env.example 的 WEB_PORT 应恰好一处，实际 {env_ports}"
    )
    return {"run.py 兜底值": run_ports, ".env.example": env_ports}


def _dockerfile_ports() -> dict[str, list[int]]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    exposed = [int(p) for p in EXPOSE_RX.findall(text)]
    binds = [int(port) for _, port in BIND_RX.findall(text)]
    health = [int(p) for p in LOCALHOST_PORT_RX.findall(text)]
    assert len(exposed) == 1, (
        f"Dockerfile 的 EXPOSE 应恰好一处，实际 {exposed}"
    )
    assert len(binds) == 1, (
        f"Dockerfile CMD 的 --bind 端口应恰好一处，实际 {binds}"
    )
    assert len(health) == 1, (
        f"Dockerfile 的 healthcheck localhost 端口应恰好一处，实际 {health}"
    )
    return {"EXPOSE": exposed, "CMD --bind": binds, "HEALTHCHECK": health}


def _compose_ports() -> dict[str, list[int]]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = (document or {}).get("services") or {}
    app = services.get("app")
    assert isinstance(app, dict), (
        "docker-compose.yml 缺少 services.app——W13 的 compose 面失锚"
    )
    mappings = app.get("ports") or []
    assert isinstance(mappings, list) and len(mappings) == 1, (
        f"services.app.ports 应恰好一条映射，实际 {mappings!r}"
    )
    mapping = str(mappings[0])
    match = re.fullmatch(r"(\d+):(\d+)", mapping.strip())
    assert match, f"services.app.ports 不是 H:C 形状：{mapping!r}"
    environment = app.get("environment") or {}
    assert isinstance(environment, dict), (
        "services.app.environment 不是映射——W13 的 WEB_PORT 面失锚"
    )
    assert "WEB_PORT" in environment, (
        "services.app.environment 缺 WEB_PORT——compose 的端口面失锚"
    )
    raw = str(environment["WEB_PORT"])
    assert raw.isdigit(), f"compose WEB_PORT 不是纯端口字面量：{raw!r}"
    return {
        "compose ports (host)": [int(match.group(1))],
        "compose ports (container)": [int(match.group(2))],
        "compose WEB_PORT": [int(raw)],
    }


def _readme_ports() -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for path in READMES:
        text = path.read_text(encoding="utf-8-sig")
        ports = [int(p) for p in LOCALHOST_PORT_RX.findall(text)]
        assert ports, (
            f"{path.name} 没有 localhost:<port>——README 的端口面失锚"
        )
        out[path.name] = ports
    return out


def _all_sources() -> dict[str, list[int]]:
    sources: dict[str, list[int]] = {
        "src/config.py WEB_PORT": [_canonical_port()],
    }
    sources.update(_entry_point_ports())
    sources.update(_dockerfile_ports())
    sources.update(_compose_ports())
    sources.update(_readme_ports())
    return sources


def test_port_sources_are_parseable() -> None:
    """W13a：八个端口写入点都能解析出端口，且形状唯一。"""
    sources = _all_sources()
    assert len(sources) >= 11, (
        f"端口源只解析出 {len(sources)} 个——W13 的覆盖面缩水了"
    )
    for name, ports in sources.items():
        assert ports, f"{name} 没有解析出端口——W13b 会静默少判一个源"


def test_port_literals_agree() -> None:
    """W13b：所有端口字面量 == config 的 WEB_PORT 默认值。"""
    canonical = _canonical_port()
    violations = [
        f"{name} 写 {ports}，config 默认值是 {canonical}"
        for name, ports in _all_sources().items()
        if any(port != canonical for port in ports)
    ]
    assert not violations, (
        "端口写入点不同账：\n" + "\n".join(violations)
    )
