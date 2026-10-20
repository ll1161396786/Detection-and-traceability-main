$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$taskPython = Join-Path $root '.runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { Write-Host 'Run install.cmd first.' -ForegroundColor Red; exit 1 }
if (-not (Test-Path -LiteralPath (Join-Path $root '.deployment\environment.json'))) { Write-Host 'Setup has not passed validation. Run install.cmd first.' -ForegroundColor Red; exit 1 }
$env:PYTHONUTF8 = '1'
& $taskPython (Join-Path $PSScriptRoot 'serve.py') --config (Join-Path $PSScriptRoot 'config.json')
exit $LASTEXITCODE
