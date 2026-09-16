# Manual Resolve Studio acceptance suite

Run on Windows and macOS before calling the release production-validated.
Use a new disposable project named **MCP Integration Test**, with copied test media.
Do not use an existing professional project. Keep other automation and GUI editing idle.

## Fixture

- A 24 fps timeline starting at 01:00:00:00.
- Two video tracks; a 120-frame clip on V2 and interview audio on A1.
- Another 24 fps media clip with at least 240 frames.
- A shorter clip, a 30 fps clip, and two identically named media clips in separate bins.
- One Text+ title; an installed Quick Export preset.
- Optional: clips suitable for speech transcription, Slate ID, and deblur.

## Read-only and reconnect

1. Run `resolve-mcp --doctor`; record Python version, Resolve version and edition.
2. Initialize a stdio client and read all 16 resources.
3. Close the project: project/timeline readers should return structured errors.
4. Reopen; restart Resolve and use `resolve_reconnect`. Check recovery.
5. Repeat via authenticated HTTPS and verify missing/incorrect credentials get 401.
6. Check an unknown Host/Origin is rejected; a configured gateway host succeeds.

## Editing

1. Find the V2 clip by elapsed time and index; confirm exclusive end-frame behavior.
2. Dry-run a replacement. Confirm no backup or edit was created.
3. Replace video-only. Confirm exact 120-frame duration, same record position,
   unchanged A1 media/timing, no ripple, and preserved link relationships.
4. Inspect the recovery timeline: original grade, transforms, markers, links,
   Fusion and retiming should remain there.
5. Attempt a short-source, mixed-FPS, locked-track, and ambiguous-name replacement.
   Confirm the original clip survives each preflight rejection.
6. Simulate an insert refusal only in a controlled mocked API test; the automated
   suite covers this. A real-world refusal should select the recovery timeline and
   explicitly identify the modified original.
7. Insert B-roll into a gap; reject an overlapping interval.
8. Build an ordered rough cut into a new timeline; preserve the previous selection.
9. Set and read transforms; verify out-of-range values do not write.
10. Place a marker halfway through a clip and verify it lands at the playhead.
11. Test chapter frame zero and 29.97 drop-frame positions.
12. Insert/modify Text+, inspect Fusion, apply/export a LUT, and verify API failures
    are reported honestly. Exercise existing import/render/project tools.

## Native AI

Check each operation against the installed Extras and edition:

- Transcribe one clip, then a nested folder; repeat with speaker detection.
- Clear transcription; classify and clear audio classification.
- Analyze IntelliSearch in Faster/Better modes; test explicit face identification.
- Reset IntelliSearch only in the disposable project.
- Slate ID: verify the selected marker color enum.
- Deblur: verify new media is created; the timeline clip is not replaced.
- Generate speech: verify media creation with no timeline insertion.
- Disable background tasks last, then restart Resolve.

## Vision and rendering

1. Configure a test Moondream key; describe, detect and ask about a frame.
2. Force an API failure and confirm temporary frame cleanup.
3. Sample visual shots: compare sample timecodes, composite image, detections and
   restored playhead/page. Confirm that sampling limits are visible.
4. Render to a new local test directory using an installed preset.
5. Read render progress and verify uploading is disabled in the YouTube workflow.

Record OS, Python, Resolve version/edition, Extras, observed results and failures.
Automated tests cannot establish these native behaviors across codecs and versions.