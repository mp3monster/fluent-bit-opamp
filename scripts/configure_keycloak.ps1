param(
  [switch]$ReadyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Configures a local Keycloak container for OpAMP JWT bearer token testing.
# This script is idempotent and can be re-run safely.

function Get-Setting {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$DefaultValue
  )

  $value = [Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($value)) {
    return $DefaultValue
  }
  return $value
}

function Require-Command {
  param([Parameter(Mandatory = $true)][string]$CommandName)

  if (-not (Get-Command -Name $CommandName -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $CommandName"
  }
}

function Test-ContainerRuntimeReady {
  param([Parameter(Mandatory = $true)][string]$RuntimeName)

  & $RuntimeName info *> $null
  return ($LASTEXITCODE -eq 0)
}

function Select-ContainerRuntime {
  if (-not [string]::IsNullOrWhiteSpace($script:CONTAINER_RUNTIME)) {
    if ($script:CONTAINER_RUNTIME -notin @("docker", "podman")) {
      throw "Invalid CONTAINER_RUNTIME '$script:CONTAINER_RUNTIME'. Expected 'docker' or 'podman'."
    }

    Require-Command $script:CONTAINER_RUNTIME
    if (Test-ContainerRuntimeReady -RuntimeName $script:CONTAINER_RUNTIME) {
      return
    }
  } else {
    if ((Get-Command -Name docker -ErrorAction SilentlyContinue) -and (Test-ContainerRuntimeReady -RuntimeName "docker")) {
      $script:CONTAINER_RUNTIME = "docker"
      return
    }

    if ((Get-Command -Name podman -ErrorAction SilentlyContinue) -and (Test-ContainerRuntimeReady -RuntimeName "podman")) {
      $script:CONTAINER_RUNTIME = "podman"
      return
    }

    if (Get-Command -Name docker -ErrorAction SilentlyContinue) {
      $script:CONTAINER_RUNTIME = "docker"
    } elseif (Get-Command -Name podman -ErrorAction SilentlyContinue) {
      $script:CONTAINER_RUNTIME = "podman"
    } else {
      throw "Missing required command: docker or podman"
    }
  }

  throw @"
Container runtime is not reachable.
Start Docker Desktop (or Podman service), then retry.
If you use Docker Desktop on Windows, ensure Linux containers are enabled and run:
  docker context use desktop-linux
"@
}

function Invoke-ContainerRuntime {
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  & $script:CONTAINER_RUNTIME @Arguments
}

function Invoke-Kcadm {
  param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
  )

  Invoke-ContainerRuntime exec $script:KEYCLOAK_CONTAINER_NAME /opt/keycloak/bin/kcadm.sh @Arguments
}

function Get-ContainerNames {
  param([switch]$IncludeAll)

  $runtimeArgs = @("ps", "--format", "{{.Names}}")
  if ($IncludeAll) {
    $runtimeArgs = @("ps", "-a", "--format", "{{.Names}}")
  }

  $names = Invoke-ContainerRuntime @runtimeArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to query containers using $script:CONTAINER_RUNTIME."
  }

  return @($names | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Ensure-ContainerRunning {
  $runningNames = Get-ContainerNames
  if ($runningNames -contains $script:KEYCLOAK_CONTAINER_NAME) {
    return
  }

  $allNames = Get-ContainerNames -IncludeAll
  if ($allNames -contains $script:KEYCLOAK_CONTAINER_NAME) {
    Write-Host "Starting existing Keycloak container $script:KEYCLOAK_CONTAINER_NAME..."
    Invoke-ContainerRuntime start $script:KEYCLOAK_CONTAINER_NAME | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to start existing Keycloak container."
    }
    return
  }

  Write-Host "Creating Keycloak container $script:KEYCLOAK_CONTAINER_NAME using $script:CONTAINER_RUNTIME..."
  Invoke-ContainerRuntime run -d `
    --name $script:KEYCLOAK_CONTAINER_NAME `
    -p "${script:KEYCLOAK_HOST_PORT}:8080" `
    -e "KEYCLOAK_ADMIN=$script:KEYCLOAK_ADMIN" `
    -e "KEYCLOAK_ADMIN_PASSWORD=$script:KEYCLOAK_ADMIN_PASSWORD" `
    $script:KEYCLOAK_IMAGE `
    start-dev | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create Keycloak container."
  }
}

function Wait-ForKeycloak {
  Write-Host "Waiting for Keycloak to become ready on $script:KEYCLOAK_EXTERNAL_URL..."
  for ($attempt = 1; $attempt -le 60; $attempt++) {
    & curl.exe -fsS "$script:KEYCLOAK_EXTERNAL_URL/realms/master/.well-known/openid-configuration" | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return
    }
    Start-Sleep -Seconds 2
  }
  throw "Keycloak did not become ready in time."
}

function Create-OrUpdateRealm {
  Invoke-Kcadm get "realms/$script:KEYCLOAK_REALM" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating realm $script:KEYCLOAK_REALM..."
    Invoke-Kcadm create realms -s "realm=$script:KEYCLOAK_REALM" -s enabled=true | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create realm $script:KEYCLOAK_REALM."
    }
  } else {
    Write-Host "Realm $script:KEYCLOAK_REALM already exists."
  }
}

function Create-OrUpdateClient {
  $clientUuid = ""
  $clientQueryJson = Invoke-Kcadm get clients -r $script:KEYCLOAK_REALM -q "clientId=$script:KEYCLOAK_CLIENT_ID" --fields id,clientId --format json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to query client $script:KEYCLOAK_CLIENT_ID."
  }

  if (-not [string]::IsNullOrWhiteSpace(($clientQueryJson | Out-String))) {
    $clients = @($clientQueryJson | ConvertFrom-Json)
    if ($clients.Count -gt 0) {
      $clientUuid = [string]$clients[0].id
    }
  }

  if ([string]::IsNullOrWhiteSpace($clientUuid)) {
    Write-Host "Creating client $script:KEYCLOAK_CLIENT_ID..."
    $clientUuid = (Invoke-Kcadm create clients -r $script:KEYCLOAK_REALM `
      -s "clientId=$script:KEYCLOAK_CLIENT_ID" `
      -s enabled=true `
      -s protocol=openid-connect `
      -s publicClient=false `
      -s directAccessGrantsEnabled=true `
      -s standardFlowEnabled=true `
      -s serviceAccountsEnabled=true `
      -s "secret=$script:KEYCLOAK_CLIENT_SECRET" `
      -i | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create client $script:KEYCLOAK_CLIENT_ID."
    }
  } else {
    Write-Host "Client $script:KEYCLOAK_CLIENT_ID already exists; updating auth settings."
  }

  if ([string]::IsNullOrWhiteSpace($clientUuid)) {
    throw "Could not determine client ID for $script:KEYCLOAK_CLIENT_ID."
  }

  Invoke-Kcadm update "clients/$clientUuid" -r $script:KEYCLOAK_REALM `
    -s enabled=true `
    -s protocol=openid-connect `
    -s publicClient=false `
    -s directAccessGrantsEnabled=true `
    -s standardFlowEnabled=true `
    -s serviceAccountsEnabled=true `
    -s "secret=$script:KEYCLOAK_CLIENT_SECRET" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update client $script:KEYCLOAK_CLIENT_ID."
  }
}

function Create-OrUpdateUser {
  $userUuid = ""
  $userQueryJson = Invoke-Kcadm get users -r $script:KEYCLOAK_REALM -q "username=$script:KEYCLOAK_USER" --fields id,username --format json
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to query user $script:KEYCLOAK_USER."
  }

  if (-not [string]::IsNullOrWhiteSpace(($userQueryJson | Out-String))) {
    $users = @($userQueryJson | ConvertFrom-Json)
    if ($users.Count -gt 0) {
      $userUuid = [string]$users[0].id
    }
  }

  if ([string]::IsNullOrWhiteSpace($userUuid)) {
    Write-Host "Creating user $script:KEYCLOAK_USER..."
    Invoke-Kcadm create users -r $script:KEYCLOAK_REALM -s "username=$script:KEYCLOAK_USER" -s enabled=true | Out-Null
    if ($LASTEXITCODE -ne 0) {
      throw "Failed to create user $script:KEYCLOAK_USER."
    }
  } else {
    Write-Host "User $script:KEYCLOAK_USER already exists; refreshing password."
  }

  Invoke-Kcadm set-password -r $script:KEYCLOAK_REALM `
    --username $script:KEYCLOAK_USER `
    --new-password $script:KEYCLOAK_USER_PASSWORD `
    --temporary false | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to update password for user $script:KEYCLOAK_USER."
  }
}

$script:KEYCLOAK_CONTAINER_NAME = Get-Setting -Name "KEYCLOAK_CONTAINER_NAME" -DefaultValue "opamp-keycloak"
$script:KEYCLOAK_IMAGE = Get-Setting -Name "KEYCLOAK_IMAGE" -DefaultValue "quay.io/keycloak/keycloak:26.2"
$script:KEYCLOAK_HOST_PORT = Get-Setting -Name "KEYCLOAK_HOST_PORT" -DefaultValue "8081"
$script:KEYCLOAK_ADMIN = Get-Setting -Name "KEYCLOAK_ADMIN" -DefaultValue "admin"
$script:KEYCLOAK_ADMIN_PASSWORD = Get-Setting -Name "KEYCLOAK_ADMIN_PASSWORD" -DefaultValue "admin"
$script:KEYCLOAK_REALM = Get-Setting -Name "KEYCLOAK_REALM" -DefaultValue "opamp"
$script:KEYCLOAK_CLIENT_ID = Get-Setting -Name "KEYCLOAK_CLIENT_ID" -DefaultValue "opamp-mcp"
$script:KEYCLOAK_CLIENT_SECRET = Get-Setting -Name "KEYCLOAK_CLIENT_SECRET" -DefaultValue "opamp-mcp-secret"
$script:KEYCLOAK_USER = Get-Setting -Name "KEYCLOAK_USER" -DefaultValue "opamp-user"
$script:KEYCLOAK_USER_PASSWORD = Get-Setting -Name "KEYCLOAK_USER_PASSWORD" -DefaultValue "opamp-password"
$script:CONTAINER_RUNTIME = Get-Setting -Name "CONTAINER_RUNTIME" -DefaultValue ""
$script:KEYCLOAK_INTERNAL_URL = "http://127.0.0.1:8080"
$script:KEYCLOAK_EXTERNAL_URL = "http://127.0.0.1:$script:KEYCLOAK_HOST_PORT"

Select-ContainerRuntime
Require-Command curl.exe

Ensure-ContainerRunning
Wait-ForKeycloak

if ($ReadyOnly) {
  Write-Host "Keycloak container is ready on $script:KEYCLOAK_EXTERNAL_URL (runtime: $script:CONTAINER_RUNTIME)."
  exit 0
}

Write-Host "Authenticating Keycloak admin client..."
Invoke-Kcadm config credentials `
  --server $script:KEYCLOAK_INTERNAL_URL `
  --realm master `
  --user $script:KEYCLOAK_ADMIN `
  --password $script:KEYCLOAK_ADMIN_PASSWORD | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Failed to authenticate with Keycloak admin credentials."
}

Create-OrUpdateRealm
Create-OrUpdateClient
Create-OrUpdateUser

Write-Host ""
Write-Host "Keycloak setup complete."
Write-Host "Runtime: $script:CONTAINER_RUNTIME"
Write-Host "Realm: $script:KEYCLOAK_REALM"
Write-Host "Client ID: $script:KEYCLOAK_CLIENT_ID"
Write-Host "Client Secret: $script:KEYCLOAK_CLIENT_SECRET"
Write-Host "User: $script:KEYCLOAK_USER"
Write-Host "Issuer URL: $script:KEYCLOAK_EXTERNAL_URL/realms/$script:KEYCLOAK_REALM"
Write-Host "JWKS URL: $script:KEYCLOAK_EXTERNAL_URL/realms/$script:KEYCLOAK_REALM/protocol/openid-connect/certs"
Write-Host ""
Write-Host "Example provider auth env (PowerShell):"
Write-Host "  `$env:OPAMP_AUTH_MODE='jwt'"
Write-Host "  `$env:OPAMP_AUTH_JWT_ISSUER='$script:KEYCLOAK_EXTERNAL_URL/realms/$script:KEYCLOAK_REALM'"
Write-Host "  `$env:OPAMP_AUTH_JWT_AUDIENCE='$script:KEYCLOAK_CLIENT_ID'"
Write-Host ""
Write-Host "Example token request:"
Write-Host "  curl.exe -s -X POST `"
Write-Host "    $script:KEYCLOAK_EXTERNAL_URL/realms/$script:KEYCLOAK_REALM/protocol/openid-connect/token `"
Write-Host "    -d grant_type=password `"
Write-Host "    -d client_id=$script:KEYCLOAK_CLIENT_ID `"
Write-Host "    -d client_secret=$script:KEYCLOAK_CLIENT_SECRET `"
Write-Host "    -d username=$script:KEYCLOAK_USER `"
Write-Host "    -d password=$script:KEYCLOAK_USER_PASSWORD"
