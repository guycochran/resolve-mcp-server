# Resolve MCP Server

**Talk to your timeline.**

AI-native remote editing and automation for DaVinci Resolve 21. Keep the editorial
workflows—precise B-roll replacement, clip transforms, frame understanding and
remote operation—and add native Resolve AI, inspectable state, and safer edits.

**2.0 development release:** automated tests and protocol checks are available.
Live acceptance testing on Resolve Studio is still required before production use.
See [validation and limitations](docs/VALIDATION.md).

## What you can ask

- “What's in this timeline?” — read project, tracks, clips and markers.
- “Find the interview at 13:22.” — search at 802 elapsed seconds.
- “Replace the second clip on V2 with TAKEOFF_03, video only.”
- “What's in the current frame?” — Moondream caption or visual Q&A.
- “Find shots containing an airplane.” — sample visible timeline frames with Moondream.
- “Transcribe every interview in this bin.” — Resolve-native transcription.
- “Add chapter markers based on these transcript timestamps.” — supply chapter boundaries.
- “Create a rough cut from these takes in this order.”
- “Render this timeline for YouTube.” — local Quick Export, uploading disabled.
- “Tell me what is currently rendering.” — read render jobs and progress.

The assistant still supplies editorial judgment. The server does not automatically
extract a speaker-timestamp transcript or query Resolve's IntelliSearch index.

## Requirements

- DaVinci Resolve **Studio 21** on the same workstation, running with
  **Preferences > System > General > External scripting using > Local**.
- A compatible **64-bit Python 3.10+** installation. Python and native Resolve
  scripting-library compatibility must be checked on your machine.
- An MCP client supporting stdio or Streamable HTTP.
- Optional Moondream API key, only for cloud vision tools.
- Required native AI packages installed through Resolve's Extras Download Manager.

Blackmagic's API documentation describes a Free/Studio superset, but some functions
fail without Studio or required Extras. This project's external automation target
is Studio; it does not promise full functionality on the free edition.

## Install on macOS

```bash
git clone https://github.com/guycochran/resolve-mcp-server.git
cd resolve-mcp-server
git switch resolve-21
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
resolve-mcp --doctor
resolve-mcp
```

The branch must be published before a fresh clone can switch to it. For a downloaded
2.0 checkout, skip that line. The current development branch is local until published.

## Install on Windows (PowerShell)

```powershell
git clone https://github.com/guycochran/resolve-mcp-server.git
cd resolve-mcp-server
git switch resolve-21
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\resolve-mcp.exe --doctor
.\.venv\Scripts\resolve-mcp.exe
```

Activation is optional. For an existing local 2.0 checkout, start at the venv step.
If PowerShell blocks launcher scripts, run the executable directly.

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

All 53 original tool names remain. New workflows include
`resolve_find_media_clip` (name/metadata),
`resolve_find_timeline_clip` (name/position),
`resolve_insert_broll`, `resolve_build_rough_cut`,
`resolve_add_marker_at_playhead`, `resolve_create_chapter_markers`,
`resolve_render_for_youtube`, and `resolve_find_shots_by_visual_description`.

### Clip replacement

`resolve_replace_clip` still reads record position, deletes without ripple,
and inserts at that same record frame. Video-only is the default.

- Use 1-based track/clip indices. `dry_run=true` returns the plan without mutations.
- Media names must be unique; `new_media_id` disambiguates them.
- Source out is **inclusive**; automatic matching uses `in + duration - 1`.
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

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m build
```

See [architecture](ARCHITECTURE.md), [manual integration tests](docs/INTEGRATION_TESTS.md),
[validation](docs/VALIDATION.md), and the [2.0 implementation report](docs/RELEASE_2.0.md).

## License

[MIT](LICENSE). Resolve-native additions were implemented independently from
Blackmagic's installed scripting documentation. No source was copied from the
Digital Workflow Company reference implementation.