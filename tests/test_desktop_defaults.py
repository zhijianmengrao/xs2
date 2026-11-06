"""R179：desktop 默认配置覆盖——config/ 与打包清单恰等（W 系续 W19）。

背景（实测，R178 §5 登记、R179 开工复核）：桌面 full 包由
``desktop/scripts/stage_defaults.py`` 生成 ``default-config/``；它把
``config/`` 分成三组——10 个原样读取的源文件（``SOURCE_CONFIG_FILES``）、
3 个桌面覆盖（``DESKTOP_OVERRIDES``：extensions / mcp_servers /
plugin-sources）、2 个 models 派生（``models_config.example.json`` 与
``models_config.json``）。当前 10 + 3 + 2 = 15，恰好覆盖 ``config/*.json``
的 15 个文件。

这条边此前无人判：新增一个 ``config/new.json`` 而忘记加进 staging 清单时，
桌面 full 包会静默缺文件，后端回落到代码默认值；删除/改名配置时也要靠
构建期 ``git show`` 才失败。W19 把「config/ 集合 == staging 清单」钉成
一枚集合恰等判据。

边界：不判每个 JSON 的内容（各自测试负责）、不判覆盖值的业务正确性
（``test_stage_defaults_uses_sanitized_overrides`` 已钉桌面覆盖与脱敏）、
不判 ``config/extension-overrides/`` 目录（不是 JSON 集合的一部分）。
"""

from __future__ import annotations

from pathlib import Path

from desktop.scripts import stage_defaults as defaults_module

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / "config"

MODELS_EXAMPLE = "models_config.example.json"
MODELS_DERIVED = "models_config.json"
MODEL_PAIR = frozenset({MODELS_EXAMPLE, MODELS_DERIVED})


def _config_names() -> set[str]:
    names = {path.name for path in CONFIG.glob("*.json")}
    assert names, "config/ 下没有 JSON——W19 无锚"
    return names


def test_every_config_file_is_covered_by_the_staging_manifest() -> None:
    """W19a：config/*.json == 源清单 ∪ 覆盖清单 ∪ models 派生对，且三组不重叠。"""
    names = _config_names()
    source = list(defaults_module.SOURCE_CONFIG_FILES)
    overrides = set(defaults_module.DESKTOP_OVERRIDES)
    source_set = set(source)

    assert len(source) == len(source_set), (
        f"SOURCE_CONFIG_FILES 有重复项：{source}"
    )
    for left, right, label in (
        (source_set, overrides, "源清单 ∩ 覆盖清单"),
        (source_set, MODEL_PAIR, "源清单 ∩ models 派生对"),
        (overrides, MODEL_PAIR, "覆盖清单 ∩ models 派生对"),
    ):
        overlap = sorted(left & right)
        assert not overlap, f"{label} 不重叠，实测 {overlap}"

    covered = source_set | overrides | MODEL_PAIR
    missing = sorted(names - covered)
    stale = sorted(covered - names)
    assert not missing and not stale, (
        "config/ 与桌面打包清单不同账："
        f"config 有而清单没有 {missing}；清单有而 config 没有 {stale}"
        "——新增配置必须在 SOURCE_CONFIG_FILES / DESKTOP_OVERRIDES / "
        "models 派生对里显式登记"
    )
    # 语料守卫：三组都还在，避免「只剩一个空集合」的静默空转。
    assert len(source_set) >= 10, f"源清单只剩 {len(source_set)} 项"
    assert len(overrides) >= 3, f"覆盖清单只剩 {len(overrides)} 项"
    assert MODEL_PAIR <= names


def test_staging_payloads_cover_the_whole_config_directory(
    tmp_path: Path,
) -> None:
    """W19b：build_payloads / stage_defaults 落盘集合 == config/。"""
    names = _config_names()
    payloads = defaults_module.build_payloads(REPO_ROOT)
    assert set(payloads) == names, (
        "build_payloads 的键集合与 config/ 不同账："
        f"缺 {sorted(names - set(payloads))}；多 {sorted(set(payloads) - names)}"
    )
    assert payloads[MODELS_DERIVED] == payloads[MODELS_EXAMPLE], (
        "models_config.json 必须由 models_config.example.json 派生"
    )

    output = tmp_path / "default-config"
    files = defaults_module.stage_defaults(REPO_ROOT, output)
    staged = {path.name for path in files}
    written = {path.name for path in output.iterdir() if path.is_file()}
    assert staged == names, (
        f"stage_defaults 返回 {sorted(staged)}，config/ 是 {sorted(names)}"
    )
    assert written == names, (
        f"stage_defaults 落盘 {sorted(written)}，config/ 是 {sorted(names)}"
    )
