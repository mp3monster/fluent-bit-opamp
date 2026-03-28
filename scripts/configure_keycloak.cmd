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
set "PYTHON_EXE="

call :require_command docker || exit /b 1
call :require_command curl || exit /b 1
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

call :ensure_container_running || exit /b 1
call :wait_for_keycloak || exit /b 1

echo Authenticating Keycloak admin client...
docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh config credentials ^
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

:require_command
where "%~1" >nul 2>&1
if errorlevel 1 (
  echo Missing required command: %~1
  exit /b 1
)
exit /b 0

:ensure_container_running
docker ps --format "{{.Names}}" | findstr /x /c:"%KEYCLOAK_CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 exit /b 0

docker ps -a --format "{{.Names}}" | findstr /x /c:"%KEYCLOAK_CONTAINER_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo Starting existing Keycloak container %KEYCLOAK_CONTAINER_NAME%...
  docker start "%KEYCLOAK_CONTAINER_NAME%" >nul
  if errorlevel 1 exit /b 1
  exit /b 0
)

echo Creating Keycloak container %KEYCLOAK_CONTAINER_NAME%...
docker run -d ^
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
docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get "realms/%KEYCLOAK_REALM%" >nul 2>&1
if errorlevel 1 (
  echo Creating realm %KEYCLOAK_REALM%...
  docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create realms -s "realm=%KEYCLOAK_REALM%" -s enabled=true >nul
  if errorlevel 1 exit /b 1
) else (
  echo Realm %KEYCLOAK_REALM% already exists.
)
exit /b 0

:create_or_update_client
set "CLIENT_UUID="
set "TMP_CLIENT_JSON=%TEMP%\opamp_keycloak_client_%RANDOM%%RANDOM%.json"
docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get clients -r "%KEYCLOAK_REALM%" -q "clientId=%KEYCLOAK_CLIENT_ID%" --fields id,clientId --format json > "%TMP_CLIENT_JSON%"
if errorlevel 1 (
  del /q "%TMP_CLIENT_JSON%" >nul 2>&1
  exit /b 1
)
for /f "usebackq delims=" %%I in (`%PYTHON_EXE% -c "import json,sys,pathlib; data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8') or '[]'); print(data[0].get('id','') if data else '')" "%TMP_CLIENT_JSON%"`) do set "CLIENT_UUID=%%I"
del /q "%TMP_CLIENT_JSON%" >nul 2>&1

if "%CLIENT_UUID%"=="" (
  echo Creating client %KEYCLOAK_CLIENT_ID%...
  for /f "usebackq delims=" %%I in (`docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create clients -r "%KEYCLOAK_REALM%" -s "clientId=%KEYCLOAK_CLIENT_ID%" -s enabled=true -s protocol=openid-connect -s publicClient=false -s directAccessGrantsEnabled=true -s standardFlowEnabled=true -s serviceAccountsEnabled=true -s "secret=%KEYCLOAK_CLIENT_SECRET%" -i`) do set "CLIENT_UUID=%%I"
) else (
  echo Client %KEYCLOAK_CLIENT_ID% already exists; updating auth settings.
)

if "%CLIENT_UUID%"=="" exit /b 1

docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh update "clients/%CLIENT_UUID%" -r "%KEYCLOAK_REALM%" ^
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
docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh get users -r "%KEYCLOAK_REALM%" -q "username=%KEYCLOAK_USER%" --fields id,username --format json > "%TMP_USER_JSON%"
if errorlevel 1 (
  del /q "%TMP_USER_JSON%" >nul 2>&1
  exit /b 1
)
for /f "usebackq delims=" %%I in (`%PYTHON_EXE% -c "import json,sys,pathlib; data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8') or '[]'); print(data[0].get('id','') if data else '')" "%TMP_USER_JSON%"`) do set "USER_UUID=%%I"
del /q "%TMP_USER_JSON%" >nul 2>&1

if "%USER_UUID%"=="" (
  echo Creating user %KEYCLOAK_USER%...
  docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh create users -r "%KEYCLOAK_REALM%" -s "username=%KEYCLOAK_USER%" -s enabled=true >nul
  if errorlevel 1 exit /b 1
) else (
  echo User %KEYCLOAK_USER% already exists; refreshing password.
)

docker exec "%KEYCLOAK_CONTAINER_NAME%" /opt/keycloak/bin/kcadm.sh set-password -r "%KEYCLOAK_REALM%" --username "%KEYCLOAK_USER%" --new-password "%KEYCLOAK_USER_PASSWORD%" --temporary false >nul
if errorlevel 1 exit /b 1
exit /b 0
