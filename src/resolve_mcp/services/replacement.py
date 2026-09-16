"""Conservative non-ripple edits with full-timeline recovery copies."""
import math
import uuid
from .lookup import find_media, timeline_clip, item_info
from .resolve_connection import get_project, get_timeline, get_media_pool
from .timecode import fps_value


def source_range(media, timeline, start: int, duration: int, end_exclusive: int = 0):
    """Validate AppendToTimeline's half-open source range [start, end_exclusive).

    Live-verified on Resolve Studio 21.0.4.5. TimelineItem.GetSourceEndFrame()
    is a separate native readback and must not be reused as an append bound.
    Zero requests automatic duration matching.
    """
    if start < 0 or duration < 1:
        raise ValueError("Source in must be nonnegative and duration positive.")
    props = media.GetClipProperty() or {}
    try:
        frames = int(props["Frames"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Source frame count is unavailable; cannot validate media bounds.") from None
    source_fps = fps_value(props.get("FPS"))
    timeline_fps = fps_value(timeline.GetSetting("timelineFrameRate"))
    if not math.isclose(source_fps, timeline_fps, abs_tol=0.01):
        raise ValueError("Source and timeline frame rates differ. Conform media before this frame-exact operation.")
    end_exclusive = start + duration if end_exclusive == 0 else end_exclusive
    if end_exclusive <= start or end_exclusive > frames:
        raise ValueError(f"Source range [{start}, {end_exclusive}) exceeds media bounds [0, {frames}).")
    if end_exclusive - start != duration:
        raise ValueError("Source range must match the original timeline duration exactly.")
    return start, end_exclusive


def backup_timeline(project, timeline):
    name = f"{timeline.GetName()} - MCP recovery {uuid.uuid4().hex[:8]}"
    backup = timeline.DuplicateTimeline(name)
    if not backup:
        raise RuntimeError("Recovery timeline creation failed; no clips were changed.")
    if not project.SetCurrentTimeline(timeline):
        raise RuntimeError(f"Could not reselect original timeline. Recovery copy: {name}. No clips were changed.")
    return backup


def replace_clip(track_index: int, clip_index: int, new_clip_name: str,
                 source_start_frame: int = 0, source_end_frame: int = 0, media_type: int = 1,
                 dry_run: bool = False, new_media_id: str = "") -> dict:
    if media_type not in (1, 2):
        raise ValueError("Use media_type 1 (video) or 2 (audio); combined replacement cannot safely target both tracks.")
    track_type = "video" if media_type == 1 else "audio"
    project, timeline, pool = get_project(), get_timeline(), get_media_pool()
    old = timeline_clip(timeline, track_type, track_index, clip_index, writable=True)
    before = item_info(old)
    duration = before["end"] - before["start"]
    if not isinstance(duration, (int, float)) or duration < 1 or int(duration) != duration:
        raise ValueError("Replacement requires an integral, positive timeline duration.")
    if before["start"] < timeline.GetStartFrame():
        raise ValueError("Invalid record position before timeline start.")
    media = find_media(new_clip_name, new_media_id)
    source_in, source_out_exclusive = source_range(
        media, timeline, source_start_frame, int(duration), source_end_frame)
    linked = old.GetLinkedItems() or []
    # Preserve raw TimelineItem readbacks without assigning append-range semantics.
    recovery = dict(before, source_in_native=old.GetSourceStartFrame(), source_out_native=old.GetSourceEndFrame(),
                    properties=old.GetProperty() or {}, markers=old.GetMarkers() or {})
    plan = {"success": True, "dry_run": dry_run, "original": recovery, "replacement": media.GetName(),
            "media_id": media.GetMediaId(), "track_type": track_type, "track_index": track_index,
            "record_start": before["start"], "duration_frames": duration,
            "source_in": source_in, "source_out_exclusive": source_out_exclusive, "ripple": False,
            "linked_items_preserved": [item_info(item) for item in linked]}
    if dry_run:
        return plan
    backup = backup_timeline(project, timeline)
    plan["recovery_timeline"] = backup.GetName()
    plan["original_timeline"] = timeline.GetName()
    deleted = False
    unlinked = False
    inserted = []
    insert_verified = False
    try:
        if linked:
            if not timeline.SetClipsLinked([old, *linked], False):
                raise RuntimeError("Could not unlink the target from linked clips; deletion was not attempted.")
            unlinked = True
        if not timeline.DeleteClips([old], False):
            raise RuntimeError("Resolve refused the non-ripple deletion.")
        deleted = True
        inserted = pool.AppendToTimeline([{"mediaPoolItem": media, "trackIndex": track_index,
                                          "recordFrame": before["start"], "startFrame": source_in,
                                          "endFrame": source_out_exclusive, "mediaType": media_type}]) or []
        if len(inserted) != 1:
            raise RuntimeError("Resolve did not return exactly one replacement item.")
        new = inserted[0]
        if new.GetStart() != before["start"] or new.GetEnd() != before["end"]:
            raise RuntimeError("Inserted clip position or duration differs from the requested edit.")
        insert_verified = True
        if linked and not timeline.SetClipsLinked([new, *linked], True):
            raise RuntimeError("Replacement inserted, but the original link relationships could not be restored.")
        plan["inserted"] = item_info(new)
        plan["note"] = "Recovery copy retains original grades, Fusion, retiming, and links. Replacement uses new media defaults."
        return plan
    except Exception as exc:
        # Best-effort repair of the ORIGINAL timeline before switching away:
        # remove a mis-sized insert and restore the links the unlink step broke.
        # A verified insert is never removed — only its link restoration failed.
        repair = {}
        if inserted and not insert_verified:
            try:
                repair["bad_insert_removed"] = bool(timeline.DeleteClips(list(inserted), False))
            except Exception:
                repair["bad_insert_removed"] = False
        if unlinked and not deleted:
            try:
                repair["links_restored"] = bool(timeline.SetClipsLinked([old, *linked], True))
            except Exception:
                repair["links_restored"] = False
        elif unlinked and not insert_verified:
            repair["links_restored"] = False  # original was deleted; nothing to relink to
        try:
            active_backup = bool(project.SetCurrentTimeline(backup))
        except Exception:
            active_backup = False
        return dict(plan, success=False, deleted_original=deleted,
                    error={"code": "replacement_failed", "message": str(exc)},
                    recovery={"backup_selected": active_backup, "timeline": backup.GetName(),
                              "original_repair": repair,
                              "original_timeline_may_be_modified": True,
                              "instruction": "Use the complete recovery timeline. The original timeline is retained for inspection; references are not automatically redirected."})
