"""Shared deterministic media and timeline lookup, with ambiguity rejection."""
from .resolve_connection import get_media_pool


def walk_folders(folder, path=""):
    path = f"{path}/{folder.GetName()}" if path else folder.GetName()
    yield path, folder
    for child in folder.GetSubFolderList() or []:
        yield from walk_folders(child, path)


def find_media(name: str = "", media_id: str = ""):
    if not name and not media_id:
        raise ValueError("Provide an exact media name or media_id.")
    matches = []
    for _, folder in walk_folders(get_media_pool().GetRootFolder()):
        for clip in folder.GetClipList() or []:
            if (clip.GetMediaId() == media_id if media_id else clip.GetName() == name):
                matches.append(clip)
    if len(matches) != 1:
        raise ValueError(f"Expected one matching media clip; found {len(matches)}. Use media_id to disambiguate.")
    return matches[0]


def validate_track(timeline, track_type: str, track_index: int, writable=False):
    if track_type not in ("video", "audio", "subtitle"):
        raise ValueError("track_type must be video, audio, or subtitle.")
    if track_index < 1 or track_index > timeline.GetTrackCount(track_type):
        raise ValueError(f"No {track_type} track {track_index}.")
    if writable and timeline.GetIsTrackLocked(track_type, track_index):
        raise ValueError(f"{track_type} track {track_index} is locked.")


def timeline_clip(timeline, track_type: str, track_index: int, clip_index: int, writable=False):
    validate_track(timeline, track_type, track_index, writable)
    items = timeline.GetItemListInTrack(track_type, track_index) or []
    if clip_index < 1 or clip_index > len(items):
        raise ValueError(f"No clip {clip_index} on {track_type} track {track_index}.")
    return items[clip_index - 1]


def item_info(item) -> dict:
    return {"id": item.GetUniqueId(), "name": item.GetName(), "start": item.GetStart(),
            "end": item.GetEnd(), "duration": item.GetDuration()}