"""Session resume screen — pick a saved session to continue."""

from __future__ import annotations

import colorsys
import json
import math
from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Footer, Static

from potatui.config import Config
from potatui.session import Session

LOGO_LINES = [
    "██████╗  ██████╗ ████████╗ █████╗ ████████╗██╗   ██╗██╗",
    "██╔══██╗██╔═══██╗╚══██╔══╝██╔══██╗╚══██╔══╝██║   ██║██║",
    "██████╔╝██║   ██║   ██║   ███████║   ██║   ██║   ██║██║",
    "██╔═══╝ ██║   ██║   ██║   ██╔══██║   ██║   ██║   ██║██║",
    "██║     ╚██████╔╝   ██║   ██║  ██║   ██║   ╚██████╔╝██║",
    "╚═╝      ╚═════╝    ╚═╝   ╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝",
]
SUBTITLE = "P a r k s  O n  T h e  A i r  ·  T U I  L o g g e r"

_WAVE_BARS = "▁▂▃▄▅▆▇█"
_WAVE_WIDTH = 55  # matches logo width
_PANEL_WIDTH = 88  # width of the session picker panel


def _hsl_hex(h_deg: float, s_pct: float, l_pct: float) -> str:
    """Convert HSL to a Rich-compatible hex color string."""
    # colorsys uses HLS order (hue, lightness, saturation)
    r, g, b = colorsys.hls_to_rgb(h_deg / 360.0, l_pct / 100.0, s_pct / 100.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


@dataclass
class SavedSessionMeta:
    path: Path
    operator: str
    station_callsign: str
    park_refs: list[str]
    start_time: str
    qso_count: int

    @property
    def display_date(self) -> str:
        try:
            return self.start_time[:10]
        except Exception:
            return "?"


def find_saved_sessions(log_dir: Path) -> list[SavedSessionMeta]:
    """Scan log_dir for *.json session files, sorted newest first."""
    sessions: list[SavedSessionMeta] = []
    if not log_dir.exists():
        return sessions

    for p in sorted(log_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(p) as f:
                data = json.load(f)
            operator = data.get("operator", "?")
            sessions.append(SavedSessionMeta(
                path=p,
                operator=operator,
                station_callsign=data.get("station_callsign", operator),
                park_refs=data.get("park_refs", []),
                start_time=data.get("start_time", ""),
                qso_count=len(data.get("qsos", [])),
            ))
        except Exception:
            continue
    return sessions


class AnimatedLogo(Widget):
    """Block-character POTATUI logo with a sweeping color-wave animation."""

    DEFAULT_CSS = """
    AnimatedLogo {
        width: 55;
        height: auto;
        align: center middle;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._frame: int = 0

    def on_mount(self) -> None:
        self.set_interval(1 / 15, self._tick)

    def _tick(self) -> None:
        self._frame += 1
        self.refresh()

    def render(self) -> Text:
        text = Text(no_wrap=True)
        f = self._frame

        # --- Logo ---
        t = f / 15.0
        base_hue = (f * 0.6) % 360.0
        for line in LOGO_LINES:
            text.append(line + "\n")

        # --- Plasma sine wave visualiser (single row) ---
        text.append("\n")
        for i in range(_WAVE_WIDTH):
            x = i / _WAVE_WIDTH
            v = (
                math.sin(x * math.pi * 4 + t * 3.0) * 0.50
                + math.sin(x * math.pi * 7 + t * 1.7) * 0.30
                + math.sin(x * math.pi * 2 + t * 5.0) * 0.20
            )
            h = (v + 1.0) / 2.0
            bar = _WAVE_BARS[int(h * (len(_WAVE_BARS) - 1))]
            # Wave hue follows the same drifting base, offset by position and height
            hue = (base_hue + x * 360.0 * 0.6 + h * 60.0) % 360.0
            light = 28.0 + 44.0 * h
            sat = 80.0 + 15.0 * h
            text.append(bar, style=_hsl_hex(hue, sat, light))
        text.append("\n")

        # --- Subtitle ---
        text.append("\n")
        pad = " " * max(0, (_WAVE_WIDTH - len(SUBTITLE)) // 2)
        text.append(pad + SUBTITLE, style="#888888")

        return text


class ResumeScreen(Screen):
    """Shown on startup when saved sessions exist."""

    BINDINGS = [
        Binding("n", "new_activation", "New Activation"),
        Binding("escape", "new_activation", "New Activation"),
    ]

    CSS = """
    ResumeScreen {
        layout: vertical;
        background: $surface-darken-1;
        align: center top;
    }

    #logo-panel {
        width: 88;
        height: auto;
        align: center middle;
        margin-top: 1;
        margin-bottom: 1;
    }

    #session-panel {
        width: 88;
        height: auto;
        border: double $primary;
        background: $surface;
        padding: 1 2;
        margin-bottom: 1;
    }

    #resume-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #resume-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    DataTable {
        height: 12;
        margin-bottom: 1;
    }

    #btn-row {
        height: auto;
        align: right middle;
        margin-top: 1;
    }
    """

    def __init__(self, config: Config, sessions: list[SavedSessionMeta]) -> None:
        super().__init__()
        self.config = config
        self.sessions = sessions

    def compose(self) -> ComposeResult:
        with Container(id="logo-panel"):
            yield AnimatedLogo()
        with Container(id="session-panel"):
            yield Static("Resume Activation", id="resume-title")
            yield Static(
                "Select a session to resume, or start a new activation.",
                id="resume-subtitle",
            )
            yield DataTable(id="session-table", cursor_type="row")
            with Horizontal(id="btn-row"):
                yield Button("Resume Selected", variant="primary", id="btn-resume")
                yield Button("New Activation", id="btn-new")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#session-table", DataTable)
        table.add_columns("Date", "Station", "Operator", "Parks", "QSOs")
        for meta in self.sessions:
            parks = ", ".join(meta.park_refs)
            table.add_row(
                meta.display_date,
                meta.station_callsign,
                meta.operator,
                parks,
                str(meta.qso_count),
            )
        table.focus()

    @on(Button.Pressed, "#btn-resume")
    def on_resume(self) -> None:
        self._resume_selected()

    @on(Button.Pressed, "#btn-new")
    def on_new(self) -> None:
        self.action_new_activation()

    @on(DataTable.RowSelected)
    def on_row_selected(self) -> None:
        self._resume_selected()

    def _resume_selected(self) -> None:
        table = self.query_one("#session-table", DataTable)
        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(self.sessions):
            return
        meta = self.sessions[row_idx]
        self._load_and_launch(meta)

    @work
    async def _load_and_launch(self, meta: SavedSessionMeta) -> None:
        try:
            session = Session.load_json(str(meta.path))
        except Exception as e:
            self.notify(f"Failed to load session: {e}", severity="error")
            return

        from potatui.pota_api import lookup_park
        from potatui.screens.logger import LoggerScreen

        park_names: dict[str, str] = {}
        for ref in session.park_refs:
            info = await lookup_park(ref, self.config.pota_api_base)
            park_names[ref] = info.name if info else ""

        freq_khz = 14200.0
        mode = "SSB"
        if session.qsos:
            last = session.qsos[-1]
            freq_khz = last.freq_khz
            mode = last.mode

        self.notify(
            f"Resumed {session.station_callsign} @ {session.active_park_ref} — {len(session.qsos)} QSOs",
            severity="information",
        )
        self.app.push_screen(
            LoggerScreen(
                session=session,
                config=self.config,
                park_names=park_names,
                freq_khz=freq_khz,
                mode=mode,
            )
        )

    def action_new_activation(self) -> None:
        from potatui.screens.setup import SetupScreen
        self.app.push_screen(SetupScreen(self.config, dismissable=True))
