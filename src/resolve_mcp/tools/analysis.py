"""Resolve-native AI, independently implemented from Blackmagic's 21 API docs."""
from ..services.resolve_connection import get_resolve, get_media_pool, get_project
from ..services.lookup import walk_folders
from ..services.results import structured, invoke

COLORS = ("Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
          "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream")


def require_21():
    resolve = get_resolve()
    version = resolve.GetVersion()
    if not version or int(version[0]) < 21:
        raise RuntimeError("These analysis tools require Resolve 21 or newer.")
    return resolve


def _target(clip_name="", folder_path=""):
    require_21()
    pool = get_media_pool()
    folder = pool.GetCurrentFolder()
    if folder_path:
        matches = [f for path, f in walk_folders(pool.GetRootFolder()) if path == folder_path]
        if len(matches) != 1:
            raise ValueError("Folder path must match exactly one path from resolve://mediapool/folders.")
        folder = matches[0]
    if folder is None:
        raise RuntimeError("No current media pool folder.")
    if not clip_name:
        return folder
    matches = [c for c in folder.GetClipList() or [] if c.GetName() == clip_name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one clip named {clip_name!r} in the bin; found {len(matches)}.")
    return matches[0]


def _run(method, clip_name="", folder_path="", *args):
    target = _target(clip_name, folder_path)
    result = invoke(target, method, *args)
    response = {"success": bool(result), "target": target.GetName(), "operation": method,
                "scope": "clip" if clip_name else "folder (native API may include nested folders)",
                "detail": None if result else "Resolve returned failure. Check Studio features, media, and required Extras."}
    if not result and method == "TranscribeAudio":
        # Live-observed: the first call right after import can return false, then succeed.
        response["retryable"] = True
        response["hint"] = "Newly imported media may still be processing. Wait a few seconds and retry once."
    return response


def register(mcp):
    @mcp.tool()
    @structured
    def resolve_transcribe_audio(clip_name: str = "", use_speaker_detection: bool = False,
                                 folder_path: str = "") -> dict:
        """Transcribe one exact clip, or a folder AND nested folders when clip_name is empty.
        folder_path is an exact resource path; empty uses current bin. Requires Resolve 21.
        Returns operation status, not a transcript; speaker detection is optional."""
        return _run("TranscribeAudio", clip_name, folder_path, use_speaker_detection)

    @mcp.tool()
    @structured
    def resolve_clear_transcription(clip_name: str = "", folder_path: str = "") -> dict:
        """Delete transcription for one clip, or the current/specified folder AND nested folders."""
        return _run("ClearTranscription", clip_name, folder_path)

    @mcp.tool()
    @structured
    def resolve_classify_audio(clip_name: str = "", folder_path: str = "") -> dict:
        """Classify audio for one clip, or the current/specified folder AND nested folders."""
        return _run("PerformAudioClassification", clip_name, folder_path)

    @mcp.tool()
    @structured
    def resolve_clear_audio_classification(clip_name: str = "", folder_path: str = "") -> dict:
        """Remove audio classification for one clip, or the current/specified folder AND nested folders."""
        return _run("ClearAudioClassification", clip_name, folder_path)

    @mcp.tool()
    @structured
    def resolve_analyze_intellisearch(clip_name: str = "", identify_faces: bool = False,
                                     better_mode: bool = False, folder_path: str = "") -> dict:
        """Analyze a clip or folder for IntelliSearch. Needs Faster/Better Extras.
        Face identification is opt-in. This starts native analysis; it does not query a search index."""
        return _run("AnalyzeForIntellisearch", clip_name, folder_path, identify_faces, better_mode)

    @mcp.tool()
    @structured
    def resolve_reset_intellisearch() -> dict:
        """Clear IntelliSearch analysis for the ENTIRE current project (Resolve API scope)."""
        require_21()
        result = invoke(get_project(), "ResetIntellisearchAnalysis")
        return {"success": bool(result), "scope": "entire current project"}

    @mcp.tool()
    @structured
    def resolve_analyze_slate(clip_name: str = "", marker_color: str = "Green",
                              folder_path: str = "") -> dict:
        """Run native Slate ID analysis on a clip or folder and add slate markers. Requires AI Slate ID Extras."""
        resolve = require_21()
        if marker_color not in COLORS:
            raise ValueError(f"marker_color must be one of {COLORS}.")
        enum = getattr(resolve, f"MARKER_{marker_color.upper()}", None)
        if enum is None:
            raise RuntimeError("Resolve did not expose the requested marker-color constant.")
        return _run("AnalyzeForSlate", clip_name, folder_path, enum)

    @mcp.tool()
    @structured
    def resolve_remove_motion_blur(clip_name: str, filename: str, format: str = "mov",
                                   codec: str = "H264", extreme_mode: bool = False,
                                   folder_path: str = "") -> dict:
        """Create new deblurred media from ONE uniquely named clip; does not replace timeline clips.
        filename names the native output. Format/codec availability depends on this workstation."""
        if not clip_name or not filename.strip():
            raise ValueError("Provide a clip_name and output filename.")
        target = _target(clip_name, folder_path)
        result = invoke(target, "RemoveMotionBlur",
                        {"FileName": filename, "Format": format, "Codec": codec,
                         "UseExtremeMode": extreme_mode, "UseMarkInMarkOut": False,
                         "RenderAtSourceRes": True, "UseMoreGpuMemory": False})
        return {"success": result is not None and result is not False,
                "original": target.GetName(), "created": result.GetName() if result else None,
                "media_id": result.GetMediaId() if result else None}

    @mcp.tool()
    @structured
    def resolve_generate_speech(text: str, filename: str, voice: str = "Female 1") -> dict:
        """Generate a speech clip into the media pool, leaving the timeline untouched.
        Requires AI Speech Generator Extras. Text is limited to 350 characters."""
        require_21()
        if not text.strip() or len(text) > 350 or not filename.strip() or not voice.strip():
            raise ValueError("Provide 1–350 text characters, a filename, and a voice model.")
        if voice == "Custom Voice":
            raise ValueError("Use a built-in voice; custom voice files are not exposed by this tool.")
        result = invoke(get_project(), "GenerateSpeech",
                        {"TextInput": text, "VoiceModel": voice, "Filename": filename, "AddToTimeline": False}, "")
        return {"success": bool(result), "created": result.GetName() if result else None,
                "media_id": result.GetMediaId() if result else None, "added_to_timeline": False}

    @mcp.tool()
    @structured
    def resolve_disable_background_tasks() -> dict:
        """Disable ALL Resolve background tasks for this application session.
        The API has no corresponding enable call; restart Resolve to reset this setting."""
        invoke(require_21(), "DisableBackgroundTasksForCurrentResolveSession")
        return {"success": True, "scope": "current Resolve session",
                "verification": "Command returned without error; native API returns no status."}