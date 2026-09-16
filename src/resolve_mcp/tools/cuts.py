"""Tighten and cut talking-head / podcast recordings into NEW variant timelines."""
import math
import time

from ..services import audio, variant
from ..services.resolve_connection import get_project, get_timeline, get_media_pool
from ..services.results import structured

SAFETY = ("The current timeline is only read. Kept pieces are assembled into a new timeline; "
          "nothing is deleted, rippled or overwritten.")


def _spine(timeline, spine_track_type, spine_track_index):
    return variant.spine(timeline, spine_track_type, spine_track_index)


def _silences(timeline, pieces, fps, threshold_db, min_silence_seconds, audio_stream):
    """Silent ranges per spine item, as absolute record frames, plus calibration details."""
    ranges, calibration = [], []
    for piece in pieces:
        if not piece["path"]:
            raise ValueError(f"{piece['name']!r} has no source file path to analyze.")
        start = piece["source_in"] / fps
        duration = (piece["end"] - piece["start"]) / fps
        threshold = threshold_db
        if not threshold:
            info = audio.calibrate_threshold(piece["path"], start, duration, audio_stream)
            calibration.append(dict(info, clip=piece["name"]))
            threshold = info["threshold_db"]
        for a, b in audio.detect_silence(piece["path"], start, duration, threshold, min_silence_seconds,
                                         audio_stream):
            ranges.append((piece["start"] + round(a * fps), piece["start"] + round(b * fps)))
    return ranges, calibration


def _default_name(timeline, label):
    return f"{timeline.GetName()} - {label} {time.strftime('%H%M%S')}"


def _finish(timeline, pieces, fps, removals, min_keep_seconds, name, dry_run, open_variant, extra):
    if not 0 <= min_keep_seconds <= 10:
        raise ValueError("min_keep_seconds must be 0–10.")
    keeps, summary, preview = variant.plan(timeline, pieces, fps, removals, round(min_keep_seconds * fps))
    result = dict(extra, success=True, dry_run=dry_run, source_timeline=timeline.GetName(),
                  variant_timeline=name, summary=summary, keep_segments=preview[:300],
                  keep_segments_truncated=len(preview) > 300,
                  not_carried_over=variant.uncovered_items(timeline, pieces)[:50], safety=SAFETY)
    if dry_run:
        return result
    built = variant.build(get_project(), get_media_pool(), timeline, keeps, name, fps, open_variant)
    return dict(result, **built)


def register(mcp):
    @mcp.tool()
    @structured
    def resolve_detect_silence(threshold_db: float = 0, min_silence_seconds: float = 0.7,
                               spine_track_type: str = "audio", spine_track_index: int = 1,
                               audio_stream: int = 0) -> dict:
        """Find dead air on the current timeline's dialogue track with ffmpeg (read-only; needs ffmpeg).
        threshold_db 0 = calibrate from the recording's own noise floor. Returns silent ranges as
        timeline-relative seconds (the same scale as resolve_get_transcript captions)."""
        timeline = get_timeline()
        fps, pieces = _spine(timeline, spine_track_type, spine_track_index)
        ranges, calibration = _silences(timeline, pieces, fps, threshold_db, min_silence_seconds, audio_stream)
        origin = int(timeline.GetStartFrame())
        silences = [{"start_seconds": round((a - origin) / fps, 3), "end_seconds": round((b - origin) / fps, 3),
                     "duration_seconds": round((b - a) / fps, 3)} for a, b in variant.merge(ranges)]
        return {"success": True, "timeline": timeline.GetName(), "silences": silences[:1000],
                "truncated": len(silences) > 1000,
                "total_silence_seconds": round(sum(s["duration_seconds"] for s in silences), 2),
                "calibration": calibration or {"threshold_db": threshold_db, "method": "fixed"}}

    @mcp.tool()
    @structured
    def resolve_tighten_silence(threshold_db: float = 0, min_silence_seconds: float = 0.7,
                                keep_pause_seconds: float = 0.25, min_keep_seconds: float = 0.3,
                                new_timeline_name: str = "", spine_track_type: str = "audio",
                                spine_track_index: int = 1, audio_stream: int = 0,
                                dry_run: bool = True, open_variant: bool = True) -> dict:
        """Remove dead air from a talking-head/podcast timeline into a NEW timeline (dry-run by default).
        Silences longer than min_silence_seconds are cut, leaving keep_pause_seconds of breathing room
        at each side so words are not clipped. The spine track (default A1) decides what is kept; its
        clips' own video/audio follow. Items from other media are listed in not_carried_over. Needs ffmpeg."""
        if not 0 <= keep_pause_seconds <= 5:
            raise ValueError("keep_pause_seconds must be 0–5.")
        timeline = get_timeline()
        fps, pieces = _spine(timeline, spine_track_type, spine_track_index)
        ranges, calibration = _silences(timeline, pieces, fps, threshold_db, min_silence_seconds, audio_stream)
        pad = round(keep_pause_seconds * fps)
        removals = [(a + pad, b - pad) for a, b in variant.merge(ranges) if b - a > 2 * pad]
        name = new_timeline_name.strip() or _default_name(timeline, "tightened")
        return _finish(timeline, pieces, fps, removals, min_keep_seconds, name, dry_run, open_variant,
                       {"calibration": calibration or {"threshold_db": threshold_db, "method": "fixed"},
                        "silences_cut": len(removals)})

    @mcp.tool()
    @structured
    def resolve_build_cut_variant(remove: list[dict], new_timeline_name: str = "",
                                  min_keep_seconds: float = 0.0, spine_track_type: str = "audio",
                                  spine_track_index: int = 1, dry_run: bool = True,
                                  open_variant: bool = True) -> dict:
        """Text-based / manual editing: cut the listed ranges into a NEW timeline (dry-run by default).
        remove: [{start_seconds, end_seconds}] in timeline-relative seconds, e.g. caption cues from
        resolve_get_transcript(source="captions") for filler words, false starts or off-topic passages.
        Ranges may overlap; the original timeline is not changed."""
        if not isinstance(remove, list) or not 1 <= len(remove) <= 5000:
            raise ValueError("remove must list 1–5000 ranges.")
        timeline = get_timeline()
        fps, pieces = _spine(timeline, spine_track_type, spine_track_index)
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
        return _finish(timeline, pieces, fps, removals, min_keep_seconds, name, dry_run, open_variant,
                       {"ranges_requested": len(remove)})
