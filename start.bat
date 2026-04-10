@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0" || (
  echo ERROR: Failed to change directory to %~dp0
  pause
  exit /b 1
)

where py >nul 2>&1
if !errorlevel! equ 0 (
  echo Found py launcher. Starting app...
  py -3 start.py
  set EXIT_CODE=!errorlevel!
) else (
  where python >nul 2>&1
  if !errorlevel! equ 0 (
    echo py launcher not found. Using python executable...
    python start.py
    set EXIT_CODE=!errorlevel!
  ) else (
    echo ERROR: Python was not found in PATH.
    echo Install Python 3 and enable "Add python.exe to PATH".
    set EXIT_CODE=1
  )
)

if !EXIT_CODE! neq 0 (
  echo.
  echo Setup failed with exit code !EXIT_CODE!.
  echo Troubleshooting:
  echo 1. Run from terminal: python --version
  echo 2. Run from terminal: python start.py
  echo 3. If needed, reinstall Python 3.x and add it to PATH.
  pause
)

exit /b !EXIT_CODE!
