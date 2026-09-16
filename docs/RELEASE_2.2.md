# Resolve MCP Server 2.2: multi-track variants

2.2 makes silence tightening and text cuts safe for real multi-camera, multi-mic podcast
timelines. Tool names are unchanged (77 tools, 5 prompts); behaviour and new options below.

## What changed

- **Every track is carried** (`tracks="all"`, the new default). Removals are applied to all
  video and audio tracks at once, so separate host/guest mic files and extra cameras stay in
  sync. `tracks="spine"` restores 2.1's single-track behaviour.
- **Shared-silence detection** (`detect_on="carried"`, the new default). A pause is only cut
  where every *enabled* audio track is quiet; time with no clip on a track counts as quiet.
  2.1 analyzed only the spine track, which would have cut a guest's answer while the host's
  mic was silent. `detect_on="spine"` keeps the old behaviour.
- **Variants start from a duplicate.** The source is duplicated, the copy is emptied, and the
  kept pieces are appended back onto their original track numbers with explicit `mediaType`.
  The copy therefore keeps track names, audio channel formats (mono/stereo/…), enable states
  and timeline settings. 2.1 built a fresh empty timeline with one video and one audio track.
- **Locked tracks are refused.** If a track with clips is locked, the build tools stop before
  creating anything and name the tracks to unlock. Live finding on Resolve Studio 21.0.4.5:
  unlocking a track on the duplicate also unlocked it on the source, and re-locking the source
  did not stick once the duplicate was selected again. Read-only silence detection still works
  on locked tracks.
- **Links restored.** Clips that were linked in the source (for example camera video with its
  scratch audio) are relinked piece by piece. Relink failures are reported in `notes`.
- **Markers follow the edit** (`carry_markers=true`). Timeline markers inside kept time move
  with it (color, name, note, custom data; duration clipped to the kept stretch). Markers inside
  removed time are dropped and counted in `notes`.
- **Every track is verified** after appending (`verified_tracks`), not just track 1.
- **Sync-safe `min_keep_seconds`**: short kept stretches are removed from the global keep list,
  never from one track only.
- **Clearer exclusions.** Off the spine track, titles, generators, compound/multicam clips,
  retimed clips and other-frame-rate media are skipped with a reason in `not_carried_over`;
  on the spine track they are an error. Caption cues are summarized per subtitle track and are
  not copied (re-run captions on the variant).

## Limitations

- Clip-level effects, grades, Fusion comps and per-clip audio settings on source clips are not
  carried: pieces are appended fresh from the media pool. Track-level settings are kept.
- Items that can't be re-cut exactly are dropped from the variant (and listed), not guessed.
- A clip whose audio Resolve splits across several tracks from one append (multi-channel media
  on mixed track formats) is caught by verification and reported as a failure.

## Validation

- Automated: 160 tests, including a real ffmpeg two-mic run.
- Live: see [VALIDATION.md](VALIDATION.md), section "2.2 live acceptance".
