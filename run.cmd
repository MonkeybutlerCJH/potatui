@echo off
REM Launcher script for Potatui on Windows (Command Prompt)
REM This script automatically uses the virtual environment without requiring manual activation

setlocal

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"

REM Path to the venv Python interpreter
set "VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

REM Check if venv exists
if not exist "%VENV_PYTHON%" (
    echo Error: Virtual environment not found at %SCRIPT_DIR%.venv
    echo Please run the installation steps first:
    echo   python -m venv .venv
    echo   .venv\Scripts\Activate.ps1
    echo   pip install -e .
    exit /b 1
)

REM Run potatui using the venv Python interpreter
"%VENV_PYTHON%" -m potatui.main %*
