"""Read-only snapshots. Reads never select a project, bin, or timeline."""
import json
from .services.resolve_connection import get_project, get_timeline, get_media_pool, is_connected, get_resolve
from .tools.media import _folder_to_dict


def register(mcp):
    @mcp.resource("resolve://system/status", mime_type="application/json")
    def system_status() -> str:
        if not is_connected():
            return json.dumps({"connected": False})
        resolve = get_resolve()
        return json.dumps({"connected": True, "product": resolve.GetProductName(),
                           "version": resolve.GetVersionString(), "page": resolve.GetCurrentPage()})

    @mcp.resource("resolve://project/current", mime_type="application/json")
    def current_project() -> str:
        project = get_project()
        return json.dumps({"name": project.GetName(), "timeline_count": project.GetTimelineCount(),
                           "settings": project.GetSetting()})

    @mcp.resource("resolve://timeline/current", mime_type="application/json")
    def current_timeline() -> str:
        timeline = get_timeline()
        return json.dumps({"name": timeline.GetName(), "start": timeline.GetStartFrame(),
                           "end": timeline.GetEndFrame(), "timecode": timeline.GetCurrentTimecode()})

    @mcp.resource("resolve://timeline/items", mime_type="application/json")
    def timeline_items() -> str:
        timeline = get_timeline()
        tracks = []
        for kind in ("video", "audio", "subtitle"):
            for index in range(1, timeline.GetTrackCount(kind) + 1):
                tracks.append({"type": kind, "index": index, "name": timeline.GetTrackName(kind, index),
                               "items": [{"name": item.GetName(), "start": item.GetStart(), "end": item.GetEnd()}
                                         for item in (timeline.GetItemListInTrack(kind, index) or [])]})
        return json.dumps(tracks)

    @mcp.resource("resolve://mediapool/clips", mime_type="application/json")
    def media_clips() -> str:
        return json.dumps(_folder_to_dict(get_media_pool().GetCurrentFolder()))

    @mcp.resource("resolve://render/jobs", mime_type="application/json")
    def render_jobs() -> str:
        return json.dumps(get_project().GetRenderJobList() or [])
