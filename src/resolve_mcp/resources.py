"""Read-only MCP snapshots; unavailable application state has a JSON error envelope."""
import json
from .services import resolve_connection as conn
from .services.lookup import walk_folders, item_info

RESOURCE_URIS = (
    "system/status", "project/current", "project/list", "project/settings", "project/timelines",
    "timeline/current", "timeline/tracks", "timeline/items", "timeline/markers",
    "mediapool/folders", "mediapool/current-folder", "mediapool/clips",
    "render/jobs", "render/formats", "render/presets", "render/is-rendering",
)


def tracks(timeline, include_items=False):
    result = []
    for kind in ("video", "audio", "subtitle"):
        for index in range(1, timeline.GetTrackCount(kind) + 1):
            items = timeline.GetItemListInTrack(kind, index) or []
            track = {"type": kind, "index": index, "name": timeline.GetTrackName(kind, index),
                     "enabled": timeline.GetIsTrackEnabled(kind, index),
                     "locked": timeline.GetIsTrackLocked(kind, index), "item_count": len(items)}
            if include_items:
                track["items"] = [dict(item_info(item), clip_index=i) for i, item in enumerate(items, 1)]
            result.append(track)
    return result


def clips(folder):
    return [{"id": c.GetMediaId(), "name": c.GetName(), "properties": c.GetClipProperty() or {},
             "metadata": c.GetMetadata() or {}} for c in folder.GetClipList() or []]


def snapshot(name: str):
    if name == "system/status":
        return conn.status()
    if name == "project/list":
        return conn.get_project_manager().GetProjectListInCurrentFolder() or []
    project = conn.get_project()
    if name == "project/current":
        return {"name": project.GetName(), "timeline_count": project.GetTimelineCount()}
    if name == "project/settings":
        return project.GetSetting() or {}
    if name == "project/timelines":
        return [{"index": i, "name": project.GetTimelineByIndex(i).GetName()}
                for i in range(1, project.GetTimelineCount() + 1)]
    if name.startswith("timeline/"):
        timeline = conn.get_timeline()
        if name == "timeline/current":
            return {"name": timeline.GetName(), "start": timeline.GetStartFrame(), "end": timeline.GetEndFrame(),
                    "timecode": timeline.GetCurrentTimecode(), "frame_rate": timeline.GetSetting("timelineFrameRate")}
        if name in ("timeline/tracks", "timeline/items"):
            return tracks(timeline, name.endswith("items"))
        if name == "timeline/markers":
            return timeline.GetMarkers() or {}
    if name.startswith("mediapool/"):
        pool = conn.get_media_pool()
        if name == "mediapool/folders":
            return [{"path": path, "clip_count": len(folder.GetClipList() or [])}
                    for path, folder in walk_folders(pool.GetRootFolder())]
        folder = pool.GetCurrentFolder()
        if folder is None:
            raise RuntimeError("No media pool folder selected.")
        if name == "mediapool/clips":
            return clips(folder)
        if name == "mediapool/current-folder":
            return {"name": folder.GetName(), "clips": clips(folder),
                    "subfolders": [f.GetName() for f in folder.GetSubFolderList() or []]}
    if name == "render/jobs":
        return [dict(job, status=project.GetRenderJobStatus(job["JobId"]) or {})
                for job in project.GetRenderJobList() or []]
    if name == "render/formats":
        return {key: {"extension": value, "codecs": project.GetRenderCodecs(value) or {}}
                for key, value in (project.GetRenderFormats() or {}).items()}
    if name == "render/presets":
        return {"standard": project.GetRenderPresetList() or [], "quick_export": project.GetQuickExportRenderPresets() or []}
    if name == "render/is-rendering":
        return {"is_rendering": project.IsRenderingInProgress()}
    raise ValueError(f"Unknown resource: {name}")


def read_snapshot(name: str) -> str:
    try:
        return json.dumps({"success": True, "data": snapshot(name)}, allow_nan=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": {"code": "state_unavailable", "message": str(exc)}})


def register(mcp):
    def make_reader(name):
        def read() -> str:
            return read_snapshot(name)
        read.__name__ = name.replace("/", "_").replace("-", "_")
        read.__doc__ = f"Read-only snapshot: {name}. Returns success/data or success/error JSON."
        return read
    for name in RESOURCE_URIS:
        mcp.resource(f"resolve://{name}", mime_type="application/json")(make_reader(name))
