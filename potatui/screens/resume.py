"""Session resume screen — pick a saved session to continue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from potatui.config import Config
from potatui.session import Session


@dataclass
class SavedSessionMeta:
    path: Path
    operator: str
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
            sessions.append(SavedSessionMeta(
                path=p,
                operator=data.get("operator", "?"),
                park_refs=data.get("park_refs", []),
                start_time=data.get("start_time", ""),
                qso_count=len(data.get("qsos", [])),
            ))
        except Exception:
            continue
    return sessions


class ResumeScreen(Screen):
    """Shown on startup when saved sessions exist."""

    BINDINGS = [
        Binding("n", "new_activation", "New Activation"),
        Binding("escape", "new_activation", "New Activation"),
    ]

    CSS = """
    ResumeScreen {
        align: center middle;
    }

    #resume-container {
        width: 80;
        height: auto;
        max-height: 90vh;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
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
        height: 15;
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
        yield Header(show_clock=True)
        with Container(id="resume-container"):
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
        table.add_columns("Date", "Operator", "Parks", "QSOs", "File")
        for meta in self.sessions:
            parks = ", ".join(meta.park_refs)
            table.add_row(
                meta.display_date,
                meta.operator,
                parks,
                str(meta.qso_count),
                meta.path.name,
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

    def _load_and_launch(self, meta: SavedSessionMeta) -> None:
        try:
            session = Session.load_json(str(meta.path))
        except Exception as e:
            self.notify(f"Failed to load session: {e}", severity="error")
            return

        from potatui.screens.logger import LoggerScreen

        # Restore freq/mode from last QSO if available
        freq_khz = 14200.0
        mode = "SSB"
        if session.qsos:
            last = session.qsos[-1]
            freq_khz = last.freq_khz
            mode = last.mode

        self.notify(
            f"Resumed {session.operator} @ {session.active_park_ref} — {len(session.qsos)} QSOs",
            severity="information",
        )
        self.app.push_screen(
            LoggerScreen(
                session=session,
                config=self.config,
                park_names={ref: "" for ref in session.park_refs},
                freq_khz=freq_khz,
                mode=mode,
            )
        )

    def action_new_activation(self) -> None:
        from potatui.screens.setup import SetupScreen
        self.app.push_screen(SetupScreen(self.config))
