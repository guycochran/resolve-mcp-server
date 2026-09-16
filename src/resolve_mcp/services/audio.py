"""Read-only source-audio analysis with ffmpeg. Never writes or transcodes media."""
import os
import re
import shutil
import subprocess

_SILENCE = re.compile(r"silence_(start|end): (-?[\d.]+)")
_RMS = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)")
DEFAULT_THRESHOLD_DB = -35.0


def ffmpeg_path() -> str:
    path = os.environ.get("RESOLVE_MCP_FFMPEG") or shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg was not found. Install it or set RESOLVE_MCP_FFMPEG to its full path.")
    return path


def _run(args, timeout):
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = subprocess.run([ffmpeg_path(), "-hide_banner", "-nostats", *args], capture_output=True,
                              text=True, errors="replace", timeout=timeout, creationflags=creation)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg did not finish within {timeout} seconds.") from None
    if done.returncode != 0:
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise RuntimeError(f"ffmpeg failed: {tail[0]}")
    return done.stderr + done.stdout


def _slice(path, start, duration, stream):
    if not os.path.isfile(path):
        raise ValueError(f"Source media is not reachable from this machine: {path}")
    if start < 0 or duration <= 0:
        raise ValueError("Invalid analysis range.")
    return ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", path, "-map", f"0:a:{stream}", "-vn"]


def calibrate_threshold(path, start, duration, stream=0, timeout=600) -> dict:
    """Pick a silence threshold from the recording's own levels (100 ms RMS windows).
    Threshold = noise floor + 40% of the floor-to-speech spread (at least 10 dB), clamped to -60..-20 dB.
    silencedetect compares peaks, not RMS, so the margin above the RMS floor must be generous."""
    out = _run([*_slice(path, start, duration, stream), "-af",
                "aresample=48000,asetnsamples=4800,astats=metadata=1:reset=1,"
                "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"], timeout)
    levels = sorted(float(v) if v != "-inf" else -120.0 for v in _RMS.findall(out))
    if len(levels) < 20:
        return {"threshold_db": DEFAULT_THRESHOLD_DB, "method": "default (too little audio to calibrate)"}
    floor = levels[len(levels) // 10]
    speech = levels[(len(levels) * 9) // 10]
    spread = speech - floor
    if spread < 10:
        return {"threshold_db": DEFAULT_THRESHOLD_DB, "noise_floor_db": round(floor, 1),
                "speech_db": round(speech, 1), "method": "default (no clear speech/silence contrast)"}
    threshold = max(-60.0, min(-20.0, floor + max(10.0, spread * 0.4)))
    return {"threshold_db": round(threshold, 1), "noise_floor_db": round(floor, 1),
            "speech_db": round(speech, 1), "method": "calibrated"}


def detect_silence(path, start, duration, threshold_db, min_silence, stream=0, timeout=600):
    """Silent intervals as (start, end) seconds relative to the analyzed slice."""
    if not -90 <= threshold_db <= 0:
        raise ValueError("threshold_db must be between -90 and 0.")
    if min_silence <= 0:
        raise ValueError("min_silence_seconds must be positive.")
    out = _run([*_slice(path, start, duration, stream), "-af",
                f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-"], timeout)
    intervals, begin = [], None
    for kind, value in _SILENCE.findall(out):
        value = max(0.0, min(duration, float(value)))
        if kind == "start":
            begin = value
        elif begin is not None:
            intervals.append((begin, value))
            begin = None
    if begin is not None:
        intervals.append((begin, duration))
    return [(a, b) for a, b in intervals if b > a]
