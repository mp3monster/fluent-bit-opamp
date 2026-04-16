param(
    [switch]$Service
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSCommandPath
$RootDir = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RootDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$LinuxVenvPython = Join-Path $VenvDir "bin\python"
$PythonCmd = ""

if (-not $env:PYTHONUNBUFFERED) {
    $env:PYTHONUNBUFFERED = "1"
}
if (-not $env:BROKER_CONFIG_PATH) {
    $env:BROKER_CONFIG_PATH = Join-Path $RootDir "opamp_broker\config\broker.example.json"
}

if (-not (Test-Path $VenvDir)) {
    python -m venv $VenvDir
}

if (Test-Path $VenvPython) {
    $PythonCmd = $VenvPython
} else {
    if (Test-Path $LinuxVenvPython) {
        Write-Host "Detected Linux-style .venv layout; falling back to python on PATH for PowerShell runtime."
    } else {
        Write-Host "Windows venv python not found at $VenvPython; falling back to python on PATH."
    }
    $PythonCmd = "python"
}

try {
    & $PythonCmd --version *> $null
} catch {
    throw "Unable to run Python command '$PythonCmd'. Ensure Python is installed and available on PATH."
}

& $PythonCmd -m pip install -r (Join-Path $RootDir "requirements.txt")

if (-not $Service) {
    & $PythonCmd -m opamp_broker.broker_app
    exit $LASTEXITCODE
}

$RuntimeDir = if ($env:BROKER_RUNTIME_DIR) { $env:BROKER_RUNTIME_DIR } else { Join-Path $RootDir ".broker" }
$PidFile = if ($env:BROKER_PID_FILE) { $env:BROKER_PID_FILE } else { Join-Path $RuntimeDir "broker.pid" }
$LogFile = if ($env:BROKER_LOG_FILE) { $env:BROKER_LOG_FILE } else { Join-Path $RuntimeDir "broker.log" }
$ErrLogFile = if ($env:BROKER_ERR_LOG_FILE) { $env:BROKER_ERR_LOG_FILE } else { "$LogFile.err" }

if (-not (Test-Path $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

if (Test-Path $PidFile) {
    $existingPid = (Get-Content $PidFile -Raw).Trim()
    if ($existingPid) {
        $existingProc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProc) {
            Write-Host "Broker already running (pid=$existingPid)."
            Write-Host "Stdout log file: $LogFile"
            Write-Host "Stderr log file: $ErrLogFile"
            exit 0
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

$process = Start-Process `
    -FilePath $PythonCmd `
    -ArgumentList @("-m", "opamp_broker.broker_app") `
    -WorkingDirectory $RootDir `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrLogFile `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id -Encoding utf8
Start-Sleep -Seconds 1

$runningProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if ($runningProcess) {
    Write-Host "Broker started (pid=$($process.Id))."
    Write-Host "PID file: $PidFile"
    Write-Host "Stdout log file: $LogFile"
    Write-Host "Stderr log file: $ErrLogFile"
    exit 0
}

Remove-Item $PidFile -ErrorAction SilentlyContinue
throw "Broker failed to start. Check log files: $LogFile and $ErrLogFile"
