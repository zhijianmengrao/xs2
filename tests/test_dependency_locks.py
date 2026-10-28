from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILES = ("requirements.lock", "requirements-dev.lock")



def test_uvloop_is_excluded_on_windows() -> None:
    for lock_file in LOCK_FILES:
        lines = (REPO_ROOT / lock_file).read_text(encoding="utf-8").splitlines()
        uvloop_lines = [line for line in lines if line.startswith("uvloop==")]

        assert len(uvloop_lines) == 1
        marker = Requirement(uvloop_lines[0]).marker
        assert marker is not None

        windows = default_environment()
        windows.update(
            sys_platform="win32",
            platform_python_implementation="CPython",
        )
        assert not marker.evaluate(windows)

        linux = default_environment()
        linux.update(
            sys_platform="linux",
            platform_python_implementation="CPython",
        )
        assert marker.evaluate(linux)


# ------------------------------------------------- R45: uvicorn-worker 迁移
# uvicorn>=0.36 把 gunicorn worker 搬到了独立的 uvicorn-worker 包，
# 旧的 uvicorn.workers 导入即发 DeprecationWarning。这三条一起钉住「Dockerfile
# 用的 worker class 必须真的由已锁定的依赖提供」，任何一边单改都会红。
def _lock_lines(lock_file: str) -> list[str]:
    return (REPO_ROOT / lock_file).read_text(encoding="utf-8").splitlines()


def _require_version(requirements_file: str, package: str) -> str:
    """在 requirements*.txt 里取某个包的钉版本（缺包即失败）。"""
    prefix = f"{package}=="
    hits = [
        line.strip()[len(prefix):]
        for line in (REPO_ROOT / requirements_file).read_text(
            encoding="utf-8").splitlines()
        if line.strip().startswith(prefix)
    ]
    assert len(hits) == 1, f"{requirements_file} 应恰好钉一次 {package}，实际 {hits}"
    return hits[0]


def test_dockerfile_uses_the_packaged_uvicorn_worker() -> None:
    """Dockerfile 必须用 uvicorn_worker.UvicornWorker（旧路径已弃用）。"""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert '"uvicorn_worker.UvicornWorker"' in dockerfile
    assert "uvicorn.workers.UvicornWorker" not in dockerfile


def test_every_worker_class_in_dockerfile_is_provided_by_the_lock() -> None:
    """Dockerfile 里出现的 gunicorn worker class 必须能在锁文件里找到其来源包。

    这条是防止「改了 Dockerfile 却漏刷锁」的直接闸门：uvicorn-worker 没被锁定时，
    镜像里 `--worker-class uvicorn_worker.UvicornWorker` 会在启动瞬间 ModuleNotFound。
    """
    import re

    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    worker_classes = re.findall(r'--worker-class",\s*"([^"]+)"', dockerfile)
    assert worker_classes, "Dockerfile 未声明 --worker-class（生产启动方式变了？）"

    locked = {line.split("==", 1)[0].strip()
              for line in _lock_lines("requirements.lock")}
    for worker_class in worker_classes:
        # "uvicorn_worker.UvicornWorker" -> 分布包名 "uvicorn-worker"
        module = worker_class.split(".")[0]
        package = module.replace("_", "-")
        assert package in locked, (
            f"{worker_class} 的提供包 {package} 不在 requirements.lock 里；"
            f"新增依赖后需重生成锁文件"
        )


def test_uvicorn_worker_pin_is_identical_in_txt_and_both_locks() -> None:
    """requirements.txt 与两份锁的 uvicorn-worker 版本必须一致，且 uvicorn 同锁。"""
    pinned = _require_version("requirements.txt", "uvicorn-worker")
    for lock_file in LOCK_FILES:
        assert f"uvicorn-worker=={pinned}" in _lock_lines(lock_file), (
            f"{lock_file} 的 uvicorn-worker 与 requirements.txt ({pinned}) 不一致"
        )
    # uvicorn-worker 0.4.0 要求 uvicorn>=0.36：主锁里的 uvicorn 也必须存在且够新。
    uvicorn_lines = [line for line in _lock_lines("requirements.lock")
                     if line.startswith("uvicorn==")]
    assert len(uvicorn_lines) == 1, uvicorn_lines
    major, minor, *_ = uvicorn_lines[0].split("==", 1)[1].split(".")
    assert (int(major), int(minor)) >= (0, 36), uvicorn_lines[0]
