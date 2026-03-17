@echo off
setlocal

set HOST=%1
if "%HOST%"=="" set HOST=127.0.0.1
set PORT=%2
if "%PORT%"=="" set PORT=8080

where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "Invoke-RestMethod -Method Post -Uri 'http://%HOST%:%PORT%/api/shutdown' -ContentType 'application/json' -Body '{\"confirm\":true}'"
) else (
  echo PowerShell is required to send the shutdown request.
  exit /b 1
)
