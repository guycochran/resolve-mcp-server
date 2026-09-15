"""Timeline operation tools — list, navigate, playhead, tracks, create."""

import json
from mcp.server.fastmcp import FastMCP
from ..services.resolve_connection import get_project, get_timeline, get_media_pool


def register(mcp: FastMCP):

    @mcp.tool()
    def resolve_list_timelines() -> str:
        """List all timelines in the current project.

        Returns JSON array with each timeline's name, index, duration, and track counts."""
        project = get_project()
        count = project.GetTimelineCount()
        timelines = []
        for i in range(1, count + 1):
            tl = project.GetTimelineByIndex(i)
            if tl:
                timelines.append({
                    "index": i,
                    "name": tl.GetName(),
                    "startTimecode": tl.GetStartTimecode(),
                    "videoTracks": tl.GetTrackCount("video"),
                    "audioTracks": tl.GetTrackCount("audio"),
                    "subtitleTracks": tl.GetTrackCount("subtitle"),
                })
        return json.dumps(timelines, indent=2)

    @mcp.tool()
    def resolve_get_current_timeline() -> str:
        """Get detailed info about the current timeline.

        Returns JSON with name, timecode, track counts, and start/end frames."""
        tl = get_timeline()
        info = {
            "name": tl.GetName(),
            "currentTimecode": tl.GetCurrentTimecode(),
            "startFrame": tl.GetStartFrame(),
            "endFrame": tl.GetEndFrame(),
            "startTimecode": tl.GetStartTimecode(),
            "videoTracks": tl.GetTrackCount("video"),
            "audioTracks": tl.GetTrackCount("audio"),
            "subtitleTracks": tl.GetTrackCount("subtitle"),
        }
        # List track names
        tracks = []
        for track_type in ["video", "audio"]:
            count = tl.GetTrackCount(track_type)
            for idx in range(1, count + 1):
                tracks.append({
                    "type": track_type,
                    "index": idx,
                    "name": tl.GetTrackName(track_type, idx),
                    "enabled": tl.GetIsTrackEnabled(track_type, idx),
                    "locked": tl.GetIsTrackLocked(track_type, idx),
                })
        info["tracks"] = tracks
        return json.dumps(info, indent=2)

    @mcp.tool()
    def resolve_set_current_timeline(name: str = "", index: int = 0) -> str:
        """Switch to a different timeline by name or index.

        Args:
            name: Timeline name to switch to (preferred).
            index: Timeline index (1-based). Used if name is empty.
        """
        project = get_project()
        if name:
            count = project.GetTimelineCount()
            for i in range(1, count + 1):
                tl = project.GetTimelineByIndex(i)
                if tl and tl.GetName() == name:
                    project.SetCurrentTimeline(tl)
                    return f"Switched to timeline: {name}"
            return f"Timeline '{name}' not found."
        elif index > 0:
            tl = project.GetTimelineByIndex(index)
            if tl:
                project.SetCurrentTimeline(tl)
                return f"Switched to timeline {index}: {tl.GetName()}"
            return f"No timeline at index {index}."
        return "Provide either a timeline name or index."

    @mcp.tool()
    def resolve_get_playhead() -> str:
        """Get the current playhead timecode position."""
        tl = get_timeline()
        return tl.GetCurrentTimecode()

    @mcp.tool()
    def resolve_set_playhead(timecode: str) -> str:
        """Set the playhead to a specific timecode.

        Args:
            timecode: Timecode string (e.g., "01:00:05:00").
        """
        tl = get_timeline()
        if tl.SetCurrentTimecode(timecode):
            return f"Playhead set to {timecode}"
        return f"Failed to set playhead to {timecode}. Check the timecode format."

    @mcp.tool()
    def resolve_get_track_items(track_type: str = "video", track_index: int = 1) -> str:
        """List all clips on a specific track.

        Args:
            track_type: "video", "audio", or "subtitle" (default: "video").
            track_index: Track number, 1-based (default: 1).

        Returns JSON array of clips with name, start/end frame, duration, and source info."""
        tl = get_timeline()
        items = tl.GetItemListInTrack(track_type, track_index)
        if not items:
            return json.dumps([])

        result = []
        for item in items:
            clip_info = {
                "name": item.GetName(),
                "start": item.GetStart(),
                "end": item.GetEnd(),
                "duration": item.GetDuration(),
                "enabled": item.GetClipEnabled(),
                "color": item.GetClipColor(),
            }
            mpi = item.GetMediaPoolItem()
            if mpi:
                clip_info["mediaPoolItem"] = mpi.GetName()
            result.append(clip_info)
        return json.dumps(result, indent=2)

    @mcp.tool()
    def resolve_create_timeline(name: str) -> str:
        """Create a new empty timeline.

        Args:
            name: Name for the new timeline.
        """
        mp = get_media_pool()
        tl = mp.CreateEmptyTimeline(name)
        if tl:
            return f"Created timeline: {name}"
        return f"Failed to create timeline '{name}'."

    @mcp.tool()
    def resolve_duplicate_timeline(new_name: str = "") -> str:
        """Duplicate the current timeline.

        Args:
            new_name: Name for the duplicate (optional, defaults to original + " Copy").
        """
        tl = get_timeline()
        name = new_name or f"{tl.GetName()} Copy"
        dup = tl.DuplicateTimeline(name)
        if dup:
            return f"Duplicated timeline as: {name}"
        return "Failed to duplicate timeline."
