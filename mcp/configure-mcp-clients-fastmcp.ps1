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
- Claude Desktop via `mcp-remote` SSE endpoint entry in `claude_desktop_config.json`
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
    [int]$OpAMPServerPort = 8080,
    [switch]$NoEditable,
    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ProviderSrc = Join-Path $RepoRoot "provider/src"
$SharedSrc = Join-Path $RepoRoot "shared"
$PythonPathValue = $env:PYTHONPATH
$UseLocalSourcePaths = $false

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
    $source = $cmd.Source
    if ([string]::IsNullOrWhiteSpace($source)) {
        return $null
    }
    # PowerShell commonly resolves npm tools to *.ps1 shims (for example npx.ps1),
    # but desktop apps spawning child processes usually need a directly executable
    # target such as *.cmd or *.exe.
    if ([string]::Equals([System.IO.Path]::GetExtension($source), ".ps1", [System.StringComparison]::OrdinalIgnoreCase)) {
        $cmdShim = [System.IO.Path]::ChangeExtension($source, ".cmd")
        if (Test-Path -Path $cmdShim -PathType Leaf) {
            return $cmdShim
        }
        $exeShim = [System.IO.Path]::ChangeExtension($source, ".exe")
        if (Test-Path -Path $exeShim -PathType Leaf) {
            return $exeShim
        }
    }
    return $source
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

function Get-MissingRequiredModules {
    # Returns a list of required modules not importable from the current Python environment.
    $code = @'
import importlib.util
import os
import tempfile
os.chdir(tempfile.gettempdir())
required = ("opamp_provider", "shared")
missing = [name for name in required if importlib.util.find_spec(name) is None]
print(",".join(missing))
'@
    $result = & python -c $code
    return @("$result".Trim())
}

function Build-PythonPathValue {
    # Builds PYTHONPATH, adding local repo/provider/shared paths only when needed.
    param(
        [string]$CurrentValue,
        [bool]$NeedLocalPaths
    )
    $entries = @()
    if (-not [string]::IsNullOrWhiteSpace($CurrentValue)) {
        $entries += ($CurrentValue -split ";" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    }
    if ($NeedLocalPaths) {
        foreach ($entry in @($RepoRoot, $ProviderSrc, $SharedSrc)) {
            if (-not [string]::IsNullOrWhiteSpace($entry) -and -not ($entries -contains $entry)) {
                $entries += $entry
            }
        }
    }
    return ($entries -join ";")
}

function Remove-LegacyServerEntries {
    # Removes known legacy OpAMP server names from a config map, preserving the active target name.
    param(
        [System.Collections.IDictionary]$ServerMap,
        [string]$KeepName,
        [string]$ContextLabel
    )
    if ($null -eq $ServerMap) {
        return
    }
    $legacyNames = @("OpAMP Server", "opamp-server", "opampServer")
    foreach ($legacyName in $legacyNames) {
        if ([string]::Equals($legacyName, $KeepName, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        if ($ServerMap.Contains($legacyName)) {
            $ServerMap.Remove($legacyName) | Out-Null
            Write-Host "Removed legacy $ContextLabel MCP entry '$legacyName'."
        }
    }
}

function Resolve-ClaudeRemoteLaunch {
    # Resolves an executable launch form for remote MCP transport.
    # Preference order:
    # 1) direct mcp-remote binary
    # 2) npx -y mcp-remote
    $mcpRemotePath = Get-CmdPath "mcp-remote"
    if (-not [string]::IsNullOrWhiteSpace($mcpRemotePath)) {
        return @{
            command = $mcpRemotePath
            args = @($OpAMPMcpSseUrl)
        }
    }

    $npxPath = Get-CmdPath "npx"
    if (-not [string]::IsNullOrWhiteSpace($npxPath)) {
        return @{
            command = $npxPath
            args = @("-y", "mcp-remote", $OpAMPMcpSseUrl)
        }
    }

    Write-Error (
        "Neither 'mcp-remote' nor 'npx' was found on PATH. " +
        "Install one of them before configuring Claude Desktop MCP."
    )
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
    $remoteLaunch = Resolve-ClaudeRemoteLaunch
    $serverConfig = @{
        command = $remoteLaunch.command
        args = $remoteLaunch.args
        env = @{
            OPAMP_SERVER_IP = $OpAMPServerIp
            OPAMP_SERVER_URL = $OpAMPServerUrl
            OPAMP_MCP_SSE_URL = $OpAMPMcpSseUrl
        }
    }

    $appDataPath = [Environment]::GetFolderPath("ApplicationData")
    if ([string]::IsNullOrWhiteSpace($appDataPath)) {
        Write-Error "Unable to resolve ApplicationData folder for Claude Desktop config."
    }
    $claudeConfigPath = Join-Path $appDataPath "Claude\claude_desktop_config.json"

    if (Test-Path -Path $claudeConfigPath) {
        $existingText = Get-Content -Raw -Path $claudeConfigPath
        if ([string]::IsNullOrWhiteSpace($existingText)) {
            $document = @{}
        } else {
            $document = $existingText | ConvertFrom-Json -AsHashtable
        }
    } else {
        $document = @{}
    }
    if ($document -isnot [System.Collections.IDictionary]) {
        Write-Error "Invalid Claude Desktop MCP config format in $claudeConfigPath"
    }
    if (-not $document.ContainsKey("mcpServers") -or $document["mcpServers"] -isnot [System.Collections.IDictionary]) {
        $document["mcpServers"] = @{}
    }
    Remove-LegacyServerEntries -ServerMap $document["mcpServers"] -KeepName $ClaudeName -ContextLabel "Claude Desktop"
    $document["mcpServers"][$ClaudeName] = $serverConfig

    $claudeConfigDir = Split-Path -Parent $claudeConfigPath
    if (-not (Test-Path -Path $claudeConfigDir -PathType Container)) {
        New-Item -ItemType Directory -Path $claudeConfigDir -Force | Out-Null
    }

    $jsonOutput = $document | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($claudeConfigPath, "$jsonOutput`n", $utf8NoBom)
    Write-Host "Claude Desktop configuration has been updated at $claudeConfigPath (mcp-remote -> $OpAMPMcpSseUrl)."
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
    foreach ($legacyName in @("OpAMP Server", "opamp-server", "opampServer")) {
        if ([string]::Equals($legacyName, $ChatGPTName, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        try {
            & codex mcp get $legacyName | Out-Null
            Write-Host "Removing legacy ChatGPT/Codex MCP server '$legacyName'..."
            & codex mcp remove $legacyName | Out-Null
        } catch {
            # Not found is fine.
        }
    }

    $serverCommand = @(
        "uv",
        "run",
        "--project", $Project,
        "--with", "fastmcp"
    )
    if (-not $NoEditable) {
        $serverCommand += @("--with-editable", $Project)
        if ($UseLocalSourcePaths) {
            $serverCommand += @("--with-editable", $RepoRoot)
        }
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
        if ($UseLocalSourcePaths) {
            $mcpJsonArgs += @("--with-editable", $RepoRoot)
        }
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
    Remove-LegacyServerEntries -ServerMap $document["servers"] -KeepName $VSCodeName -ContextLabel "VS Code"
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
  -OpAMPServerPort <port>  OpAMP server port used for URL env vars (default: 8080)
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
$OpAMPServerUrl = "http://$($OpAMPServerIp):$($OpAMPServerPort)"
$OpAMPMcpSseUrl = "$OpAMPServerUrl/sse"

$InstallTargets = Get-InstallTargets -ClientList $Clients
$NeedChatGPT = [bool]$InstallTargets["chatgpt"]
$NeedVSCode = [bool]$InstallTargets["vscode"]
$NeedPythonTooling = ($NeedChatGPT -or $NeedVSCode)
$NeedFastMCPCli = $NeedVSCode

if ($NeedPythonTooling) {
    Ensure-Python
    Ensure-Pip
    Ensure-Uv
    if ($NeedFastMCPCli) {
        Ensure-FastMCP
    }
    $missingModules = Get-MissingRequiredModules
    if (-not [string]::IsNullOrWhiteSpace($missingModules[0])) {
        $UseLocalSourcePaths = $true
        Write-Host "Detected missing Python modules ($($missingModules[0])); using local source paths."
    } else {
        $UseLocalSourcePaths = $false
        Write-Host "Detected globally importable opamp_provider/shared modules; local source paths are optional."
    }
    $PythonPathValue = Build-PythonPathValue -CurrentValue $env:PYTHONPATH -NeedLocalPaths $UseLocalSourcePaths
    $RuntimePath = Build-RuntimePath
} else {
    $UseLocalSourcePaths = $false
    $PythonPathValue = ""
    $RuntimePath = $env:PATH
}

if (($NeedChatGPT -or $NeedVSCode) -and -not (Test-Path -Path $Project -PathType Container)) {
    Write-Error "Project directory not found: $Project"
}

if ([bool]$InstallTargets["claude"]) {
    Install-ClaudeTarget
}
if ([bool]$InstallTargets["chatgpt"]) {
    Ensure-Codex
    Install-ChatGPTTarget
}
if ([bool]$InstallTargets["vscode"]) {
    Install-VSCodeTarget
}

Write-Host "Completed MCP client installation for targets: $Clients."
