#!/usr/bin/env python3
"""Add SPDX license headers to all project Python files."""

import pathlib

HEADER = """\
# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)
"""

ROOT = pathlib.Path(__file__).parent / "potatui"

for py_file in ROOT.rglob("*.py"):
    text = py_file.read_text(encoding="utf-8")
    if "SPDX-License-Identifier" in text:
        print(f"skip (already has header): {py_file.relative_to(ROOT.parent)}")
        continue
    py_file.write_text(HEADER + "\n" + text, encoding="utf-8")
    print(f"added: {py_file.relative_to(ROOT.parent)}")
