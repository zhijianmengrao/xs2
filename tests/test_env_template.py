"""R170：.env.example 环境模板 ↔ config 读取点（W 系续 W15）。

背景（实测，R168 §3 登记）：``.env.example`` 是用户复制成 ``.env`` 的
模板，9 个 active 键里有 8 个带非空默认值。模板与代码之间的两种静默
漂移：

- 模板写了 ``FOO=1`` 但代码从不读 ``FOO``：用户以为自己调了参数；
- 模板的默认值与代码兜底值不同：复制模板后行为与默认部署不一致。

W14 已钉 compose 的 6 个 env；``.env.example`` 是另一份独立写入点
（9 个键，含 4 个未在 compose 出现的键），必须单独对账：

- **W15a 读取点存在**：模板的每个 active 键都必须在 ``src/`` 找到读取
  点——裸名命中 ``os.getenv`` / ``os.environ.get`` / ``_get_config_value``
  / ``_get_int_config`` / ``_get_bool_config``；带 ``DETERMINFLOW_``
  前缀的键，后缀命中 ``get_determinflow_env("<suffix>")``。至少 9 个键
  的语料守卫，且键不得重复（重复键的后写覆盖先写，模板本身就歧义）。
- **W15b 默认值同账**：非空值必须等于代码兜底值（布尔与大小写归一）；
  空值（凭证类）只判读取点，不判默认值——``DEEPSEEK_API_KEY=`` 的语义
  是「由部署者填」，没有可比较的默认值。至少 8 个非空值的语料守卫。

边界：只判 active 行——``#`` 注释掉的键（``# DETERMINFLOW_DATA_DIR=…``）
是文档示例，不在射程；不判 ``.env`` 本身（不入库）；不判运行时
dotenv 的加载优先级（``load_dotenv`` 会读 ``.env``，那是运维面）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
SRC = REPO_ROOT / "src"

PREFIX = "DETERMINFLOW_"
LINE_RX = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
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
    assert files, "src/ 下没有 Python 源文件——W15 没有读取点可查"
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in files
    )


def _active_entries() -> list[tuple[str, str]]:
    """返回 active 的 (键, 值)；注释行与空行跳过。"""
    entries: list[tuple[str, str]] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RX.match(stripped)
        if match:
            entries.append((match.group(1), match.group(2)))
    assert entries, ".env.example 没有 active 键——W15 没有语料"
    return entries


def _suffix(key: str) -> str:
    return key[len(PREFIX):] if key.startswith(PREFIX) else key


def _code_default(key: str) -> str:
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
        f".env.example 的 {key} 在 src/ 里找不到带兜底值的读取点"
        "——W15b 无锚"
    )
    assert len(candidates) == 1, (
        f".env.example 的 {key} 在 src/ 里解析到 {len(candidates)} 处兜底值："
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


def test_env_template_keys_have_read_points() -> None:
    """W15a：.env.example 的每个 active 键都有读取点，且键不重复。"""
    entries = _active_entries()
    assert len(entries) >= 9, (
        f".env.example 只剩 {len(entries)} 个 active 键——W15 的覆盖面缩水了"
    )
    keys = [key for key, _ in entries]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicates, (
        f".env.example 的键重复：{duplicates}——后写覆盖先写，模板歧义"
    )
    text = _src_text()
    violations = []
    for key, _ in entries:
        if key.startswith(PREFIX):
            pattern = rf'get_determinflow_env\(\s*"{re.escape(_suffix(key))}"'
            if not re.search(pattern, text):
                violations.append(
                    f"{key}: src/ 没有 get_determinflow_env("
                    f'"{_suffix(key)}") 读取点'
                )
        else:
            if not re.search(BARE_CALL_RX.format(key=re.escape(key)), text):
                violations.append(
                    f"{key}: src/ 没有裸名读取点（os.getenv / "
                    f"_get_config_value / _get_int_config / _get_bool_config）"
                )
    assert not violations, (
        ".env.example 存在无人消费的键：\n" + "\n".join(violations)
    )


def test_env_template_defaults_agree() -> None:
    """W15b：非空模板值 == 代码兜底值；空值凭证只判读取点。"""
    compared = 0
    violations = []
    for key, value in _active_entries():
        if value == "":
            continue  # 凭证类：语义是部署者填，没有可比较的默认值
        compared += 1
        code_default = _code_default(key)
        if _normalized(value) != _normalized(code_default):
            violations.append(
                f"{key}: 模板写 {value!r}，代码兜底 {code_default!r}"
            )
    assert compared >= 8, (
        f"只有 {compared} 个非空模板值参与对账——W15b 的覆盖面缩水了"
    )
    assert not violations, (
        ".env.example 默认值与代码兜底不同账：\n" + "\n".join(violations)
    )
