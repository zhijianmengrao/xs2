"""Executable entry for the bundled DeterminFlow backend."""

from __future__ import annotations

import argparse
import multiprocessing
import os
import runpy
import socket
import sys
from pathlib import Path

from desktop.python.runtime import prepare_runtime


def _run_python_compatibility_mode(arguments: list[str]) -> bool:
    """Let the frozen executable act as the Workflow Python interpreter."""
    if not arguments:
        return False
    if arguments[0] == "-m" and len(arguments) >= 2:
        module_name = arguments[1]
        sys.argv = [module_name, *arguments[2:]]
        runpy.run_module(module_name, run_name="__main__", alter_sys=True)
        return True
    script = Path(arguments[0])
    if script.suffix.lower() != ".py":
        return False
    sys.argv = arguments
    runpy.run_path(str(script), run_name="__main__")
    return True


def _parse_server_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeterminFlow desktop backend")
    parser.add_argument("--port", type=int, default=None,
                        help="监听端口（旧协议；0 表示后端自选）")
    parser.add_argument("--user-data-dir", type=Path, required=True)
    return parser.parse_args(arguments)


def _report_port(port: int) -> None:
    """把实际端口写到 stdout 第一行，供上层读取（R47 根治端口竞态）。"""
    sys.stdout.write(f"LISTEN_PORT={port}\n")
    sys.stdout.flush()


def _serve_uvicorn(host: str, port: int) -> None:
    """uvicorn 标准启动（旧协议或已知端口时的统一路径）。"""
    import uvicorn
    from src.web_server import app

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config=None,
        access_log=False,
    )


def _write_port_file(port: int, user_root: Path) -> None:
    """把实际端口写到 user_root/config/backend-port，供 Rust 端读取。"""
    port_file = user_root / "config" / "backend-port"
    port_file.parent.mkdir(parents=True, exist_ok=True)
    port_file.write_text(f"LISTEN_PORT={port}\n", encoding="utf-8")


def _serve_self_select(user_root: Path) -> int:
    """自选端口模式：Python 自己 bind port 0，拿到实际端口后通过文件上报。

    关键：**同一个 socket 直接交给 uvicorn**，不存在「释放再复用」的 TOCTOU 窗口。
    """
    import uvicorn
    from src.web_server import app

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    actual_port = sock.getsockname()[1]

    _write_port_file(actual_port, user_root)
    os.environ["WEB_PORT"] = str(actual_port)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=actual_port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config=config)
    server.run(sockets=[sock])
    return 0


def main(arguments: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    values = list(sys.argv[1:] if arguments is None else arguments)
    if _run_python_compatibility_mode(values):
        return 0

    options = _parse_server_arguments(values)

    if options.port is not None:
        if options.port == 0:
            prepare_runtime(options.user_data_dir, 0)
            return _serve_self_select(options.user_data_dir)
        prepare_runtime(options.user_data_dir, options.port)
        _report_port(options.port)
        _serve_uvicorn("127.0.0.1", options.port)
        return 0

    default_port = int(os.environ.get("WEB_PORT", "8020"))
    prepare_runtime(options.user_data_dir, default_port)
    _report_port(default_port)
    _serve_uvicorn("127.0.0.1", default_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
