"""POTA REST API client — spots, park lookup, self-spot."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

PARK_REF_RE = re.compile(r"^[A-Z]{1,4}-\d{1,6}$", re.IGNORECASE)


@dataclass
class ParkInfo:
    reference: str
    name: str
    location: str = ""
    state: str = ""                          # primary 2-letter abbreviation
    grid: str = ""
    locations: list[str] = field(default_factory=list)  # all abbrevs (multi-state parks)


# US state name → 2-letter abbreviation
_US_STATE_ABBREV: dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
    "Puerto Rico": "PR", "Virgin Islands": "VI", "Guam": "GU",
    "American Samoa": "AS", "Northern Mariana Islands": "MP",
}


@dataclass
class Spot:
    activator: str
    reference: str
    park_name: str
    frequency: float  # kHz
    band: str
    mode: str
    spotter: str
    spot_time: str  # ISO string from API
    comments: str
    location: str = ""   # 2-letter state/province abbreviation when available
    grid: str = ""       # Maidenhead grid for distance calc


def is_valid_park_ref(ref: str) -> bool:
    return bool(PARK_REF_RE.match(ref.strip()))


async def lookup_park(ref: str, base_url: str) -> Optional[ParkInfo]:
    """Look up a park — local DB first, POTA API on cache miss."""
    # Check local cache first (lazy import avoids circular dependency)
    from potatui.park_db import park_db
    if park_db.loaded:
        local = park_db.lookup(ref)
        if local:
            return local

    url = f"{base_url.rstrip('/')}/park/{ref.upper()}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                location = data.get("locationName", "")
                # Parse locationDesc ("US-VA,US-NC") into list of 2-letter abbrevs
                loc_desc = data.get("locationDesc", "")
                locations = []
                for part in loc_desc.split(","):
                    part = part.strip()
                    if "-" in part:
                        locations.append(part.split("-", 1)[1])
                    elif part:
                        locations.append(part)
                # Primary state: first parsed location, then API fields, then name map
                state = (
                    (locations[0] if locations else "")
                    or data.get("stateAbbrev", "")
                    or data.get("state", "")
                    or _US_STATE_ABBREV.get(location, "")
                )
                return ParkInfo(
                    reference=data.get("reference", ref).upper(),
                    name=data.get("name", "Unknown Park"),
                    location=location,
                    state=state.strip(),
                    grid=data.get("grid6", data.get("grid4", "")),
                    locations=locations,
                )
    except Exception:
        pass
    return None


async def fetch_spots(base_url: str) -> list[Spot]:
    """Fetch current POTA activator spots."""
    url = f"{base_url.rstrip('/')}/spot/activator"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw: list[dict[str, Any]] = resp.json()
            spots = []
            for item in raw:
                try:
                    freq_khz = float(item.get("frequency", 0))
                    loc_name = item.get("locationName", "")
                    location = (
                        item.get("stateAbbrev")
                        or item.get("state")
                        or _US_STATE_ABBREV.get(loc_name, loc_name)
                    )
                    spots.append(
                        Spot(
                            activator=item.get("activator", ""),
                            reference=item.get("reference", ""),
                            park_name=item.get("name", item.get("parkName", "")),
                            frequency=freq_khz,
                            band=_freq_to_band(freq_khz),
                            mode=item.get("mode", ""),
                            spotter=item.get("spotter", ""),
                            spot_time=item.get("spotTime", ""),
                            comments=item.get("comments", ""),
                            location=location.strip(),
                            grid=item.get("grid4", item.get("grid6", "")),
                        )
                    )
                except Exception:
                    continue
            return spots
    except Exception:
        return []


async def self_spot(
    base_url: str,
    activator: str,
    spotter: str,
    freq_khz: float,
    reference: str,
    mode: str,
    comments: str = "",
) -> tuple[bool, str]:
    """Post a self-spot. Returns (success, message)."""
    url = f"{base_url.rstrip('/')}/spot"
    payload = {
        "activator": activator.upper(),
        "spotter": spotter.upper(),
        "frequency": str(freq_khz),
        "reference": reference.upper(),
        "mode": mode,
        "source": "potatui",
        "comments": comments,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 201):
                return True, "Spot posted successfully"
            return False, f"API error {resp.status_code}: {resp.text[:100]}"
    except httpx.TimeoutException:
        return False, "Request timed out"
    except Exception as e:
        return False, str(e)


def _freq_to_band(freq_khz: float) -> str:
    """Return band name for a frequency in kHz."""
    from potatui.adif import freq_to_band  # avoid circular at module load
    return freq_to_band(freq_khz)
