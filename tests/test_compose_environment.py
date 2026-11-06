"""R167：compose 环境账 ↔ config 读取点（W 系续 W14）。

背景（实测，R164 §7 登记、R167 开工复核）：``docker-compose.yml`` 给 app
设了 **6 个**环境变量，但 compose 只是「一份写死的默认值清单」——它读的
每个键到底有没有代码在消费、静态默认值是否与代码兜底值一致，此前无人
对账：

- 裸名：``WEB_HOST`` / ``WEB_PORT`` / ``LOG_LEVEL`` /
  ``CODING_WORKSPACE_COPY_ON_CREATE``；
- 带 ``DETERMINFLOW_`` 前缀：``DETERMINFLOW_WORKFLOW_EXECUTOR_MODE`` /
  ``DETERMINFLOW_WORKFLOW_EXECUTOR_COUNT``（``get_determinflow_env`` 的
  后缀命中 ``WORKFLOW_EXECUTOR_MODE`` / ``WORKFLOW_EXECUTOR_COUNT``）。

compose 写 ``WEB_HOST: "127.0.0.1"`` 而 config 兜底 ``0.0.0.0``，容器会
只在回环上监听；compose 设一个没有任何读取点的 ``DETERMINFLOW_*``，用户
以为调了参数、实际什么都没发生。本文件把这条面钉住：

- **W14a 读取点存在**：compose 的每个 env 都必须能在 ``src/`` 里找到读取
  点——裸名命中 ``os.getenv`` / ``os.environ.get`` / ``_get_config_value``
  / ``_get_int_config`` / ``_get_bool_config``；带前缀的键，其后缀必须
  命中 ``get_determinflow_env("<suffix>")``。语料守卫要求至少 6 个键，
  防止 compose 缩水后判据空转。
- **W14b 静态默认值同账**：compose 的值是 ``${KEY:-default}`` 时，插值
  变量名必须就是该键本身（``WEB_PORT: "${WEB_HOST:-8020}"`` 是错的），
  且 default 必须等于代码里的兜底值；字面量值直接与代码兜底值比较。
  布尔与大小写归一后比较（``true`` / ``True``）。

边界：只判 compose 的 ``services.app.environment`` 静态账——不判
``docker compose`` 的运行时插值优先级（shell/``.env`` 会覆盖默认值，
那是运维面）、不判未在 compose 出现的其它 env（``.env.example`` 的模板
面由另一条判据负责）、不判非字符串值（当前 6 个全是字符串）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.yml"
SRC = REPO_ROOT / "src"

PREFIX = "DETERMINFLOW_"
INTERP_RX = re.compile(r"^\$\{([A-Z0-9_]+):-(.*)\}$")
HELPERS = (
    "_get_config_value",
    "_get_int_config",
    "_get_bool_config",
)
BARE_CALL_RX = (
    r'(?:os\.getenv|os\.environ\.get|_get_config_value|_get_int_config'
    r"|_get_bool_config|get_determinflow_env)\(\s*\"{key}\""
)


def _src_text() -> str:
    files = sorted(SRC.rglob("*.py"))
    assert files, "src/ 下没有 Python 源文件——W14 没有读取点可查"
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in files
    )


def _app_environment() -> dict[str, str]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = (document or {}).get("services") or {}
    app = services.get("app")
    assert isinstance(app, dict), (
        "docker-compose.yml 缺少 services.app——W14 的 compose 面失锚"
    )
    environment = app.get("environment")
    assert isinstance(environment, dict) and environment, (
        "services.app.environment 缺失或为空——W14 没有语料"
    )
    out: dict[str, str] = {}
    for key, value in environment.items():
        assert isinstance(value, str), (
            f"compose 环境变量 {key} 不是字符串：{value!r}——W14b 无锚"
        )
        out[str(key)] = value
    return out


def _suffix(key: str) -> str:
    return key[len(PREFIX):] if key.startswith(PREFIX) else key


def _interpolation(key: str, raw: str) -> tuple[str, str]:
    """返回 (插值变量名, 静态默认值)；字面量值的变量名就是键本身。"""
    match = INTERP_RX.match(raw.strip())
    if not match:
        return key, raw
    return match.group(1), match.group(2)


def _code_default(key: str) -> str:
    """从 src 的读取点里取该键的兜底值；必须恰好一处候选。"""
    suffix = _suffix(key)
    text = _src_text()
    candidates: list[tuple[str, str]] = []
    for helper in HELPERS:
        candidates.extend(
            (helper, value)
            for value in re.findall(
                rf'{helper}\(\s*"{re.escape(suffix)}"\s*,\s*([^)]+)\)', text
            )
        )
    for call in ("os.getenv", "os.environ.get"):
        candidates.extend(
            (call, value)
            for value in re.findall(
                rf'{call}\(\s*"{re.escape(key)}"\s*,\s*([^)]+)\)', text
            )
        )
    assert candidates, (
        f"compose 的 {key} 在 src/ 里找不到带兜底值的读取点——W14b 无锚"
    )
    assert len(candidates) == 1, (
        f"compose 的 {key} 在 src/ 里解析到 {len(candidates)} 处兜底值："
        f"{candidates}——同一键多兜底值本身就是不同账"
    )
    return candidates[0][1]


def _normalized(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if text.lower() == "true":
        return "true"
    if text.lower() == "false":
        return "false"
    return text.lower()


def test_compose_environment_has_read_points() -> None:
    """W14a：compose 的每个 env 都能在 src/ 找到读取点。"""
    environment = _app_environment()
    assert len(environment) >= 6, (
        f"compose 环境变量只剩 {len(environment)} 个——W14 的覆盖面缩水了"
    )
    text = _src_text()
    violations = []
    for key in environment:
        if key.startswith(PREFIX):
            pattern = (
                rf'get_determinflow_env\(\s*"{re.escape(_suffix(key))}"'
            )
            if not re.search(pattern, text):
                violations.append(
                    f"{key}: src/ 没有 get_determinflow_env("
                    f'"{_suffix(key)}") 读取点'
                )
        else:
            pattern = BARE_CALL_RX.format(key=re.escape(key))
            if not re.search(pattern, text):
                violations.append(
                    f"{key}: src/ 没有裸名读取点（os.getenv / "
                    f"_get_config_value / _get_int_config / _get_bool_config）"
                )
    assert not violations, (
        "compose 环境变量存在无人消费的键：\n" + "\n".join(violations)
    )


def test_compose_environment_defaults_agree() -> None:
    """W14b：compose 静态默认值 == 代码兜底值；插值变量名 == 键名。"""
    violations = []
    for key, raw in _app_environment().items():
        variable, compose_default = _interpolation(key, raw)
        if variable != key:
            violations.append(
                f"{key}: 插值变量名写 {variable}——别名会让默认值张冠李戴"
            )
        code_default = _code_default(key)
        if _normalized(compose_default) != _normalized(code_default):
            violations.append(
                f"{key}: compose 写 {compose_default!r}，"
                f"代码兜底 {code_default!r}"
            )
    assert not violations, (
        "compose 静态默认值与代码兜底值不同账：\n" + "\n".join(violations)
    )
