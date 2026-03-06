#!/usr/bin/env pwsh
# Launcher script for Potatui on Windows (PowerShell)
# This script automatically uses the virtual environment without requiring manual activation

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Path to the venv Python interpreter
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

# Check if venv exists
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $ScriptDir\.venv"
    Write-Host "Please run the installation steps first:"
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\Activate.ps1"
    Write-Host "  pip install -e ."
    exit 1
}

# Run potatui using the venv Python interpreter
& $VenvPython -m potatui.main $args
