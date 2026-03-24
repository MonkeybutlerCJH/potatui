# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Modal dialogs used by the logger screen (and potentially others)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    ListItem,
    ListView,
    Rule,
    Select,
    Static,
)

from potatui.adif import freq_to_band
from potatui.park_db import park_db
from potatui.session import QSO, Session
from potatui.space_weather import SpaceWeatherData, fetch_muf

MODES = ["SSB", "CW", "AM", "FM"]

# Full default RST values. On focus, the signal digits (after the first char)
# are selected so the user can type to replace just that part.
DEFAULT_RST: dict[str, str] = {
    "SSB": "59",
    "AM": "59",
    "FM": "59",
    "CW": "599",
}


def _rst_default(mode: str) -> str:
    return DEFAULT_RST.get(mode.upper(), "59")


# ---------------------------------------------------------------------------
# Mode picker modal
# ---------------------------------------------------------------------------

class ModePickerModal(ModalScreen[str | None]):
    CSS = """
    ModePickerModal {
        align: center middle;
    }
    #picker-box {
        width: 16;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 0 1;
    }
    #mode-list {
        width: 14;
        height: auto;
        background: $surface;
    }
    #mode-list > ListItem {
        padding: 0 2;
    }
    #mode-list > ListItem.--highlight {
        background: $primary;
        color: $text;
    }
    """

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current

    def compose(self) -> ComposeResult:
        with Container(id="picker-box"):
            items = [ListItem(Static(m), id=f"mode-{m}") for m in MODES]
            yield ListView(*items, id="mode-list")

    def on_mount(self) -> None:
        lv = self.query_one("#mode-list", ListView)
        try:
            idx = MODES.index(self.current)
            lv.index = idx
        except ValueError:
            pass
        lv.focus()

    @on(ListView.Selected, "#mode-list")
    def on_mode_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        mode = item_id.removeprefix("mode-")
        self.dismiss(mode if mode in MODES else None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Edit QSO modal
# ---------------------------------------------------------------------------

class EditQSOModal(ModalScreen[dict | None]):
    CSS = """
    EditQSOModal {
        align: center middle;
    }
    #edit-box {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #edit-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    .edit-row {
        height: auto;
        margin-bottom: 1;
    }
    .edit-label {
        width: 12;
        padding-top: 1;
        color: $text-muted;
    }
    .edit-input {
        width: 1fr;
    }
    #e-mode {
        width: 1fr;
    }
    #edit-btn-row {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    """

    def __init__(self, qso: QSO, qrz=None) -> None:
        super().__init__()
        self.qso = qso
        self.qrz = qrz

    def compose(self) -> ComposeResult:
        with Container(id="edit-box"):
            yield Static(f"Edit QSO #{self.qso.qso_id}", id="edit-title")
            with Horizontal(classes="edit-row"):
                yield Label("Callsign:", classes="edit-label")
                yield Input(value=self.qso.callsign, id="e-callsign", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("RST Sent:", classes="edit-label")
                yield Input(value=self.qso.rst_sent, id="e-rst-sent", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("RST Rcvd:", classes="edit-label")
                yield Input(value=self.qso.rst_rcvd, id="e-rst-rcvd", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("Freq (kHz):", classes="edit-label")
                yield Input(value=f"{self.qso.freq_khz:.1f}", id="e-freq", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("Mode:", classes="edit-label")
                yield Select(
                    [(m, m) for m in MODES],
                    value=self.qso.mode if self.qso.mode in MODES else Select.BLANK,
                    id="e-mode",
                )
            with Horizontal(classes="edit-row"):
                yield Label("Name:", classes="edit-label")
                yield Input(value=self.qso.name, id="e-name", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("State:", classes="edit-label")
                yield Input(value=self.qso.state, id="e-state", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("P2P Park:", classes="edit-label")
                yield Input(value=self.qso.p2p_ref, id="e-p2p", classes="edit-input")
            with Horizontal(classes="edit-row"):
                yield Label("Notes:", classes="edit-label")
                yield Input(value=self.qso.notes, id="e-notes", classes="edit-input")
            with Horizontal(id="edit-btn-row"):
                if self.qrz and self.qrz.configured:
                    yield Button("QRZ ↗", id="e-qrz")
                yield Button("Save", variant="primary", id="e-save")
                yield Button("Cancel", id="e-cancel")

    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        self.on_save()

    @on(Button.Pressed, "#e-save")
    def on_save(self) -> None:
        try:
            freq_khz = float(self.query_one("#e-freq", Input).value.strip())
        except ValueError:
            freq_khz = self.qso.freq_khz
        band = freq_to_band(freq_khz)
        p2p_ref = self.query_one("#e-p2p", Input).value.strip().upper()
        self.dismiss({
            "callsign": self.query_one("#e-callsign", Input).value.strip().upper(),
            "rst_sent": self.query_one("#e-rst-sent", Input).value.strip(),
            "rst_rcvd": self.query_one("#e-rst-rcvd", Input).value.strip(),
            "freq_khz": freq_khz,
            "band": band if band != "?" else self.qso.band,
            "mode": self.query_one("#e-mode", Select).value or self.qso.mode,
            "name": self.query_one("#e-name", Input).value.strip(),
            "state": self.query_one("#e-state", Input).value.strip(),
            "p2p_ref": p2p_ref,
            "is_p2p": bool(p2p_ref),
            "notes": self.query_one("#e-notes", Input).value.strip(),
        })

    @on(Button.Pressed, "#e-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#e-qrz")
    def on_qrz(self) -> None:
        self._do_qrz_lookup()

    @work(exclusive=True, group="edit-qrz-lookup")
    async def _do_qrz_lookup(self) -> None:
        btn = self.query_one("#e-qrz", Button)
        callsign = self.query_one("#e-callsign", Input).value.strip().upper()
        if not callsign:
            return
        btn.disabled = True
        btn.label = "…"
        info = await self.qrz.lookup(callsign)
        if info:
            self.query_one("#e-name", Input).value = info.name
            self.query_one("#e-state", Input).value = info.state or ""
            btn.label = "QRZ ✓"
        else:
            self.notify(f"QRZ: {callsign} not found", severity="warning")
            btn.label = "QRZ ↗"
        btn.disabled = False

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Session summary modal (shown on F10 before ending)
# ---------------------------------------------------------------------------

class SessionSummaryModal(ModalScreen[bool]):
    CSS = """
    SessionSummaryModal { align: center middle; }
    #summary-box {
        width: 62;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #summary-title {
        text-align: center;
        text-style: bold;
        color: $primary;
    }
    #summary-subtitle {
        text-align: center;
        color: $text-muted;
    }
    .summary-rule {
        color: $primary-darken-2;
        margin: 1 0;
    }
    #summary-activation {
        text-style: bold;
        margin-bottom: 0;
    }
    .stat-grid {
        height: auto;
        margin: 0;
    }
    .stat-col {
        width: 1fr;
        height: auto;
    }
    .stat-label {
        color: $text-muted;
        width: auto;
    }
    .stat-value {
        text-style: bold;
        width: auto;
    }
    .breakdown-col {
        width: 1fr;
        height: auto;
    }
    .breakdown-header {
        color: $text-muted;
        text-style: bold;
        width: auto;
    }
    .breakdown-row {
        height: auto;
    }
    .breakdown-band {
        width: 6;
        color: $text-muted;
    }
    .breakdown-count {
        text-style: bold;
        width: auto;
    }
    .summary-files {
        color: $text-muted;
        text-style: italic;
    }
    #summary-btns {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, session: Session, log_paths: list) -> None:
        super().__init__()
        self._session = session
        self._log_paths = log_paths

    def compose(self) -> ComposeResult:
        from collections import Counter

        from potatui.adif import BAND_RANGES

        session = self._session
        now = datetime.utcnow()
        total = len(session.qsos)
        today = now.date()
        today_count = sum(1 for q in session.qsos if q.timestamp_utc.date() == today)
        elapsed = now - session.start_time
        elapsed_secs = elapsed.total_seconds()
        h, rem = divmod(int(elapsed_secs), 3600)
        m, s = divmod(rem, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}"
        unique_calls = len({q.callsign for q in session.qsos})
        p2p_count = sum(1 for q in session.qsos if q.is_p2p)
        elapsed_hours = elapsed_secs / 3600
        if elapsed_hours < 1.0:
            rate = int(total / elapsed_hours) if elapsed_hours > 0 and total > 0 else 0
        else:
            cutoff = now - timedelta(hours=1)
            rate = sum(1 for q in session.qsos if q.timestamp_utc >= cutoff)

        band_order = {name: i for i, (_, _, name) in enumerate(BAND_RANGES)}
        band_counts = Counter(q.band for q in session.qsos)
        mode_counts = Counter(q.mode for q in session.qsos)

        rule = "─" * 54

        with Container(id="summary-box"):
            yield Static("Session Summary", id="summary-title")
            parks_str = "  ·  ".join(session.park_refs)
            date_str = session.start_time.strftime("%d %b %Y")
            yield Static(f"{session.station_callsign}  ·  {parks_str}  ·  {date_str}", id="summary-subtitle")

            yield Static(rule, classes="summary-rule")

            if today_count >= 10:
                yield Static(f"[green]●  Activated  —  {today_count} QSOs today[/green]", id="summary-activation")
            else:
                yield Static(f"[red]●  Not activated  —  {today_count} / 10 QSOs today[/red]", id="summary-activation")
            if total != today_count:
                yield Static(f"[dim]({total} QSOs total across all UTC days)[/dim]", classes="stat-label")

            yield Static(rule, classes="summary-rule")

            # Stats grid
            with Horizontal(classes="stat-grid"):
                with Vertical(classes="stat-col"):
                    yield Static("Unique calls", classes="stat-label")
                    yield Static(str(unique_calls), classes="stat-value")
                with Vertical(classes="stat-col"):
                    yield Static("Duration", classes="stat-label")
                    yield Static(duration_str, classes="stat-value")
                with Vertical(classes="stat-col"):
                    yield Static("Rate", classes="stat-label")
                    yield Static(f"{rate}/hr", classes="stat-value")
                if p2p_count:
                    with Vertical(classes="stat-col"):
                        yield Static("P2P", classes="stat-label")
                        yield Static(str(p2p_count), classes="stat-value")

            # Band / mode breakdown
            if band_counts or mode_counts:
                yield Static(rule, classes="summary-rule")
                with Horizontal(classes="stat-grid"):
                    if band_counts:
                        with Vertical(classes="breakdown-col"):
                            yield Static("Band", classes="breakdown-header")
                            for band, count in sorted(band_counts.items(), key=lambda x: band_order.get(x[0], 99)):
                                with Horizontal(classes="breakdown-row"):
                                    yield Static(band, classes="breakdown-band")
                                    yield Static(str(count), classes="breakdown-count")
                    if mode_counts:
                        with Vertical(classes="breakdown-col"):
                            yield Static("Mode", classes="breakdown-header")
                            for mode, count in sorted(mode_counts.items(), key=lambda x: -x[1]):
                                with Horizontal(classes="breakdown-row"):
                                    yield Static(mode, classes="breakdown-band")
                                    yield Static(str(count), classes="breakdown-count")

            yield Static(rule, classes="summary-rule")
            for i, path in enumerate(self._log_paths):
                yield Static(str(path), id=f"summary-files-{i}", classes="summary-files")

            with Horizontal(id="summary-btns"):
                yield Button("Cancel", id="summary-cancel")
                yield Button("End Session", variant="error", id="summary-confirm")

    def on_mount(self) -> None:
        self.query_one("#summary-confirm", Button).focus()

    @on(Button.Pressed, "#summary-confirm")
    def on_confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#summary-cancel")
    def on_cancel(self) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


# ---------------------------------------------------------------------------
# Confirm delete modal
# ---------------------------------------------------------------------------

class ConfirmModal(ModalScreen[bool]):
    CSS = """
    ConfirmModal { align: center middle; }
    #confirm-box {
        width: 50;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    #confirm-msg { margin-bottom: 1; }
    #confirm-btns { align: right middle; height: auto; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Container(id="confirm-box"):
            yield Static(self.message, id="confirm-msg")
            with Horizontal(id="confirm-btns"):
                yield Button("Yes", variant="error", id="yes")
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
# QRZ connection log modal
# ---------------------------------------------------------------------------

class QrzLogModal(ModalScreen[None]):
    CSS = """
    QrzLogModal { align: center middle; }
    #qrz-log-box {
        width: 72;
        height: 20;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #qrz-log-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #qrz-log-container {
        height: 1fr;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
    }
    #qrz-log-label {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 0;
    }
    #qrz-log-scroll { height: 1fr; }
    #qrz-log-empty { color: $text-muted; text-style: italic; }
    #qrz-log-close { height: auto; align: right middle; margin-top: 1; }
    """

    def __init__(self, error_log: list[str]) -> None:
        super().__init__()
        self._log = error_log

    def compose(self) -> ComposeResult:
        with Container(id="qrz-log-box"):
            yield Static("QRZ Connection Log", id="qrz-log-title")
            with Vertical(id="qrz-log-container"):
                yield Static("Error Log", id="qrz-log-label")
                with ScrollableContainer(id="qrz-log-scroll"):
                    if self._log:
                        for entry in self._log:
                            yield Static(entry)
                    else:
                        yield Static("No errors logged — QRZ is working fine.", id="qrz-log-empty")
            with Horizontal(id="qrz-log-close"):
                yield Button("Close", variant="primary", id="qrz-log-btn-close")

    @on(Button.Pressed, "#qrz-log-btn-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# (VoiceKeyerModal removed — replaced by CommanderModal in screens/commander.py)


# ---------------------------------------------------------------------------
# flrig status modal
# ---------------------------------------------------------------------------

class FlrigStatusModal(ModalScreen[None]):
    CSS = """
    FlrigStatusModal { align: center middle; }
    #flrig-status-box {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #flrig-status-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #flrig-status-info {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
    }
    #flrig-status-info Static { width: auto; height: 1; }
    #flrig-status-log-container {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
        margin-top: 1;
    }
    #flrig-status-log-label {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 0;
    }
    #flrig-status-scroll { height: 10; }
    #flrig-status-close { height: auto; align: right middle; margin-top: 1; }
    """

    def __init__(
        self,
        url: str,
        online: bool,
        freq_khz: float,
        band: str,
        mode: str,
        state_log: list[str],
        detail_log: list[str],
    ) -> None:
        super().__init__()
        self._url = url
        self._online = online
        self._freq_khz = freq_khz
        self._band = band
        self._mode = mode
        self._state_log = state_log    # connect/disconnect transitions
        self._detail_log = detail_log  # raw XML-RPC call results

    def compose(self) -> ComposeResult:
        status = "[green]Online[/green]" if self._online else "[red]Offline[/red]"
        combined = sorted(
            self._state_log + self._detail_log,
            reverse=True,
        )
        with Container(id="flrig-status-box"):
            yield Static("flrig Connection", id="flrig-status-title")
            with Vertical(id="flrig-status-info"):
                yield Static(f"URL:    {self._url}")
                yield Static(f"Status: {status}")
                if self._online:
                    yield Static(f"Freq:   {self._freq_khz:.1f} kHz  {self._band}  {self._mode}")
            with Vertical(id="flrig-status-log-container"):
                yield Static("Event Log", id="flrig-status-log-label")
                with ScrollableContainer(id="flrig-status-scroll"):
                    if combined:
                        for entry in combined:
                            yield Static(entry)
                    else:
                        yield Static("No events logged yet.", classes="muted")
            with Horizontal(id="flrig-status-close"):
                yield Button("Close", variant="primary", id="flrig-status-btn-close")

    @on(Button.Pressed, "#flrig-status-btn-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Network status modal
# ---------------------------------------------------------------------------


@dataclass
class NetworkStatusSnapshot:
    """Point-in-time snapshot of all network/service states for the modal."""

    internet_online: bool
    offline_manual: bool

    pota_online: bool

    qrz_status: str  # "unconfigured" | "pending" | "ok" | "error"
    qrz_errors: list[str]

    hamdb_errors: list[str]
    hamdb_used: bool

    flrig_url: str
    flrig_online: bool

    noaa_ok: bool
    noaa_loaded: bool


def _net_status_dot(ok: bool) -> str:
    return "[green]●[/green]" if ok else "[red]●[/red]"


def _net_svc_line(name: str, online: bool) -> str:
    dot = _net_status_dot(online)
    status = "[green]Online[/green]" if online else "[red]Offline[/red]"
    return f"{dot}  {name}  {status}"


def _net_svc_qrz(status: str) -> str:
    if status == "unconfigured":
        return "[dim]○[/dim]  QRZ API  Not configured"
    if status == "pending":
        return "[dim]○[/dim]  QRZ API  Waiting"
    dot = _net_status_dot(status == "ok")
    label = "[green]OK[/green]" if status == "ok" else "[red]Error[/red]"
    return f"{dot}  QRZ API  {label}"


def _net_svc_hamdb(errors: list[str], used: bool) -> str:
    if not used and not errors:
        return "[dim]○[/dim]  HamDB API  Not used"
    ok = len(errors) == 0
    dot = _net_status_dot(ok)
    label = "OK" if ok else f"{len(errors)} recent error(s)"
    return f"{dot}  HamDB API  {label}"


def _net_svc_flrig(online: bool, url: str) -> str:
    dot = _net_status_dot(online)
    status = "[green]Online[/green]" if online else "[red]Offline[/red]"
    return f"{dot}  flrig  {status}  [dim]({url})[/dim]"


def _net_svc_noaa(ok: bool, loaded: bool) -> str:
    if not loaded:
        return "[dim]○[/dim]  NOAA  Not loaded yet"
    dot = _net_status_dot(ok)
    label = "[green]OK[/green]" if ok else "[red]Fetch error[/red]"
    return f"{dot}  NOAA  {label}"


class NetworkStatusModal(ModalScreen[None]):
    CSS = """
    NetworkStatusModal { align: center middle; }
    #net-status-box {
        width: 64;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #net-status-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #net-ping-section {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
    }
    #net-ping-section Static { width: auto; height: 1; }
    #net-services-section {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
        margin-top: 1;
    }
    #net-services-section Static { width: auto; height: 1; }
    #net-errors-section {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
        margin-top: 1;
    }
    #net-errors-label {
        text-style: bold;
        color: $text-muted;
    }
    #net-errors-scroll { height: 8; }
    #net-status-close { height: auto; align: right middle; margin-top: 1; }
    """

    def __init__(self, snapshot: NetworkStatusSnapshot) -> None:
        super().__init__()
        self._snap = snapshot

    def compose(self) -> ComposeResult:
        s = self._snap

        if s.offline_manual:
            inet = "[yellow]Manual Offline[/yellow]  (Ctrl+N to toggle)"
        elif s.internet_online:
            inet = "[green]Online[/green]"
        else:
            inet = "[red]Offline[/red]"

        with Container(id="net-status-box"):
            yield Static("Network Status", id="net-status-title")

            with Vertical(id="net-ping-section"):
                yield Static(f"Internet:  {inet}")
                if s.offline_manual:
                    yield Static("Latency:   [dim]skipped (manual offline)[/dim]",
                                 id="net-ping-latency")
                else:
                    yield Static("Latency:   [dim]measuring…[/dim]",
                                 id="net-ping-latency")

            with Vertical(id="net-services-section"):
                if s.offline_manual:
                    yield Static("[dim]○[/dim]  POTA API  [dim]Paused[/dim]")
                    yield Static(_net_svc_qrz(s.qrz_status) if s.qrz_status == "unconfigured"
                                 else "[dim]○[/dim]  QRZ API  [dim]Paused[/dim]")
                    yield Static("[dim]○[/dim]  HamDB API  [dim]Paused[/dim]"
                                 if s.hamdb_used
                                 else _net_svc_hamdb(s.hamdb_errors, s.hamdb_used))
                    yield Static(_net_svc_flrig(s.flrig_online, s.flrig_url))
                    yield Static("[dim]○[/dim]  NOAA  [dim]Paused[/dim]")
                else:
                    yield Static(_net_svc_line("POTA API", s.pota_online))
                    yield Static(_net_svc_qrz(s.qrz_status))
                    yield Static(_net_svc_hamdb(s.hamdb_errors, s.hamdb_used))
                    yield Static(_net_svc_flrig(s.flrig_online, s.flrig_url))
                    yield Static(_net_svc_noaa(s.noaa_ok, s.noaa_loaded))

            errors: list[str] = []
            for e in s.qrz_errors:
                errors.append(f"QRZ:   {e}")
            for e in s.hamdb_errors:
                errors.append(f"HamDB: {e}")
            if errors:
                with Vertical(id="net-errors-section"):
                    yield Static("Recent Errors", id="net-errors-label")
                    with ScrollableContainer(id="net-errors-scroll"):
                        for entry in errors:
                            yield Static(entry)

            with Horizontal(id="net-status-close"):
                yield Button("Close", variant="primary", id="net-status-btn-close")

    def on_mount(self) -> None:
        if not self._snap.offline_manual:
            self._measure_ping()

    @work(thread=True, exclusive=True, group="net-ping")
    def _measure_ping(self) -> None:
        import socket
        import time

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            start = time.monotonic()
            sock.connect(("8.8.8.8", 53))
            latency_ms = (time.monotonic() - start) * 1000
            sock.close()
            self.app.call_from_thread(self._update_ping, f"{latency_ms:.0f} ms")
        except Exception:
            self.app.call_from_thread(self._update_ping, "[red]unreachable[/red]")

    def _update_ping(self, text: str) -> None:
        try:
            self.query_one("#net-ping-latency", Static).update(f"Latency:   {text}")
        except Exception:
            pass

    @on(Button.Pressed, "#net-status-btn-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Self-spot modal
# ---------------------------------------------------------------------------

class SelfSpotModal(ModalScreen[None]):
    CSS = """
    SelfSpotModal { align: center middle; }
    #spot-box {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #spot-title { text-align: center; text-style: bold; margin-bottom: 1; }
    #spot-offline-note { color: $warning; margin-bottom: 1; height: auto; }
    .spot-row { height: auto; margin-bottom: 1; }
    .spot-label { width: 14; padding-top: 1; color: $text-muted; }
    .spot-input { width: 1fr; }
    #spot-btns { align: right middle; height: auto; margin-top: 1; }
    """

    def __init__(
        self,
        callsign: str,
        park_ref: str,
        freq_khz: float,
        mode: str,
        pota_api_base: str,
        offline: bool = False,
    ) -> None:
        super().__init__()
        self._callsign = callsign
        self._park_ref = park_ref
        self._freq_khz = freq_khz
        self._mode = mode
        self._api_base = pota_api_base
        self._offline = offline

    def compose(self) -> ComposeResult:
        with Container(id="spot-box"):
            yield Static("Self-Spot", id="spot-title")
            if self._offline:
                yield Static("  Self-spotting unavailable in offline mode.", id="spot-offline-note")
            with Horizontal(classes="spot-row"):
                yield Label("Frequency:", classes="spot-label")
                yield Input(value=f"{self._freq_khz:.1f}", id="s-freq", classes="spot-input", disabled=self._offline)
            with Horizontal(classes="spot-row"):
                yield Label("Mode:", classes="spot-label")
                yield Input(value=self._mode, id="s-mode", classes="spot-input", disabled=self._offline)
            with Horizontal(classes="spot-row"):
                yield Label("Park Ref:", classes="spot-label")
                yield Input(value=self._park_ref, id="s-park", classes="spot-input", disabled=self._offline)
            with Horizontal(classes="spot-row"):
                yield Label("Activator:", classes="spot-label")
                yield Input(value=self._callsign, id="s-activator", classes="spot-input", disabled=self._offline)
            with Horizontal(classes="spot-row"):
                yield Label("Comments:", classes="spot-label")
                yield Input(
                    placeholder="CQ POTA 20m SSB",
                    id="s-comments",
                    classes="spot-input",
                    disabled=self._offline,
                )
            with Horizontal(id="spot-btns"):
                yield Button("Post Spot", variant="primary", id="s-post", disabled=self._offline)
                yield Button("Cancel", id="s-cancel")

    @on(Button.Pressed, "#s-post")
    def on_post(self) -> None:
        self._do_spot()

    @on(Button.Pressed, "#s-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter" and not self._offline:
            self._do_spot()

    @work
    async def _do_spot(self) -> None:
        from potatui.pota_api import self_spot

        freq_str = self.query_one("#s-freq", Input).value.strip()
        mode = self.query_one("#s-mode", Input).value.strip()
        park = self.query_one("#s-park", Input).value.strip().upper()
        activator = self.query_one("#s-activator", Input).value.strip().upper()
        comments = self.query_one("#s-comments", Input).value.strip()

        try:
            freq_khz = float(freq_str)
        except ValueError:
            self.app.notify("Invalid frequency", severity="error")
            return

        success, msg = await self_spot(
            self._api_base, activator, activator, freq_khz, park, mode, comments
        )
        if success:
            self.app.notify(msg, severity="information")
        else:
            self.app.notify(f"Spot failed: {msg}", severity="error")
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Set Run Frequency Modal
# ---------------------------------------------------------------------------

class SetFreqModal(ModalScreen):
    """Quick dialog to set the run/CQ frequency and tune flrig."""

    CSS = """
    SetFreqModal {
        align: center middle;
    }
    #setfreq-dialog {
        width: 44;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #setfreq-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #setfreq-hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    #setfreq-row {
        height: auto;
        margin-bottom: 1;
    }
    #setfreq-btns {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    #setfreq-cancel { margin-right: 1; }
    """

    def __init__(self, current_freq: float) -> None:
        super().__init__()
        self._current = current_freq

    def compose(self) -> ComposeResult:
        with Container(id="setfreq-dialog"):
            yield Static("Set Run Frequency", id="setfreq-title")
            yield Static("Enter frequency in kHz. flrig will be tuned if connected.", id="setfreq-hint")
            with Horizontal(id="setfreq-row"):
                yield Input(
                    value=f"{self._current:.1f}",
                    placeholder="14225.0",
                    id="setfreq-input",
                    select_on_focus=True,
                )
            with Horizontal(id="setfreq-btns"):
                yield Button("Cancel", id="setfreq-cancel")
                yield Button("Set", variant="primary", id="setfreq-ok")

    def on_mount(self) -> None:
        self.query_one("#setfreq-input", Input).focus()

    @on(Input.Submitted, "#setfreq-input")
    @on(Button.Pressed, "#setfreq-ok")
    def on_confirm(self) -> None:
        raw = self.query_one("#setfreq-input", Input).value.strip()
        try:
            freq = float(raw)
        except ValueError:
            return
        self.dismiss(freq)

    @on(Button.Pressed, "#setfreq-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Change Operator Modal
# ---------------------------------------------------------------------------

class ChangeOperatorModal(ModalScreen):
    """Quick dialog to change the active operator callsign."""

    CSS = """
    ChangeOperatorModal {
        align: center middle;
    }
    #chgop-dialog {
        width: 44;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #chgop-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #chgop-row {
        height: auto;
        margin-bottom: 1;
    }
    #chgop-btns {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    #chgop-cancel { margin-right: 1; }
    """

    def __init__(self, current_operator: str) -> None:
        super().__init__()
        self._current = current_operator

    def compose(self) -> ComposeResult:
        with Container(id="chgop-dialog"):
            yield Static("Change Operator", id="chgop-title")
            with Horizontal(id="chgop-row"):
                yield Input(
                    value=self._current,
                    placeholder="W1AW",
                    id="chgop-input",
                    select_on_focus=True,
                )
            with Horizontal(id="chgop-btns"):
                yield Button("Cancel", id="chgop-cancel")
                yield Button("Set", variant="primary", id="chgop-ok")

    def on_mount(self) -> None:
        self.query_one("#chgop-input", Input).focus()

    @on(Input.Submitted, "#chgop-input")
    @on(Button.Pressed, "#chgop-ok")
    def on_confirm(self) -> None:
        raw = self.query_one("#chgop-input", Input).value.strip().upper()
        if not raw:
            return
        self.dismiss(raw)

    @on(Button.Pressed, "#chgop-cancel")
    def on_cancel(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# WAWA Easter Egg Modal
# ---------------------------------------------------------------------------


class WawaModal(ModalScreen[None]):
    """Easter egg: show nearest Wawa when user types WAWA as callsign."""

    CSS = """
    WawaModal {
        align: center middle;
    }
    #wawa-box {
        width: 52;
        height: auto;
        border: heavy $warning;
        background: $surface;
        padding: 1 2;
    }
    #wawa-art {
        text-align: center;
        color: $warning;
        margin-bottom: 1;
    }
    #wawa-result {
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }
    #wawa-btn-row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, grid: str, use_miles: bool = True, offline_mode: bool = False) -> None:
        super().__init__()
        self._grid = grid
        self._use_miles = use_miles
        self._offline_mode = offline_mode

    def compose(self) -> ComposeResult:
        from potatui.wawa import WAWA_ASCII

        with Container(id="wawa-box"):
            yield Static(WAWA_ASCII, id="wawa-art")
            yield Static("Searching for nearest Wawa…", id="wawa-result")
            with Horizontal(id="wawa-btn-row"):
                yield Button("Nice!", variant="warning", id="wawa-close", disabled=True)

    def on_mount(self) -> None:
        self._do_lookup()

    @work
    async def _do_lookup(self) -> None:
        from potatui.qrz import grid_to_latlon
        from potatui.wawa import find_nearest_wawa_osm

        result_widget = self.query_one("#wawa-result", Static)
        unit = "mi" if self._use_miles else "km"

        found = False
        if self._offline_mode:
            result_widget.update("Offline mode active — Wawa search unavailable.")
        else:
            try:
                lat, lon = grid_to_latlon(self._grid)
                result = await find_nearest_wawa_osm(lat, lon, self._use_miles)
                if result is None:
                    result_widget.update("No Wawas within 50 miles. Sad :(")
                else:
                    address, distance = result
                    result_widget.update(f"{address}\n{distance:.1f} {unit} away")
                    found = True
            except RuntimeError as e:
                if str(e) == "rate_limited":
                    result_widget.update("Overpass API rate limited — try again in a minute.")
                else:
                    result_widget.update("Could not reach OpenStreetMap — check your connection.")
            except Exception:
                result_widget.update("Could not reach OpenStreetMap — check your connection.")

        btn = self.query_one("#wawa-close", Button)
        btn.label = "Nice!" if found else "Bummer"
        btn.disabled = False

    @on(Button.Pressed, "#wawa-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# Solar / Space Weather Modal
# ---------------------------------------------------------------------------


class SolarWeatherModal(ModalScreen[None]):
    """Space weather detail: current Kp, 24h history, and active alerts."""

    CSS = """
    SolarWeatherModal {
        align: center middle;
    }
    #solar-box {
        width: 90;
        height: auto;
        max-height: 62;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #solar-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #solar-conditions {
        height: auto;
        padding: 0 2;
        background: $panel;
        border: tall $primary;
        margin-bottom: 0;
        align: center middle;
    }
    #solar-conditions Static {
        width: auto;
        height: 1;
    }
    .solar-lbl {
        color: $text-muted;
    }
    .solar-val {
        text-style: bold;
    }
    .solar-sep {
        color: $text-muted;
    }
    #solar-prop-header {
        color: $text-muted;
        text-style: italic;
        margin-top: 0;
        margin-bottom: 1;
        padding: 0 1;
        background: $panel;
    }
    #solar-tables-row {
        height: auto;
        margin-top: 1;
    }
    #solar-history-col {
        width: 32;
        height: auto;
        margin-right: 1;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
    }
    #solar-forecast-col {
        width: 1fr;
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
    }
    #solar-history-label, #solar-forecast-label, #solar-alerts-label {
        text-style: bold;
        color: $text-muted;
        margin-bottom: 0;
    }
    #solar-alerts-label {
        margin-top: 0;
    }
    #solar-alerts-container {
        height: auto;
        border: tall $primary;
        background: $panel;
        padding: 0 1;
        margin-top: 1;
    }
    #solar-history-table {
        height: 10;
        margin-bottom: 0;
    }
    #solar-forecast-table {
        height: 10;
        margin-bottom: 0;
    }
    #solar-alerts-scroll {
        height: auto;
        max-height: 18;
    }
    .solar-alert {
        margin-bottom: 1;
    }
    #solar-btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    .solar-muted { color: $text-muted; text-style: italic; }
    """

    def __init__(self, data: SpaceWeatherData, park_latlon: tuple[float, float] | None = None, park_grid: str | None = None) -> None:
        super().__init__()
        self._data = data
        self._park_latlon = park_latlon
        self._park_grid = park_grid

    def compose(self) -> ComposeResult:
        from potatui.space_weather import kp_severity, kp_traditional

        data = self._data

        with VerticalScroll(id="solar-box"):
            yield Static("Space Weather", id="solar-title")

            # Current conditions – single line
            with Horizontal(id="solar-conditions"):
                if data.kp_current is None:
                    kp_display = "[dim]—[/dim]"
                else:
                    sev = kp_severity(data.kp_current)
                    color = {"normal": "green", "elevated": "yellow", "storm": "red"}[sev]
                    level = {"normal": "Normal", "elevated": "Elevated", "storm": "Storm"}[sev]
                    kp_display = f"[{color}]{kp_traditional(data.kp_current)} {level}[/{color}]"
                sfi_display = f"{data.sfi:.0f}" if data.sfi is not None else "[dim]—[/dim]"

                yield Static("Kp ", classes="solar-lbl")
                yield Static(kp_display, classes="solar-val")
                yield Static("  ·  ", classes="solar-sep")
                yield Static("SFI ", classes="solar-lbl")
                yield Static(sfi_display, classes="solar-val")
                if self._park_latlon is not None:
                    yield Static("  ·  ", classes="solar-sep")
                    yield Static("MUF ", classes="solar-lbl")
                    yield Static("[dim]…[/dim]", id="solar-muf-val", classes="solar-val")
                    yield Static("  ·  ", classes="solar-sep solar-fof2-sep")
                    yield Static("foF2 ", classes="solar-lbl solar-fof2-sep")
                    yield Static("[dim]…[/dim]", id="solar-fof2-val", classes="solar-val")

            # Propagation source note
            if self._park_latlon is not None:
                grid_label = self._park_grid or "unknown grid"
                yield Static(
                    f"[dim]Propagation for [bold]{grid_label}[/bold] via prop.kc2g.com[/dim]",
                    id="solar-prop-header",
                )

            # Kp history + 3-day forecast side by side
            with Horizontal(id="solar-tables-row"):
                with Vertical(id="solar-history-col"):
                    yield Static("Last 24h Kp", id="solar-history-label")
                    yield DataTable(id="solar-history-table", show_cursor=False, zebra_stripes=True)
                with Vertical(id="solar-forecast-col"):
                    yield Static("3-Day Kp Forecast", id="solar-forecast-label")
                    yield DataTable(id="solar-forecast-table", show_cursor=False, zebra_stripes=True)

            # Active alerts
            with Vertical(id="solar-alerts-container"):
                yield Static("Space Weather Alerts", id="solar-alerts-label")
                with ScrollableContainer(id="solar-alerts-scroll"):
                    if data.active_alerts:
                        for i, alert in enumerate(data.active_alerts):
                            if i > 0:
                                yield Rule()
                            yield Static(
                                f"{alert.issue_datetime[:16]}\n{alert.message}",
                                classes="solar-alert",
                            )
                    else:
                        yield Static("No alerts in the last 8 hours.", classes="solar-muted")

            with Horizontal(id="solar-btn-row"):
                yield Button("Close", variant="primary", id="solar-close")

    def on_mount(self) -> None:
        from potatui.space_weather import kp_severity, kp_traditional

        # Populate history DataTable
        table = self.query_one("#solar-history-table", DataTable)
        table.add_column("Time (UTC)", key="time")
        table.add_column("Kp", key="kp")

        data = self._data
        if data.kp_history:
            for reading in data.kp_history:
                sev = kp_severity(reading.kp)
                color = {"normal": "green", "elevated": "yellow", "storm": "red"}[sev]
                filled = round(reading.kp)
                bar = "▓" * min(filled, 6) + "░" * max(0, 6 - filled)
                table.add_row(
                    reading.time_utc[5:16],  # strip year: "MM-DD HH:MM"
                    f"[{color}]{bar} {kp_traditional(reading.kp)}[/{color}]",
                )
        else:
            table.add_row("—", "No history available")

        # Populate 3-day forecast table
        ftable = self.query_one("#solar-forecast-table", DataTable)
        if data.kp_forecast:
            ftable.add_column("UTC", key="period")
            for label in data.kp_forecast.day_labels:
                ftable.add_column(label, key=label.replace(" ", "_"))
            for period in data.kp_forecast.periods:
                row_label = period.label.replace("UT", "")
                cells: list[str] = [row_label]
                for kp_val in period.kp:
                    if kp_val is None:
                        cells.append("[dim]—[/dim]")
                    else:
                        sev = kp_severity(kp_val)
                        color = {"normal": "green", "elevated": "yellow", "storm": "red"}[sev]
                        cells.append(f"[{color}]{kp_traditional(kp_val)}[/{color}]")
                ftable.add_row(*cells)
        else:
            ftable.add_column("UTC", key="period")
            ftable.add_row("[dim]Forecast unavailable[/dim]")

        if self._park_latlon is not None:
            self._fetch_muf()

    @work(exclusive=True, group="solar-muf")
    async def _fetch_muf(self) -> None:
        lat, lon = self._park_latlon  # type: ignore[misc]
        try:
            muf = await fetch_muf(lat, lon)
        except Exception:
            try:
                self.query_one("#solar-muf-val", Static).update("[dim]n/a[/dim]")
                for w in self.query(".solar-fof2-sep"):
                    w.display = False
                self.query_one("#solar-fof2-val", Static).display = False
            except Exception:
                pass
            return

        stale_note = " [dim](stale)[/dim]" if muf.stale else ""
        try:
            self.query_one("#solar-muf-val", Static).update(f"{muf.mufd:.1f} MHz{stale_note}")
            self.query_one("#solar-fof2-val", Static).update(f"{muf.fof2:.1f} MHz")
        except Exception:
            pass

    @on(Button.Pressed, "#solar-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


# ---------------------------------------------------------------------------
# About modal
# ---------------------------------------------------------------------------

_LAST_UPDATED = "2026-03-24"

_ABOUT_LOGO = [
    "██████╗  ██████╗ ████████╗ █████╗ ████████╗██╗   ██╗██╗",
    "██╔══██╗██╔═══██╗╚══██╔══╝██╔══██╗╚══██╔══╝██║   ██║██║",
    "██████╔╝██║   ██║   ██║   ███████║   ██║   ██║   ██║██║",
    "██╔═══╝ ██║   ██║   ██║   ██╔══██║   ██║   ██║   ██║██║",
    "██║     ╚██████╔╝   ██║   ██║  ██║   ██║   ╚██████╔╝██║",
    "╚═╝      ╚═════╝    ╚═╝   ╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝",
]
_ABOUT_SUBTITLE = "P a r k s  O n  T h e  A i r  ·  T U I  L o g g e r"


class AboutModal(ModalScreen[None]):
    """About screen — F1."""

    CSS = """
    AboutModal {
        align: center middle;
    }
    #about-box {
        width: 64;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #about-logo {
        text-align: center;
        color: $primary;
        margin-bottom: 0;
        opacity: 1.0;
    }
    #about-subtitle {
        text-align: center;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    #about-rule {
        margin: 1 0;
        color: $primary-darken-2;
    }
    #about-body {
        text-align: center;
        height: auto;
        margin-bottom: 0;
    }
    #about-meta-row {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    #about-meta-prefix {
        color: $text-muted;
        width: auto;
    }
    #about-db-btn {
        color: $primary;
        background: transparent;
        border: none;
        height: auto;
        min-width: 0;
        width: auto;
        padding: 0;
        text-style: underline;
    }
    #about-db-btn:hover {
        background: transparent;
        color: $primary-lighten-1;
        text-style: underline bold;
    }
    #about-db-btn:focus {
        background: transparent;
        color: $primary-lighten-1;
        text-style: underline bold;
    }
    #about-btn-row {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        logo_text = "\n".join(_ABOUT_LOGO)
        db_date = park_db.db_updated
        db_label = db_date if db_date else "not downloaded"
        with Container(id="about-box"):
            yield Static(logo_text, id="about-logo")
            yield Static(_ABOUT_SUBTITLE, id="about-subtitle")
            yield Rule(id="about-rule")
            yield Static(
                "Created by [bold]NV3Y[/bold] with help from [bold]Claude[/bold] (Anthropic)\n"
                "Licensed under the GNU General Public License v3.0 or later",
                id="about-body",
            )
            with Horizontal(id="about-meta-row"):
                yield Static(f"App updated: {_LAST_UPDATED}  ·  Park DB: ", id="about-meta-prefix")
                yield Button(db_label, id="about-db-btn")
            with Horizontal(id="about-btn-row"):
                yield Button("Close", variant="primary", id="about-close")

    def on_mount(self) -> None:
        self.query_one("#about-close", Button).focus()
        self._pulse_t = 0.0
        self.set_interval(1 / 20, self._pulse_step)

    def _pulse_step(self) -> None:
        self._pulse_t += 1 / 20
        # Sine wave: 0.45–1.0 range, ~3-second period
        opacity = 0.725 + 0.275 * math.sin(2 * math.pi * self._pulse_t / 3.0)
        self.query_one("#about-logo", Static).styles.opacity = opacity

    @on(Button.Pressed, "#about-db-btn")
    def on_db_btn(self) -> None:
        from potatui.screens.park_update import ParkDbModal

        def _after_update(downloaded: bool | None) -> None:
            if downloaded:
                park_db.load()
                new_date = park_db.db_updated or "not downloaded"
                self.query_one("#about-db-btn", Button).label = new_date

        self.app.push_screen(ParkDbModal(is_refresh=True), _after_update)

    @on(Button.Pressed, "#about-close")
    def on_close(self) -> None:
        self.dismiss(None)

    def on_key(self, event) -> None:
        if event.key in ("escape", "f1"):
            self.dismiss(None)
