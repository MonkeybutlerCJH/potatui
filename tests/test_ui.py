# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""UI helper function tests and Textual screen smoke tests."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from potatui.config import Config
from potatui.screens.logger import _shift_status
from potatui.screens.logger_modals import _rst_default


# ---------------------------------------------------------------------------
# _rst_default — pure function, no Textual needed
# ---------------------------------------------------------------------------

class TestRstDefault:
    def test_ssb_returns_59(self):
        assert _rst_default("SSB") == "59"

    def test_cw_returns_599(self):
        assert _rst_default("CW") == "599"

    def test_ft8_returns_minus10(self):
        assert _rst_default("FT8") == "-10"

    def test_ft4_returns_minus10(self):
        assert _rst_default("FT4") == "-10"

    def test_am_returns_59(self):
        assert _rst_default("AM") == "59"

    def test_fm_returns_59(self):
        assert _rst_default("FM") == "59"

    def test_lowercase_mode_handled(self):
        assert _rst_default("ssb") == "59"
        assert _rst_default("cw") == "599"

    def test_unknown_mode_defaults_to_59(self):
        assert _rst_default("OLIVIA") == "59"
        assert _rst_default("") == "59"


# ---------------------------------------------------------------------------
# _shift_status — pure function, no Textual needed
# ---------------------------------------------------------------------------

def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 5, hour, minute, 0)


class TestShiftStatus:
    """POTA shift windows for a park at longitude 0:
        Early Shift: round(2 - 0/15) = 2 UTC, duration 6h  → 02:00–08:00
        Late Shift:  round(18 - 0/15) = 18 UTC, duration 8h → 18:00–02:00
    """

    def test_noon_utc_is_inactive(self):
        assert _shift_status(0.0, _utc(12, 0)) is None

    def test_early_shift_active_at_03(self):
        assert _shift_status(0.0, _utc(3, 0)) == "early"

    def test_early_shift_active_at_start(self):
        assert _shift_status(0.0, _utc(2, 0)) == "early"

    def test_early_shift_inactive_at_exact_end(self):
        # window is [02:00, 08:00) — 08:00 is NOT in the window
        assert _shift_status(0.0, _utc(8, 0)) is None

    def test_late_shift_active_at_20(self):
        assert _shift_status(0.0, _utc(20, 0)) == "late"

    def test_late_shift_active_at_start(self):
        assert _shift_status(0.0, _utc(18, 0)) == "late"

    def test_late_shift_wraps_midnight(self):
        # Late shift at lon=0 is 18:00–02:00 UTC, so 01:00 is in the window
        assert _shift_status(0.0, _utc(1, 0)) == "late"

    def test_late_shift_inactive_at_02(self):
        # 02:00 is the start of early shift, not late shift
        # Late shift ends at 02:00; early shift starts at 02:00
        result_at_02 = _shift_status(0.0, _utc(2, 0))
        # It should be 'early' not 'late' at 02:00
        assert result_at_02 == "early"

    def test_west_longitude_shifts_windows(self):
        # At lon=-75 (US Eastern):
        #   Early shift: round(2+5) = 7 UTC, 6h → 07:00–13:00 UTC
        #   Late shift:  round(18+5) = 23 UTC, 8h → 23:00–07:00 UTC (wraps midnight)
        #   Outside both: 13:00–23:00 UTC
        assert _shift_status(-75.0, _utc(9, 0)) == "early"
        assert _shift_status(-75.0, _utc(1, 0)) == "late"
        assert _shift_status(-75.0, _utc(16, 0)) is None

    def test_east_longitude_shifts_windows(self):
        # At lon=+60: round(2 - 60/15) = round(2 - 4) = round(-2) = -2 % 24 = 22 UTC early start
        # Early shift: 22:00–04:00 UTC (wraps midnight)
        assert _shift_status(60.0, _utc(23, 0)) == "early"
        assert _shift_status(60.0, _utc(12, 0)) is None


# ---------------------------------------------------------------------------
# SetupScreen — Textual smoke test
# ---------------------------------------------------------------------------

def _run_async(coro):
    return asyncio.run(coro)


class TestSetupScreenRender:
    def test_screen_mounts_and_shows_form_fields(self):
        """SetupScreen should mount without errors and expose the core form inputs."""
        from textual.app import App, ComposeResult
        from textual.widgets import Input, Static
        from potatui.screens.setup import SetupScreen

        class _TestApp(App):
            CSS = ""

            def compose(self) -> ComposeResult:
                yield Static("")

            def on_mount(self) -> None:
                config = Config()
                self.push_screen(SetupScreen(config))

        async def run():
            # Patch park lookups so no network is attempted
            with patch("potatui.screens.setup.lookup_park", new=AsyncMock(return_value=None)):
                async with _TestApp().run_test(size=(120, 40)) as pilot:
                    await pilot.pause(0.1)
                    screen = pilot.app.screen
                    # Core form inputs must exist
                    assert screen.query_one("#callsign", Input) is not None
                    assert screen.query_one("#park_refs", Input) is not None
                    assert screen.query_one("#grid_sq", Input) is not None
                    assert screen.query_one("#power_w", Input) is not None

        _run_async(run())

    def test_state_row_hidden_by_default(self):
        """The 'Your State' dropdown row must be hidden until a multi-state park is entered."""
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from potatui.screens.setup import SetupScreen

        class _TestApp(App):
            CSS = ""

            def compose(self) -> ComposeResult:
                yield Static("")

            def on_mount(self) -> None:
                self.push_screen(SetupScreen(Config()))

        async def run():
            with patch("potatui.screens.setup.lookup_park", new=AsyncMock(return_value=None)):
                async with _TestApp().run_test(size=(120, 40)) as pilot:
                    await pilot.pause(0.1)
                    screen = pilot.app.screen
                    state_row = screen.query_one("#state-row")
                    # Should not have the 'visible' class (CSS hides it by default)
                    assert "visible" not in state_row.classes

        _run_async(run())

    def test_park_suggestions_hidden_by_default(self):
        """Park suggestions OptionList should be hidden until the user types."""
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from potatui.screens.setup import SetupScreen

        class _TestApp(App):
            CSS = ""

            def compose(self) -> ComposeResult:
                yield Static("")

            def on_mount(self) -> None:
                self.push_screen(SetupScreen(Config()))

        async def run():
            with patch("potatui.screens.setup.lookup_park", new=AsyncMock(return_value=None)):
                async with _TestApp().run_test(size=(120, 40)) as pilot:
                    await pilot.pause(0.1)
                    screen = pilot.app.screen
                    suggestions = screen.query_one("#park-suggestions")
                    assert "visible" not in suggestions.classes

        _run_async(run())

    def test_callsign_prepopulated_from_config(self):
        """Callsign input should be pre-filled with the config callsign."""
        from textual.app import App, ComposeResult
        from textual.widgets import Input, Static
        from potatui.screens.setup import SetupScreen

        class _TestApp(App):
            CSS = ""

            def compose(self) -> ComposeResult:
                yield Static("")

            def on_mount(self) -> None:
                config = Config()
                config.callsign = "W1AW"
                self.push_screen(SetupScreen(config))

        async def run():
            with patch("potatui.screens.setup.lookup_park", new=AsyncMock(return_value=None)):
                async with _TestApp().run_test(size=(120, 40)) as pilot:
                    await pilot.pause(0.1)
                    screen = pilot.app.screen
                    callsign_input = screen.query_one("#callsign", Input)
                    assert callsign_input.value == "W1AW"

        _run_async(run())


# ---------------------------------------------------------------------------
# LoggerScreen — Textual smoke test
# ---------------------------------------------------------------------------

class TestLoggerScreenRender:
    def _make_session(self):
        from datetime import datetime
        from potatui.session import Session
        return Session(
            operator="W1AW",
            station_callsign="W1AW",
            park_refs=["US-1234"],
            active_park_ref="US-1234",
            grid="FN31",
            rig="IC-7300",
            antenna="EFHW",
            power_w=100,
            start_time=datetime.utcnow(),
        )

    def _make_test_app(self, mode="SSB", freq_khz=14200.0):
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from potatui.screens.logger import LoggerScreen

        session = self._make_session()
        config = Config()
        config.offline_mode = True  # all network workers return immediately

        class _TestApp(App):
            CSS = ""

            def compose(self) -> ComposeResult:
                yield Static("")

            def on_mount(self) -> None:
                self.push_screen(
                    LoggerScreen(session, config, {"US-1234": "Test Park"},
                                 mode=mode, freq_khz=freq_khz)
                )

        return _TestApp()

    def test_logger_screen_mounts(self):
        """LoggerScreen should mount with expected entry form widgets."""
        from textual.widgets import Input

        async def run():
            async with self._make_test_app().run_test(size=(160, 50)) as pilot:
                await pilot.pause(0.2)
                screen = pilot.app.screen
                assert screen.query_one("#f-callsign", Input) is not None
                assert screen.query_one("#f-rst-sent", Input) is not None
                assert screen.query_one("#f-rst-rcvd", Input) is not None
                assert screen.query_one("#f-freq", Input) is not None

        _run_async(run())

    def test_rst_default_ssb_in_logger(self):
        """RST fields should be pre-filled with '59' for SSB mode."""
        from textual.widgets import Input

        async def run():
            async with self._make_test_app(mode="SSB").run_test(size=(160, 50)) as pilot:
                await pilot.pause(0.2)
                screen = pilot.app.screen
                assert screen.query_one("#f-rst-sent", Input).value == "59"
                assert screen.query_one("#f-rst-rcvd", Input).value == "59"

        _run_async(run())

    def test_rst_default_cw_in_logger(self):
        """RST fields should be pre-filled with '599' for CW mode."""
        from textual.widgets import Input

        async def run():
            async with self._make_test_app(mode="CW").run_test(size=(160, 50)) as pilot:
                await pilot.pause(0.2)
                screen = pilot.app.screen
                assert screen.query_one("#f-rst-sent", Input).value == "599"

        _run_async(run())

    def test_freq_field_prepopulated(self):
        """Frequency field should be pre-filled with the passed freq_khz."""
        from textual.widgets import Input

        async def run():
            async with self._make_test_app(freq_khz=7074.0).run_test(size=(160, 50)) as pilot:
                await pilot.pause(0.2)
                screen = pilot.app.screen
                assert screen.query_one("#f-freq", Input).value == "7074.0"

        _run_async(run())
