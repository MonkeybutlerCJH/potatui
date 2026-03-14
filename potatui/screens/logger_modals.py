# SPDX-License-Identifier: CC-BY-NC-SA-4.0
# Copyright (c) 2026 MonkeybutlerCJH (https://github.com/MonkeybutlerCJH)

"""Modal dialogs used by the logger screen (and potentially others)."""

from __future__ import annotations

from datetime import datetime, timedelta

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Select, Static

from potatui.adif import freq_to_band
from potatui.session import QSO, Session

MODES = ["SSB", "CW", "FT8", "FT4", "AM", "FM"]

# Full default RST values. On focus, the signal digits (after the first char)
# are selected so the user can type to replace just that part.
# FT8/FT4 use dB values (e.g. -10) so leave blank.
DEFAULT_RST: dict[str, str] = {
    "SSB": "59",
    "AM": "59",
    "FM": "59",
    "CW": "599",
    "FT8": "",
    "FT4": "",
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
