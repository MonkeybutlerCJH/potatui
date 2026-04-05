# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for flrig XML-RPC client."""

import xmlrpc.client
from unittest.mock import MagicMock, patch

import pytest

from potatui.flrig import FlrigClient, _canonical_to_flrig
from potatui.mode_map import ModeTranslations


def _make_client() -> FlrigClient:
    return FlrigClient("localhost", 12345)


def _inject_proxy(client: FlrigClient, proxy: MagicMock) -> None:
    """Set the poll proxy directly so no real XML-RPC connection is made."""
    client._proxy = proxy


def _inject_cat_proxy(client: FlrigClient, proxy: MagicMock) -> None:
    client._cat_proxy = proxy


# ---------------------------------------------------------------------------
# _canonical_to_flrig helper
# ---------------------------------------------------------------------------

class TestCanonicalToFlrig:
    def test_ssb_above_10mhz_is_usb(self):
        assert _canonical_to_flrig("SSB", 14200.0) == "USB"

    def test_ssb_below_10mhz_is_lsb(self):
        assert _canonical_to_flrig("SSB", 7100.0) == "LSB"

    def test_ssb_at_boundary_is_usb(self):
        assert _canonical_to_flrig("SSB", 10000.0) == "USB"

    def test_ssb_unknown_freq_defaults_to_usb(self):
        assert _canonical_to_flrig("SSB", None) == "USB"

    def test_cw(self):
        assert _canonical_to_flrig("CW", None) == "CW-U"

    def test_am(self):
        assert _canonical_to_flrig("AM", None) == "AM"

    def test_fm(self):
        assert _canonical_to_flrig("FM", None) == "FM"

    def test_ft8(self):
        assert _canonical_to_flrig("FT8", None) == "PKTUSB"

    def test_ft4(self):
        assert _canonical_to_flrig("FT4", None) == "PKTUSB"

    def test_unknown_mode_passthrough(self):
        assert _canonical_to_flrig("OLIVIA", None) == "OLIVIA"


# ---------------------------------------------------------------------------
# get_frequency
# ---------------------------------------------------------------------------

class TestGetFrequency:
    def test_returns_khz_from_hz(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.return_value = 14225000
        _inject_proxy(client, proxy)
        freq = client.get_frequency()
        assert freq == pytest.approx(14225.0)

    def test_returns_none_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.side_effect = OSError("Connection refused")
        _inject_proxy(client, proxy)
        freq = client.get_frequency()
        assert freq is None

    def test_resets_proxy_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.side_effect = OSError("Connection refused")
        _inject_proxy(client, proxy)
        client.get_frequency()
        assert client._proxy is None

    def test_error_logged_on_failure(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.side_effect = OSError("timeout")
        _inject_proxy(client, proxy)
        client.get_frequency()
        assert any("get_vfo" in entry for entry in client.log)


# ---------------------------------------------------------------------------
# get_mode
# ---------------------------------------------------------------------------

class TestGetMode:
    def test_usb_maps_to_ssb(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "USB"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "SSB"

    def test_lsb_maps_to_ssb(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "LSB"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "SSB"

    def test_cw_maps_to_cw(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "CW"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "CW"

    def test_pktusb_maps_to_ft8(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "PKTUSB"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "FT8"

    def test_uses_custom_translations_when_provided(self):
        translations = ModeTranslations(
            rig_to_canonical={"DATA-U": "FT8"},
            canonical_to_rig={},
        )
        client = FlrigClient("localhost", 12345, mode_translations=translations)
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "DATA-U"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "FT8"

    def test_returns_none_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.side_effect = OSError("timeout")
        _inject_proxy(client, proxy)
        assert client.get_mode() is None


# ---------------------------------------------------------------------------
# get_modes
# ---------------------------------------------------------------------------

class TestGetModes:
    def test_returns_list_of_strings(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_modes.return_value = ["USB", "LSB", "CW", "FM"]
        _inject_proxy(client, proxy)
        modes = client.get_modes()
        assert modes == ["USB", "LSB", "CW", "FM"]

    def test_returns_none_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_modes.side_effect = OSError("timeout")
        _inject_proxy(client, proxy)
        assert client.get_modes() is None


# ---------------------------------------------------------------------------
# set_frequency
# ---------------------------------------------------------------------------

class TestSetFrequency:
    def test_calls_set_vfo_with_hz(self):
        client = _make_client()
        proxy = MagicMock()
        _inject_proxy(client, proxy)
        result = client.set_frequency(14225000.0)
        assert result is True
        proxy.rig.set_vfo.assert_called_once_with(14225000.0)

    def test_returns_false_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.set_vfo.side_effect = OSError("timeout")
        _inject_proxy(client, proxy)
        result = client.set_frequency(14225000.0)
        assert result is False


# ---------------------------------------------------------------------------
# set_mode
# ---------------------------------------------------------------------------

class TestSetMode:
    def test_ssb_above_10mhz_sets_usb(self):
        client = _make_client()
        proxy = MagicMock()
        _inject_proxy(client, proxy)
        client.set_mode("SSB", freq_khz=14200.0)
        proxy.rig.set_mode.assert_called_once_with("USB")

    def test_ssb_below_10mhz_sets_lsb(self):
        client = _make_client()
        proxy = MagicMock()
        _inject_proxy(client, proxy)
        client.set_mode("SSB", freq_khz=7100.0)
        proxy.rig.set_mode.assert_called_once_with("LSB")

    def test_cw_sets_cwu(self):
        client = _make_client()
        proxy = MagicMock()
        _inject_proxy(client, proxy)
        client.set_mode("CW")
        proxy.rig.set_mode.assert_called_once_with("CW-U")

    def test_returns_false_on_exception(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.set_mode.side_effect = OSError("timeout")
        _inject_proxy(client, proxy)
        result = client.set_mode("SSB")
        assert result is False


# ---------------------------------------------------------------------------
# send_cat_string
# ---------------------------------------------------------------------------

class TestSendCatString:
    def test_returns_true_on_success(self):
        client = _make_client()
        cat_proxy = MagicMock()
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cat_string("PB01;")
        assert result is True
        cat_proxy.rig.cat_string.assert_called_once_with("PB01;")

    def test_returns_true_on_timeout(self):
        """TimeoutError is treated as success — flrig is busy playing audio."""
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cat_string.side_effect = TimeoutError("timeout")
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cat_string("PB01;")
        assert result is True

    def test_returns_false_on_fault(self):
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cat_string.side_effect = xmlrpc.client.Fault(400, "unsupported")
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cat_string("BAD;")
        assert result is False

    def test_returns_false_on_other_error(self):
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cat_string.side_effect = OSError("connection reset")
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cat_string("PB01;")
        assert result is False

    def test_cat_in_flight_cleared_after_success(self):
        client = _make_client()
        cat_proxy = MagicMock()
        _inject_cat_proxy(client, cat_proxy)
        client.send_cat_string("PB01;")
        assert client.cat_in_flight is False

    def test_cat_in_flight_cleared_after_error(self):
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cat_string.side_effect = OSError("error")
        _inject_cat_proxy(client, cat_proxy)
        client.send_cat_string("PB01;")
        assert client.cat_in_flight is False

    def test_log_entry_added(self):
        client = _make_client()
        cat_proxy = MagicMock()
        _inject_cat_proxy(client, cat_proxy)
        client.send_cat_string("PB01;")
        assert any("PB01;" in entry for entry in client.log)


# ---------------------------------------------------------------------------
# send_cw
# ---------------------------------------------------------------------------

class TestSendCw:
    def test_returns_true_on_success(self):
        client = _make_client()
        cat_proxy = MagicMock()
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cw("CQ CQ DE W1AW")
        assert result is True
        cat_proxy.rig.cwio_text.assert_called_once_with("CQ CQ DE W1AW")
        cat_proxy.rig.cwio_send.assert_called_once_with(1)

    def test_returns_true_on_timeout(self):
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cwio_text.side_effect = TimeoutError("busy")
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cw("CQ")
        assert result is True

    def test_returns_false_on_fault(self):
        client = _make_client()
        cat_proxy = MagicMock()
        cat_proxy.rig.cwio_text.side_effect = xmlrpc.client.Fault(500, "CW not available")
        _inject_cat_proxy(client, cat_proxy)
        result = client.send_cw("CQ")
        assert result is False

    def test_cat_in_flight_cleared_after_cw(self):
        client = _make_client()
        cat_proxy = MagicMock()
        _inject_cat_proxy(client, cat_proxy)
        client.send_cw("CQ")
        assert client.cat_in_flight is False


# ---------------------------------------------------------------------------
# is_online / _port_open
# ---------------------------------------------------------------------------

class TestIsOnline:
    def test_online_when_get_frequency_returns_value(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.return_value = 14225000
        _inject_proxy(client, proxy)
        assert client.is_online() is True

    def test_offline_when_get_frequency_returns_none(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_vfo.side_effect = OSError("refused")
        _inject_proxy(client, proxy)
        assert client.is_online() is False

    def test_port_open_returns_false_on_refused(self):
        client = _make_client()
        with patch("socket.create_connection", side_effect=OSError("refused")):
            assert client._port_open() is False

    def test_port_open_returns_true_when_connection_succeeds(self):
        client = _make_client()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            assert client._port_open() is True


# ---------------------------------------------------------------------------
# update_translations
# ---------------------------------------------------------------------------

class TestUpdateTranslations:
    def test_hot_swap_replaces_translations(self):
        client = _make_client()
        proxy = MagicMock()
        proxy.rig.get_mode.return_value = "DATA-U"
        _inject_proxy(client, proxy)

        # Before update: DATA-U passthrough (not in default MODE_MAP)
        assert client.get_mode() == "DATA-U"

        # After update: DATA-U → FT8
        translations = ModeTranslations(
            rig_to_canonical={"DATA-U": "FT8"},
            canonical_to_rig={},
        )
        client.update_translations(translations)
        proxy.rig.get_mode.side_effect = None
        proxy.rig.get_mode.return_value = "DATA-U"
        _inject_proxy(client, proxy)
        assert client.get_mode() == "FT8"
