"""Validate all transform inputs before the first mutation; report partial failures."""
import math


def set_transform(item, timeline, values: dict) -> dict:
    limits = {"ZoomX": (0, 100), "ZoomY": (0, 100), "RotationAngle": (-360, 360), "Opacity": (0, 100)}
    for key, setting in (("Pan", "timelineResolutionWidth"), ("Tilt", "timelineResolutionHeight")):
        if key in values:
            size = float(timeline.GetSetting(setting))
            if size <= 0:
                raise ValueError(f"Cannot validate {key}: missing timeline dimensions.")
            limits[key] = (-4 * size, 4 * size)
    for key, value in values.items():
        lo, hi = limits[key]
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"{key} must be finite and between {lo} and {hi}.")
    before = {key: item.GetProperty(key) for key in values}
    changed = {}
    for key, value in values.items():
        if not item.SetProperty(key, value):
            return {"success": False, "clip": item.GetName(), "before": before, "changed": changed,
                    "failed_property": key, "error": "Resolve refused this property; earlier changes remain."}
        changed[key] = value
    return {"success": True, "clip": item.GetName(), "before": before, "changed": changed}