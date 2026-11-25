@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build Portable Package

echo.
echo ========================================
echo   Build portable package (one-dir)
echo ========================================
echo.

set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    for /f "delims=" %%I in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%I"
)
if not defined PY goto :no_python

echo [OK] Python: %PY%
"%PY%" "%~dp0build.py"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [ERROR] Build failed. See messages above.
echo.
pause
endlocal
exit /b %RC%

:no_python
echo [ERROR] No usable Python found. Install Python 3.10+ first.
pause
exit /b 1
