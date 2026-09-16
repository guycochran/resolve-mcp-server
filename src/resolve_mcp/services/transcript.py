"""Transcript text from Resolve: native auto-captions (all 21.x Studio builds) and,
on 21.1+, MediaPoolItem.GetTranscription. Plus plain SRT/VTT/text writers.

Caption cue text is read with TimelineItem.GetName() on subtitle-track items; cue
timing is the item's record range, so it already reflects the edit.
"""
import re
from pathlib import Path

from .timecode import fps_value, to_frame

LANGUAGES = ("auto", "danish", "dutch", "english", "french", "german", "italian", "japanese",
             "korean", "mandarin_simplified", "mandarin_traditional", "norwegian", "portuguese",
             "russian", "spanish", "swedish")
PRESETS = {"default": "AUTO_CAPTION_SUBTITLE_DEFAULT", "teletext": "AUTO_CAPTION_TELETEXT",
           "netflix": "AUTO_CAPTION_NETFLIX"}
LINE_BREAKS = {"single": "AUTO_CAPTION_LINE_SINGLE", "double": "AUTO_CAPTION_LINE_DOUBLE"}
FORMATS = ("json", "srt", "vtt", "text")


def caption_settings(resolve, language="auto", preset="default", chars_per_line=0,
                     line_break="single", gap=0):
    """Build CreateSubtitlesFromAudio settings keyed by Resolve's own enum constants.
    Plain string keys are silently ignored by Resolve, so a missing constant is an error."""
    language = language.lower()
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)}.")
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESETS)}.")
    if line_break not in LINE_BREAKS:
        raise ValueError("line_break must be single or double.")
    if chars_per_line and not 1 <= chars_per_line <= 60:
        raise ValueError("chars_per_line must be 1–60 (0 keeps Resolve's preset default).")
    if not 0 <= gap <= 10:
        raise ValueError("gap must be 0–10 frames.")
    wanted = [("SUBTITLE_LANGUAGE", f"AUTO_CAPTION_{language.upper()}"),
              ("SUBTITLE_CAPTION_PRESET", PRESETS[preset]),
              ("SUBTITLE_LINE_BREAK", LINE_BREAKS[line_break]),
              ("SUBTITLE_GAP", gap)]
    if chars_per_line:
        wanted.append(("SUBTITLE_CHARS_PER_LINE", chars_per_line))
    settings = {}
    for key_name, value in wanted:
        key = getattr(resolve, key_name, None)
        if isinstance(value, str):
            value = getattr(resolve, value, None)
        if key is None or value is None:
            raise RuntimeError(f"Installed Resolve does not expose the {key_name} caption constant.")
        settings[key] = value
    return settings


def timeline_cues(timeline, track_index: int = 0):
    """Caption cues from one subtitle track (or all when track_index is 0), in record order."""
    count = int(timeline.GetTrackCount("subtitle") or 0)
    if track_index and not 1 <= track_index <= count:
        raise ValueError(f"No subtitle track {track_index}; the timeline has {count}.")
    fps = fps_value(timeline.GetSetting("timelineFrameRate"))
    origin = int(timeline.GetStartFrame())
    cues = []
    for index in ([track_index] if track_index else range(1, count + 1)):
        for item in timeline.GetItemListInTrack("subtitle", index) or []:
            start, end = int(item.GetStart()), int(item.GetEnd())
            cues.append({"track": index, "text": (item.GetName() or "").strip(),
                         "start_frame": start, "end_frame": end,
                         "start_seconds": round((start - origin) / fps, 3),
                         "end_seconds": round((end - origin) / fps, 3)})
    cues.sort(key=lambda cue: (cue["start_frame"], cue["track"]))
    return cues


def _seconds(value, fps, origin_frame):
    """Seconds from clip start for a GetTranscription time (timecode string or number)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    return (to_frame(text, fps) - origin_frame) / fps_value(fps)


def clip_segments(media):
    """Full transcript of a media pool clip (Resolve 21.1+). Times become seconds from clip start."""
    method = getattr(media, "GetTranscription", None)
    if not callable(method):
        raise RuntimeError("This Resolve build has no MediaPoolItem.GetTranscription (added in 21.1). "
                           "Use source='captions' after resolve_create_captions instead.")
    data = method(False) or {}
    segments = data.get("segments") or []
    if not segments:
        raise ValueError("The clip has no transcription. Run resolve_transcribe_audio first.")
    props = media.GetClipProperty() or {}
    fps = props.get("FPS") or "24"
    start_tc = props.get("Start TC") or "00:00:00:00"
    origin = to_frame(start_tc, fps) if re.fullmatch(r"\d{2}:\d{2}:\d{2}[:;]\d{2,3}", start_tc) else 0
    out = []
    for segment in segments:
        entry = {"text": str(segment.get("text", "")).strip(),
                 "start_seconds": round(_seconds(segment.get("start", 0), fps, origin), 3),
                 "end_seconds": round(_seconds(segment.get("end", 0), fps, origin), 3)}
        if segment.get("speaker"):
            entry["speaker"] = segment["speaker"]
        words = segment.get("words")
        if words:
            entry["words"] = [{"text": str(w.get("text", "")).strip(),
                               "start_seconds": round(_seconds(w.get("start", 0), fps, origin), 3),
                               "end_seconds": round(_seconds(w.get("end", 0), fps, origin), 3)}
                              for w in words]
        out.append(entry)
    return {"language": data.get("language"), "segments": out, "clip_start_timecode": start_tc}


def _stamp(seconds: float, separator: str) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def render(entries, fmt: str) -> str:
    """Entries need text, start_seconds and end_seconds (optionally speaker)."""
    if fmt not in FORMATS[1:]:
        raise ValueError("fmt must be srt, vtt or text.")
    rows = [e for e in entries if e.get("text") and e["end_seconds"] > e["start_seconds"]]
    if fmt == "text":
        return "\n".join((f"{e['speaker']}: " if e.get("speaker") else "") + e["text"] for e in rows) + "\n"
    blocks = ["WEBVTT\n"] if fmt == "vtt" else []
    sep = "." if fmt == "vtt" else ","
    for number, e in enumerate(rows, 1):
        head = "" if fmt == "vtt" else f"{number}\n"
        speaker = f"<v {e['speaker']}>" if fmt == "vtt" and e.get("speaker") else ""
        blocks.append(f"{head}{_stamp(e['start_seconds'], sep)} --> {_stamp(e['end_seconds'], sep)}\n"
                      f"{speaker}{e['text']}\n")
    return "\n".join(blocks)


def write_new_file(path: str, content: str) -> str:
    target = Path(path)
    if not target.is_absolute():
        raise ValueError("output_path must be absolute.")
    if not target.parent.is_dir():
        raise ValueError("output_path's folder must already exist.")
    if target.exists():
        raise ValueError("output_path already exists; choose a new file name.")
    target.write_text(content, encoding="utf-8")
    return str(target)


def summarize(entries):
    words = sum(len(e["text"].split()) for e in entries)
    duration = max((e["end_seconds"] for e in entries), default=0)
    return {"entries": len(entries), "words": words,
            "words_per_minute": round(words / (duration / 60), 1) if duration > 0 else None}
