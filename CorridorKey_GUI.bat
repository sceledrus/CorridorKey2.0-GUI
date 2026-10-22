@echo off
rem CorridorKey 2.0 launcher (Python version). Optionally drag a clip or folder onto this file.
rem Prefer CorridorKey2.exe - it does the same and also checks the environment for you.
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if "%~1"=="" (
    "%PYTHON%" run_gui.py
) else (
    "%PYTHON%" run_gui.py "%~1"
)

if errorlevel 1 pause
