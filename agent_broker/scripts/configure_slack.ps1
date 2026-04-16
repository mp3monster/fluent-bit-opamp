param(
  [string]$EnvFile = "",
  [string]$ManifestFile = "",
  [string]$AppName = "OpAMP Conversation Broker",
  [string]$CommandName = "/opamp",
  [string]$BotToken = "",
  [string]$SigningSecret = "",
  [string]$AppToken = "",
  [switch]$NonInteractive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $PSCommandPath
$RootDir = Split-Path -Parent $ScriptDir

if ([string]::IsNullOrWhiteSpace($EnvFile)) {
  $EnvFile = Join-Path $RootDir ".env"
}
if ([string]::IsNullOrWhiteSpace($ManifestFile)) {
  $ManifestFile = Join-Path $RootDir "opamp_broker\config\slack_app_manifest.yaml"
}

if (-not $CommandName.StartsWith("/")) {
  throw "Slash command must start with '/': $CommandName"
}

function Set-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )

  $content = @()
  if (Test-Path $Path) {
    $content = Get-Content -Path $Path
  }

  $updated = $false
  for ($idx = 0; $idx -lt $content.Count; $idx++) {
    if ($content[$idx] -match "^$Key=") {
      $content[$idx] = "$Key=$Value"
      $updated = $true
      break
    }
  }

  if (-not $updated) {
    $content += "$Key=$Value"
  }

  Set-Content -Path $Path -Value $content -Encoding UTF8
}

function Get-EnvValue {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key
  )

  if (-not (Test-Path $Path)) {
    return ""
  }

  foreach ($line in Get-Content -Path $Path) {
    if ($line -match "^\s*#") {
      continue
    }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
      continue
    }
    if ($parts[0].Trim() -eq $Key) {
      return $parts[1].Trim()
    }
  }
  return ""
}

function Mask-Secret {
  param(
    [Parameter(Mandatory = $true)][string]$Value
  )

  if ([string]::IsNullOrEmpty($Value)) {
    return "<empty>"
  }
  if ($Value.Length -le 8) {
    return ("*" * $Value.Length)
  }
  return ("{0}...{1}" -f $Value.Substring(0, 4), $Value.Substring($Value.Length - 4))
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $EnvFile) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ManifestFile) | Out-Null

if (-not (Test-Path $EnvFile)) {
  Copy-Item -Path (Join-Path $RootDir ".env.example") -Destination $EnvFile
}

$existingBotToken = Get-EnvValue -Path $EnvFile -Key "SLACK_BOT_TOKEN"
$existingSigningSecret = Get-EnvValue -Path $EnvFile -Key "SLACK_SIGNING_SECRET"
$existingAppToken = Get-EnvValue -Path $EnvFile -Key "SLACK_APP_TOKEN"

Write-Host ""
Write-Host "Current .env Slack values:"
Write-Host "- SLACK_BOT_TOKEN: $(Mask-Secret -Value $existingBotToken)"
Write-Host "- SLACK_SIGNING_SECRET: $(Mask-Secret -Value $existingSigningSecret)"
Write-Host "- SLACK_APP_TOKEN: $(Mask-Secret -Value $existingAppToken)"

if ([string]::IsNullOrWhiteSpace($BotToken)) {
  $BotToken = $existingBotToken
}
if ([string]::IsNullOrWhiteSpace($SigningSecret)) {
  $SigningSecret = $existingSigningSecret
}
if ([string]::IsNullOrWhiteSpace($AppToken)) {
  $AppToken = $existingAppToken
}

if (-not $NonInteractive) {
  if ([string]::IsNullOrWhiteSpace($existingBotToken)) {
    if ([string]::IsNullOrWhiteSpace($BotToken)) {
      $BotToken = Read-Host "SLACK_BOT_TOKEN (xoxb-..., optional now)"
    }
  } else {
    $botPrompt = Read-Host "SLACK_BOT_TOKEN (press Enter to keep existing)"
    if (-not [string]::IsNullOrWhiteSpace($botPrompt)) {
      $BotToken = $botPrompt
    }
  }
  if ([string]::IsNullOrWhiteSpace($existingSigningSecret)) {
    if ([string]::IsNullOrWhiteSpace($SigningSecret)) {
      $SigningSecret = Read-Host "SLACK_SIGNING_SECRET (optional now)"
    }
  } else {
    $signingPrompt = Read-Host "SLACK_SIGNING_SECRET (press Enter to keep existing)"
    if (-not [string]::IsNullOrWhiteSpace($signingPrompt)) {
      $SigningSecret = $signingPrompt
    }
  }
  if ([string]::IsNullOrWhiteSpace($existingAppToken)) {
    if ([string]::IsNullOrWhiteSpace($AppToken)) {
      $AppToken = Read-Host "SLACK_APP_TOKEN (xapp-..., optional now)"
    }
  } else {
    $appPrompt = Read-Host "SLACK_APP_TOKEN (press Enter to keep existing)"
    if (-not [string]::IsNullOrWhiteSpace($appPrompt)) {
      $AppToken = $appPrompt
    }
  }
}

$manifest = @"
display_information:
  name: $AppName
  description: Conversational Slack broker for OpAMP diagnostics and operations.
  background_color: "#1a73e8"
features:
  bot_user:
    display_name: $AppName
    always_online: false
  slash_commands:
    - command: $CommandName
      description: Query OpAMP status, health, config, and diagnostics.
      usage_hint: "[status|health|config|tools] <target>"
      should_escape: false
      url: https://example.invalid/slack/commands
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - channels:history
      - chat:write
      - commands
      - groups:history
      - im:history
      - im:write
      - mpim:history
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
  org_deploy_enabled: false
  socket_mode_enabled: true
  token_rotation_enabled: false
"@
Set-Content -Path $ManifestFile -Value $manifest -Encoding UTF8

if (-not [string]::IsNullOrWhiteSpace($BotToken)) {
  Set-EnvValue -Path $EnvFile -Key "SLACK_BOT_TOKEN" -Value $BotToken
}
if (-not [string]::IsNullOrWhiteSpace($SigningSecret)) {
  Set-EnvValue -Path $EnvFile -Key "SLACK_SIGNING_SECRET" -Value $SigningSecret
}
if (-not [string]::IsNullOrWhiteSpace($AppToken)) {
  Set-EnvValue -Path $EnvFile -Key "SLACK_APP_TOKEN" -Value $AppToken
}
Set-EnvValue -Path $EnvFile -Key "BROKER_CONFIG_PATH" -Value "./opamp_broker/config/broker.example.json"

Write-Host ""
Write-Host "Slack setup files prepared."
Write-Host "- Env file: $EnvFile"
Write-Host "- Manifest: $ManifestFile"
Write-Host ""
Write-Host "Next:"
Write-Host "1. Follow docs/slack_configuration.md to create/install the Slack app from this manifest."
Write-Host "2. If you skipped tokens, rerun this script with -BotToken/-SigningSecret/-AppToken."
Write-Host "3. Start broker: ./scripts/start_broker.ps1"
