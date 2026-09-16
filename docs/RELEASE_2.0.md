# Resolve MCP Server 2.0 implementation report

## 1. Architecture

The existing FastMCP and central connection model remain. Code now lives in an
installable `src/resolve_mcp` package with environment validation, HTTP authentication,
shared lookup/timecode/replacement helpers, read-only snapshots, and separate
native-AI and VLM modules. All tool/resource requests are serialized per process.

## 2. Preserved functionality

All **53 original tool names** remain: connection/navigation; project management;
timeline and media browsing/import; clip replacement, transforms, speed requests,
enable/disable and compounds; color/LUTs; markers; titles; rendering/export; Fusion;
and Moondream caption/detection/Q&A. Both stdio and Streamable HTTP remain.

Safety changes are explicit: append source out is exclusive, combined A/V replacement is
rejected, audio-only replacement addresses an audio track, and ambiguous lookup or
unverifiable media bounds fails before deletion. Some legacy tools still return
text/JSON text; new workflows return structured dicts.

## 3. New native Resolve 21 functionality

- `resolve_transcribe_audio`, including optional speaker detection.
- `resolve_clear_transcription`.
- `resolve_classify_audio` and `resolve_clear_audio_classification`.
- `resolve_analyze_intellisearch` and project-wide `resolve_reset_intellisearch`.
- `resolve_analyze_slate`, using Resolve marker enums.
- `resolve_remove_motion_blur`, creating new media.
- `resolve_generate_speech`, creating media without timeline insertion.
- `resolve_disable_background_tasks`, session-wide, with the API's void-return semantics.

Signatures were checked against the official README installed with Resolve 21.0.4.5,
including the AI settings and documented scopes. No reference-project source was copied.

## 4. New resources

```text
resolve://system/status
resolve://project/current
resolve://project/list
resolve://project/settings
resolve://project/timelines
resolve://timeline/current
resolve://timeline/tracks
resolve://timeline/items
resolve://timeline/markers
resolve://mediapool/folders
resolve://mediapool/current-folder
resolve://mediapool/clips
resolve://render/jobs
resolve://render/formats
resolve://render/presets
resolve://render/is-rendering
```

All are read-only, with structured errors for unavailable state.

## 5. New editorial workflows

Name/metadata media search, position/name timeline search, video-only B-roll into a
gap, ordered rough-cut assembly into a new timeline, exact playhead markers,
chapter/speaker markers from supplied boundaries, local YouTube preset rendering,
and sampled visual shot search. Existing replacement now validates ranges and
creates a full recovery timeline before non-ripple deletion/insertion.

B-roll and rough cuts default to dry-run. Failed replacement selects a recovery
copy; it does not claim atomic restoration of the original timeline object.

## 6. Security improvements

Loopback default; explicit external binding; required token for external HTTP and
public URL configurations; constant-time bearer comparison on every HTTP method;
Host/Origin validation; no arbitrary Python/Lua tools; private environment secrets;
documented TLS and Cloudflare/Tailscale operator access controls.

This is shared-token access, not built-in OAuth or per-user authorization. A trusted
token grants full server functionality. The gateway must enforce finer policies.

## 7. Windows/macOS compatibility

Platform-specific scripting paths and environment overrides, cached health checks,
retry cooldown, forced reconnect, process/connection diagnostics, portable launchers,
`pip install -e .`, `resolve-mcp`, and `python -m resolve_mcp`.
The legacy source launcher is retained. Native-library compatibility is reported,
not assumed.

## 8. Testing

See [VALIDATION.md](VALIDATION.md) for the final executed results. Tests cover
connection lifecycle, all unavailable-state resource envelopes, track/media lookup,
half-open append source bounds, non-ripple replacement and recovery, linked audio,
transform validation, markers/timecode, native AI contracts, vision cleanup,
transport defaults, authentication, host/origin validation, request serialization,
all original tool names and actual stdio protocol initialization.

## 8a. Post-acceptance consistency changes

- JSON-returning legacy editing, marker and title tools now return
  `{"success": false, "error": {code, message}}` for rejected input instead of an
  MCP tool error. Tool names and parameters are unchanged; clients should read `success`.
  Plain-text legacy tools (for example `resolve_reconnect`) are unchanged.
- Replacement and B-roll plans, including dry-runs, include a `recovery_policy` field.
- B-roll failures use the same `{code, message}` error and `recovery` block as replacement.
- `original_timeline_may_be_modified` is false when nothing on the original was changed.
- `resolve_quick_export` always sends `EnableUpload: false` and reports a `success` field.
- A false native transcription result is marked `retryable` with a wait-and-retry hint.

## 9. Remaining limitations

- Core live acceptance passed on Windows (Resolve Studio 21.0.4.5, see PR #1) and
  macOS (Resolve Studio 21.1.0.17, see VALIDATION.md). Windows has not yet re-run
  replacement and recovery against e8a3d8d; several native AI and vision checks
  remain unexercised live.
- Source/timeline FPS mismatch is rejected for exact replacement and B-roll insertion.
- Recovery uses a full timeline copy. The modified original and external references
  remain; copies should be reviewed and cleaned up by the operator.
- Transcription tools return native status, not transcript text or speaker timestamps.
- Chapter markers require supplied boundaries; rough cuts require an ordered clip list.
- IntelliSearch analysis is available; querying its internal semantic index is not.
- Visual search samples visible timeline composites, not every source frame.
- General in-place trim/move, automatic transitions and effect-preserving retiming
  are not exposed as new speculative operations.
- The legacy speed tool may be rejected by Resolve and may affect underlying media.
- Native AI depends on Studio features, installed Extras, hardware and media support.
- Authentication is shared-token; multi-user auditing/OAuth require further work.

## 10. Suggested next features

After the live acceptance suite: verified mixed-FPS conforming; a persistent,
opt-in visual shot index; transcript import with explicit source/timecode mapping;
a reviewable edit-decision plan; per-user OAuth/audit logging; and curated recovery
timeline management.

## Resolve MCP Server 1.0 → 2.0

| Area | 1.0 | 2.0 |
|---|---|---|
| Identity | Remote AI editor | Remote AI editor with inspectable state and recovery |
| Existing tools | 53 | All 53 names retained |
| Native AI | No 21-specific layer | Transcription, classification, search analysis, Slate ID, deblur, speech |
| State inspection | Tool calls | 16 read-only MCP resources |
| Replacement | Delete then append | Preflight, half-open source bounds, backup, result verification |
| Vision | Caption/detect/Q&A | Preserved; isolated files and sampled shot search |
| HTTP | Unauthenticated external default | Loopback default, token guard, host/origin checks |
| Install | Mac-specific launcher | Python package, CLI, Windows/macOS launchers |
| Validation | Ad hoc live checks | Mocked suite, protocol checks, documented live acceptance |
