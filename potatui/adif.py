"""ADIF export logic."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from potatui import __version__
from potatui.session import QSO, Session

# Band frequency ranges in kHz: (min_khz, max_khz, band_name)
BAND_RANGES: list[tuple[float, float, str]] = [
    (1800, 2000, "160m"),
    (3500, 4000, "80m"),
    (5330, 5410, "60m"),
    (7000, 7300, "40m"),
    (10100, 10150, "30m"),
    (14000, 14350, "20m"),
    (18068, 18168, "17m"),
    (21000, 21450, "15m"),
    (24890, 24990, "12m"),
    (28000, 29700, "10m"),
    (50000, 54000, "6m"),
    (144000, 148000, "2m"),
    (420000, 450000, "70cm"),
]


def freq_to_band(freq_khz: float) -> str:
    """Map a frequency in kHz to an amateur band name."""
    for lo, hi, band in BAND_RANGES:
        if lo <= freq_khz <= hi:
            return band
    return "?"


def _field(tag: str, value: str) -> str:
    """Format a single ADIF field."""
    return f"<{tag}:{len(value)}>{value}"


def _qso_to_adif(qso: QSO, operator: str, park_ref: str) -> str:
    """Convert a QSO to an ADIF record string."""
    date_str = qso.timestamp_utc.strftime("%Y%m%d")
    time_str = qso.timestamp_utc.strftime("%H%M%S")
    freq_mhz = f"{qso.freq_khz / 1000:.4f}"

    # Map mode to ADIF mode
    adif_mode, submode = _mode_to_adif(qso.mode)

    parts = [
        _field("CALL", qso.callsign),
        _field("QSO_DATE", date_str),
        _field("TIME_ON", time_str),
        _field("BAND", qso.band.upper()),
        _field("MODE", adif_mode),
        _field("FREQ", freq_mhz),
        _field("RST_SENT", qso.rst_sent),
        _field("RST_RCVD", qso.rst_rcvd),
        _field("OPERATOR", operator),
        _field("STATION_CALLSIGN", operator),
        _field("MY_SIG", "POTA"),
        _field("MY_SIG_INFO", park_ref.upper()),
    ]

    if submode:
        parts.append(_field("SUBMODE", submode))
    if qso.name:
        parts.append(_field("NAME", qso.name))
    if qso.state:
        parts.append(_field("STATE", qso.state))
    if qso.notes:
        parts.append(_field("COMMENT", qso.notes))
    if qso.is_p2p and qso.p2p_ref:
        parts.append(_field("SIG", "POTA"))
        parts.append(_field("SIG_INFO", qso.p2p_ref))

    return " ".join(parts) + " <EOR>\n"


def _mode_to_adif(mode: str) -> tuple[str, str]:
    """Return (ADIF_MODE, SUBMODE) pair."""
    mapping = {
        "SSB": ("SSB", ""),
        "CW": ("CW", ""),
        "AM": ("AM", ""),
        "FM": ("FM", ""),
        "FT8": ("FT8", ""),
        "FT4": ("FT4", ""),
    }
    return mapping.get(mode.upper(), (mode.upper(), ""))


def _adif_header() -> str:
    return (
        f"<PROGRAMID:{len('Potatui')}>Potatui "
        f"<PROGRAMVERSION:{len(__version__)}>{__version__} "
        "<EOH>\n"
    )


def write_adif(session: Session, path: Path) -> None:
    """Write the complete ADIF file for the session (overwrites)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(_adif_header())
        for qso in session.qsos:
            f.write(_qso_to_adif(qso, session.operator, session.active_park_ref))


def append_qso_adif(qso: QSO, operator: str, park_ref: str, path: Path) -> None:
    """Append a single QSO to an ADIF file, writing header if new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w") as f:
            f.write(_adif_header())
    with open(path, "a") as f:
        f.write(_qso_to_adif(qso, operator, park_ref))


def session_file_stem(session: Session) -> str:
    """Return the base filename stem for session files."""
    date = session.start_time.strftime("%Y%m%d")
    call = session.operator.upper().replace("/", "-")
    park = session.active_park_ref.upper().replace("/", "-")
    return f"{date}-{call}-{park}"
