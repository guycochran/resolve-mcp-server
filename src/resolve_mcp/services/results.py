"""Consistent errors for new workflow tools; legacy tool names remain intact."""
from functools import wraps


def structured(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (ValueError, RuntimeError) as exc:
            return {"success": False, "error": {"code": "invalid_request" if isinstance(exc, ValueError)
                                              else "resolve_error", "message": str(exc)}}
    return call


def invoke(target, method, *args):
    operation = getattr(target, method, None)
    if not callable(operation):
        raise RuntimeError(f"Installed Resolve does not expose {method}.")
    return operation(*args)