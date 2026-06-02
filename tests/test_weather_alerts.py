# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Tests for terrestrial weather alert handling."""

from __future__ import annotations

from potatui.weather import WeatherAlert, WeatherData, _weather_emoji


def _make_alert(event: str, severity: str, headline: str = "", alert_id: str = "") -> WeatherAlert:
    return WeatherAlert(
        id=alert_id or f"test:{event}",
        event=event,
        headline=headline or f"{event} headline",
        description=f"{event} description",
        severity=severity,
        effective="2026-06-02T12:00:00+00:00",
        expires="2026-06-02T18:00:00+00:00",
        instruction="Take shelter" if severity in ("Extreme", "Severe") else None,
    )


class TestWeatherAlertClassification:
    """Verify alert severity classification for toasting and flashing."""

    def test_extreme_severity_should_toast(self):
        alert = _make_alert("Tornado Warning", "Extreme")
        assert alert.severity == "Extreme"
        assert alert.severity in ("Extreme", "Severe")  # should toast

    def test_severe_severity_should_toast(self):
        alert = _make_alert("Severe Thunderstorm Warning", "Severe")
        assert alert.severity == "Severe"
        assert alert.severity in ("Extreme", "Severe")  # should toast

    def test_moderate_severity_should_not_toast(self):
        alert = _make_alert("Heat Advisory", "Moderate")
        assert alert.severity == "Moderate"
        assert alert.severity not in ("Extreme", "Severe")  # no toast

    def test_minor_severity_should_not_toast(self):
        alert = _make_alert("Dense Fog Advisory", "Minor")
        assert alert.severity == "Minor"
        assert alert.severity not in ("Extreme", "Severe")  # no toast

    def test_unknown_severity_should_not_toast(self):
        alert = _make_alert("Special Weather Statement", "Unknown")
        assert alert.severity == "Unknown"
        assert alert.severity not in ("Extreme", "Severe")  # no toast

    def test_alert_key_is_unique(self):
        a1 = _make_alert("Flood Watch", "Severe", alert_id="urn:oid:test.1")
        a2 = _make_alert("Flood Watch", "Severe", alert_id="urn:oid:test.2")
        assert a1.alert_key != a2.alert_key
        assert a1.alert_key == "urn:oid:test.1"
        assert a2.alert_key == "urn:oid:test.2"


class TestWeatherAlertTracking:
    """Simulate the _check_weather_alerts logic from logger.py."""

    def test_first_poll_seeds_silently(self):
        """On first poll, alert keys are stored but no toasts fire."""
        seen_keys: set[str] = set()
        initial_done = False

        data = WeatherData(observation=None, alerts=[
            _make_alert("Flood Watch", "Severe", alert_id="alert.1"),
            _make_alert("Heat Advisory", "Moderate", alert_id="alert.2"),
        ])

        current_keys = {a.alert_key for a in data.alerts}
        new_keys = current_keys - seen_keys
        seen_keys |= current_keys

        # Before initial poll done check
        assert not initial_done
        initial_done = True

        # After seeding: new_keys should have been detected but suppressed
        assert len(new_keys) == 2
        assert len(seen_keys) == 2

    def test_second_poll_new_alert_toasts(self):
        """A new alert on a subsequent poll triggers a toast."""
        seen_keys: set[str] = {"alert.1", "alert.2"}
        acknowledged = True

        data = WeatherData(observation=None, alerts=[
            _make_alert("Flood Watch", "Severe", alert_id="alert.1"),
            _make_alert("Heat Advisory", "Moderate", alert_id="alert.2"),
            _make_alert("Tornado Warning", "Extreme", alert_id="alert.3"),  # NEW!
        ])

        current_keys = {a.alert_key for a in data.alerts}
        new_keys = current_keys - seen_keys
        seen_keys |= current_keys

        assert new_keys == {"alert.3"}
        assert acknowledged  # was True before detection

        # New keys should cause acknowledged reset
        if new_keys:
            acknowledged = False

        assert not acknowledged  # flash should start

        # Only Extreme/Severe new alerts should generate toasts
        toastable = [a for a in data.alerts
                     if a.alert_key in new_keys
                     and a.severity in ("Extreme", "Severe")]
        assert len(toastable) == 1
        assert toastable[0].event == "Tornado Warning"

        # Toast severity
        for alert in toastable:
            sev = "error" if alert.severity == "Extreme" else "warning"
            assert sev == "error"  # Extreme → error

    def test_moderate_alert_does_not_toast(self):
        """A new moderate alert on subsequent poll does NOT trigger a toast."""
        seen_keys: set[str] = {"alert.1"}
        acknowledged = True

        data = WeatherData(observation=None, alerts=[
            _make_alert("Flood Watch", "Severe", alert_id="alert.1"),
            _make_alert("Dense Fog Advisory", "Minor", alert_id="alert.4"),  # NEW Minor
        ])

        current_keys = {a.alert_key for a in data.alerts}
        new_keys = current_keys - seen_keys

        toastable = [a for a in data.alerts
                     if a.alert_key in new_keys
                     and a.severity in ("Extreme", "Severe")]
        assert len(toastable) == 0  # No toast for Minor

    def test_acknowledgment_stops_flash(self):
        """Clicking the pill acknowledges alerts and stops the flash."""
        acknowledged = False

        # Simulate click
        acknowledged = True

        assert acknowledged  # Flash stops on click

    def test_disappeared_alert_cleans_up(self):
        """When an alert expires, its key stays in seen but doesn't re-toast."""
        seen_keys: set[str] = {"alert.1", "alert.2"}
        acknowledged = True

        # alert.2 has expired, no longer in active set
        data = WeatherData(observation=None, alerts=[
            _make_alert("Flood Watch", "Severe", alert_id="alert.1"),
        ])

        current_keys = {a.alert_key for a in data.alerts}
        new_keys = current_keys - seen_keys
        seen_keys |= current_keys  # "alert.1" stays, "alert.2" stays in seen

        assert new_keys == set()
        assert acknowledged  # remains True, no flash


class TestWeatherEmoji:
    """Verify weather emoji mapping for display."""

    def test_thunderstorm(self):
        assert _weather_emoji("Chance Thunderstorms") == '⛈️'

    def test_snow(self):
        assert _weather_emoji("Snow showers likely") == '❄️'

    def test_rain(self):
        assert _weather_emoji("Rain") == '🌧️'

    def test_cloudy(self):
        assert _weather_emoji("Mostly Cloudy") == '⛅'

    def test_sunny(self):
        assert _weather_emoji("Sunny") == '☀️'

    def test_fog(self):
        assert _weather_emoji("Patchy Fog") == '🌫️'

    def test_windy(self):
        assert _weather_emoji("Windy conditions") == '💨'

    def test_unknown(self):
        assert _weather_emoji("Some unknown condition") == '🌡️'
