$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stateFile = Join-Path $root '.deployment\server.json'
try {
    if (-not (Test-Path -LiteralPath $stateFile)) { Write-Host 'No managed deployment is running.'; exit 0 }
    $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    $serverPid = [int]$state.pid
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
    if (-not $process) { Write-Host 'The recorded process has already exited.'; exit 0 }
    $expectedScript = Join-Path $PSScriptRoot 'serve.py'
    $createdUtc = ([datetimeoffset]$state.created_utc).UtcDateTime
    if ($process.ExecutablePath -ne $state.executable -or -not $process.CommandLine.Contains($expectedScript) -or [math]::Abs((([datetime]$process.CreationDate).ToUniversalTime() - $createdUtc).TotalSeconds) -gt 3) {
        throw 'Process identity mismatch; no process was stopped.'
    }
    $base = "http://127.0.0.1:$($state.port)"
    $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 10
    if ($health.instance -ne $state.instance) { throw 'Server identity mismatch; no process was stopped.' }
    if ($health.active_offline_jobs -gt 0) { throw 'An offline workbench job is running. Finish it before stopping this deployment.' }
    Invoke-RestMethod "$base/api/shuttles/04/stop" -Method Post -TimeoutSec 20 | Out-Null
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 300
        $current = Invoke-RestMethod "$base/api/shuttles/04/state" -TimeoutSec 10
        $running = @($current.cameras | Where-Object { $_.status -in @('running','loading') }).Count
    } while ($running -gt 0 -and (Get-Date) -lt $deadline)
    if ($running -gt 0) { throw 'Detection is still stopping. Retry later; no process was terminated.' }
    Stop-Process -Id $serverPid -Force
    Remove-Item -LiteralPath $stateFile -Force
    Write-Host 'Deployment stopped; detection evidence has been retained.'
} catch { Write-Host $_ -ForegroundColor Red; exit 1 }
