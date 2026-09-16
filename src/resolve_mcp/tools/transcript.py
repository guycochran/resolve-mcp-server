"""Transcript and caption tools: Resolve's own speech recognition, read back as text."""
from ..services import transcript as tx
from ..services.lookup import find_media
from ..services.resolve_connection import get_timeline
from ..services.results import structured
from .analysis import require_studio


def register(mcp):
    @mcp.tool()
    @structured
    def resolve_create_captions(language: str = "auto", preset: str = "default", chars_per_line: int = 0,
                                line_break: str = "single", gap_frames: int = 0,
                                dry_run: bool = False) -> dict:
        """Auto-caption the CURRENT timeline with Resolve's speech recognition (Studio, adds a subtitle track).
        Clips and audio are not changed. The native true/false result is unreliable, so success means a
        new subtitle track or new cues were read back. Then use resolve_get_transcript(source="captions").
        language: auto, english, spanish, ...; preset: default, netflix, teletext; chars_per_line 0 = preset default."""
        resolve = require_studio()
        timeline = get_timeline()
        settings = tx.caption_settings(resolve, language, preset, chars_per_line, line_break, gap_frames)
        tracks_before = int(timeline.GetTrackCount("subtitle") or 0)
        cues_before = len(tx.timeline_cues(timeline))
        plan = {"timeline": timeline.GetName(), "language": language, "preset": preset,
                "subtitle_tracks_before": tracks_before, "cues_before": cues_before}
        if dry_run:
            return dict(plan, success=True, dry_run=True)
        native = timeline.CreateSubtitlesFromAudio(settings)
        tracks_after = int(timeline.GetTrackCount("subtitle") or 0)
        cues = tx.timeline_cues(timeline)
        created = tracks_after > tracks_before or len(cues) > cues_before
        new_track = tracks_after if tracks_after > tracks_before else None
        new_cues = [c for c in cues if new_track is None or c["track"] == new_track]
        result = dict(plan, success=created, dry_run=False, native_result=bool(native),
                      subtitle_tracks_after=tracks_after, new_track=new_track, cues_after=len(cues),
                      preview=[c["text"] for c in new_cues[:5]])
        if not created:
            result["error"] = {"code": "captions_not_created", "retryable": True,
                               "message": "No subtitle track or cues appeared. Check that the timeline has "
                                          "audible speech and that Studio AI features are available."}
        return result

    @mcp.tool()
    @structured
    def resolve_get_transcript(source: str = "captions", subtitle_track: int = 0, clip_name: str = "",
                               media_id: str = "", format: str = "json", output_path: str = "",
                               max_entries: int = 2000) -> dict:
        """Read transcript TEXT with timing.
        source="captions": cues from the current timeline's subtitle track(s) (0 = all); seconds are
        timeline-relative, frames absolute. Works on any Resolve 21 Studio after resolve_create_captions.
        source="clip": a media pool clip's full native transcript (Resolve 21.1+) with speakers and
        word times, in seconds from the clip's start; run resolve_transcribe_audio first.
        format json|srt|vtt|text. output_path (absolute, new file) writes SRT/VTT/text to disk."""
        if format not in tx.FORMATS:
            raise ValueError("format must be json, srt, vtt or text.")
        if not 1 <= max_entries <= 20000:
            raise ValueError("max_entries must be 1–20000.")
        if source == "captions":
            timeline = get_timeline()
            entries = tx.timeline_cues(timeline, subtitle_track)
            if not entries:
                raise ValueError("The timeline has no caption cues. Run resolve_create_captions first.")
            info = {"source": "captions", "timeline": timeline.GetName(), "timing": "timeline"}
        elif source == "clip":
            media = find_media(clip_name, media_id)
            data = tx.clip_segments(media)
            entries = data.pop("segments")
            info = dict(data, source="clip", clip=media.GetName(), timing="clip")
        else:
            raise ValueError('source must be "captions" or "clip".')
        result = dict(info, success=True, summary=tx.summarize(entries), truncated=len(entries) > max_entries)
        if format == "json":
            if output_path:
                raise ValueError("output_path needs format srt, vtt or text.")
            result["entries"] = entries[:max_entries]
            return result
        text = tx.render(entries, format)
        if output_path:
            result["written"] = tx.write_new_file(output_path, text)
            result["preview"] = text[:500]
        else:
            result["text"] = text if len(text) <= 200_000 else text[:200_000]
            result["truncated"] = len(text) > 200_000
        return result
