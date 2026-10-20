param(
    [ValidateSet('gpu', 'cpu')][string]$Mode = 'gpu',
    [string]$PythonExe = '',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Program $($Arguments -join ' ')" }
}
try {
    $runtime = Join-Path $root '.runtime'
    $taskPython = Join-Path $runtime 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        if ($PythonExe) {
            Invoke-Checked $PythonExe @('-c', "import sys,struct; assert sys.version_info[:2] in [(3,10),(3,11)] and struct.calcsize('P')==8")
            Invoke-Checked $PythonExe @('-m', 'venv', $runtime)
        } else {
            $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
            if (-not $launcher) { throw 'Install 64-bit Python 3.10 first, or pass -PythonExe with its full executable path.' }
            Invoke-Checked $launcher.Source @('-3.10', '-m', 'venv', $runtime)
        }
    }
    Invoke-Checked $taskPython @('-c', "import sys,struct; assert sys.version_info[:2] in [(3,10),(3,11)] and struct.calcsize('P')==8; assert sys.prefix != sys.base_prefix; assert not __import__('site').ENABLE_USER_SITE")
    $state = Join-Path $root '.deployment'
    New-Item -ItemType Directory -Path $state -Force | Out-Null
    $modeFile = Join-Path $state 'environment.json'
    if (Test-Path -LiteralPath $modeFile) {
        $previous = Get-Content -LiteralPath $modeFile -Raw | ConvertFrom-Json
        if ($previous.mode -ne $Mode) { throw 'This runtime uses another mode. Keep its backup and rebuild .runtime before changing GPU/CPU mode.' }
    }
    if (-not $SkipInstall) {
        Invoke-Checked $taskPython @('-m', 'ensurepip', '--upgrade')
        Invoke-Checked $taskPython @('-m', 'pip', 'install', '--upgrade', 'pip')
        if ($Mode -eq 'gpu') {
            Invoke-Checked $taskPython @('-m', 'pip', 'install', 'torch==2.8.0', 'torchvision==0.23.0', '--index-url', 'https://download.pytorch.org/whl/cu129')
        } else {
            Invoke-Checked $taskPython @('-m', 'pip', 'install', 'torch==2.8.0', 'torchvision==0.23.0', '--index-url', 'https://download.pytorch.org/whl/cpu')
        }
        Invoke-Checked $taskPython @('-m', 'pip', 'install', '-r', (Join-Path $PSScriptRoot 'requirements-common.txt'))
        Invoke-Checked $taskPython @('-m', 'pip', 'check')
    }
    Invoke-Checked $taskPython @((Join-Path $PSScriptRoot 'check_env.py'), '--mode', $Mode, '--infer')
    @{ mode=$Mode; installed=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $modeFile -Encoding UTF8
    Write-Host 'Setup complete. Run start-deploy.cmd.' -ForegroundColor Green
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
}
