# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for adif.py — freq_to_band() and ADIF record generation."""

import datetime

import pytest

from potatui.adif import _qso_to_adif, freq_to_band
from potatui.session import QSO

# --------------------------------------------------------------------------
# Representative centre frequencies — should map to correct band
# --------------------------------------------------------------------------

@pytest.mark.parametrize("freq_khz, expected", [
    (1900.0,   "160m"),
    (3750.0,   "80m"),
    (5357.0,   "60m"),
    (7100.0,   "40m"),
    (10125.0,  "30m"),
    (14200.0,  "20m"),
    (18100.0,  "17m"),
    (21200.0,  "15m"),
    (24940.0,  "12m"),
    (28500.0,  "10m"),
    (52000.0,  "6m"),
    (146000.0, "2m"),
    (435000.0, "70cm"),
])
def test_centre_frequencies(freq_khz, expected):
    assert freq_to_band(freq_khz) == expected


# --------------------------------------------------------------------------
# Band boundary edge cases
# --------------------------------------------------------------------------

@pytest.mark.parametrize("freq_khz, expected", [
    # 20m boundaries (14000–14350)
    (14000.0,  "20m"),   # lower bound inclusive
    (14350.0,  "20m"),   # upper bound inclusive
    (13999.9,  "?"),     # just below 20m
    (14350.1,  "?"),     # just above 20m

    # 40m boundaries (7000–7300)
    (7000.0,   "40m"),
    (7300.0,   "40m"),
    (6999.9,   "?"),
    (7300.1,   "?"),

    # 2m boundaries (144000–148000)
    (144000.0, "2m"),
    (148000.0, "2m"),
    (143999.9, "?"),
    (148000.1, "?"),
])
def test_band_boundaries(freq_khz, expected):
    assert freq_to_band(freq_khz) == expected


# --------------------------------------------------------------------------
# Out-of-range / unknown frequencies
# --------------------------------------------------------------------------

@pytest.mark.parametrize("freq_khz", [
    0.0,
    1799.9,
    2000.1,
    500000.0,
    999999.0,
    -1.0,
])
def test_unknown_frequency_returns_question_mark(freq_khz):
    assert freq_to_band(freq_khz) == "?"


# --------------------------------------------------------------------------
# STATE field — only written for valid US state abbreviations
# --------------------------------------------------------------------------

def _make_qso(state: str) -> QSO:
    return QSO(
        qso_id=1,
        timestamp_utc=datetime.datetime(2026, 3, 15, 12, 0, 0),
        callsign="M0MCM",
        rst_sent="59",
        rst_rcvd="59",
        freq_khz=14200.0,
        band="20m",
        mode="SSB",
        state=state,
    )


@pytest.mark.parametrize("state", ["NY", "CA", "TX", "WI", "DC", "PR", "GU", "ny", "ca"])
def test_us_state_written_to_adif(state):
    record = _qso_to_adif(_make_qso(state), "W1AW", "W1AW", "US-0001")
    assert "<STATE:" in record


@pytest.mark.parametrize("state", ["ENG", "WAL", "SCO", "NSW", "ON", "BC", "QLD", "NRW", ""])
def test_non_us_state_not_written_to_adif(state):
    record = _qso_to_adif(_make_qso(state), "W1AW", "W1AW", "US-0001")
    assert "<STATE:" not in record


# --------------------------------------------------------------------------
# MY_RIG, MY_ANTENNA, TX_PWR fields
# --------------------------------------------------------------------------

def _make_basic_qso() -> QSO:
    return QSO(
        qso_id=1,
        timestamp_utc=datetime.datetime(2026, 3, 15, 12, 0, 0),
        callsign="W1AW",
        rst_sent="59",
        rst_rcvd="59",
        freq_khz=14200.0,
        band="20m",
        mode="SSB",
    )


def test_rig_written_to_adif():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", rig="IC-7300")
    assert "<MY_RIG:7>IC-7300" in record


def test_antenna_written_to_adif():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", antenna="EFHW")
    assert "<MY_ANTENNA:4>EFHW" in record


def test_power_written_to_adif():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", power_w=100)
    assert "<TX_PWR:3>100" in record


def test_empty_rig_not_written():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", rig="")
    assert "<MY_RIG:" not in record


def test_empty_antenna_not_written():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", antenna="")
    assert "<MY_ANTENNA:" not in record


def test_zero_power_not_written():
    record = _qso_to_adif(_make_basic_qso(), "W1AW", "W1AW", "US-0001", power_w=0)
    assert "<TX_PWR:" not in record


def test_all_station_fields_together():
    record = _qso_to_adif(
        _make_basic_qso(), "W1AW", "W1AW", "US-0001",
        rig="Yaesu FT-710", antenna="EFHW", power_w=50,
    )
    assert "<MY_RIG:" in record
    assert "<MY_ANTENNA:" in record
    assert "<TX_PWR:2>50" in record
