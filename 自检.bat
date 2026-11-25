@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo.
echo   Media Reverse - Self Check
echo   Opens the browser and checks: endpoint / key / models / disk / vision
echo.
REM The exe name contains Chinese characters; use a wildcard so this bat stays ASCII-encoded.
for %%F in (*.exe) do (
    start "" "%%F" --selfcheck
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" run.py --selfcheck
    exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
    start "" python run.py --selfcheck
    exit /b
)
echo   [X] App not found. Run start_simple.bat first to set up the environment.
pause
endlocal
