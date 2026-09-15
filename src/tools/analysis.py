"""Resolve 21 analysis, using the installed Blackmagic scripting API contract."""
import json
from ..services.resolve_connection import get_resolve, get_media_pool


def _target(clip_name):
    version = get_resolve().GetVersion()
    if not version or int(version[0]) < 21:
        raise RuntimeError("These analysis tools require Resolve 21 or newer.")
    folder = get_media_pool().GetCurrentFolder()
    if folder is None:
        raise RuntimeError("No current media pool folder.")
    if not clip_name:
        return folder
    matches = [c for c in (folder.GetClipList() or []) if c.GetName() == clip_name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one clip named {clip_name!r} in the current bin; found {len(matches)}.")
    return matches[0]


def _run(method, clip_name, *args):
    target = _target(clip_name)
    operation = getattr(target, method, None)
    if not callable(operation):
        raise RuntimeError(f"Installed Resolve does not expose {method}.")
    result = operation(*args)
    return json.dumps({"success": bool(result), "target": target.GetName(),
                       "operation": method,
                       "detail": None if result else "Resolve returned failure. Check media, Studio features, and required Extras packages."})


def register(mcp):
    @mcp.tool()
    def resolve_transcribe_audio(clip_name: str = "", use_speaker_detection: bool = False) -> str:
        """Transcribe a uniquely named clip in the current bin. Empty name processes the current folder AND nested folders. Requires Resolve 21."""
        return _run("TranscribeAudio", clip_name, use_speaker_detection)

    @mcp.tool()
    def resolve_classify_audio(clip_name: str = "") -> str:
        """Classify audio for a uniquely named clip. Empty name processes the current folder AND nested folders. Requires Resolve 21."""
        return _run("PerformAudioClassification", clip_name)

    @mcp.tool()
    def resolve_analyze_intellisearch(clip_name: str = "", identify_faces: bool = False,
                                    better_mode: bool = False) -> str:
        """Analyze a clip, or current folder when name is empty, for IntelliSearch. Face analysis is opt-in. Requires Resolve 21 and the Faster/Better Extras package."""
        return _run("AnalyzeForIntellisearch", clip_name, identify_faces, better_mode)
