# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""HamDB.org callsign lookup — no-auth fallback when QRZ is unavailable."""

from __future__ import annotations

import asyncio
import datetime

import httpx

from potatui.qrz import QRZInfo

_HAMDB_URL = "http://api.hamdb.org/v1/{call}/json/potatui"
_MAX_ERROR_LOG = 50


class HamDbClient:
    """Async client for the HamDB.org REST API. No authentication required."""

    def __init__(self) -> None:
        self._cache: dict[str, QRZInfo | None] = {}
        self._error_log: list[str] = []
        # Sync client with connection pooling, run via asyncio.to_thread.
        # Consistent with QRZClient and avoids AsyncClient lifecycle management.
        self._http = httpx.Client(timeout=10)

    @property
    def error_log(self) -> list[str]:
        """Recent error messages, newest first."""
        return list(reversed(self._error_log))

    def _log_error(self, msg: str) -> None:
        ts = datetime.datetime.utcnow().strftime("%H:%Mz")
        self._error_log.append(f"{ts}  {msg}")
        if len(self._error_log) > _MAX_ERROR_LOG:
            self._error_log.pop(0)

    async def lookup(self, callsign: str) -> QRZInfo | None:
        """Look up a callsign. Returns None if not found or on error."""
        callsign = callsign.upper().split("/")[0]
        if callsign in self._cache:
            return self._cache[callsign]
        result = await asyncio.to_thread(self._do_lookup, callsign)
        self._cache[callsign] = result
        return result

    def _do_lookup(self, callsign: str) -> QRZInfo | None:
        url = _HAMDB_URL.format(call=callsign.lower())
        try:
            r = self._http.get(url)
            data = r.json()
            hamdb = data.get("hamdb", {})
            if hamdb.get("messages", {}).get("status") == "NOT_FOUND":
                return None
            cs_data = hamdb.get("callsign", {})
            if not cs_data or cs_data.get("call", "").upper() == "NOT_FOUND":
                return None

            fname = cs_data.get("fname", "") or ""
            lname = cs_data.get("name", "") or ""
            name = f"{fname} {lname}".strip()

            lat_s = cs_data.get("lat", "") or ""
            lon_s = cs_data.get("lon", "") or ""
            try:
                lat: float | None = float(lat_s) if lat_s else None
            except ValueError:
                lat = None
            try:
                lon: float | None = float(lon_s) if lon_s else None
            except ValueError:
                lon = None

            return QRZInfo(
                callsign=callsign,
                fname=fname,
                name=name,
                city=cs_data.get("addr2", "") or "",
                state=cs_data.get("state", "") or "",
                country=cs_data.get("country", "") or "",
                grid=cs_data.get("grid", "") or "",
                lat=lat,
                lon=lon,
            )
        except Exception as exc:
            self._log_error(f"HamDB lookup {callsign}: {exc}")
            return None
