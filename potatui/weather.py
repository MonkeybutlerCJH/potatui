# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Terrestrial weather data fetching from the US National Weather Service API.

The NWS API (api.weather.gov) is free, requires no authentication, and covers
US states and territories. Non-US coordinates will 404 gracefully — the top-level
fetch_weather() never raises.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

from potatui.log import get_logger

_log = get_logger("weather")

# Module-level persistent client — avoids reconstructing the SSL context and
# reading certifi's cacert.pem on every fetch call.
_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        from potatui._ssl_ctx import ssl_ctx
        _http = httpx.AsyncClient(verify=ssl_ctx)
    return _http


# NWS requires a User-Agent header per their API policy
_USER_AGENT = "Potatui/1.0 (TUI POTA Logger; https://github.com/MonkeybutlerCJH)"

# Cache TTLs in seconds
_POINTS_CACHE_SECONDS = 86400        # 24h — grid points don't change
_FORECAST_CACHE_SECONDS = 600        # 10 min
_FORECAST_HOURLY_CACHE_SECONDS = 300  # 5 min
_OBSERVATIONS_CACHE_SECONDS = 600    # 10 min
_ALERTS_CACHE_SECONDS = 300          # 5 min — alerts can appear quickly

# In-memory cache: key → (data, monotonic fetch time)
_weather_cache: dict[str, tuple[object, float]] = {}


def _cache_get(key: str, ttl: float) -> object | None:
    cached = _weather_cache.get(key)
    if cached is not None:
        result, fetched_at = cached
        if time.monotonic() - fetched_at < ttl:
            return result
    return None


def _cache_set(key: str, data: object) -> None:
    _weather_cache[key] = (data, time.monotonic())


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WeatherObservation:
    """Current weather conditions from the nearest NWS observation station."""
    temperature_f: float | None
    humidity: int | None           # percentage
    wind_speed_mph: float | None
    wind_direction: str | None     # cardinal, e.g. "NW"
    conditions: str                # textDescription from NWS, e.g. "Mostly Cloudy"
    icon_url: str | None
    timestamp: str | None          # ISO 8601


@dataclass
class WeatherForecastPeriod:
    """One forecast period (day, night, or hourly) from the NWS gridpoint forecast."""
    name: str                      # "Today", "Tonight", "Wednesday Night"
    temperature: int
    temperature_unit: str          # "F" or "C"
    wind_speed: str                # "5 to 10 mph"
    wind_direction: str
    short_forecast: str            # "Mostly Sunny"
    detailed_forecast: str         # Longer text description
    icon_url: str | None
    is_daytime: bool


@dataclass
class WeatherAlert:
    """A weather alert/warning from the NWS alerts endpoint."""
    id: str                        # NWS unique identifier
    event: str                     # "Tornado Warning", "Severe Thunderstorm Warning"
    headline: str                  # Short headline
    description: str               # Full description
    severity: str                  # "Extreme", "Severe", "Moderate", "Minor", "Unknown"
    effective: str
    expires: str
    instruction: str | None        # "Take shelter..." if available

    @property
    def alert_key(self) -> str:
        return self.id


@dataclass
class WeatherData:
    """Aggregated weather data for a location; returned by fetch_weather()."""
    observation: WeatherObservation | None
    forecast: list[WeatherForecastPeriod] = field(default_factory=list)
    forecast_hourly: list[WeatherForecastPeriod] = field(default_factory=list)
    alerts: list[WeatherAlert] = field(default_factory=list)
    fetch_error: bool = False
    location_name: str = ""


# ---------------------------------------------------------------------------
# Weather emoji helper
# ---------------------------------------------------------------------------

# Ordered list of (compiled regex, emoji) — first match wins
_EMOJI_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r'(thunderstorm|t-storm|t storm|tornado)', re.I), '⛈️'),
    (re.compile(r'(freezing|ice|sleet|hail)', re.I), '🌨️'),
    (re.compile(r'(snow|blizzard|flurr)', re.I), '❄️'),
    (re.compile(r'(rain|drizzle|shower)', re.I), '🌧️'),
    (re.compile(r'(fog|mist|haze|smoke)', re.I), '🌫️'),
    (re.compile(r'(windy|breezy|wind)', re.I), '💨'),
    (re.compile(r'(partly cloudy|mostly cloudy)', re.I), '⛅'),
    (re.compile(r'(cloudy|overcast)', re.I), '☁️'),
    (re.compile(r'(mostly sunny|partly sunny)', re.I), '🌤️'),
    (re.compile(r'(fair|clear|sunny|hot)', re.I), '☀️'),
]


def _weather_emoji(short_forecast: str) -> str:
    """Map an NWS short forecast string to an emoji character."""
    for pattern, emoji in _EMOJI_MAP:
        if pattern.search(short_forecast):
            return emoji
    return '🌡️'  # default: thermometer


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def _fetch_points(lat: float, lon: float) -> dict | None:
    """Fetch /points/{lat},{lon} — cached 24h per (rounded lat, lon)."""
    key = f"points|{lat:.2f}|{lon:.2f}"
    cached = _cache_get(key, _POINTS_CACHE_SECONDS)
    if cached is not None:
        return cached  # type: ignore[return-value]

    _t0 = time.perf_counter()
    url = f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
    try:
        resp = await _client().get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
        resp.raise_for_status()
    except Exception:
        _log.debug("_fetch_points(%.4f, %.4f): failed", lat, lon)
        return None
    data = resp.json()["properties"]
    _cache_set(key, data)
    _log.debug("_fetch_points(%.4f, %.4f): %.0f ms", lat, lon, (time.perf_counter() - _t0) * 1000)
    return data  # type: ignore[no-any-return]


def _parse_period(p: dict) -> WeatherForecastPeriod:
    return WeatherForecastPeriod(
        name=p.get("name", ""),
        temperature=p.get("temperature", 0),
        temperature_unit=p.get("temperatureUnit", "F"),
        wind_speed=p.get("windSpeed", ""),
        wind_direction=p.get("windDirection", ""),
        short_forecast=p.get("shortForecast", ""),
        detailed_forecast=p.get("detailedForecast", ""),
        icon_url=p.get("icon"),
        is_daytime=p.get("isDaytime", True),
    )


# ---------------------------------------------------------------------------
# Public fetch functions (each standalone for asyncio.gather)
# ---------------------------------------------------------------------------


async def fetch_observation(lat: float, lon: float) -> WeatherObservation | None:
    """Fetch current observations from the nearest NWS station."""
    points = await _fetch_points(lat, lon)
    if not points:
        return None

    _t0 = time.perf_counter()
    stations_url = points.get("observationStations")
    if not stations_url:
        return None

    try:
        stations_resp = await _client().get(stations_url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
        stations_resp.raise_for_status()
        stations = stations_resp.json().get("features", [])
    except Exception:
        _log.debug("fetch_observation: station list failed")
        return None

    if not stations:
        return None

    # Try up to 5 stations, preferring ones that report a text description.
    # Some AWOS stations (e.g. KLYO) return data but with empty textDescription
    # and no icon — keep looking for a better station.
    fallback: WeatherObservation | None = None

    for station in stations[:5]:
        station_id = station["properties"]["stationIdentifier"]
        obs_url = f"https://api.weather.gov/stations/{station_id}/observations/latest"

        try:
            resp = await _client().get(obs_url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
            resp.raise_for_status()
            props = resp.json()["properties"]
        except Exception:
            _log.debug("fetch_observation: station %s request failed", station_id)
            continue

        # NWS returns values in metric; convert to imperial.
        # Use `or {}` because dict.get(key, default) returns default only if the
        # key is missing — if the key exists but the value is JSON null, .get()
        # returns None, and chaining .get("value") on None would raise.
        temp_c = (props.get("temperature") or {}).get("value")
        temp_f = (temp_c * 9 / 5 + 32) if temp_c is not None else None

        wind_kmh = (props.get("windSpeed") or {}).get("value")
        wind_mph = (wind_kmh / 1.60934) if wind_kmh is not None else None

        wind_dir_deg = (props.get("windDirection") or {}).get("value")
        wind_dir = _degrees_to_cardinal(wind_dir_deg) if wind_dir_deg is not None else None

        humidity = (props.get("relativeHumidity") or {}).get("value")
        conditions = props.get("textDescription", "")
        icon = props.get("icon")

        obs = WeatherObservation(
            temperature_f=temp_f,
            humidity=humidity,
            wind_speed_mph=wind_mph,
            wind_direction=wind_dir,
            conditions=conditions,
            icon_url=icon,
            timestamp=props.get("timestamp"),
        )

        # Prefer stations that have actual temperature data — some stations
        # report a textDescription/icon but no sensor values (e.g. KGXF).
        if temp_f is not None:
            _log.debug("fetch_observation(%.4f, %.4f): %.0f ms (station %s)",
                       lat, lon, (time.perf_counter() - _t0) * 1000, station_id)
            return obs

        # Keep the first station with any data as a last-resort fallback
        if fallback is None:
            fallback = obs

    if fallback is not None:
        _log.debug("fetch_observation(%.4f, %.4f): using fallback station", lat, lon)
        return fallback

    _log.debug("fetch_observation(%.4f, %.4f): all stations failed", lat, lon)
    return None


def _degrees_to_cardinal(deg: float) -> str:
    """Convert a wind direction in degrees to a 16-point cardinal string."""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return dirs[idx]


async def fetch_forecast(lat: float, lon: float) -> list[WeatherForecastPeriod]:
    """Fetch 7-day day/night forecast from the NWS gridpoint."""
    points = await _fetch_points(lat, lon)
    if not points or "forecast" not in points:
        return []

    _t0 = time.perf_counter()
    try:
        resp = await _client().get(points["forecast"], headers={"User-Agent": _USER_AGENT}, timeout=10.0)
        resp.raise_for_status()
        periods = resp.json()["properties"]["periods"]
    except Exception:
        _log.debug("fetch_forecast: failed")
        return []

    _log.debug("fetch_forecast: %.0f ms, %d periods", (time.perf_counter() - _t0) * 1000, len(periods))
    return [_parse_period(p) for p in periods]


async def fetch_forecast_hourly(lat: float, lon: float) -> list[WeatherForecastPeriod]:
    """Fetch hourly forecast from the NWS gridpoint."""
    points = await _fetch_points(lat, lon)
    if not points or "forecastHourly" not in points:
        return []

    _t0 = time.perf_counter()
    try:
        resp = await _client().get(points["forecastHourly"], headers={"User-Agent": _USER_AGENT}, timeout=10.0)
        resp.raise_for_status()
        periods = resp.json()["properties"]["periods"]
    except Exception:
        _log.debug("fetch_forecast_hourly: failed")
        return []

    _log.debug("fetch_forecast_hourly: %.0f ms, %d periods", (time.perf_counter() - _t0) * 1000, len(periods))
    return [_parse_period(p) for p in periods]


async def fetch_alerts(lat: float, lon: float) -> list[WeatherAlert]:
    """Fetch active weather alerts for the given point."""
    _t0 = time.perf_counter()
    url = f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
    try:
        resp = await _client().get(url, headers={"User-Agent": _USER_AGENT}, timeout=10.0)
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except Exception:
        _log.debug("fetch_alerts: failed")
        return []

    alerts: list[WeatherAlert] = []
    for f in features:
        p = f["properties"]
        alerts.append(WeatherAlert(
            id=p.get("id", ""),
            event=p.get("event", "Unknown"),
            headline=p.get("headline", ""),
            description=p.get("description", ""),
            severity=p.get("severity", "Unknown"),
            effective=p.get("effective", ""),
            expires=p.get("expires", ""),
            instruction=p.get("instruction"),
        ))

    _log.debug("fetch_alerts: %.0f ms, %d alerts", (time.perf_counter() - _t0) * 1000, len(alerts))
    return alerts


async def fetch_weather(lat: float, lon: float) -> WeatherData:
    """Fetch observations, forecast, and alerts for a location; never raises."""
    _t0 = time.perf_counter()

    points_results = await asyncio.gather(
        _fetch_points(lat, lon),
        return_exceptions=True,
    )
    points_result = points_results[0]
    if isinstance(points_result, BaseException) or points_result is None:
        _log.debug("fetch_weather(%.4f, %.4f): points lookup failed, aborting", lat, lon)
        return WeatherData(
            observation=None, forecast=[], forecast_hourly=[], alerts=[],
            fetch_error=True, location_name="",
        )

    location_name = "".join([
        points_result.get("relativeLocation", {}).get("properties", {}).get("city", ""),
        ", ",
        points_result.get("relativeLocation", {}).get("properties", {}).get("state", ""),
    ]).strip(", ")

    results = await asyncio.gather(
        fetch_observation(lat, lon),
        fetch_forecast(lat, lon),
        fetch_forecast_hourly(lat, lon),
        fetch_alerts(lat, lon),
        return_exceptions=True,
    )

    obs_res, fcst_res, hfcst_res, alert_res = results

    fetch_error = any(isinstance(r, BaseException) for r in results)

    obs = obs_res if isinstance(obs_res, WeatherObservation) else None
    forecast = fcst_res if isinstance(fcst_res, list) else []
    hourly = hfcst_res if isinstance(hfcst_res, list) else []
    alerts = alert_res if isinstance(alert_res, list) else []

    _log.debug(
        "fetch_weather(%.4f, %.4f): %.0f ms total (error=%s, obs=%s, forecast=%d, alerts=%d)",
        lat, lon, (time.perf_counter() - _t0) * 1000,
        fetch_error, obs is not None, len(forecast), len(alerts),
    )

    return WeatherData(
        observation=obs,
        forecast=forecast,
        forecast_hourly=hourly,
        alerts=alerts,
        fetch_error=fetch_error,
        location_name=location_name,
    )
