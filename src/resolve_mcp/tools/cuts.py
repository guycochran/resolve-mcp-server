"""Tighten and cut talking-head / podcast recordings into NEW variant timelines."""
import math
import time

from ..services import audio, variant
from ..services.resolve_connection import get_project, get_timeline, get_media_pool
from ..services.results import structured

SAFETY = ("The current timeline is only read. The variant is a duplicate that is emptied and refilled "
          "with the kept pieces; nothing in the source is deleted, rippled or overwritten.")


def _track_silence(track, fps, domain, threshold_db, min_silence_seconds, audio_stream, calibration):
    """Silent record ranges on one audio track; time with no clip counts as silent."""
    silent = []
    cursor = domain[0]
    for piece in sorted(track["pieces"], key=lambda p: p["start"]):
        if piece["start"] > cursor:
            silent.append((cursor, piece["start"]))
        cursor = max(cursor, piece["end"])
        start = piece["source_in"] / fps
        duration = (piece["end"] - piece["start"]) / fps
        threshold = threshold_db
        if not threshold:
            info = audio.calibrate_threshold(piece["path"], start, duration, audio_stream)
            calibration.append(dict(info, clip=piece["name"], track=f"audio {track['index']}"))
            threshold = info["threshold_db"]
        for a, b in audio.detect_silence(piece["path"], start, duration, threshold, min_silence_seconds,
                                         audio_stream):
            silent.append((piece["start"] + round(a * fps), piece["start"] + round(b * fps)))
    if cursor < domain[1]:
        silent.append((cursor, domain[1]))
    return variant.merge(silent)


def _silences(timeline, tracks, fps, threshold_db, min_silence_seconds, audio_stream, detect_on,
              spine_type, spine_index):
    """Ranges where every analyzed audio track is silent (min_silence applied to the result)."""
    if detect_on not in ("carried", "spine"):
        raise ValueError('detect_on must be "carried" or "spine".')
    domain = variant.extent(timeline, tracks)
    if detect_on == "spine":
        if spine_type != "audio":
            raise ValueError('detect_on="spine" needs an audio spine track.')
        chosen = [t for t in tracks if (t["kind"], t["index"]) == ("audio", spine_index)]
    else:
        enabled = [t for t in tracks if t["kind"] == "audio" and t["enabled"]]
        unreadable = [p for t in enabled for p in t["problems"]]
        if unreadable:
            # Ignoring a mic we can't analyze would make its speech look like silence.
            raise ValueError("Cannot analyze every enabled audio clip, so shared silence can't be trusted: "
                             f"{'; '.join(unreadable[:5])}. Disable or fix those tracks, or use "
                             'detect_on="spine".')
        chosen = [t for t in enabled if t["pieces"]]
    if not chosen:
        raise ValueError("No enabled audio track with clips to analyze.")
    calibration, combined = [], None
    for track in chosen:
        ranges = _track_silence(track, fps, domain, threshold_db, min_silence_seconds, audio_stream, calibration)
        combined = ranges if combined is None else variant.intersect(combined, ranges)
    minimum = round(min_silence_seconds * fps)
    result = [(a, b) for a, b in combined if b - a >= minimum]
    return result, calibration, [f"audio {t['index']}" for t in chosen]


def _default_name(timeline, label):
    return f"{timeline.GetName()} - {label} {time.strftime('%H%M%S')}"


def _finish(timeline, tracks, skipped, fps, removals, min_keep_seconds, name, dry_run, open_variant,
            markers, extra):
    if not 0 <= min_keep_seconds <= 10:
        raise ValueError("min_keep_seconds must be 0–10.")
    planned = variant.plan(timeline, tracks, fps, removals, round(min_keep_seconds * fps))
    result = dict(extra, success=True, dry_run=dry_run, source_timeline=timeline.GetName(),
                  variant_timeline=name, summary=planned["summary"], keep_segments=planned["preview"][:300],
                  keep_segments_truncated=len(planned["preview"]) > 300,
                  not_carried_over=skipped[:50], not_carried_over_count=len(skipped), safety=SAFETY)
    if dry_run:
        return result
    built = variant.build(get_project(), get_media_pool(), timeline, planned, name, markers, open_variant)
    return dict(result, **built)


def register(mcp):
    @mcp.tool()
    @structured
    def resolve_detect_silence(threshold_db: float = 0, min_silence_seconds: float = 0.7,
                               tracks: str = "all", detect_on: str = "carried",
                               spine_track_type: str = "audio", spine_track_index: int = 1,
                               audio_stream: int = 0) -> dict:
        """Find dead air on the current timeline with ffmpeg (read-only; needs ffmpeg).
        detect_on="carried" reports only time when EVERY enabled audio track is quiet (safe for
        multi-mic podcasts); "spine" analyzes just the spine track. threshold_db 0 = calibrate per clip.
        Returns timeline-relative seconds (the same scale as resolve_get_transcript captions)."""
        timeline = get_timeline()
        fps, carried, _ = variant.collect(timeline, tracks, spine_track_type, spine_track_index)
        ranges, calibration, analyzed = _silences(timeline, carried, fps, threshold_db, min_silence_seconds,
                                                  audio_stream, detect_on, spine_track_type, spine_track_index)
        origin = int(timeline.GetStartFrame())
        silences = [{"start_seconds": round((a - origin) / fps, 3), "end_seconds": round((b - origin) / fps, 3),
                     "duration_seconds": round((b - a) / fps, 3)} for a, b in ranges]
        return {"success": True, "timeline": timeline.GetName(), "analyzed_tracks": analyzed,
                "silences": silences[:1000], "truncated": len(silences) > 1000,
                "total_silence_seconds": round(sum(s["duration_seconds"] for s in silences), 2),
                "calibration": calibration or {"threshold_db": threshold_db, "method": "fixed"}}

    @mcp.tool()
    @structured
    def resolve_tighten_silence(threshold_db: float = 0, min_silence_seconds: float = 0.7,
                                keep_pause_seconds: float = 0.25, min_keep_seconds: float = 0.3,
                                new_timeline_name: str = "", tracks: str = "all", detect_on: str = "carried",
                                spine_track_type: str = "audio", spine_track_index: int = 1,
                                audio_stream: int = 0, carry_markers: bool = True,
                                dry_run: bool = True, open_variant: bool = True) -> dict:
        """Remove dead air from a talking-head/podcast timeline into a NEW timeline (dry-run by default).
        A pause is cut only where every enabled mic track is quiet for longer than min_silence_seconds;
        keep_pause_seconds of room stays at each side. All tracks are cut together, so cameras and mics
        stay in sync; timeline markers in kept time move with the edit. Needs ffmpeg.
        tracks="all" (default) carries every video/audio track, keeping mics and cameras in sync;
        tracks="spine" carries only the spine track (A1 by default)."""
        if not 0 <= keep_pause_seconds <= 5:
            raise ValueError("keep_pause_seconds must be 0–5.")
        timeline = get_timeline()
        fps, carried, skipped = variant.collect(timeline, tracks, spine_track_type, spine_track_index)
        ranges, calibration, analyzed = _silences(timeline, carried, fps, threshold_db, min_silence_seconds,
                                                  audio_stream, detect_on, spine_track_type, spine_track_index)
        pad = round(keep_pause_seconds * fps)
        lo, hi = variant.extent(timeline, carried)
        removals = []
        for a, b in ranges:
            a2 = a if a <= lo else a + pad
            b2 = b if b >= hi else b - pad
            if b2 > a2:
                removals.append((a2, b2))
        name = new_timeline_name.strip() or _default_name(timeline, "tightened")
        return _finish(timeline, carried, skipped, fps, removals, min_keep_seconds, name, dry_run, open_variant,
                       carry_markers,
                       {"calibration": calibration or {"threshold_db": threshold_db, "method": "fixed"},
                        "analyzed_tracks": analyzed, "silences_cut": len(removals)})

    @mcp.tool()
    @structured
    def resolve_build_cut_variant(remove: list[dict], new_timeline_name: str = "",
                                  min_keep_seconds: float = 0.0, tracks: str = "all",
                                  spine_track_type: str = "audio", spine_track_index: int = 1,
                                  carry_markers: bool = True, dry_run: bool = True,
                                  open_variant: bool = True) -> dict:
        """Text-based / manual editing: cut the listed ranges from ALL carried tracks into a NEW timeline
        (dry-run by default). remove: [{start_seconds, end_seconds}] in timeline-relative seconds, e.g.
        caption cues from resolve_get_transcript(source="captions") for filler words, false starts or
        off-topic passages. Ranges may overlap; the original timeline is not changed.
        tracks="all" (default) carries every video/audio track, keeping mics and cameras in sync;
        tracks="spine" carries only the spine track (A1 by default)."""
        if not isinstance(remove, list) or not 1 <= len(remove) <= 5000:
            raise ValueError("remove must list 1–5000 ranges.")
        timeline = get_timeline()
        fps, carried, skipped = variant.collect(timeline, tracks, spine_track_type, spine_track_index)
        origin = int(timeline.GetStartFrame())
        removals = []
        for entry in remove:
            try:
                a, b = float(entry["start_seconds"]), float(entry["end_seconds"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Each range needs numeric start_seconds and end_seconds.") from None
            if not (math.isfinite(a) and math.isfinite(b)) or a < 0 or b <= a:
                raise ValueError(f"Invalid range {entry!r}.")
            removals.append((origin + round(a * fps), origin + round(b * fps)))
        name = new_timeline_name.strip() or _default_name(timeline, "cut")
        return _finish(timeline, carried, skipped, fps, removals, min_keep_seconds, name, dry_run, open_variant,
                       carry_markers, {"ranges_requested": len(remove)})
