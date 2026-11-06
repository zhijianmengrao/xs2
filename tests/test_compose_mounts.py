"""R171：compose 挂载点 ↔ config 目录默认值（W 系续 W16）。

背景（实测，R168 §3 登记）：``docker-compose.yml`` 给 app 挂三个卷——

- ``./data:/app/data``
- ``./logs:/app/logs``
- ``./config:/app/config``

它们的容器内目标必须与 ``src/config.py`` 的三个目录默认值落在同一处：
``DATA_DIR = BASE_DIR / "data"``、``LOGS_DIR = BASE_DIR / "logs"``、
``CONFIG_DIR = BASE_DIR / "config"``。容器里代码位于 ``/app/src/config.py``，
所以 ``BASE_DIR`` 就是 Dockerfile 的运行时 ``WORKDIR /app``。三种静默
漂移：

- 卷挂到 ``/app/dta``：容器把数据写进镜像层，重启即丢；
- 宿主机源目录与容器目录不同名（``./mydata:/app/data``）：运维在
  ``./data`` 里找数据找不到；
- 少挂一个卷：该目录退回容器可写层，``docker compose down`` 即清空。

W16 把这三条钉住：

- **W16a 语料守卫**：compose 恰有 3 个卷、config 恰解析出 3 个目录默认值、
  Dockerfile 有运行时 ``WORKDIR``。任一面缺失显式红。
- **W16b 挂载点同账**：三个容器目标集合 == ``WORKDIR/<目录名>`` 集合；
  每个卷的宿主机源 basename == 目录名（``./data`` ↔ ``data``）。

边界：只判 app 服务的三个持久化目录——不判卷的读写权限、不判 bind
mount 与 named volume 的类型选择、不判 ``./data`` 等源目录是否已存在
（compose 会自动创建，CI 检出树里通常没有）；不判其它服务的卷。
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"
CONFIG_PY = REPO_ROOT / "src" / "config.py"
DOCKERFILE = REPO_ROOT / "Dockerfile"

DIR_RX = re.compile(
    r"^(DATA_DIR|LOGS_DIR|CONFIG_DIR)\s*=\s*Path\(\s*"
    r'get_determinflow_env\(\s*"(?:DATA_DIR|LOGS_DIR|CONFIG_DIR)"\s*,\s*'
    r'str\(\s*BASE_DIR\s*/\s*"([^"]+)"\s*\)',
    re.M,
)
WORKDIR_RX = re.compile(r"^WORKDIR\s+(\S+)\s*$", re.M)


def _config_directories() -> list[tuple[str, str]]:
    """返回 [(变量名, 默认目录名)]，必须恰好三项。"""
    text = CONFIG_PY.read_text(encoding="utf-8")
    found = DIR_RX.findall(text)
    assert len(found) == 3, (
        f"src/config.py 只解析出 {len(found)} 个目录默认值：{found}"
        "——W16 无锚"
    )
    return found


def _runtime_workdir() -> str:
    """Dockerfile 的运行时 WORKDIR（最后一个）。"""
    matches = WORKDIR_RX.findall(DOCKERFILE.read_text(encoding="utf-8"))
    assert matches, "Dockerfile 没有 WORKDIR——W16 无容器根"
    return matches[-1]


def _app_volumes() -> list[str]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = (document or {}).get("services") or {}
    app = services.get("app")
    assert isinstance(app, dict), (
        "docker-compose.yml 缺少 services.app——W16 的 compose 面失锚"
    )
    volumes = app.get("volumes") or []
    assert isinstance(volumes, list), "services.app.volumes 不是列表"
    out: list[str] = []
    for volume in volumes:
        assert isinstance(volume, str), (
            f"卷声明不是短语法字符串：{volume!r}——W16b 无锚"
        )
        out.append(volume)
    assert len(out) == 3, (
        f"services.app 有 {len(out)} 个卷，预期 3 个持久化目录：{out}"
    )
    return out


def _split_volume(volume: str) -> tuple[str, str]:
    parts = volume.split(":")
    assert len(parts) == 2, (
        f"卷声明不是 src:dst 两段：{volume!r}——W16b 无锚"
    )
    return parts[0], parts[1]


def test_compose_mounts_are_parseable() -> None:
    """W16a：三个 config 目录、三个卷与运行时 WORKDIR 都能解析。"""
    directories = _config_directories()
    volumes = _app_volumes()
    workdir = _runtime_workdir()
    assert workdir.startswith("/"), (
        f"运行时 WORKDIR 不是绝对路径：{workdir!r}"
    )
    assert len(directories) == len(volumes) == 3, (
        f"config 目录 {len(directories)} 个、卷 {len(volumes)} 个——"
        "W16 的覆盖面缩水了"
    )


def test_compose_mount_targets_match_config_directories() -> None:
    """W16b：卷目标 == WORKDIR/<目录名>，宿主机源 basename == 目录名。"""
    workdir = _runtime_workdir()
    directories = _config_directories()
    volumes = _app_volumes()

    expected_targets = {
        posixpath.join(workdir, name): name for _, name in directories
    }
    actual: dict[str, str] = {}
    violations = []
    for volume in volumes:
        source, target = _split_volume(volume)
        if target not in expected_targets:
            violations.append(
                f"{volume}: 容器目标 {target!r} 不在 "
                f"{sorted(expected_targets)} 里"
            )
            continue
        actual[target] = source
        expected_name = expected_targets[target]
        source_name = posixpath.basename(source.rstrip("/"))
        if source_name != expected_name:
            violations.append(
                f"{volume}: 宿主机目录名 {source_name!r} 与容器目录名 "
                f"{expected_name!r} 不同名"
            )
    missing = sorted(set(expected_targets) - set(actual))
    if missing:
        violations.append(f"缺少卷目标：{missing}")
    assert not violations, (
        "compose 挂载点与 config 目录不同账：\n" + "\n".join(violations)
    )
