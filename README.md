# Resolve MCP Server

**Talk to your timeline.**

AI-native remote editing and automation for DaVinci Resolve 21. Keep the editorial
workflows—precise B-roll replacement, clip transforms, frame understanding and
remote operation—and add native Resolve AI, inspectable state, safer edits, captions,
transcripts, silence tightening, and multi-track podcast/interview workflows.

**Current release: 2.2.0.** The 2.0 editing workflows and 2.2 multi-track variant workflows
have been live-tested on both Windows and macOS. Some less common Resolve-native AI and
legacy operations remain unit-tested or partially exercised only. See
[validation and limitations](docs/VALIDATION.md).

Current inventory: **77 tools, 16 read-only MCP resources, and 5 workflow prompts.**

## What you can ask

- “What's in this timeline?” — read project, tracks, clips and markers.
- “Find the interview at 13:22.” — search at 802 elapsed seconds.
- “Replace the second clip on V2 with TAKEOFF_03, video only.”
- “What's in the current frame?” — Moondream caption or visual Q&A.
- “Find shots containing an airplane.” — sample visible timeline frames with Moondream.
- “Transcribe every interview in this bin.” — Resolve-native transcription.
- “Caption this episode and give me an SRT.” — Resolve's speech recognition, read back as text.
- “Cut the dead air out of this podcast.” — builds a tightened copy; the original is untouched.
- “Remove the ums and the tangent about parking.” — text-based cuts into a new timeline.
- “Keep all cameras and microphones in sync while tightening this interview.” — cuts every carried track together.
- “Add chapter markers based on these transcript timestamps.” — supply chapter boundaries.
- “Create a rough cut from these takes in this order.”
- “Render this timeline for YouTube.” — local Quick Export, uploading disabled.
- “Tell me what is currently rendering.” — read render jobs and progress.

The assistant still supplies editorial judgment. It cannot query Resolve's
IntelliSearch index. Word-level, speaker-labelled clip transcripts need Resolve 21.1+;
timeline captions work on supported Resolve 21 Studio builds.

## Requirements

- DaVinci Resolve **Studio 21** on the same workstation, running with
  **Preferences > System > General > External scripting using > Local**.
- A compatible **64-bit Python 3.10+** installation. Python and native Resolve
  scripting-library compatibility must be checked on your machine.
- An MCP client supporting stdio or Streamable HTTP.
- Optional Moondream API key, only for cloud vision tools.
- Optional **ffmpeg** on `PATH` (or `RESOLVE_MCP_FFMPEG`), only for silence detection and tightening.
- Required native AI packages installed through Resolve's Extras Download Manager.

Blackmagic's API documentation describes a Free/Studio superset, but some functions
fail without Studio or required Extras. This project's external automation target
is Studio; it does not promise full functionality on the free edition.

## Install on macOS

```bash
git clone https://github.com/guycochran/resolve-mcp-server.git
cd resolve-mcp-server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
resolve-mcp --doctor
resolve-mcp
```

## Install on Windows (PowerShell)

```powershell
git clone https://github.com/guycochran/resolve-mcp-server.git
cd resolve-mcp-server
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\resolve-mcp.exe --doctor
.\.venv\Scripts\resolve-mcp.exe
```

Activation is optional. If PowerShell blocks launcher scripts, run the executable directly.

Supported launchers: `resolve-mcp`, `resolve-mcp-server`,
`python -m resolve_mcp`, `python src/server.py`, `start.sh`, and `start.ps1`.
The existing FastMCP implementation is retained using the maintained MCP SDK 1.x
line (`mcp>=1.28,<2`); SDK 2.x is a separate migration.

### Automatic scripting discovery

| Platform | Default Modules directory |
|---|---|
| Windows | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules` |
| macOS | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules` |

Override with `PYTHONPATH_RESOLVE` (Modules directory) or `RESOLVE_SCRIPT_API`
(parent Scripting directory). Blackmagic's loader honors `RESOLVE_SCRIPT_LIB`
for a nonstandard native library location. Linux's standard path is retained as
a best effort, without claiming Linux testing.

Connection health checks are cached for five seconds; failed attempts have a
two-second cooldown. `resolve_reconnect` forces an immediate retry.
`--doctor` separates OS process presence from scripting connectivity and reports
the version/edition when the API is available.

## MCP client configuration

For a client using an `mcpServers` JSON configuration, use an absolute interpreter
path and module arguments. Windows example:

```json
{
  "mcpServers": {
    "resolve": {
      "command": "C:/path/to/resolve-mcp-server/.venv/Scripts/python.exe",
      "args": ["-m", "resolve_mcp"],
      "env": {"TRANSPORT": "stdio"}
    }
  }
}
```

On macOS use `/absolute/path/to/resolve-mcp-server/.venv/bin/python`.
No working-directory assumption is needed after installation.

Copy `.env.example` to `.env` in a source checkout for local configuration.
Environment variables take precedence. Installed-wheel deployments can set
`RESOLVE_MCP_ENV_FILE` to an explicit private file path. Do not commit credentials.

## Remote operation: authenticated Streamable HTTP

```text
Remote MCP client → HTTPS access gateway → localhost:3001/mcp → Resolve
Local MCP client  → stdio                                  → Resolve
```

Set `TRANSPORT=http`, `MCP_AUTH_TOKEN` and optionally `PORT`.
The server defaults to `HOST=127.0.0.1`. Generate a random token, for example with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`, and save it in your
private environment configuration. A token requires at least 32 characters.

Clients send `Authorization: Bearer <token>` on every HTTP request.
External binding requires a token; setting `MCP_PUBLIC_URL` also requires one.
Use `MCP_PUBLIC_URL=https://resolve.example.com` to allow your exact gateway host
and origin. Invalid host/origin requests remain blocked.

This is shared-token authentication for trusted operators, **not an OAuth login
server**. Clients requiring OAuth need a compatible authentication gateway.
A token grants access to all exposed tools and local media operations. Run one
server process per Resolve instance, with no concurrent GUI edits during mutations.
TLS and operator access policies belong at the gateway.

### Cloudflare Tunnel

Route a named tunnel hostname to `http://127.0.0.1:3001`. Set `MCP_PUBLIC_URL`
to that HTTPS hostname, keep the backend on loopback, and retain bearer authentication.
Apply Cloudflare Access policies appropriate for the operators/clients; an Access
login page alone is not compatible with every MCP client. Configure service
credentials or an OAuth-capable gateway where necessary.

See [Cloudflare's published application documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/).
A tunnel supplies connectivity; configure access controls as a separate step.

### Tailscale

Keep the same loopback backend and bearer token. Use Tailscale Serve to proxy
`http://127.0.0.1:3001` over your tailnet's HTTPS hostname; set `MCP_PUBLIC_URL`
to that origin and restrict operators with tailnet policy.
See [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

Do not forward the workstation's HTTP port directly onto the public internet.
No arbitrary Python or Lua execution tool is exposed.

## Two complementary kinds of AI

### Resolve-native AI

Transcription with optional speaker detection, transcription clearing, audio
classification/clearing, IntelliSearch analysis/reset, Slate ID markers, motion
deblur, speech generation, and session-wide background-task disabling.

Native AI runs through Resolve. IntelliSearch and Slate ID need their Extras
packages; speech generation needs AI Speech Generator. Face identification is
off by default. Folder transcription/classification includes nested folders.
Resetting IntelliSearch affects the whole project. Background-task disabling
lasts for the Resolve session and has no API enable counterpart.

### Moondream visual-language analysis

Set `MOONDREAM_API_KEY` to preserve frame descriptions, object detection and visual
Q&A. These requests send compressed frames to Moondream's cloud API.
Images use unique temporary paths and are deleted after each request; JPEG
compression happens in memory. Review [Moondream API documentation](https://docs.moondream.ai/api/).

Visual shot search samples one midpoint frame per timeline clip, up to the requested
limit, and restores page/playhead. It observes the visible composite, including
upper tracks; it can miss objects outside the sample. It is not an exhaustive
source-media search or a query into native IntelliSearch.

## Read-only MCP resources

Each resource returns JSON: `{success: true, data: ...}` or
`{success: false, error: {code, message}}`. Reads never select a project/bin/timeline.

| Area | Resource URIs |
|---|---|
| System | `resolve://system/status` |
| Project | `resolve://project/current`, `resolve://project/list`, `resolve://project/settings`, `resolve://project/timelines` |
| Timeline | `resolve://timeline/current`, `resolve://timeline/tracks`, `resolve://timeline/items`, `resolve://timeline/markers` |
| Media | `resolve://mediapool/folders`, `resolve://mediapool/current-folder`, `resolve://mediapool/clips` |
| Render | `resolve://render/jobs`, `resolve://render/formats`, `resolve://render/presets`, `resolve://render/is-rendering` |

Project listing is scoped to the current database folder; media clip listing is
scoped to the current bin. Folder paths and workflow searches can traverse all bins.

## Editorial workflows and recovery

All 53 original tool names remain. Newer workflows include media/timeline lookup,
`resolve_insert_broll`, `resolve_build_rough_cut`, marker/chapter helpers,
`resolve_render_for_youtube`, visual shot search, captions/transcripts, silence analysis,
reviewable cut variants, and render waiting.

### Clip replacement

`resolve_replace_clip` still reads record position, deletes without ripple,
and inserts at that same record frame. Video-only is the default.

- Use 1-based track/clip indices. `dry_run=true` returns the plan without mutations.
- Media names must be unique; `new_media_id` disambiguates them.
- Append source ranges are **half-open**: `[in, out_exclusive)`; automatic matching uses `in + duration`.
  The existing `source_end_frame` argument is exclusive (zero means automatic).
  Plans return `source_out_exclusive`; original `source_in_native` / `source_out_native`
  preserve raw TimelineItem readbacks and must not be reused as append bounds.
- Source bounds, timeline position and track locks are checked before deletion.
- Mixed source/timeline FPS is rejected rather than guessed.
- A full recovery timeline is created before changing clips.
- Linked peers are unlinked before deleting only the target, then linked to the
  replacement. Interview audio is not included in the delete call.
- An insertion, duration or relinking failure selects the recovery timeline.
  The modified original remains for inspection; references to that timeline are
  not automatically redirected. A recovery copy is not an atomic undo.
- The new clip uses its own media defaults. Original effects, grades, Fusion
  and retiming remain in the recovery copy.

`media_type=2` explicitly targets an audio-track item. Combined video/audio
replacement is rejected because a single index cannot safely identify both targets.
This is a safety-related change from the permissive legacy parameter.

B-roll insertion requires an empty destination interval. B-roll and rough-cut tools
default to dry-run. Chapter markers take supplied timestamps; they do not infer
speaker changes. Direct trim/move operations are deferred because the API does not
provide a general, reliable in-place edit with full effect preservation.

## Transcripts, captions and multi-track tightening

These workflows are designed to preserve the source timeline by reading it or building a new variant.

| Tool | What it does |
|---|---|
| `resolve_create_captions` | Runs Resolve's auto-captioning on the current timeline and verifies success by reading cues back. |
| `resolve_get_transcript` | Returns caption cues, or on Resolve 21.1+ a clip's native transcript with speakers/word times. Can write SRT, VTT or text to a new path. |
| `resolve_detect_silence` | Read-only ffmpeg `silencedetect`, calibrated from recording noise floor unless overridden. Can consider all carried audio tracks. |
| `resolve_tighten_silence` | Removes shared dead air into a **new timeline**, keeping a small pause around speech. Dry-run by default. |
| `resolve_build_cut_variant` | Removes specified time ranges across carried tracks into a **new timeline**. Dry-run by default. |
| `resolve_wait_for_render` | Waits for a render job or queue, then reports status and output file. |

In 2.2, variant editing is multi-track aware. The source timeline is duplicated, the copy is
emptied and rebuilt from kept media ranges on their original track numbers. Cameras and separate
microphone tracks are cut together, links are restored, timeline markers in kept time move with
the edit, and each track is read back and verified against the plan.

Silence is cut only where the selected audio set is quiet. With the default carried-track mode,
a guest answering while the host is silent is not mistaken for dead air. Track names, audio formats,
enable states and timeline settings are carried where supported.

Locked, non-empty tracks are intentionally refused rather than automatically unlocked because
Resolve lock behavior differs across tested 21.x builds and can affect duplicate/source timelines.
Titles, generators, compound/multicam clips, retimed clips and media at a different frame rate
cannot always be rebuilt exactly; unsupported cases are rejected or reported instead of guessed.

Free-edition calls to Resolve's AI features can open a modal upgrade dialog that disrupts later API calls,
so these tools refuse to run unless the product is Resolve Studio.

## Live validation highlights

### Windows

Resolve Studio 21.0.4.5 / Python 3.12.14. The 2.2 multi-track suite passed 34/34 checks,
including locked-track refusal, shared-silence detection across A1/A2/A3, synchronized V1/A1/A2/A3
tightening, link restoration, marker movement, text cuts, source-timeline preservation, and render/wait.

### macOS

Apple silicon / macOS 27.0 / Resolve Studio 21.1.0.17 / Python 3.14.2. The 2.2 live run passed,
including shared-silence detection, multi-track tightening, link restoration, marker mapping,
text cuts, render/wait and project save. The macOS unit suite reported 164 tests.

See `docs/VALIDATION.md` for fixtures, raw values and Resolve-version-specific findings.

## Workflow prompts

MCP clients that support prompts get ready-made recipes with the safety rules built in:
`podcast_episode_edit`, `tighten_recording`, `captions_and_transcript`,
`safe_shot_replacement` and `youtube_delivery`.

## Development

Codex and other coding agents should read [AGENTS.md](AGENTS.md) before making changes.

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m build
```

See [architecture](ARCHITECTURE.md), [manual integration tests](docs/INTEGRATION_TESTS.md),
[validation](docs/VALIDATION.md), the [2.0 implementation report](docs/RELEASE_2.0.md),
the [2.1 release notes](docs/RELEASE_2.1.md) and [2.2 release notes](docs/RELEASE_2.2.md).

## License

[MIT](LICENSE). Resolve-native additions were implemented independently from
Blackmagic's installed scripting documentation. No source was copied from the
Digital Workflow Company reference implementation. The 2.1 transcript and tightening
workflows were written independently; the idea of caption readback and calibrated silence
detection was informed by reviewing samuelgursky/davinci-resolve-mcp (MIT).
