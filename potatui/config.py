"""Load and save configuration from the platform-appropriate config directory."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[no-reuse-imports]

CONFIG_DIR = Path(user_config_dir("potatui", appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.toml"


def _default_config_toml() -> str:
    """Default config content from packaged resource (single source of truth)."""
    return (resources.files("potatui") / "resources" / "default_config.toml").read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Mapping: TOML section + key  →  Config field name
# Supports both the current sectioned format and the old flat format.
# ---------------------------------------------------------------------------

_SECTION_MAP: dict[tuple[str, str], str] = {
    ("operator", "callsign"): "callsign",
    ("operator", "grid"): "grid",
    ("operator", "distance_unit"): "distance_unit",
    ("qrz", "username"): "qrz_username",
    ("qrz", "password"): "qrz_password",
    ("qrz", "api_url"): "qrz_api_url",
    ("logs", "dir"): "log_dir",
    ("rig", "name"): "rig",
    ("rig", "antenna"): "antenna",
    ("rig", "power_w"): "power_w",
    ("flrig", "host"): "flrig_host",
    ("flrig", "port"): "flrig_port",
    ("voice_keyer", "vk1"): "vk1",
    ("voice_keyer", "vk2"): "vk2",
    ("voice_keyer", "vk3"): "vk3",
    ("voice_keyer", "vk4"): "vk4",
    ("voice_keyer", "vk5"): "vk5",
    ("pota", "api_base"): "pota_api_base",
    ("app", "theme"): "theme",
}


@dataclass
class Config:
    # Kept flat so the rest of the codebase needs no changes.
    callsign: str = ""
    grid: str = ""
    distance_unit: str = "mi"  # "mi" or "km"
    rig: str = ""
    antenna: str = ""
    power_w: int = 100
    log_dir: str = "~/potatui-logs"
    flrig_host: str = "localhost"
    flrig_port: int = 12345
    pota_api_base: str = "https://api.pota.app"
    theme: str = "nord"
    qrz_username: str = ""
    qrz_password: str = ""
    qrz_api_url: str = "https://xmldata.qrz.com/xml/current/"
    vk1: str = "PB01;"
    vk2: str = "PB02;"
    vk3: str = "PB03;"
    vk4: str = "PB04;"
    vk5: str = "PB05;"

    @property
    def log_dir_path(self) -> Path:
        return Path(self.log_dir).expanduser()


def _qrz_username_for_save(cfg: Config) -> str:
    """When saving: do not write username to TOML if it came from env (keep secrets out of config)."""
    env_user = os.environ.get("POTATUI_QRZ_USERNAME", "")
    return "" if (env_user and cfg.qrz_username == env_user) else cfg.qrz_username


def _qrz_password_for_save(cfg: Config) -> str:
    """When saving: do not write password to TOML if it came from env (keep secrets out of config)."""
    env_pass = os.environ.get("POTATUI_QRZ_PASSWORD", "")
    return "" if (env_pass and cfg.qrz_password == env_pass) else cfg.qrz_password


def save_config(cfg: Config) -> None:
    """Write config back to disk in the sectioned TOML format."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    content = f"""\
# ============================================================
#  Potatui configuration
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

username = {q(_qrz_username_for_save(cfg))}
password = {q(_qrz_password_for_save(cfg))}
api_url = {q(cfg.qrz_api_url)}


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
    CONFIG_PATH.write_text(content, encoding="utf-8")


def load_config() -> Config:
    """Load config, creating the default file if it doesn't exist yet."""
    if not CONFIG_PATH.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(_default_config_toml(), encoding="utf-8")

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    cfg = Config()

    # New sectioned format
    for (section, key), field in _SECTION_MAP.items():
        if section in data and key in data[section]:
            setattr(cfg, field, data[section][key])

    # Legacy flat format (backwards compat with old config files)
    _LEGACY_FLAT = {
        "callsign": "callsign",
        "grid": "grid",
        "rig": "rig",
        "antenna": "antenna",
        "power_w": "power_w",
        "log_dir": "log_dir",
        "flrig_host": "flrig_host",
        "flrig_port": "flrig_port",
        "pota_api_base": "pota_api_base",
        "qrz_username": "qrz_username",
        "qrz_password": "qrz_password",
        "vk1": "vk1",
        "vk2": "vk2",
        "vk3": "vk3",
        "vk4": "vk4",
        "vk5": "vk5",
    }
    for flat_key, field in _LEGACY_FLAT.items():
        # Skip keys that map to a TOML section (dict) rather than a scalar value.
        if flat_key in data and not isinstance(data[flat_key], dict):
            setattr(cfg, field, data[flat_key])

    # Coerce types (TOML or hand-edit may give str for numeric fields)
    try:
        cfg.power_w = int(cfg.power_w) if cfg.power_w not in (None, "") else 100
    except (TypeError, ValueError):
        cfg.power_w = 100
    try:
        cfg.flrig_port = (
            int(cfg.flrig_port) if cfg.flrig_port not in (None, "") else 12345
        )
    except (TypeError, ValueError):
        cfg.flrig_port = 12345
    for field in (
        "callsign",
        "grid",
        "distance_unit",
        "rig",
        "antenna",
        "log_dir",
        "flrig_host",
        "theme",
        "qrz_username",
        "qrz_password",
        "qrz_api_url",
        "pota_api_base",
        "vk1",
        "vk2",
        "vk3",
        "vk4",
        "vk5",
    ):
        val = getattr(cfg, field)
        if val is not None and not isinstance(val, str):
            setattr(cfg, field, str(val))

    # .env in config dir overrides TOML for QRZ credentials (keeps secrets out of config.toml)
    load_dotenv(CONFIG_DIR / ".env")
    if os.environ.get("POTATUI_QRZ_USERNAME"):
        cfg.qrz_username = os.environ["POTATUI_QRZ_USERNAME"]
    if os.environ.get("POTATUI_QRZ_PASSWORD"):
        cfg.qrz_password = os.environ["POTATUI_QRZ_PASSWORD"]

    return cfg
