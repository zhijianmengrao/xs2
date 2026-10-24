# -*- coding: utf-8 -*-
"""一次性只读诊断：扫描数据/配置存储中的 Windows 保留设备名遗留（R21，B13 纵深）。

R20 已在全部入口拒绝设备名 id，此后不会再写入新数据；本脚本用于确认**历史
数据**是否干净（HANDOVER_ROUND20 §8.3 遗留项）。只读，不修改任何文件。

用法：
    python scripts/audit_storage_names.py [仓库根目录]

退出码：0 = 无命中；1 = 存在设备名遗留（见输出整改建议）；2 = 参数错误。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.storage_name_audit import scan_storage_names  # noqa: E402


def main() -> int:
    if len(sys.argv) > 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ROOT
    findings = scan_storage_names(root)
    if not findings:
        print(f"[clean] {root} 存储名审计：未发现 Windows 保留设备名遗留")
        return 0
    print(f"[findings] {root} 存在 {len(findings)} 处设备名遗留：")
    for finding in findings:
        print(f"  - {finding.surface} :: {finding.name!r} ({finding.kind})")
        print(f"    {finding.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
