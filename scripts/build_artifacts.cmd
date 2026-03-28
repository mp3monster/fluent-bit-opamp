@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set DIST_ROOT=%REPO_ROOT%\dist
set PROVIDER_DIST=%DIST_ROOT%\provider
set CONSUMER_DIST=%DIST_ROOT%\consumer

if exist "%REPO_ROOT%\.venv\Scripts\activate.bat" call "%REPO_ROOT%\.venv\Scripts\activate.bat"

echo Ensuring Python build tooling is available...
python -m pip show build >nul 2>&1 || python -m pip install build

echo Preparing artifact directories...
if not exist "%PROVIDER_DIST%" mkdir "%PROVIDER_DIST%"
if not exist "%CONSUMER_DIST%" mkdir "%CONSUMER_DIST%"
del /q "%PROVIDER_DIST%\*" >nul 2>&1
del /q "%CONSUMER_DIST%\*" >nul 2>&1

echo Building provider artifacts...
python -m build --sdist --wheel --outdir "%PROVIDER_DIST%" "%REPO_ROOT%\provider"
if errorlevel 1 exit /b 1

echo Building consumer artifacts...
python -m build --sdist --wheel --outdir "%CONSUMER_DIST%" "%REPO_ROOT%\consumer"
if errorlevel 1 exit /b 1

echo Build complete.
echo Provider artifacts:
dir /b "%PROVIDER_DIST%"
echo Consumer artifacts:
dir /b "%CONSUMER_DIST%"

