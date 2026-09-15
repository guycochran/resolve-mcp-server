# Resolve 21 / Windows update

This local 1.1.0 development update adds Windows/macOS/Linux scripting module discovery,
stale-connection recovery, six read-only MCP resources, and three Resolve 21 tools:
transcription with speaker detection, audio classification, and IntelliSearch.
The AI signatures were checked against the scripting README installed with Resolve 21.0.4.5.
Existing editing, vision, and HTTP tools remain available.

## Setup

Use a standard 64-bit Python 3.10+ installation compatible with Resolve's native scripting library.
From the repository directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\start.ps1
```

Start Resolve Studio and set Preferences > System > General > External scripting using to Local.
For a local MCP client, use the absolute path to `.venv\Scripts\python.exe` as the command,
and the absolute path to `src\server.py` as its argument.
Custom installations can set `RESOLVE_SCRIPT_API` to the Scripting directory,
`PYTHONPATH_RESOLVE` to its Modules directory, and `RESOLVE_SCRIPT_LIB` to fusionscript.dll.

HTTP: set `TRANSPORT=http` and optionally `PORT`. The default HOST is now 127.0.0.1.
Set HOST explicitly for a trusted network deployment; remote authentication must be provided
by your access gateway. Loopback HTTP still supports a tunnel running on this machine.

## Resources

- `resolve://system/status`
- `resolve://project/current`
- `resolve://timeline/current`
- `resolve://timeline/items` (video, audio, subtitle tracks)
- `resolve://mediapool/clips` (current bin)
- `resolve://render/jobs`

Analysis tools accept an exact clip name within the current bin and reject duplicates.
An empty clip name selects the current folder; transcription and classification include
nested folders. IntelliSearch needs the appropriate Extras package. Face identification
defaults to off.

## Validation and remaining work

Run `python -m unittest discover -s tests -v` for isolated connection/analysis tests.
These tests do not establish live Resolve compatibility.
On the development machine, dependency installation encountered filesystem permission errors,
and the bundled Python 3.12 interpreter failed to initialize Resolve's fusionscript extension.
Full MCP startup and live API operations still require verification with a working Python/Resolve setup.
No project edits or AI analyses were executed during this update.

Slate ID, motion deblur, speech generation, and remote authentication are future work.
This is an initial compatibility update, not a complete 2.0 release.
