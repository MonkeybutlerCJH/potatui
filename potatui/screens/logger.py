# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Main logging screen."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    Static,
)
from textual.widgets._input import Selection

from potatui.adif import append_qso_adif, freq_to_band, session_file_stem, write_adif
from potatui.config import Config
from potatui.flrig import FlrigClient
from potatui.propagation import PropProfile
from potatui.screens.logger_modals import (
    AboutModal,
    ChangeOperatorModal,
    ConfirmModal,
    EditQSOModal,
    ModePickerModal,
    NetworkStatusModal,
    NetworkStatusSnapshot,
    SelfSpotModal,
    SessionSummaryModal,
    SetFreqModal,
    SolarWeatherModal,
    WawaModal,
    _rst_default,
)
from potatui.session import QSO, Session
from potatui.space_weather import (
    SpaceWeatherData,
    fetch_muf,
    fetch_space_weather,
    kp_severity,
    kp_traditional,
)
from potatui.wsjtx import WsjtxClient

# ---------------------------------------------------------------------------
# Shift helpers
# ---------------------------------------------------------------------------

def _shift_status(lon: float, utc_now: datetime) -> str | None:
    """Return 'early', 'late', or None based on park longitude and current UTC.

    Early Shift: 6-hour period starting at round(2 - lon/15) UTC.
    Late Shift:  8-hour period starting at round(18 - lon/15) UTC.
    """
    early_start = round(2 - lon / 15) % 24
    late_start = round(18 - lon / 15) % 24
    minutes_utc = utc_now.hour * 60 + utc_now.minute

    def _in(start_h: int, duration_h: int) -> bool:
        start_m = start_h * 60
        end_m = (start_m + duration_h * 60) % (24 * 60)
        if end_m > start_m:
            return start_m <= minutes_utc < end_m
        # window wraps midnight
        return minutes_utc >= start_m or minutes_utc < end_m

    if _in(early_start, 6):
        return "early"
    if _in(late_start, 8):
        return "late"
    return None


# ---------------------------------------------------------------------------
# Main Logger Screen
# ---------------------------------------------------------------------------

class LoggerScreen(Screen):
    BINDINGS = [
        Binding("f1", "about", "About", show=False),
        Binding("f2", "set_freq", "Set Run Freq"),
        Binding("f3", "mode_picker", "Mode"),
        Binding("f4", "edit_last_qso", "Edit QSO"),
        Binding("f5", "goto_spots", "Spots"),
        Binding("ctrl+s", "goto_spots", "Spots", show=False),
        Binding("f6", "self_spot", "Self-Spot"),
        Binding("f7", "commander", "Commander"),
        Binding("f8", "settings", "Settings"),
        Binding("f10", "end_session", "End Session"),
        Binding("ctrl+o", "change_operator", "Operator"),
        Binding("ctrl+n", "toggle_offline", "Offline Mode", show=False),
        Binding("escape", "clear_form", "Clear / Back"),
        # Table-mode only (shown when QSO table is focused)
        Binding("ctrl+d", "delete_qso", "Delete"),
        Binding("ctrl+l", "qrz_lookup_selected", "Lookup"),
        Binding("ctrl+b", "qrz_backfill", "Backfill All"),
    ]

    CSS_PATH = "logger.tcss"

    def __init__(
        self,
        session: Session,
        config: Config,
        park_names: dict[str, str],
        mode: str = "SSB",
        freq_khz: float = 14200.0,
    ) -> None:
        super().__init__()
        self.session = session
        self.config = config
        self.freq_khz: float = freq_khz
        self.band = freq_to_band(self.freq_khz)
        self.mode = mode
        self.park_names = park_names
        self.flrig = FlrigClient(config.flrig_host, config.flrig_port)
        self._flrig_online = False
        self._flrig_online_prev: bool | None = None  # tracks previous state for change detection
        self._flrig_log: list[str] = []  # timestamped connection events
        self._wsjtx = WsjtxClient(config.wsjtx_host, config.wsjtx_port)
        self._wsjtx_online = False
        self._wsjtx_online_prev: bool | None = None
        self._wsjtx_log: list[str] = []  # timestamped connection events
        from potatui.commands import CommandConfig, load_commands
        legacy_vk = [config.vk1, config.vk2, config.vk3, config.vk4, config.vk5]
        self._cmd_config: CommandConfig = load_commands(legacy_vk)
        from potatui.hamdb import HamDbClient
        from potatui.qrz import QRZClient
        self._qrz = QRZClient(config.qrz_username, config.qrz_password, config.qrz_api_url)
        self._hamdb = HamDbClient()
        self._park_latlon: tuple[float, float] | None = None
        self._park_grid: str | None = None  # grid square used for MUF lookup
        self._shift_lon: float | None = None  # longitude for shift calc (state pin for multi-location parks)
        self._last_spot_data: tuple[datetime, str, str] | None = None  # (utc_time, spotter, comments)
        self._qrz_filled_name: bool = False   # True if #f-name was auto-filled by QRZ
        self._qrz_filled_state: bool = False  # True if #f-state was auto-filled by QRZ
        self._p2p_last_value: str = ""        # Previous P2P field value for auto-fill guard
        self._qrz_bars: dict[str, Static] = {}  # callsign → QRZ info bar widget
        self._qrz_contact_info: dict[str, tuple[str, float | None]] = {}  # callsign → (grid, dist_km)
        self._prop_profile: PropProfile = PropProfile()
        self._celebrated_100: bool = False  # fire rainbow only once per session
        self._table_focused: bool = False  # True when QSO table has focus
        self._solar_data: SpaceWeatherData | None = None
        self._seen_alert_keys: set[str] = set()
        self._solar_initial_poll_done: bool = False
        self._solar_alerts_acknowledged: bool = False
        self._solar_flash_timer: Timer | None = None
        self._solar_flash_toggle_state: bool = False
        self._offline: bool = config.offline_mode  # True = skip all internet calls
        self._offline_manual: bool = config.offline_mode  # True = user explicitly set offline
        self._current_utc_date = datetime.utcnow().date()
        self._clock_tick_count: int = 0
        self._log_paths = self._make_log_paths()
        self._json_path = self._make_json_path()

    def _make_log_paths(self):
        return [
            self.config.log_dir_path / f"{session_file_stem(self.session, ref)}.adi"
            for ref in self.session.park_refs
        ]

    def _make_json_path(self):
        stem = session_file_stem(self.session)
        return self.config.log_dir_path / f"{stem}.json"

    def compose(self) -> ComposeResult:
        # Header bar
        with Horizontal(id="header-bar"):
            yield Static("", id="hdr-sta", classes="hdr-item")
            yield Static("|", classes="hdr-sep")
            yield Static("", id="hdr-park", classes="hdr-item")
            yield Static("|", classes="hdr-sep")
            yield Static("", id="hdr-utc", classes="hdr-item")
            yield Static("|", classes="hdr-sep")
            yield Static("", id="hdr-radio", classes="hdr-item")
            yield Static("|", classes="hdr-sep")
            yield Static("", id="hdr-qso-count", classes="hdr-item")
            yield Static("|", classes="hdr-sep")
            yield Static("", id="hdr-elapsed", classes="hdr-item")
            yield Static("", id="hdr-spacer")
            yield Static("net", id="hdr-net", classes="net-unknown")
            yield Static("|", classes="hdr-sep")
            yield Static("K:?", id="hdr-solar", classes="solar-unknown")
            yield Static("|", id="hdr-shift-sep", classes="hdr-sep shift-inactive")
            yield Static("", id="hdr-shift", classes="shift-inactive")

        # Last-spotted bar (hidden until a spot is found)
        yield Static("", id="last-spotted-bar", classes="hidden")

        # Entry form (two rows)
        with Vertical(id="entry-form"):
            with Horizontal(id="entry-row1"):
                with Vertical(classes="form-field", id="callsign-field"):
                    yield Label("Callsign", classes="form-label")
                    yield Input(placeholder="W1AW,NV3Y", id="f-callsign")
                    yield Static("", id="dup-warning")
                with Vertical(classes="form-field", id="rst-sent-field"):
                    yield Label("RST Snt", classes="form-label")
                    yield Input(value=_rst_default(self.mode), id="f-rst-sent", max_length=3, select_on_focus=False)
                with Vertical(classes="form-field", id="rst-rcvd-field"):
                    yield Label("RST Rcv", classes="form-label")
                    yield Input(value=_rst_default(self.mode), id="f-rst-rcvd", max_length=3, select_on_focus=False)
                with Vertical(classes="form-field", id="p2p-field"):
                    yield Label("P2P Park", classes="form-label")
                    yield Input(value=self.config.p2p_prefix, id="f-p2p", select_on_focus=False)
                with Vertical(classes="form-field", id="freq-field"):
                    yield Label("Freq (kHz)", classes="form-label")
                    yield Input(value=f"{self.freq_khz:.1f}", id="f-freq", max_length=10)
                with Vertical(classes="form-field"):
                    yield Label(" ", classes="form-label")
                    yield Button("Log [Enter]", variant="primary", id="btn-log")
            with Horizontal(id="entry-row2"):
                with Vertical(classes="form-field", id="name-field"):
                    yield Label("Name", classes="form-label")
                    yield Input(placeholder="optional", id="f-name")
                with Vertical(classes="form-field", id="state-field"):
                    yield Label("State/Loc", classes="form-label")
                    yield Input(placeholder="optional", id="f-state")
                with Vertical(classes="form-field", id="notes-field"):
                    yield Label("Notes", classes="form-label")
                    yield Input(placeholder="optional", id="f-notes")

        # QRZ callsign info strips (one per callsign in multi-callsign mode)
        yield Vertical(id="qrz-info-container")

        # P2P park info strip (hidden when empty)
        yield Static("", id="p2p-info-bar", classes="hidden")

        # QSO table
        with Container(id="qso-table-container"):
            yield DataTable(id="qso-table", cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        # Seed prop profile from any existing QSOs (resumed session)
        for qso in self.session.qsos:
            if qso.distance_km is not None:
                self._prop_profile.add_qso(qso.band, qso.distance_km)
        if self.session.qsos:
            self._rebuild_table()
        self._update_header()
        self._wsjtx.start()
        self.set_interval(1.0, self._tick_clock)
        self.set_interval(2.0, self._poll_flrig)
        self.set_interval(2.0, self._poll_wsjtx)
        self.set_interval(30.0, self._check_internet_connectivity)
        self.set_interval(60.0, self._poll_spots_for_self)
        self.set_interval(600.0, self._poll_space_weather)
        if self._offline_manual:
            net_widget = self.query_one("#hdr-net", Static)
            net_widget.update("OFFL")
            net_widget.set_classes("net-offline-manual")
        else:
            self._check_internet_connectivity()
        self._fetch_park_location()
        self._poll_spots_for_self()
        self._update_qrz_indicator()
        self._poll_space_weather()
        self.query_one("#f-callsign", Input).focus()

    @work
    async def _fetch_park_location(self) -> None:
        """Fetch the active park's lat/lon for distance calculations.

        If the user specified a grid at activation setup (session.grid), that
        takes priority — it reflects their actual operating position within the park.
        Falls back to the park's lat/lon from the POTA API/local DB.
        """
        from potatui.qrz import grid_to_latlon
        # User's grid takes priority for distance calcs (_park_latlon)
        if self.session.grid:
            try:
                self._park_latlon = grid_to_latlon(self.session.grid)
                self._park_grid = self.session.grid
            except Exception:
                pass
        # If grid didn't resolve, fall back to the park's own lat/lon
        if self._park_latlon is None:
            if self._offline:
                # Try local DB only — no API call
                from potatui.park_db import park_db
                info = park_db.lookup(self.session.active_park_ref) if park_db.loaded else None
            else:
                from potatui.pota_api import lookup_park
                info = await lookup_park(self.session.active_park_ref, self.config.pota_api_base)
            if info:
                if info.lat is not None and info.lon is not None:
                    self._park_latlon = (info.lat, info.lon)
                    self._park_grid = info.grid or None
                elif info.grid:
                    try:
                        self._park_latlon = grid_to_latlon(info.grid)
                        self._park_grid = info.grid
                    except Exception:
                        pass
        # For multi-location parks, use the state/province pin longitude for shift calc.
        # Key is the full locationDesc (e.g. "US-CT") to avoid cross-entity abbrev collisions.
        if self.session.my_state and not self._offline:
            from potatui.pota_api import fetch_location_pins
            pins = await fetch_location_pins(self.config.pota_api_base)
            entity = self.session.active_park_ref.split("-")[0]  # "US" from "US-4556"
            location_key = f"{entity}-{self.session.my_state}"   # "US-CT"
            if location_key in pins:
                self._shift_lon = pins[location_key][1]
        if self._shift_lon is None and self._park_latlon is not None:
            self._shift_lon = self._park_latlon[1]
        self._update_shift_indicator()
        # Kick off MUF fetch now that we have coordinates (the space-weather poll
        # may have already fired before _park_latlon was resolved)
        if self._park_latlon is not None and not self._offline:
            self._poll_space_weather()

    def _setup_table(self) -> None:
        table = self.query_one("#qso-table", DataTable)
        table.add_columns("#", "UTC", "Callsign", "Sent", "Rcvd", "Freq", "Mode", "Name", "State", "P2P", "Notes")

    def _update_header(self) -> None:
        park_ref = self.session.active_park_ref
        park_name = self.park_names.get(park_ref, "")
        # Only append name if it's non-empty and different from the ref itself
        if park_name and park_name != park_ref:
            if len(park_name) > 25:
                park_name = park_name[:25].rstrip() + "…"
            park_display = f"{park_ref}  {park_name}"
        else:
            park_display = park_ref
        self.query_one("#hdr-park", Static).update(park_display)
        call_sta = self.session.station_callsign
        call_op  = self.session.operator
        if not call_op or call_op == call_sta:
            sta_display = call_sta
        else:
            sta_display = f"{call_sta} ({call_op})"
        self.query_one("#hdr-sta", Static).update(sta_display)
        self._update_radio_display()
        self._update_qso_count()

    def _update_radio_display(self) -> None:
        if self._flrig_online:
            radio_str = f"{self.freq_khz:.1f} kHz  {self.band}  {self.mode}"
        else:
            radio_str = f"---  {self.band}  {self.mode}"
        self.query_one("#hdr-radio", Static).update(radio_str)


    def _update_shift_indicator(self) -> None:
        """Update the Early/Late Shift emoji indicator in the header."""
        widget = self.query_one("#hdr-shift", Static)
        sep = self.query_one("#hdr-shift-sep", Static)
        if self._shift_lon is None:
            widget.update("")
            widget.set_classes("shift-inactive")
            sep.set_classes("hdr-sep shift-inactive")
            return
        lon = self._shift_lon
        status = _shift_status(lon, datetime.utcnow())
        if status == "early":
            widget.update("🌅")
            widget.set_classes("shift-early")
            sep.set_classes("hdr-sep")
        elif status == "late":
            widget.update("🌙")
            widget.set_classes("shift-late")
            sep.set_classes("hdr-sep")
        else:
            widget.update("")
            widget.set_classes("shift-inactive")
            sep.set_classes("hdr-sep shift-inactive")

    @on(events.Click, "#hdr-shift")
    def _on_shift_click(self) -> None:
        if self._shift_lon is None:
            return
        lon = self._shift_lon
        now = datetime.utcnow()
        early_start = round(2 - lon / 15) % 24
        late_start = round(18 - lon / 15) % 24
        status = _shift_status(lon, now)
        if status == "early":
            end_h = (early_start + 6) % 24
            self.notify(
                f"Early Shift active: {early_start:02d}:00 – {end_h:02d}:00 UTC",
                title="🌅 Early Shift",
            )
        elif status == "late":
            end_h = (late_start + 8) % 24
            self.notify(
                f"Late Shift active: {late_start:02d}:00 – {end_h:02d}:00 UTC",
                title="🌙 Late Shift",
            )

    def _update_qso_count(self) -> None:
        now = datetime.utcnow()
        today = now.date()
        today_count = sum(1 for q in self.session.qsos if q.timestamp_utc.date() == today)
        total_count = len(self.session.qsos)
        circle = "[green]●[/green]" if today_count >= 10 else "[red]●[/red]"
        elapsed_hours = (now - self.session.start_time).total_seconds() / 3600
        if elapsed_hours < 1.0:
            count = len(self.session.qsos)
            rate = int(count / elapsed_hours) if elapsed_hours > 0 and count > 0 else 0
        else:
            cutoff = now - timedelta(hours=1)
            rate = sum(1 for q in self.session.qsos if q.timestamp_utc >= cutoff)
        rate_str = f"{rate}/hr" if (rate > 0 or self.session.qsos) else "--/hr"
        if total_count != today_count:
            text = f"{circle} QSOs: {today_count} ({total_count} total)  {rate_str}"
        else:
            text = f"{circle} QSOs: {today_count}  {rate_str}"
        self.query_one("#hdr-qso-count", Static).update(text)
        if total_count >= 100 and not self._celebrated_100:
            self._celebrated_100 = True
            self._rainbow_flash()

    @work(exclusive=False)
    async def _rainbow_flash(self) -> None:
        """Celebrate 100 QSOs with a non-blocking rainbow border animation."""
        self.notify("100 QSOs! 🎉", timeout=4)
        container = self.query_one("#qso-table-container")
        rainbow_classes = [f"rainbow-{i}" for i in range(7)]
        steps = 28  # 4 full spectrum cycles
        for step in range(steps):
            cls = rainbow_classes[step % 7]
            for old in rainbow_classes:
                container.remove_class(old)
            container.add_class(cls)
            await asyncio.sleep(0.12)
        for cls in rainbow_classes:
            container.remove_class(cls)

    def _tick_clock(self) -> None:
        now = datetime.utcnow()
        if now.date() != self._current_utc_date:
            self._current_utc_date = now.date()
            self.notify(
                "UTC date has changed — new activation day has begun! "
                "You need 10 QSOs today for a valid activation.",
                severity="warning",
                timeout=15,
            )
            self._update_qso_count()
        utc_str = now.strftime("%H:%Mz")
        elapsed = now - self.session.start_time
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"
        self.query_one("#hdr-utc", Static).update(utc_str)
        self.query_one("#hdr-elapsed", Static).update(elapsed_str)
        self._update_qso_count()
        # On Windows/ConPTY each widget update is expensive. These two status
        # indicators change slowly, so throttle them to every 5s on Windows.
        self._clock_tick_count += 1
        if sys.platform != "win32" or self._clock_tick_count % 5 == 0:
            self._update_last_spotted_bar()
            self._update_shift_indicator()

    @work(exclusive=True, group="self-spot-poll")
    async def _poll_spots_for_self(self) -> None:
        """Fetch current POTA spots and find the most recent one for our callsign."""
        if self._offline:
            return
        from potatui.pota_api import fetch_spots
        spots = await fetch_spots(self.config.pota_api_base)
        my_call = self.session.operator.upper()
        my_spots = [s for s in spots if s.activator.upper() == my_call]
        if not my_spots:
            return

        def _parse_spot_time(s) -> datetime:
            try:
                dt = datetime.fromisoformat(s.spot_time.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except Exception:
                return datetime.min.replace(tzinfo=UTC)

        latest = max(my_spots, key=_parse_spot_time)
        spot_dt = _parse_spot_time(latest)
        self._last_spot_data = (spot_dt, latest.spotter, latest.comments)
        self._update_last_spotted_bar()

    def _update_last_spotted_bar(self) -> None:
        try:
            bar = self.query_one("#last-spotted-bar", Static)
        except Exception:
            return
        if self._last_spot_data is None:
            bar.set_classes("hidden")
            return
        spot_dt, spotter, comments = self._last_spot_data
        now = datetime.now(UTC)
        age_min = int((now - spot_dt).total_seconds() / 60)
        if age_min < 60:
            age_str = f"{age_min}m ago"
        else:
            age_str = f"{age_min // 60}h {age_min % 60}m ago"
        text = f" Last spotted {age_str} by {spotter}"
        if comments:
            text += f"  —  {comments}"
        bar.update(text)
        if age_min < 15:
            bar.set_classes("spot-recent")
        elif age_min < 30:
            bar.set_classes("spot-stale")
        else:
            bar.set_classes("spot-old")

    @work(exclusive=True, group="flrig-poll")
    async def _poll_flrig(self) -> None:
        import asyncio
        freq, mode = await asyncio.to_thread(
            lambda: (self.flrig.get_frequency(), self.flrig.get_mode())
        )

        now_online = freq is not None
        if freq is not None:
            self._flrig_online = True
            self.freq_khz = freq
            band = freq_to_band(freq)
            if band != "?":
                self.band = band
            if mode and mode != self.mode:
                old_mode = self.mode
                self.mode = mode
                # Update RST defaults when the mode changes (e.g. rig switched
                # CW ↔ SSB), but only if the fields still hold the old default
                # so we don't clobber a value the user has already typed.
                old_default = _rst_default(old_mode)
                new_default = _rst_default(mode)
                if old_default != new_default:
                    rst_sent = self.query_one("#f-rst-sent", Input)
                    rst_rcvd = self.query_one("#f-rst-rcvd", Input)
                    if rst_sent.value == old_default:
                        rst_sent.value = new_default
                    if rst_rcvd.value == old_default:
                        rst_rcvd.value = new_default
            elif mode:
                self.mode = mode
            # Sync the freq input field (only if it doesn't have focus —
            # don't clobber what the user is typing)
            freq_inp = self.query_one("#f-freq", Input)
            if not freq_inp.has_focus:
                freq_inp.value = f"{freq:.1f}"
        elif not self.flrig.cat_in_flight:
            # Only mark offline if no CAT command is in flight — flrig's
            # XML-RPC server blocks completely during voice playback, making
            # legitimate poll calls time out even though flrig is healthy.
            self._flrig_online = False

        # Log connection state transitions (ignore transient drops during CAT)
        effective_online = now_online or self.flrig.cat_in_flight
        if effective_online != self._flrig_online_prev:
            ts = datetime.now().strftime("%H:%M:%S")
            event = "Connected" if effective_online else "Disconnected"
            self._flrig_log.append(f"{ts}  {event}")
            if len(self._flrig_log) > 50:
                self._flrig_log = self._flrig_log[-50:]
            self._flrig_online_prev = effective_online

        self._update_radio_display()

    def _update_qrz_indicator(self) -> None:
        pass  # QRZ status now shown in NetworkStatusModal only

    @work(exclusive=True, group="wsjtx-poll")
    async def _poll_wsjtx(self) -> None:
        now_online = self._wsjtx.is_online()
        self._wsjtx_online = now_online

        # Log connection state transitions
        if now_online != self._wsjtx_online_prev:
            ts = datetime.now().strftime("%H:%M:%S")
            event = "Connected" if now_online else "Disconnected"
            self._wsjtx_log.append(f"{ts}  {event}")
            if len(self._wsjtx_log) > 50:
                self._wsjtx_log = self._wsjtx_log[-50:]
            self._wsjtx_online_prev = now_online

        for qso_data in self._wsjtx.drain_qsos():
            await self._ingest_wsjtx_qso(qso_data)

    async def _ingest_wsjtx_qso(self, data: dict) -> None:
        """Log a QSO received from WSJT-X into the current session."""
        callsign = data.get("dx_call", "").strip().upper()
        if not callsign:
            return

        freq_hz = data.get("tx_freq_hz", 0)
        freq_khz = freq_hz / 1000.0
        band = freq_to_band(freq_khz)
        mode = data.get("mode", "FT8").upper() or "FT8"
        rst_sent = data.get("rst_sent", "-10") or "-10"
        rst_rcvd = data.get("rst_rcvd", "-10") or "-10"
        name = data.get("name", "")
        comments = data.get("comments", "")
        timestamp = data.get("datetime_off")

        contact_grid = data.get("dx_grid", "")
        distance_km: float | None = None
        state = ""

        # QRZ/HamDB lookup for name, state, grid, distance (best-effort)
        info = None
        if self._qrz.configured:
            try:
                info = await self._qrz.lookup(callsign)
            except Exception:
                info = None
        if info is None:
            try:
                info = await self._hamdb.lookup(callsign)
            except Exception:
                info = None

        if info is not None:
            name = info.name or name  # prefer lookup; fall back to WSJT-X name
            if info.grid and not contact_grid:
                contact_grid = info.grid
            state = info.state or ""

        # Distance from park to contact (prefer exact lat/lon, fall back to grid)
        if info is not None and info.lat is not None and info.lon is not None and self._park_latlon:
            from potatui.qrz import haversine_km
            distance_km = haversine_km(
                self._park_latlon[0], self._park_latlon[1], info.lat, info.lon
            )
        elif contact_grid and self._park_latlon:
            from potatui.qrz import grid_to_latlon, haversine_km
            try:
                clat, clon = grid_to_latlon(contact_grid)
                distance_km = haversine_km(
                    self._park_latlon[0], self._park_latlon[1], clat, clon
                )
            except Exception:
                pass

        qso = self.session.add_qso(
            callsign=callsign,
            rst_sent=rst_sent,
            rst_rcvd=rst_rcvd,
            freq_khz=freq_khz,
            band=band,
            mode=mode,
            name=name,
            state=state,
            notes=comments,
            operator=self.session.operator,
            contact_grid=contact_grid,
            distance_km=distance_km,
            timestamp_utc=timestamp,
        )

        if distance_km is not None:
            self._prop_profile.add_qso(band, distance_km)

        self._rebuild_table()

        for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
            try:
                append_qso_adif(
                    qso,
                    self.session.operator,
                    self.session.station_callsign,
                    park_ref,
                    log_path,
                    self.session.my_state,
                    self.session.rig,
                    self.session.antenna,
                    self.session.power_w,
                )
            except Exception as exc:
                self.notify(f"ADIF write error: {exc}", severity="error")

        self._save_session()
        self._update_qso_count()
        self.notify(f"WSJT-X: logged {callsign}  {freq_khz:.1f} kHz  {mode}")

    @on(events.Click, "#hdr-net")
    def on_net_indicator_click(self) -> None:
        snapshot = NetworkStatusSnapshot(
            internet_online=not self._offline,
            offline_manual=self._offline_manual,
            pota_online=not self._offline,
            qrz_status=self._qrz.status,
            qrz_errors=self._qrz.error_log[:5],
            qrz_full_log=self._qrz.error_log,
            hamdb_errors=self._hamdb.error_log[:5],
            hamdb_used=bool(self._hamdb._cache),
            flrig_url=self.flrig._url,
            flrig_online=self._flrig_online,
            flrig_freq_khz=self.freq_khz,
            flrig_band=self.band,
            flrig_mode=self.mode,
            flrig_state_log=self._flrig_log,
            flrig_detail_log=self.flrig.log,
            wsjtx_host=self.config.wsjtx_host,
            wsjtx_port=self.config.wsjtx_port,
            wsjtx_online=self._wsjtx_online,
            wsjtx_state_log=self._wsjtx_log,
            wsjtx_detail_log=list(self._wsjtx.log),
            noaa_ok=not (self._solar_data.fetch_error if self._solar_data else True),
            noaa_loaded=self._solar_data is not None,
        )
        self.app.push_screen(NetworkStatusModal(snapshot))

    @work(exclusive=True, group="net-check")
    async def _check_internet_connectivity(self) -> None:
        from potatui.park_db import check_internet
        online = await check_internet(self.config.pota_api_base)
        net_widget = self.query_one("#hdr-net", Static)
        if self._offline_manual:
            # Manual override — keep showing offline-manual indicator, don't change _offline
            return
        if online:
            net_widget.update("net")
            net_widget.set_classes("net-online")
            self._offline = False
        else:
            net_widget.update("net")
            net_widget.set_classes("net-offline")
            self._offline = True

    # -----------------------------------------------------------------------
    # Space weather
    # -----------------------------------------------------------------------

    @work(exclusive=True, group="space-weather")
    async def _poll_space_weather(self) -> None:
        if self._offline:
            return
        data = await fetch_space_weather()
        self._solar_data = data
        self._update_solar_indicator()
        self._check_solar_alerts(data)
        # Also fetch MUF for propagation scoring (cached, 15-min rate limit respected)
        if self._park_latlon is not None:
            try:
                muf = await fetch_muf(self._park_latlon[0], self._park_latlon[1])
                self._prop_profile.fof2_mhz = muf.fof2
                self._prop_profile.muf_mhz = muf.mufd
            except Exception:
                pass

    def _update_solar_indicator(self) -> None:
        try:
            widget = self.query_one("#hdr-solar", Static)
        except Exception:
            return
        data = self._solar_data
        if data is None or data.fetch_error or data.kp_current is None:
            # Don't overwrite a flashing widget if we already have storm data
            if self._solar_flash_timer is None:
                widget.update("K:?")
                widget.set_classes("solar-unknown")
            return
        kp = data.kp_current
        sev = kp_severity(kp)
        widget.update(f"Kp:{kp_traditional(kp)}")
        if data.active_alerts and not self._solar_alerts_acknowledged:
            self._start_solar_flash()
        else:
            self._stop_solar_flash()
            widget.set_classes(f"solar-{sev}")

    def _check_solar_alerts(self, data: SpaceWeatherData) -> None:
        current_keys = {a.alert_key for a in data.active_alerts}
        new_keys = current_keys - self._seen_alert_keys
        self._seen_alert_keys |= current_keys
        if not self._solar_initial_poll_done:
            self._solar_initial_poll_done = True
            return
        if new_keys:
            self._solar_alerts_acknowledged = False
        for alert in data.active_alerts:
            if alert.alert_key in new_keys:
                first_line = alert.message.splitlines()[0] if alert.message else "New alert"
                self.notify(first_line, title="Space Weather", severity="warning", timeout=10)

    def _start_solar_flash(self) -> None:
        if self._solar_flash_timer is not None:
            return
        self._solar_flash_timer = self.set_interval(0.5, self._solar_flash_toggle)

    def _stop_solar_flash(self) -> None:
        if self._solar_flash_timer is not None:
            self._solar_flash_timer.stop()
            self._solar_flash_timer = None
        # Reset to appropriate severity if we have data
        try:
            widget = self.query_one("#hdr-solar", Static)
            if self._solar_data and self._solar_data.kp_current is not None:
                sev = kp_severity(self._solar_data.kp_current)
                widget.set_classes(f"solar-{sev}")
            else:
                widget.set_classes("solar-unknown")
        except Exception:
            pass

    def _solar_flash_toggle(self) -> None:
        try:
            widget = self.query_one("#hdr-solar", Static)
        except Exception:
            return
        self._solar_flash_toggle_state = not self._solar_flash_toggle_state
        if self._solar_flash_toggle_state:
            widget.set_classes("solar-storm solar-flash-a")
        else:
            widget.set_classes("solar-storm solar-flash-b")

    @on(events.Click, "#hdr-solar")
    def on_solar_indicator_click(self) -> None:
        if self._solar_data is None:
            self.notify("Space weather data not yet loaded.")
            return
        self._solar_alerts_acknowledged = True
        self._stop_solar_flash()
        self.app.push_screen(SolarWeatherModal(self._solar_data, park_latlon=self._park_latlon, park_grid=self._park_grid))

    def on_unmount(self) -> None:
        self._stop_solar_flash()
        self._wsjtx.stop()

    def _add_qso_row(self, qso: QSO, display_num: int) -> None:
        table = self.query_one("#qso-table", DataTable)
        freq_str = f"{qso.freq_khz:.1f}"
        name = qso.name[:30] + "…" if len(qso.name) > 30 else qso.name
        notes = qso.notes[:20] + "…" if len(qso.notes) > 20 else qso.notes
        row = (
            str(display_num),
            qso.timestamp_utc.strftime("%H%M"),
            qso.callsign,
            qso.rst_sent,
            qso.rst_rcvd,
            freq_str,
            qso.mode,
            name,
            qso.state,
            qso.p2p_ref if qso.is_p2p else "",
            notes,
        )
        # Insert at top
        table.add_row(*row, key=str(qso.qso_id))

    def _rebuild_table(self) -> None:
        table = self.query_one("#qso-table", DataTable)
        table.clear()
        for i, qso in enumerate(reversed(self.session.qsos), 1):
            self._add_qso_row(qso, len(self.session.qsos) - i + 1)

    def _save_session(self) -> None:
        try:
            self.config.log_dir_path.mkdir(parents=True, exist_ok=True)
            self.session.save_json(str(self._json_path))
        except Exception as e:
            self.notify(f"Save error: {e}", severity="error")

    # ------------------------------------------------------------------
    # Logging a QSO
    # ------------------------------------------------------------------

    @on(Button.Pressed, "#btn-log")
    def on_log_button(self) -> None:
        self._log_qso()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Track table focus for context-sensitive footer; select RST signal digits on focus."""
        now_table = isinstance(event.widget, DataTable)
        if now_table != self._table_focused:
            self._table_focused = now_table
            self.refresh_bindings()

        if event.widget.id == "f-p2p":
            inp = event.widget
            assert isinstance(inp, Input)
            inp.cursor_position = len(inp.value)
            return

        if event.widget.id not in ("f-rst-sent", "f-rst-rcvd"):
            return
        assert isinstance(event.widget, Input)
        inp = event.widget
        val = inp.value
        if len(val) == 3:
            inp.selection = Selection(0, 2)
        elif len(val) > 1:
            inp.selection = Selection(1, len(val))

    def check_action(self, action: str, parameters: tuple) -> bool:
        """Show form bindings when entry form is active, table bindings when table is active."""
        in_table = self._table_focused
        if action in ("set_freq", "mode_picker", "goto_spots", "self_spot", "commander", "settings", "edit_last_qso", "end_session", "change_operator"):
            return not in_table
        if action in ("delete_qso", "qrz_lookup_selected", "qrz_backfill"):
            return in_table
        return True

    @on(Input.Submitted, "#f-callsign")
    @on(Input.Submitted, "#f-rst-sent")
    @on(Input.Submitted, "#f-rst-rcvd")
    @on(Input.Submitted, "#f-name")
    @on(Input.Submitted, "#f-state")
    @on(Input.Submitted, "#f-notes")
    def on_field_submitted(self) -> None:
        self._log_qso()

    @work(group="log-qso")
    async def _log_qso(self) -> None:
        raw_cs = self.query_one("#f-callsign", Input).value.strip().upper()
        callsigns = [cs.strip() for cs in raw_cs.split(",") if cs.strip()]
        if not callsigns:
            self.query_one("#f-callsign", Input).focus()
            return

        rst_sent = self.query_one("#f-rst-sent", Input).value.strip() or _rst_default(self.mode)
        rst_rcvd = self.query_one("#f-rst-rcvd", Input).value.strip() or _rst_default(self.mode)
        form_name = self.query_one("#f-name", Input).value.strip()
        form_state = self.query_one("#f-state", Input).value.strip()
        notes = self.query_one("#f-notes", Input).value.strip()

        # Freq: read from input field so manual edits are always used
        try:
            self.freq_khz = float(self.query_one("#f-freq", Input).value.strip())
            band = freq_to_band(self.freq_khz)
            if band != "?":
                self.band = band
        except ValueError:
            pass
        self._update_radio_display()

        # P2P — parse comma-separated refs; one QSO per callsign × per valid park ref
        from potatui.pota_api import is_valid_park_ref
        raw_p2p = self.query_one("#f-p2p", Input).value.strip().upper()
        p2p_refs = [r.strip() for r in raw_p2p.split(",") if is_valid_park_ref(r.strip())]

        multi = len(callsigns) > 1

        async def _resolve_name_state(callsign: str) -> tuple[str, str]:
            """Return (name, state) for a callsign, doing a QRZ lookup in multi mode."""
            if not multi or not self._qrz.configured:
                return form_name, form_state
            info = await self._qrz.lookup(callsign)
            # Ignore form values that were QRZ-auto-filled for a previous callsign;
            # only use them if the user manually typed them.
            user_name = "" if self._qrz_filled_name else form_name
            user_state = "" if self._qrz_filled_state else form_state
            name = user_name or (info.name if info else "") or ""
            state = user_state or (info.state if info else "") or ""
            return name, state

        def _contact_location(callsign: str) -> tuple[str, float | None]:
            """Return (grid, distance_km) from cached QRZ lookup, if available."""
            key = callsign.upper().split("/")[0]
            return self._qrz_contact_info.get(key, ("", None))

        new_qsos: list[QSO] = []
        if p2p_refs:
            for callsign in callsigns:
                name, state = await _resolve_name_state(callsign)
                grid, dist_km = _contact_location(callsign)
                for ref in p2p_refs:
                    new_qsos.append(self.session.add_qso(
                        callsign=callsign,
                        rst_sent=rst_sent,
                        rst_rcvd=rst_rcvd,
                        freq_khz=self.freq_khz,
                        band=self.band,
                        mode=self.mode,
                        name=name,
                        state=state,
                        notes=notes,
                        is_p2p=True,
                        p2p_ref=ref,
                        operator=self.session.operator,
                        contact_grid=grid,
                        distance_km=dist_km,
                    ))
        else:
            for callsign in callsigns:
                name, state = await _resolve_name_state(callsign)
                grid, dist_km = _contact_location(callsign)
                new_qsos.append(self.session.add_qso(
                    callsign=callsign,
                    rst_sent=rst_sent,
                    rst_rcvd=rst_rcvd,
                    freq_khz=self.freq_khz,
                    band=self.band,
                    mode=self.mode,
                    name=name,
                    state=state,
                    notes=notes,
                    is_p2p=False,
                    p2p_ref="",
                    operator=self.session.operator,
                    contact_grid=grid,
                    distance_km=dist_km,
                ))

        # Update propagation profile with new QSO distances
        for qso in new_qsos:
            if qso.distance_km is not None:
                self._prop_profile.add_qso(qso.band, qso.distance_km)

        # Rebuild table so newest QSO(s) appear at top
        self._rebuild_table()

        # Persist — append each new QSO to every park's ADIF file
        for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
            for qso in new_qsos:
                try:
                    append_qso_adif(qso, self.session.operator, self.session.station_callsign, park_ref, log_path, self.session.my_state, self.session.rig, self.session.antenna, self.session.power_w)
                except Exception as e:
                    self.notify(f"ADIF write error: {e}", severity="error")
        self._save_session()
        self._update_qso_count()
        self._reset_form()

    def _reset_form(self) -> None:
        """Clear all entry fields back to their default state."""
        self.query_one("#f-callsign", Input).value = ""
        self.query_one("#f-rst-sent", Input).value = _rst_default(self.mode)
        self.query_one("#f-rst-rcvd", Input).value = _rst_default(self.mode)
        self.query_one("#f-name", Input).value = ""
        self.query_one("#f-state", Input).value = ""
        self.query_one("#f-notes", Input).value = ""
        self.query_one("#f-p2p", Input).value = self.config.p2p_prefix
        self.query_one("#dup-warning", Static).update("")
        self._qrz_filled_name = False
        self._qrz_filled_state = False
        self._clear_p2p_info()
        self._clear_qrz_info()
        self.query_one("#f-callsign", Input).focus()

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @on(Input.Changed, "#f-callsign")
    def on_callsign_changed(self, event: Input.Changed) -> None:
        raw_cs = event.value.strip().upper()

        # Easter egg: WAWA triggers the hoagie modal
        if raw_cs == "WAWA":
            use_miles = self.config.distance_unit.lower() == "mi"
            self.app.push_screen(
                WawaModal(self.session.grid, use_miles, self._offline),
                callback=self._after_wawa,
            )
            return

        callsigns = [cs.strip() for cs in raw_cs.split(",") if cs.strip()]
        dup_widget = self.query_one("#dup-warning", Static)

        # Dup detection: only meaningful for single callsign
        if len(callsigns) == 1 and self.session.is_duplicate(callsigns[0], self.band):
            dup_widget.update("DUPE!")
        else:
            dup_widget.update("")

        # Remove bars for callsigns no longer in the field
        container = self.query_one("#qrz-info-container", Vertical)
        for cs in [cs for cs in list(self._qrz_bars) if cs not in callsigns]:
            self._qrz_bars.pop(cs).remove()

        # Add bars for new callsigns; trigger lookup for valid-looking ones
        for cs in callsigns:
            if cs not in self._qrz_bars:
                bar = Static("", classes="qrz-info-bar hidden")
                self._qrz_bars[cs] = bar
                container.mount(bar)
            if self._looks_like_callsign(cs) and "hidden" in self._qrz_bars[cs].classes:
                self._trigger_qrz_lookup(cs)

        # If no callsigns at all, clear auto-filled name/state
        if not callsigns:
            self.query_one("#f-name", Input).value = ""
            self.query_one("#f-state", Input).value = ""
            self._qrz_filled_name = False
            self._qrz_filled_state = False

    def _after_wawa(self, _result: object = None) -> None:
        """Clear callsign field after dismissing the Wawa modal."""
        self.query_one("#f-callsign", Input).value = ""
        self.query_one("#f-callsign", Input).focus()

    @staticmethod
    def _looks_like_callsign(cs: str) -> bool:
        """True when the string looks like a complete callsign worth querying."""
        if len(cs) < 3:
            return False
        return any(c.isdigit() for c in cs) and sum(c.isalpha() for c in cs) >= 2

    def format_dist_bearing(self, dist_km, brg) -> str:
        """Format distance and bearing into a human readable string"""
        from potatui.qrz import cardinal
        if dist_km is None or brg is None:
            return ""
        direction = cardinal(brg)
        use_mi = self.config.distance_unit.lower() == "mi"
        if use_mi:
            dist_str = f"{dist_km * 0.621371:,.0f} mi"
        else:
            dist_str = f"{dist_km:,.0f} km"
        if direction:
            dist_str = f"{direction} {dist_str}"
        return dist_str

    def _trigger_qrz_lookup(self, callsign: str) -> None:
        """Start a per-callsign QRZ lookup worker (exclusive within its group)."""
        self.run_worker(
            self._do_qrz_lookup(callsign),
            exclusive=True,
            group=f"qrz-{callsign}",
        )

    async def _do_qrz_lookup(self, callsign: str) -> None:
        # Debounce: wait for typing to pause before hitting QRZ
        await asyncio.sleep(1.0)

        # Stale-check: callsign must still have a bar
        if callsign not in self._qrz_bars:
            return
        bar = self._qrz_bars[callsign]

        if self._offline:
            bar.set_classes("qrz-info-bar hidden")
            return

        from potatui.qrz import (
            bearing_deg,
            distance_from_grid,
            grid_to_latlon,
            haversine_km,
        )

        bar.set_classes("qrz-info-bar pending")
        bar.update("  looking up…")

        source = "QRZ"
        info = None
        if self._qrz.configured:
            info = await self._qrz.lookup(callsign)
        if info is None:
            source = "HamDB"
            info = await self._hamdb.lookup(callsign)

        # Stale-check again after the HTTP round-trip
        if callsign not in self._qrz_bars or self._qrz_bars[callsign] is not bar:
            return

        if info is None:
            bar.set_classes("qrz-info-bar notfound")
            bar.update(f"  {callsign} — not found")
            self._update_qrz_indicator()
            return

        # Auto-fill name and state only in single-callsign mode
        if len(self._qrz_bars) == 1:
            if info.name:
                name_inp = self.query_one("#f-name", Input)
                if not name_inp.value.strip() or self._qrz_filled_name:
                    name_inp.value = info.name
                    self._qrz_filled_name = True

            p2p_val = self.query_one("#f-p2p", Input).value.strip().upper()
            state_inp = self.query_one("#f-state", Input)
            if (not state_inp.value.strip() or self._qrz_filled_state) and p2p_val in ("", self.config.p2p_prefix) and info.state:
                state_inp.value = info.state
                self._qrz_filled_state = True

        parts = [f"  {source}: {info.callsign}"]
        if info.name:
            parts.append(info.name)
        loc = info.location
        if loc:
            parts.append(loc)
        if info.grid:
            parts.append(f"Grid: {info.grid}")

        # Resolve callsign lat/lon
        clat: float | None = info.lat
        clon: float | None = info.lon
        if (clat is None or clon is None) and info.grid:
            try:
                clat, clon = grid_to_latlon(info.grid)
            except Exception:
                pass

        # Distance and direction from park
        dist_km: float | None = None
        brg: float | None = None
        if self._park_latlon is not None and clat is not None and clon is not None:
            plat, plon = self._park_latlon
            dist_km = haversine_km(plat, plon, clat, clon)
            brg = bearing_deg(plat, plon, clat, clon)
        else:
            dist_km = distance_from_grid(self.session.grid, info)
            if dist_km is not None and self.session.grid:
                try:
                    plat, plon = grid_to_latlon(self.session.grid)
                    if clat is not None and clon is not None:
                        brg = bearing_deg(plat, plon, clat, clon)
                except Exception:
                    pass

        if dist_km is not None:
            dist_str = self.format_dist_bearing(dist_km, brg)
            parts.append(dist_str)

        # Cache grid and distance for use at log time
        self._qrz_contact_info[callsign] = (info.grid or "", dist_km)

        bar.set_classes("qrz-info-bar")
        bar.update("  ·  ".join(parts))
        self._update_qrz_indicator()

    def _clear_qrz_info(self) -> None:
        for bar in list(self._qrz_bars.values()):
            bar.remove()
        self._qrz_bars.clear()
        self._qrz_contact_info.clear()

    @on(Input.Changed, "#f-freq")
    def on_freq_changed(self, event: Input.Changed) -> None:
        """Live-update band label as user types a frequency."""
        try:
            khz = float(event.value.strip())
            self.freq_khz = khz
            band = freq_to_band(khz)
            if band != "?":
                self.band = band
            self._update_radio_display()
        except ValueError:
            pass  # incomplete input — ignore

    @on(Input.Submitted, "#f-freq")
    def on_freq_submitted(self) -> None:
        """Log the QSO when Enter is pressed in the frequency field."""
        self._log_qso()

    @on(Input.Changed, "#f-p2p")
    def on_p2p_changed(self, event: Input.Changed) -> None:
        # Auto-fill country prefix after a comma (e.g. "US-1234," → "US-1234,US-")
        # Only trigger when the user typed a comma (value grew), not when deleting back to one.
        if event.value.endswith(",") and len(event.value) > len(self._p2p_last_value):
            segments = event.value[:-1].split(",")
            last_ref = segments[-1].strip().upper() if segments else ""
            if last_ref and "-" in last_ref:
                prefix = last_ref.split("-")[0] + "-"
                inp = self.query_one("#f-p2p", Input)
                self._p2p_last_value = event.value + prefix
                inp.value = event.value + prefix
                inp.cursor_position = len(inp.value)
                return

        self._p2p_last_value = event.value
        raw = event.value.strip().upper()
        if not raw or raw == self.config.p2p_prefix.upper():
            self._clear_p2p_info()
            return
        from potatui.pota_api import is_valid_park_ref
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            self._clear_p2p_info()
            return
        valid_refs = [p for p in parts if is_valid_park_ref(p)]
        if valid_refs:
            self._lookup_p2p_park(valid_refs, raw)
        else:
            self._set_p2p_info(f"  P2P: {parts[-1]} (incomplete…)", warn=True)

    @on(Input.Submitted, "#f-p2p")
    def on_p2p_submitted(self) -> None:
        self._log_qso()

    @work(exclusive=True, group="p2p-lookup")
    async def _lookup_p2p_park(self, refs: list[str], raw: str) -> None:
        from potatui.qrz import bearing_deg, haversine_km

        if self._offline:
            from potatui.park_db import park_db
            results = [(ref, park_db.lookup(ref) if park_db.loaded else None) for ref in refs]
            suffix = " (local DB only)"
        else:
            from potatui.pota_api import lookup_park
            self._set_p2p_info(f"  P2P: {', '.join(refs)} — looking up…", warn=False)
            results = [(ref, await lookup_park(ref, self.config.pota_api_base)) for ref in refs]
            suffix = ""

        # Discard if the field changed while we were looking up
        current = self.query_one("#f-p2p", Input).value.strip().upper()
        if current != raw:
            return

        segments = []
        first_state: str | None = None
        has_error = False
        for ref, info in results:
            if info:
                segments.append(info.reference)
                segments.append(info.name)
                segments.append(info.location)
                segments.append(f"Grid: {info.grid}")

                if self._park_latlon is not None and info.lat is not None and info.lon is not None:
                    plat, plon = self._park_latlon
                    dist_km = haversine_km(plat, plon, info.lat, info.lon)
                    brg = bearing_deg(plat, plon, info.lat, info.lon)
                    dist_str = self.format_dist_bearing(dist_km, brg)
                    if dist_str:
                        segments.append(dist_str)

                if first_state is None and info.state:
                    first_state = info.state
            else:
                segments.append(f"{ref} — not found")
                has_error = True

        # Flag any parts that are still incomplete (in the field but not yet valid)
        all_parts = [p.strip() for p in raw.split(",") if p.strip()]
        for part in all_parts:
            if part not in refs:
                segments.append(f"{part} (incomplete)")
                has_error = True

        info_text = "  " + "  ·  ".join(segments)
        if suffix:
            info_text += suffix
        self._set_p2p_info(info_text, warn=has_error)
        if first_state:
            self.query_one("#f-state", Input).value = first_state

    def _set_p2p_info(self, text: str, warn: bool) -> None:
        bar = self.query_one("#p2p-info-bar", Static)
        bar.update(text)
        bar.remove_class("hidden")
        if warn:
            bar.add_class("warn")
        else:
            bar.remove_class("warn")

    def _clear_p2p_info(self) -> None:
        bar = self.query_one("#p2p-info-bar", Static)
        bar.update("")
        bar.add_class("hidden")

    # ------------------------------------------------------------------
    # Tab wrap within entry form
    # ------------------------------------------------------------------

    _FORM_FIELDS = [
        "#f-callsign", "#f-rst-sent", "#f-rst-rcvd", "#f-p2p", "#f-freq", "#btn-log",
        "#f-name", "#f-state", "#f-notes",
    ]

    def on_key(self, event: events.Key) -> None:
        # ── Command slot shortcuts ──────────────────────────────────────
        key = event.key.lower()
        for i, slot in enumerate(self._cmd_config.cat_slots, 1):
            if slot.shortcut and slot.shortcut.lower() == key and slot.command:
                event.stop()
                self._fire_cat_slot(slot.label or f"CAT {i}", slot.command)
                return
        for i, slot in enumerate(self._cmd_config.console_slots, 1):
            if slot.shortcut and slot.shortcut.lower() == key and slot.command:
                event.stop()
                self._fire_console_slot(slot.label or f"Console {i}", slot.command)
                return

        # ── Tab-wrap within the entry form ─────────────────────────────
        focused = self.focused
        if focused is None:
            return
        focused_id = f"#{focused.id}" if focused.id else None
        if focused_id not in self._FORM_FIELDS:
            return
        if event.key == "tab" and focused_id == "#f-notes":
            event.prevent_default()
            event.stop()
            self.query_one("#f-callsign", Input).focus()
        elif event.key == "shift+tab" and focused_id == "#f-callsign":
            event.prevent_default()
            event.stop()
            self.query_one("#f-notes", Input).focus()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_about(self) -> None:
        self.app.push_screen(AboutModal())

    def action_set_freq(self) -> None:
        def on_result(freq: float | None) -> None:
            if freq is None:
                return
            self.freq_khz = freq
            band = freq_to_band(freq)
            if band != "?":
                self.band = band
            self._update_radio_display()
            # Update the freq entry field
            freq_inp = self.query_one("#f-freq", Input)
            freq_inp.value = f"{freq:.1f}"
            # Tune flrig if connected — set mode before frequency so any
            # VFO drift caused by a USB↔LSB switch is corrected by the
            # subsequent set_frequency call (avoids ~1.4 kHz offset on
            # cross-band changes).
            if self._flrig_online:
                if self.mode == "SSB":
                    self.flrig.set_mode("SSB", freq)
                self.flrig.set_frequency(freq * 1000)
            self.query_one("#f-callsign", Input).focus()

        self.app.push_screen(SetFreqModal(self.freq_khz), on_result)

    def action_change_operator(self) -> None:
        def on_result(callsign: str | None) -> None:
            if not callsign:
                return
            self.session.operator = callsign
            self._update_header()
            self._save_session()
            self.notify(f"Operator: {callsign}")
            self.query_one("#f-callsign", Input).focus()

        self.app.push_screen(ChangeOperatorModal(self.session.operator), on_result)

    def action_mode_picker(self) -> None:
        def on_result(mode: str | None) -> None:
            if mode:
                self.mode = mode
                self._update_radio_display()
                # Update RST defaults
                self.query_one("#f-rst-sent", Input).value = _rst_default(mode)
                self.query_one("#f-rst-rcvd", Input).value = _rst_default(mode)
                # Tell the rig to change mode
                if self._flrig_online:
                    self.flrig.set_mode(mode, self.freq_khz)

        self.app.push_screen(ModePickerModal(self.mode), on_result)

    def _qso_id_from_table_cursor(self) -> int | None:
        """Return the QSO id of the currently highlighted table row, or None."""
        table = self.query_one("#qso-table", DataTable)
        try:
            row_key = list(table.rows)[table.cursor_row]
            assert row_key.value is not None
            return int(row_key.value)
        except Exception:
            return None

    def _open_edit_for_qso_id(self, qso_id: int) -> None:
        qso = next((q for q in self.session.qsos if q.qso_id == qso_id), None)
        if qso is None:
            return

        def on_result(data: dict | None) -> None:
            if data:
                self.session.update_qso(qso_id, **data)
                self._rebuild_table()
                self._save_session()
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
                        write_adif(self.session, log_path, park_ref)
                except Exception as e:
                    self.notify(f"ADIF rewrite error: {e}", severity="error")

        self.app.push_screen(EditQSOModal(qso, self._qrz), on_result)

    def action_edit_last_qso(self) -> None:
        """F4 — toggle between QSO table and entry form."""
        table = self.query_one("#qso-table", DataTable)
        if table.has_focus:
            self.query_one("#f-callsign", Input).focus()
        else:
            if not self.session.qsos:
                self.notify("No QSOs logged yet", severity="warning")
                return
            table.focus()

    @on(DataTable.RowSelected)
    def on_qso_row_selected(self, event: DataTable.RowSelected) -> None:
        qso_id = self._qso_id_from_table_cursor()
        if qso_id is not None:
            self._open_edit_for_qso_id(qso_id)

    def action_edit_selected_qso(self) -> None:
        """Enter (table mode) — edit the selected QSO."""
        qso_id = self._qso_id_from_table_cursor()
        if qso_id is not None:
            self._open_edit_for_qso_id(qso_id)

    @work(exclusive=True, group="qrz-lookup-selected")
    async def action_qrz_lookup_selected(self) -> None:
        """Ctrl+L (table mode) — callsign lookup for the selected QSO (QRZ, or HamDB fallback)."""
        qso_id = self._qso_id_from_table_cursor()
        if qso_id is None:
            return
        qso = next((q for q in self.session.qsos if q.qso_id == qso_id), None)
        if qso is None:
            return
        self.notify(f"Looking up {qso.callsign}…")
        source = "QRZ"
        info = None
        if self._qrz.configured:
            info = await self._qrz.lookup(qso.callsign)
        if info is None:
            source = "HamDB"
            info = await self._hamdb.lookup(qso.callsign)
        if info:
            state = qso.state if qso.is_p2p else (info.state or qso.state)
            self.session.update_qso(qso.qso_id, name=info.name, state=state)
            self._rebuild_table()
            self._save_session()
            try:
                for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
                    write_adif(self.session, log_path, park_ref)
            except Exception as e:
                self.notify(f"ADIF rewrite error: {e}", severity="error")
                return
            self._update_qrz_indicator()
            self.notify(f"{source}: {qso.callsign} — {info.name or 'updated'}")
        else:
            self.notify(f"{qso.callsign} — not found", severity="warning")

    def action_clear_form(self) -> None:
        """Escape — return focus to callsign (table mode) or clear entry form (form mode)."""
        if self._table_focused:
            self.query_one("#f-callsign", Input).focus()
        else:
            self._reset_form()

    def action_goto_spots(self) -> None:
        from potatui.screens.spots import SpotsScreen

        self.app.push_screen(
            SpotsScreen(
                config=self.config,
                flrig=self.flrig,
                park_latlon=self._park_latlon,
                session=self.session,
                offline=self._offline,
                prop_profile=self._prop_profile,
            )
        )

    def action_self_spot(self) -> None:
        self.app.push_screen(
            SelfSpotModal(
                callsign=self.session.operator,
                park_ref=self.session.active_park_ref,
                freq_khz=self.freq_khz,
                mode=self.mode,
                pota_api_base=self.config.pota_api_base,
                offline=self._offline,
            )
        )

    def action_toggle_offline(self) -> None:
        from potatui.config import save_config
        self._offline = not self._offline
        self._offline_manual = self._offline
        self.config.offline_mode = self._offline
        save_config(self.config)
        net_widget = self.query_one("#hdr-net", Static)
        if self._offline:
            net_widget.update("OFFL")
            net_widget.set_classes("net-offline-manual")
            self.notify("Offline mode ON — QRZ, spots, and self-spotting disabled", severity="warning")
        else:
            net_widget.update("net")
            net_widget.set_classes("net-unknown")
            self.notify("Offline mode OFF — network features re-enabled")
            self._check_internet_connectivity()
            self._poll_space_weather()

    @work(thread=True)
    def _fire_cat_slot(self, label: str, cmd: str) -> None:
        ok = self.flrig.send_cat_string(cmd)
        if ok:
            self.app.call_from_thread(self.notify, f"{label}  ({cmd})", severity="information")
        else:
            self.app.call_from_thread(self.notify, "flrig not connected", severity="error")

    @work(thread=True)
    def _fire_console_slot(self, label: str, cmd: str) -> None:
        import subprocess
        try:
            result = subprocess.run(  # noqa: S602
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self.app.call_from_thread(
                    self.notify, f"{label} OK", severity="information"
                )
            else:
                err = (result.stderr or "").strip() or f"exit {result.returncode}"
                self.app.call_from_thread(
                    self.notify, f"{label} failed: {err[:30]}", severity="error"
                )
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(self.notify, f"{label} timed out", severity="error")
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error: {e}", severity="error")

    def action_commander(self) -> None:
        from potatui.screens.commander import CommanderModal
        self.app.push_screen(CommanderModal(self._cmd_config, self.flrig))

    def action_settings(self) -> None:
        from potatui.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen(self.config))

    def action_end_session(self) -> None:
        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
                        write_adif(self.session, log_path, park_ref)
                    self._save_session()
                    if len(self._log_paths) == 1:
                        self.notify(f"Session saved to {self._log_paths[0]}", severity="information")
                    else:
                        self.notify(f"Session saved — {len(self._log_paths)} ADIF files written", severity="information")
                except Exception as e:
                    self.notify(f"Export error: {e}", severity="error")
                self.app.exit()

        self.app.push_screen(
            SessionSummaryModal(self.session, self._log_paths),
            on_confirm,
        )

    def action_delete_qso(self) -> None:
        table = self.query_one("#qso-table", DataTable)
        cursor_index = table.cursor_row
        if cursor_index is None:
            return
        # Row keys are set to str(qso.qso_id) — retrieve by cursor index
        try:
            row_key = list(table.rows)[cursor_index]
            assert row_key.value is not None
            qso_id = int(row_key.value)
        except Exception:
            return

        def on_confirm(confirmed: bool | None) -> None:
            if confirmed:
                self.session.remove_qso(qso_id)
                self._rebuild_table()
                self._update_qso_count()
                self._save_session()
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
                        write_adif(self.session, log_path, park_ref)
                except Exception as e:
                    self.notify(f"ADIF rewrite error: {e}", severity="error")

        qso = next((q for q in self.session.qsos if q.qso_id == qso_id), None)
        label = qso.callsign if qso else "selected QSO"
        self.app.push_screen(ConfirmModal(f"Delete QSO with {label}?"), on_confirm)

    @work(exclusive=True, group="qrz-backfill")
    async def action_qrz_backfill(self) -> None:
        """Ctrl+B — look up callsign info for all QSOs with empty name (QRZ, or HamDB fallback)."""
        targets = [q for q in self.session.qsos if not q.name]
        if not targets:
            self.notify("All contacts already have names")
            return
        self.notify(f"Looking up {len(targets)} contact(s)…")

        # Run up to 5 lookups concurrently. QRZClient serialises its own login
        # internally, so concurrent callers are safe.
        sem = asyncio.Semaphore(5)

        async def _one(qso):
            async with sem:
                info = None
                if self._qrz.configured:
                    info = await self._qrz.lookup(qso.callsign)
                if info is None:
                    info = await self._hamdb.lookup(qso.callsign)
                return qso, info

        results = await asyncio.gather(*[_one(q) for q in targets])

        updated = 0
        for qso, info in results:
            if info:
                state = qso.state if qso.is_p2p else (info.state or qso.state)
                self.session.update_qso(qso.qso_id, name=info.name, state=state)
                updated += 1
        self._rebuild_table()
        self._save_session()
        try:
            for park_ref, log_path in zip(self.session.park_refs, self._log_paths, strict=False):
                write_adif(self.session, log_path, park_ref)
        except Exception as e:
            self.notify(f"ADIF rewrite error: {e}", severity="error")
            return
        self._update_qrz_indicator()
        self.notify(f"Updated {updated} of {len(targets)} contact(s)")

    # ------------------------------------------------------------------
    # Called from SpotsScreen when user QSYs to a spot
    # ------------------------------------------------------------------

    def prefill_callsign(self, callsign: str) -> None:
        inp = self.query_one("#f-callsign", Input)
        inp.value = callsign.upper()
        inp.focus()

    def update_freq_mode(self, freq_khz: float, mode: str) -> None:
        self.freq_khz = freq_khz
        band = freq_to_band(freq_khz)
        if band != "?":
            self.band = band
        self.mode = mode
        try:
            self.query_one("#f-freq", Input).value = f"{freq_khz:.1f}"
            self.query_one("#f-rst-sent", Input).value = _rst_default(mode)
            self.query_one("#f-rst-rcvd", Input).value = _rst_default(mode)
            self._update_radio_display()
        except Exception:
            pass

    def prefill_p2p(self, park_ref: str) -> None:
        """Pre-fill the P2P field with a park reference (from spot QSY)."""
        try:
            inp = self.query_one("#f-p2p", Input)
            inp.value = park_ref.upper()
        except Exception:
            pass
        self._update_radio_display()
