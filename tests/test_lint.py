# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Lint and type-check gates — ruff and mypy must pass cleanly."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable


def test_ruff() -> None:
    result = subprocess.run(
        [PYTHON, "-m", "ruff", "check", "potatui/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ruff errors:\n{result.stdout}{result.stderr}"


def test_mypy() -> None:
    result = subprocess.run(
        [PYTHON, "-m", "mypy", "potatui/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"mypy errors:\n{result.stdout}{result.stderr}"
