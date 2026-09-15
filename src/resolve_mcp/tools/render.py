"""Render & export tools — quick export, render jobs, timeline export."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_resolve, get_project, get_timeline


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_list_render_presets() -> str:
        """List all available render presets (both standard and Quick Export).

        Returns JSON with standard render presets and Quick Export presets."""
        project = get_project()
        standard = project.GetRenderPresetList() or []
        quick = project.GetQuickExportRenderPresets() or []
        formats = project.GetRenderFormats() or {}
        current = project.GetCurrentRenderFormatAndCodec() or {}

        return json.dumps({
            "standardPresets": standard,
            "quickExportPresets": quick,
            "availableFormats": formats,
            "currentFormatAndCodec": current,
        }, indent=2)

    @mcp.tool()
    def resolve_quick_export(
        preset: str,
        output_dir: str = "",
        filename: str = "",
    ) -> str:
        """Render the current timeline using a Quick Export preset.

        Common presets: "H.264 Master", "H.265 Master", "ProRes 422 HQ",
        "YouTube", "Vimeo", "TikTok", "Twitter".

        Args:
            preset: Quick Export preset name.
            output_dir: Output directory (optional, uses project default if empty).
            filename: Custom filename (optional, uses timeline name if empty).
        """
        project = get_project()
        params = {}
        if output_dir:
            params["TargetDir"] = output_dir
        if filename:
            params["CustomName"] = filename

        result = project.RenderWithQuickExport(preset, params)
        if result:
            return json.dumps({"status": "rendering", "preset": preset, "result": str(result)})
        return f"Failed to start Quick Export with preset '{preset}'. Check preset name with resolve_list_render_presets."

    @mcp.tool()
    def resolve_add_render_job(
        output_dir: str,
        filename: str = "",
        format: str = "",
        codec: str = "",
        width: int = 0,
        height: int = 0,
        frame_rate: float = 0,
    ) -> str:
        """Add a custom render job to the render queue.

        Args:
            output_dir: Output directory path.
            filename: Custom filename (optional).
            format: Video format (e.g., "mov", "mp4"). Leave empty for project default.
            codec: Codec name (e.g., "ProRes422", "H264"). Leave empty for project default.
            width: Output width. 0 = use project setting.
            height: Output height. 0 = use project setting.
            frame_rate: Output FPS. 0 = use project setting.
        """
        project = get_project()

        settings = {
            "SelectAllFrames": True,
            "TargetDir": output_dir,
            "ExportVideo": True,
            "ExportAudio": True,
        }
        if filename:
            settings["CustomName"] = filename
        if width > 0:
            settings["FormatWidth"] = width
        if height > 0:
            settings["FormatHeight"] = height
        if frame_rate > 0:
            settings["FrameRate"] = frame_rate

        project.SetRenderSettings(settings)

        if format and codec:
            project.SetCurrentRenderFormatAndCodec(format, codec)

        job_id = project.AddRenderJob()
        if job_id:
            return json.dumps({"jobId": job_id, "settings": settings})
        return "Failed to add render job. Check settings."

    @mcp.tool()
    def resolve_start_render() -> str:
        """Start rendering all queued render jobs."""
        project = get_project()
        if project.StartRendering():
            return "Rendering started."
        return "Failed to start rendering. Check render queue."

    @mcp.tool()
    def resolve_get_render_status() -> str:
        """Get the status of all render jobs.

        Returns JSON with each job's status, progress percentage, and completion state."""
        project = get_project()
        is_rendering = project.IsRenderingInProgress()
        jobs = project.GetRenderJobList() or []

        status_list = []
        for job in jobs:
            job_id = job.get("JobId", "")
            if job_id:
                job_status = project.GetRenderJobStatus(job_id)
                job.update(job_status or {})
            status_list.append(job)

        return json.dumps({
            "isRendering": is_rendering,
            "jobs": status_list,
        }, indent=2)

    @mcp.tool()
    def resolve_export_timeline(
        output_path: str,
        format: str = "fcpxml",
    ) -> str:
        """Export the current timeline to an interchange format.

        Args:
            output_path: Absolute path for the output file.
            format: Export format — "fcpxml" (default), "edl", "csv", "aaf", "otio".
        """
        resolve = get_resolve()
        tl = get_timeline()

        format_map = {
            "aaf": ("EXPORT_AAF", "EXPORT_AAF_NEW"),
            "edl": ("EXPORT_EDL", "EXPORT_NONE"),
            "fcpxml": ("EXPORT_FCPXML_1_10", "EXPORT_NONE"),
            "csv": ("EXPORT_TEXT_CSV", "EXPORT_NONE"),
            "otio": ("EXPORT_OTIO", "EXPORT_NONE"),
        }

        if format not in format_map:
            return f"Unknown format '{format}'. Use: {', '.join(format_map.keys())}"

        export_type_name, export_subtype_name = format_map[format]

        # Get the enum values from the resolve object
        export_type = getattr(resolve, export_type_name, None)
        export_subtype = getattr(resolve, export_subtype_name, None)

        if export_type is None:
            return f"Export type {export_type_name} not available in this Resolve version."

        if tl.Export(output_path, export_type, export_subtype):
            return f"Exported timeline '{tl.GetName()}' as {format} to {output_path}"
        return f"Failed to export timeline as {format}."
