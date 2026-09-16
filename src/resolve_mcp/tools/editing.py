"""Existing editing tool names, with validation and recoverable replacement."""
import json
import math
from ..services.resolve_connection import get_timeline, get_project
from ..services.lookup import timeline_clip, item_info
from ..services.replacement import replace_clip, backup_timeline
from ..services.transforms import set_transform
from ..services.results import structured_json


def _get_clip_at_playhead():
    item = get_timeline().GetCurrentVideoItem()
    if item is None:
        raise RuntimeError("No video clip at the current playhead position.")
    return item


def _get_clip_by_index(track_index: int, clip_index: int):
    return timeline_clip(get_timeline(), "video", track_index, clip_index)


def _selected(track_index, clip_index, writable=False):
    timeline = get_timeline()
    if track_index == clip_index == 0:
        item = _get_clip_at_playhead()
        if writable:
            track_type, track = item.GetTrackTypeAndIndex()
            if timeline.GetIsTrackLocked(track_type, track):
                raise ValueError("The selected clip's track is locked.")
        return item
    if track_index <= 0 or clip_index <= 0:
        raise ValueError("Provide both positive track_index and clip_index, or leave both zero for playhead.")
    return timeline_clip(timeline, "video", track_index, clip_index, writable)


def register(mcp):
    @mcp.tool()
    @structured_json
    def resolve_set_clip_transform(pan: float | None = None, tilt: float | None = None,
                                   zoom_x: float | None = None, zoom_y: float | None = None,
                                   rotation: float | None = None, opacity: float | None = None,
                                   track_index: int = 0, clip_index: int = 0) -> str:
        """Set pan/tilt, zoom (0–100), rotation (-360–360), opacity (0–100).
        Targets playhead, or explicit 1-based video track/clip indices. Validates before writing.
        Returns JSON including original values and any partial failure."""
        values = {k: v for k, v in (("Pan", pan), ("Tilt", tilt), ("ZoomX", zoom_x),
                  ("ZoomY", zoom_y if zoom_y is not None else zoom_x),
                  ("RotationAngle", rotation), ("Opacity", opacity)) if v is not None}
        return json.dumps(set_transform(_selected(track_index, clip_index, True), get_timeline(), values))

    @mcp.tool()
    @structured_json
    def resolve_get_clip_transform(track_index: int = 0, clip_index: int = 0) -> str:
        """Read clip transform values at the playhead or explicit 1-based video track/clip indices."""
        item = _selected(track_index, clip_index)
        props = {key: item.GetProperty(key) for key in ("Pan", "Tilt", "ZoomX", "ZoomY", "RotationAngle",
                 "Opacity", "CropLeft", "CropRight", "CropTop", "CropBottom")}
        return json.dumps(dict(props, name=item.GetName()))

    @mcp.tool()
    @structured_json
    def resolve_set_clip_speed(speed: float, track_index: int = 0, clip_index: int = 0) -> str:
        """Legacy speed-property request. Resolve may reject it; timeline retiming is not guaranteed by the API.
        This acts on the underlying media-pool property, potentially affecting other uses of the media."""
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("Speed percentage must be finite and positive.")
        item = _selected(track_index, clip_index, True)
        media = item.GetMediaPoolItem()
        result = bool(media and media.SetClipProperty("Speed", str(speed)))
        return json.dumps({"success": result, "clip": item.GetName(), "requested_speed": speed,
                           "scope": "media pool property", "detail": "Use Edit-page Retime controls if unsupported."})

    @mcp.tool()
    @structured_json
    def resolve_set_clip_enabled(enabled: bool, track_index: int = 0, clip_index: int = 0) -> str:
        """Enable/disable a clip at playhead or explicit 1-based video track/clip indices."""
        item = _selected(track_index, clip_index, True)
        before = item.GetClipEnabled()
        result = item.SetClipEnabled(enabled)
        return json.dumps({"success": bool(result), "clip": item.GetName(), "before": before,
                           "requested_enabled": enabled})

    @mcp.tool()
    @structured_json
    def resolve_create_compound_clip(track_index: int = 1, start_clip: int = 1, end_clip: int = 0,
                                     name: str = "Compound Clip") -> str:
        """Create a compound clip from a 1-based video-track range. Creates a recovery timeline first."""
        timeline = get_timeline()
        timeline_clip(timeline, "video", track_index, start_clip, writable=True)
        items = timeline.GetItemListInTrack("video", track_index) or []
        end_clip = end_clip or len(items)
        if not start_clip <= end_clip <= len(items) or not name.strip():
            raise ValueError("Invalid compound clip range or name.")
        backup = backup_timeline(get_project(), timeline)
        result = timeline.CreateCompoundClip(items[start_clip - 1:end_clip], {"name": name})
        return json.dumps({"success": bool(result), "name": name, "clip_count": end_clip-start_clip+1,
                           "recovery_timeline": backup.GetName()})

    @mcp.tool()
    @structured_json
    def resolve_delete_clip(track_type: str = "video", track_index: int = 2, clip_index: int = 1,
                            ripple: bool = False) -> str:
        """Delete exactly one clip; defaults to non-ripple. Linked peers remain. Creates a recovery copy."""
        timeline, project = get_timeline(), get_project()
        item = timeline_clip(timeline, track_type, track_index, clip_index, writable=True)
        before = item_info(item)
        backup = backup_timeline(project, timeline)
        linked = item.GetLinkedItems() or []
        unlinked = False
        try:
            if linked:
                if not timeline.SetClipsLinked([item, *linked], False):
                    raise RuntimeError("Could not unlink target; delete was not attempted.")
                unlinked = True
            if not timeline.DeleteClips([item], ripple):
                raise RuntimeError("Resolve refused deletion.")
            return json.dumps({"success": True, "deleted": before, "ripple": ripple,
                               "recovery_timeline": backup.GetName()})
        except Exception as exc:
            # The clip survives every failure path here, so restore the links
            # the unlink step broke instead of leaving the pair silently split.
            repair = {}
            if unlinked:
                try:
                    repair["links_restored"] = bool(timeline.SetClipsLinked([item, *linked], True))
                except Exception:
                    repair["links_restored"] = False
            try:
                selected = bool(project.SetCurrentTimeline(backup))
            except Exception:
                selected = False
            return json.dumps({"success": False, "error": str(exc), "recovery_timeline": backup.GetName(),
                               "backup_selected": selected, "original_repair": repair})

    @mcp.tool()
    @structured_json
    def resolve_replace_clip(track_index: int, clip_index: int, new_clip_name: str,
                             source_start_frame: int = 0, source_end_frame: int = 0, media_type: int = 1,
                             dry_run: bool = False, new_media_id: str = "") -> str:
        """Replace at the original record position without ripple. Video-only preserves linked audio.
        Indices are 1-based. media_type 1 targets video; 2 targets audio. Combined replacement is rejected.
        source_end_frame is EXCLUSIVE; zero auto-matches source_start_frame + original duration.
        Source FPS must match timeline. Native source-out readbacks are reported separately.
        Validates bounds/locks/ambiguity and creates a recovery timeline before mutation.
        dry_run returns the plan without edits; new_media_id disambiguates duplicate names."""
        return json.dumps(replace_clip(track_index, clip_index, new_clip_name, source_start_frame,
                                       source_end_frame, media_type, dry_run, new_media_id))
