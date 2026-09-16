"""Cut variants: remove record-time ranges from a timeline into a NEW timeline.

The source timeline is only read. The variant starts as DuplicateTimeline(source), so it
inherits track count, names, audio channel formats, enable states and timeline settings.
Timelines with locked tracks are refused rather than unlocked (see collect).
Every clip in the copy is then deleted and the kept pieces of each source clip are
appended back onto the same track, closed up so the result has no gaps. Removals are
global (all tracks at once), so multi-camera and multi-mic tracks stay in sync.

AppendToTimeline's endFrame is exclusive (live-verified on Resolve Studio 21.0.4.5).
"""
import math
import re

from .timecode import fps_value, to_frame

BATCH = 50
KINDS = ("video", "audio")


TC = re.compile(r"\d{2}:\d{2}:\d{2}[:;]\d{2,3}")


def frame_count(props):
    """Media length in frames. Audio-only files (e.g. WAV) report an empty "Frames" property on
    Resolve 21.0.4.5 but do carry a Duration timecode, which is used as the fallback."""
    try:
        return int(float(props["Frames"]))
    except (KeyError, TypeError, ValueError):
        pass
    fps = props.get("FPS")
    duration = str(props.get("Duration") or "")
    if TC.fullmatch(duration):
        return to_frame(duration, fps)
    start, end = str(props.get("Start TC") or ""), str(props.get("End TC") or "")
    if TC.fullmatch(start) and TC.fullmatch(end):
        return to_frame(end, fps) - to_frame(start, fps)
    raise ValueError("no readable frame count or duration")


def _source_offset(item, props, duration):
    """Source in-frame as a 0-based media frame. Some media report timecode-based frames."""
    src_in = int(item.GetSourceStartFrame())
    total = frame_count(props)
    if src_in + duration <= total:
        return src_in
    tc = props.get("Start TC") or ""
    if TC.fullmatch(tc):
        shifted = src_in - to_frame(tc, props.get("FPS"))
        if 0 <= shifted and shifted + duration <= total:
            return shifted
    raise ValueError("cannot map it to its source media range")


def _describe(item, kind, index, fps):
    """A carriable clip, or raise ValueError(reason) for anything that can't be re-cut exactly."""
    media = item.GetMediaPoolItem()
    if media is None:
        raise ValueError("not a media clip (title, generator or effect)")
    props = media.GetClipProperty() or {}
    if not props.get("File Path"):
        raise ValueError("no source file (compound, multicam or synthetic clip)")
    if not math.isclose(fps_value(props.get("FPS")), fps, abs_tol=0.01):
        raise ValueError("media frame rate differs from the timeline")
    start, end = int(item.GetStart()), int(item.GetEnd())
    duration = end - start
    native_span = int(item.GetSourceEndFrame()) - int(item.GetSourceStartFrame())
    if native_span not in (duration, duration - 1):
        raise ValueError("retimed (speed change)")
    return {"uid": item.GetUniqueId(), "name": item.GetName(), "kind": kind, "track": index,
            "media": media, "start": start, "end": end, "path": props["File Path"],
            "source_in": _source_offset(item, props, duration),
            "links": {linked.GetUniqueId() for linked in item.GetLinkedItems() or []}}


def collect(timeline, scope="all", spine_type="audio", spine_index=1, allow_locked=False):
    """Clips to carry, grouped per track, plus human-readable notes for what is left out.
    The spine track must be fully carriable; other tracks skip (and list) problem clips."""
    if spine_type not in KINDS:
        raise ValueError("spine track must be video or audio.")
    if scope not in ("all", "spine"):
        raise ValueError('tracks must be "all" or "spine".')
    if not 1 <= spine_index <= int(timeline.GetTrackCount(spine_type) or 0):
        raise ValueError(f"No {spine_type} track {spine_index}.")
    fps = fps_value(timeline.GetSetting("timelineFrameRate"))
    tracks, skipped = [], []
    for kind in KINDS:
        for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1):
            items = timeline.GetItemListInTrack(kind, index) or []
            is_spine = (kind, index) == (spine_type, spine_index)
            if scope == "spine" and not is_spine:
                skipped += [f"{kind} {index}: {i.GetName()!r} (not the spine track)" for i in items]
                continue
            pieces, problems = [], []
            for item in items:
                try:
                    pieces.append(_describe(item, kind, index, fps))
                except ValueError as exc:
                    if is_spine:
                        raise ValueError(f"Spine clip {item.GetName()!r}: {exc}.") from None
                    problems.append(f"{kind} {index}: {item.GetName()!r} ({exc})")
            skipped += problems
            if is_spine and not pieces:
                raise ValueError(f"{kind} track {index} is empty.")
            tracks.append({"kind": kind, "index": index, "pieces": pieces, "problems": problems,
                           "enabled": bool(timeline.GetIsTrackEnabled(kind, index))})
    locked = [f"{kind} {index}" for kind in (*KINDS, "subtitle")
              for index in range(1, int(timeline.GetTrackCount(kind) or 0) + 1)
              if timeline.GetIsTrackLocked(kind, index) and timeline.GetItemListInTrack(kind, index)]
    if locked and not allow_locked:
        # Live finding (Resolve Studio 21.0.4.5): unlocking a track on a duplicated timeline also
        # changes the source timeline's lock, and restoring it does not stick. So nothing is unlocked.
        raise ValueError(f"Unlock these tracks first: {', '.join(locked)}. Variants are built from a "
                         "duplicate, and Resolve shares track-lock changes between a timeline and its copy.")
    for index in range(1, int(timeline.GetTrackCount("subtitle") or 0) + 1):
        cues = len(timeline.GetItemListInTrack("subtitle", index) or [])
        if cues:
            skipped.append(f"subtitle {index}: {cues} caption cues (re-run resolve_create_captions on the variant)")
    return fps, tracks, skipped


def merge(ranges):
    merged = []
    for a, b in sorted(r for r in ranges if r[1] > r[0]):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [tuple(r) for r in merged]


def intersect(a, b):
    """Intersection of two merged interval lists."""
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def extent(timeline, tracks):
    ends = [p["end"] for t in tracks for p in t["pieces"]]
    if not ends:
        raise ValueError("Nothing to carry.")
    return int(timeline.GetStartFrame()), max(ends)


def keep_intervals(domain, removals, min_keep_frames):
    """Complement of removals within domain; kept stretches shorter than min_keep are also removed."""
    lo, hi = domain
    keeps, cursor = [], lo
    for a, b in merge(removals):
        a, b = max(a, lo), min(b, hi)
        if b <= cursor:
            continue
        if a > cursor:
            keeps.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < hi:
        keeps.append((cursor, hi))
    dropped = sum(b - a for a, b in keeps if b - a < min_keep_frames)
    return [k for k in keeps if k[1] - k[0] >= min_keep_frames], dropped


def plan(timeline, tracks, fps, removals, min_keep_frames):
    """Pieces to append (with variant-relative record offsets) and a summary."""
    origin, end = extent(timeline, tracks)
    keeps, dropped = keep_intervals((origin, end), removals, min_keep_frames)
    offsets, total = [], 0
    for a, b in keeps:
        offsets.append(total)
        total += b - a
    appends = []
    for track in tracks:
        for piece in track["pieces"]:
            for k, (a, b) in enumerate(keeps):
                lo, hi = max(a, piece["start"]), min(b, piece["end"])
                if hi <= lo:
                    continue
                src = piece["source_in"] + (lo - piece["start"])
                appends.append({"piece": piece, "kind": track["kind"], "track": track["index"], "keep": k,
                                "offset": offsets[k] + (lo - a), "frames": hi - lo,
                                "source_in": src, "source_out_exclusive": src + hi - lo})
    original = end - origin
    summary = {"segments": len(keeps), "tracks_carried": sum(1 for t in tracks if t["pieces"]),
               "clip_pieces": len(appends), "original_frames": original, "kept_frames": total,
               "removed_frames": original - total, "short_pieces_dropped_frames": dropped,
               "original_seconds": round(original / fps, 2), "kept_seconds": round(total / fps, 2),
               "removed_seconds": round((original - total) / fps, 2)}
    preview = [{"from_seconds": round((a - origin) / fps, 3), "to_seconds": round((b - origin) / fps, 3)}
               for a, b in keeps]
    return {"keeps": keeps, "appends": appends, "origin": origin, "summary": summary, "preview": preview}


def remap_markers(markers, keeps, origin):
    """Timeline markers (frame offsets from timeline start) that fall in kept time, moved to match."""
    out, offset = [], 0
    spans = []
    for a, b in keeps:
        spans.append((a - origin, b - origin, offset))
        offset += b - a
    for frame, info in sorted((markers or {}).items(), key=lambda kv: float(kv[0])):
        f = float(frame)
        for lo, hi, base in spans:
            if lo <= f < hi:
                duration = max(1, min(int(info.get("duration", 1) or 1), int(hi - f)))
                out.append({"frame": int(base + (f - lo)), "info": dict(info, duration=duration)})
                break
    return out


def _link_groups(tracks):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for track in tracks:
        for piece in track["pieces"]:
            for other in piece["links"]:
                parent[find(piece["uid"])] = find(other)
    return {p["uid"]: find(p["uid"]) for t in tracks for p in t["pieces"] if p["links"]}


def _existing_names(project):
    return {project.GetTimelineByIndex(i).GetName() for i in range(1, project.GetTimelineCount() + 1)}


def _empty_copy(variant, notes):
    """Delete every clip (and marker) in the duplicated timeline."""
    for kind in (*KINDS, "subtitle"):
        for index in range(1, int(variant.GetTrackCount(kind) or 0) + 1):
            items = variant.GetItemListInTrack(kind, index) or []
            if not items:
                continue
            if variant.GetIsTrackLocked(kind, index):
                raise RuntimeError(f"{kind} track {index} is locked in the copy; nothing was unlocked.")
            if not variant.DeleteClips(list(items), False) or variant.GetItemListInTrack(kind, index):
                if kind == "subtitle":
                    notes.append(f"subtitle {index}: old caption cues could not be removed from the variant")
                    continue
                raise RuntimeError(f"Could not clear {kind} track {index} in the copy.")
    if (variant.GetMarkers() or {}) and not variant.DeleteMarkersByColor("All"):
        notes.append("old timeline markers could not be removed from the variant")


def build(project, pool, timeline, planned, name, markers=True, open_variant=True):
    """Create and fill the variant, verify every piece, relink and restore markers.
    Never edits `timeline`. On failure the incomplete variant is kept and the source reselected."""
    appends = planned["appends"]
    if not appends:
        raise ValueError("Nothing would remain; no timeline was created.")
    if name in _existing_names(project):
        raise ValueError(f"A timeline named {name!r} already exists.")
    variant = timeline.DuplicateTimeline(name)
    if not variant:
        raise RuntimeError("Resolve could not duplicate the source timeline; nothing was changed.")
    result = {"variant_timeline": name, "source_timeline": timeline.GetName(), "notes": []}
    try:
        if not project.SetCurrentTimeline(variant):
            raise RuntimeError("Could not select the new variant timeline.")
        _empty_copy(variant, result["notes"])
        start = int(variant.GetStartFrame())
        expected = {}
        for step in appends:
            step["record"] = start + step["offset"]
            expected.setdefault((step["kind"], step["track"]), []).append(
                (step["record"], step["record"] + step["frames"]))
        by_track = {}
        for step in appends:
            by_track.setdefault((step["kind"], step["track"]), []).append(step)
        for (kind, index), steps in by_track.items():
            infos = [{"mediaPoolItem": s["piece"]["media"], "startFrame": s["source_in"],
                      "endFrame": s["source_out_exclusive"], "recordFrame": s["record"],
                      "trackIndex": index, "mediaType": 1 if kind == "video" else 2} for s in steps]
            for offset in range(0, len(infos), BATCH):
                pool.AppendToTimeline(infos[offset:offset + BATCH])
        placed = {}
        mismatched = []
        for kind in KINDS:
            for index in range(1, int(variant.GetTrackCount(kind) or 0) + 1):
                items = variant.GetItemListInTrack(kind, index) or []
                actual = sorted((int(i.GetStart()), int(i.GetEnd())) for i in items)
                if actual != sorted(expected.get((kind, index), [])):
                    mismatched.append({"track": f"{kind} {index}", "expected_count": len(expected.get((kind, index), [])),
                                       "actual_count": len(actual), "expected": sorted(expected.get((kind, index), []))[:3],
                                       "actual": actual[:3]})
                for i in items:
                    placed[(kind, index, int(i.GetStart()))] = i
        result["verified_tracks"] = {f"{k} {i}": len(v) for (k, i), v in expected.items()}
        if mismatched:
            raise RuntimeError(f"Variant does not match the plan: {mismatched[:4]}")
        groups = _link_groups([{"pieces": list({s['piece']['uid']: s['piece'] for s in appends}.values())}])
        linksets = {}
        for step in appends:
            group = groups.get(step["piece"]["uid"])
            if group is not None:
                linksets.setdefault((group, step["keep"]), []).append(
                    placed[(step["kind"], step["track"], step["record"])])
        linked = failed = 0
        for members in linksets.values():
            if len(members) < 2:
                continue
            if variant.SetClipsLinked(members, True):
                linked += 1
            else:
                failed += 1
        result["link_groups_restored"] = linked
        if failed:
            result["notes"].append(f"{failed} linked clip groups could not be relinked")
        if markers:
            moved = remap_markers(timeline.GetMarkers() or {}, planned["keeps"], planned["origin"])
            added = 0
            for m in moved:
                info = m["info"]
                if variant.AddMarker(m["frame"], info.get("color", "Blue"), info.get("name", ""),
                                     info.get("note", ""), info["duration"], info.get("customData", "")):
                    added += 1
            result["markers_carried"] = added
            source_count = len(timeline.GetMarkers() or {})
            if added != len(moved):
                result["notes"].append(f"{len(moved) - added} markers could not be re-added")
            if source_count > len(moved):
                result["notes"].append(f"{source_count - len(moved)} markers were inside removed time")
        result["success"] = True
    except Exception as exc:
        result.update(success=False, error={"code": "variant_failed", "message": str(exc)},
                      note="The source timeline was not modified. The incomplete variant is kept for inspection.")
    finally:
        if not open_variant or not result.get("success"):
            result["source_reselected"] = bool(project.SetCurrentTimeline(timeline))
    return result
