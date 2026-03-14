@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

set PYTHONPATH=%REPO_ROOT%\provider\src
python -m pip show protobuf >nul 2>&1 || python -m pip install -r "%REPO_ROOT%\provider\requirements.txt"
python -m opamp_provider.server %*
