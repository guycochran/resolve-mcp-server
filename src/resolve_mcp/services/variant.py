"""Cut variants: remove time ranges from a timeline by assembling the kept pieces into a
NEW timeline. The source timeline is only read, never edited.

The "spine" is one track (normally the main dialogue audio). Each spine item's media is
re-appended source-accurately; its video and audio come along only if the original used them.
AppendToTimeline's endFrame is exclusive (live-verified on Resolve Studio 21.0.4.5).
"""
import math
import re

from .timecode import fps_value, to_frame

BATCH = 50


def _frames(props):
    try:
        return int(props["Frames"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("A spine clip has no readable frame count.") from None


def _source_offset(item, props, duration):
    """Source in-frame as a 0-based media frame. Some media report timecode-based frames."""
    src_in = int(item.GetSourceStartFrame())
    total = _frames(props)
    if src_in + duration <= total:
        return src_in
    tc = props.get("Start TC") or ""
    if re.fullmatch(r"\d{2}:\d{2}:\d{2}[:;]\d{2,3}", tc):
        shifted = src_in - to_frame(tc, props.get("FPS"))
        if 0 <= shifted and shifted + duration <= total:
            return shifted
    raise ValueError(f"Cannot map {item.GetName()!r} to its source media range.")


def spine(timeline, track_type="audio", track_index=1):
    """Describe the spine track's items; rejects anything that cannot be re-cut frame-exactly."""
    if track_type not in ("video", "audio"):
        raise ValueError("spine track must be video or audio.")
    count = int(timeline.GetTrackCount(track_type) or 0)
    if not 1 <= track_index <= count:
        raise ValueError(f"No {track_type} track {track_index}.")
    fps = fps_value(timeline.GetSetting("timelineFrameRate"))
    items = timeline.GetItemListInTrack(track_type, track_index) or []
    if not items:
        raise ValueError(f"{track_type} track {track_index} is empty.")
    pieces = []
    for item in items:
        media = item.GetMediaPoolItem()
        if media is None:
            raise ValueError(f"{item.GetName()!r} is not a media clip (generator, title or compound).")
        props = media.GetClipProperty() or {}
        if not math.isclose(fps_value(props.get("FPS")), fps, abs_tol=0.01):
            raise ValueError(f"{item.GetName()!r} is not at the timeline frame rate.")
        start, end = int(item.GetStart()), int(item.GetEnd())
        duration = end - start
        native_span = int(item.GetSourceEndFrame()) - int(item.GetSourceStartFrame())
        if native_span not in (duration, duration - 1):
            raise ValueError(f"{item.GetName()!r} appears retimed; speed changes are not supported.")
        kinds = {track_type}
        for linked in item.GetLinkedItems() or []:
            if linked.GetMediaPoolItem() is not None and linked.GetMediaPoolItem().GetMediaId() == media.GetMediaId():
                kinds.add("video" if linked.GetTrackTypeAndIndex()[0] == "video" else "audio")
        pieces.append({"item": item, "media": media, "name": item.GetName(), "start": start, "end": end,
                       "source_in": _source_offset(item, props, duration), "path": props.get("File Path", ""),
                       "kinds": kinds})
    return fps, pieces


def merge(ranges):
    merged = []
    for a, b in sorted(r for r in ranges if r[1] > r[0]):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(r) for r in merged]


def plan(timeline, pieces, fps, remove_frames, min_keep_frames):
    """Kept segments in order. remove_frames are absolute [start, end) record frames."""
    removals = merge(remove_frames)
    keeps, dropped_short = [], 0
    for piece in pieces:
        cursor = piece["start"]
        spans = []
        for a, b in removals:
            if b <= cursor or a >= piece["end"]:
                continue
            if a > cursor:
                spans.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < piece["end"]:
            spans.append((cursor, piece["end"]))
        for a, b in spans:
            if b - a < min_keep_frames:
                dropped_short += b - a
                continue
            offset = piece["source_in"] + (a - piece["start"])
            keeps.append({"piece": piece, "record_start": a, "record_end": b, "source_in": offset,
                          "source_out_exclusive": offset + (b - a), "frames": b - a})
    origin = int(timeline.GetStartFrame())
    kept = sum(k["frames"] for k in keeps)
    original = sum(p["end"] - p["start"] for p in pieces)
    summary = {"segments": len(keeps), "original_frames": original, "kept_frames": kept,
               "removed_frames": original - kept, "short_pieces_dropped_frames": dropped_short,
               "original_seconds": round(original / fps, 2), "kept_seconds": round(kept / fps, 2),
               "removed_seconds": round((original - kept) / fps, 2)}
    preview = [{"from_seconds": round((k["record_start"] - origin) / fps, 3),
                "to_seconds": round((k["record_end"] - origin) / fps, 3), "clip": k["piece"]["name"]}
               for k in keeps]
    return keeps, summary, preview


def uncovered_items(timeline, pieces):
    """Items on other tracks that the variant will NOT contain (not the spine media)."""
    ids = {p["media"].GetMediaId() for p in pieces}
    warnings = []
    for kind in ("video", "audio"):
        for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
            for item in timeline.GetItemListInTrack(kind, index) or []:
                media = item.GetMediaPoolItem()
                if media is None or media.GetMediaId() not in ids:
                    warnings.append(f"{kind} {index}: {item.GetName()!r}")
    for index in range(1, int(timeline.GetTrackCount("subtitle") or 0) + 1):
        cues = len(timeline.GetItemListInTrack("subtitle", index) or [])
        if cues:
            warnings.append(f"subtitle {index}: {cues} caption cues (re-run resolve_create_captions on the variant)")
    return warnings


def _existing_names(project):
    return {project.GetTimelineByIndex(i).GetName() for i in range(1, project.GetTimelineCount() + 1)}


def build(project, pool, timeline, keeps, name, fps, open_variant=True):
    """Create the variant timeline and verify every appended piece. Never touches `timeline`."""
    if not keeps:
        raise ValueError("Nothing would remain; no timeline was created.")
    if name in _existing_names(project):
        raise ValueError(f"A timeline named {name!r} already exists.")
    variant = pool.CreateEmptyTimeline(name)
    if not variant:
        raise RuntimeError("Resolve could not create the variant timeline; nothing was changed.")
    result = {"variant_timeline": name, "source_timeline": timeline.GetName()}
    try:
        if not project.SetCurrentTimeline(variant):
            raise RuntimeError("Could not select the new variant timeline.")
        if not math.isclose(fps_value(variant.GetSetting("timelineFrameRate")), fps, abs_tol=0.01):
            raise RuntimeError("The new timeline's frame rate differs from the source; check project settings.")
        start_tc = timeline.GetStartTimecode()
        if start_tc:
            result["start_timecode_matched"] = bool(variant.SetStartTimecode(start_tc))
        record = int(variant.GetStartFrame())
        infos = []
        for keep in keeps:
            info = {"mediaPoolItem": keep["piece"]["media"], "startFrame": keep["source_in"],
                    "endFrame": keep["source_out_exclusive"], "recordFrame": record, "trackIndex": 1}
            kinds = keep["piece"]["kinds"]
            if kinds != {"video", "audio"}:
                info["mediaType"] = 1 if kinds == {"video"} else 2
            infos.append((info, kinds))
            record += keep["frames"]
        expected = {"video": [], "audio": []}
        for info, kinds in infos:
            for kind in kinds:
                expected[kind].append((info["recordFrame"],
                                       info["recordFrame"] + info["endFrame"] - info["startFrame"]))
        appended = 0
        for offset in range(0, len(infos), BATCH):
            batch = [info for info, _ in infos[offset:offset + BATCH]]
            appended += len(pool.AppendToTimeline(batch) or [])
        actual = {kind: sorted((int(i.GetStart()), int(i.GetEnd()))
                               for i in variant.GetItemListInTrack(kind, 1) or [])
                  for kind in expected}
        mismatched = [kind for kind in expected if actual[kind] != sorted(expected[kind])]
        result.update(appended_items=appended,
                      verified={kind: len(expected[kind]) for kind in expected if kind not in mismatched})
        if mismatched:
            first = {k: {"expected": sorted(expected[k])[:3], "actual": actual[k][:3],
                         "expected_count": len(expected[k]), "actual_count": len(actual[k])} for k in mismatched}
            raise RuntimeError(f"Variant does not match the plan on {', '.join(mismatched)} track 1: {first}")
        result["success"] = True
    except Exception as exc:
        result.update(success=False, error={"code": "variant_failed", "message": str(exc)},
                      note="The source timeline was not modified. The incomplete variant is kept for inspection.")
    finally:
        if not open_variant or not result.get("success"):
            result["source_reselected"] = bool(project.SetCurrentTimeline(timeline))
    return result
