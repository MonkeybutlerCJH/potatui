# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""User-configurable rig mode translation tables.

Two directions:
  rig_to_canonical — what flrig reports → what potatui displays
  canonical_to_rig — what potatui selects → what flrig receives

Stored as JSON in the user config directory.  Falls back to built-in
defaults (matching the old hardcoded MODE_MAP / _canonical_to_flrig).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

from potatui.config import CONFIG_DIR

TRANSLATIONS_PATH = CONFIG_DIR / "mode_translations.json"

# ---------------------------------------------------------------------------
# Built-in defaults (mirrors the old hardcoded tables in flrig.py)
# ---------------------------------------------------------------------------

_DEFAULT_RIG_TO_CANONICAL: dict[str, str] = {
    "USB": "SSB",
    "LSB": "SSB",
    "CW": "CW",
    "CWR": "CW",
    "CW-R": "CW",
    "CW-U": "CW",
    "CW-L": "CW",
    "AM": "AM",
    "FM": "FM",
    "FMN": "FM",
    "FT8": "FT8",
    "FT4": "FT4",
    "PKTUSB": "FT8",
    "PKTLSB": "FT8",
    "DIGU": "FT8",
    "DIGL": "FT8",
}

# SSB is intentionally "" — the outbound logic keeps automatic USB/LSB-by-freq.
_DEFAULT_CANONICAL_TO_RIG: dict[str, str] = {
    "SSB": "",
    "CW": "CW-U",
    "AM": "AM",
    "FM": "FM",
    "FT8": "PKTUSB",
    "FT4": "PKTUSB",
}

# ---------------------------------------------------------------------------
# Pattern-based auto-mapping used when fetching modes from the rig
# ---------------------------------------------------------------------------

_AUTO_EXACT: dict[str, str] = dict(_DEFAULT_RIG_TO_CANONICAL)

def _auto_guess(raw: str) -> str | None:
    """Best-effort canonical guess for an unrecognised rig mode string."""
    u = raw.upper()
    if u in _AUTO_EXACT:
        return _AUTO_EXACT[u]
    if "CW" in u:
        return "CW"
    if "USB" in u or "LSB" in u:
        return "SSB"
    if "FMN" in u or "FM" in u or "WFM" in u:
        return "FM"
    if "AM" in u:
        return "AM"
    if "PKT" in u or "DIG" in u or "DATA" in u or "FT8" in u:
        return "FT8"
    if "FT4" in u:
        return "FT4"
    return None


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModeTranslations:
    rig_to_canonical: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_RIG_TO_CANONICAL))
    canonical_to_rig: dict[str, str] = field(default_factory=lambda: dict(_DEFAULT_CANONICAL_TO_RIG))


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def _load_raw() -> dict[str, Any] | None:
    """Return parsed JSON dict from the translations file, or None on failure."""
    if not TRANSLATIONS_PATH.exists():
        return None
    try:
        with open(TRANSLATIONS_PATH, encoding="utf-8") as f:
            return cast("dict[str, Any]", json.load(f))
    except Exception:
        return None


def load_translations() -> ModeTranslations:
    """Load translations for runtime use by FlrigClient.

    Merges user-saved data on top of built-in defaults so that modes not
    explicitly configured still resolve to a canonical name.
    """
    data = _load_raw()
    if data is None:
        return ModeTranslations()
    r2c = dict(_DEFAULT_RIG_TO_CANONICAL)
    r2c.update({str(k): str(v) for k, v in data.get("rig_to_canonical", {}).items()})
    c2r = dict(_DEFAULT_CANONICAL_TO_RIG)
    c2r.update({str(k): str(v) for k, v in data.get("canonical_to_rig", {}).items()})
    return ModeTranslations(rig_to_canonical=r2c, canonical_to_rig=c2r)


def load_user_translations() -> ModeTranslations:
    """Load translations for display in the UI editor.

    Returns *only* what was explicitly saved by the user — no built-in defaults
    are injected into rig_to_canonical.  canonical_to_rig still seeds from
    defaults so the outbound table always has a starting value for every mode.
    """
    data = _load_raw()
    if data is None:
        return ModeTranslations(
            rig_to_canonical={},
            canonical_to_rig=dict(_DEFAULT_CANONICAL_TO_RIG),
        )
    r2c = {str(k): str(v) for k, v in data.get("rig_to_canonical", {}).items()}
    c2r = dict(_DEFAULT_CANONICAL_TO_RIG)
    c2r.update({str(k): str(v) for k, v in data.get("canonical_to_rig", {}).items()})
    return ModeTranslations(rig_to_canonical=r2c, canonical_to_rig=c2r)


def save_translations(t: ModeTranslations) -> None:
    """Persist translations to JSON in the config directory."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRANSLATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "rig_to_canonical": t.rig_to_canonical,
                "canonical_to_rig": t.canonical_to_rig,
            },
            f,
            indent=2,
        )


# ---------------------------------------------------------------------------
# Auto-map from a list of raw rig mode strings
# ---------------------------------------------------------------------------

def auto_map(rig_modes: list[str]) -> ModeTranslations:
    """Build a ModeTranslations from a list of rig mode strings.

    Inbound: tries to guess canonical name for each rig mode.
    Outbound: for each canonical mode, picks the first rig mode that maps to it
    (or keeps the existing default).
    """
    r2c: dict[str, str] = {}
    for m in rig_modes:
        guess = _auto_guess(m)
        if guess:
            r2c[m] = guess
        # Leave unmapped modes out; they'll pass through as raw strings.

    # Build outbound: canonical → first matching rig mode (prefer current defaults)
    c2r: dict[str, str] = dict(_DEFAULT_CANONICAL_TO_RIG)
    for canonical in ("SSB", "CW", "AM", "FM", "FT8", "FT4"):
        # If we already have a good default that appears in the rig's mode list, keep it.
        existing = c2r.get(canonical, "")
        if existing and existing in rig_modes:
            continue
        # Otherwise find the first rig mode that maps to this canonical.
        for rig_mode, mapped in r2c.items():
            if mapped == canonical:
                c2r[canonical] = rig_mode
                break

    return ModeTranslations(rig_to_canonical=r2c, canonical_to_rig=c2r)
