@echo off
setlocal

where powershell >nul 2>&1
if %errorlevel%==0 (
  powershell -NoProfile -Command "Get-Process -Name fluent-bit -ErrorAction SilentlyContinue | Stop-Process"
  exit /b 0
)

taskkill /IM fluent-bit.exe /T >nul 2>&1
if %errorlevel%==0 (
  echo Sent termination to fluent-bit.
) else (
  echo No fluent-bit process found.
)
