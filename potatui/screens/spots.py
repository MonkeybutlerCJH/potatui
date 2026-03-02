"""Live POTA spots screen."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    Select,
    Static,
)

from potatui.adif import freq_to_band
from potatui.config import Config
from potatui.flrig import FlrigClient
from potatui.pota_api import Spot, fetch_spots

BAND_FILTER_OPTIONS = [("All", "All"), ("160m", "160m"), ("80m", "80m"),
                       ("60m", "60m"), ("40m", "40m"), ("30m", "30m"),
                       ("20m", "20m"), ("17m", "17m"), ("15m", "15m"),
                       ("12m", "12m"), ("10m", "10m"), ("6m", "6m"), ("2m", "2m")]
MODE_FILTER_OPTIONS = [("All", "All"), ("SSB", "SSB"), ("CW", "CW"),
                       ("FT8", "FT8"), ("FT4", "FT4"), ("FM", "FM"), ("AM", "AM")]
SORT_OPTIONS = [("Distance", "distance"), ("Age", "age")]


def _spot_age_minutes(spot_time_str: str) -> int:
    """Return minutes since the spot was posted."""
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                t = datetime.strptime(spot_time_str, fmt)
                t = t.replace(tzinfo=timezone.utc)
                delta = datetime.now(timezone.utc) - t
                return max(0, int(delta.total_seconds() / 60))
            except ValueError:
                continue
    except Exception:
        pass
    return 0


# ---------------------------------------------------------------------------
# QSY confirmation modal
# ---------------------------------------------------------------------------

class QSYModal(ModalScreen[bool]):
    CSS = """
    QSYModal { align: center middle; }
    #qsy-box {
        width: 55;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #qsy-title { text-align: center; text-style: bold; margin-bottom: 1; }
    #qsy-msg { margin-bottom: 1; }
    #qsy-btns { align: right middle; height: auto; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="qsy-box"):
            yield Static("QSY Confirmation", id="qsy-title")
            yield Static(self.message, id="qsy-msg")
            with Horizontal(id="qsy-btns"):
                yield Button("Yes", variant="primary", id="yes")
                yield Button("No", id="no")

    @on(Button.Pressed, "#yes")
    def on_yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def on_no(self) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


# ---------------------------------------------------------------------------
# Spots Screen
# ---------------------------------------------------------------------------

class SpotsScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("q", "go_back", "Back"),
        Binding("f5", "go_back", "Back"),
    ]

    # Class-level state persists across visits within a session
    _saved_band: str = "All"
    _saved_mode: str = "All"
    _saved_sort: str = "distance"

    CSS = """
    SpotsScreen {
        layout: vertical;
    }

    #spots-header {
        height: 3;
        background: $primary-darken-2;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    #spots-title {
        width: 1fr;
        color: $text;
        text-style: bold;
    }

    #last-refresh {
        color: $text-muted;
    }

    #filter-bar {
        height: auto;
        padding: 1;
        background: $surface-darken-1;
        border-bottom: solid $primary-darken-2;
        layout: horizontal;
    }

    .filter-label {
        padding-top: 1;
        width: 8;
        color: $text-muted;
    }

    .sort-label {
        padding-top: 1;
        width: 6;
        color: $text-muted;
    }

    #band-filter {
        width: 12;
        margin-right: 2;
    }

    #mode-filter {
        width: 12;
        margin-right: 2;
    }

    #sort-select {
        width: 14;
    }

    #error-msg {
        color: $error;
        padding: 1;
        height: auto;
    }

    DataTable {
        height: 1fr;
    }
    """

    def __init__(
        self,
        config: Config,
        flrig: FlrigClient,
        park_latlon: tuple[float, float] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.flrig = flrig
        self._park_latlon = park_latlon
        self._spots: list[Spot] = []
        self._filtered: list[Spot] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="spots-header"):
            yield Static("POTA Live Spots", id="spots-title")
            yield Static("", id="last-refresh")

        with Horizontal(id="filter-bar"):
            yield Label("Band:", classes="filter-label")
            yield Select(BAND_FILTER_OPTIONS, value=SpotsScreen._saved_band, id="band-filter")
            yield Label("Mode:", classes="filter-label")
            yield Select(MODE_FILTER_OPTIONS, value=SpotsScreen._saved_mode, id="mode-filter")
            yield Label("Sort:", classes="sort-label")
            yield Select(SORT_OPTIONS, value=SpotsScreen._saved_sort, id="sort-select")

        yield Static("", id="error-msg")
        yield DataTable(id="spots-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#spots-table", DataTable)
        table.add_columns(
            "Activator", "Park", "Park Name", "Freq", "Band",
            "Mode", "State", "Dist", "Age", "Comments"
        )
        self._do_refresh()
        self.set_interval(60.0, self._do_refresh)

    def action_refresh(self) -> None:
        self._do_refresh()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    @work(exclusive=True)
    async def _do_refresh(self) -> None:
        error_widget = self.query_one("#error-msg", Static)
        error_widget.update("")

        spots = await fetch_spots(self.config.pota_api_base)
        if not spots:
            error_widget.update("Could not fetch spots (API unavailable or no spots)")
            return

        self._spots = spots
        self._apply_filters()

        now_str = datetime.utcnow().strftime("%H:%Mz")
        self.query_one("#last-refresh", Static).update(f"Updated: {now_str}")

    def _dist_km(self, spot: Spot) -> float | None:
        """Return distance in km from park to spot, or None if not computable."""
        if self._park_latlon is None or not spot.grid:
            return None
        from potatui.qrz import grid_to_latlon, haversine_km
        try:
            slat, slon = grid_to_latlon(spot.grid)
            plat, plon = self._park_latlon
            return haversine_km(plat, plon, slat, slon)
        except Exception:
            return None

    def _dist_str(self, spot: Spot) -> str:
        km = self._dist_km(spot)
        if km is None:
            return "—"
        use_mi = self.config.distance_unit.lower() == "mi"
        if use_mi:
            return f"{km * 0.621371:,.0f} mi"
        return f"{km:,.0f} km"

    def _apply_filters(self) -> None:
        band_sel = self.query_one("#band-filter", Select)
        mode_sel = self.query_one("#mode-filter", Select)
        sort_sel = self.query_one("#sort-select", Select)

        band_filter = str(band_sel.value) if band_sel.value != Select.BLANK else "All"
        mode_filter = str(mode_sel.value) if mode_sel.value != Select.BLANK else "All"
        sort_by = str(sort_sel.value) if sort_sel.value != Select.BLANK else "distance"

        # Persist selections
        SpotsScreen._saved_band = band_filter
        SpotsScreen._saved_mode = mode_filter
        SpotsScreen._saved_sort = sort_by

        filtered = self._spots
        if band_filter != "All":
            filtered = [s for s in filtered if s.band == band_filter]
        if mode_filter != "All":
            filtered = [s for s in filtered if s.mode.upper() == mode_filter.upper()]

        # Sort
        if sort_by == "distance":
            # Spots with known distance first (ascending), then unknowns
            def dist_key(s: Spot) -> tuple:
                km = self._dist_km(s)
                return (1, 0.0) if km is None else (0, km)
            filtered = sorted(filtered, key=dist_key)
        else:  # age — newest first
            filtered = sorted(filtered, key=lambda s: _spot_age_minutes(s.spot_time))

        self._filtered = filtered
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one("#spots-table", DataTable)
        table.clear()
        for spot in self._filtered:
            age = _spot_age_minutes(spot.spot_time)
            table.add_row(
                spot.activator,
                spot.reference,
                spot.park_name[:22] if spot.park_name else "",
                f"{spot.frequency:.1f}",
                spot.band,
                spot.mode,
                spot.location,
                self._dist_str(spot),
                str(age),
                spot.comments[:28] if spot.comments else "",
                key=f"{spot.activator}-{spot.reference}-{spot.frequency}",
            )

    @on(Select.Changed, "#band-filter")
    @on(Select.Changed, "#mode-filter")
    @on(Select.Changed, "#sort-select")
    def on_filter_changed(self) -> None:
        self._apply_filters()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        table = self.query_one("#spots-table", DataTable)
        try:
            row = table.get_row_at(event.cursor_row)
        except Exception:
            return

        activator = str(row[0])
        park_ref = str(row[1])
        freq_str = str(row[3])
        mode = str(row[5])

        try:
            freq_khz = float(freq_str)
        except ValueError:
            return

        msg = f"QSY to {freq_khz:.1f} kHz {mode}\nfor {activator} at {park_ref}?"

        def on_confirm(confirmed: bool) -> None:
            if not confirmed:
                return
            ok_freq = self.flrig.set_frequency(freq_khz * 1000)
            ok_mode = self.flrig.set_mode(mode)
            if not ok_freq or not ok_mode:
                self.notify("flrig not connected — radio not tuned", severity="warning")
            self.app.pop_screen()
            from potatui.screens.logger import LoggerScreen
            for screen in self.app.screen_stack:
                if isinstance(screen, LoggerScreen):
                    screen.prefill_callsign(activator)
                    screen.update_freq_mode(freq_khz, mode)
                    screen.prefill_p2p(park_ref)
                    break

        self.app.push_screen(QSYModal(msg), on_confirm)
