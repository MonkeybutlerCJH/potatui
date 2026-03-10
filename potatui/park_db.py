"""Local POTA park database — cached CSV for offline use."""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx
from platformdirs import user_data_dir

if TYPE_CHECKING:
    from potatui.pota_api import ParkInfo

DATA_DIR = Path(user_data_dir("potatui", appauthor=False))
PARKS_CSV = DATA_DIR / "parks.csv"
PARKS_CSV_URL = "https://pota.app/all_parks_ext.csv"
REFRESH_DAYS = 30


class ParkDb:
    """In-memory park database loaded from the cached CSV file."""

    def __init__(self) -> None:
        self._parks: dict[str, "ParkInfo"] = {}

    def load(self) -> None:
        """Load parks from the CSV into memory. Safe to call multiple times."""
        from potatui.pota_api import ParkInfo, _US_STATE_ABBREV

        if not PARKS_CSV.exists():
            return

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
        except Exception:
            return

        self._parks = parks

    def lookup(self, ref: str) -> Optional["ParkInfo"]:
        """Return ParkInfo for a reference, or None if not found."""
        return self._parks.get(ref.strip().upper())

    def search_parks(self, query: str, limit: int = 15) -> list["ParkInfo"]:
        """Search by name substring or ref prefix (case-insensitive). Runs synchronously."""
        if not self._parks or not query:
            return []
        q = query.strip().lower()
        results: list["ParkInfo"] = []
        for park in self._parks.values():
            if q in park.name.lower() or park.reference.lower().startswith(q):
                results.append(park)
                if len(results) >= limit:
                    break
        return results

    @property
    def loaded(self) -> bool:
        return bool(self._parks)

    @property
    def count(self) -> int:
        return len(self._parks)

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
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(PARKS_CSV_URL)
            resp.raise_for_status()
            PARKS_CSV.write_bytes(resp.content)
        return True, f"Downloaded {len(resp.content) // 1024} KB"
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        return False, "Request timed out"
    except Exception as e:
        return False, str(e)


async def check_internet(host: str = "https://api.pota.app") -> bool:
    """Quick connectivity check — True if host is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
            await client.head(host)
        return True
    except Exception:
        return False


# Module-level singleton loaded at app startup.
park_db = ParkDb()
