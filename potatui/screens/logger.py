"""Main logging screen."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from textual import events, on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)
from textual.widgets._input import Selection

from potatui.adif import append_qso_adif, freq_to_band, session_file_stem, write_adif
from potatui.config import Config
from potatui.flrig import FlrigClient
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

class ModePickerModal(ModalScreen[Optional[str]]):
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

class EditQSOModal(ModalScreen[Optional[dict]]):
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


# ---------------------------------------------------------------------------
# Voice keyer modal
# ---------------------------------------------------------------------------

class VoiceKeyerModal(ModalScreen[None]):
    CSS = """
    VoiceKeyerModal { align: center middle; }
    #vk-box {
        width: 44;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    #vk-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #vk-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    .vk-btn {
        width: 1fr;
        margin-bottom: 1;
    }
    .vk-btn-disabled {
        width: 1fr;
        margin-bottom: 1;
    }
    #vk-status {
        text-align: center;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, vk_commands: list[str], flrig: "FlrigClient") -> None:
        super().__init__()
        self._commands = vk_commands
        self._flrig = flrig

    def compose(self) -> ComposeResult:
        with Container(id="vk-box"):
            yield Static("Voice Keyer", id="vk-title")
            yield Static("Press 1–5 or click a button", id="vk-subtitle")
            for i, cmd in enumerate(self._commands, start=1):
                label = f"[{i}]  VK{i}  {cmd}" if cmd else f"[{i}]  VK{i}  (not configured)"
                btn = Button(label, id=f"vk-btn-{i}", classes="vk-btn", disabled=not cmd)
                yield btn
            yield Static("", id="vk-status")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key.isdigit():
            idx = int(event.key)
            if 1 <= idx <= 5:
                event.stop()
                self._fire(idx)

    @on(Button.Pressed)
    def on_btn_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("vk-btn-"):
            idx = int(btn_id.split("-")[-1])
            self._fire(idx)

    def _fire(self, idx: int) -> None:
        cmd = self._commands[idx - 1] if idx <= len(self._commands) else ""
        if not cmd:
            self._set_status(f"VK{idx} not configured", error=True)
            return
        ok = self._flrig.send_cat_string(cmd)
        if ok:
            self._set_status(f"VK{idx} fired  ({cmd})", error=False)
        else:
            self._set_status("flrig not connected", error=True)

    def _set_status(self, msg: str, error: bool) -> None:
        status = self.query_one("#vk-status", Static)
        status.update(msg)
        if error:
            status.styles.color = "red"
        else:
            status.styles.color = "green"


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
    ) -> None:
        super().__init__()
        self._callsign = callsign
        self._park_ref = park_ref
        self._freq_khz = freq_khz
        self._mode = mode
        self._api_base = pota_api_base

    def compose(self) -> ComposeResult:
        with Container(id="spot-box"):
            yield Static("Self-Spot", id="spot-title")
            with Horizontal(classes="spot-row"):
                yield Label("Frequency:", classes="spot-label")
                yield Input(value=f"{self._freq_khz:.1f}", id="s-freq", classes="spot-input")
            with Horizontal(classes="spot-row"):
                yield Label("Mode:", classes="spot-label")
                yield Input(value=self._mode, id="s-mode", classes="spot-input")
            with Horizontal(classes="spot-row"):
                yield Label("Park Ref:", classes="spot-label")
                yield Input(value=self._park_ref, id="s-park", classes="spot-input")
            with Horizontal(classes="spot-row"):
                yield Label("Activator:", classes="spot-label")
                yield Input(value=self._callsign, id="s-activator", classes="spot-input")
            with Horizontal(classes="spot-row"):
                yield Label("Comments:", classes="spot-label")
                yield Input(
                    placeholder="CQ POTA 20m SSB",
                    id="s-comments",
                    classes="spot-input",
                )
            with Horizontal(id="spot-btns"):
                yield Button("Post Spot", variant="primary", id="s-post")
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


# ---------------------------------------------------------------------------
# Main Logger Screen
# ---------------------------------------------------------------------------

class LoggerScreen(Screen):
    BINDINGS = [
        Binding("f2", "set_freq", "Set Run Freq"),
        Binding("f3", "mode_picker", "Mode"),
        Binding("f4", "edit_last_qso", "Edit QSOs"),
        Binding("f5", "goto_spots", "Spots"),
        Binding("f6", "self_spot", "Self-Spot"),
        Binding("f7", "voice_keyer", "VK Panel"),
        Binding("f8", "settings", "Settings"),
        Binding("ctrl+1", "vk1", "VK1", show=False),
        Binding("ctrl+2", "vk2", "VK2", show=False),
        Binding("ctrl+3", "vk3", "VK3", show=False),
        Binding("ctrl+4", "vk4", "VK4", show=False),
        Binding("ctrl+5", "vk5", "VK5", show=False),
        Binding("f10", "end_session", "End Session"),
        Binding("ctrl+d", "delete_qso", "Del QSO"),
        Binding("f9", "qrz_backfill", "QRZ Backfill"),
        Binding("escape", "clear_form", "Clear QSO"),
        Binding("ctrl+o", "change_operator", "Operator change"),
    ]

    CSS = """
    LoggerScreen {
        layout: vertical;
    }

    #header-bar {
        height: 3;
        background: $primary-darken-2;
        padding: 0 1;
        layout: horizontal;
        align: left middle;
    }

    #header-bar:dark {
        background: $primary-darken-3;
        tint: $background 40%;
    }

    .hdr-item {
        padding: 0 1;
        color: $text;
        width: auto;
    }

    .hdr-sep {
        color: $text-muted;
        padding: 0 0;
        width: auto;
    }


    .hdr-offline {
        color: $warning;
    }

    #hdr-net, #hdr-flrig, #hdr-qrz {
        width: auto;
        padding: 0 1;
        color: $background;
        text-style: bold;
    }

    #hdr-net.net-online, #hdr-flrig.flrig-online, #hdr-qrz.qrz-ok {
        background: $success;
    }

    #hdr-net.net-offline, #hdr-flrig.flrig-offline, #hdr-qrz.qrz-error {
        background: $error;
    }

    #hdr-net.net-unknown, #hdr-qrz.qrz-unconfigured {
        background: $panel;
        color: $text-muted;
    }

    #hdr-spacer {
        width: 1fr;
    }

    #entry-form {
        height: auto;
        background: $surface-darken-1;
        padding: 1;
        layout: horizontal;
        border-bottom: solid $primary-darken-2;
    }

    .form-field {
        layout: vertical;
        margin-right: 1;
        height: auto;
    }

    .form-label {
        color: $text-muted;
        height: 1;
    }

    #dup-warning {
        color: $warning;
        text-style: bold;
        height: 1;
    }

    #freq-field {
        width: 14;
    }

    #callsign-field {
        width: 22;
    }

    #p2p-field {
        width: 26;
    }

    #rst-sent-field {
        width: 10;
    }

    #rst-rcvd-field {
        width: 10;
    }

    #state-field {
        width: 14;
    }

    #qrz-info-bar {
        height: 3;
        background: #0d0d0d;
        border: round $accent;
        padding: 0 2;
        color: $accent;
        text-style: bold;
        content-align: left middle;
    }

    #qrz-info-bar.hidden {
        display: none;
    }

    #qrz-info-bar.pending {
        color: $accent-darken-2;
        text-style: italic;
        border: round $accent-darken-2;
    }

    #qrz-info-bar.notfound {
        color: $text-muted;
        text-style: none;
        border: round $surface-lighten-2;
    }

    #p2p-info-bar {
        height: 3;
        background: #0d0d0d;
        border: round $accent;
        padding: 0 2;
        color: $accent;
        text-style: bold;
        content-align: left middle;
    }

    #p2p-info-bar.hidden {
        display: none;
    }

    #p2p-info-bar.warn {
        color: $warning;
        border: round $warning;
    }

    #btn-log {
        min-width: 8;
    }

    #last-spotted-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }

    #last-spotted-bar.hidden {
        display: none;
    }

    #last-spotted-bar.spot-recent {
        color: $success;
        text-style: bold;
    }

    #last-spotted-bar.spot-stale {
        color: $warning;
        text-style: none;
    }

    #last-spotted-bar.spot-old {
        color: $text-muted;
        text-style: italic;
    }

    #qso-table-container {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
    }
    """

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
        from potatui.qrz import QRZClient
        self._qrz = QRZClient(config.qrz_username, config.qrz_password, config.qrz_api_url)
        self._park_latlon: tuple[float, float] | None = None
        self._last_spot_data: tuple[datetime, str, str] | None = None  # (utc_time, spotter, comments)
        self._log_paths = self._make_log_paths()
        self._json_path = self._make_json_path()

    def _make_log_paths(self):
        from pathlib import Path
        return [
            self.config.log_dir_path / f"{session_file_stem(self.session, ref)}.adi"
            for ref in self.session.park_refs
        ]

    def _make_json_path(self):
        from pathlib import Path
        stem = session_file_stem(self.session)
        return self.config.log_dir_path / f"{stem}.json"

    def compose(self) -> ComposeResult:
        # Header bar
        with Horizontal(id="header-bar"):
            yield Static("", id="hdr-op", classes="hdr-item")
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
            yield Static("flrig", id="hdr-flrig", classes="flrig-offline")
            yield Static("|", classes="hdr-sep")
            yield Static("qrz", id="hdr-qrz", classes="qrz-unconfigured")

        # Last-spotted bar (hidden until a spot is found)
        yield Static("", id="last-spotted-bar", classes="hidden")

        # Entry form
        with Horizontal(id="entry-form"):
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
                yield Input(value="US-", id="f-p2p", select_on_focus=False)
            with Vertical(classes="form-field"):
                yield Label("Name", classes="form-label")
                yield Input(placeholder="optional", id="f-name")
            with Vertical(classes="form-field", id="state-field"):
                yield Label("State/Loc", classes="form-label")
                yield Input(placeholder="optional", id="f-state")
            with Vertical(classes="form-field"):
                yield Label("Notes", classes="form-label")
                yield Input(placeholder="optional", id="f-notes")
            with Vertical(classes="form-field", id="freq-field"):
                yield Label("Freq (kHz)", classes="form-label")
                yield Input(value=f"{self.freq_khz:.1f}", id="f-freq", max_length=10)
            with Vertical(classes="form-field"):
                yield Label(" ", classes="form-label")
                yield Button("Log [Enter]", variant="primary", id="btn-log")

        # QRZ callsign info strip (hidden when empty)
        yield Static("", id="qrz-info-bar", classes="hidden")

        # P2P park info strip (hidden when empty)
        yield Static("", id="p2p-info-bar", classes="hidden")

        # QSO table
        with Container(id="qso-table-container"):
            yield DataTable(id="qso-table", cursor_type="row")

        yield Footer()

    def on_mount(self) -> None:
        self._setup_table()
        if self.session.qsos:
            self._rebuild_table()
        self._update_header()
        self.set_interval(1.0, self._tick_clock)
        self.set_interval(2.0, self._poll_flrig)
        self.set_interval(30.0, self._check_internet_connectivity)
        self.set_interval(60.0, self._poll_spots_for_self)
        self._check_internet_connectivity()
        self._fetch_park_location()
        self._poll_spots_for_self()
        self._update_qrz_indicator()
        self.query_one("#f-callsign", Input).focus()

    @work
    async def _fetch_park_location(self) -> None:
        """Fetch the active park's lat/lon from the POTA API for distance calculations."""
        from potatui.pota_api import lookup_park
        from potatui.qrz import grid_to_latlon
        info = await lookup_park(self.session.active_park_ref, self.config.pota_api_base)
        if info and info.grid:
            try:
                self._park_latlon = grid_to_latlon(info.grid)
            except Exception:
                pass

    def _setup_table(self) -> None:
        table = self.query_one("#qso-table", DataTable)
        table.add_columns("#", "UTC", "Callsign", "Sent", "Rcvd", "Freq", "Mode", "Name", "State", "P2P", "Notes")

    def _update_header(self) -> None:
        park_ref = self.session.active_park_ref
        park_name = self.park_names.get(park_ref, "")
        # Only append name if it's non-empty and different from the ref itself
        if park_name and park_name != park_ref:
            park_display = f"{park_ref}  {park_name}"
        else:
            park_display = park_ref
        self.query_one("#hdr-park", Static).update(park_display)
        self.query_one("#hdr-op", Static).update(self.session.operator)
        self._update_radio_display()
        self._update_qso_count()

    def _update_radio_display(self) -> None:
        if self._flrig_online:
            radio_str = f"{self.freq_khz:.1f} kHz  {self.band}  {self.mode}"
        else:
            radio_str = f"---  {self.band}  {self.mode}"
        self.query_one("#hdr-radio", Static).update(radio_str)

        flrig_widget = self.query_one("#hdr-flrig", Static)
        if self._flrig_online:
            flrig_widget.add_class("flrig-online")
            flrig_widget.remove_class("flrig-offline")
        else:
            flrig_widget.add_class("flrig-offline")
            flrig_widget.remove_class("flrig-online")

    def _update_qso_count(self) -> None:
        count = len(self.session.qsos)
        count_widget = self.query_one("#hdr-qso-count", Static)
        count_widget.update(f"QSOs: {count}")

    def _tick_clock(self) -> None:
        now = datetime.utcnow()
        utc_str = now.strftime("%H:%Mz")
        elapsed = now - self.session.start_time
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        elapsed_str = f"{h:02d}:{m:02d}:{s:02d}"
        self.query_one("#hdr-utc", Static).update(utc_str)
        self.query_one("#hdr-elapsed", Static).update(elapsed_str)
        self._update_last_spotted_bar()

    @work(exclusive=True, group="self-spot-poll")
    async def _poll_spots_for_self(self) -> None:
        """Fetch current POTA spots and find the most recent one for our callsign."""
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
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

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
        now = datetime.now(timezone.utc)
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

        if freq is not None:
            self._flrig_online = True
            self.freq_khz = freq
            band = freq_to_band(freq)
            if band != "?":
                self.band = band
            if mode:
                self.mode = mode
            # Sync the freq input field (only if it doesn't have focus —
            # don't clobber what the user is typing)
            freq_inp = self.query_one("#f-freq", Input)
            if not freq_inp.has_focus:
                freq_inp.value = f"{freq:.1f}"
        else:
            self._flrig_online = False

        self._update_radio_display()

    def _update_qrz_indicator(self) -> None:
        try:
            widget = self.query_one("#hdr-qrz", Static)
            widget.set_classes(f"qrz-{self._qrz.status}")
        except Exception:
            pass

    @on(events.Click, "#hdr-qrz")
    def on_qrz_indicator_click(self) -> None:
        if not self._qrz.configured:
            self.notify("QRZ not configured — add credentials in Settings (F8)", severity="warning")
            return
        self.app.push_screen(QrzLogModal(self._qrz.error_log))

    @work(exclusive=True, group="net-check")
    async def _check_internet_connectivity(self) -> None:
        from potatui.park_db import check_internet
        online = await check_internet(self.config.pota_api_base)
        net_widget = self.query_one("#hdr-net", Static)
        if online:
            net_widget.add_class("net-online")
            net_widget.remove_class("net-offline")
            net_widget.remove_class("net-unknown")
        else:
            net_widget.add_class("net-offline")
            net_widget.remove_class("net-online")
            net_widget.remove_class("net-unknown")

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
        """Select signal digits on RST field focus so typing overwrites just that part."""
        if event.widget.id not in ("f-rst-sent", "f-rst-rcvd"):
            return
        inp = event.widget
        val = inp.value
        if len(val) > 1:
            inp.selection = Selection(1, len(val))

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
            name = form_name or (info.name if info else "") or ""
            state = form_state or (info.state if info else "") or ""
            return name, state

        new_qsos: list[QSO] = []
        if p2p_refs:
            for callsign in callsigns:
                name, state = await _resolve_name_state(callsign)
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
                    ))
        else:
            for callsign in callsigns:
                name, state = await _resolve_name_state(callsign)
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
                ))

        # Rebuild table so newest QSO(s) appear at top
        self._rebuild_table()

        # Persist — append each new QSO to every park's ADIF file
        for park_ref, log_path in zip(self.session.park_refs, self._log_paths):
            for qso in new_qsos:
                try:
                    append_qso_adif(qso, self.session.operator, self.session.station_callsign, park_ref, log_path, self.session.my_state)
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
        self.query_one("#f-p2p", Input).value = "US-"
        self.query_one("#dup-warning", Static).update("")
        self._clear_p2p_info()
        self._clear_qrz_info()
        self.query_one("#f-callsign", Input).focus()

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @on(Input.Changed, "#f-callsign")
    def on_callsign_changed(self, event: Input.Changed) -> None:
        callsign = event.value.strip().upper()
        dup_widget = self.query_one("#dup-warning", Static)

        # Multi-callsign mode: suppress per-callsign QRZ and dup logic
        if "," in callsign:
            dup_widget.update("")
            self._clear_qrz_info()
            return

        if callsign and self.session.is_duplicate(callsign, self.band):
            dup_widget.update("DUP")
        else:
            dup_widget.update("")

        # Trigger QRZ lookup when the callsign looks complete
        if self._looks_like_callsign(callsign):
            self._lookup_qrz(callsign)
        else:
            self._clear_qrz_info()
            if not callsign:
                self.query_one("#f-name", Input).value = ""
                self.query_one("#f-state", Input).value = ""

    @staticmethod
    def _looks_like_callsign(cs: str) -> bool:
        """True when the string looks like a complete callsign worth querying."""
        if len(cs) < 3:
            return False
        return any(c.isdigit() for c in cs) and sum(c.isalpha() for c in cs) >= 2

    @work(exclusive=True, group="qrz-lookup")
    async def _lookup_qrz(self, callsign: str) -> None:
        # Debounce: wait for typing to pause before hitting QRZ
        await asyncio.sleep(1.0)

        # Stale-check: if the form callsign changed while we were waiting, bail out
        current_cs = self.query_one("#f-callsign", Input).value.strip().upper()
        if current_cs != callsign:
            return

        from potatui.qrz import (
            bearing_deg, cardinal, distance_from_grid,
            grid_to_latlon, haversine_km,
        )
        bar = self.query_one("#qrz-info-bar", Static)

        if not self._qrz.configured:
            bar.set_classes("hidden")
            return

        bar.set_classes("pending")
        bar.update("  QRZ: looking up…")

        info = await self._qrz.lookup(callsign)

        # Stale-check again after the HTTP round-trip
        current_cs = self.query_one("#f-callsign", Input).value.strip().upper()
        if current_cs != callsign:
            return

        if info is None:
            bar.set_classes("notfound")
            bar.update(f"  QRZ: {callsign} — not found")
            self._update_qrz_indicator()
            return

        # Auto-fill name and state fields if empty (state only if P2P not entered)
        if info.name:
            name_inp = self.query_one("#f-name", Input)
            if not name_inp.value.strip():
                name_inp.value = info.name

        p2p_val = self.query_one("#f-p2p", Input).value.strip().upper()
        state_inp = self.query_one("#f-state", Input)
        if not state_inp.value.strip() and p2p_val in ("", "US-") and info.state:
            state_inp.value = info.state

        parts = [f"  {info.callsign}"]
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
        if self._park_latlon is not None and clat is not None and clon is not None:
            plat, plon = self._park_latlon
            dist_km = haversine_km(plat, plon, clat, clon)
            brg = bearing_deg(plat, plon, clat, clon)
            direction = cardinal(brg)
        else:
            dist_km = distance_from_grid(self.session.grid, info)
            if dist_km is not None and self.session.grid:
                try:
                    plat, plon = grid_to_latlon(self.session.grid)
                    if clat is not None and clon is not None:
                        brg = bearing_deg(plat, plon, clat, clon)
                        direction = cardinal(brg)
                    else:
                        direction = None
                except Exception:
                    direction = None
            else:
                direction = None

        if dist_km is not None:
            use_mi = self.config.distance_unit.lower() == "mi"
            if use_mi:
                dist_str = f"{dist_km * 0.621371:,.0f} mi"
            else:
                dist_str = f"{dist_km:,.0f} km"
            if direction:
                dist_str = f"{direction} {dist_str}"
            parts.append(dist_str)

        bar.set_classes("")
        bar.update("  ·  ".join(parts))
        self._update_qrz_indicator()

    def _clear_qrz_info(self) -> None:
        bar = self.query_one("#qrz-info-bar", Static)
        bar.update("")
        bar.set_classes("hidden")

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
        raw = event.value.strip().upper()
        if not raw or raw == "US-":
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
        from potatui.pota_api import lookup_park
        self._set_p2p_info(f"  P2P: {', '.join(refs)} — looking up…", warn=False)

        results = [(ref, await lookup_park(ref, self.config.pota_api_base)) for ref in refs]

        # Discard if the field changed while we were looking up
        current = self.query_one("#f-p2p", Input).value.strip().upper()
        if current != raw:
            return

        segments = []
        first_state: str | None = None
        has_error = False
        for ref, info in results:
            if info:
                segments.append(f"{info.reference}  {info.name}  ({info.location})")
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

        self._set_p2p_info("  " + "  ·  ".join(segments), warn=has_error)
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
        "#f-callsign", "#f-rst-sent", "#f-rst-rcvd", "#f-p2p",
        "#f-name", "#f-state", "#f-notes", "#f-freq", "#btn-log",
    ]

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if focused is None:
            return
        focused_id = f"#{focused.id}" if focused.id else None
        if focused_id not in self._FORM_FIELDS:
            return
        if event.key == "tab" and focused_id == "#btn-log":
            event.prevent_default()
            event.stop()
            self.query_one("#f-callsign", Input).focus()
        elif event.key == "shift+tab" and focused_id == "#f-callsign":
            event.prevent_default()
            event.stop()
            self.query_one("#btn-log", Button).focus()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

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
            # Tune flrig if connected
            if self._flrig_online:
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
        def on_result(mode: Optional[str]) -> None:
            if mode:
                self.mode = mode
                self._update_radio_display()
                # Update RST defaults
                self.query_one("#f-rst-sent", Input).value = _rst_default(mode)
                self.query_one("#f-rst-rcvd", Input).value = _rst_default(mode)

        self.app.push_screen(ModePickerModal(self.mode), on_result)

    def _qso_id_from_table_cursor(self) -> Optional[int]:
        """Return the QSO id of the currently highlighted table row, or None."""
        table = self.query_one("#qso-table", DataTable)
        try:
            row_data = table.get_row_at(table.cursor_row)
            return int(row_data[0])
        except Exception:
            return None

    def _open_edit_for_qso_id(self, qso_id: int) -> None:
        qso = next((q for q in self.session.qsos if q.qso_id == qso_id), None)
        if qso is None:
            return

        def on_result(data: Optional[dict]) -> None:
            if data:
                self.session.update_qso(qso_id, **data)
                self._rebuild_table()
                self._save_session()
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths):
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

    def action_clear_form(self) -> None:
        """Escape — clear entry form and return focus to callsign."""
        self._reset_form()

    def action_goto_spots(self) -> None:
        from potatui.screens.spots import SpotsScreen

        self.app.push_screen(
            SpotsScreen(
                config=self.config,
                flrig=self.flrig,
                park_latlon=self._park_latlon,
                session=self.session,
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
            )
        )

    def _fire_vk(self, idx: int) -> None:
        """Fire voice keyer slot idx (1–5) and show a notification."""
        commands = [self.config.vk1, self.config.vk2, self.config.vk3,
                    self.config.vk4, self.config.vk5]
        cmd = commands[idx - 1] if idx <= len(commands) else ""
        if not cmd:
            self.notify(f"VK{idx} not configured", severity="warning")
            return
        ok = self.flrig.send_cat_string(cmd)
        if ok:
            self.notify(f"VK{idx}  {cmd}", severity="information")
        else:
            self.notify("flrig not connected", severity="error")

    def action_vk1(self) -> None: self._fire_vk(1)
    def action_vk2(self) -> None: self._fire_vk(2)
    def action_vk3(self) -> None: self._fire_vk(3)
    def action_vk4(self) -> None: self._fire_vk(4)
    def action_vk5(self) -> None: self._fire_vk(5)

    def action_voice_keyer(self) -> None:
        cfg = self.config
        commands = [cfg.vk1, cfg.vk2, cfg.vk3, cfg.vk4, cfg.vk5]
        self.app.push_screen(VoiceKeyerModal(commands, self.flrig))

    def action_settings(self) -> None:
        from potatui.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen(self.config))

    def action_end_session(self) -> None:
        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths):
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
            ConfirmModal(f"End session? ({len(self.session.qsos)} QSOs logged)\nADIF will be exported."),
            on_confirm,
        )

    def action_delete_qso(self) -> None:
        table = self.query_one("#qso-table", DataTable)
        row_key = table.cursor_row
        if row_key is None:
            return
        # Get QSO id from the first column of the selected row
        try:
            row_data = table.get_row_at(row_key)
            qso_id = int(row_data[0])
        except Exception:
            return

        def on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.session.remove_qso(qso_id)
                self._rebuild_table()
                self._update_qso_count()
                self._save_session()
                try:
                    for park_ref, log_path in zip(self.session.park_refs, self._log_paths):
                        write_adif(self.session, log_path, park_ref)
                except Exception as e:
                    self.notify(f"ADIF rewrite error: {e}", severity="error")

        self.app.push_screen(ConfirmModal(f"Delete QSO #{qso_id}?"), on_confirm)

    @work(exclusive=True, group="qrz-backfill")
    async def action_qrz_backfill(self) -> None:
        """Ctrl+Q — look up QRZ info for all QSOs with empty name."""
        if not self._qrz.configured:
            self.notify("QRZ not configured", severity="warning")
            return
        targets = [q for q in self.session.qsos if not q.name]
        if not targets:
            self.notify("All contacts already have names")
            return
        self.notify(f"QRZ: looking up {len(targets)} contact(s)…")
        updated = 0
        for qso in targets:
            info = await self._qrz.lookup(qso.callsign)
            if info:
                state = qso.state if qso.is_p2p else (info.state or qso.state)
                self.session.update_qso(qso.qso_id, name=info.name, state=state)
                updated += 1
        self._rebuild_table()
        self._save_session()
        try:
            for park_ref, log_path in zip(self.session.park_refs, self._log_paths):
                write_adif(self.session, log_path, park_ref)
        except Exception as e:
            self.notify(f"ADIF rewrite error: {e}", severity="error")
            return
        self._update_qrz_indicator()
        self.notify(f"QRZ: updated {updated} of {len(targets)} contact(s)")

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
