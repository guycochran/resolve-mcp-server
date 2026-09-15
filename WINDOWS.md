# Windows setup

The full current instructions are in [README.md](README.md#install-on-windows-powershell).
Use a compatible standard 64-bit Python interpreter and Resolve Studio with
External scripting set to Local.

Run `.venv\Scripts\resolve-mcp.exe --doctor` for read-only diagnostics.

The development machine has Resolve 21.0.4.5 running, but its bundled Python 3.12.14
could not initialize Blackmagic's fusionscript extension. This does not establish
a failure on standard Python installations; live compatibility remains unverified.
See [validation](docs/VALIDATION.md).