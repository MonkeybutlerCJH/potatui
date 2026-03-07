"""Live POTA spots screen."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import (
    Checkbox,
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
from potatui.session import Session

BAND_FILTER_OPTIONS = [("All", "All"), ("160m", "160m"), ("80m", "80m"),
                       ("60m", "60m"), ("40m", "40m"), ("30m", "30m"),
                       ("20m", "20m"), ("17m", "17m"), ("15m", "15m"),
                       ("12m", "12m"), ("10m", "10m"), ("6m", "6m"), ("2m", "2m")]
MODE_FILTER_OPTIONS = [("All", "All"), ("SSB", "SSB"), ("CW", "CW"),
                       ("FT8", "FT8"), ("FT4", "FT4"), ("FM", "FM"), ("AM", "AM")]
SORT_OPTIONS = [("Distance", "distance"), ("Age", "age"), ("Frequency", "freq")]


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
# Spots Screen
# ---------------------------------------------------------------------------

class SpotsScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "go_back", "Back"),
        Binding("f5", "go_back", "Back"),
    ]

    # Class-level state persists across visits within a session
    _saved_band: str = "All"
    _saved_mode: str = "All"
    _saved_sort: str = "distance"
    _saved_qrt: bool = True
    _saved_qsy: bool = True

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

    #spots-header:dark {
        background: $primary-darken-3;
        tint: $background 40%;
    }

    #spots-title {
        width: 1fr;
        color: $text;
        text-style: bold;
    }

    #last-refresh {
        width: auto;
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

    .filter-out-label {
        padding-top: 1;
        padding-left: 1;
        width: 12;
        color: $text-muted;
    }

    #band-filter {
        width: 14;
        margin-right: 2;
    }

    #mode-filter {
        width: 14;
        margin-right: 2;
    }

    #sort-select {
        width: 17;
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
        session: Session | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.flrig = flrig
        self._park_latlon = park_latlon
        self._session = session
        self._spots: list[Spot] = []
        self._filtered: list[Spot] = []
        self._park_grid_cache: dict[str, str] = {}  # ref → grid6 from park_db or API

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
            yield Label("Filter out:", classes="filter-out-label")
            yield Checkbox("QRT", value=SpotsScreen._saved_qrt, id="qrt-filter")
            yield Checkbox("QSY", value=SpotsScreen._saved_qsy, id="qsy-filter")

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
        await self._prefetch_park_grids(spots)
        self._apply_filters()

        now_str = datetime.utcnow().strftime("%H:%Mz")
        self.query_one("#last-refresh", Static).update(f"Updated: {now_str}")

    async def _prefetch_park_grids(self, spots: list[Spot]) -> None:
        """Populate _park_grid_cache for all unique spot park references.

        Checks park_db first (instant dict lookup); falls back to the POTA park
        API (grid6) for any refs not found locally.
        """
        import asyncio
        from potatui.pota_api import lookup_park

        refs = list({s.reference for s in spots if s.reference})

        async def _get_grid(ref: str) -> tuple[str, str]:
            info = await lookup_park(ref, self.config.pota_api_base)
            return ref, (info.grid if info and info.grid else "")

        results = await asyncio.gather(*[_get_grid(r) for r in refs])
        self._park_grid_cache = {ref: grid for ref, grid in results if grid}

    def _dist_km(self, spot: Spot) -> float | None:
        """Return distance in km from park to spot, or None if not computable."""
        if self._park_latlon is None:
            return None
        from potatui.qrz import grid_to_latlon, haversine_km
        try:
            # Priority: park_grid_cache (park_db grid6 or API grid6) → spot's own grid field
            grid = self._park_grid_cache.get(spot.reference, "") or spot.grid
            if not grid:
                return None
            slat, slon = grid_to_latlon(grid)
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
        qrt_filt = self.query_one("#qrt-filter", Checkbox).value
        qsy_filt = self.query_one("#qsy-filter", Checkbox).value

        band_filter = str(band_sel.value) if band_sel.value != Select.BLANK else "All"
        mode_filter = str(mode_sel.value) if mode_sel.value != Select.BLANK else "All"
        sort_by = str(sort_sel.value) if sort_sel.value != Select.BLANK else "distance"

        # Persist selections
        SpotsScreen._saved_band = band_filter
        SpotsScreen._saved_mode = mode_filter
        SpotsScreen._saved_sort = sort_by
        SpotsScreen._saved_qrt = qrt_filt
        SpotsScreen._saved_qsy = qsy_filt

        filtered = self._spots
        if band_filter != "All":
            filtered = [s for s in filtered if s.band == band_filter]
        if mode_filter != "All":
            filtered = [s for s in filtered if s.mode.upper() == mode_filter.upper()]
        if qsy_filt:
            filtered = [s for s in filtered if "QSY".casefold() not in s.comments.casefold()]
        if qrt_filt:
            filtered = [s for s in filtered if "QRT".casefold() not in s.comments.casefold()]

        # Sort
        if sort_by == "distance":
            # Spots with known distance first (ascending), then unknowns
            def dist_key(s: Spot) -> tuple:
                km = self._dist_km(s)
                return (1, 0.0) if km is None else (0, km)
            filtered = sorted(filtered, key=dist_key)
        elif sort_by == "age":
            filtered = sorted(filtered, key=lambda s: _spot_age_minutes(s.spot_time))
        elif sort_by == "freq":
            filtered = sorted(filtered, key=lambda s: s.frequency)
        else:
            self.notify(f"Error: unexpected sort: {sort_by}", severity="error")


        self._filtered = filtered
        self._rebuild_table()

    def _worked_callsigns(self) -> set[str]:
        if not self._session:
            return set()
        return {q.callsign.upper() for q in self._session.qsos}

    def _rebuild_table(self) -> None:
        table = self.query_one("#spots-table", DataTable)
        table.clear()
        worked = self._worked_callsigns()
        for spot in self._filtered:
            age = _spot_age_minutes(spot.spot_time)
            is_worked = spot.activator.upper() in worked
            if is_worked:
                activator_cell = Text(f"✓ {spot.activator}", style="bold green")
            else:
                activator_cell = Text(spot.activator)
            table.add_row(
                activator_cell,
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
    @on(Checkbox.Changed, "#qrt-filter")
    @on(Checkbox.Changed, "#qsy-filter")
    def on_filter_changed(self) -> None:
        self._apply_filters()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        table = self.query_one("#spots-table", DataTable)
        try:
            row = table.get_row_at(event.cursor_row)
        except Exception:
            return

        # Activator cell may be a Rich Text with "✓ " prefix — strip it
        activator = str(row[0]).removeprefix("✓ ")
        park_ref = str(row[1])
        freq_str = str(row[3])
        mode = str(row[5])

        try:
            freq_khz = float(freq_str)
        except ValueError:
            return

        ok_freq = self.flrig.set_frequency(freq_khz * 1000)
        ok_mode = self.flrig.set_mode(mode, freq_khz)
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
