"""R237：replace workflow provenance 步 env 定义 == os.environ 消费（W 系续 W61）。

背景（实测，R236 §3 登记）：replace-desktop-assets.yml 的 provenance 步
env 定义两个键（``WINDOWS_RUN`` L33 / ``MACOS_RUN`` L34，值来自
``${{ inputs.* }}``——输入名本身由 W57 钉住），消费点为 heredoc 内的
``os.environ`` 读取：两键作为元组字面（L43/L45 的
``'WINDOWS_RUN'``/``'MACOS_RUN'``）流进循环变量，在
``os.environ[key]``（L48）统一取出。定义与消费漂移无人判：env 键改名
而 heredoc 元组没跟 → ``os.environ[key]`` 抛 ``KeyError``——应急通道
当场失败，两个平台的构建 run 校验全部中断。

W61 把这条边钉成两半（W57/W58 同型分工）：

- **W61a 语料守卫**：env 定义（值来自 inputs）恰 2 键；首个 heredoc
  存在、``os.environ[key]`` 循环读取恰 1 处、heredoc 内引号大写键字面
  恰 2 个（排除 ``os.environ['…']`` 直接读取——那是 runner 注入的
  ``GITHUB_*``，不归 env 定义管）。
- **W61b 定义 == 消费（双向）**：env 键集合 == heredoc 键字面集合
  （消费未定义的红、定义未消费的死键也红）。

边界：只判 env 键名的字面同账——不判键值（``inputs.*`` 的取值由 W57
钉输入名）、不判 ``os.environ['GITHUB_*']`` 直接读取（runner 注入，无
定义侧可对）、不判 ``gh api`` 的运行时校验（脚本负责）、不判 workflow
触发与下载行为（CI 负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE_WF = (
    REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"
)

# 定义：10 空格缩进的 env 键，值恰为 `${{ inputs.* }}`（GH_TOKEN 用
# github.token、发布步用 secrets/vars/steps，都不匹配）。
DEFINE_RX = re.compile(r"^ {10}([A-Z_]+): \$\{\{ inputs\.(\w+) \}\}$", re.M)
# heredoc 边界：``python - <<'PY'`` 到 10 空格缩进的收尾 ``PY``。
HEREDOC_RX = re.compile(r"python - <<'PY'\n(.*?)\n {10}PY\n", re.S)
# 消费 A：循环变量读取 `os.environ[key]`。
LOOP_READ_RX = re.compile(r"os\.environ\[key\]")
# 直接读取 `os.environ['LITERAL']`（runner 注入键，先剥掉再数键字面）。
DIRECT_READ_RX = re.compile(r"os\.environ\[[^\]]*\]")
# 消费 B：heredoc 内的单引号大写键字面（元组里流给 key 的那两个）。
KEY_LITERAL_RX = re.compile(r"'([A-Z_]+)'")

EXPECTED_DEFINES = 2
EXPECTED_LITERALS = 2


def _text() -> str:
    return REPLACE_WF.read_text(encoding="utf-8")


def _heredoc() -> str:
    match = HEREDOC_RX.search(_text())
    assert match, "replace workflow 找不到 <<'PY' heredoc——语料形态变了"
    return match.group(1)


def _defined() -> list[str]:
    return DEFINE_RX.findall(_text())


def _literals() -> list[str]:
    stripped = DIRECT_READ_RX.sub("", _heredoc())
    return KEY_LITERAL_RX.findall(stripped)


def test_provenance_env_definition_shape() -> None:
    """W61a：env 定义恰 2 键；heredoc 存在、循环读取与键字面恰一处/两处。"""
    defined = _defined()
    assert len(defined) == EXPECTED_DEFINES, (
        f"provenance 步 env（值来自 inputs.*）应恰 {EXPECTED_DEFINES} 个键，"
        f"实测 {len(defined)} 个（{defined}）——W61a 语料守卫"
    )
    loop_reads = LOOP_READ_RX.findall(_heredoc())
    assert len(loop_reads) == 1, (
        f"heredoc 的 os.environ[key] 循环读取应恰 1 处，实测 "
        f"{len(loop_reads)} 处——W61a 语料守卫"
    )
    literals = _literals()
    assert len(literals) == EXPECTED_LITERALS, (
        f"heredoc 内引号大写键字面应恰 {EXPECTED_LITERALS} 个，实测 "
        f"{len(literals)} 个（{literals}）——W61a 语料守卫"
    )


def test_provenance_env_keys_agree() -> None:
    """W61b：env 键集合 == heredoc 键字面集合（双向：谁多谁少都红）。"""
    defined = {name for name, _ in _defined()}
    consumed = set(_literals())
    assert defined and consumed, "env 定义或 heredoc 键字面为空——W61b 无锚"
    undefined = sorted(consumed - defined)
    dead = sorted(defined - consumed)
    assert not undefined and not dead, (
        f"provenance 步 env 定义与 heredoc os.environ 消费不同账：消费未"
        f"定义 {undefined}（os.environ[key] 抛 KeyError）、定义未消费 "
        f"{dead}（死 env 键）——改名/删除两侧必须同改"
    )
