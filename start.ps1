$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$resolvePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $resolvePython)) {
    throw 'Create .venv and install dependencies first; see WINDOWS.md.'
}
& $resolvePython -m src.server
exit $LASTEXITCODE
