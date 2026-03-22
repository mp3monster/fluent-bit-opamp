param(
    [string]$ServerSpec = "",
    [string]$Name = "OpAMP Server",
    [string]$Project = "",
    [string]$OpAMPServerIp = "",
    [switch]$NoEditable
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ProviderSrc = Join-Path $RepoRoot "provider/src"
$PythonPathValue = "$RepoRoot;$ProviderSrc"

if ([string]::IsNullOrWhiteSpace($ServerSpec)) {
    $ServerSpec = Join-Path $RepoRoot "provider/src/opamp_provider/mcptool/routes.py:mcpserver"
}

if ([string]::IsNullOrWhiteSpace($Project)) {
    $Project = Join-Path $RepoRoot "provider"
}

if ([string]::IsNullOrWhiteSpace($OpAMPServerIp)) {
    $enteredIp = Read-Host "Enter OpAMP server IP (default: localhost)"
    if ([string]::IsNullOrWhiteSpace($enteredIp)) {
        $OpAMPServerIp = "localhost"
    } else {
        $OpAMPServerIp = $enteredIp.Trim()
    }
}
$OpAMPServerUrl = "http://$OpAMPServerIp:8000"
$OpAMPMcpSseUrl = "$OpAMPServerUrl/sse"

function Get-CmdPath {
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Add-PathEntry {
    param(
        [string[]]$ExistingEntries,
        [string]$Entry
    )
    if ([string]::IsNullOrWhiteSpace($Entry)) { return $ExistingEntries }
    if ($ExistingEntries -contains $Entry) { return $ExistingEntries }
    return @($ExistingEntries + $Entry)
}

function Build-RuntimePath {
    $entries = @($env:PATH -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $requiredTools = @("python", "uv", "fastmcp", "node", "npm")

    foreach ($tool in $requiredTools) {
        $toolPath = Get-CmdPath $tool
        if (-not [string]::IsNullOrWhiteSpace($toolPath)) {
            $toolDir = Split-Path -Parent $toolPath
            $entries = Add-PathEntry -ExistingEntries $entries -Entry $toolDir
        }
    }

    return ($entries -join ";")
}

function Install-WithPackageManager {
    param(
        [string]$WingetId,
        [string]$ChocoId
    )
    if (Get-CmdPath "winget") {
        try {
            & winget install -e --id $WingetId --accept-source-agreements --accept-package-agreements
            return $true
        } catch {
            Write-Warning "winget install failed for ${WingetId}: $($_.Exception.Message)"
        }
    }
    if (Get-CmdPath "choco") {
        try {
            & choco install -y $ChocoId
            return $true
        } catch {
            Write-Warning "choco install failed for ${ChocoId}: $($_.Exception.Message)"
        }
    }
    return $false
}

function Ensure-Python {
    if (Get-CmdPath "python") { return }
    Write-Host "python not found. Attempting install..."
    $installed = Install-WithPackageManager -WingetId "Python.Python.3.11" -ChocoId "python"
    if (-not $installed -or -not (Get-CmdPath "python")) {
        Write-Error "python is required. Install Python 3.11+ and re-run."
    }
}

function Ensure-Pip {
    try {
        & python -m pip --version | Out-Null
    } catch {
        Write-Host "pip not found. Attempting bootstrap with ensurepip..."
        & python -m ensurepip --upgrade | Out-Null
    }
    try {
        & python -m pip --version | Out-Null
    } catch {
        Write-Error "pip is required. Install pip and re-run."
    }
}

function Ensure-Uv {
    if (Get-CmdPath "uv") { return }
    Write-Host "uv not found. Attempting install via pip..."
    try {
        & python -m pip install --upgrade uv | Out-Null
    } catch {
        Write-Warning "pip install uv failed: $($_.Exception.Message)"
    }
    if (-not (Get-CmdPath "uv")) {
        Write-Host "Attempting uv install via package manager..."
        $installed = Install-WithPackageManager -WingetId "astral-sh.uv" -ChocoId "uv"
        if (-not $installed -or -not (Get-CmdPath "uv")) {
            Write-Error "uv is required. Install uv and re-run."
        }
    }
}

function Ensure-FastMCP {
    if (Get-CmdPath "fastmcp") { return }
    Write-Host "fastmcp not found. Installing with pip..."
    & python -m pip install --upgrade fastmcp | Out-Null
    if (-not (Get-CmdPath "fastmcp")) {
        Write-Error "fastmcp install failed. Run: python -m pip install --upgrade fastmcp"
    }
}

Ensure-Python
Ensure-Pip
Ensure-Uv
Ensure-FastMCP
$RuntimePath = Build-RuntimePath

if (-not (Test-Path -Path $Project -PathType Container)) {
    Write-Error "Project directory not found: $Project"
}

$args = @(
    "install",
    "claude-desktop",
    "--name", $Name,
    "--project", $Project,
    "--env", "PYTHONPATH=$PythonPathValue",
    "--env", "OPAMP_SERVER_IP=$OpAMPServerIp",
    "--env", "OPAMP_SERVER_URL=$OpAMPServerUrl",
    "--env", "OPAMP_MCP_SSE_URL=$OpAMPMcpSseUrl",
    "--env", "PATH=$RuntimePath"
)

if (-not $NoEditable) {
    $args += @("--with-editable", $Project)
}

$args += $ServerSpec

Write-Host "Installing Claude Desktop MCP server via fastmcp..."
Write-Host ("Command: fastmcp " + ($args -join " "))

& fastmcp @args

Write-Host "Claude Desktop configuration has been updated via fastmcp."
