# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for Session.is_duplicate() and QSO round-trip serialisation."""

from datetime import datetime

from potatui.session import QSO, Session

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def make_session(*qsos: QSO) -> Session:
    s = Session(
        operator="W1AW",
        station_callsign="W1AW",
        park_refs=["US-1234"],
        active_park_ref="US-1234",
        grid="FN31",
        rig="IC-7300",
        antenna="EFHW",
        power_w=100,
        start_time=datetime(2026, 3, 14, 12, 0, 0),
        qsos=list(qsos),
    )
    return s


def make_qso(**overrides) -> QSO:
    defaults = dict(
        qso_id=1,
        timestamp_utc=datetime(2026, 3, 14, 12, 0, 0),
        callsign="K1ABC",
        rst_sent="59",
        rst_rcvd="59",
        freq_khz=14200.0,
        band="20m",
        mode="SSB",
    )
    defaults.update(overrides)
    return QSO(**defaults)


# --------------------------------------------------------------------------
# Session.is_duplicate()
# --------------------------------------------------------------------------

class TestIsDuplicate:
    def test_same_callsign_same_band_is_dupe(self):
        q = make_qso(callsign="K1ABC", band="20m")
        s = make_session(q)
        assert s.is_duplicate("K1ABC", "20m") is True

    def test_same_callsign_different_band_not_dupe(self):
        q = make_qso(callsign="K1ABC", band="20m")
        s = make_session(q)
        assert s.is_duplicate("K1ABC", "40m") is False

    def test_different_callsign_same_band_not_dupe(self):
        q = make_qso(callsign="K1ABC", band="20m")
        s = make_session(q)
        assert s.is_duplicate("W9XYZ", "20m") is False

    def test_case_insensitive_callsign(self):
        q = make_qso(callsign="K1ABC", band="20m")
        s = make_session(q)
        assert s.is_duplicate("k1abc", "20m") is True
        assert s.is_duplicate("K1ABC", "20m") is True

    def test_no_band_arg_matches_any_band(self):
        q = make_qso(callsign="K1ABC", band="40m")
        s = make_session(q)
        assert s.is_duplicate("K1ABC") is True

    def test_empty_session_never_dupe(self):
        s = make_session()
        assert s.is_duplicate("K1ABC", "20m") is False


# --------------------------------------------------------------------------
# QSO.to_dict() / QSO.from_dict() round-trip
# --------------------------------------------------------------------------

class TestQSORoundTrip:
    def test_full_qso_round_trip(self):
        q = QSO(
            qso_id=42,
            timestamp_utc=datetime(2026, 3, 14, 15, 30, 0),
            callsign="VE3XYZ",
            rst_sent="59",
            rst_rcvd="57",
            freq_khz=7074.0,
            band="40m",
            mode="FT8",
            name="Alice",
            state="ON",
            notes="Good signal",
            is_p2p=True,
            p2p_ref="CA-0042",
            operator="W1AW",
        )
        restored = QSO.from_dict(q.to_dict())
        assert restored == q

    def test_missing_state_defaults_to_empty_string(self):
        d = {
            "qso_id": 1,
            "timestamp_utc": "2026-03-14T12:00:00",
            "callsign": "K1ABC",
            "rst_sent": "59",
            "rst_rcvd": "59",
            "freq_khz": 14200.0,
            "band": "20m",
            "mode": "SSB",
            # no "state" key — simulates old session file
        }
        q = QSO.from_dict(d)
        assert q.state == ""

    def test_missing_operator_defaults_to_empty_string(self):
        d = {
            "qso_id": 1,
            "timestamp_utc": "2026-03-14T12:00:00",
            "callsign": "K1ABC",
            "rst_sent": "59",
            "rst_rcvd": "59",
            "freq_khz": 14200.0,
            "band": "20m",
            "mode": "SSB",
            # no "operator" key — simulates old session file
        }
        q = QSO.from_dict(d)
        assert q.operator == ""

    def test_timestamp_survives_round_trip(self):
        ts = datetime(2026, 3, 14, 23, 59, 59)
        q = make_qso(timestamp_utc=ts)
        assert QSO.from_dict(q.to_dict()).timestamp_utc == ts
