# Executed validation — 2026-09-15

## Environment

Windows workstation with DaVinci Resolve executable version **21.0.4.5** installed.
Development interpreter: bundled CPython **3.12.14**, 64-bit.
Resolved/tested MCP SDK: **1.30.0**, preserving FastMCP.
No existing Resolve project was edited and no paid/cloud AI operation was invoked.

## Results

| Check | Result |
|---|---|
| Unit/protocol tests | 93 passing |
| Ruff static checks | Pass |
| All original tool names | All 53 retained |
| Server inventory | 71 tools, 16 resources |
| Editable package installation | Pass |
| Source distribution and wheel build | Pass |
| Wheel installation to a separate directory | Pass |
| Installed-wheel imports, inventory and CLI | Pass |
| Dependency consistency (`pip check`) | Pass |
| Real stdio process initialization, tools/resources listing and resource read | Pass |
| Authenticated HTTP initialization | Pass, ASGI protocol test |
| Missing/incorrect HTTP token and untrusted Host/Origin | Rejected as expected |
| Live Resolve native-library connection | Pass after 225abbc (Windows runtime discovery) |
| macOS native acceptance | Pass, 2026-09-15 at e8a3d8d (see below) |
| Cloudflare/Tailscale deployment | Documented; not deployed |

The tests emit two upstream Starlette/AnyIO deprecation warnings; they do not fail
the suite. These are test-client dependencies, not evidence of a native Resolve
integration pass.

## Commands

Normal development commands:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m build
resolve-mcp --version
resolve-mcp --doctor
```

This restricted Windows environment needed an external, workspace-only temporary
directory workaround: Python's mode-0700 temporary directories were not accessible
to the sandbox process. The workaround inherits existing workspace permissions,
is not shipped in the package, and does not modify system Python. Editable
installation/build used `--no-build-isolation` / `--no-isolation` with the required
build dependencies preinstalled. Builds were written into the workspace temporary
root to avoid the same permission issue.

The SDK client's Windows asyncio subprocess helper could not open its named pipes
in this sandbox. The stdio protocol test uses a real subprocess and anonymous pipes,
with initialize, initialized notification, tools/list, resources/list and
resources/read exchanges and bounded read timeouts.

## Live blocker

`--doctor` reports:

```text
SystemError: initialization of fusionscript failed without raising an exception
```

The native module fails before a usable scripting connection is established.
This is not proof that the server works with the installed Resolve, nor proof that
Resolve itself is incompatible. OS process enumeration may also report unknown
when the diagnostic process query is restricted.

Next live step: use a compatible standard 64-bit Python installation with Resolve
Studio external scripting set to Local, then run [INTEGRATION_TESTS.md](INTEGRATION_TESTS.md).
Do not certify production readiness until the Windows and macOS acceptance results
are recorded.
# macOS live acceptance: 2026-09-15

## Environment

macOS 27.0 (26A5406e), Apple silicon. DaVinci Resolve Studio **21.1.0.17**, external
scripting Local. Homebrew CPython **3.14.2** venv, MCP SDK **1.30.0**. Branch
`resolve-21` at **e8a3d8d**. Disposable project `MCP macOS Acceptance 20260915-184429`
with generated 24 fps fixtures (120-frame A/V base, 168-frame replacement,
72-frame B-roll, `say`-generated speech WAV). No professional project was opened.

## Results

| Check | Result |
|---|---|
| `pytest` (115 tests) and `ruff check src tests` on macOS | Pass |
| `--doctor` | Connected, Studio edition, Python 3.14.2 |
| Real stdio client: initialize, 71 tools, 16 resources | Pass |
| `resolve_get_status` and all 16 resource reads | Pass |
| Marker add/read/delete at timeline offset 12 | Pass |
| Transform set/readback; out-of-range ZoomX rejected with no write | Pass |
| Replacement dry-run: no edit, no recovery copy | Pass |
| Video-only replacement: record 86400–86520 kept, 120 frames, A1 unchanged, relinked | Pass |
| Recovery timeline retains original linked A/V pair | Pass |
| Short-source and missing-media replacement rejected; clip intact | Pass |
| B-roll into a V2 gap (exactly 24 frames); overlapping B-roll rejected | Pass |
| `resolve_reconnect` then status | Pass |
| Local Quick Export (H.264 Master) | Pass, 1.8 MB .mov |
| Native transcription (clip), then clear | Pass on first attempt |

## e8a3d8d repair paths, live failure injection

Run in-process against live Resolve. A proxy made one native call refuse or
mis-size its result; every other call was the real Resolve API.

| Scenario | Observed |
|---|---|
| Replace, `DeleteClips` refused after unlink | `links_restored: true`; original V1/A1 relinked; recovery selected |
| Replace, insert 12 frames short after deletion | `bad_insert_removed: true`, `links_restored: false`; original V1 empty, A1 intact; recovery selected |
| `resolve_delete_clip`, deletion refused | `links_restored: true`; pair relinked; recovery selected |
| B-roll, insert 6 frames short | `bad_insert_removed: true`; V2 empty; recovery selected |

## Not run on macOS

Close/reopen project and Resolve restart, authenticated HTTPS and Host/Origin
checks (covered by automated tests only), locked-track and mixed-FPS rejections,
rough cut, chapter/drop-frame markers, Text+/Fusion/LUT, speaker detection and
folder transcription, audio classification, IntelliSearch, Slate ID, deblur,
speech generation, Moondream vision, and YouTube render workflow.

## Post-acceptance changes

The consistency changes listed in RELEASE_2.0.md section 8a were made after the
first macOS live run. They are covered by 10 new unit tests (125 total, passing).
The full macOS live suite above was re-run on the same machine with them applied:
17 of 17 checks pass (project `MCP macOS Acceptance 20260915-190338`), including the
four repair scenarios, now also checking `original_timeline_may_be_modified`.
Rejected replacements now return `invalid_request` results rather than tool errors.
Windows re-run at b86ca8f: 26 of 26 replacement/recovery checks pass (see PR #1).

## 2.1 live acceptance (Windows)

Windows, DaVinci Resolve Studio 21.0.4.5, Python 3.12.14, MCP SDK 1.30.0, ffmpeg from
Shutter Encoder. Commit f8730eb, driven through a real stdio client. Disposable project
`MCP ACCEPTANCE 2026-09-15`; source timeline `MCP 2.1 Podcast 222800` built from a generated
35 s, 24 fps clip (start timecode 01:00:00:00, speech with silent gaps at 10–13 s and
23–25 s). Unit tests on Windows: 156 passed, 1 skipped (the real-ffmpeg unit test; ffmpeg is
not on PATH there). **30 of 30 live checks pass.**

| Check | Result |
|---|---|
| Inventory | 77 tools, 5 prompts |
| Captions dry-run | No subtitle track created |
| `resolve_create_captions` (English) | Native true; subtitle track 1 with 11 cues read back; clips unchanged |
| `resolve_get_transcript` | 11 entries, 66 words, cue times within the timeline; SRT written to a new file |
| `resolve_detect_silence` (calibrated) | Threshold -49.5 dB (floor -74.7, speech -11.6); silences 10.000–13.083 s and 23.000–25.083 s |
| `resolve_tighten_silence` dry-run | No timeline created, source unchanged; 100 of 840 frames to remove |
| `resolve_tighten_silence` | 3 pieces on V1 and A1: 86400–86646, 86646–86896, 86896–87140 (740 frames, gapless, identical on both tracks); video linked to audio; start TC 01:00:00:00 matched; second piece source in = 308 (gap end 314 minus 6-frame pause); source timeline unchanged |
| `resolve_build_cut_variant` (first caption cue) | 126 frames removed (the cue length); 2 gapless pieces; source unchanged |
| Render of the tightened variant + `resolve_wait_for_render` | Complete in 4 s; output file present; ffprobe 30.848 s vs 30.83 s planned |
| Project save | Pass |

This re-confirms AppendToTimeline's exclusive `endFrame` on 21.0.4.5, contrary to the
comment in Blackmagic's `Examples/7_add_subclips_to_timeline.py` ("endFrame 23" described
as the first 24 frames).

After the run, `not_carried_over` was changed to summarize caption cues per subtitle track
instead of listing each cue (unit-tested; no live behaviour change otherwise).

Not live-tested for 2.1: 21.1 `GetTranscription` clip transcripts (unit-tested only),
multi-clip spines, audio-only spines, free-edition refusal, render timeout/stop.
