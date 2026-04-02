# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Local POTA park database — cached CSV for offline use."""

from __future__ import annotations

import csv
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from platformdirs import user_data_dir

from potatui.log import get_logger

_log = get_logger("park_db")

_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        from potatui._ssl_ctx import ssl_ctx
        _http = httpx.AsyncClient(verify=ssl_ctx)
    return _http

if TYPE_CHECKING:
    from potatui.pota_api import ParkInfo

DATA_DIR = Path(user_data_dir("potatui", appauthor=False))
PARKS_CSV = DATA_DIR / "parks.csv"
PARKS_CSV_URL = "https://pota.app/all_parks_ext.csv"
REFRESH_DAYS = 30

class ParkDb:
    """In-memory park database loaded from the cached CSV file."""

    # Parks that are always available regardless of the downloaded CSV.
    # K-TEST is the official POTA test park used for software testing.
    _BUILTINS: dict[str, ParkInfo] = {}  # populated in _init_builtins()

    def __init__(self) -> None:
        self._parks: dict[str, ParkInfo] = {}
        self._init_builtins()

    def load(self) -> None:
        """Load parks from the CSV into memory. Safe to call multiple times."""
        from potatui.pota_api import ParkInfo

        if not PARKS_CSV.exists():
            _log.debug("park_db.load: CSV not found, skipping")
            return

        _t0 = time.perf_counter()
        parks: dict[str, ParkInfo] = {}
        try:
            with open(PARKS_CSV, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ref = (row.get("reference") or "").strip().upper()
                    if not ref:
                        continue
                    # Parse locationDesc ("US-VA,US-NC") into list of 2-letter abbrevs
                    loc_desc = row.get("locationDesc") or ""
                    locations: list[str] = []
                    for part in loc_desc.split(","):
                        part = part.strip()
                        if "-" in part:
                            locations.append(part.split("-", 1)[1])
                        elif part:
                            locations.append(part)
                    # CSV locationDesc is "US-ME" or "US-DC,US-MD,US-WV"
                    # locations list already contains 2-letter abbrevs e.g. ["ME"] or ["DC","MD","WV"]
                    state = locations[0] if locations else ""
                    # CSV has a single "grid" column (6-char Maidenhead)
                    grid = (row.get("grid") or "").strip()
                    lat_s = (row.get("latitude") or "").strip()
                    lon_s = (row.get("longitude") or "").strip()
                    try:
                        park_lat = float(lat_s) if lat_s else None
                        park_lon = float(lon_s) if lon_s else None
                    except (ValueError, TypeError):
                        park_lat, park_lon = None, None
                    parks[ref] = ParkInfo(
                        reference=ref,
                        name=(row.get("name") or "Unknown Park").strip(),
                        location=loc_desc,  # e.g. "US-ME" — consistent with API locationDesc
                        state=state,
                        grid=grid,
                        locations=locations,
                        lat=park_lat,
                        lon=park_lon,
                    )
        except Exception as exc:
            _log.debug("park_db.load: failed in %.0f ms — %s", (time.perf_counter() - _t0) * 1000, exc)
            return

        self._parks = parks
        _log.debug("park_db.load: %.0f ms, %d parks", (time.perf_counter() - _t0) * 1000, len(parks))

    def _init_builtins(self) -> None:
        """Populate the class-level builtins dict once."""
        if ParkDb._BUILTINS:
            return
        from potatui.pota_api import ParkInfo

        ParkDb._BUILTINS = {
            "K-TEST": ParkInfo(
                reference="K-TEST",
                name="POTA Test Park",
                location="",
                state="",
                grid="",
                locations=[],
                lat=None,
                lon=None,
            ),
        }

    def lookup(self, ref: str) -> ParkInfo | None:
        """Return ParkInfo for a reference, or None if not found."""
        key = ref.strip().upper()
        return self._parks.get(key) or ParkDb._BUILTINS.get(key)

    def search_parks(self, query: str, limit: int = 15) -> list[ParkInfo]:
        """Search by name substring or ref prefix (case-insensitive). Runs synchronously."""
        if not query:
            return []
        q = query.strip().lower()
        results: list[ParkInfo] = []
        seen: set[str] = set()
        for source in (self._parks, ParkDb._BUILTINS):
            for park in source.values():
                if park.reference in seen:
                    continue
                if q in park.name.lower() or park.reference.lower().startswith(q):
                    results.append(park)
                    seen.add(park.reference)
                    if len(results) >= limit:
                        return results
        return results

    @property
    def loaded(self) -> bool:
        return bool(self._parks)

    @property
    def count(self) -> int:
        return len(self._parks)

    @property
    def db_updated(self) -> str | None:
        """Return the CSV last-modified date as 'YYYY-MM-DD', or None if not downloaded."""
        if not PARKS_CSV.exists():
            return None
        mtime = PARKS_CSV.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")

    @property
    def db_age_days(self) -> int | None:
        """Return age of the CSV in whole days, or None if not downloaded."""
        if not PARKS_CSV.exists():
            return None
        return int((time.time() - PARKS_CSV.stat().st_mtime) / 86400)

    def needs_download(self) -> bool:
        """True if the CSV has never been downloaded."""
        return not PARKS_CSV.exists()

    def needs_refresh(self) -> bool:
        """True if the CSV exists but is older than REFRESH_DAYS."""
        if not PARKS_CSV.exists():
            return False
        age_days = (time.time() - PARKS_CSV.stat().st_mtime) / 86400
        return age_days >= REFRESH_DAYS


async def download_parks() -> tuple[bool, str]:
    """Download the POTA all-parks CSV. Returns (success, message)."""
    _t0 = time.perf_counter()
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        resp = await _client().get(PARKS_CSV_URL, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        PARKS_CSV.write_bytes(resp.content)
        kb = len(resp.content) // 1024
        _log.debug("download_parks: %.0f ms, %d KB", (time.perf_counter() - _t0) * 1000, kb)
        return True, f"Downloaded {kb} KB"
    except httpx.HTTPStatusError as e:
        _log.debug("download_parks: HTTP %s in %.0f ms", e.response.status_code, (time.perf_counter() - _t0) * 1000)
        return False, f"HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        _log.debug("download_parks: timed out after %.0f ms", (time.perf_counter() - _t0) * 1000)
        return False, "Request timed out"
    except Exception as e:
        _log.debug("download_parks: error in %.0f ms — %s", (time.perf_counter() - _t0) * 1000, e)
        return False, str(e)


async def check_internet(host: str = "https://api.pota.app") -> bool:
    """Quick connectivity check — True if host is reachable."""
    try:
        await _client().head(host, timeout=3, follow_redirects=True)
        return True
    except Exception:
        return False


# Module-level singleton loaded at app startup.
park_db = ParkDb()
