"""Consistent errors for new workflow tools; legacy tool names remain intact."""
import json
from functools import wraps


def error_result(exc):
    code = "invalid_request" if isinstance(exc, ValueError) else "resolve_error"
    return {"success": False, "error": {"code": code, "message": str(exc)}}


def structured(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, RuntimeError) as exc:
            return error_result(exc)
    return call


def structured_json(function):
    """Like structured, for legacy tools that return JSON text: rejections become
    {"success": false, "error": {...}} instead of MCP tool errors."""
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, RuntimeError) as exc:
            return json.dumps(error_result(exc))
    return call


RECOVERY_POLICY = {
    "backup": "A full copy of the timeline is made before any clip is changed.",
    "on_failure": "Mis-sized inserts are removed and broken links restored where possible; "
                  "the recovery copy is then selected.",
    "original_timeline": "Kept for inspection and may be modified; references are not redirected.",
    "cleanup": "Neither timeline is deleted automatically.",
}


def render_succeeded(result):
    """Interpret RenderWithQuickExport's native result: True, False, or None when unknown."""
    if not result or isinstance(result, str) or (isinstance(result, dict) and result.get("Error")):
        return False
    if not isinstance(result, dict):
        return None
    status = str(result.get("Status", result.get("JobStatus", ""))).lower()
    if not status:
        return None
    return status in ("complete", "completed", "success", "render complete")


def invoke(target, method, *args):
    operation = getattr(target, method, None)
    if not callable(operation):
        raise RuntimeError(f"Installed Resolve does not expose {method}.")
    return operation(*args)