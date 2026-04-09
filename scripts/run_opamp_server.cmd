@echo off
setlocal EnableExtensions EnableDelayedExpansion

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set LOG_DIR=%REPO_ROOT%\logs
set LOG_FILE=%LOG_DIR%\opamp_server.log

title OpAMP Server

set ENABLE_HTTPS=0
set SERVER_ARGS=
set CONFIG_PATH_OVERRIDE=
:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--https" (
  set ENABLE_HTTPS=1
) else if /I "%~1"=="--config-path" (
  set SERVER_ARGS=!SERVER_ARGS! "%~1"
  shift
  if "%~1"=="" goto args_done
  set SERVER_ARGS=!SERVER_ARGS! "%~1"
  set CONFIG_PATH_OVERRIDE=%~1
) else (
  set ARG_VALUE=%~1
  set ARG_PREFIX=!ARG_VALUE:~0,14!
  if /I "!ARG_PREFIX!"=="--config-path=" (
    set CONFIG_PATH_OVERRIDE=!ARG_VALUE:~14!
  )
  set SERVER_ARGS=!SERVER_ARGS! "%~1"
)
shift
goto parse_args
:args_done

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

if defined CONFIG_PATH_OVERRIDE (
  set PROVIDER_CONFIG_PATH=%CONFIG_PATH_OVERRIDE%
) else if defined OPAMP_CONFIG_PATH (
  set PROVIDER_CONFIG_PATH=%OPAMP_CONFIG_PATH%
) else (
  set PROVIDER_CONFIG_PATH=%REPO_ROOT%\config\opamp.json
)
echo Using provider config file: %PROVIDER_CONFIG_PATH%
set OPAMP_CONFIG_PATH=%PROVIDER_CONFIG_PATH%
set PYTHONPATH=%REPO_ROOT%\provider\src
python -m pip show protobuf >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\provider\requirements.txt"
if "%ENABLE_HTTPS%"=="1" (
  set CERT_DIR=%REPO_ROOT%\certs
  set CERT_FILE=!CERT_DIR!\provider-server.pem
  set KEY_FILE=!CERT_DIR!\provider-server-key.pem
  python "%REPO_ROOT%\scripts\generate_self_signed_tls_cert.py" --force --cert-file "!CERT_FILE!" --key-file "!KEY_FILE!" --common-name localhost --dns-name localhost --ip-address 127.0.0.1 --days 365
  if errorlevel 1 exit /b %errorlevel%
  python "%REPO_ROOT%\scripts\ensure_provider_tls_config.py" --config-file "%PROVIDER_CONFIG_PATH%" --cert-file "!CERT_FILE!" --key-file "!KEY_FILE!" --trust-anchor-mode none
  if errorlevel 1 exit /b %errorlevel%
)
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"
where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "python -m opamp_provider.server !SERVER_ARGS! 2>&1 | Tee-Object -FilePath '%LOG_FILE%'"
) else (
  python -m opamp_provider.server !SERVER_ARGS! > "%LOG_FILE%" 2>&1
)
