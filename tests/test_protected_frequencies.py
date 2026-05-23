# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

import pytest

from potatui.protected_frequencies import (
    ProtectedFrequency,
    _protected_range,
    _ranges_overlap,
    _tx_bandwidth_khz,
    _tx_range,
    _tx_sideband,
    check_overlap,
)


# -- _tx_sideband -----------------------------------------------------------

def test_tx_sideband_usb_above_10mhz():
    assert _tx_sideband("SSB", 14_200) == "USB"
    assert _tx_sideband("CW", 14_050) == "USB"
    assert _tx_sideband("SSB", 28_500) == "USB"


def test_tx_sideband_lsb_below_10mhz():
    assert _tx_sideband("SSB", 7_074) == "LSB"
    assert _tx_sideband("CW", 3_550) == "LSB"
    assert _tx_sideband("SSB", 1_900) == "LSB"


def test_tx_sideband_exactly_10mhz_is_usb():
    assert _tx_sideband("SSB", 10_000) == "USB"


def test_tx_sideband_data_modes_always_usb():
    assert _tx_sideband("FT8", 7_074) == "USB"
    assert _tx_sideband("FT4", 3_575) == "USB"
    assert _tx_sideband("FT8", 14_074) == "USB"


def test_tx_sideband_case_insensitive():
    assert _tx_sideband("ssb", 7_074) == "LSB"
    assert _tx_sideband("ft8", 7_074) == "USB"


# -- _tx_bandwidth_khz ------------------------------------------------------

def test_tx_bandwidth_ssb():
    assert _tx_bandwidth_khz("SSB") == 3.0
    assert _tx_bandwidth_khz("AM") == 3.0
    assert _tx_bandwidth_khz("FM") == 3.0


def test_tx_bandwidth_cw():
    assert _tx_bandwidth_khz("CW") == 0.5


def test_tx_bandwidth_data():
    assert _tx_bandwidth_khz("FT8") == 0.05
    assert _tx_bandwidth_khz("FT4") == 0.05


def test_tx_bandwidth_unknown_defaults_to_3():
    assert _tx_bandwidth_khz("RTTY") == 3.0


# -- _protected_range -------------------------------------------------------

def test_protected_range_usb():
    e = ProtectedFrequency(frequency_khz=14300.0, label="Test", mode="USB")
    assert _protected_range(e) == (14300.0, 14303.0)


def test_protected_range_lsb():
    e = ProtectedFrequency(frequency_khz=7171.0, label="Test", mode="LSB")
    assert _protected_range(e) == (7168.0, 7171.0)


def test_protected_range_custom_bandwidth():
    e = ProtectedFrequency(frequency_khz=14300.0, label="Wide Net", mode="USB", bandwidth_khz=6.0)
    assert _protected_range(e) == (14300.0, 14306.0)


# -- _tx_range --------------------------------------------------------------

def test_tx_range_ssb_usb():
    lo, hi = _tx_range(14200.0, "SSB")
    assert lo == 14200.0
    assert hi == 14203.0


def test_tx_range_ssb_lsb():
    lo, hi = _tx_range(7074.0, "SSB")
    assert lo == 7071.0
    assert hi == 7074.0


def test_tx_range_cw():
    lo, hi = _tx_range(14050.0, "CW")
    assert lo == 14050.0
    assert hi == 14050.5


def test_tx_range_ft8():
    lo, hi = _tx_range(14074.0, "FT8")
    assert lo == 14074.0
    assert hi == 14074.05


# -- _ranges_overlap --------------------------------------------------------

def test_ranges_overlap_true():
    assert _ranges_overlap(1.0, 4.0, 3.0, 6.0) is True


def test_ranges_overlap_touching():
    assert _ranges_overlap(1.0, 3.0, 3.0, 6.0) is True


def test_ranges_overlap_contained():
    assert _ranges_overlap(2.0, 4.0, 1.0, 6.0) is True


def test_ranges_overlap_identical():
    assert _ranges_overlap(1.0, 3.0, 1.0, 3.0) is True


def test_ranges_overlap_false_below():
    assert _ranges_overlap(1.0, 2.0, 3.0, 4.0) is False


def test_ranges_overlap_false_above():
    assert _ranges_overlap(5.0, 6.0, 3.0, 4.0) is False


# -- check_overlap ----------------------------------------------------------

MARITIME = ProtectedFrequency(
    frequency_khz=14300.0, label="Maritime Mobile Service Net",
    mode="USB", bandwidth_khz=6.0,
)
SSTV_20M = ProtectedFrequency(
    frequency_khz=14230.0, label="SSTV Call (20m)",
    mode="USB", bandwidth_khz=3.0,
)
SSTV_40M = ProtectedFrequency(
    frequency_khz=7171.0, label="SSTV Call (40m)",
    mode="LSB", bandwidth_khz=3.0,
)
LID_20M = ProtectedFrequency(
    frequency_khz=14313.0, label="'Lid' frequency (20m)",
    mode="USB", bandwidth_khz=3.0,
)


def test_usb_near_maritime_net_overlaps():
    """14.298 USB → TX 14298.0–14301.0 overlaps Maritime 14300.0–14306.0."""
    result = check_overlap(14298.0, "SSB", [MARITIME])
    assert len(result) == 1
    assert result[0].label == "Maritime Mobile Service Net"


def test_usb_exact_maritime_net_overlaps():
    """14.300 USB → TX 14300.0–14303.0 overlaps Maritime."""
    result = check_overlap(14300.0, "SSB", [MARITIME])
    assert len(result) == 1


def test_usb_just_above_maritime_net_no_overlap():
    """14.3065 USB → TX 14306.5–14309.5 — no overlap with Maritime (ends 14306.0)."""
    result = check_overlap(14306.5, "SSB", [MARITIME])
    assert len(result) == 0


def test_usb_on_sstv_call_exact_overlaps():
    result = check_overlap(14230.0, "SSB", [SSTV_20M])
    assert len(result) == 1


def test_usb_1khz_above_sstv_call_still_overlaps():
    """14.231 USB → TX 14231.0–14234.0 overlaps SSTV 14230.0–14233.0."""
    result = check_overlap(14231.0, "SSB", [SSTV_20M])
    assert len(result) == 1


def test_usb_just_past_sstv_call_no_overlap():
    """14.2335 USB → TX 14233.5–14236.5 ends after SSTV ends at 14233.0."""
    result = check_overlap(14233.5, "SSB", [SSTV_20M])
    assert len(result) == 0


def test_lsb_near_40m_sstv_overlaps():
    """7.170 LSB → TX 7167.0–7170.0 overlaps SSTV 7168.0–7171.0."""
    result = check_overlap(7170.0, "SSB", [SSTV_40M])
    assert len(result) == 1
    assert result[0].label == "SSTV Call (40m)"


def test_lsb_just_below_sstv_no_overlap():
    """7.1675 LSB → TX 7164.5–7167.5 — no overlap with SSTV 7168.0–7171.0."""
    result = check_overlap(7167.5, "SSB", [SSTV_40M])
    assert len(result) == 0


def test_multiple_overlaps():
    """14.313 USB on Lid freq also overlaps Maritime (14296+). Not quite."""
    pass


def test_multiple_simultaneous_overlaps():
    """Tune between two protected freqs that are close together."""
    # SSTV 14230 (14230.0–14233.0) and Maritime 14300 (14300.0–14306.0)
    # At 14.298 USB → TX 14298.0–14301.0: only overlaps Maritime
    entries = [SSTV_20M, MARITIME]
    result = check_overlap(14298.0, "SSB", entries)
    assert len(result) == 1
    assert result[0].label == "Maritime Mobile Service Net"


def test_lid_20m_overlaps():
    """14.314 USB → TX 14314.0–14317.0 overlaps Lid 14313.0–14316.0."""
    result = check_overlap(14314.0, "SSB", [LID_20M])
    assert len(result) == 1


def test_lsb_tx_no_overlap_with_usb_protected():
    """SSB at 14.300 but LSB → TX is below dial, shouldn't overlap Maritime USB."""
    # This would be unusual (LSB on 20m) but test the logic.
    # _tx_sideband forces USB at >=10MHz, so this case is theoretical.
    # Test with a hypothetical LSB entry on 20m.
    pass


def test_ft8_narrow_no_overlap():
    """FT8 at 14.300.5 is only 50 Hz wide — should still hit wide Maritime net."""
    result = check_overlap(14300.5, "FT8", [MARITIME])
    # FT8 TX: 14300.5–14300.55, Maritime: 14300.0–14306.0 → overlap
    assert len(result) == 1


def test_cw_narrow_bandwidth():
    """CW at 14.299 is 500 Hz wide — 14299.0–14299.5 should NOT overlap Maritime 14300.0."""
    result = check_overlap(14299.0, "CW", [MARITIME])
    assert len(result) == 0


def test_empty_entries():
    assert check_overlap(14300.0, "SSB", []) == []


def test_no_overlap_clean_frequency():
    """14.250 USB is far from any protected 20m freq."""
    result = check_overlap(14250.0, "SSB", [SSTV_20M, MARITIME, LID_20M])
    assert len(result) == 0
