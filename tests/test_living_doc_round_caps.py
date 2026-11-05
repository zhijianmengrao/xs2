"""R146：活文档的「轮次盖子」与当前时态数字（L 系判据）。

背景（实测，R145 收尾复核）：

- ``PROJECT_INFO.md`` H2 仍写「至 R133」（磁盘已到 R145，落后 12 轮）；
- ``HANDOVER_INDEX.md`` H1「R24–R131」、§4 H2「R24–R134」、§6.1
  「R24–R134」三处轮次区间各停在不同的旧值；
- §3 标题「106 份文档的骨架」而磁盘 120 份；§3 阶段表 R135–R139 的行尾
  仍写「R140–R143 已登记」——那四轮已经完成并有文档；
- §6.4.3「42/109」、§6.4.4「38/107」两个历史审计数字没有轮次锚，
  无法判断是哪一轮的口径；
- §1「判据登记 19 条」自 R133 起手抄（台账 §2 只有 18 个编号条目）。

本文件把四类当前时态数字钉成 **L 系判据**：

- **L1 轮次盖子**：PROJECT_INFO H2 的「至 R<n>」与索引 H1 / §4 H2 /
  §6.1 的「R24–R<n>」必须等于磁盘最新交接文档轮次。当前时态只有一个
  合法值——最新轮。
- **L2 阶段表**：§3 标题份数 == 磁盘交接文档数；每行「区间 × 份数」
  自洽；区间按序、无重叠，覆盖 R24..latest（R34/R35 无文档，登记为
  显式缺口）；「R<a>–R<b> 已登记」的轮次必须严格晚于 latest——已完成
  的轮次不能再以「已登记」的口吻挂在行尾。
- **L3 历史审计数字**：活文档里的「N/M 份」必须带同一行内的轮次锚
  （``R<n>`` + 审计/实测/统计/口径）。裸数字无法复核是哪一轮的口径。
- **L4 判据条数**：索引 §1 的「N 条编号判据」== 台账 §2 编号表的行数，
  且编号连续。R133 的 19 把未编号的导航判据也算了进去；R146 起只数
  编号表，「编号」二字就是口径。

边界：只扫两份活文档（PROJECT_INFO / HANDOVER_INDEX）。「文档体量」行
与交接文档内的历史叙述不在射程（前者随轮次波动、后者是史料）；§4 行的
日期/主题同账由 R147 的判据负责，这里不引入 git 依赖。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
PROJECT_INFO = DOCS / "PROJECT_INFO.md"
INDEX = DOCS / "HANDOVER_INDEX.md"
LEDGER = DOCS / "JUDGEMENT_LEDGER.md"

DASH = r"[–—\-]"
# R34/R35 从未有文档（R36 收编）：阶段表的显式缺口，不是漂移。
ALLOWED_STAGE_GAPS = frozenset({34, 35})
AUDIT_FRACTION_RX = re.compile(r"\d+\s*/\s*\d+\s*份")
AUDIT_ANCHOR_RX = re.compile(r"R\d+[^。；\n]{0,20}?(?:审计|实测|统计|口径)")
STAGE_ROW_RX = re.compile(
    rf"^\| (?P<name>[^|]+?) \| R(?P<lo>\d+)(?:{DASH}R(?P<hi>\d+))? "
    rf"\| (?P<count>\d+) \| (?P<tail>.*) \|$"
)
REGISTERED_TAIL_RX = re.compile(rf"R(\d+)(?:{DASH}R?(\d+))?\s*已登记")


def _text(path: Path) -> str:
    assert path.is_file(), f"活文档不存在：{path}"
    text = path.read_text(encoding="utf-8-sig")
    assert text.strip(), f"活文档为空：{path}"
    return text


def _handover_numbers() -> list[int]:
    nums = []
    for path in DOCS.glob("HANDOVER_ROUND*.md"):
        match = re.search(r"ROUND(\d+)\.md$", path.name)
        if match:
            nums.append(int(match.group(1)))
    assert nums, "docs/ 下没有交接文档——仓库形态不对？"
    return sorted(nums)


def _latest() -> int:
    return max(_handover_numbers())


def _stage_rows() -> list[re.Match[str]]:
    """返回 §3 阶段表的行（标题之后、下一个 ``## `` 之前）。"""
    lines = _text(INDEX).splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("## 3. ")), None
    )
    assert start is not None, "索引找不到 §3 阶段划分——定位失效"
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    rows = [
        match
        for line in lines[start:end]
        if (match := STAGE_ROW_RX.match(line))
    ]
    assert len(rows) >= 10, f"§3 阶段表只解析到 {len(rows)} 行——表形状变了？"
    return rows


def test_living_doc_anchors_exist() -> None:
    """L0 语料守卫：两份活文档与台账 §2 编号表必须都在，且锚点可定位。"""
    index = _text(INDEX)
    info = _text(PROJECT_INFO)
    ledger = _text(LEDGER)
    assert re.search(r"^## 项目状态.*至 R\d+", info, re.M), (
        "PROJECT_INFO 的「## 项目状态…至 R<n>」标题不见了——L1 无处落锚"
    )
    assert re.search(rf"^# 交接文档总索引（R24{DASH}R\d+）$", index, re.M), (
        "索引 H1 的「R24–R<n>」区间不见了——L1 无处落锚"
    )
    assert re.search(rf"^## 4\. 全量索引（R24{DASH}R\d+）$", index, re.M), (
        "索引 §4 标题的「R24–R<n>」区间不见了——L1 无处落锚"
    )
    assert re.search(rf"R24{DASH}R\d+ 每轮恰好一份", index), (
        "索引 §6.1 的「R24–R<n> 每轮恰好一份」不见了——L1 无处落锚"
    )
    assert re.search(r"^## 3\. 阶段划分（\d+ 份文档的骨架）$", index, re.M), (
        "索引 §3 标题的「N 份文档的骨架」不见了——L2 无处落锚"
    )
    assert any(line.startswith("| 判据登记 |") for line in index.splitlines()), (
        "索引 §1 缺「判据登记」行——L4 无处落锚"
    )
    assert "## 2. 逐条登记" in ledger, "台账缺 §2 逐条登记——L4 无处落锚"


def test_round_caps_equal_the_latest_handover() -> None:
    """L1：当前时态的轮次盖子只有一个合法值——磁盘最新交接文档轮次。"""
    latest = _latest()
    info = _text(PROJECT_INFO)
    index = _text(INDEX)

    info_h2 = re.search(r"^## 项目状态.*?至 R(\d+)", info, re.M)
    assert info_h2, "PROJECT_INFO H2 的「至 R<n>」不见了"
    assert int(info_h2.group(1)) == latest, (
        f"PROJECT_INFO H2 写「至 R{info_h2.group(1)}」，磁盘最新是 R{latest}"
        "——轮次盖子落后"
    )

    index_h1 = re.search(rf"^# 交接文档总索引（R24{DASH}R(\d+)）$", index, re.M)
    assert index_h1, "索引 H1 的「R24–R<n>」不见了"
    assert int(index_h1.group(1)) == latest, (
        f"索引 H1 写「R24–R{index_h1.group(1)}」，磁盘最新是 R{latest}"
    )

    index_h2 = re.search(rf"^## 4\. 全量索引（R24{DASH}R(\d+)）$", index, re.M)
    assert index_h2, "索引 §4 H2 的「R24–R<n>」不见了"
    assert int(index_h2.group(1)) == latest, (
        f"索引 §4 H2 写「R24–R{index_h2.group(1)}」，磁盘最新是 R{latest}"
    )

    index_61 = re.search(rf"R24{DASH}R(\d+) 每轮恰好一份", index)
    assert index_61, "索引 §6.1 的「R24–R<n> 每轮恰好一份」不见了"
    assert int(index_61.group(1)) == latest, (
        f"索引 §6.1 写「R24–R{index_61.group(1)}」，磁盘最新是 R{latest}"
    )


def test_stage_table_is_self_consistent() -> None:
    """L2：§3 标题份数、逐行区间/份数、覆盖与「已登记」时限。"""
    latest = _latest()
    index = _text(INDEX)

    title = re.search(r"^## 3\. 阶段划分（(\d+) 份文档的骨架）$", index, re.M)
    assert title, "索引 §3 标题的「N 份文档的骨架」不见了"
    disk_count = len(_handover_numbers())
    assert int(title.group(1)) == disk_count, (
        f"§3 标题写「{title.group(1)} 份」，磁盘有 {disk_count} 份交接文档"
    )

    covered: set[int] = set()
    previous_hi = 0
    for row in _stage_rows():
        lo = int(row.group("lo"))
        hi = int(row.group("hi") or lo)
        count = int(row.group("count"))
        assert lo <= hi, f"§3 行区间倒置：R{lo}–R{hi}"
        assert hi - lo + 1 == count, (
            f"§3 行「{row.group('name')}」写 R{lo}–R{hi} 却记 {count} 份"
            f"（区间长度 {hi - lo + 1}）"
        )
        assert lo > previous_hi, (
            f"§3 阶段行未按轮次递增：R{lo} 落在上一行 R{previous_hi} 之前"
            f"（「{row.group('name')}」）"
        )
        previous_hi = hi
        for round_no in range(lo, hi + 1):
            assert round_no not in covered, (
                f"§3 阶段表把 R{round_no} 登记了两次（「{row.group('name')}」）"
            )
            covered.add(round_no)
        for match in REGISTERED_TAIL_RX.finditer(row.group("tail")):
            future = {int(match.group(1))}
            if match.group(2):
                future.add(int(match.group(2)))
            stale = sorted(n for n in future if n <= latest)
            assert not stale, (
                f"§3 行「{row.group('name')}」仍把已完成的 {stale} 写成"
                f"「已登记」——已登记只能指向严格晚于 R{latest} 的轮次"
            )

    for round_no in range(24, latest + 1):
        assert round_no in covered or round_no in ALLOWED_STAGE_GAPS, (
            f"§3 阶段表漏了 R{round_no}（latest = R{latest}）"
        )


def test_historical_audit_numbers_carry_a_round_anchor() -> None:
    """L3：活文档的「N/M 份」必须带同行的轮次锚（审计/实测/统计/口径）。"""
    violations: list[str] = []
    for name in ("PROJECT_INFO.md", "HANDOVER_INDEX.md"):
        for lineno, line in enumerate(_text(DOCS / name).splitlines(), 1):
            for fraction in AUDIT_FRACTION_RX.finditer(line):
                if not AUDIT_ANCHOR_RX.search(line[: fraction.start()]):
                    violations.append(
                        f"{name}:{lineno}: 裸审计数字「{fraction.group(0)}」"
                        f"没有轮次锚：{line.strip()[:100]}"
                    )
    assert not violations, (
        "历史审计数字必须带显式轮次锚（形如「R132 审计：38/107 份」）：\n"
        + "\n".join(violations)
    )


def test_judgement_count_matches_the_numbered_ledger() -> None:
    """L4：索引 §1 的「N 条编号判据」== 台账 §2 编号表行数。"""
    lines = _text(LEDGER).splitlines()
    start = lines.index("## 2. 逐条登记")
    end = next(
        i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")
    )
    numbers = []
    for line in lines[start:end]:
        match = re.match(r"^\|\s*(\d+)\s*\|", line)
        if match:
            numbers.append(int(match.group(1)))
    assert numbers, "台账 §2 编号表没有解析到任何行"
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"台账 §2 编号不连续：{numbers}"
    )

    row = next(
        line
        for line in _text(INDEX).splitlines()
        if line.startswith("| 判据登记 |")
    )
    claimed = re.search(r"(\d+)\s*条编号判据", row)
    assert claimed, (
        f"索引 §1 判据行没有「N 条编号判据」：{row.strip()[:120]}"
    )
    assert "§2 编号表" in row, (
        f"索引 §1 判据行没有标明口径「§2 编号表」：{row.strip()[:120]}"
    )
    assert int(claimed.group(1)) == len(numbers), (
        f"索引写「{claimed.group(1)} 条编号判据」，台账 §2 编号表实有 "
        f"{len(numbers)} 条（#1–#{len(numbers)}）"
    )

# ------------------------------------------------- R163: 支持面行同账（L8）
# PROJECT_INFO 是支持面的活文档第二份账：§技术栈 / §约束 / §仓库结构
# 里手抄的 Python / Node 下限，此前无人对账（P4/P7 只钉 README）。
# L8 把活文档里的下限行钉到与 P4/P7 同一个锚（requires-python / engines）。
PI_PY_FLOOR_RX = re.compile(r"Python\s*≥\s*(\d+\.\d+)")
PI_NODE_FLOOR_RX = re.compile(r"[Nn]ode(?:\.js)?\s*≥\s*(\d+\.\d+)")


def _project_info_floors() -> tuple[set, set]:
    """PROJECT_INFO 里的 (Python 下限集合, Node 下限集合)。"""
    text = PROJECT_INFO.read_text(encoding="utf-8-sig")
    py = {m.group(1) for m in PI_PY_FLOOR_RX.finditer(text)}
    node = {m.group(1) for m in PI_NODE_FLOOR_RX.finditer(text)}
    return py, node


def test_project_info_support_floors_agree() -> None:
    """L8：PROJECT_INFO 的 Python/Node 下限 == requires-python / engines。"""
    import json
    import tomllib

    document = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    match = re.search(
        r">=\s*(\d+\.\d+)", document["project"]["requires-python"]
    )
    assert match, "requires-python 没有可解析下限——L8 无锚"
    py_floor = match.group(1)
    web = json.loads(
        (REPO_ROOT / "web" / "package.json").read_text(encoding="utf-8")
    )
    node_match = re.match(
        r">=(\d+)\.(\d+)\.0$", (web.get("engines") or {}).get("node", "")
    )
    assert node_match, "engines.node 不是 >=X.Y.0 形状——L8 无锚"
    node_floor = f"{node_match.group(1)}.{node_match.group(2)}"

    py_floors, node_floors = _project_info_floors()
    assert py_floors, "PROJECT_INFO 没有「Python ≥X.Y」——L8 的 Python 面空转"
    assert node_floors, "PROJECT_INFO 没有「Node ≥X.Y」——L8 的 Node 面空转"
    assert py_floors == {py_floor}, (
        f"PROJECT_INFO 的 Python 下限与 requires-python 不同账："
        f"文档写 {sorted(py_floors)}，requires-python 下限是 {py_floor}"
    )
    assert node_floors == {node_floor}, (
        f"PROJECT_INFO 的 Node 下限与 engines 不同账："
        f"文档写 {sorted(node_floors)}，engines 下限是 {node_floor}"
    )
