$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    Write-Host 'Python environment missing. See README.md to set up .venv.' -ForegroundColor Yellow
    exit 1
}
$env:PYTHONUTF8 = '1'
& $taskPython app.py --open
exit $LASTEXITCODE
