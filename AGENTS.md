# Resolve MCP Server — Agent Handoff

This file is the persistent project handoff for Codex and other coding agents.

## Current release

Work from `main` unless the user explicitly asks for a feature branch.

Current package version: **2.2.0**.

The 2.0, 2.1, and 2.2 work has been merged to `main`.

Do not revive old branch instructions such as `resolve-21` unless reviewing history.

## Product identity

Resolve MCP Server is an AI-native editing and automation layer for DaVinci Resolve 21.

The goal is not maximum raw API-tool count. Prefer reliable, editor-facing workflows that an AI can reason about safely:

- inspect project, timeline, clips, markers, render state, and media-pool state
- make precise editorial changes
- preserve linked audio where intended
- build reviewable variants rather than destructively rewriting source timelines
- use Resolve-native AI where appropriate
- use Moondream for frame understanding
- support local stdio and authenticated remote Streamable HTTP

The project currently exposes **77 tools**, **16 read-only resources**, and **5 MCP workflow prompts**.

## Current validated state

### Windows

Live acceptance has been run on:

- DaVinci Resolve Studio 21.0.4.5
- Python 3.12.14

Validated live behavior includes connection and resources, marker and transform round trips, exact replacement, linked-audio preservation, recovery timelines, B-roll insertion, rendering, captions/transcription-related workflows, silence detection/tightening, cut variants, and multi-track/multi-mic synchronization.

The 2.2 multi-track live suite passed 34/34 checks.

### macOS

Live acceptance has been run on:

- Apple silicon
- macOS 27.0
- DaVinci Resolve Studio 21.1.0.17
- Python 3.14.2
- MCP SDK 1.30.0
- Homebrew ffmpeg 8.0.1

The 2.2 multi-track acceptance completed successfully, including shared-silence detection, multi-track tightening, link restoration, marker mapping, text cuts, rendering, and project save.

The macOS unit suite reported 164 tests.

See `docs/VALIDATION.md` for the exact fixtures, raw findings, and version-specific Resolve behavior.

## Important empirical Resolve behavior

Prefer live-observed Resolve behavior over assumptions from comments or documentation when they conflict.

### AppendToTimeline end bounds

`MediaPool.AppendToTimeline()` uses a **half-open / exclusive** `endFrame` bound in tested Resolve 21 builds.

For a 192-frame append beginning at source frame 0, use:

- `startFrame = 0`
- `endFrame = 192`

Do not convert this back to an inclusive append bound.

Timeline-item source readbacks can use different semantics. Keep append bounds and native TimelineItem source values separately named.

### WAV frame count

Imported WAV clips may return an empty `Frames` property. The implementation falls back to duration timecode for frame count. Do not remove this fallback without live evidence.

### Track locks

Build tools intentionally **refuse locked, non-empty tracks** instead of unlocking them.

Resolve 21.0.4.5 demonstrated lock-state propagation between a source timeline and its duplicate. Resolve 21.1 behaves somewhat differently, but refusing locked tracks remains the conservative cross-version policy.

### Non-current timeline track state

On Resolve 21.1, `GetIsTrackEnabled` and `GetIsTrackLocked` can return misleading false values for a timeline that is not current. Code that depends on these values should read them with the intended timeline selected.

## Safety rules

Preserve these unless a change is justified by live evidence and tests:

- destructive editorial workflows should dry-run where practical
- source timelines should remain unchanged for tightening/text-cut variants
- replacement creates a full recovery timeline before destructive mutation
- failed edits must not claim success
- replacement/B-roll source bounds are half-open
- mixed-FPS frame-exact edits are rejected rather than guessed
- ambiguous media lookups fail instead of picking a random clip
- locked tracks are refused rather than silently modified
- arbitrary Python/Lua execution is not exposed remotely
- HTTP defaults to loopback and external access requires authentication
- do not upload renders automatically
- do not delete recovery timelines automatically

## Workflow architecture

Important areas include:

- `src/resolve_mcp/services/resolve_connection.py` — Resolve discovery/connection lifecycle
- `src/resolve_mcp/services/replacement.py` — conservative replacement and recovery
- `src/resolve_mcp/tools/analysis.py` — Resolve-native AI
- `src/resolve_mcp/tools/editing.py` — editing tools
- transcript/caption/silence/variant code supporting podcast/interview workflows
- `src/resolve_mcp/resources.py` — read-only MCP resources
- `src/resolve_mcp/security.py` — HTTP access protections

Keep Resolve discovery centralized. Do not let individual tools reinvent connection/project/timeline discovery.

## Development checks

Before committing code changes, run:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m build
```

For Resolve API behavior changes, unit tests are not enough. Use a disposable Resolve Studio project and record the live result in `docs/VALIDATION.md` when practical.

## Branch and PR discipline

- `main` is the current integrated 2.2 line.
- Create a focused feature/fix branch for substantive code changes.
- Do not merge a live-editing behavioral change solely because mocked tests pass.
- Keep changes small enough that a Resolve-specific regression can be isolated.
- Update validation/release notes when live behavior changes the implementation.

## Known limitations

Do not silently promise capabilities beyond what the repository supports.

Examples:

- the native IntelliSearch index is analyzed but not directly queryable through the Resolve API used here
- visual shot search samples frames rather than exhaustively indexing every source frame
- variant rebuilding does not preserve every possible clip-level effect/grade/Fusion/retiming state
- frame-exact workflows reject unsupported mixed-FPS cases rather than conforming automatically
- some Resolve-native AI capabilities depend on Studio, installed Extras, hardware, media, and Resolve-version behavior

## Current direction

Favor workflow quality over raw tool count.

Good next work should improve real editing outcomes, safety, observability, validation, or interoperability. Avoid adding speculative API wrappers merely to increase coverage.

When starting a new task, first read:

1. `README.md`
2. `docs/VALIDATION.md`
3. the relevant release notes under `docs/`
4. this `AGENTS.md`

Then inspect the current implementation before proposing changes.
