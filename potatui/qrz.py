# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""QRZ XML data API client — callsign lookup with name, location, distance."""

from __future__ import annotations

import asyncio
import math
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from potatui.log import get_logger

_log = get_logger("qrz")

_QRZ_URL = "https://xmldata.qrz.com/xml/current/"
_AGENT = "Potatui/1.0"
_QRZ_NS = "http://xmldata.qrz.com"
_MAX_ERROR_LOG = 50


@dataclass
class QRZInfo:
    callsign: str
    fname: str      # Full first name (may include nickname in parens)
    name: str       # "First Last"
    city: str       # addr2
    state: str      # USA state
    country: str
    grid: str
    lat: float | None
    lon: float | None

    @property
    def location(self) -> str:
        """Human-readable city/state/country string."""
        if self.state:
            parts = [p for p in [self.city, self.state] if p]
            return ", ".join(parts)
        parts = [p for p in [self.city, self.country] if p]
        return ", ".join(parts)


class QRZClient:
    """QRZ XML data API client with session-key caching and per-session callsign cache."""

    def __init__(self, username: str, password: str, api_url: str = _QRZ_URL) -> None:
        self._username = username.strip()
        self._password = password.strip()
        self._api_url = api_url.strip() or _QRZ_URL
        self._session_key: str | None = None
        self._cache: dict[str, QRZInfo | None] = {}
        self._error_log: list[str] = []
        self._last_ok: bool | None = None  # None = not yet tested
        from potatui._ssl_ctx import ssl_ctx
        self._http = httpx.Client(timeout=10, headers={"User-Agent": _AGENT}, verify=ssl_ctx)
        # Prevents concurrent backfill threads from stampeding the QRZ session
        # endpoint when the key is absent or has just expired.
        self._login_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._username and self._password)

    @property
    def status(self) -> str:
        """'unconfigured' | 'pending' | 'ok' | 'error' — reflects last API interaction."""
        if not self.configured:
            return "unconfigured"
        if self._last_ok is None:
            return "pending"  # configured but not yet tested
        return "ok" if self._last_ok else "error"

    @property
    def error_log(self) -> list[str]:
        """Recent error messages, newest first."""
        return list(reversed(self._error_log))

    def _mark_ok(self) -> None:
        self._last_ok = True

    def _log_error(self, msg: str) -> None:
        import datetime
        ts = datetime.datetime.utcnow().strftime("%H:%Mz")
        self._error_log.append(f"{ts}  {msg}")
        if len(self._error_log) > _MAX_ERROR_LOG:
            self._error_log.pop(0)
        self._last_ok = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find(self, el: ET.Element, tag: str) -> ET.Element | None:
        """Find child element, trying with and without the QRZ namespace."""
        result = el.find(f"{{{_QRZ_NS}}}{tag}")
        if result is None:
            result = el.find(tag)
        return result

    def _text(self, el: ET.Element, tag: str) -> str:
        child = self._find(el, tag)
        return child.text.strip() if child is not None and child.text else ""

    def _parse_session_key(self, root: ET.Element) -> str | None:
        session = self._find(root, "Session")
        if session is None:
            return None
        key_el = self._find(session, "Key")
        return key_el.text.strip() if key_el is not None and key_el.text else None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _login(self) -> bool:
        """Authenticate and cache the session key. Runs in a thread. Returns True on success."""
        _t0 = time.perf_counter()
        try:
            r = self._http.get(
                self._api_url,
                params={
                    "username": self._username,
                    "password": self._password,
                    "agent": _AGENT,
                },
            )
            root = ET.fromstring(r.text)
            key = self._parse_session_key(root)
            if key:
                self._session_key = key
                self._mark_ok()
                _log.debug("qrz login: ok in %.0f ms", (time.perf_counter() - _t0) * 1000)
                return True
            # Extract error message for logging
            session = self._find(root, "Session")
            err_text = ""
            if session is not None:
                err_el = self._find(session, "Error")
                if err_el is not None and err_el.text:
                    err_text = err_el.text.strip()
            self._log_error(f"Login failed: {err_text or 'no session key returned'}")
            _log.debug("qrz login: failed in %.0f ms — %s", (time.perf_counter() - _t0) * 1000, err_text or "no session key")
            return False
        except Exception as exc:
            self._log_error(f"Login error: {exc}")
            _log.debug("qrz login: error in %.0f ms — %s", (time.perf_counter() - _t0) * 1000, exc)
            return False

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def lookup(self, callsign: str) -> QRZInfo | None:
        """Look up a callsign. Returns None if not configured, not found, or on error.

        The HTTP fetch and XML parsing are run in a thread so the event loop
        stays free to handle UI rendering and input during the request.
        """
        if not self.configured:
            return None

        callsign = callsign.upper().split("/")[0]   # strip /P, /MM, etc.

        if callsign in self._cache:
            _log.debug("qrz lookup %s: session cache hit", callsign)
            return self._cache[callsign]

        info = await asyncio.to_thread(self._fetch_blocking, callsign)
        self._cache[callsign] = info
        return info

    def _fetch_blocking(self, callsign: str) -> QRZInfo | None:
        """Synchronous fetch — login if needed, look up, retry once on session expiry.

        Runs in a thread via asyncio.to_thread. Uses a threading.Lock so concurrent
        backfill threads don't stampede the QRZ login endpoint simultaneously.
        """
        if not self._session_key:
            with self._login_lock:
                if not self._session_key:  # double-check after acquiring lock
                    if not self._login():
                        return None

        info = self._do_lookup(callsign)

        # Session may have expired — try re-login once
        if info is None and self._session_key:
            with self._login_lock:
                self._session_key = None
                if not self._login():
                    return None
            info = self._do_lookup(callsign)

        return info

    def _do_lookup(self, callsign: str) -> QRZInfo | None:
        """Fetch and parse a callsign. Runs in a thread."""
        _t0 = time.perf_counter()
        try:
            r = self._http.get(
                self._api_url,
                params={"s": self._session_key, "callsign": callsign},
            )
            root = ET.fromstring(r.text)

            # Refresh session key if provided
            new_key = self._parse_session_key(root)
            if new_key:
                self._session_key = new_key

            call_el = self._find(root, "Callsign")
            if call_el is None:
                # Distinguish "not found" (valid response) from session errors
                session = self._find(root, "Session")
                if session is not None:
                    err_el = self._find(session, "Error")
                    if err_el is not None and err_el.text:
                        err_text = err_el.text.strip()
                        if "not found" in err_text.lower():
                            self._mark_ok()  # Callsign not in QRZ — still a valid API response
                            _log.debug("qrz lookup %s: not found in %.0f ms", callsign, (time.perf_counter() - _t0) * 1000)
                        else:
                            _log.debug("qrz lookup %s: session error in %.0f ms — %s", callsign, (time.perf_counter() - _t0) * 1000, err_text)
                        # else: session/auth error — caller handles retry; don't change status
                        return None
                self._mark_ok()  # Valid response with no callsign and no error
                _log.debug("qrz lookup %s: no data in %.0f ms", callsign, (time.perf_counter() - _t0) * 1000)
                return None

            def t(tag: str) -> str:
                return self._text(call_el, tag)

            fname = t("fname")
            lname = t("name")
            nickname = t("nickname")
            first = nickname if nickname else fname
            name = f"{first} {lname}".strip() if (first or lname) else ""

            lat_s = t("lat")
            lon_s = t("lon")
            lat = float(lat_s) if lat_s else None
            lon = float(lon_s) if lon_s else None

            self._mark_ok()
            info = QRZInfo(
                callsign=callsign,
                fname=fname,
                name=name,
                city=t("addr2"),
                state=t("state"),
                country=t("country") or t("land"),
                grid=t("grid"),
                lat=lat,
                lon=lon,
            )
            _log.debug("qrz lookup %s: found in %.0f ms", callsign, (time.perf_counter() - _t0) * 1000)
            return info
        except Exception as exc:
            self._log_error(f"Lookup {callsign}: {exc}")
            _log.debug("qrz lookup %s: error in %.0f ms — %s", callsign, (time.perf_counter() - _t0) * 1000, exc)
            return None


# ---------------------------------------------------------------------------
# Grid / distance utilities
# ---------------------------------------------------------------------------

def grid_to_latlon(grid: str) -> tuple[float, float]:
    """Convert a Maidenhead grid locator to (lat, lon) of its center."""
    g = grid.upper()
    if len(g) < 4:
        raise ValueError(f"Grid too short: {grid}")
    lon: float = (ord(g[0]) - ord("A")) * 20 - 180 + int(g[2]) * 2
    lat: float = (ord(g[1]) - ord("A")) * 10 - 90 + int(g[3]) * 1
    if len(g) >= 6:
        lon += (ord(g[4].lower()) - ord("a")) * (2.0 / 24) + (1.0 / 24)
        lat += (ord(g[5].lower()) - ord("a")) * (1.0 / 24) + (1.0 / 48)
    else:
        # move to center of grid
        lon += 1.0
        lat += 0.5
    return lat, lon


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0–360) from point 1 to point 2."""
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def cardinal(deg: float) -> str:
    """Convert a bearing in degrees to a 16-point cardinal direction string."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round(deg / 22.5) % 16]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def distance_from_grid(my_grid: str, info: QRZInfo) -> float | None:
    """Return distance in km from my_grid to the QRZ location, or None if not computable."""
    if not my_grid or len(my_grid) < 4:
        return None
    try:
        lat1, lon1 = grid_to_latlon(my_grid)
    except Exception:
        return None

    if info.lat is not None and info.lon is not None:
        return haversine_km(lat1, lon1, info.lat, info.lon)

    if info.grid and len(info.grid) >= 4:
        try:
            lat2, lon2 = grid_to_latlon(info.grid)
            return haversine_km(lat1, lon1, lat2, lon2)
        except Exception:
            pass

    return None
