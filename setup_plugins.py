#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeterminFlow 内置插件自举。

内置插件随软件分发在 ``builtin-plugins/<plugin-id>``，首次启动时直接复制到
``data/plugins/checkouts/`` 并写入 ``plugins.lock.json``：

- 不需要 Git、不联网、不需要用户手动安装；
- 已安装且校验通过时零副作用；
- 同时把插件写入 ``config/extensions.json`` 的启用列表（默认启用）。

运行时判定「插件是否已安装」只认 PluginStore 的 lock + checkouts，
因此这里走与 ``POST /api/plugins/install`` 相同的 ``PluginStore.install``
与 ``validate_plugin_checkout`` 预检链路。
"""

import codecs
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extension_host.plugin_preflight import validate_plugin_checkout
from src.plugin_system.builtin import (
    BUILTIN_PLUGIN_IDS,
    builtin_plugins_root,
    ensure_builtin_plugins,
    ensure_enabled_plugins,
)


class PluginManager:
    """安装并启用随软件分发的内置插件。"""

    REQUIRED_PLUGINS = BUILTIN_PLUGIN_IDS

    def __init__(self) -> None:
        self.determinflow_root = Path(__file__).parent.resolve()
        self.plugins_dir = self.determinflow_root / "data" / "plugins"
        self.extensions_config = self.determinflow_root / "config" / "extensions.json"
        self.builtin_root = builtin_plugins_root()

    def _preflight(self, plugin_id: str, checkout: Path) -> None:
        validate_plugin_checkout(plugin_id, checkout)

    def print_plugin_info(self) -> None:
        print("=" * 60)
        print("DeterminFlow 内置插件")
        print("=" * 60)
        print(f"插件目录: {self.plugins_dir}")
        print(f"内置插件目录: {self.builtin_root}")
        if not self.builtin_root.is_dir():
            print("\n⚠️  未找到内置插件目录，跳过插件自举")
            return
        for plugin_id in sorted(BUILTIN_PLUGIN_IDS):
            if (self.builtin_root / plugin_id / "extension.toml").is_file():
                print(f"  - {plugin_id}")
        print()

    def check_and_install_required_plugins(self) -> bool:
        print("=" * 60)
        print("DeterminFlow 内置插件检测")
        print("=" * 60)
        if not self.builtin_root.is_dir():
            print(f"✗ 内置插件目录不存在: {self.builtin_root}")
            return False
        try:
            installed = ensure_builtin_plugins(
                self.plugins_dir,
                preflight=self._preflight,
            )
        except Exception as exc:  # noqa: BLE001 - 安装失败不应阻断服务启动
            print(f"✗ 内置插件安装失败: {exc}")
            return False
        if installed:
            for plugin_id in installed:
                print(f"✓ 已安装内置插件: {plugin_id}")
        else:
            print("✓ 内置插件已就绪（无需安装）")
        try:
            added = ensure_enabled_plugins(self.extensions_config, BUILTIN_PLUGIN_IDS)
        except OSError as exc:
            print(f"⚠️  无法写入启用配置: {exc}")
            return False
        if added:
            print(f"✓ 已默认启用: {', '.join(added)}")
        print()
        print("=" * 60)
        print("✓ 内置插件检测完成")
        print("=" * 60)
        return True


def main() -> int:
    manager = PluginManager()
    manager.print_plugin_info()
    return 0 if manager.check_and_install_required_plugins() else 1


if __name__ == "__main__":
    # Windows 重定向的控制台默认使用 GBK，无法输出插件诊断中的中文与符号。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        elif getattr(stream, "encoding", None) and stream.encoding.lower() != "utf-8":
            try:
                if stream is sys.stdout:
                    sys.stdout = codecs.getwriter("utf-8")(stream.buffer, "strict")
                else:
                    sys.stderr = codecs.getwriter("utf-8")(stream.buffer, "strict")
            except (AttributeError, ValueError):
                pass

    sys.exit(main())
