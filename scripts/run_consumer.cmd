@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

set CONFIG_PATH=%REPO_ROOT%\tests\opamp.json
set FLUENTBIT_PATH=%REPO_ROOT%\tests\fluent-bit.yaml
if not exist "%CONFIG_PATH%" set CONFIG_PATH=%REPO_ROOT%\consumer\opamp.json
if not exist "%FLUENTBIT_PATH%" set FLUENTBIT_PATH=%REPO_ROOT%\consumer\fluent-bit.yaml

set PYTHONPATH=%REPO_ROOT%\consumer\src
set OPAMP_CONFIG_PATH=%CONFIG_PATH%
python -m pip show httpx >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\consumer\requirements.txt"
python -m opamp_consumer.client --config-path "%CONFIG_PATH%" --fluentbit-config-path "%FLUENTBIT_PATH%" %*
