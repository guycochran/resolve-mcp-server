"""Frame/timecode conversion, including 29.97 and 59.94 drop-frame labels."""
import math
import re


def fps_value(value) -> float:
    try:
        result = float(str(value).split()[0])
    except (ValueError, IndexError, TypeError):
        raise ValueError(f"Unrecognized frame rate: {value!r}") from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Frame rate must be finite and positive.")
    return result


def to_frame(timecode: str, fps) -> int:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})([:;])(\d{2,3})", timecode)
    if not match:
        raise ValueError("Use HH:MM:SS:FF timecode, or HH:MM:SS;FF for drop-frame.")
    h, m, s, sep, f = match.groups()
    h, m, s, f = map(int, (h, m, s, f))
    rate = fps_value(fps)
    nominal = round(rate)
    if h > 23 or m > 59 or s > 59 or f >= nominal:
        raise ValueError("Timecode component is out of range.")
    frames = ((h * 60 + m) * 60 + s) * nominal + f
    if sep == ";":
        if not (abs(rate - 29.97) < 0.01 or abs(rate - 59.94) < 0.01):
            raise ValueError("Drop-frame is supported only at 29.97 and 59.94 fps.")
        drop = 2 if nominal == 30 else 4
        if m % 10 and s == 0 and f < drop:
            raise ValueError("This frame label is skipped in drop-frame timecode.")
        total_minutes = h * 60 + m
        frames -= drop * (total_minutes - total_minutes // 10)
    return frames


def playhead_offset(timeline) -> int:
    return to_frame(timeline.GetCurrentTimecode(), timeline.GetSetting("timelineFrameRate")) - int(timeline.GetStartFrame())


def from_frame(frame: int, fps, drop_frame=False) -> str:
    rate = fps_value(fps)
    nominal = round(rate)
    if frame < 0:
        raise ValueError("Frame must be nonnegative.")
    if drop_frame:
        if not (abs(rate - 29.97) < 0.01 or abs(rate - 59.94) < 0.01):
            raise ValueError("Unsupported drop-frame rate.")
        drop = 2 if nominal == 30 else 4
        per_minute = nominal * 60 - drop
        per_ten = nominal * 600 - drop * 9
        blocks, remainder = divmod(frame, per_ten)
        frame += drop * 9 * blocks + drop * max(0, (remainder - drop) // per_minute)
    seconds, f = divmod(frame, nominal)
    minutes, s = divmod(seconds, 60)
    h, m = divmod(minutes, 60)
    return f"{h % 24:02}:{m:02}:{s:02}{';' if drop_frame else ':'}{f:02}"
