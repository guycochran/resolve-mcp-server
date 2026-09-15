# Executed validation — 2026-09-15

## Environment

Windows workstation with DaVinci Resolve executable version **21.0.4.5** installed.
Development interpreter: bundled CPython **3.12.14**, 64-bit.
Resolved/tested MCP SDK: **1.30.0**, preserving FastMCP.
No existing Resolve project was edited and no paid/cloud AI operation was invoked.

## Results

| Check | Result |
|---|---|
| Unit/protocol tests | 93 passing |
| Ruff static checks | Pass |
| All original tool names | All 53 retained |
| Server inventory | 71 tools, 16 resources |
| Editable package installation | Pass |
| Source distribution and wheel build | Pass |
| Wheel installation to a separate directory | Pass |
| Installed-wheel imports, inventory and CLI | Pass |
| Dependency consistency (`pip check`) | Pass |
| Real stdio process initialization, tools/resources listing and resource read | Pass |
| Authenticated HTTP initialization | Pass, ASGI protocol test |
| Missing/incorrect HTTP token and untrusted Host/Origin | Rejected as expected |
| Live Resolve native-library connection | Blocked: fusionscript initialization |
| macOS native acceptance | Not run |
| Cloudflare/Tailscale deployment | Documented; not deployed |

The tests emit two upstream Starlette/AnyIO deprecation warnings; they do not fail
the suite. These are test-client dependencies, not evidence of a native Resolve
integration pass.

## Commands

Normal development commands:

```bash
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m build
resolve-mcp --version
resolve-mcp --doctor
```

This restricted Windows environment needed an external, workspace-only temporary
directory workaround: Python's mode-0700 temporary directories were not accessible
to the sandbox process. The workaround inherits existing workspace permissions,
is not shipped in the package, and does not modify system Python. Editable
installation/build used `--no-build-isolation` / `--no-isolation` with the required
build dependencies preinstalled. Builds were written into the workspace temporary
root to avoid the same permission issue.

The SDK client's Windows asyncio subprocess helper could not open its named pipes
in this sandbox. The stdio protocol test uses a real subprocess and anonymous pipes,
with initialize, initialized notification, tools/list, resources/list and
resources/read exchanges and bounded read timeouts.

## Live blocker

`--doctor` reports:

```text
SystemError: initialization of fusionscript failed without raising an exception
```

The native module fails before a usable scripting connection is established.
This is not proof that the server works with the installed Resolve, nor proof that
Resolve itself is incompatible. OS process enumeration may also report unknown
when the diagnostic process query is restricted.

Next live step: use a compatible standard 64-bit Python installation with Resolve
Studio external scripting set to Local, then run [INTEGRATION_TESTS.md](INTEGRATION_TESTS.md).
Do not certify production readiness until the Windows and macOS acceptance results
are recorded.