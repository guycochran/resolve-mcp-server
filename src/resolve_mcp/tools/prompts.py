"""Workflow recipes exposed as MCP prompts, so any client gets the safe order of operations."""

RULES = """House rules for every Resolve edit:
- Work in a disposable or duplicated timeline unless the editor says otherwise; never edit source media.
- Read state first (resolve://timeline/current, resolve://timeline/items) and restate what you will change.
- Run the dry-run form of any editing tool, show the plan, and wait for approval before dry_run=false.
- After every change, read the timeline back and compare with the plan. If anything differs, stop and report.
- Keep recovery and variant timelines; never delete timelines, clips or media unless asked explicitly.
- Save the project (resolve_save_project) after a verified change."""


def register(mcp):
    @mcp.prompt()
    def podcast_episode_edit(episode_timeline: str = "", goal: str = "a tight first cut") -> str:
        """End-to-end first cut of a podcast or interview episode: captions, tightening, text edits, chapters."""
        return f"""Edit the episode timeline {episode_timeline or '(the current timeline)'} toward: {goal}.

{RULES}

Steps:
1. resolve_set_current_timeline if a name was given; read resolve://timeline/tracks and items. Identify the
   dialogue spine track (usually A1) and any clips that won't be carried into a variant.
2. resolve_create_captions (language auto unless known), then resolve_get_transcript(source="captions").
3. resolve_tighten_silence with dry_run=true. Report the removed seconds and not_carried_over list.
   After approval run it with dry_run=false; it creates a NEW timeline and leaves the original alone.
4. On the tightened timeline, create captions again, read the transcript, and propose text cuts
   (filler, false starts, off-topic). Show each cue's text and times. After approval call
   resolve_build_cut_variant(remove=[...], dry_run=false).
5. Propose chapter titles from the transcript and add them with resolve_create_chapter_markers
   (timeline-relative frames = seconds x fps).
6. Report: timelines created, runtime before/after, and anything that needs a human decision."""

    @mcp.prompt()
    def tighten_recording(max_pause_seconds: float = 0.7) -> str:
        """Remove dead air from one long talking-head, screencast or podcast recording."""
        return f"""Tighten the current timeline.

{RULES}

1. resolve_detect_silence(min_silence_seconds={max_pause_seconds}) and summarize total dead air.
2. resolve_tighten_silence(min_silence_seconds={max_pause_seconds}, dry_run=true). If calibration says
   "default", or more than 40% would be removed, ask before continuing and consider a fixed threshold_db.
3. After approval, run with dry_run=false and report the variant timeline name and new runtime.
4. Spot-check: read resolve://timeline/items on the variant and confirm the piece count matches."""

    @mcp.prompt()
    def captions_and_transcript(output_path: str = "") -> str:
        """Create captions with Resolve's speech recognition and deliver SRT/VTT or plain text."""
        target = output_path or "a new .srt file the editor names"
        return f"""Produce a transcript for the current timeline.

1. Check resolve://system/status shows Studio 21+. If captions already exist, ask whether to reuse them.
2. resolve_create_captions; confirm success and the preview lines look like real speech.
3. resolve_get_transcript(source="captions", format="srt", output_path=...) to write {target}.
   Use format="text" for show notes or a blog draft.
4. Report cue count, words per minute, and the file path. Do not change clips."""

    @mcp.prompt()
    def safe_shot_replacement(shot_description: str = "") -> str:
        """Replace one shot with other media without disturbing linked interview audio."""
        return f"""Replace this shot: {shot_description or '(ask the editor which shot)'}.

{RULES}

1. Locate the clip with resolve_find_timeline_clip (by seconds or timecode) and the new media with
   resolve_find_media_clip. If either is ambiguous, ask.
2. resolve_replace_clip(..., dry_run=true). Check record_start, duration_frames, source range, and
   linked_items_preserved; confirm the replacement media is long enough.
3. After approval run it for real. Verify the new clip's start/end match and linked audio is unchanged.
4. Mention the recovery timeline name so the editor can roll back."""

    @mcp.prompt()
    def youtube_delivery(output_dir: str = "") -> str:
        """Render a finished episode locally for YouTube, with captions and chapters ready to paste."""
        return f"""Deliver the current timeline for YouTube into {output_dir or '(ask for an output folder)'}.

1. Read resolve://render/presets and confirm a YouTube Quick Export preset exists.
2. resolve_render_for_youtube (uploading stays disabled), or resolve_add_render_job + resolve_start_render,
   then resolve_wait_for_render until complete. Report the output file and size.
3. If captions exist, write an SRT next to the video with resolve_get_transcript.
4. List chapter markers (resolve_get_markers) as YouTube chapter lines "MM:SS Title", starting at 00:00.
   Never upload anything."""
