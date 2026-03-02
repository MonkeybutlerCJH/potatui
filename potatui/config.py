"""Load and save configuration from ~/.config/potatui/config.toml."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-reuse-imports]

CONFIG_DIR = Path.home() / ".config" / "potatui"
CONFIG_PATH = CONFIG_DIR / "config.toml"

# ---------------------------------------------------------------------------
# Default config written on first run
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_TOML = """\
# ============================================================
#  Potatui configuration
#  ~/.config/potatui/config.toml
#
#  Edit this file to pre-populate the activation setup screen.
#  All fields are optional — Potatui will still run without
#  them, but you will be prompted to fill things in manually.
# ============================================================


# ── Operator ────────────────────────────────────────────────
[operator]

# Your station callsign.  Used in ADIF exports and self-spots.
callsign = ""

# Maidenhead grid square (4 or 6 characters, e.g. "EN34" or "EN34ab").
grid = ""

# Distance units shown in the QRZ callsign info strip: "mi" or "km"
distance_unit = "mi"


# ── QRZ Lookup ──────────────────────────────────────────────
# Optional.  Not used in the current version, reserved for
# future callsign lookup / name auto-fill features.
[qrz]

username = ""
password = ""


# ── Log Files ───────────────────────────────────────────────
[logs]

# Directory where ADIF (.adi) and session (.json) files are saved.
# Tilde expansion is supported.
dir = "~/potatui-logs"


# ── Rig ─────────────────────────────────────────────────────
[rig]

# Free-text rig description written to the ADIF file.
# Example: "Icom IC-7300", "Elecraft KX3", "Yaesu FT-710"
name = ""

# Free-text antenna description written to the ADIF file.
# Example: "EFHW", "Dipole", "Vertical"
antenna = ""

# Transmit power in watts — written to the session log.
power_w = 100


# ── flrig Connection ────────────────────────────────────────
# flrig provides frequency and mode readout via XML-RPC.
# Start flrig before launching pota-log.  If flrig is not
# running the app works normally — radio fields just show "---".
[flrig]

host = "localhost"
port = 12345


# ── Voice Keyer ─────────────────────────────────────────────
# CAT commands forwarded to the rig via flrig's rig.cat_string
# method.  Press F7 in the logger to open the voice keyer panel,
# then press 1-5 to fire a message.
#
# These commands are rig-specific.  Common examples:
#   Yaesu FT-710 / FT-991A / FT-DX series:  PB01; through PB05;
#   Icom (voice keyer varies by model — check your manual)
#   Kenwood (check your manual for the DVR playback command)
#
# Leave a slot empty ("") to disable that button in the panel.
[voice_keyer]

vk1 = "PB01;"
vk2 = "PB02;"
vk3 = "PB03;"
vk4 = "PB04;"
vk5 = "PB05;"


# ── POTA API ────────────────────────────────────────────────
# You should not need to change this unless you are testing
# against a non-production POTA server.
[pota]

api_base = "https://api.pota.app"


# ── App ─────────────────────────────────────────────────────
[app]

# Textual theme name.  Changed automatically when you switch
# themes with the command palette (Ctrl+backslash).
theme = "textual-dark"
"""

# ---------------------------------------------------------------------------
# Mapping: TOML section + key  →  Config field name
# Supports both the current sectioned format and the old flat format.
# ---------------------------------------------------------------------------

_SECTION_MAP: dict[tuple[str, str], str] = {
    ("operator", "callsign"):       "callsign",
    ("operator", "grid"):           "grid",
    ("operator", "distance_unit"):  "distance_unit",
    ("qrz",      "username"):  "qrz_username",
    ("qrz",      "password"):  "qrz_password",
    ("logs",     "dir"):       "log_dir",
    ("rig",      "name"):      "rig",
    ("rig",      "antenna"):   "antenna",
    ("rig",      "power_w"):   "power_w",
    ("flrig",    "host"):      "flrig_host",
    ("flrig",    "port"):      "flrig_port",
    ("voice_keyer", "vk1"):    "vk1",
    ("voice_keyer", "vk2"):    "vk2",
    ("voice_keyer", "vk3"):    "vk3",
    ("voice_keyer", "vk4"):    "vk4",
    ("voice_keyer", "vk5"):    "vk5",
    ("pota",     "api_base"):  "pota_api_base",
    ("app",      "theme"):     "theme",
}


@dataclass
class Config:
    # Kept flat so the rest of the codebase needs no changes.
    callsign:       str = ""
    grid:           str = ""
    distance_unit:  str = "mi"  # "mi" or "km"
    rig:          str = ""
    antenna:      str = ""
    power_w:      int = 100
    log_dir:      str = "~/potatui-logs"
    flrig_host:   str = "localhost"
    flrig_port:   int = 12345
    pota_api_base: str = "https://api.pota.app"
    theme: str = "textual-dark"
    qrz_username: str = ""
    qrz_password: str = ""
    vk1: str = "PB01;"
    vk2: str = "PB02;"
    vk3: str = "PB03;"
    vk4: str = "PB04;"
    vk5: str = "PB05;"

    @property
    def log_dir_path(self) -> Path:
        return Path(self.log_dir).expanduser()


def save_config(cfg: Config) -> None:
    """Write config back to disk in the sectioned TOML format."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    content = f"""\
# ============================================================
#  Potatui configuration
#  ~/.config/potatui/config.toml
#
#  Edit this file to pre-populate the activation setup screen.
#  All fields are optional — Potatui will still run without
#  them, but you will be prompted to fill things in manually.
# ============================================================


# ── Operator ────────────────────────────────────────────────
[operator]

# Your station callsign.  Used in ADIF exports and self-spots.
callsign = {q(cfg.callsign)}

# Maidenhead grid square (4 or 6 characters, e.g. "EN34" or "EN34ab").
grid = {q(cfg.grid)}

# Distance units shown in the QRZ callsign info strip: "mi" or "km"
distance_unit = {q(cfg.distance_unit)}


# ── QRZ Lookup ──────────────────────────────────────────────
[qrz]

username = {q(cfg.qrz_username)}
password = {q(cfg.qrz_password)}


# ── Log Files ───────────────────────────────────────────────
[logs]

# Directory where ADIF (.adi) and session (.json) files are saved.
dir = {q(cfg.log_dir)}


# ── Rig ─────────────────────────────────────────────────────
[rig]

# Free-text rig description written to the ADIF file.
name = {q(cfg.rig)}

# Free-text antenna description written to the ADIF file.
antenna = {q(cfg.antenna)}

# Transmit power in watts.
power_w = {cfg.power_w}


# ── flrig Connection ────────────────────────────────────────
[flrig]

host = {q(cfg.flrig_host)}
port = {cfg.flrig_port}


# ── Voice Keyer ─────────────────────────────────────────────
[voice_keyer]

vk1 = {q(cfg.vk1)}
vk2 = {q(cfg.vk2)}
vk3 = {q(cfg.vk3)}
vk4 = {q(cfg.vk4)}
vk5 = {q(cfg.vk5)}


# ── POTA API ────────────────────────────────────────────────
[pota]

api_base = {q(cfg.pota_api_base)}


# ── App ─────────────────────────────────────────────────────
[app]

theme = {q(cfg.theme)}
"""
    CONFIG_PATH.write_text(content)


def load_config() -> Config:
    """Load config, creating the default file if it doesn't exist yet."""
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG_TOML)

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    cfg = Config()

    # New sectioned format
    for (section, key), field in _SECTION_MAP.items():
        if section in data and key in data[section]:
            setattr(cfg, field, data[section][key])

    # Legacy flat format (backwards compat with old config files)
    _LEGACY_FLAT = {
        "callsign": "callsign", "grid": "grid", "rig": "rig",
        "antenna": "antenna", "power_w": "power_w", "log_dir": "log_dir",
        "flrig_host": "flrig_host", "flrig_port": "flrig_port",
        "pota_api_base": "pota_api_base", "qrz_username": "qrz_username",
        "qrz_password": "qrz_password",
        "vk1": "vk1", "vk2": "vk2", "vk3": "vk3", "vk4": "vk4", "vk5": "vk5",
    }
    for flat_key, field in _LEGACY_FLAT.items():
        # Skip keys that map to a TOML section (dict) rather than a scalar value.
        if flat_key in data and not isinstance(data[flat_key], dict):
            setattr(cfg, field, data[flat_key])

    return cfg
