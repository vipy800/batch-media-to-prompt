@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Media Reverse - Launcher

echo.
echo ========================================
echo   Media Reverse - Launcher
echo ========================================
echo.

REM ================= 1. Find Python =================
set "BASEPY="
set "PY="

REM 1.1 Project venv (preferred)
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

REM 1.2 python on PATH
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

REM 1.3 py launcher
if not defined PY (
    for /f "delims=" %%I in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%I"
)

REM 1.4 Portable Python shipped with the project
if not defined PY (
    if exist "%~dp0python\python.exe" (
        "%~dp0python\python.exe" -c "import sys" >nul 2>&1
        if not errorlevel 1 set "PY=%~dp0python\python.exe"
    )
)

REM 1.5 Common install locations
if not defined PY (
    for %%P in (
        "C:\Python\python.exe"
        "C:\Python312\python.exe"
        "C:\Python311\python.exe"
        "C:\Python310\python.exe"
        "C:\Python39\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python39\python.exe"
        "C:\ProgramData\Anaconda3\python.exe"
        "%USERPROFILE%\anaconda3\python.exe"
        "%USERPROFILE%\miniconda3\python.exe"
    ) do (
        if not defined PY if exist "%%~P" (
            "%%~P" -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PY=%%~P"
        )
    )
)

if not defined PY goto :no_python
echo [OK] Python found: %PY%
echo.

REM ================= 2. Prepare project environment =================
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
    goto :check_deps
)

echo First run: creating a private environment for this project (once only)...
"%PY%" -m venv "%~dp0.venv"
if errorlevel 1 (
    echo [WARN] Could not create venv, falling back to system Python.
    goto :check_deps
)
set "PY=%~dp0.venv\Scripts\python.exe"
echo [OK] Environment created

:check_deps
"%PY%" -c "import fastapi, uvicorn, jinja2, multipart, cv2, PIL, dotenv, requests, numpy" >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo Installing dependencies (first time may take a few minutes)...
if exist "requirements.txt" (
    "%PY%" -m pip install -r "requirements.txt" --disable-pip-version-check
) else (
    "%PY%" -m pip install fastapi uvicorn jinja2 python-multipart opencv-python pillow python-dotenv requests numpy --disable-pip-version-check
)

echo.
echo Re-checking dependencies...
"%PY%" -c "import fastapi, uvicorn, jinja2, multipart, cv2, PIL, dotenv, requests, numpy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Dependency installation failed. Check your network and retry.
    echo         Manual command: "%PY%" -m pip install -r requirements.txt
    goto :end
)
echo [OK] Dependencies ready

:deps_ok
echo.

REM ================= 3. Start service =================
echo ========================================
echo   Service URL: http://127.0.0.1:8888/
echo   Close this window or press Ctrl+C to stop
echo ========================================
echo.

if exist "%~dp0run.py" goto :run_entry
"%PY%" -m uvicorn webapp.main:app --host 127.0.0.1 --port 8888
goto :after_run
:run_entry
"%PY%" "%~dp0run.py"
:after_run

echo.
echo [Service stopped]
goto :end

:no_python
echo [ERROR] No usable Python found.
echo.
echo Install Python 3.9+ from https://www.python.org/downloads/
echo During setup check "Add python.exe to PATH", then run this script again.

:end
echo.
pause
endlocal
exit /b
