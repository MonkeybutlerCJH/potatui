# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for MUF fetching and caching in space_weather.py."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from potatui.space_weather import (
    _MUF_CACHE_SECONDS,
    _MUF_STALE_SECONDS,
    MufData,
    _muf_cache,
    fetch_muf,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(mufd: float, fof2: float, ts: int) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"mufd": mufd, "fof2": fof2, "ts": ts}
    mock.raise_for_status = MagicMock()
    return mock


def _patch_client(mufd=14.0, fof2=8.0, ts=None) -> AsyncMock:
    """Return an AsyncMock httpx client for patching potatui.space_weather._http."""
    if ts is None:
        ts = int(time.time()) - 60  # fresh
    mock_resp = _make_response(mufd, fof2, ts)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client


def _fresh_ts() -> int:
    return int(time.time()) - 60


def _stale_ts() -> int:
    return int(time.time()) - _MUF_STALE_SECONDS - 60


# ---------------------------------------------------------------------------
# MufData.stale flag
# ---------------------------------------------------------------------------

class TestMufDataStale:
    def test_fresh_data_not_stale(self):
        data = MufData(mufd=14.0, fof2=8.0, ts=_fresh_ts(), stale=False)
        assert data.stale is False

    def test_old_data_is_stale(self):
        data = MufData(mufd=14.0, fof2=8.0, ts=_stale_ts(), stale=True)
        assert data.stale is True


# ---------------------------------------------------------------------------
# fetch_muf — HTTP call and response parsing
# ---------------------------------------------------------------------------

class TestFetchMuf:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        _muf_cache.clear()
        yield
        _muf_cache.clear()

    def test_returns_muf_data(self):
        ts = _fresh_ts()
        mock_client = _patch_client(mufd=14.253, fof2=8.431, ts=ts)

        with patch("potatui.space_weather._http", mock_client):
            result = _run(fetch_muf(45.0, -75.0))

        assert isinstance(result, MufData)
        assert result.mufd == pytest.approx(14.253)
        assert result.fof2 == pytest.approx(8.431)
        assert result.ts == ts
        assert result.stale is False

    def test_stale_flag_set_for_old_ts(self):
        ts = _stale_ts()
        mock_client = _patch_client(mufd=10.0, fof2=6.0, ts=ts)

        with patch("potatui.space_weather._http", mock_client):
            result = _run(fetch_muf(45.0, -75.0))

        assert result.stale is True

    def test_query_param_uses_lat_lon(self):
        mock_client = _patch_client()

        with patch("potatui.space_weather._http", mock_client):
            _run(fetch_muf(44.5, -76.2))

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params", {})
        assert "grid" in params
        assert "44.5" in params["grid"]
        assert "-76.2" in params["grid"]


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------

class TestFetchMufCache:
    @pytest.fixture(autouse=True)
    def clear_cache(self):
        _muf_cache.clear()
        yield
        _muf_cache.clear()

    def test_second_call_uses_cache(self):
        mock_client = _patch_client()

        with patch("potatui.space_weather._http", mock_client):
            first = _run(fetch_muf(45.0, -75.0))
            second = _run(fetch_muf(45.0, -75.0))

        assert mock_client.get.call_count == 1
        assert first is second

    def test_different_location_not_cached(self):
        mock_client = _patch_client()

        with patch("potatui.space_weather._http", mock_client):
            _run(fetch_muf(45.0, -75.0))
            _run(fetch_muf(50.0, -80.0))

        assert mock_client.get.call_count == 2

    def test_expired_cache_refetches(self):
        mock_client = _patch_client(mufd=14.0)

        with patch("potatui.space_weather._http", mock_client):
            _run(fetch_muf(45.0, -75.0))

        # Backdate the cache entry so it appears expired
        key = (45.0, -75.0)
        data, _ = _muf_cache[key]
        _muf_cache[key] = (data, time.monotonic() - _MUF_CACHE_SECONDS - 1)

        mock_client2 = _patch_client(mufd=16.0)
        with patch("potatui.space_weather._http", mock_client2):
            result = _run(fetch_muf(45.0, -75.0))

        assert mock_client2.get.call_count == 1
        assert result.mufd == pytest.approx(16.0)

    def test_cache_populated_after_fetch(self):
        mock_client = _patch_client()

        with patch("potatui.space_weather._http", mock_client):
            _run(fetch_muf(45.0, -75.0))

        assert (45.0, -75.0) in _muf_cache

    def test_cache_key_rounds_latlon(self):
        """Tiny coordinate differences within rounding precision share a cache slot."""
        mock_client = _patch_client()

        with patch("potatui.space_weather._http", mock_client):
            _run(fetch_muf(45.00001, -75.00001))
            _run(fetch_muf(45.00002, -75.00002))

        assert mock_client.get.call_count == 1
