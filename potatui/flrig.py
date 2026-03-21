# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""flrig XML-RPC client for frequency and mode control."""

from __future__ import annotations

import threading
import xmlrpc.client
from datetime import datetime


class _TimeoutTransport(xmlrpc.client.Transport):
    """Transport with a configurable socket timeout (important on Windows)."""

    def __init__(self, timeout: float = 1.0, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._timeout = timeout

    def make_connection(self, host: str) -> xmlrpc.client.http.client.HTTPConnection:  # type: ignore[override, name-defined]
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

_LOG_MAX = 100


class FlrigClient:
    def __init__(self, host: str = "localhost", port: int = 12345) -> None:
        self._url = f"http://{host}:{port}"
        # Two independent proxies: _proxy for polling (1s timeout),
        # _cat_proxy for CAT/command sends (longer timeout).  Keeping them
        # separate means a slow or timed-out CAT command never touches the
        # proxy used by the poll loop, so the online indicator stays stable.
        self._proxy: xmlrpc.client.ServerProxy | None = None
        self._cat_proxy: xmlrpc.client.ServerProxy | None = None
        self._lock = threading.Lock()       # guards _proxy
        self._cat_lock = threading.Lock()   # guards _cat_proxy
        self.log: list[str] = []            # diagnostic log, newest appended last
        self.cat_in_flight = False          # True while a CAT command is being sent

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _append_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
        entry = f"{ts}  {msg}"
        self.log.append(entry)
        if len(self.log) > _LOG_MAX:
            self.log = self.log[-_LOG_MAX:]

    # ------------------------------------------------------------------
    # Poll proxy (1 s timeout — used for get_frequency / get_mode / set_*)
    # ------------------------------------------------------------------

    def _get_proxy(self) -> xmlrpc.client.ServerProxy:
        """Must be called with self._lock held."""
        if self._proxy is None:
            self._proxy = xmlrpc.client.ServerProxy(
                self._url, allow_none=True, transport=_TimeoutTransport(timeout=1.0)
            )
        return self._proxy

    def _reset(self) -> None:
        """Must be called with self._lock held."""
        self._proxy = None

    # ------------------------------------------------------------------
    # CAT proxy (5 s timeout — used for send_cat_string only)
    # ------------------------------------------------------------------

    def _get_cat_proxy(self) -> xmlrpc.client.ServerProxy:
        """Must be called with self._cat_lock held."""
        if self._cat_proxy is None:
            self._cat_proxy = xmlrpc.client.ServerProxy(
                self._url, allow_none=True, transport=_TimeoutTransport(timeout=5.0)
            )
        return self._cat_proxy

    def _reset_cat(self) -> None:
        """Must be called with self._cat_lock held."""
        self._cat_proxy = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_frequency(self) -> float | None:
        """Return current VFO frequency in kHz, or None if offline."""
        with self._lock:
            try:
                hz = self._get_proxy().rig.get_vfo()
                return float(hz) / 1000.0  # type: ignore[arg-type]
            except Exception as exc:
                self._append_log(f"poll get_vfo FAIL  {type(exc).__name__}: {exc}")
                self._reset()
                return None

    def get_mode(self) -> str | None:
        """Return current mode as our canonical string, or None if offline."""
        with self._lock:
            try:
                raw = self._get_proxy().rig.get_mode()
                return MODE_MAP.get(str(raw).upper(), str(raw))
            except Exception as exc:
                self._append_log(f"poll get_mode FAIL  {type(exc).__name__}: {exc}")
                self._reset()
                return None

    def set_frequency(self, freq_hz: float) -> bool:
        """Set VFO frequency in Hz. Returns True on success."""
        with self._lock:
            try:
                self._get_proxy().rig.set_vfo(freq_hz)
                return True
            except Exception as exc:
                self._append_log(f"set_vfo({freq_hz}) FAIL  {type(exc).__name__}: {exc}")
                self._reset()
                return False

    def set_mode(self, mode: str, freq_khz: float | None = None) -> bool:
        """Set mode by canonical name. Returns True on success.

        freq_khz is used to pick USB vs LSB for SSB: >=10 MHz → USB, <10 MHz → LSB.
        """
        flrig_mode = _canonical_to_flrig(mode, freq_khz)
        with self._lock:
            try:
                self._get_proxy().rig.set_mode(flrig_mode)
                return True
            except Exception as exc:
                self._append_log(f"set_mode({flrig_mode}) FAIL  {type(exc).__name__}: {exc}")
                self._reset()
                return False

    def send_cat_string(self, cmd: str) -> bool:
        """Send a raw CAT command string via rig.cat_string. Returns True on success.

        Uses a separate proxy with a longer timeout so a slow rig response
        (e.g. while playing a voice message) does not disturb the poll proxy.

        A TimeoutError is treated as success: flrig's XML-RPC server is
        single-threaded and blocks while playing audio, so the command was
        almost certainly delivered even though the response never came back.

        The command is forwarded as-is to the connected rig. Examples:
          Yaesu voice keyer: "PB01;" through "PB05;"
          Other rigs: whatever CAT command triggers the desired function.
        """
        self._append_log(f"cat_string({cmd!r}) sending…")
        self.cat_in_flight = True
        try:
            with self._cat_lock:
                try:
                    self._get_cat_proxy().rig.cat_string(cmd)
                    self._append_log(f"cat_string({cmd!r}) OK")
                    return True
                except TimeoutError as exc:
                    # flrig is busy (playing audio) — command was sent, response just never came
                    self._append_log(f"cat_string({cmd!r}) timeout (treated as OK)  {exc}")
                    self._reset_cat()
                    return True
                except xmlrpc.client.Fault as exc:
                    # Rig is reachable but rejected the command — don't drop the connection
                    self._append_log(f"cat_string({cmd!r}) Fault  code={exc.faultCode} {exc.faultString!r}")
                    return False
                except Exception as exc:
                    self._append_log(f"cat_string({cmd!r}) FAIL  {type(exc).__name__}: {exc}")
                    self._reset_cat()
                    return False
        finally:
            self.cat_in_flight = False

    def is_online(self) -> bool:
        """Quick connectivity check."""
        return self.get_frequency() is not None


def _canonical_to_flrig(mode: str, freq_khz: float | None = None) -> str:
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
