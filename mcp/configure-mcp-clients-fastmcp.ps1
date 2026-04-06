#
# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

<#
.SYNOPSIS
Configure OpAMP MCP for Claude Desktop, ChatGPT (Codex CLI), and VS Code.

.DESCRIPTION
Supports these targets in one script:
- Claude Desktop via `fastmcp install claude-desktop`
- ChatGPT/Codex CLI via `codex mcp add`
- VS Code by writing a `servers` entry in `.vscode/mcp.json`

Target a specific client with `-Clients`:
- `-Clients claude`
- `-Clients chatgpt`
- `-Clients vscode`
- `-Clients claude,vscode` (multiple targets)

Default server names intentionally differ by client convention:
- ChatGPT/Codex uses `opamp-server` (kebab-case, CLI-friendly, backward-compatible)
- VS Code uses `opampServer` (camelCase per VS Code MCP naming guidance)

Use `-ChatGPTName`/`-ClaudeName`/`-VSCodeName` to override defaults.
#>

[CmdletBinding()]
param(
    [Alias("ServerName")]
    [string]$ChatGPTName = "opamp-server", # Kebab-case keeps CLI compatibility with prior script defaults.
    [string]$ClaudeName = "OpAMP Server",
    [string]$VSCodeName = "opampServer", # CamelCase follows VS Code MCP server naming guidance.
    [string]$VSCodeConfigPath = "",
    [string]$Clients = "claude,chatgpt,vscode",
    [string]$ServerSpec = "",
    [string]$Project = "",
    [string]$OpAMPServerIp = "",
    [switch]$NoEditable,
    [Alias("h", "help", "?")]
    [switch]$Help
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
if ([string]::IsNullOrWhiteSpace($VSCodeConfigPath)) {
    $VSCodeConfigPath = Join-Path $RepoRoot ".vscode/mcp.json"
}

function Get-CmdPath {
    # Returns the resolved executable path for the requested command, if present.
    param([string]$CommandName)
    $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { return $null }
    return $cmd.Source
}

function Add-PathEntry {
    # Appends a directory to PATH entries only when it is non-empty and not already present.
    param(
        [string[]]$ExistingEntries,
        [string]$Entry
    )
    if ([string]::IsNullOrWhiteSpace($Entry)) { return $ExistingEntries }
    if ($ExistingEntries -contains $Entry) { return $ExistingEntries }
    return @($ExistingEntries + $Entry)
}

function Build-RuntimePath {
    # Builds a PATH value that includes locations for required runtime tools.
    $entries = @($env:PATH -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $requiredTools = @("python", "uv", "fastmcp", "codex", "node", "npm")

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
    # Attempts installation via winget first, then Chocolatey.
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

function Ensure-Codex {
    if (Get-CmdPath "codex") { return }
    Write-Error "codex CLI is required but not on PATH. Install Codex CLI and re-run."
}

function Get-InstallTargets {
    param([string]$ClientList)
    $targets = @{
        claude = $false
        chatgpt = $false
        vscode = $false
    }
    foreach ($item in ($ClientList -split ",")) {
        $target = $item.Trim().ToLowerInvariant()
        switch ($target) {
            "claude" { $targets.claude = $true }
            "chatgpt" { $targets.chatgpt = $true }
            "codex" { $targets.chatgpt = $true }
            "vscode" { $targets.vscode = $true }
            "vs-code" { $targets.vscode = $true }
            "vs_code" { $targets.vscode = $true }
            "vs" { $targets.vscode = $true }
            "" { }
            default { Write-Error "Unknown client target '$target'. Expected: claude, chatgpt, vscode." }
        }
    }
    if (-not ($targets.claude -or $targets.chatgpt -or $targets.vscode)) {
        Write-Error "No valid client targets selected. Use -Clients 'claude,chatgpt,vscode'."
    }
    return $targets
}

function Install-ClaudeTarget {
    $args = @(
        "install",
        "claude-desktop",
        "--name", $ClaudeName,
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
    Write-Host "Claude Desktop configuration has been updated."
}

function Install-ChatGPTTarget {
    # Replace existing server definition when present.
    try {
        & codex mcp get $ChatGPTName | Out-Null
        Write-Host "Existing ChatGPT/Codex MCP server '$ChatGPTName' found. Replacing..."
        & codex mcp remove $ChatGPTName | Out-Null
    } catch {
        # Not found is fine.
    }

    $serverCommand = @(
        "uv",
        "run",
        "--project", $Project,
        "--with", "fastmcp"
    )
    if (-not $NoEditable) {
        $serverCommand += @("--with-editable", $Project)
    }
    $serverCommand += @(
        "fastmcp",
        "run",
        $ServerSpec
    )

    $addArgs = @(
        "mcp",
        "add",
        $ChatGPTName,
        "--env", "PYTHONPATH=$PythonPathValue",
        "--env", "OPAMP_SERVER_IP=$OpAMPServerIp",
        "--env", "OPAMP_SERVER_URL=$OpAMPServerUrl",
        "--env", "OPAMP_MCP_SSE_URL=$OpAMPMcpSseUrl",
        "--env", "PATH=$RuntimePath",
        "--"
    ) + $serverCommand

    Write-Host "Registering MCP server in ChatGPT/Codex CLI..."
    Write-Host ("Command: codex " + ($addArgs -join " "))
    & codex @addArgs

    Write-Host "ChatGPT/Codex MCP server '$ChatGPTName' has been configured."
}

function Install-VSCodeTarget {
    $mcpJsonArgs = @(
        "install",
        "mcp-json",
        "--name", $VSCodeName,
        "--project", $Project,
        "--env", "PYTHONPATH=$PythonPathValue",
        "--env", "OPAMP_SERVER_IP=$OpAMPServerIp",
        "--env", "OPAMP_SERVER_URL=$OpAMPServerUrl",
        "--env", "OPAMP_MCP_SSE_URL=$OpAMPMcpSseUrl",
        "--env", "PATH=$RuntimePath"
    )
    if (-not $NoEditable) {
        $mcpJsonArgs += @("--with-editable", $Project)
    }
    $mcpJsonArgs += $ServerSpec
    $generatedJson = & fastmcp @mcpJsonArgs
    $generated = $generatedJson | ConvertFrom-Json -AsHashtable

    $serverConfig = $generated[$VSCodeName]
    if ($null -eq $serverConfig) {
        foreach ($entry in $generated.GetEnumerator()) {
            $serverConfig = $entry.Value
            break
        }
    }
    if ($null -eq $serverConfig) {
        Write-Error "Unable to parse generated MCP JSON for VS Code."
    }
    $serverConfig = ($serverConfig | ConvertTo-Json -Depth 20 | ConvertFrom-Json -AsHashtable)
    if (-not $serverConfig.ContainsKey("type")) {
        $serverConfig["type"] = "stdio"
    }

    if (Test-Path -Path $VSCodeConfigPath) {
        $existingText = Get-Content -Raw -Path $VSCodeConfigPath
        if ([string]::IsNullOrWhiteSpace($existingText)) {
            $document = @{}
        } else {
            $document = $existingText | ConvertFrom-Json -AsHashtable
        }
    } else {
        $document = @{}
    }
    if ($document -isnot [System.Collections.IDictionary]) {
        Write-Error "Invalid VS Code MCP config format in $VSCodeConfigPath"
    }
    if (-not $document.ContainsKey("servers") -or $document["servers"] -isnot [System.Collections.IDictionary]) {
        $document["servers"] = @{}
    }
    $document["servers"][$VSCodeName] = $serverConfig

    $vscodeDir = Split-Path -Parent $VSCodeConfigPath
    if (-not (Test-Path -Path $vscodeDir -PathType Container)) {
        New-Item -ItemType Directory -Path $vscodeDir -Force | Out-Null
    }

    $jsonOutput = $document | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($VSCodeConfigPath, "$jsonOutput`n", $utf8NoBom)
    Write-Host "VS Code MCP configuration updated at $VSCodeConfigPath."
}

function Show-Usage {
    $scriptName = Split-Path -Leaf $MyInvocation.ScriptName
    @"
Usage: .\mcp\$scriptName [options]

Configure the OpAMP MCP server for Claude Desktop, ChatGPT (Codex CLI), and VS Code.

Options:
  -ChatGPTName <value>     ChatGPT/Codex MCP server name (default: opamp-server)
  -ClaudeName <value>      Claude Desktop display name (default: OpAMP Server)
  -VSCodeName <value>      VS Code server name in mcp.json (default: opampServer)
  -VSCodeConfigPath <path> VS Code mcp.json path (default: .vscode/mcp.json in repo)
  -Clients <list>          Comma-separated targets: claude,chatgpt,vscode
                           (default: claude,chatgpt,vscode)
  -ServerSpec <value>      Server spec (default: provider/src/opamp_provider/mcptool/routes.py:mcpserver)
  -Project <path>          Project directory for uv --project/--with-editable
  -OpAMPServerIp <ip>      OpAMP server IP (if omitted, prompts; default: localhost)
  -NoEditable              Skip --with-editable
  --help / -Help / -h      Show this help

Targeting examples:
  -Clients claude
  -Clients chatgpt
  -Clients vscode
  -Clients claude,vscode
"@ | Write-Host
}

if ($Help) {
    Show-Usage
    return
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

$InstallTargets = Get-InstallTargets -ClientList $Clients
Ensure-Python
Ensure-Pip
Ensure-Uv
Ensure-FastMCP
$NeedChatGPT = [bool]$InstallTargets["chatgpt"]
if ($NeedChatGPT) {
    Ensure-Codex
}
$RuntimePath = Build-RuntimePath

if (-not (Test-Path -Path $Project -PathType Container)) {
    Write-Error "Project directory not found: $Project"
}

if ([bool]$InstallTargets["claude"]) {
    Install-ClaudeTarget
}
if ([bool]$InstallTargets["chatgpt"]) {
    Install-ChatGPTTarget
}
if ([bool]$InstallTargets["vscode"]) {
    Install-VSCodeTarget
}

Write-Host "Completed MCP client installation for targets: $Clients."
