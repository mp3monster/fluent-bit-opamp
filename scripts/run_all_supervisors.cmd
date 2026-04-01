@echo off
setlocal EnableExtensions

set SCRIPT_DIR=%~dp0

set FOUND_ANY=0
for /f "delims=" %%F in ('dir /b /a:-d "%SCRIPT_DIR%run_*_supervisor.cmd" 2^>nul') do (
  if /I not "%%~F"=="run_all_supervisors.cmd" (
    set FOUND_ANY=1
    echo Launching %SCRIPT_DIR%%%~F
    start "OpAMP %%~nF" cmd /k call "%SCRIPT_DIR%%%~F"
  )
)

if "%FOUND_ANY%"=="0" (
  echo No run_*_supervisor.cmd scripts found in %SCRIPT_DIR%
)

endlocal
