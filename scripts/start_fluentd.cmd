@echo off
setlocal

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set FLUENTD_CONFIG_PATH=%REPO_ROOT%\consumer\fluentd.conf

if not exist "%FLUENTD_CONFIG_PATH%" (
  echo No fluentd config file found at consumer\fluentd.conf
  exit /b 1
)

where fluentd >nul 2>&1
if not %errorlevel%==0 (
  echo fluentd command not found in PATH
  exit /b 1
)

echo Starting fluentd with config: %FLUENTD_CONFIG_PATH%
fluentd -c "%FLUENTD_CONFIG_PATH%" %*
