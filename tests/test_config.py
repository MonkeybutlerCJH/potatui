# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for load_config() / save_config() round-trip in config.py."""


import pytest

import potatui.config as config_mod
from potatui.config import Config, load_config, save_config

# --------------------------------------------------------------------------
# Fixture: redirect CONFIG_PATH / CONFIG_DIR to a tmp directory
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a throwaway temp directory."""
    cfg_dir = tmp_path / "potatui"
    cfg_dir.mkdir()
    cfg_path = cfg_dir / "config.toml"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config_mod, "CONFIG_PATH", cfg_path)
    # Make sure no real QRZ env vars leak into tests
    monkeypatch.delenv("POTATUI_QRZ_USERNAME", raising=False)
    monkeypatch.delenv("POTATUI_QRZ_PASSWORD", raising=False)
    return cfg_path


# --------------------------------------------------------------------------
# Round-trip: save then reload produces equal Config
# --------------------------------------------------------------------------

class TestRoundTrip:
    def test_default_config_round_trip(self, isolated_config):
        """A freshly-constructed Config survives a save/load cycle."""
        original = Config(
            callsign="W1AW",
            rig="IC-7300",
            antenna="EFHW",
            power_w=50,
            flrig_host="localhost",
            flrig_port=12345,
            pota_api_base="https://api.pota.app",
            p2p_prefix="US-",
            theme="nord",
            distance_unit="mi",
            vk1="PB01;",
            vk2="PB02;",
            vk3="PB03;",
            vk4="PB04;",
            vk5="PB05;",
            offline_mode=False,
        )
        save_config(original)
        loaded = load_config()

        assert loaded.callsign == original.callsign
        assert loaded.rig == original.rig
        assert loaded.antenna == original.antenna
        assert loaded.power_w == original.power_w
        assert loaded.flrig_host == original.flrig_host
        assert loaded.flrig_port == original.flrig_port
        assert loaded.theme == original.theme
        assert loaded.distance_unit == original.distance_unit
        assert loaded.vk1 == original.vk1
        assert loaded.vk5 == original.vk5
        assert loaded.offline_mode == original.offline_mode
        assert loaded.p2p_prefix == original.p2p_prefix

    def test_non_default_values_survive_round_trip(self, isolated_config):
        cfg = Config(
            callsign="VE3TEST",
            power_w=5,
            distance_unit="km",
            flrig_port=7362,
            theme="dracula",
            offline_mode=True,
            p2p_prefix="VE-",
        )
        save_config(cfg)
        loaded = load_config()

        assert loaded.callsign == "VE3TEST"
        assert loaded.power_w == 5
        assert loaded.distance_unit == "km"
        assert loaded.flrig_port == 7362
        assert loaded.theme == "dracula"
        assert loaded.offline_mode is True
        assert loaded.p2p_prefix == "VE-"

    def test_load_creates_default_file_when_missing(self, isolated_config):
        """load_config() creates the config file from the packaged default if absent."""
        assert not isolated_config.exists()
        cfg = load_config()
        assert isolated_config.exists()
        # Default callsign is empty string
        assert cfg.callsign == ""


# --------------------------------------------------------------------------
# Legacy flat format (no TOML sections)
# --------------------------------------------------------------------------

class TestLegacyFlatFormat:
    def test_flat_format_loads_without_crash(self, isolated_config):
        """A flat (section-less) TOML file loads without raising."""
        isolated_config.write_text(
            'callsign = "K1LGY"\n'
            'rig = "FT-817"\n'
            'power_w = 5\n'
            'flrig_port = 12345\n',
            encoding="utf-8",
        )
        cfg = load_config()
        assert cfg.callsign == "K1LGY"
        assert cfg.rig == "FT-817"
        assert cfg.power_w == 5

    def test_flat_format_section_name_collision_not_overwritten(self, isolated_config):
        """A TOML section named 'rig' must NOT overwrite cfg.rig with a dict."""
        # "rig" appears as both a section (dict) and we don't want cfg.rig = {...}
        isolated_config.write_text(
            "[rig]\n"
            'name = "FT-991A"\n'
            "power_w = 100\n",
            encoding="utf-8",
        )
        cfg = load_config()
        # cfg.rig must be the string from _SECTION_MAP ("rig" → "name" under [rig]),
        # not the dict representation of the section.
        assert isinstance(cfg.rig, str)
        assert cfg.rig == "FT-991A"
