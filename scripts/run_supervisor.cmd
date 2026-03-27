@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set LOG_DIR=%REPO_ROOT%\logs
set LOG_FILE=%LOG_DIR%\supervisor.log

title OpAMP Supervisor

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

set CONFIG_PATH=%REPO_ROOT%\tests\opamp.json
set FLUENTBIT_PATH=%REPO_ROOT%\tests\fluent-bit.yaml
if not exist "%CONFIG_PATH%" set CONFIG_PATH=%REPO_ROOT%\consumer\opamp.json
if not exist "%FLUENTBIT_PATH%" set FLUENTBIT_PATH=%REPO_ROOT%\consumer\fluent-bit.yaml

set PYTHONPATH=%REPO_ROOT%\consumer\src
set OPAMP_CONFIG_PATH=%CONFIG_PATH%
echo Using consumer config file: %CONFIG_PATH%
python -m pip show httpx >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\consumer\requirements.txt"
if exist "%cd%\OpAMPSupervisor.signal" del /f /q "%cd%\OpAMPSupervisor.signal"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if exist "%LOG_FILE%" del /f /q "%LOG_FILE%"
where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "python -m opamp_consumer.client --config-path '%CONFIG_PATH%' --fluentbit-config-path '%FLUENTBIT_PATH%' %* 2>&1 | Tee-Object -FilePath '%LOG_FILE%'"
) else (
  python -m opamp_consumer.client --config-path "%CONFIG_PATH%" --fluentbit-config-path "%FLUENTBIT_PATH%" %* > "%LOG_FILE%" 2>&1
)
