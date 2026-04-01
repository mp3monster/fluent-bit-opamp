@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set LOG_DIR=%REPO_ROOT%\logs
set LOG_FILE=%LOG_DIR%\supervisor_fluentd.log

title OpAMP Supervisor (Fluentd)

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

set CONFIG_PATH=%REPO_ROOT%\consumer\opamp-fluentd.json
set FLUENTD_PATH=%REPO_ROOT%\consumer\fluentd.conf
if not exist "%CONFIG_PATH%" set CONFIG_PATH=%REPO_ROOT%\tests\opamp.json
if not exist "%CONFIG_PATH%" set CONFIG_PATH=%REPO_ROOT%\config\opamp.json

set PYTHONPATH=%REPO_ROOT%\consumer\src
set OPAMP_CONFIG_PATH=%CONFIG_PATH%
echo Using consumer config file: %CONFIG_PATH%
python -m pip show httpx >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\consumer\requirements.txt"
if exist "%cd%\OpAMPSupervisor.signal" del /f /q "%cd%\OpAMPSupervisor.signal"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%" >nul 2>&1
where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "python -m opamp_consumer.fluentd_client --config-path '%CONFIG_PATH%' --fluentd-config-path '%FLUENTD_PATH%' %* 2>&1 | Tee-Object -FilePath '%LOG_FILE%'"
) else (
  python -m opamp_consumer.fluentd_client --config-path "%CONFIG_PATH%" --fluentd-config-path "%FLUENTD_PATH%" %* > "%LOG_FILE%" 2>&1
)
