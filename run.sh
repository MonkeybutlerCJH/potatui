#!/usr/bin/env bash
# Launcher script for Potatui on Linux/macOS
# This script automatically uses the virtual environment without requiring manual activation

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect the Python interpreter (supports both Unix and Windows-style venvs)
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
    # Windows-style venv (WSL or Cygwin)
    VENV_PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"
else
    echo "Error: Virtual environment not found at $SCRIPT_DIR/.venv"
    echo "Please run the installation steps first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -e ."
    exit 1
fi

# Run potatui using the venv Python interpreter
exec "$VENV_PYTHON" -m potatui.main "$@"
