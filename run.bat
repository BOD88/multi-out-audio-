@echo off
:: ─────────────────────────────────────────────────────────────────
:: run.bat — Windows launcher for Multi-Output Audio Console
:: Double-click this file or run it from a command prompt.
:: ─────────────────────────────────────────────────────────────────

title Multi-Output Audio Console

:: Check that Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python 3.8+ from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Install dependencies if needed (silent)
echo  Checking dependencies ...
pip install -r requirements.txt -q --disable-pip-version-check

:: Launch the application
echo  Starting Multi-Output Audio Console ...
python main.py

if errorlevel 1 (
    echo.
    echo  The application exited with an error.
    pause
)
