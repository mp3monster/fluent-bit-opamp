@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%package.ps1"
set "PS_CMD="

where pwsh >nul 2>&1
if not errorlevel 1 set "PS_CMD=pwsh"

if not defined PS_CMD (
  where powershell >nul 2>&1
  if not errorlevel 1 set "PS_CMD=powershell"
)

if not defined PS_CMD (
  echo Could not find PowerShell runtime. Install PowerShell 7 ^(pwsh^) or Windows PowerShell.
  exit /b 1
)

"%PS_CMD%" -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
exit /b %ERRORLEVEL%
