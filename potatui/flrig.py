# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""flrig XML-RPC client for frequency and mode control."""

from __future__ import annotations

import xmlrpc.client
from typing import Optional

class _TimeoutTransport(xmlrpc.client.Transport):
    """Transport with a configurable socket timeout (important on Windows)."""

    def __init__(self, timeout: float = 1.0, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._timeout = timeout

    def make_connection(self, host: str) -> xmlrpc.client.http.client.HTTPConnection:  # type: ignore[override]
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


# Map flrig mode strings to our canonical mode names
MODE_MAP: dict[str, str] = {
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


class FlrigClient:
    def __init__(self, host: str = "localhost", port: int = 12345) -> None:
        self._url = f"http://{host}:{port}"
        self._proxy: Optional[xmlrpc.client.ServerProxy] = None

    def _get_proxy(self) -> xmlrpc.client.ServerProxy:
        if self._proxy is None:
            self._proxy = xmlrpc.client.ServerProxy(
                self._url, allow_none=True, transport=_TimeoutTransport(timeout=1.0)
            )
        return self._proxy

    def _reset(self) -> None:
        """Clear cached proxy so it's recreated on next call."""
        self._proxy = None

    def get_frequency(self) -> Optional[float]:
        """Return current VFO frequency in kHz, or None if offline."""
        try:
            proxy = self._get_proxy()
            hz = proxy.rig.get_vfo()  # type: ignore[union-attr]
            return float(hz) / 1000.0
        except Exception:
            self._reset()
            return None

    def get_mode(self) -> Optional[str]:
        """Return current mode as our canonical string, or None if offline."""
        try:
            proxy = self._get_proxy()
            raw = proxy.rig.get_mode()  # type: ignore[union-attr]
            return MODE_MAP.get(str(raw).upper(), str(raw))
        except Exception:
            self._reset()
            return None

    def set_frequency(self, freq_hz: float) -> bool:
        """Set VFO frequency in Hz. Returns True on success."""
        try:
            proxy = self._get_proxy()
            proxy.rig.set_vfo(freq_hz)  # type: ignore[union-attr]
            return True
        except Exception:
            self._reset()
            return False

    def set_mode(self, mode: str, freq_khz: Optional[float] = None) -> bool:
        """Set mode by canonical name. Returns True on success.

        freq_khz is used to pick USB vs LSB for SSB: >=10 MHz → USB, <10 MHz → LSB.
        """
        flrig_mode = _canonical_to_flrig(mode, freq_khz)
        try:
            proxy = self._get_proxy()
            proxy.rig.set_mode(flrig_mode)  # type: ignore[union-attr]
            return True
        except Exception:
            self._reset()
            return False

    def send_cat_string(self, cmd: str) -> bool:
        """Send a raw CAT command string via rig.cat_string. Returns True on success.

        The command is forwarded as-is to the connected rig. Examples:
          Yaesu voice keyer: "PB01;" through "PB05;"
          Other rigs: whatever CAT command triggers the desired function.
        """
        try:
            proxy = self._get_proxy()
            proxy.rig.cat_string(cmd)  # type: ignore[union-attr]
            return True
        except xmlrpc.client.Fault:
            # Rig is reachable but rejected the command — don't drop the connection
            return False
        except Exception:
            self._reset()
            return False

    def is_online(self) -> bool:
        """Quick connectivity check."""
        return self.get_frequency() is not None


def _canonical_to_flrig(mode: str, freq_khz: Optional[float] = None) -> str:
    """Best-effort map from canonical mode name back to flrig mode string.

    For SSB, picks USB (>=10 MHz) or LSB (<10 MHz) based on freq_khz.
    Defaults to USB if freq_khz is unknown.
    """
    if mode.upper() == "SSB":
        return "LSB" if (freq_khz is not None and freq_khz < 10_000) else "USB"
    mapping = {
        "CW": "CW-U",
        "AM": "AM",
        "FM": "FM",
        "FT8": "PKTUSB",
        "FT4": "PKTUSB",
    }
    return mapping.get(mode.upper(), mode)
