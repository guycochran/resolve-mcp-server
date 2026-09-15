# DaVinci Resolve MCP Server

**Resolve 21 / Windows development update:** see [WINDOWS.md](WINDOWS.md) for setup,
new analysis tools and resources, and current validation limitations.

**Talk to your timeline.** Control DaVinci Resolve with natural language through Claude — browse projects, swap clips, color grade, render for YouTube, and see what's in any frame with AI vision. From your desk or from your phone, anywhere in the world.

```
You:    "Replace the b-roll at 13:22 with the South Pole takeoff shot"
Claude: Done. Replaced AOA_CLIP_04 with A663C012_SOUTH_POLE_TAKE_OFF on V2.
        Same position, same duration, video only — your interview audio is untouched.
```

---

## What This Is

An [MCP server](https://modelcontextprotocol.io) that connects Claude to a running DaVinci Resolve instance. **53 tools** across 11 categories give Claude full read/write access to your projects, timelines, media pool, color page, and render queue — plus AI-powered frame analysis via [Moondream](https://moondream.ai).

This isn't a toy. It edits. It replaced a clip on a multi-track documentary timeline, matched the duration, preserved the audio, and exported the result for YouTube. All through conversation.

## What You Can Do

### Edit by talking
```
"Open the tutorial project"
"Switch to the Full Documentary timeline"
"What clips are on V2?"
"Replace clip 2 on V2 with the milky way shot"
"Zoom in to 120% on the interview clip"
"Add a blue marker here that says 'Great take'"
"Export this for YouTube"
```

### See through your timeline with AI vision
```
"What's in this frame?"
→ A wide shot of a beach in St. Maarten with an airplane on final approach,
  turquoise water, and spectators watching from behind a chain-link fence.

"Is there a person at the podium?"
→ Yes, there is a person standing at the podium on the left side of the frame.

"How many people are visible?"
→ 4
```

### Control Resolve from your phone
The server runs over HTTP with a Cloudflare tunnel, so you can edit from your couch, your car, or another continent. Same tools, same capabilities — just talking to Claude on your phone.

---

## The 53 Tools

| Category | Count | What they do |
|----------|-------|-------------|
| **Connection** | 4 | Status, page navigation, reconnect |
| **Project** | 6 | List, load, save, create projects, read/write settings |
| **Timeline** | 8 | List/switch timelines, playhead control, track inspection, create new |
| **Media** | 5 | Browse media pool, import clips, create bins, append to timeline |
| **Editing** | 7 | Transform, speed, enable/disable, compound clips, **delete clips, replace clips** |
| **Color** | 6 | Apply LUTs, create/load color versions, export grades |
| **Markers** | 3 | Add, list, delete timeline markers |
| **Titles** | 2 | Insert Fusion Text+ titles, modify text content |
| **Render** | 6 | Quick export (YouTube/Vimeo/TikTok), custom render jobs, export EDL/FCPXML |
| **Fusion** | 3 | Access Fusion compositions and tools |
| **Vision** | 3 | AI scene description, object detection, visual Q&A |

---

## Quick Start

### Prerequisites
- **DaVinci Resolve Studio** (paid — the scripting API is not available in the free version of Resolve)
- **Python 3.10+** (tested with 3.14)
- A [Moondream API key](https://console.moondream.ai) (free tier available — for AI vision features). Sign up at [console.moondream.ai](https://console.moondream.ai) to get your key. Moondream charges per API call, but the free tier is generous for normal editing use.

### 1. Clone and install

```bash
git clone https://github.com/guycochran/resolve-mcp-server.git
cd resolve-mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
# Edit .env and add your Moondream API key
```

### 3. Add to Claude Desktop

Add to your Claude Desktop MCP config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "resolve": {
      "command": "/path/to/resolve-mcp-server/start.sh"
    }
  }
}
```

### 4. Open Resolve and start talking

> "What project am I working on?"

That's it. Claude can now see and control everything in Resolve.

---

## Remote Access (HTTP Mode)

Control Resolve from anywhere — your phone, a tablet, another computer.

```bash
# Start the server in HTTP mode
TRANSPORT=http PORT=3001 .venv/bin/python3 src/server.py
```

### With Cloudflare Tunnel (worldwide access)

```bash
# Add to your cloudflared config:
#   hostname: resolve.yourdomain.com
#     service: http://localhost:3001

cloudflared tunnel run
```

Now point any MCP client at `https://resolve.yourdomain.com/mcp` and you're editing remotely.

---

## How Clip Replacement Works

The Resolve scripting API has no overwrite edit or three-point edit. We built one.

`resolve_replace_clip` performs a two-step operation:

1. **Read** the old clip's exact timeline position and duration
2. **Delete** the old clip (no ripple — preserves the gap)
3. **Insert** the new clip at the identical record position with matching duration

```python
# What happens under the hood:
timeline.DeleteClips([old_clip], False)
pool.AppendToTimeline([{
    "mediaPoolItem": new_item,
    "trackIndex": 2,
    "recordFrame": 86734,       # exact same position
    "startFrame": 0,
    "endFrame": 120,            # matches original duration
    "mediaType": 1              # video only — preserves audio
}])
```

This means Claude can swap b-roll, try alternate takes, and revert — all through conversation.

---

## How AI Vision Works

The server uses [Moondream](https://moondream.ai) Vision Language Models (VLMs) for AI-powered frame analysis. It grabs the current frame from Resolve, compresses it via Pillow (6MB PNG down to ~250KB JPEG), and sends it to the Moondream cloud API.

Sign up at [console.moondream.ai](https://console.moondream.ai) (free tier available) to get your API key.

Three tools:
- **`resolve_describe_frame`** — "What's in this shot?"
- **`resolve_detect_in_frame`** — Find objects with bounding boxes
- **`resolve_ask_about_frame`** — Visual Q&A about the frame

Use cases: automated scene logging, accessibility descriptions, content verification, shot matching.

---

## Architecture

```
Phone/Tablet ──── HTTPS ────→ Cloudflare Tunnel ────→ localhost:3001
                                                           │
Claude Desktop ── stdio ──────────────────────────────────→│
                                                           │
                                                   Resolve MCP Server
                                                   (Python + FastMCP)
                                                           │
                                              ┌────────────┼────────────┐
                                              ▼            ▼            ▼
                                        DaVinci       Moondream      Cloudflare
                                        Resolve       Vision API      Tunnel
                                        (local)       (cloud)        (cloud)
```

## Project Structure

```
src/
├── server.py                    # FastMCP entry point (stdio + HTTP)
├── services/
│   ├── resolve_connection.py    # Resolve API connection management
│   └── moondream.py             # Moondream vision API client + image prep
└── tools/
    ├── connection.py            # Status, page navigation
    ├── project.py               # Project management
    ├── timeline.py              # Timeline operations
    ├── media.py                 # Media pool management
    ├── editing.py               # Transform, delete, replace clips
    ├── color.py                 # LUTs, color versions, grade export
    ├── markers.py               # Timeline markers
    ├── titles.py                # Fusion titles
    ├── render.py                # Rendering & export
    ├── fusion.py                # Fusion compositions
    └── vision.py                # AI frame analysis
```

## Requirements

- **DaVinci Resolve Studio** — The scripting API requires the paid Studio version
- `mcp[cli]` — Model Context Protocol SDK
- `httpx` — HTTP client for Moondream API
- `Pillow` — Image compression (PNG → JPEG for vision pipeline)

## License

MIT
