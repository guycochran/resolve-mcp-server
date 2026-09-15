# Operating Resolve MCP Server 2.0

- Read `resolve://system/status` or call `resolve_get_status` before work.
- Inspect current project and timeline; use exact media IDs for ambiguous names.
- Timeline item endpoints use absolute record frames; markers use offsets from
  timeline start. Source out-points for replacement are inclusive.
- Use a dry-run before replacement or B-roll insertion when planning an edit.
- Video-only replacement preserves linked interview audio by deleting only the
  selected video item. Combined A/V replacement is rejected.
- Recovery timelines are full copies. If a failed edit selects a recovery copy,
  tell the operator which original timeline may be modified. Do not claim an
  atomic rollback or automatically delete either copy.
- Read every operation result; do not interpret a false API status as success.
- Moondream sends frames to a cloud service; native Resolve AI is a separate path.
- Native transcription does not expose transcript text or speaker timestamps here.
  Chapter/speaker markers require timestamps supplied by the user or assistant.
- Visual search samples one visible composite frame per clip. Explain misses and
  sampling limits; do not claim it searched every source frame.
- Do not perform live acceptance tests on a professional project. Use the explicit
  disposable project described in docs/INTEGRATION_TESTS.md.
- Environment secrets belong in a private .env file or process environment.
- See README.md for setup and docs/VALIDATION.md for actual verification status.