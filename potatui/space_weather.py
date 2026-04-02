# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""NOAA space weather data fetching — Kp index and geomagnetic storm alerts."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from potatui.log import get_logger

_log = get_logger("space_weather")

# Module-level persistent client — avoids reconstructing the SSL context and
# reading certifi's cacert.pem on every fetch call. fetch_space_weather() uses
# asyncio.gather, so without this all four coroutines would construct their own
# AsyncClient simultaneously in the same event loop tick.
_http: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http
    if _http is None:
        from potatui._ssl_ctx import ssl_ctx
        _http = httpx.AsyncClient(verify=ssl_ctx)
    return _http

_KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"
_SFI_URL = "https://services.swpc.noaa.gov/products/summary/10cm-flux.json"
_MUF_URL = "https://prop.kc2g.com/api/point_prediction.json"
_FORECAST_URL = "https://services.swpc.noaa.gov/text/3-day-forecast.txt"

# Age threshold (seconds) beyond which MUF model data is considered stale
_MUF_STALE_SECONDS = 17 * 60

# Minimum interval between API calls as requested by prop.kc2g.com
_MUF_CACHE_SECONDS = 15 * 60

# In-memory cache: maps (lat, lon) → (MufData, monotonic fetch time)
_muf_cache: dict[tuple[float, float], tuple[MufData, float]] = {}


@dataclass
class KpReading:
    time_utc: str
    kp: float


@dataclass
class SpaceWeatherAlert:
    product_id: str
    issue_datetime: str
    message: str

    @property
    def alert_key(self) -> str:
        return f"{self.product_id}|{self.issue_datetime}"


@dataclass
class KpForecastPeriod:
    label: str               # e.g. "00-03UT"
    kp: list[float | None]   # one value per forecast day (typically 3)


@dataclass
class KpForecastData:
    day_labels: list[str]              # e.g. ["Mar 19", "Mar 20", "Mar 21"]
    periods: list[KpForecastPeriod]    # 8 three-hour periods


@dataclass
class MufData:
    mufd: float
    fof2: float
    ts: int  # Unix timestamp of model data
    stale: bool  # True if data is older than _MUF_STALE_SECONDS


@dataclass
class SpaceWeatherData:
    kp_current: float | None
    kp_history: list[KpReading]
    active_alerts: list[SpaceWeatherAlert]
    sfi: float | None = None
    fetch_error: bool = False
    kp_forecast: KpForecastData | None = None


def kp_severity(kp: float) -> str:
    """Returns 'normal', 'elevated', or 'storm'."""
    if kp >= 7:
        return "storm"
    if kp >= 5:
        return "elevated"
    return "normal"


def kp_traditional(kp: float) -> str:
    """Convert a decimal Kp value to traditional notation (e.g. 2.33 → '2+')."""
    whole = int(kp)
    frac = kp - whole
    if frac < 0.17:
        suffix = ""
    elif frac < 0.5:
        suffix = "+"
    else:
        suffix = "-"
        whole += 1
    return f"{whole}{suffix}"


async def fetch_kp() -> list[KpReading]:
    """Fetch the last 8 Kp readings, newest first."""
    _t0 = time.perf_counter()
    resp = await _client().get(_KP_URL, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    # data is a list of dicts: {"time_tag": "...", "Kp": 3.0, ...}
    readings: list[KpReading] = []
    for row in data:
        try:
            readings.append(KpReading(time_utc=row["time_tag"], kp=float(row["Kp"])))
        except (KeyError, ValueError):
            continue
    # newest first, cap at 8
    readings.reverse()
    _log.debug("fetch_kp: %.0f ms", (time.perf_counter() - _t0) * 1000)
    return readings[:8]


async def fetch_sfi() -> float | None:
    """Fetch the current 10.7cm solar flux index (SFI)."""
    _t0 = time.perf_counter()
    resp = await _client().get(_SFI_URL, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    _log.debug("fetch_sfi: %.0f ms", (time.perf_counter() - _t0) * 1000)
    return float(data[0]["flux"])


async def fetch_alerts() -> list[SpaceWeatherAlert]:
    """Fetch active geomagnetic alerts from the past 8 hours."""
    _t0 = time.perf_counter()
    resp = await _client().get(_ALERTS_URL, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    cutoff = datetime.now(UTC) - timedelta(hours=8)
    alerts: list[SpaceWeatherAlert] = []

    for item in data:
        try:
            product_id: str = item.get("product_id", "")
            issue_str: str = item.get("issue_datetime", "")
            message: str = item.get("message", "")
        except (AttributeError, KeyError):
            continue

        # Parse issue_datetime — format is "2024-01-15 12:00:00.000"
        try:
            issue_dt = datetime.strptime(issue_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            continue

        if issue_dt < cutoff:
            continue

        # Strip NOAA preamble lines ("Space Weather Message Code:", "Serial Number:", "Issue Time:")
        # The actual content follows the blank line after those headers.
        _preamble = {"space weather message code", "serial number", "issue time"}
        lines = message.splitlines()
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip().lower().split(":")[0] in _preamble or line.strip() == "":
                content_start = i + 1
            else:
                break
        message = "\n".join(lines[content_start:]).strip()

        alerts.append(SpaceWeatherAlert(
            product_id=product_id,
            issue_datetime=issue_str,
            message=message,
        ))

    _log.debug("fetch_alerts: %.0f ms, %d active", (time.perf_counter() - _t0) * 1000, len(alerts))
    return alerts


async def fetch_muf(lat: float, lon: float) -> MufData:
    """Fetch MUF prediction for the given lat/lon, cached for 15 min per api owner request."""
    import time as _time

    key = (round(lat, 4), round(lon, 4))
    cached = _muf_cache.get(key)
    if cached is not None:
        result, fetched_at = cached
        if _time.monotonic() - fetched_at < _MUF_CACHE_SECONDS:
            _log.debug("fetch_muf (%.4f, %.4f): in-memory cache hit", lat, lon)
            return result

    _t0 = time.perf_counter()
    resp = await _client().get(_MUF_URL, params={"grid": f"{lat},{lon}"}, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    mufd = float(data["mufd"])
    fof2 = float(data["fof2"])
    ts = int(data["ts"])
    stale = (_time.time() - ts) > _MUF_STALE_SECONDS
    result = MufData(mufd=mufd, fof2=fof2, ts=ts, stale=stale)
    _muf_cache[key] = (result, _time.monotonic())
    _log.debug("fetch_muf (%.4f, %.4f): %.0f ms, mufd=%.1f stale=%s", lat, lon, (time.perf_counter() - _t0) * 1000, mufd, stale)
    return result


async def fetch_kp_forecast() -> KpForecastData | None:
    """Fetch and parse the NOAA 3-day Kp index forecast."""
    resp = await _client().get(_FORECAST_URL, timeout=10.0)
    resp.raise_for_status()
    text = resp.text

    lines = text.splitlines()

    # Locate "NOAA Kp index breakdown" section
    section_start: int | None = None
    for i, line in enumerate(lines):
        if "NOAA Kp index breakdown" in line:
            section_start = i
            break
    if section_start is None:
        return None

    # Next non-blank line after section_start should be blank, then the date header
    day_labels: list[str] = []
    period_start: int | None = None
    for i in range(section_start + 1, min(section_start + 6, len(lines))):
        line = lines[i]
        found = re.findall(r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+', line)
        if found:
            day_labels = found
            period_start = i + 1
            break

    if not day_labels or period_start is None:
        return None

    # Parse "HH-HHUT  val val val" rows
    periods: list[KpForecastPeriod] = []
    for i in range(period_start, len(lines)):
        m = re.match(r'^\s*(\d{2}-\d{2}UT)\s+(.*)', lines[i])
        if not m:
            if periods:
                break
            continue
        kp_vals = re.findall(r'\d+\.\d+', m.group(2))
        kp: list[float | None] = []
        for j in range(len(day_labels)):
            if j < len(kp_vals):
                try:
                    kp.append(float(kp_vals[j]))
                except ValueError:
                    kp.append(None)
            else:
                kp.append(None)
        periods.append(KpForecastPeriod(label=m.group(1), kp=kp))

    if not periods:
        return None

    return KpForecastData(day_labels=day_labels, periods=periods)


async def fetch_space_weather() -> SpaceWeatherData:
    """Fetch Kp index, SFI, alerts, and 3-day forecast; never raises."""
    _t0 = time.perf_counter()
    results = await asyncio.gather(
        fetch_kp(), fetch_alerts(), fetch_sfi(), fetch_kp_forecast(),
        return_exceptions=True,
    )

    kp_result = results[0]
    alerts_result = results[1]
    sfi_result = results[2]
    forecast_result = results[3]

    fetch_error = isinstance(kp_result, BaseException) or isinstance(alerts_result, BaseException)

    kp_history: list[KpReading] = kp_result if isinstance(kp_result, list) else []
    active_alerts: list[SpaceWeatherAlert] = alerts_result if isinstance(alerts_result, list) else []
    sfi: float | None = sfi_result if isinstance(sfi_result, float) else None
    kp_forecast: KpForecastData | None = forecast_result if isinstance(forecast_result, KpForecastData) else None

    kp_current = kp_history[0].kp if kp_history else None

    _log.debug(
        "fetch_space_weather: %.0f ms total (error=%s, kp=%s, sfi=%s, alerts=%d)",
        (time.perf_counter() - _t0) * 1000,
        fetch_error,
        kp_current,
        sfi,
        len(active_alerts),
    )
    return SpaceWeatherData(
        kp_current=kp_current,
        kp_history=kp_history,
        active_alerts=active_alerts,
        sfi=sfi,
        fetch_error=fetch_error,
        kp_forecast=kp_forecast,
    )
