# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for HamDB.org callsign lookup client."""

import asyncio
from unittest.mock import MagicMock

import pytest

from potatui.hamdb import HamDbClient


def _run(coro):
    return asyncio.run(coro)


def _mock_http(json_data: dict | None = None, exc: Exception | None = None) -> MagicMock:
    mock = MagicMock()
    if exc is not None:
        mock.get.side_effect = exc
    else:
        resp = MagicMock()
        resp.json.return_value = json_data
        mock.get.return_value = resp
    return mock


def _found_response(
    call: str = "W1AW",
    fname: str = "Hiram",
    name: str = "Maxim",
    addr2: str = "Newington",
    state: str = "CT",
    country: str = "USA",
    grid: str = "FN31",
    lat: str = "41.7",
    lon: str = "-72.7",
) -> dict:
    return {
        "hamdb": {
            "callsign": {
                "call": call,
                "fname": fname,
                "name": name,
                "addr2": addr2,
                "state": state,
                "country": country,
                "grid": grid,
                "lat": lat,
                "lon": lon,
            },
            "messages": {"status": "OK"},
        }
    }


def _not_found_response() -> dict:
    return {"hamdb": {"messages": {"status": "NOT_FOUND"}}}


# ---------------------------------------------------------------------------
# Successful lookups
# ---------------------------------------------------------------------------

class TestHamDbClientLookup:
    def test_returns_qrz_info_on_success(self):
        client = HamDbClient()
        client._http = _mock_http(_found_response())
        info = _run(client.lookup("W1AW"))
        assert info is not None
        assert info.callsign == "W1AW"
        assert info.fname == "Hiram"
        assert info.name == "Hiram Maxim"
        assert info.city == "Newington"
        assert info.state == "CT"
        assert info.grid == "FN31"
        assert info.lat == pytest.approx(41.7)
        assert info.lon == pytest.approx(-72.7)

    def test_callsign_normalised_to_uppercase(self):
        client = HamDbClient()
        client._http = _mock_http(_found_response(call="W1AW"))
        info = _run(client.lookup("w1aw"))
        assert info is not None
        assert info.callsign == "W1AW"

    def test_suffix_stripped(self):
        """W1AW/P → look up W1AW."""
        client = HamDbClient()
        client._http = _mock_http(_found_response(call="W1AW"))
        info = _run(client.lookup("W1AW/P"))
        assert info is not None

    def test_name_composed_from_fname_and_name(self):
        client = HamDbClient()
        client._http = _mock_http(_found_response(fname="Hiram", name="Maxim"))
        info = _run(client.lookup("W1AW"))
        assert info is not None
        assert info.name == "Hiram Maxim"

    def test_missing_lat_lon_returns_none_coords(self):
        data = _found_response()
        data["hamdb"]["callsign"]["lat"] = ""
        data["hamdb"]["callsign"]["lon"] = ""
        client = HamDbClient()
        client._http = _mock_http(data)
        info = _run(client.lookup("W1AW"))
        assert info is not None
        assert info.lat is None
        assert info.lon is None

    def test_invalid_lat_lon_returns_none_coords(self):
        data = _found_response()
        data["hamdb"]["callsign"]["lat"] = "not_a_number"
        data["hamdb"]["callsign"]["lon"] = "not_a_number"
        client = HamDbClient()
        client._http = _mock_http(data)
        info = _run(client.lookup("W1AW"))
        assert info is not None
        assert info.lat is None
        assert info.lon is None


# ---------------------------------------------------------------------------
# Not found and error cases
# ---------------------------------------------------------------------------

class TestHamDbClientNotFound:
    def test_status_not_found_returns_none(self):
        client = HamDbClient()
        client._http = _mock_http(_not_found_response())
        info = _run(client.lookup("ZZZZZZ"))
        assert info is None

    def test_call_field_not_found_returns_none(self):
        data = {"hamdb": {"callsign": {"call": "NOT_FOUND"}, "messages": {"status": "OK"}}}
        client = HamDbClient()
        client._http = _mock_http(data)
        info = _run(client.lookup("ZZZZZZ"))
        assert info is None

    def test_empty_callsign_block_returns_none(self):
        data = {"hamdb": {"callsign": {}, "messages": {"status": "OK"}}}
        client = HamDbClient()
        client._http = _mock_http(data)
        info = _run(client.lookup("ZZZZZZ"))
        assert info is None

    def test_network_error_returns_none(self):
        client = HamDbClient()
        client._http = _mock_http(exc=OSError("Connection refused"))
        info = _run(client.lookup("W1AW"))
        assert info is None

    def test_error_is_logged_on_failure(self):
        client = HamDbClient()
        client._http = _mock_http(exc=OSError("Network unreachable"))
        _run(client.lookup("W1AW"))
        assert len(client.error_log) > 0
        assert "W1AW" in client.error_log[0]


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

class TestHamDbClientCache:
    def test_second_call_uses_cache(self):
        client = HamDbClient()
        client._http = _mock_http(_found_response())
        first = _run(client.lookup("W1AW"))
        second = _run(client.lookup("W1AW"))
        assert first is second
        assert client._http.get.call_count == 1

    def test_different_callsigns_not_cached(self):
        client = HamDbClient()
        client._http = _mock_http(
            _found_response(call="W1AW"),
        )
        resp2 = MagicMock()
        resp2.json.return_value = _found_response(call="K1ABC")
        client._http.get.side_effect = [
            MagicMock(**{"json.return_value": _found_response(call="W1AW")}),
            MagicMock(**{"json.return_value": _found_response(call="K1ABC")}),
        ]
        _run(client.lookup("W1AW"))
        _run(client.lookup("K1ABC"))
        assert client._http.get.call_count == 2

    def test_none_result_also_cached(self):
        """A NOT_FOUND response should be cached so we don't re-query."""
        client = HamDbClient()
        client._http = _mock_http(_not_found_response())
        _run(client.lookup("ZZZZZZ"))
        _run(client.lookup("ZZZZZZ"))
        assert client._http.get.call_count == 1
