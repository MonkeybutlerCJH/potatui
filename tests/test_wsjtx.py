# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for WSJT-X UDP listener client."""

import struct
import time

import pytest

from potatui.wsjtx import (
    WsjtxClient,
    _read_bool,
    _read_double,
    _read_u32,
    _read_u64,
    _read_utf8,
    _read_qdatetime,
)

_MAGIC = 0xADBCCBDA


# ---------------------------------------------------------------------------
# Binary helper functions
# ---------------------------------------------------------------------------

def _w_u32(val: int) -> bytes:
    return struct.pack(">I", val)


def _w_u64(val: int) -> bytes:
    return struct.pack(">Q", val)


def _w_utf8(s: str) -> bytes:
    if not s and s == "":
        # Qt null string
        return _w_u32(0xFFFFFFFF)
    encoded = s.encode("utf-8")
    return _w_u32(len(encoded)) + encoded


def _w_utf8_nonempty(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return _w_u32(len(encoded)) + encoded


def _w_qdatetime_utc(jd: int, ms: int) -> bytes:
    """timespec=1 (UTC)."""
    return _w_u64(jd) + _w_u32(ms) + bytes([1])


class TestBinaryHelpers:
    def test_read_u32(self):
        data = struct.pack(">I", 42)
        val, pos = _read_u32(data, 0)
        assert val == 42
        assert pos == 4

    def test_read_u64(self):
        data = struct.pack(">Q", 123456789)
        val, pos = _read_u64(data, 0)
        assert val == 123456789
        assert pos == 8

    def test_read_utf8_normal_string(self):
        data = _w_utf8_nonempty("W1AW")
        text, pos = _read_utf8(data, 0)
        assert text == "W1AW"
        assert pos == len(data)

    def test_read_utf8_null_string(self):
        """Qt null string (0xFFFFFFFF length) → empty string."""
        data = _w_u32(0xFFFFFFFF)
        text, pos = _read_utf8(data, 0)
        assert text == ""
        assert pos == 4

    def test_read_utf8_empty_string(self):
        data = _w_u32(0)
        text, pos = _read_utf8(data, 0)
        assert text == ""
        assert pos == 4

    def test_read_qdatetime_zero_jd_returns_none(self):
        data = _w_qdatetime_utc(jd=0, ms=0)
        dt, _ = _read_qdatetime(data, 0)
        assert dt is None

    def test_read_qdatetime_known_date(self):
        """JD 2451545 = 2000-01-01."""
        jd = 2451545
        ms = 12 * 3600 * 1000  # noon
        data = _w_qdatetime_utc(jd=jd, ms=ms)
        dt, _ = _read_qdatetime(data, 0)
        assert dt is not None
        assert dt.year == 2000
        assert dt.month == 1
        assert dt.day == 1
        assert dt.hour == 12

    def test_read_bool(self):
        data = bytes([1, 0])
        t, pos = _read_bool(data, 0)
        assert t is True
        assert pos == 1
        f, pos = _read_bool(data, 1)
        assert f is False

    def test_read_double(self):
        data = struct.pack(">d", 3.14159)
        val, pos = _read_double(data, 0)
        assert val == pytest.approx(3.14159)
        assert pos == 8


# ---------------------------------------------------------------------------
# WsjtxClient state
# ---------------------------------------------------------------------------

class TestWsjtxClientState:
    def test_drain_qsos_returns_and_clears_queue(self):
        client = WsjtxClient()
        client._qso_queue = [{"dx_call": "W1AW"}, {"dx_call": "K1ABC"}]
        result = client.drain_qsos()
        assert len(result) == 2
        assert result[0]["dx_call"] == "W1AW"
        # Queue should now be empty
        assert client.drain_qsos() == []

    def test_drain_qsos_empty_when_nothing_queued(self):
        client = WsjtxClient()
        assert client.drain_qsos() == []

    def test_is_online_false_when_never_received(self):
        client = WsjtxClient()
        # _last_rx starts at 0.0
        assert client.is_online() is False

    def test_is_online_true_when_recently_received(self):
        client = WsjtxClient()
        client._last_rx = time.monotonic()
        assert client.is_online() is True

    def test_is_online_false_when_last_rx_too_old(self):
        client = WsjtxClient()
        client._last_rx = time.monotonic() - 25.0  # > 20 second threshold
        assert client.is_online() is False

    def test_is_online_true_at_19_seconds(self):
        client = WsjtxClient()
        client._last_rx = time.monotonic() - 19.0  # just inside threshold
        assert client.is_online() is True


# ---------------------------------------------------------------------------
# WsjtxClient packet parsing
# ---------------------------------------------------------------------------

def _make_packet(msg_type: int, payload: bytes, id_str: str = "WSJT-X") -> bytes:
    """Build a minimal WSJT-X framed packet."""
    header = (
        _w_u32(_MAGIC)
        + _w_u32(2)          # schema
        + _w_u32(msg_type)   # message type
        + _w_utf8_nonempty(id_str)
    )
    return header + payload


def _make_qso_packet(
    dx_call: str = "W1AW",
    dx_grid: str = "FN31",
    freq_hz: int = 14225000,
    mode: str = "FT8",
    rst_sent: str = "-10",
    rst_rcvd: str = "-10",
    name: str = "Hiram",
    comments: str = "TNX",
    jd: int = 2451545,
    ms: int = 0,
) -> bytes:
    payload = (
        _w_qdatetime_utc(jd, ms)
        + _w_utf8_nonempty(dx_call)
        + _w_utf8_nonempty(dx_grid)
        + _w_u64(freq_hz)
        + _w_utf8_nonempty(mode)
        + _w_utf8_nonempty(rst_sent)
        + _w_utf8_nonempty(rst_rcvd)
        + _w_utf8_nonempty("100")   # tx_power
        + _w_utf8_nonempty(comments)
        + _w_utf8_nonempty(name)
    )
    return _make_packet(5, payload)  # type 5 = QSO Logged


class TestWsjtxPacketParsing:
    def test_short_packet_ignored(self):
        client = WsjtxClient()
        client._parse_message(b"\x00\x01\x02")  # < 8 bytes
        assert client._qso_queue == []

    def test_wrong_magic_ignored(self):
        client = WsjtxClient()
        data = _w_u32(0xDEADBEEF) + _w_u32(2) + _w_u32(5) + bytes(20)
        client._parse_message(data)
        assert client._qso_queue == []

    def test_heartbeat_packet_updates_log(self):
        client = WsjtxClient()
        # Heartbeat payload: u32 max_schema + utf8 version
        payload = _w_u32(3) + _w_utf8_nonempty("2.6.1")
        data = _make_packet(0, payload)
        client._parse_message(data)
        assert any("Heartbeat" in entry for entry in client.log)

    def test_qso_logged_populates_queue(self):
        client = WsjtxClient()
        data = _make_qso_packet()
        client._parse_message(data)
        assert len(client._qso_queue) == 1

    def test_qso_logged_fields(self):
        client = WsjtxClient()
        data = _make_qso_packet(
            dx_call="K1ABC",
            dx_grid="FM18",
            freq_hz=7074000,
            mode="FT8",
            rst_sent="-10",
            rst_rcvd="-12",
            name="Bob",
            comments="Nice QSO",
        )
        client._parse_message(data)
        assert len(client._qso_queue) == 1
        qso = client._qso_queue[0]
        assert qso["dx_call"] == "K1ABC"
        assert qso["dx_grid"] == "FM18"
        assert qso["tx_freq_hz"] == 7074000
        assert qso["mode"] == "FT8"
        assert qso["rst_sent"] == "-10"
        assert qso["rst_rcvd"] == "-12"
        assert qso["name"] == "Bob"
        assert qso["comments"] == "Nice QSO"

    def test_qso_callsign_normalised_to_uppercase(self):
        client = WsjtxClient()
        # Build packet where dx_call is already uppercase (it comes from WSJT-X that way)
        data = _make_qso_packet(dx_call="w1aw")
        client._parse_message(data)
        assert client._qso_queue[0]["dx_call"] == "W1AW"

    def test_qso_empty_rst_defaults_to_minus10(self):
        """Empty RST fields should default to '-10' per WSJT-X digital mode convention."""
        client = WsjtxClient()
        # Build packet with empty rst strings
        jd, ms = 2451545, 0
        payload = (
            _w_qdatetime_utc(jd, ms)
            + _w_utf8_nonempty("W1AW")
            + _w_utf8_nonempty("FN31")
            + _w_u64(14074000)
            + _w_utf8_nonempty("FT8")
            + _w_u32(0)   # empty rst_sent (length=0)
            + _w_u32(0)   # empty rst_rcvd
            + _w_utf8_nonempty("100")
            + _w_u32(0)   # empty comments
            + _w_u32(0)   # empty name
        )
        data = _make_packet(5, payload)
        client._parse_message(data)
        assert len(client._qso_queue) == 1
        qso = client._qso_queue[0]
        assert qso["rst_sent"] == "-10"
        assert qso["rst_rcvd"] == "-10"

    def test_multiple_qso_packets_all_queued(self):
        client = WsjtxClient()
        data1 = _make_qso_packet(dx_call="W1AW")
        data2 = _make_qso_packet(dx_call="K1ABC")
        client._parse_message(data1)
        client._parse_message(data2)
        assert len(client._qso_queue) == 2
        calls = {q["dx_call"] for q in client._qso_queue}
        assert calls == {"W1AW", "K1ABC"}

    def test_status_packet_updates_log(self):
        client = WsjtxClient()
        payload = (
            _w_u64(14225000)         # dial_freq_hz
            + _w_utf8_nonempty("FT8")  # mode
            + _w_utf8_nonempty("W1AW") # dx_call
        )
        data = _make_packet(1, payload)
        client._parse_message(data)
        assert any("Status" in entry for entry in client.log)
