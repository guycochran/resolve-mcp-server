$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$resolvePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $resolvePython)) {
    throw 'Create .venv and install the package first; see README.md.'
}
& $resolvePython -m resolve_mcp
exit $LASTEXITCODE