# Architecture

## Foundation retained

The original server uses FastMCP, a central connection service, eleven tool modules,
and a Moondream HTTP client. Version 2.0 evolves those modules into an installable
`resolve_mcp` package; it does not replace the editing model or MCP framework.

```text
src/resolve_mcp/
  server.py               FastMCP composition, serialized operations, stdio/HTTP
  config.py               Environment validation and conservative network defaults
  security.py             Shared bearer-token ASGI authentication
  resources.py            Sixteen read-only JSON snapshots
  services/
    resolve_connection.py Platform paths, health cache, retry cooldown, diagnostics
    lookup.py             Deterministic media/tree/track lookup
    replacement.py        Source bounds, non-ripple replacement, recovery timelines
    transforms.py         Validate before writing; report partial failures
    timecode.py           NDF/DF frame conversion and exact playhead offset
    results.py            Structured errors and native method availability
    moondream.py          Existing cloud vision client, in-memory JPEG preparation
  tools/
    connection.py project.py timeline.py media.py editing.py
    color.py markers.py titles.py render.py fusion.py vision.py
    analysis.py           Resolve-native AI, distinct from Moondream
    workflows.py          Editorial tasks built from shared services
src/server.py             Legacy source-launch compatibility
tests/                   Mocked units plus real MCP protocol startup tests
```

The resources remain one short module sharing snapshot helpers; splitting each
three-line reader into a separate file would add little isolation.

## Execution and concurrency

Every registered tool and resource is serialized under the server's operation
lock, including async vision requests. This protects the shared Resolve selection
and complete delete/insert sequences from concurrent calls within this process.
It does not prevent a person or a second server process from changing Resolve.
Use one process and coordinate exclusive editing access.

Connection checks are cached for five seconds; failed connections retry at most
once every two seconds. Forced reconnect bypasses this delay. Failed operations
are not automatically replayed, because repeating a mutation can duplicate work.

## Compatibility

All 53 original MCP tool names remain, verified against the main-branch source.
Existing tool responses generally remain JSON text or readable text. New tools use
JSON-compatible dict responses. Resources use explicit success/data/error envelopes.

Source launchers remain available. Internal imports move from generic `src.*`
to `resolve_mcp.*`; third-party code importing the old internal modules should
update imports. The legacy `src.server` entry point remains.

## Mutation recovery

Replacement preflights media, ranges and track state, then duplicates the entire
timeline before unlink/delete/append. On failure it selects that full recovery
copy. It never claims the original timeline object has been atomically rolled back.
Reports include original frame/source/property information and the recovery name.
Backup timelines are deliberately retained until the operator reviews them.

## Security boundary

stdio relies on local OS access. HTTP uses loopback by default and validates
Host/Origin. External binding and public origins require a configured token.
Bearer authentication protects all HTTP methods. TLS, per-user identity,
revocation, rate limiting and OAuth belong at a gateway.

Tokens confer full editing authority; this is not multi-tenant isolation.
There is no arbitrary-code tool. Media import/export can access workstation files.
Only explicitly invoked vision tools send image data to Moondream.

## Technical debt addressed

Hard-coded Mac launch paths, stdout redirection, undeclared dotenv dependency,
unchecked transforms, incorrect playhead markers, ambiguous replacement lookup,
inclusive-out off-by-one, lost clips after insertion failure, shared frame filenames,
and permissive external HTTP defaults.

Remaining acceptance work and native API constraints are recorded in
[VALIDATION.md](docs/VALIDATION.md) and [INTEGRATION_TESTS.md](docs/INTEGRATION_TESTS.md).