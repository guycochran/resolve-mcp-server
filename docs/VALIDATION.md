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
| Live Resolve native-library connection | Blocked: fusionscript initialization |
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
macOS live run. They are covered by 10 new unit tests (125 total, passing) but have
not yet been re-run against live Resolve.
