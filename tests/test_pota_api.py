# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for POTA REST API client — spots, park lookup, self-spot, location pins."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import potatui.pota_api as pota_api_mod
from potatui.pota_api import (
    ParkInfo,
    Spot,
    fetch_location_pins,
    fetch_spots,
    is_valid_park_ref,
    lookup_park,
    self_spot,
)


def _run(coro):
    return asyncio.run(coro)


_BASE = "https://api.pota.app"


def _mock_get(json_data, status_code: int = 200) -> AsyncMock:
    """Return an AsyncMock httpx client whose .get() returns the given JSON."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=resp)
    return mock_client


def _mock_post(status_code: int = 200, text: str = "OK") -> AsyncMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    return mock_client


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset module-level globals before each test."""
    orig_pins = pota_api_mod._location_pins
    orig_http = pota_api_mod._http
    pota_api_mod._location_pins = None
    pota_api_mod._http = None
    yield
    pota_api_mod._location_pins = orig_pins
    pota_api_mod._http = orig_http


# ---------------------------------------------------------------------------
# is_valid_park_ref
# ---------------------------------------------------------------------------

class TestIsValidParkRef:
    @pytest.mark.parametrize("ref", [
        "US-1234",
        "CA-12345",
        "VK-0001",
        "K-1234",
        "DL-9999",
        "ZL-12",
        "US-A1B2",   # alphanumeric suffix
    ])
    def test_valid_refs(self, ref):
        assert is_valid_park_ref(ref) is True

    @pytest.mark.parametrize("ref", [
        "us-1234",    # lowercase — regex is case-insensitive but still valid
        "",
        "1234",
        "US",
        "US-",
        "US-1234567",  # suffix too long (>6 chars)
        "TOOLONG-1234",  # prefix too long (>4 chars)
    ])
    def test_invalid_refs(self, ref):
        # lowercase is valid per the case-insensitive regex; only test truly invalid ones
        if ref == "us-1234":
            assert is_valid_park_ref(ref) is True  # regex is case-insensitive
        elif ref == "TOOLONG-1234":
            assert is_valid_park_ref(ref) is False
        else:
            assert is_valid_park_ref(ref) is False


# ---------------------------------------------------------------------------
# lookup_park
# ---------------------------------------------------------------------------

_PARK_API_RESPONSE = {
    "reference": "US-1234",
    "name": "Test National Park",
    "locationName": "Virginia",
    "locationDesc": "US-VA",
    "stateAbbrev": "VA",
    "grid6": "FM18lv",
    "latitude": 38.9,
    "longitude": -77.0,
}


class TestLookupPark:
    def _patched_lookup(self, json_data, status_code=200, db_loaded=False):
        mock_client = _mock_get(json_data, status_code)
        with patch("potatui.park_db.park_db") as mock_db, \
             patch("potatui.pota_api._http", mock_client):
            mock_db.loaded = db_loaded
            mock_db.lookup.return_value = None
            return _run(lookup_park("US-1234", _BASE))

    def test_returns_park_info_on_success(self):
        info = self._patched_lookup(_PARK_API_RESPONSE)
        assert info is not None
        assert isinstance(info, ParkInfo)
        assert info.reference == "US-1234"
        assert info.name == "Test National Park"

    def test_state_extracted_from_location_desc(self):
        info = self._patched_lookup(_PARK_API_RESPONSE)
        assert info is not None
        assert info.state == "VA"

    def test_state_extracted_from_multi_state_location_desc(self):
        data = {**_PARK_API_RESPONSE, "locationDesc": "US-VA,US-NC"}
        info = self._patched_lookup(data)
        assert info is not None
        assert info.state == "VA"
        assert "VA" in info.locations
        assert "NC" in info.locations

    def test_lat_lon_populated(self):
        info = self._patched_lookup(_PARK_API_RESPONSE)
        assert info is not None
        assert info.lat == pytest.approx(38.9)
        assert info.lon == pytest.approx(-77.0)

    def test_grid_populated(self):
        info = self._patched_lookup(_PARK_API_RESPONSE)
        assert info is not None
        assert info.grid == "FM18lv"

    def test_returns_none_on_404(self):
        info = self._patched_lookup({}, status_code=404)
        assert info is None

    def test_returns_none_on_network_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=OSError("Connection refused"))
        with patch("potatui.park_db.park_db") as mock_db, \
             patch("potatui.pota_api._http", mock_client):
            mock_db.loaded = False
            result = _run(lookup_park("US-1234", _BASE))
        assert result is None

    def test_local_db_hit_skips_api(self):
        local_park = ParkInfo(reference="US-1234", name="Local Park", state="VA")
        mock_client = _mock_get(_PARK_API_RESPONSE)
        with patch("potatui.park_db.park_db") as mock_db, \
             patch("potatui.pota_api._http", mock_client):
            mock_db.loaded = True
            mock_db.lookup.return_value = local_park
            result = _run(lookup_park("US-1234", _BASE))
        assert result is local_park
        mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_spots
# ---------------------------------------------------------------------------

_SPOT_ITEM = {
    "activator": "W1AW",
    "reference": "US-1234",
    "name": "Test Park",
    "frequency": "14225",   # POTA API returns kHz
    "mode": "SSB",
    "spotter": "K1ABC",
    "spotTime": "2026-04-05T12:00:00",
    "comments": "Strong signal",
    "locationDesc": "US-VA",
    "grid6": "FM18",
}


class TestFetchSpots:
    def test_returns_list_of_spots(self):
        mock_client = _mock_get([_SPOT_ITEM])
        with patch("potatui.pota_api._http", mock_client):
            spots = _run(fetch_spots(_BASE))
        assert len(spots) == 1
        s = spots[0]
        assert isinstance(s, Spot)
        assert s.activator == "W1AW"
        assert s.reference == "US-1234"
        assert s.frequency == pytest.approx(14225.0)
        assert s.mode == "SSB"
        assert s.location == "VA"
        assert s.grid == "FM18"

    def test_returns_multiple_spots(self):
        items = [_SPOT_ITEM, {**_SPOT_ITEM, "activator": "K1ABC", "reference": "US-5678"}]
        mock_client = _mock_get(items)
        with patch("potatui.pota_api._http", mock_client):
            spots = _run(fetch_spots(_BASE))
        assert len(spots) == 2

    def test_skips_malformed_items(self):
        items = [
            _SPOT_ITEM,
            {"frequency": "not_a_number"},   # malformed — will fail float()... actually float("not_a_number") raises
            {**_SPOT_ITEM, "activator": "K2DEF"},
        ]
        # Note: float("not_a_number") will raise ValueError which is caught by the inner try/except
        mock_client = _mock_get(items)
        with patch("potatui.pota_api._http", mock_client):
            spots = _run(fetch_spots(_BASE))
        # Should get 2 valid spots, skip the malformed one
        assert len(spots) == 2

    def test_returns_empty_list_on_http_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=OSError("Connection refused"))
        with patch("potatui.pota_api._http", mock_client):
            spots = _run(fetch_spots(_BASE))
        assert spots == []

    def test_band_derived_from_frequency(self):
        item = {**_SPOT_ITEM, "frequency": "14225"}
        mock_client = _mock_get([item])
        with patch("potatui.pota_api._http", mock_client):
            spots = _run(fetch_spots(_BASE))
        assert spots[0].band == "20m"


# ---------------------------------------------------------------------------
# self_spot
# ---------------------------------------------------------------------------

class TestSelfSpot:
    def test_returns_true_on_200(self):
        mock_client = _mock_post(status_code=200, text="OK")
        with patch("potatui.pota_api._http", mock_client):
            ok, msg = _run(self_spot(_BASE, "W1AW", "W1AW", 14225.0, "US-1234", "SSB"))
        assert ok is True
        assert "success" in msg.lower()

    def test_returns_true_on_201(self):
        mock_client = _mock_post(status_code=201, text="Created")
        with patch("potatui.pota_api._http", mock_client):
            ok, msg = _run(self_spot(_BASE, "W1AW", "W1AW", 14225.0, "US-1234", "SSB"))
        assert ok is True

    def test_returns_false_on_400(self):
        mock_client = _mock_post(status_code=400, text="Bad request")
        with patch("potatui.pota_api._http", mock_client):
            ok, msg = _run(self_spot(_BASE, "W1AW", "W1AW", 14225.0, "US-1234", "SSB"))
        assert ok is False
        assert "400" in msg

    def test_returns_false_on_timeout(self):
        import httpx
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        with patch("potatui.pota_api._http", mock_client):
            ok, msg = _run(self_spot(_BASE, "W1AW", "W1AW", 14225.0, "US-1234", "SSB"))
        assert ok is False
        assert "timed out" in msg.lower()

    def test_returns_false_on_network_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=OSError("Connection refused"))
        with patch("potatui.pota_api._http", mock_client):
            ok, msg = _run(self_spot(_BASE, "W1AW", "W1AW", 14225.0, "US-1234", "SSB"))
        assert ok is False


# ---------------------------------------------------------------------------
# fetch_location_pins
# ---------------------------------------------------------------------------

_PINS_RESPONSE = [
    {"locationDesc": "US-VA", "latitude": 37.5, "longitude": -79.0},
    {"locationDesc": "US-CT", "latitude": 41.6, "longitude": -72.7},
]


class TestFetchLocationPins:
    def test_returns_dict_of_pins(self):
        mock_client = _mock_get(_PINS_RESPONSE)
        with patch("potatui.pota_api._http", mock_client):
            pins = _run(fetch_location_pins(_BASE))
        assert "US-VA" in pins
        assert pins["US-VA"] == pytest.approx((37.5, -79.0))
        assert "US-CT" in pins

    def test_second_call_uses_cache(self):
        mock_client = _mock_get(_PINS_RESPONSE)
        with patch("potatui.pota_api._http", mock_client):
            first = _run(fetch_location_pins(_BASE))
            second = _run(fetch_location_pins(_BASE))
        assert first is second
        assert mock_client.get.call_count == 1

    def test_skips_entries_with_missing_coords(self):
        data = [
            {"locationDesc": "US-VA", "latitude": 37.5, "longitude": -79.0},
            {"locationDesc": "US-XX"},   # missing lat/lon
        ]
        mock_client = _mock_get(data)
        with patch("potatui.pota_api._http", mock_client):
            pins = _run(fetch_location_pins(_BASE))
        assert "US-VA" in pins
        assert "US-XX" not in pins

    def test_returns_empty_dict_on_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=OSError("timeout"))
        with patch("potatui.pota_api._http", mock_client):
            pins = _run(fetch_location_pins(_BASE))
        assert pins == {}
