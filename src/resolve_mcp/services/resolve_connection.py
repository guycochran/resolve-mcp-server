"""Central Resolve discovery, health checks, cooldown, and diagnostic state."""
import importlib
import os
import sys
import subprocess
import threading
import time
from pathlib import PurePosixPath, PureWindowsPath

_resolve = None
_last_error = None
_last_checked = float("-inf")
_last_attempt = float("-inf")
_lock = threading.RLock()
HEALTH_INTERVAL = 5.0
RETRY_INTERVAL = 2.0


def scripting_paths(platform=None, env=None):
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    path_type = PureWindowsPath if platform == "win32" else PurePosixPath
    if platform == "win32":
        base = str(path_type(env.get("PROGRAMDATA", "C:/ProgramData")) /
                   "Blackmagic Design/DaVinci Resolve/Support/Developer/Scripting")
    elif platform == "darwin":
        base = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
    else:
        base = "/opt/resolve/Developer/Scripting"
    api = env.get("RESOLVE_SCRIPT_API") or base
    return env.get("PYTHONPATH_RESOLVE") or str(path_type(api) / "Modules")


def _connect():
    global _resolve, _last_error, _last_attempt, _last_checked
    _last_attempt = time.monotonic()
    modules = scripting_paths()
    if modules not in sys.path:
        sys.path.insert(0, modules)
    try:
        module = importlib.import_module("DaVinciResolveScript")
        candidate = module.scriptapp("Resolve")
        if candidate is None or not candidate.GetProductName():
            raise RuntimeError("Resolve did not return a live scripting connection.")
        _resolve = candidate
        _last_checked = time.monotonic()
        _last_error = None
    except Exception as exc:
        _resolve = None
        _last_error = f"{type(exc).__name__}: {exc}"


def is_connected() -> bool:
    global _resolve, _last_checked, _last_error
    with _lock:
        now = time.monotonic()
        if _resolve is not None:
            if now - _last_checked < HEALTH_INTERVAL:
                return True
            try:
                if _resolve.GetProductName():
                    _last_checked = now
                    return True
                _last_error = "Resolve's previous connection is no longer live."
            except Exception as exc:
                _last_error = f"{type(exc).__name__}: {exc}"
            _resolve = None
        if now - _last_attempt >= RETRY_INTERVAL:
            _connect()
        return _resolve is not None


def get_resolve():
    if not is_connected():
        raise RuntimeError(
            "Cannot connect to Resolve. Start Resolve Studio; set Preferences > System > General > "
            "External scripting using to Local. Use a compatible 64-bit Python installation. "
            f"Scripting modules: {scripting_paths()}. Detail: {_last_error}")
    return _resolve


def get_project_manager():
    manager = get_resolve().GetProjectManager()
    if manager is None:
        raise RuntimeError("Resolve has no accessible project manager.")
    return manager


def get_project():
    project = get_project_manager().GetCurrentProject()
    if project is None:
        raise RuntimeError("No project is currently open in DaVinci Resolve.")
    return project


def get_timeline():
    timeline = get_project().GetCurrentTimeline()
    if timeline is None:
        raise RuntimeError("No timeline is currently selected.")
    return timeline


def get_media_pool():
    pool = get_project().GetMediaPool()
    if pool is None:
        raise RuntimeError("No media pool is available.")
    return pool


def get_media_storage():
    storage = get_resolve().GetMediaStorage()
    if storage is None:
        raise RuntimeError("No media storage is available.")
    return storage


def reconnect() -> bool:
    global _resolve
    with _lock:
        _resolve = None
        _connect()
        return _resolve is not None


def status() -> dict:
    connected = is_connected()
    result = {"connected": connected, "process_running": process_running(), "scripting_modules": scripting_paths(),
              "python": sys.version.split()[0], "platform": sys.platform,
              "error": None if connected else _last_error}
    if connected:
        try:
            product = _resolve.GetProductName()
            result.update(product=product, version=_resolve.GetVersionString(),
                          edition="Studio" if "studio" in product.lower() else "Free/unknown",
                          page=_resolve.GetCurrentPage())
        except Exception as exc:
            result.update(connected=False, error=f"Resolve disconnected during status read: {exc}")
    return result


def process_running() -> bool | None:
    """OS process presence is separate from scripting availability; unknown is None."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/FO", "CSV", "/NH"],
                                    capture_output=True, text=True, timeout=3,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            return "resolve.exe" in result.stdout.lower() if result.returncode == 0 else None
        result = subprocess.run(["pgrep", "-x", "Resolve"], capture_output=True, timeout=3)
        return result.returncode == 0 if result.returncode in (0, 1) else None
    except (OSError, subprocess.SubprocessError):
        return None
