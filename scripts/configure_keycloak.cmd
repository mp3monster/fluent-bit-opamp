@echo off
setlocal EnableExtensions

rem Configures a local Keycloak container for OpAMP JWT bearer token testing.
rem This script is idempotent and can be re-run safely.

if not defined KEYCLOAK_CONTAINER_NAME set "KEYCLOAK_CONTAINER_NAME=opamp-keycloak"
if not defined KEYCLOAK_IMAGE set "KEYCLOAK_IMAGE=quay.io/keycloak/keycloak:26.2"
if not defined KEYCLOAK_HOST_PORT set "KEYCLOAK_HOST_PORT=8081"
if not defined KEYCLOAK_ADMIN set "KEYCLOAK_ADMIN=admin"
if not defined KEYCLOAK_ADMIN_PASSWORD set "KEYCLOAK_ADMIN_PASSWORD=admin"
if not defined KEYCLOAK_REALM set "KEYCLOAK_REALM=opamp"
if not defined KEYCLOAK_CLIENT_ID set "KEYCLOAK_CLIENT_ID=opamp-mcp"
if not defined KEYCLOAK_CLIENT_SECRET set "KEYCLOAK_CLIENT_SECRET=opamp-mcp-secret"
if not defined KEYCLOAK_USER set "KEYCLOAK_USER=opamp-user"
if not defined KEYCLOAK_USER_PASSWORD set "KEYCLOAK_USER_PASSWORD=opamp-password"

set "KEYCLOAK_INTERNAL_URL=http://127.0.0.1:8080"
set "KEYCLOAK_EXTERNAL_URL=http://127.0.0.1:%KEYCLOAK_HOST_PORT%"
if not defined CONTAINER_RUNTIME set "CONTAINER_RUNTIME="
set "PYTHON_EXE="
set "READY_ONLY=0"

if not "%~2"=="" (
  call :print_usage
  exit /b 1
)
if /i "%~1"=="--ready-only" (
  set "READY_ONLY=1"
) else if /i "%~1"=="--help" (
  call :print_usage
  exit /b 0
) else if /i "%~1"=="-h" (
  call :print_usage
  exit /b 0
) else if not "%~1"=="" (
  echo Unknown argument: %~1
  call :print_usage
  exit /b 1
)

call :select_container_runtime || exit /b 1
call :require_command curl || exit /b 1
if "%READY_ONLY%"=="0" (
  where python >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON_EXE=python"
  ) else (
    where py >nul 2>&1
    if not errorlevel 1 (
      set "PYTHON_EXE=py"
    ) else (
      echo Missing required command: python ^(or py launcher^)
      exit /b 1
    )
  )
)

call :ensure_container_running || exit /b 1
call :wait_for_keycloak || exit /b 1

if "%READY_ONLY%"=="1" (
  echo Keycloak container is ready on %KEYCLOAK_EXTERNAL_URL% ^(runtime: %CONTAINER_RUNTIME%^).
  exit /b 0
)

echo Authenticating Keycloak admin client...
%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh config credentials ^
  --server "%KEYCLOAK_INTERNAL_URL%" ^
  --realm master ^
  --user "%KEYCLOAK_ADMIN%" ^
  --password "%KEYCLOAK_ADMIN_PASSWORD%" >nul
if errorlevel 1 (
  echo Failed to authenticate with Keycloak admin credentials.
  exit /b 1
)

call :create_or_update_realm || exit /b 1
call :create_or_update_client || exit /b 1
call :create_or_update_user || exit /b 1

echo.
echo Keycloak setup complete.
echo Runtime: %CONTAINER_RUNTIME%
echo Realm: %KEYCLOAK_REALM%
echo Client ID: %KEYCLOAK_CLIENT_ID%
echo Client Secret: %KEYCLOAK_CLIENT_SECRET%
echo User: %KEYCLOAK_USER%
echo Issuer URL: %KEYCLOAK_EXTERNAL_URL%/realms/%KEYCLOAK_REALM%
echo JWKS URL: %KEYCLOAK_EXTERNAL_URL%/realms/%KEYCLOAK_REALM%/protocol/openid-connect/certs
echo.
echo Example provider auth env (PowerShell):
echo   $env:OPAMP_AUTH_MODE='jwt'
echo   $env:OPAMP_AUTH_JWT_ISSUER='%KEYCLOAK_EXTERNAL_URL%/realms/%KEYCLOAK_REALM%'
echo   $env:OPAMP_AUTH_JWT_AUDIENCE='%KEYCLOAK_CLIENT_ID%'
echo.
echo Example provider auth env (cmd):
echo   set OPAMP_AUTH_MODE=jwt
echo   set OPAMP_AUTH_JWT_ISSUER=%KEYCLOAK_EXTERNAL_URL%/realms/%KEYCLOAK_REALM%
echo   set OPAMP_AUTH_JWT_AUDIENCE=%KEYCLOAK_CLIENT_ID%
echo.
echo Example token request:
echo   curl -s -X POST ^
echo     %KEYCLOAK_EXTERNAL_URL%/realms/%KEYCLOAK_REALM%/protocol/openid-connect/token ^
echo     -d grant_type=password ^
echo     -d client_id=%KEYCLOAK_CLIENT_ID% ^
echo     -d client_secret=%KEYCLOAK_CLIENT_SECRET% ^
echo     -d username=%KEYCLOAK_USER% ^
echo     -d password=%KEYCLOAK_USER_PASSWORD%
exit /b 0

:print_usage
echo Usage: %~nx0 [--ready-only]
echo Container runtime can be set with CONTAINER_RUNTIME=docker^|podman
exit /b 0

:require_command
where "%~1" >nul 2>&1
if errorlevel 1 (
  echo Missing required command: %~1
  exit /b 1
)
exit /b 0

:check_runtime_ready
%~1 info >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:select_container_runtime
if /i not "%CONTAINER_RUNTIME%"=="" (
  if /i not "%CONTAINER_RUNTIME%"=="docker" if /i not "%CONTAINER_RUNTIME%"=="podman" (
    echo Invalid CONTAINER_RUNTIME "%CONTAINER_RUNTIME%". Expected docker or podman.
    exit /b 1
  )
  call :require_command %CONTAINER_RUNTIME% || exit /b 1
  call :check_runtime_ready %CONTAINER_RUNTIME%
  if not errorlevel 1 exit /b 0
) else (
  where docker >nul 2>&1
  if not errorlevel 1 (
    call :check_runtime_ready docker
    if not errorlevel 1 (
      set "CONTAINER_RUNTIME=docker"
      exit /b 0
    )
  )
  where podman >nul 2>&1
  if not errorlevel 1 (
    call :check_runtime_ready podman
    if not errorlevel 1 (
      set "CONTAINER_RUNTIME=podman"
      exit /b 0
    )
  )
  where docker >nul 2>&1
  if not errorlevel 1 (
    set "CONTAINER_RUNTIME=docker"
  ) else (
    where podman >nul 2>&1
    if not errorlevel 1 (
      set "CONTAINER_RUNTIME=podman"
    ) else (
      echo Missing required command: docker or podman
      exit /b 1
    )
  )
)
echo Container runtime is not reachable.
echo Start Docker Desktop ^(or Podman service^), then retry.
echo If you use Docker Desktop on Windows, ensure Linux containers are enabled and run:
echo   docker context use desktop-linux
exit /b 1

:ensure_container_running
%CONTAINER_RUNTIME% ps --format "{{.Names}}" | findstr /x /c:"%KEYCLOAK_CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 exit /b 0

%CONTAINER_RUNTIME% ps -a --format "{{.Names}}" | findstr /x /c:"%KEYCLOAK_CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo Starting existing Keycloak container %KEYCLOAK_CONTAINER_NAME%...
  %CONTAINER_RUNTIME% start "%KEYCLOAK_CONTAINER_NAME%" >nul
  if errorlevel 1 exit /b 1
  exit /b 0
)

echo Creating Keycloak container %KEYCLOAK_CONTAINER_NAME% using %CONTAINER_RUNTIME%...
%CONTAINER_RUNTIME% run -d ^
  --name "%KEYCLOAK_CONTAINER_NAME%" ^
  -p "%KEYCLOAK_HOST_PORT%:8080" ^
  -e KEYCLOAK_ADMIN="%KEYCLOAK_ADMIN%" ^
  -e KEYCLOAK_ADMIN_PASSWORD="%KEYCLOAK_ADMIN_PASSWORD%" ^
  "%KEYCLOAK_IMAGE%" ^
  start-dev >nul
if errorlevel 1 exit /b 1
exit /b 0

:wait_for_keycloak
echo Waiting for Keycloak to become ready on %KEYCLOAK_EXTERNAL_URL%...
for /l %%A in (1,1,60) do (
  curl -fsS "%KEYCLOAK_EXTERNAL_URL%/realms/master/.well-known/openid-configuration" >nul 2>&1
  if not errorlevel 1 exit /b 0
  timeout /t 2 /nobreak >nul
)
echo Keycloak did not become ready in time.
exit /b 1

:create_or_update_realm
%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get "realms/%KEYCLOAK_REALM%" >nul 2>&1
if errorlevel 1 (
  echo Creating realm %KEYCLOAK_REALM%...
  %CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create realms -s "realm=%KEYCLOAK_REALM%" -s enabled=true >nul
  if errorlevel 1 exit /b 1
) else (
  echo Realm %KEYCLOAK_REALM% already exists.
)
exit /b 0

:create_or_update_client
set "CLIENT_UUID="
set "TMP_CLIENT_JSON=%TEMP%\opamp_keycloak_client_%RANDOM%%RANDOM%.json"
%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get clients -r "%KEYCLOAK_REALM%" -q "clientId=%KEYCLOAK_CLIENT_ID%" --fields id,clientId --format json > "%TMP_CLIENT_JSON%"
if errorlevel 1 (
  del /q "%TMP_CLIENT_JSON%" >nul 2>&1
  exit /b 1
)
for /f "usebackq delims=" %%I in (`%PYTHON_EXE% -c "import json,sys,pathlib; data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8') or '[]'); print(data[0].get('id','') if data else '')" "%TMP_CLIENT_JSON%"`) do set "CLIENT_UUID=%%I"
del /q "%TMP_CLIENT_JSON%" >nul 2>&1

if "%CLIENT_UUID%"=="" (
  echo Creating client %KEYCLOAK_CLIENT_ID%...
  for /f "usebackq delims=" %%I in (`%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create clients -r "%KEYCLOAK_REALM%" -s "clientId=%KEYCLOAK_CLIENT_ID%" -s enabled=true -s protocol=openid-connect -s publicClient=false -s directAccessGrantsEnabled=true -s standardFlowEnabled=true -s serviceAccountsEnabled=true -s "secret=%KEYCLOAK_CLIENT_SECRET%" -i`) do set "CLIENT_UUID=%%I"
) else (
  echo Client %KEYCLOAK_CLIENT_ID% already exists; updating auth settings.
)

if "%CLIENT_UUID%"=="" exit /b 1

%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh update "clients/%CLIENT_UUID%" -r "%KEYCLOAK_REALM%" ^
  -s enabled=true ^
  -s protocol=openid-connect ^
  -s publicClient=false ^
  -s directAccessGrantsEnabled=true ^
  -s standardFlowEnabled=true ^
  -s serviceAccountsEnabled=true ^
  -s "secret=%KEYCLOAK_CLIENT_SECRET%" >nul
if errorlevel 1 exit /b 1
exit /b 0

:create_or_update_user
set "USER_UUID="
set "TMP_USER_JSON=%TEMP%\opamp_keycloak_user_%RANDOM%%RANDOM%.json"
%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get users -r "%KEYCLOAK_REALM%" -q "username=%KEYCLOAK_USER%" --fields id,username --format json > "%TMP_USER_JSON%"
if errorlevel 1 (
  del /q "%TMP_USER_JSON%" >nul 2>&1
  exit /b 1
)
for /f "usebackq delims=" %%I in (`%PYTHON_EXE% -c "import json,sys,pathlib; data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8') or '[]'); print(data[0].get('id','') if data else '')" "%TMP_USER_JSON%"`) do set "USER_UUID=%%I"
del /q "%TMP_USER_JSON%" >nul 2>&1

if "%USER_UUID%"=="" (
  echo Creating user %KEYCLOAK_USER%...
  %CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create users -r "%KEYCLOAK_REALM%" -s "username=%KEYCLOAK_USER%" -s enabled=true >nul
  if errorlevel 1 exit /b 1
) else (
  echo User %KEYCLOAK_USER% already exists; refreshing password.
)

%CONTAINER_RUNTIME% exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh set-password -r "%KEYCLOAK_REALM%" --username "%KEYCLOAK_USER%" --new-password "%KEYCLOAK_USER_PASSWORD%" --temporary false >nul
if errorlevel 1 exit /b 1
exit /b 0
