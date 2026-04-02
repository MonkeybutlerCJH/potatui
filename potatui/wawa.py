# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)
"""WAWA easter egg — find your nearest hoagie via OpenStreetMap."""

from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

# Cache results so repeated triggers in the same session skip the network call.
# Key: (lat rounded to 2dp, lon rounded to 2dp)  Value: (address, dist_km) | None
_cache: dict[tuple[float, float], tuple[str, float] | None] = {}

WAWA_ASCII = r"""
        * ~ HOAGIEFEST ~ *

 ██╗    ██╗ █████╗ ██╗    ██╗ █████╗
 ██║    ██║██╔══██╗██║    ██║██╔══██╗
 ██║ █╗ ██║███████║██║ █╗ ██║███████║
 ██║███╗██║██╔══██║██║███╗██║██╔══██║
 ╚███╔███╔╝██║  ██║╚███╔███╔╝██║  ██║
  ╚══╝╚══╝ ╚═╝  ╚═╝ ╚══╝╚══╝ ╚═╝  ╚═╝

     Your nearest hoagie awaits
"""

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_UA = "Potatui/1.0 (https://github.com/MonkeybutlerCJH/potatui)"


async def _overpass_get(client: object, query: str) -> dict[str, Any]:
    """GET the Overpass interpreter, retrying once on 504."""
    url = _OVERPASS_URL + "?data=" + urllib.parse.quote(query)
    resp = await client.get(url)  # type: ignore[attr-defined]
    if resp.status_code == 429:
        raise RuntimeError("rate_limited")
    if resp.status_code == 504:
        await asyncio.sleep(3)
        resp = await client.get(url)  # type: ignore[attr-defined]
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


async def _nominatim_city(client: object, lat: float, lon: float) -> str:
    """Best-effort reverse geocode to get 'City, ST' for a coordinate."""
    try:
        resp = await client.get(  # type: ignore[attr-defined]
            _NOMINATIM_URL,
            params={"format": "json", "lat": lat, "lon": lon, "zoom": 16},
        )
        if resp.status_code != 200:
            return ""
        addr = resp.json().get("address", {})
        city = addr.get("city") or addr.get("town") or addr.get("village", "")
        state = addr.get("state", "")
        if city and state:
            return f"{city}, {state}"
        return str(city or state)
    except Exception:
        return ""


async def find_nearest_wawa_osm(
    lat: float, lon: float, use_miles: bool
) -> tuple[str, float] | None:
    """Query Overpass for nearest Wawa within 50 miles (~80,500 m).

    Returns (address, distance) or None if none found within range.
    Raises on HTTP/timeout errors so the caller can distinguish network
    failure from "not found".
    """
    import httpx  # local import — wawa is an easter egg, keep it out of startup cost

    from potatui.qrz import haversine_km

    cache_key = (round(lat, 2), round(lon, 2))
    if cache_key in _cache:
        cached = _cache[cache_key]
        if cached is None:
            return None
        addr, dist_km = cached
        return (addr, dist_km * 0.621371) if use_miles else (addr, dist_km)

    query = (
        f'[out:json][timeout:25];'
        f'node["brand"="Wawa"](around:80500,{lat},{lon});'
        f'out body;'
    )

    from potatui._ssl_ctx import ssl_ctx

    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": _UA}, verify=ssl_ctx
    ) as client:
        data = await _overpass_get(client, query)

        elements = data.get("elements", [])

        best_node: dict | None = None
        best_dist_km = float("inf")

        for node in elements:
            node_lat = node.get("lat")
            node_lon = node.get("lon")
            if node_lat is None or node_lon is None:
                continue
            dist_km = haversine_km(lat, lon, node_lat, node_lon)
            if dist_km < best_dist_km:
                best_dist_km = dist_km
                best_node = node

        # 50 miles = 80.4672 km
        if best_node is None or best_dist_km > 80.4672:
            _cache[cache_key] = None
            return None

        tags = best_node.get("tags", {})
        parts: list[str] = []
        house = tags.get("addr:housenumber", "")
        street = tags.get("addr:street", "")
        if house and street:
            parts.append(f"{house} {street}")
        elif street:
            parts.append(street)
        city = tags.get("addr:city", "")
        if city:
            parts.append(city)
        state = tags.get("addr:state", "")
        postcode = tags.get("addr:postcode", "")
        if state and postcode:
            parts.append(f"{state} {postcode}")
        elif state:
            parts.append(state)

        if not parts:
            # No address tags — try Nominatim reverse geocode for city/state
            location = await _nominatim_city(client, best_node["lat"], best_node["lon"])
            best_addr = location if location else tags.get("name", "Wawa")
        else:
            best_addr = ", ".join(parts)

    _cache[cache_key] = (best_addr, best_dist_km)
    if use_miles:
        return (best_addr, best_dist_km * 0.621371)
    return (best_addr, best_dist_km)
