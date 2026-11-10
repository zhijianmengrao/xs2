"""R241：build-runs.json 写读同账（W 系续 W66）。

背景（实测，R240 §3 登记）：replace-desktop-assets.yml 的 provenance 步
把各平台构建 run 写进 ``build-runs.json``
（``Path('build-runs.json').write_text(json.dumps(records))``，L60），
release 步再读回来塞进发布元数据
（``'build_runs': json.loads(Path('build-runs.json').read_text())``，
L100），最终落进 ``build-source.json`` 的审计面。写读改名而对面没跟
→ release 步 ``FileNotFoundError``（发版第 2 步中断）；平台键集合漂移
→ 审计面少平台（``records[platform]`` 只写元组里有的平台）；键名
``build_runs`` 改动 → 下游读者拿不到构建 run 账。

W66 钉成两半：

- **W66a 语料守卫**：两个 heredoc；写入恰 1 处、读取恰 1 处；
  ``records`` 的初始化 / 平台赋值 / 序列化各恰 1 处；``'build_runs'``
  键字面恰 1 处。
- **W66b 写读同账**：两处路径字面逐字相等且等于 ``build-runs.json``；
  元组平台字面集合 == ``{windows, macos}``；release 步的消费表达式
  == 对同一文件的 ``json.loads(Path(...).read_text())``。

边界：只判文件名/键名的字面同账——不判 JSON 内容形状（脚本写什么由
``json.dumps(records)`` 决定）、不判 ``gh api`` 拉到的 run 真假（脚本
运行时校验）、不判 ``build-source.json`` 的下游消费（发布资产校验由
release 步负责）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPLACE = REPO_ROOT / ".github" / "workflows" / "replace-desktop-assets.yml"

HEREDOC_RX = re.compile(r"python - <<'PY'\n(.*?)\n {10}PY\n", re.S)
TUPLE_RX = re.compile(
    r"\('(\w+)',\s*'([A-Z_]+)',\s*'([^']+\.yml)',\s*\[(.*?)\]\)", re.S
)

WRITE_RX = re.compile(r"Path\('([^']+)'\)\.write_text")
READ_RX = re.compile(r"Path\('([^']+)'\)\.read_text")
LEDGER_NAME = "build-runs.json"
EXPECTED_PLATFORMS = {"windows", "macos"}

# release 步的消费表达式（键名 + 同文件读取）
CONSUME_RX = re.compile(
    r"'build_runs':\s*json\.loads\(Path\('build-runs\.json'\)\.read_text\(\)\)"
)


def _heredocs() -> list[str]:
    text = REPLACE.read_text(encoding="utf-8")
    heredocs = HEREDOC_RX.findall(text)
    assert len(heredocs) == 2, (
        f"replace workflow 的 <<'PY' heredoc 应恰 2 个，实测 {len(heredocs)} 个"
        "——W66 的写读两侧无处落锚"
    )
    return heredocs


def test_build_runs_io_shape() -> None:
    """W66a：写恰 1、读回同一文件恰 1、records 三处各 1、build_runs 键恰 1。"""
    writer, reader = _heredocs()
    writes = WRITE_RX.findall(writer)
    assert len(writes) == 1, (
        f"provenance 步应恰 1 处 write_text，实测 {len(writes)} 处"
        f"（{writes}）——W66a 语料守卫"
    )
    # release 步还读 tauri.conf.json / official-plugins.lock.json，只数
    # 「读回本次写入的那个文件」的一侧。
    reads = [path for path in READ_RX.findall(reader) if path == writes[0]]
    assert len(reads) == 1, (
        f"release 步应恰 1 处读回 {writes[0]!r}，实测 {len(reads)} 处"
        "——W66a 语料守卫"
    )
    assert len(re.findall(r"records = \{\}", writer)) == 1, (
        "records 的初始化应恰 1 处——W66a 语料守卫"
    )
    assert len(re.findall(r"records\[platform\]", writer)) == 1, (
        "records 的平台赋值应恰 1 处——W66a 语料守卫"
    )
    assert len(re.findall(r"json\.dumps\(records\)", writer)) == 1, (
        "写出的对象应恰是 records（json.dumps(records) 恰 1 处）"
        "——W66a 语料守卫"
    )
    assert len(re.findall(r"'build_runs'", reader)) == 1, (
        "release 步的 'build_runs' 键应恰 1 处——W66a 语料守卫"
    )


def test_build_runs_write_and_read_agree() -> None:
    """W66b：两处路径逐字恰等；平台集合恰两平台；消费表达式逐字匹配。"""
    writer, reader = _heredocs()
    writes = WRITE_RX.findall(writer)
    assert writes, "写侧缺失——W66b 无锚"
    write_path = writes[0]
    assert write_path == LEDGER_NAME, (
        f"写侧路径是 {write_path!r}，期望 {LEDGER_NAME!r}"
    )
    # 双向：读侧必须读回**写入的那个名字**（写改名而读没跟 / 读改名而写
    # 没跟，都表现为「没有一处读回这个名字」）。
    read_back = [path for path in READ_RX.findall(reader) if path == write_path]
    assert read_back, (
        f"build-runs.json 写读不同账：写 {write_path!r}，release 步没有读回"
        f"这个名字（实际读取 {READ_RX.findall(reader)}）——改名而对面没跟时"
        " release 步 FileNotFoundError"
    )

    platforms = {platform for platform, *_ in TUPLE_RX.findall(writer)}
    assert platforms == EXPECTED_PLATFORMS, (
        f"provenance 元组的平台集合 {sorted(platforms)} != "
        f"{sorted(EXPECTED_PLATFORMS)}——审计面会少平台"
    )

    consumers = CONSUME_RX.findall(reader)
    assert len(consumers) == 1, (
        "release 步的 build_runs 消费表达式应恰 1 处且逐字为 "
        "\"'build_runs': json.loads(Path('build-runs.json').read_text())\""
        f"，实测 {len(consumers)} 处——键名/读取面漂移"
    )
