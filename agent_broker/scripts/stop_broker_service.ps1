$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSCommandPath
$RootDir = Split-Path -Parent $ScriptDir
$RuntimeDir = if ($env:BROKER_RUNTIME_DIR) { $env:BROKER_RUNTIME_DIR } else { Join-Path $RootDir ".broker" }
$PidFile = if ($env:BROKER_PID_FILE) { $env:BROKER_PID_FILE } else { Join-Path $RuntimeDir "broker.pid" }
$ShutdownTimeout = if ($env:BROKER_SHUTDOWN_TIMEOUT_SECONDS) { [int]$env:BROKER_SHUTDOWN_TIMEOUT_SECONDS } else { 30 }

if (-not (Test-Path $PidFile)) {
    Write-Host "Broker PID file not found: $PidFile"
    Write-Host "Broker may already be stopped."
    exit 0
}

$pidValue = (Get-Content $PidFile -Raw).Trim()
if (-not $pidValue) {
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host "Broker PID file was empty; cleared stale file."
    exit 0
}

$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host "Broker process $pidValue is not running; cleared stale PID file."
    exit 0
}

Write-Host "Requesting graceful broker shutdown for pid=$pidValue ..."
$closeRequested = $process.CloseMainWindow()
if (-not $closeRequested) {
    Write-Host "No main window available for close signal; requesting process stop."
    Stop-Process -Id $pidValue
}

for ($elapsed = 0; $elapsed -lt $ShutdownTimeout; $elapsed++) {
    Start-Sleep -Seconds 1
    $stillRunning = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if (-not $stillRunning) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Host "Broker stopped."
        exit 0
    }
}

Write-Host "Broker is still running after ${ShutdownTimeout}s."
Write-Host "You can force-stop manually with: Stop-Process -Id $pidValue -Force"
exit 1
