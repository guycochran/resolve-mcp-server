# Resolve MCP Server 2.1: podcast and interview editing

2.1 adds transcript, captioning and tightening workflows for long-form talking content.
Like the 2.0 editing tools, none of them edit the timeline you are working on.

## Why these features

A review of the other public Resolve MCP servers (samuelgursky/davinci-resolve-mcp,
DigitalWorkflowCompany/resolve-mcp, hiteshK03, lordhoell, apvlv) showed they compete on raw
API coverage (up to ~450 tools). This server's strength is fewer, verified, recoverable
workflows, so 2.1 adds the editorial jobs a podcast or interview editor repeats every
episode rather than more thin API wrappers.

## New tools (71 → 77)

- `resolve_create_captions`: Resolve's auto-captioning with enum-keyed settings (plain keys
  are silently ignored by Resolve). Success is verified by reading new subtitle cues back.
- `resolve_get_transcript`: caption cues with timeline seconds and frames; on 21.1+, the clip's
  full native transcript (speakers, word times) via `MediaPoolItem.GetTranscription`.
  JSON, SRT, VTT or plain text; files are only written to new, absolute paths.
- `resolve_detect_silence`: read-only ffmpeg `silencedetect` on each dialogue clip's source
  range, with a threshold calibrated from 100 ms RMS windows (noise floor + 40% of the
  floor-to-speech spread, at least 10 dB, clamped to -60..-20 dB).
- `resolve_tighten_silence`: silence removal into a new timeline, keeping a configurable
  pause on each side of every cut. Dry-run by default.
- `resolve_build_cut_variant`: remove arbitrary timeline-second ranges (for example filler
  or off-topic caption cues) into a new timeline. Dry-run by default.
- `resolve_wait_for_render`: async wait for one job or the whole queue with timeout,
  optional stop, final status and output-file check.

## New MCP prompts

`podcast_episode_edit`, `tighten_recording`, `captions_and_transcript`,
`safe_shot_replacement`, `youtube_delivery`. Each embeds the house safety rules:
duplicate first, dry-run and approve, read back and compare, keep recovery timelines.

## Safety changes

- Native AI tools (transcription, classification, IntelliSearch, Slate ID, deblur, speech
  generation, captions) now refuse to run unless the product is Resolve Studio. On the free
  edition these calls open a modal upgrade dialog that makes unrelated API calls fail until
  a person dismisses it.

## Variant engine design

- One spine track (A1 by default) decides what is kept. Each spine item must be a media clip
  at the timeline frame rate with no speed change (native source span equals its duration).
- Kept pieces are appended with explicit `recordFrame`, `trackIndex` 1 and half-open
  `[startFrame, endFrame)` source ranges (end-exclusive semantics were live-verified in 2.0).
  Pieces carry video and audio only if the original used both for that media.
- Source frames reported relative to a media start timecode are normalized to 0-based frames.
- Appends are batched (50 per call); afterwards every video and audio piece on track 1 is
  compared with the plan. On mismatch the variant is kept for inspection and the source
  timeline is reselected. The source timeline is never edited.
- The variant copies the source's start timecode.
- Items on other tracks that don't belong to spine media are listed in `not_carried_over`.

## Known limitations

- Multi-mic podcasts recorded as separate files on separate tracks: only the spine media is
  carried into a variant. Sync or compound them first, or use a single mixed recording.
- Silence detection needs ffmpeg and read access to the source files from the machine
  running the server.
- Caption quality and language support come from Resolve. There is no API to import an
  external SRT into a subtitle track.
- `resolve_wait_for_render` holds the server's operation lock while waiting.

## Validation

- Automated: see `tests/test_transcript.py`, `tests/test_cuts.py` (includes a real ffmpeg
  run on generated audio), `tests/test_jobs_prompts.py`.
- Live: see [VALIDATION.md](VALIDATION.md), section "2.1 live acceptance".
