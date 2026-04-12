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
Compatibility wrapper for Claude-first parameter naming.

.DESCRIPTION
Preserves legacy semantics where -Name maps to the Claude Desktop display name,
then delegates execution to configure-mcp-clients-fastmcp.ps1.
Supported clients (via canonical script): Claude Desktop, ChatGPT/Codex, VS Code.
#>

[CmdletBinding()]
param(
    [string]$ServerSpec = "",
    [string]$Name = "OpAMP Server",
    [string]$ChatGPTName = "opamp-server",
    [string]$Clients = "claude",
    [string]$Project = "",
    [string]$OpAMPServerIp = "",
    [int]$OpAMPServerPort = 8080,
    [switch]$NoEditable,
    [Alias("h")]
    [switch]$Help
)

$CanonicalScript = Join-Path $PSScriptRoot "configure-mcp-clients-fastmcp.ps1"
if (-not (Test-Path -Path $CanonicalScript -PathType Leaf)) {
    throw "Canonical script not found: $CanonicalScript"
}

$ForwardParams = @{
    ClaudeName  = $Name
    ChatGPTName = $ChatGPTName
    Clients     = $Clients
}
if (-not [string]::IsNullOrWhiteSpace($ServerSpec)) {
    $ForwardParams.ServerSpec = $ServerSpec
}
if (-not [string]::IsNullOrWhiteSpace($Project)) {
    $ForwardParams.Project = $Project
}
if (-not [string]::IsNullOrWhiteSpace($OpAMPServerIp)) {
    $ForwardParams.OpAMPServerIp = $OpAMPServerIp
}
if ($OpAMPServerPort -gt 0) {
    $ForwardParams.OpAMPServerPort = $OpAMPServerPort
}
if ($NoEditable) {
    $ForwardParams.NoEditable = $true
}
if ($Help) {
    $ForwardParams.Help = $true
}

& $CanonicalScript @ForwardParams
