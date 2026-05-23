# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)
"""Protected frequency overlap detection.

Loads a user-editable JSON file from the config directory, merging user
entries atop built-in defaults (shipped as a package resource).  Pure
overlap-detection functions check whether the current TX passband overlaps
any protected frequency, accounting for USB vs LSB sideband direction.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from potatui.config import CONFIG_DIR

PROTECTED_PATH: Path = CONFIG_DIR / "protected_frequencies.json"


@dataclass
class ProtectedFrequency:
    frequency_khz: float
    label: str
    mode: str              # "USB" or "LSB" — which side the protected signal occupies
    bandwidth_khz: float = 3.0
    category: str = "protected"  # future: "out_of_band"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _read_entries(raw: list[dict]) -> list[ProtectedFrequency]:
    entries: list[ProtectedFrequency] = []
    for e in raw:
        entries.append(ProtectedFrequency(
            frequency_khz=float(e["frequency_khz"]),
            label=str(e["label"]),
            mode=str(e.get("mode", "USB")),
            bandwidth_khz=float(e.get("bandwidth_khz", 3.0)),
            category=str(e.get("category", "protected")),
        ))
    return entries


def _builtin_entries() -> list[ProtectedFrequency]:
    text = (resources.files("potatui") / "resources" / "default_protected_frequencies.json") \
        .read_text(encoding="utf-8")
    return _read_entries(json.loads(text).get("entries", []))


def load_protected() -> list[ProtectedFrequency]:
    """Load protected frequencies, merging user file atop built-in defaults.

    On first run the built-in defaults are copied to the config dir.
    User entries with the same label replace built-in entries; new user
    entries are added.  Built-in entries not present in the user file are
    retained, so new defaults in future releases appear automatically.
    """
    builtins = _builtin_entries()

    if not PROTECTED_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        save_protected(builtins)
        return builtins

    try:
        data = json.loads(PROTECTED_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return builtins

    builtins_by_freq: dict[float, ProtectedFrequency] = {e.frequency_khz: e for e in builtins}
    for e in _read_entries(data.get("entries", [])):
        builtins_by_freq[e.frequency_khz] = e
    return list(builtins_by_freq.values())


def save_protected(entries: list[ProtectedFrequency]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROTECTED_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "version": 1,
            "entries": [
                {
                    "frequency_khz": e.frequency_khz,
                    "label": e.label,
                    "mode": e.mode,
                    "bandwidth_khz": e.bandwidth_khz,
                    "category": e.category,
                }
                for e in entries
            ],
        }, f, indent=2)


# ---------------------------------------------------------------------------
# Overlap detection (pure functions)
# ---------------------------------------------------------------------------

def _tx_sideband(mode: str, freq_khz: float) -> str:
    """Determine which sideband our transmission occupies.

    SSB/AM/FM/CW: >=10 MHz → USB, <10 MHz → LSB (matches flrig convention).
    Data modes (FT8/FT4): always USB regardless of band.
    """
    m = mode.upper()
    if m in ("FT8", "FT4"):
        return "USB"
    return "USB" if freq_khz >= 10_000 else "LSB"


def _tx_bandwidth_khz(mode: str) -> float:
    """Approximate TX bandwidth in kHz for overlap checking."""
    m = mode.upper()
    if m in ("SSB", "AM", "FM"):
        return 3.0
    if m in ("CW",):
        return 0.5
    if m in ("FT8", "FT4"):
        return 0.05
    return 3.0


def _protected_range(entry: ProtectedFrequency) -> tuple[float, float]:
    """Return (low_khz, high_khz) for the protected signal's passband."""
    if entry.mode.upper() == "LSB":
        return (entry.frequency_khz - entry.bandwidth_khz, entry.frequency_khz)
    return (entry.frequency_khz, entry.frequency_khz + entry.bandwidth_khz)


def _tx_range(freq_khz: float, mode: str) -> tuple[float, float]:
    """Return (low_khz, high_khz) for our TX passband."""
    bw = _tx_bandwidth_khz(mode)
    if _tx_sideband(mode, freq_khz) == "LSB":
        return (freq_khz - bw, freq_khz)
    return (freq_khz, freq_khz + bw)


def _ranges_overlap(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> bool:
    """True if two closed intervals [a_lo, a_hi] and [b_lo, b_hi] intersect."""
    return a_lo <= b_hi and b_lo <= a_hi


def check_overlap(
    freq_khz: float, mode: str, entries: list[ProtectedFrequency],
) -> list[ProtectedFrequency]:
    """Return all protected entries whose passband overlaps our TX passband."""
    tx_lo, tx_hi = _tx_range(freq_khz, mode)
    return [
        e for e in entries
        if _ranges_overlap(tx_lo, tx_hi, *_protected_range(e))
    ]
