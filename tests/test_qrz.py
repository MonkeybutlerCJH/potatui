# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for QRZ API client and grid/distance utilities."""

import asyncio
from unittest.mock import MagicMock

import pytest

from potatui.qrz import (
    QRZClient,
    QRZInfo,
    bearing_deg,
    cardinal,
    distance_from_grid,
    grid_to_latlon,
    haversine_km,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# XML fixtures
# ---------------------------------------------------------------------------

_LOGIN_OK = """<?xml version="1.0"?>
<QRZDatabase xmlns="http://xmldata.qrz.com" version="1.34">
  <Session><Key>testkey123</Key></Session>
</QRZDatabase>"""

_CALLSIGN_FOUND = """<?xml version="1.0"?>
<QRZDatabase xmlns="http://xmldata.qrz.com" version="1.34">
  <Session><Key>testkey123</Key></Session>
  <Callsign>
    <call>W1AW</call>
    <fname>Hiram</fname>
    <name>Maxim</name>
    <addr2>Newington</addr2>
    <state>CT</state>
    <country>USA</country>
    <grid>FN31</grid>
    <lat>41.714775</lat>
    <lon>-72.727260</lon>
  </Callsign>
</QRZDatabase>"""

_CALLSIGN_NOT_FOUND = """<?xml version="1.0"?>
<QRZDatabase xmlns="http://xmldata.qrz.com" version="1.34">
  <Session>
    <Key>testkey123</Key>
    <Error>Not found: ZZZZZZ</Error>
  </Session>
</QRZDatabase>"""

_LOGIN_FAILED = """<?xml version="1.0"?>
<QRZDatabase xmlns="http://xmldata.qrz.com" version="1.34">
  <Session><Error>Username/password incorrect</Error></Session>
</QRZDatabase>"""


def _mock_http(*responses: str) -> MagicMock:
    """Return a mock httpx.Client whose .get() returns each XML string in order."""
    mock = MagicMock()
    side_effects = []
    for xml in responses:
        resp = MagicMock()
        resp.text = xml
        side_effects.append(resp)
    mock.get.side_effect = side_effects
    return mock


def _make_client(username: str = "user", password: str = "pass") -> QRZClient:
    client = QRZClient(username, password, api_url="http://fake.qrz.invalid/")
    return client


# ---------------------------------------------------------------------------
# Grid utilities
# ---------------------------------------------------------------------------

class TestGridToLatLon:
    def test_4char_grid_center(self):
        lat, lon = grid_to_latlon("FN31")
        # FN31: lon = (F-A=5)*20 - 180 + 3*2 + 1 = 100-180+6+1 = -73, lat = (N-A=13)*10 - 90 + 1 + 0.5 = 41.5
        assert lat == pytest.approx(41.5)
        assert lon == pytest.approx(-73.0)

    def test_6char_grid_more_precise(self):
        lat, lon = grid_to_latlon("FN31pr")
        # More precise than 4-char — just verify it's within the 4-char square
        assert 41.0 <= lat <= 42.0
        assert -74.0 <= lon <= -72.0

    def test_raises_on_short_grid(self):
        with pytest.raises(ValueError):
            grid_to_latlon("FN")

    def test_em00_texas(self):
        # EM00: lon = (E=4)*20-180 + 0*2 + 1 = -99.0, lat = (M=12)*10-90 + 0 + 0.5 = 30.5
        lat, lon = grid_to_latlon("EM00")
        assert lat == pytest.approx(30.5)
        assert lon == pytest.approx(-99.0)


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_one_degree_lat_approx_111km(self):
        d = haversine_km(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111.2, abs=1.0)

    def test_one_degree_lon_at_equator_approx_111km(self):
        d = haversine_km(0.0, 0.0, 0.0, 1.0)
        assert d == pytest.approx(111.2, abs=1.0)

    def test_transatlantic_distance(self):
        # New York (40.7, -74.0) to London (51.5, -0.1) ≈ 5570 km
        d = haversine_km(40.7, -74.0, 51.5, -0.1)
        assert 5400 < d < 5700


class TestBearingAndCardinal:
    def test_north(self):
        assert bearing_deg(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.0, abs=1.0)

    def test_east(self):
        assert bearing_deg(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=1.0)

    def test_south(self):
        assert bearing_deg(1.0, 0.0, 0.0, 0.0) == pytest.approx(180.0, abs=1.0)

    def test_west(self):
        assert bearing_deg(0.0, 1.0, 0.0, 0.0) == pytest.approx(270.0, abs=1.0)

    def test_cardinal_north(self):
        assert cardinal(0.0) == "N"
        assert cardinal(360.0) == "N"

    def test_cardinal_east(self):
        assert cardinal(90.0) == "E"

    def test_cardinal_south(self):
        assert cardinal(180.0) == "S"

    def test_cardinal_west(self):
        assert cardinal(270.0) == "W"

    def test_cardinal_ne(self):
        assert cardinal(45.0) == "NE"

    def test_cardinal_all_16_points(self):
        # Spot-check a few intermediate points
        assert cardinal(22.5) == "NNE"
        assert cardinal(67.5) == "ENE"
        assert cardinal(202.5) == "SSW"


class TestDistanceFromGrid:
    def _make_info(self, lat=41.7, lon=-72.7, grid="FN31") -> QRZInfo:
        return QRZInfo(
            callsign="W1AW", fname="Hiram", name="Hiram Maxim",
            city="Newington", state="CT", country="USA",
            grid=grid, lat=lat, lon=lon,
        )

    def test_uses_lat_lon_when_available(self):
        info = self._make_info(lat=41.7, lon=-72.7, grid="")
        d = distance_from_grid("FM18", info)
        assert d is not None
        assert d > 0

    def test_falls_back_to_grid_when_no_coords(self):
        info = self._make_info(lat=None, lon=None, grid="FN31")
        d = distance_from_grid("FM18", info)
        assert d is not None
        assert d > 0

    def test_returns_none_when_no_coords_or_grid(self):
        info = self._make_info(lat=None, lon=None, grid="")
        d = distance_from_grid("FM18", info)
        assert d is None

    def test_returns_none_for_empty_my_grid(self):
        info = self._make_info()
        assert distance_from_grid("", info) is None

    def test_returns_none_for_short_my_grid(self):
        info = self._make_info()
        assert distance_from_grid("FN", info) is None


# ---------------------------------------------------------------------------
# QRZClient — properties
# ---------------------------------------------------------------------------

class TestQRZClientProperties:
    def test_configured_true_with_credentials(self):
        client = _make_client("user", "pass")
        assert client.configured is True

    def test_configured_false_without_username(self):
        client = _make_client("", "pass")
        assert client.configured is False

    def test_configured_false_without_password(self):
        client = _make_client("user", "")
        assert client.configured is False

    def test_status_unconfigured(self):
        client = _make_client("", "")
        assert client.status == "unconfigured"

    def test_status_pending_before_any_call(self):
        client = _make_client()
        assert client.status == "pending"

    def test_status_ok_after_successful_lookup(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_FOUND)
        _run(client.lookup("W1AW"))
        assert client.status == "ok"

    def test_status_error_after_login_failure(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_FAILED)
        _run(client.lookup("W1AW"))
        assert client.status == "error"


# ---------------------------------------------------------------------------
# QRZClient — lookup behaviour
# ---------------------------------------------------------------------------

class TestQRZClientLookup:
    def test_successful_lookup_returns_qrz_info(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_FOUND)

        info = _run(client.lookup("W1AW"))

        assert info is not None
        assert info.callsign == "W1AW"
        assert info.fname == "Hiram"
        assert info.state == "CT"
        assert info.grid == "FN31"
        assert info.lat == pytest.approx(41.714775)
        assert info.lon == pytest.approx(-72.727260)

    def test_lookup_normalises_callsign_uppercase(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_FOUND)
        info = _run(client.lookup("w1aw"))
        assert info is not None

    def test_lookup_strips_suffix(self):
        """W1AW/P should look up W1AW."""
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_FOUND)
        info = _run(client.lookup("W1AW/P"))
        assert info is not None
        assert info.callsign == "W1AW"

    def test_cache_hit_skips_http_call(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_FOUND)

        first = _run(client.lookup("W1AW"))
        second = _run(client.lookup("W1AW"))

        assert first is second
        # login + lookup = 2 calls; second lookup should be served from cache
        assert client._http.get.call_count == 2

    def test_not_found_returns_none(self):
        # Provide 4 responses: login, not-found lookup, re-login (session expiry retry), second lookup
        client = _make_client()
        client._http = _mock_http(_LOGIN_OK, _CALLSIGN_NOT_FOUND, _LOGIN_OK, _CALLSIGN_NOT_FOUND)
        info = _run(client.lookup("ZZZZZZ"))
        assert info is None

    def test_login_failure_returns_none(self):
        client = _make_client()
        client._http = _mock_http(_LOGIN_FAILED)
        info = _run(client.lookup("W1AW"))
        assert info is None

    def test_network_error_returns_none(self):
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.side_effect = OSError("Connection refused")
        client._http = mock_http
        info = _run(client.lookup("W1AW"))
        assert info is None

    def test_error_logged_on_failure(self):
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.side_effect = OSError("Network unreachable")
        client._http = mock_http
        _run(client.lookup("W1AW"))
        assert len(client.error_log) > 0

    def test_returns_none_when_not_configured(self):
        client = _make_client("", "")
        info = _run(client.lookup("W1AW"))
        assert info is None

    def test_qrz_info_location_property(self):
        info = QRZInfo(
            callsign="W1AW", fname="Hiram", name="Hiram Maxim",
            city="Newington", state="CT", country="USA",
            grid="FN31", lat=41.7, lon=-72.7,
        )
        assert info.location == "Newington, CT"

    def test_qrz_info_location_property_no_state(self):
        info = QRZInfo(
            callsign="G4ABC", fname="John", name="John Smith",
            city="London", state="", country="England",
            grid="IO91", lat=51.5, lon=-0.1,
        )
        assert info.location == "London, England"
