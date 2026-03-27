@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set LOG_DIR=%REPO_ROOT%\logs
set LOG_FILE=%LOG_DIR%\opamp_server.log

title OpAMP Server

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

if defined OPAMP_CONFIG_PATH (
  set PROVIDER_CONFIG_PATH=%OPAMP_CONFIG_PATH%
) else (
  set PROVIDER_CONFIG_PATH=%REPO_ROOT%\config\opamp.json
)
echo Using provider config file: %PROVIDER_CONFIG_PATH%
set PYTHONPATH=%REPO_ROOT%\provider\src
python -m pip show protobuf >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\provider\requirements.txt"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"
where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "python -m opamp_provider.server %* 2>&1 | Tee-Object -FilePath '%LOG_FILE%'"
) else (
  python -m opamp_provider.server %* > "%LOG_FILE%" 2>&1
)
