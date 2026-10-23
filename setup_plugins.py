#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeterminFlow 必需插件自动检测与安装。

真实写入 PluginStore 的期望状态（``data/plugins/plugins.lock.json``）：运行时
判定「插件是否已安装」只认 PluginStore 的 lock + ``data/plugins/checkouts/``。
历史实现只写 ``plugins_installed.json``（运行时无任何代码读取它），因此会出现
「脚本打印插件已就绪、运行时仍报未安装」的假象——这里改为真实安装。

设计约束：
- 只使用已克隆到兄弟目录的本地插件仓库；本地源缺失时仅打印指引，**绝不联网**。
- 已安装时零副作用、零重依赖导入（快速跳过）。
- 安装链路与 ``POST /api/plugins/install`` 一致：``PluginStore.install`` +
  ``validate_plugin_checkout`` 预检；本地源属第三方信任，需显式 acknowledge_risk。
"""

import codecs
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


class PluginManager:
    """管理 DeterminFlow 必需插件的检测与真实安装。"""

    # 必需的默认插件列表（subdirectory 为仓库内相对路径提示，
    # 实际以仓库 plugin-repository.toml 的声明为准）
    REQUIRED_PLUGINS: dict[str, dict[str, Any]] = {
        "xs2-novel-flywheel": {
            "name": "XS2 Novel Flywheel",
            "description": "Novel production workflows with selectable reference learning",
            "subdirectory": "plugins/xs2-novel-flywheel",
            "ref": "main",
        }
    }

    def __init__(self) -> None:
        self.determinflow_root = Path(__file__).parent.resolve()
        self.plugins_dir = self.determinflow_root / "data" / "plugins"
        # 插件源仓库的本地克隆（与 xs2 项目同级）
        self.local_repository = self.determinflow_root.parent / "DeterminFlow-Plugins"
        self.source_config_file = self.determinflow_root / "config" / "plugin-sources.json"

    # ------------------------------------------------------------------ 配置

    def _source_config(self) -> dict[str, Any]:
        if not self.source_config_file.is_file():
            return {}
        try:
            document = json.loads(
                self.source_config_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}
        return document if isinstance(document, dict) else {}

    def _official_sources(self) -> tuple[list[str], dict[str, list[str]]]:
        """官方源 URL 与镜像，仅用于 PluginStore 的信任分类。

        这里不解析 registry 配置：本脚本只安装本地源插件，registry 加速下载与
        官方源的信任判定无关。
        """
        urls: list[str] = []
        mirrors: dict[str, list[str]] = {}
        for entry in self._source_config().get("official_sources", []):
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("url", "")).strip()
            if not url:
                continue
            urls.append(url)
            mirrors[url] = [
                str(item).strip()
                for item in entry.get("mirrors", [])
                if str(item).strip()
            ]
        return urls, mirrors

    def _local_ref(self) -> str:
        """本地源在配置中的 ref（缺失时回退 main）。"""
        for entry in self._source_config().get("custom_sources", []):
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("url", "")).strip()
            if not raw:
                continue
            try:
                candidate = Path(raw.replace("file:///", "", 1).replace("%20", " "))
            except (ValueError, OSError):
                continue
            try:
                if candidate.resolve() == self.local_repository.resolve():
                    ref = str(entry.get("ref", "")).strip()
                    if ref:
                        return ref
            except (OSError, ValueError):
                continue
        return "main"

    # ------------------------------------------------------------- PluginStore

    def _store(self):
        # 延迟导入：已安装时本脚本不需要拉起插件系统。
        from src.plugin_system import PluginStore

        official_urls, official_mirrors = self._official_sources()
        return PluginStore(
            self.plugins_dir,
            official_sources=official_urls,
            official_source_mirrors=official_mirrors,
        )

    def _installed_plugin_ids(self) -> set[str]:
        try:
            return set(self._store().read_lock())
        except Exception:  # noqa: BLE001 - 检测失败按「未安装」处理并走安装分支
            return set()

    def _checkout_present(self, plugin_id: str) -> bool:
        """已安装记录对应的 checkout 是否仍然存在且通过校验。"""
        try:
            store = self._store()
            record = store.get(plugin_id)
        except Exception:  # noqa: BLE001
            return False
        if record is None:
            return False
        return Path(record.active_revision.checkout_path).is_dir()

    # ------------------------------------------------------------------ 安装

    def _repository_subdirectory(self, plugin_id: str, fallback: str) -> str:
        """优先采用本地仓库 plugin-repository.toml 声明的 subdirectory。"""
        index = self.local_repository / "plugin-repository.toml"
        if index.is_file():
            try:
                document = tomllib.loads(index.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                document = {}
            for entry in document.get("plugins", []):
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("id", "")).strip() == plugin_id:
                    declared = str(entry.get("subdirectory", "")).strip()
                    if declared:
                        return declared
        return fallback

    def _install_plugin(self, plugin_id: str, spec: dict[str, Any]) -> bool:
        display_name = spec.get("name", plugin_id)
        print(f"\n📦 安装插件: {display_name}")

        if not self.local_repository.is_dir():
            print(f"  ✗ 本地插件仓库不存在: {self.local_repository}")
            print("    请先克隆插件仓库到该位置，或在 Web 界面中从插件源安装")
            return False

        # 安装链路与 API 安装一致，仅在真正安装时才导入预检模块。
        from src.extension_host.plugin_preflight import validate_plugin_checkout

        subdirectory = self._repository_subdirectory(
            plugin_id,
            str(spec.get("subdirectory", "")).strip(),
        )
        source = self.local_repository.resolve().as_uri()
        try:
            record = self._store().install(
                plugin_id,
                source,
                ref=str(spec.get("ref", "")).strip() or "main",
                subdirectory=subdirectory,
                # 本地自定义源不在官方源列表内，按第三方信任需显式确认风险。
                acknowledge_risk=True,
                preflight=lambda checkout: validate_plugin_checkout(
                    plugin_id, checkout
                ),
            )
        except Exception as exc:  # noqa: BLE001 - 安装失败不应阻断服务启动
            print(f"  ✗ 安装失败: {exc}")
            return False

        print(f"  ✓ 已安装: {record.active_revision.commit[:12]}")
        print(f"    来源: {source}")
        print(f"    子目录: {subdirectory}")
        print("    重启服务后生效")
        return True

    # ------------------------------------------------------------------ 报告

    def print_plugin_info(self) -> None:
        print("=" * 60)
        print("DeterminFlow 插件源信息")
        print("=" * 60)
        print(f"插件目录: {self.plugins_dir}")
        print(f"本地插件仓库: {self.local_repository}")
        if self.local_repository.is_dir():
            available = self._available_plugins()
            if available:
                print(f"\n仓库内可用插件 ({len(available)}):")
                for plugin_id in available:
                    print(f"  - {plugin_id}")
        else:
            print("\n⚠️  未找到本地插件仓库")
        print()

    def _available_plugins(self) -> list[str]:
        index = self.local_repository / "plugin-repository.toml"
        if not index.is_file():
            return []
        try:
            document = tomllib.loads(index.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return []
        return sorted(
            str(entry.get("id", "")).strip()
            for entry in document.get("plugins", [])
            if isinstance(entry, dict) and str(entry.get("id", "")).strip()
        )

    def check_and_install_required_plugins(self) -> bool:
        print("=" * 60)
        print("DeterminFlow 插件自动检测和安装")
        print("=" * 60)

        installed_ids = self._installed_plugin_ids()
        repair_needed: list[tuple[str, dict[str, Any]]] = []
        missing: list[tuple[str, dict[str, Any]]] = []
        ready = 0

        for plugin_id, spec in self.REQUIRED_PLUGINS.items():
            display_name = spec.get("name", plugin_id)
            if plugin_id in installed_ids:
                if self._checkout_present(plugin_id):
                    print(f"✓ 插件已安装: {display_name}")
                    ready += 1
                else:
                    print(f"⚠️  插件记录存在但 checkout 缺失: {display_name}")
                    repair_needed.append((plugin_id, spec))
            else:
                print(f"✗ 插件缺失: {display_name}")
                missing.append((plugin_id, spec))

        for plugin_id, spec in repair_needed:
            print(
                f"  ℹ️  {plugin_id} 需要通过 Web 界面「更新」或卸载后重装来修复"
            )

        if missing:
            print(f"\n检测到 {len(missing)} 个缺失的插件，正在安装...")
            for plugin_id, spec in missing:
                if self._install_plugin(plugin_id, spec):
                    ready += 1
                else:
                    print(f"  ⚠️  插件安装失败: {plugin_id}")

        print()
        print("=" * 60)
        print(
            f"✓ 插件检测完成: {ready}/{len(self.REQUIRED_PLUGINS)} "
            "个必需插件已就绪"
        )
        print("=" * 60)

        return ready == len(self.REQUIRED_PLUGINS)


def main() -> int:
    manager = PluginManager()
    manager.print_plugin_info()
    success = manager.check_and_install_required_plugins()
    return 0 if success else 1


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
