#!/usr/bin/env python3
"""
环境检查脚本 - 检测所有必需的依赖和配置
支持 Windows、Linux、macOS
"""
import sys
import os
import subprocess
import platform
from pathlib import Path


# 支持面下限：与 pyproject.toml requires-python / web/package.json
# engines.node 的下限同账（tests/test_environment_check.py 的 P10 钉住）。
MIN_PYTHON = (3, 11)
MIN_NODE = (22, 12)


class EnvironmentChecker:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        self.system = platform.system()

    def check_python_version(self):
        """检查 Python 版本"""
        version = sys.version_info
        if (version.major, version.minor) < MIN_PYTHON:
            self.errors.append(
                f"Python 版本过低: {version.major}.{version.minor}.{version.micro}，"
                f"需要 {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"
            )
            return False
        self.info.append(f"✅ Python {version.major}.{version.minor}.{version.micro}")
        return True

    def check_nodejs(self):
        """检查 Node.js"""
        node_cmds = ["node", "node.exe"] if self.system == "Windows" else ["node", "nodejs"]

        for cmd in node_cmds:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    # 检查版本号（下限与 engines.node 同账）
                    try:
                        parts = version.lstrip('v').split('.')
                        node_version = (
                            int(parts[0]),
                            int(parts[1]) if len(parts) > 1 else 0,
                        )
                        if node_version < MIN_NODE:
                            self.warnings.append(
                                f"⚠️  Node.js 版本较低: {version}，"
                                f"推荐 {MIN_NODE[0]}.{MIN_NODE[1]}+"
                            )
                        else:
                            self.info.append(f"✅ Node.js {version}")
                    except (ValueError, IndexError):
                        self.info.append(f"✅ Node.js {version}")
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        self.warnings.append("⚠️  Node.js 未安装或不在 PATH 中")
        self.warnings.append("   下载: https://nodejs.org/")
        self.warnings.append("   前端功能将不可用（仅后端API模式）")
        return False

    def check_npm(self):
        """检查 npm"""
        npm_cmd = "npm.cmd" if self.system == "Windows" else "npm"

        try:
            result = subprocess.run(
                [npm_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.info.append(f"✅ npm {version}")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self.warnings.append("⚠️  npm 不可用")
        return False

    def check_git(self):
        """检查 Git（可选）"""
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.info.append(f"✅ {version}")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        self.info.append("ℹ️  Git 未安装（可选，用于版本控制）")
        return False

    def check_venv(self, root_dir):
        """检查虚拟环境"""
        venv_dir = root_dir / ".venv"
        if venv_dir.exists():
            python_exe = venv_dir / "Scripts" / "python.exe" if self.system == "Windows" else venv_dir / "bin" / "python"
            if python_exe.exists():
                self.info.append(f"✅ 虚拟环境已创建")
                return True

        self.warnings.append("⚠️  虚拟环境未创建（脚本会自动创建）")
        return False

    def check_dependencies(self, root_dir):
        """检查 Python 依赖是否已安装"""
        try:
            # 尝试导入关键依赖
            import fastapi
            import uvicorn
            self.info.append("✅ Python 依赖已安装")
            return True
        except ImportError:
            self.warnings.append("⚠️  Python 依赖未安装（脚本会自动安装）")
            return False

    def check_config_files(self, root_dir):
        """检查配置文件"""
        env_file = root_dir / ".env"
        if not env_file.exists():
            env_example = root_dir / ".env.example"
            if env_example.exists():
                self.warnings.append("⚠️  .env 文件不存在（脚本会从 .env.example 复制）")
            else:
                self.errors.append("❌ .env.example 文件不存在，无法创建配置")
                return False
        else:
            self.info.append("✅ .env 配置文件存在")

        config_dir = root_dir / "config"
        if not config_dir.exists():
            self.warnings.append("⚠️  config/ 目录不存在")
        else:
            self.info.append("✅ config/ 目录存在")

        return True

    def check_frontend(self, root_dir):
        """检查前端"""
        web_dir = root_dir / "web"
        if not web_dir.exists():
            self.warnings.append("⚠️  web/ 目录不存在，无前端")
            return False

        dist_dir = web_dir / "dist"
        if dist_dir.exists() and (dist_dir / "index.html").exists():
            self.info.append("✅ 前端已构建")
            return True

        self.warnings.append("⚠️  前端未构建（脚本会自动构建）")
        return False

    def check_disk_space(self, root_dir):
        """检查磁盘空间"""
        try:
            if self.system == "Windows":
                import shutil
                total, used, free = shutil.disk_usage(root_dir)
                free_gb = free / (1024**3)
                if free_gb < 1:
                    self.errors.append(f"❌ 磁盘空间不足: {free_gb:.2f} GB，需要至少 1 GB")
                    return False
                elif free_gb < 5:
                    self.warnings.append(f"⚠️  磁盘空间较少: {free_gb:.2f} GB")
                else:
                    self.info.append(f"✅ 磁盘空间充足: {free_gb:.2f} GB 可用")
        except:
            pass
        return True

    def run_all_checks(self, root_dir):
        """运行所有检查"""
        print("=" * 60)
        print("DeterminFlow 环境检查")
        print("=" * 60)
        print()

        # 关键检查
        self.check_python_version()
        self.check_nodejs()
        self.check_npm()
        self.check_git()

        # 项目检查
        self.check_venv(root_dir)
        self.check_dependencies(root_dir)
        self.check_config_files(root_dir)
        self.check_frontend(root_dir)
        self.check_disk_space(root_dir)

        # 输出结果
        if self.info:
            print("✅ 环境状态:")
            for msg in self.info:
                print(f"   {msg}")
            print()

        if self.warnings:
            print("⚠️  警告:")
            for msg in self.warnings:
                print(f"   {msg}")
            print()

        if self.errors:
            print("❌ 错误:")
            for msg in self.errors:
                print(f"   {msg}")
            print()
            print("请解决上述错误后重试。")
            return False

        if self.warnings:
            print("ℹ️  环境检查完成，发现一些警告，但启动脚本会自动处理。")
        else:
            print("✅ 环境检查通过！可以启动服务。")

        print()
        return True


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    checker = EnvironmentChecker()
    success = checker.run_all_checks(root)
    sys.exit(0 if success else 1)
