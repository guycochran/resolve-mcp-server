"""Waiting on Resolve's long-running work without hand-written polling loops."""
import asyncio
import os
import time

from ..services.resolve_connection import get_project
from ..services.results import error_result

DONE = {"complete", "completed", "failed", "cancelled", "canceled"}


def _job(project, job_id):
    for job in project.GetRenderJobList() or []:
        if job.get("JobId") == job_id:
            return job
    return None


def _output(job):
    if not job or not job.get("TargetDir") or not job.get("OutputFilename"):
        return None
    path = os.path.join(job["TargetDir"], job["OutputFilename"])
    exists = os.path.isfile(path)
    return {"path": path, "exists_on_server": exists, "bytes": os.path.getsize(path) if exists else None}


def register(mcp):
    @mcp.tool()
    async def resolve_wait_for_render(job_id: str = "", timeout_seconds: int = 900,
                                      poll_seconds: float = 2.0, stop_on_timeout: bool = False) -> dict:
        """Wait until a render job (or all rendering, if job_id is empty) finishes, then report the
        final status and output file. Other MCP calls wait while this runs, so keep timeouts modest
        (max 3600 s). stop_on_timeout=True calls StopRendering if the deadline passes."""
        try:
            if not 1 <= timeout_seconds <= 3600 or not 0.5 <= poll_seconds <= 30:
                raise ValueError("timeout_seconds must be 1–3600 and poll_seconds 0.5–30.")
            project = get_project()
            if job_id and _job(project, job_id) is None:
                raise ValueError(f"No render job {job_id!r} in this project's queue.")
            started = time.monotonic()
            samples = 0
            while True:
                status = dict(project.GetRenderJobStatus(job_id) or {}) if job_id else {}
                rendering = bool(project.IsRenderingInProgress())
                state = str(status.get("JobStatus", "")).lower()
                finished = state in DONE if job_id else not rendering
                if job_id and not rendering and state in ("", "ready"):
                    finished = samples > 0  # never started, or queued but not running
                elapsed = round(time.monotonic() - started, 1)
                if finished:
                    return {"success": (state in ("complete", "completed")) if job_id else True,
                            "job_id": job_id or None, "status": status, "rendering": rendering,
                            "elapsed_seconds": elapsed, "output": _output(_job(project, job_id)) if job_id else None}
                if elapsed >= timeout_seconds:
                    stopped = bool(project.StopRendering() is not False) if stop_on_timeout else False
                    return {"success": False, "timed_out": True, "job_id": job_id or None, "status": status,
                            "elapsed_seconds": elapsed, "rendering_stopped": stopped,
                            "error": {"code": "render_timeout", "retryable": True,
                                      "message": "Rendering is still running; call again to keep waiting."}}
                samples += 1
                await asyncio.sleep(poll_seconds)
        except (ValueError, RuntimeError) as exc:
            return error_result(exc)
