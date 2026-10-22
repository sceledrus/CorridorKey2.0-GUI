@echo off
rem Builds the standalone CorridorKey2.exe (a real Windows program, no Python needed to open the window).
rem Run it once from the CorridorKey folder. It needs internet access (pip) and takes a few minutes.
rem Result: dist\CorridorKey2\CorridorKey2.exe   (pass --onefile for a single exe)
cd /d "%~dp0"

set "PY="
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python was not found. Install Python 3.12 from python.org, then run this again.
    pause
    exit /b 1
)

echo Building CorridorKey 2.0 ...
%PY% build_exe.py %*
if errorlevel 1 (
    echo.
    echo The build failed - scroll up for the reason. The small launcher CorridorKey2.exe in this folder still works.
    pause
    exit /b 1
)
echo.
echo Done.
pause
